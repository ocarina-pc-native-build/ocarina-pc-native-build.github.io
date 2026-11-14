"""Exercise the exact renderer-injected guard against simulated Windows pressure (no GPU)."""
import importlib.util
import ast
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sys

ALPHA = Path(__file__).resolve().parents[1]
ROOT = ALPHA.parents[1]
sys.path.insert(0, str(ALPHA / 'launcher'))
import advisor
import performance
spec = importlib.util.spec_from_file_location('engine_memory_guard', ALPHA / 'engine_v21.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class MemoryDiagnosis(unittest.TestCase):
    def test_host_oom_without_fps_is_not_lost(self):
        for line in ['[hos host] vk: submit 2578729 failed (-1)',
                     '[hos host] vk: batched submit 42 failed (-1)',
                     '[hos host] vk: segment submit 42 failed (-1)',
                     'vk: FATAL: GPU queue submission failed: VK_ERROR_OUT_OF_HOST_MEMORY (-1).',
                     '[hos Resource Memory] mem: commit of 0x10000 bytes went through after 2 retries (Windows grew the page file)']:
            with self.subTest(line=line):
                self.assertEqual(performance.memory_events([line]), 1)
                result = advisor.diagnose([line], de=False)
                self.assertEqual(result[0][0], 'warn')
                self.assertIn('RAM guard to Strong', result[0][1])

    def test_unknown_error_or_shader_failure_is_not_host_oom(self):
        lines = ['vk: submit 10 failed (-13)', 'vk: rejected compute 1234',
                 'programs translated 0, failed 0 (all: 10)']
        self.assertEqual(performance.memory_events(lines), 0)
        self.assertEqual(advisor.diagnose(lines), [])

    def test_launcher_session_filter_keeps_memory_failures(self):
        # Run the production log reader without importing Tk or initializing the launcher.
        tree = ast.parse((ALPHA / 'launcher/launcher.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if
                 (isinstance(n, ast.FunctionDef) and n.name == 'session_from_game_log') or
                 (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SESSION_KEEP' for t in n.targets))]
        scope = dict(Path=Path, performance=performance)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<launcher log reader>', 'exec'), scope)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'ocarina_reborn_log.txt').write_text(
                '[hos host] vk: submit 2578729 failed (-1)\n'
                '[hos Resource Memory] mem: commit of 0x10000 bytes went through after 2 retries (Windows grew the page file)\n',
                encoding='utf-8')
            session = scope['session_from_game_log'](directory)
        self.assertEqual(performance.memory_events(session), 2)
        self.assertIn('RAM guard to Strong', advisor.diagnose(session, de=False)[0][1])

    def test_oom_survives_good_average_fps(self):
        from test_performance import sample
        lines = [sample(frames=300, cpu=5, gpu=7)] * 6 + ['vk: submit 23 failed (-1)']
        summary = performance.summarize(iter(lines))
        self.assertEqual(summary['host_memory_events'], 1)
        self.assertEqual(summary['fps'], 60)
        self.assertIn('Windows memory was exhausted', performance.describe(summary, False)[0][1])


@unittest.skipUnless(os.name == 'nt', 'Windows renderer')
class NativeMemoryGuard(unittest.TestCase):
    def test_pressure_cap_and_recovery(self):
        candidates = [ROOT / 'build/alpha/stage/engine/llvm-mingw/bin/clang++.exe',
                      ROOT / 'build/alpha/hookshot-v2.2.0-rc.1/tools/llvm-mingw/bin/clang++.exe']
        compiler = next((str(p) for p in candidates if p.is_file()), None) or shutil.which('clang++')
        if not compiler:
            self.skipTest('clang++ needed for native test')
        with tempfile.TemporaryDirectory(prefix='ocr-memory-test-') as directory:
            tmp = Path(directory)
            source = HARNESS.replace('/* GUARD */', engine.RAM_GUARD)
            (tmp / 'test.cpp').write_text(source, encoding='utf-8')
            exe = tmp / 'test.exe'
            built = subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                                    '-static', str(tmp / 'test.cpp'), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            for case in ['off-cap', 'off-commit', 'off-ram', 'manual', 'healthy', 'unavailable', 'floor', 'recovery']:
                with self.subTest(case=case):
                    env = dict(os.environ)
                    env.pop('RX_VK_TEX_MAX_MB', None)
                    env['OCR_RAM_RESERVE_MB'] = '0' if case.startswith('off-') else '1024'
                    ran = subprocess.run([str(exe), case], env=env, capture_output=True, text=True, timeout=10)
                    self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


HARNESS = r'''
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <cassert>
struct MEMORYSTATUSEX {
    unsigned dwLength;
    uint64_t ullTotalPhys, ullAvailPhys, ullAvailPageFile;
};
constexpr uint64_t MB = 1ull << 20, GB = 1ull << 30;
static MEMORYSTATUSEX memory{0, 32*GB, 8*GB, 12*GB};
static bool available = true;
static int manual_gb = 0;
static int GlobalMemoryStatusEx(MEMORYSTATUSEX* out) { *out = memory; return available; }
static int ocr_texture_budget_gb() { return manual_gb; }
static bool vram_usage(uint64_t* used, uint64_t* allowed) { *used = 14*GB; *allowed = 24*GB; return true; }
static void logf(const char*, ...) {}
static uint64_t run(uint64_t budget, uint64_t total_bytes, uint64_t frame_no) {
/* GUARD */
    return budget;
}
int main(int argc, char** argv) {
    assert(argc == 2);
    const char* test = argv[1];
    if (!strcmp(test, "off-cap")) {
        memory.ullTotalPhys = 16*GB;
        assert(run(12*GB, 6*GB, 10) == memory.ullTotalPhys/5*2);
    } else if (!strcmp(test, "off-commit")) {
        memory.ullAvailPageFile = 128*MB;
        assert(run(12*GB, 6*GB, 10) < 6*GB);
    } else if (!strcmp(test, "off-ram")) {
        memory.ullAvailPhys = 512*MB;
        assert(run(12*GB, 6*GB, 10) < 6*GB);
    } else if (!strcmp(test, "manual")) {
        memory.ullTotalPhys = 16*GB; manual_gb = 12;
        assert(run(12*GB, 6*GB, 10) == 12*GB);
        memory.ullAvailPageFile = 128*MB;
        assert(run(12*GB, 6*GB, 20) < 6*GB);
    } else if (!strcmp(test, "healthy")) {
        assert(run(8*GB, 6*GB, 10) == 8*GB);
    } else if (!strcmp(test, "unavailable")) {
        available = false;
        assert(run(12*GB, 6*GB, 10) == 12*GB);
    } else if (!strcmp(test, "floor")) {
        memory.ullAvailPageFile = 0;
        for (uint64_t frame=10; frame<=2000; frame+=10)
            assert(run(GB, GB, frame) == GB); // never increase a small caller budget or underflow
    } else if (!strcmp(test, "recovery")) {
        memory.ullAvailPageFile = 0;
        auto first = run(8*GB, 6*GB, 600);
        auto held = run(8*GB, first, 890);
        assert(held < first);
        memory.ullAvailPageFile = 8*GB;
        assert(run(8*GB, held, 901) == held); // last log was 600, last pressure was 890
        assert(run(8*GB, held, 1189) == held);
        assert(run(8*GB, held, 1190) == held + 128*MB);
        assert(run(8*GB, held, 1200) == held + 128*MB);
    } else return 2;
    puts("memory policy OK");
}
'''
