"""Exercise the production photo state without a game, GPU or personal saves."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows photo menu')
class PhotoTools(unittest.TestCase):
    def test_lifecycle_capture_failure_and_scene_exit(self):
        compiler = shutil.which('clang++')
        if not compiler:
            self.skipTest('clang++ required')
        with tempfile.TemporaryDirectory(prefix='ocr-photo-test-') as directory:
            folder = Path(directory)
            source = folder / 'test.cpp'
            source.write_text(HARNESS)
            exe = folder / 'test.exe'
            build = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                    '-I', str(ROOT / 'gpu/vk'), str(source), '-o', str(exe)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <string>
#include "vk_paths.h"
namespace mkwvk {
int64_t clock_ns = 1000000000;
int64_t prof_now() { return clock_ns; }
void logf(const char*, ...) {}
}
#include "ocr_photo_menu.h"
namespace mkwvk {
int shots = 0, accept = 1;
std::string last_path;
void (*completion)(void*, int64_t, int);
int photo_ask_next(const char* path, void (*done)(void*, int64_t, int), void*) {
    assert(std::filesystem::exists(std::filesystem::path(path).parent_path()));
    assert(last_path != path); last_path = path;
    ++shots; completion = done; return accept;
}
}
int main() {
    using namespace mkwvk;
    using namespace mkwvk::photo_tools;
    toggle(true, 110); assert(!active); // title screen
    availability(1); toggle(true, 110); assert(active && lens == 110);
    lens = 70; toggle(true, 120); assert(lens == 70); // do not reset an active lens
    request_capture(); request_capture();
    tick(true); tick(true); assert(shots == 0);
    tick(true); assert(shots == 1 && shot_status == 2);
    request_capture(); tick(true); assert(shots == 1); // only one photo in flight
    completion(nullptr, 1, 1); assert(shot_status == 3);
    request_capture(); tick(true); availability(0); tick(true);
    assert(!active && shots == 1 && shot_status == -1); // loading cancels queued photo
    availability(1); toggle(true, 100); accept = 0;
    request_capture(); tick(true); tick(true); tick(true);
    assert(shots == 2 && shot_status == -1); // queue/renderer failure permits retry
    accept = 1; request_capture(); tick(true); tick(true); tick(true);
    completion(nullptr, 2, 0); assert(shot_status == -1);
    tick(false); assert(!active); // disabling tools restores ordinary camera/HUD
    availability(1); toggle(true, 100); clock_ns += 300000001;
    tick(true); assert(!active && !ready()); // lost player heartbeat
}
'''

if __name__ == '__main__':
    unittest.main()
