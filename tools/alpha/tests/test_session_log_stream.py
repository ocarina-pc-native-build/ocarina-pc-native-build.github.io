"""Read a large noisy session with bounded RAM and retain beginning/end evidence."""
import ast
import datetime
from pathlib import Path
import sys
import tempfile
import tracemalloc
from types import SimpleNamespace
import unittest

ALPHA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ALPHA / 'launcher'))
import performance
import diagnostics


def reader():
    tree = ast.parse((ALPHA / 'launcher/launcher.py').read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if
             (isinstance(n, ast.FunctionDef) and n.name == 'session_from_game_log') or
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SESSION_KEEP' for t in n.targets))]
    scope = dict(Path=Path, performance=performance)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<session reader>', 'exec'), scope)
    return scope['session_from_game_log']


class SessionStreamTests(unittest.TestCase):
    def test_large_log_keeps_gpu_and_edge_evidence_with_bounded_memory(self):
        read = reader()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ocarina_reborn_log.txt'
            with path.open('w', encoding='utf-8') as f:
                f.write('[hos host] vk: Test GPU, Vulkan 1.3\n')
                noise = 'unrelated game message ' + 'x' * 2000 + '\n'
                for i in range(2000):
                    f.write(noise * 8)
                    f.write('[hos host] [perf] sample %d\n' % i)
                f.write('vk: FATAL: GPU queue submission failed: VK_ERROR_OUT_OF_DEVICE_MEMORY (-2).\n')
            self.assertGreater(path.stat().st_size, 30_000_000)
            tracemalloc.start()
            try:
                lines = read(tmp)
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
        self.assertLess(peak, 2_000_000, 'The source log must not be materialized in memory')
        self.assertEqual(len(lines), 1502)
        self.assertEqual(lines[0], 'Active GPU (Vulkan): Test GPU')
        self.assertEqual(lines[300], '[perf] sample 299')
        self.assertIn('501 lines left out', lines[301])
        self.assertEqual(lines[302], '[perf] sample 801')
        self.assertEqual(performance.gpu_failures(lines)['device_memory_errors'], 1)

    def test_short_session_preserves_all_lines_without_newlines(self):
        read = reader()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'ocarina_reborn_log.txt').write_bytes(
                b'[hos host] [perf] one\r\n[hos host] vk: segment submit 3 failed (-1)\n'
                b'vk: FATAL: GPU queue submission failed: VK_ERROR_OUT_OF_HOST_MEMORY (-1).')
            lines = read(tmp)
        self.assertEqual(len(lines), 4)
        self.assertFalse(any('\n' in line or '\r' in line for line in lines))
        self.assertEqual(performance.memory_events(lines), 2)

    def test_crash_export_reads_only_the_bounded_tail(self):
        tree = ast.parse((ALPHA / 'launcher/launcher.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'crash_info')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / 'ocarina_reborn_log.txt'
            with path.open('wb') as stream:
                stream.write(b'old log contents\n' * 1_000_000)
                stream.write(b'vk: FATAL: GPU queue submission failed: VK_ERROR_OUT_OF_HOST_MEMORY (-1).\n')
            scope = dict(Path=Path, datetime=datetime, diagnostics=diagnostics, DIRS={'CrashDumps': folder},
                         INFO=dict(name='test', version='test', build_id='test', commit='test'), tester_id=lambda: 'test')
            exec(compile(ast.Module(body=[method], type_ignores=[]), '<crash export>', 'exec'), scope)
            tracemalloc.start()
            try:
                scope['crash_info'](SimpleNamespace(cfg={'game_dir': str(folder)}), 3)
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            report = next(folder.glob('crash-info-*.txt')).read_text(encoding='utf-8')
        self.assertLess(peak, 2_000_000)
        self.assertIn('VK_ERROR_OUT_OF_HOST_MEMORY', report)
        self.assertLess(len(report), 256 * 1024 + 1024)


if __name__ == '__main__':
    unittest.main()
