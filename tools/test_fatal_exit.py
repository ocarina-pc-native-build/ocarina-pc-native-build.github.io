"""Check immediate fatal termination with a live Vulkan device and preserved SDK diagnostics."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    parser.add_argument('--logs', type=Path, required=True)
    args = parser.parse_args()
    exe = args.exe.resolve()
    args.logs.mkdir(parents=True, exist_ok=True)
    log = args.logs / 'fatal-exit.log'
    start = time.monotonic()
    timeout = False
    with log.open('wb') as stream:
        proc = subprocess.Popen([str(exe), '--probe-fatal-exit'], cwd=exe.parent,
            stdout=stream, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            code = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            timeout = True
            proc.kill()
            code = proc.wait()
    output = log.read_text(errors='replace')
    passed = (not timeout and code == 70 and 'Break (the SDK aborted)' in output
              and 'fatal: memory commit:' in output and 'unknown is not implemented' not in output)
    result = dict(passed=passed, exit_code=code, expected_exit_code=70, timeout=timeout,
                  seconds=round(time.monotonic()-start, 3), log=str(log.resolve()))
    (args.logs/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
