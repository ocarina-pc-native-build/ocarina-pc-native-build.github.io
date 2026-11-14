"""Inject queue errors into all four production submit sites (no GPU needed)."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

RUN_ALL_ARGS = ['--cxx', '{cxx}']
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='g++')
    args = parser.parse_args()
    source = (ROOT / 'gpu/vk/vk_replay.cpp').read_text(encoding='utf-8')
    marker = '[[noreturn]] void submit_failed(VkResult result) {'
    start = source.index(marker)
    end = source.index('\n}\n', start) + 2
    helper = source[start:end]
    sites = []
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if re.search(r'\bres = vkQueueSubmit2\(', line):
            tail = lines[i:i + 9]
            check = next((n for n, value in enumerate(tail)
                          if value.strip() == 'if (res != VK_SUCCESS) submit_failed(res);'), None)
            assert check is not None, 'An unchecked queue submission can leave a fence unsignalled'
            snippet = '\n'.join(tail[:check + 1])
            if 'const VkResult res' not in snippet:
                snippet = 'VkResult res = VK_SUCCESS;\n' + snippet
            sites.append(snippet)
    assert len(sites) == 4, 'Audit any added or removed submission paths'
    fixture = r'''
#include <cstdio>
#include <string>
using VkResult = int;
enum { VK_SUCCESS=0, VK_ERROR_OUT_OF_HOST_MEMORY=-1, VK_ERROR_OUT_OF_DEVICE_MEMORY=-2,
       VK_ERROR_DEVICE_LOST=-4, VK_NULL_HANDLE=0 };
struct Recording { bool submitted=false; int fence=0; unsigned long long value=1; } r;
struct Job { Recording* r; } job{&r}, *j=&job;
struct { int queue=0; } dev;
struct { int done=0; } f;
int si=0, injected=0, submissions=0, lost=0, continued=0;
unsigned long long batch_next=1;
struct Fatal {};
std::string reason;
template<class... A> void logf(const char*, A...) {}
template<class... A> VkResult vkQueueSubmit2(A...) { ++submissions; return injected; }
[[noreturn]] void replay_fatal(const char* why) { reason=why; throw Fatal{}; }
[[noreturn]] void device_lost() { ++lost; throw Fatal{}; }
'''
    fixture += helper + '\n'
    for i, snippet in enumerate(sites):
        fixture += 'void site_%d() {\n%s\n++continued;\n}\n' % (i, snippet)
    fixture += 'int main() { int failed=0;\n'
    for i in range(len(sites)):
        for result in (0, -1, -2, -4, -13):
            expected = {0: '', -1: 'VK_ERROR_OUT_OF_HOST_MEMORY (-1)',
                        -2: 'VK_ERROR_OUT_OF_DEVICE_MEMORY (-2)', -4: '', -13: 'VkResult -13'}[result]
            fixture += (
                'injected=%d; submissions=lost=continued=0; reason.clear();\n'
                'try { site_%d(); } catch (const Fatal&) {}\n'
                'if (submissions!=1 || continued!=%d || lost!=%d || reason.find("%s")==std::string::npos) '
                '{ std::printf("FAIL site %d result %d\\n"); ++failed; }\n'
                % (result, i, int(result == 0), int(result == -4), expected, i, result))
    fixture += 'if (!failed) std::puts("PASS: all four submit paths stop on failure, preserve the result and handle device loss"); return failed ? 1 : 0; }\n'
    with tempfile.TemporaryDirectory(prefix='queue-submit-') as tmp:
        cpp, exe = Path(tmp) / 'test.cpp', Path(tmp) / 'test.exe'
        cpp.write_text(fixture, encoding='utf-8')
        subprocess.run([args.cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)


if __name__ == '__main__':
    main()
