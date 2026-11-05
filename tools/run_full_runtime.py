"""Run a bounded native game diagnostic, preserving each log and compact preview."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from make_frame_preview import make_preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    parser.add_argument('--logs', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=600)
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--preemption', choices=['0', '1', '2'], default='2')
    parser.add_argument('--trace', default='')
    parser.add_argument('--screenshot', action='store_true')
    args = parser.parse_args()
    if args.frames <= 0 or args.timeout <= 0:
        parser.error('--frames and --timeout must be positive')
    exe, logs = args.exe.resolve(), args.logs.resolve()
    logs.mkdir(parents=True, exist_ok=True)
    stem = logs / ('boot-' + str(time.time_ns()))
    log = stem.with_suffix('.log')
    command = [str(exe), '--frames', str(args.frames)]
    shot = stem.with_suffix('.png') if args.screenshot else None
    if shot:
        command += ['--shot', str(shot)]
    env = dict(os.environ, TOTK_GPU='vulkan', TOTK_ASYNC_PREEMPT=args.preemption)
    if args.trace:
        env['TOTK_TRACE'] = args.trace
    started = time.monotonic()
    with exe.open('rb') as stream:
        exe_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    with log.open('wb') as stream:
        process = subprocess.Popen(command, cwd=exe.parent, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            code = None
    output = log.read_text(errors='replace')
    matches = re.findall(r'boot: frames (\d+) presented \(nvn calls (\d+), distinct (\d+), unimplemented (\d+), '
                         r'validation errors (\d+), shader failures (\d+), draws skipped (\d+)\)', output)
    metrics = dict(zip(('frames', 'nvn_calls', 'nvn_distinct', 'unimplemented', 'validation_errors',
                       'shader_failures', 'draws_skipped'), map(int, matches[-1]))) if matches else {}
    if code is None:
        status, result = 'timeout', 124
    elif code:
        status, result = 'process-failed', 1
    elif metrics.get('frames', 0) < args.frames:
        status, result = 'checkpoint-missing', 2
    elif any(metrics.get(key) for key in ('unimplemented', 'validation_errors', 'shader_failures')):
        status, result = 'checkpoint-with-errors', 2
    else:
        status, result = 'checkpoint-reached', 0
    record = dict(status=status, diagnostic_exit_code=result, process_exit_code=code,
                  elapsed_seconds=round(time.monotonic() - started, 3), command=command,
                  exe_sha256=exe_hash, log=str(log), preemption=args.preemption,
                  validation_requested=env.get('TOTK_VK_VALIDATION') == '1', metrics=metrics,
                  rendering_verified=False)
    if shot:
        record['screenshot_original'] = str(shot)
        if shot.is_file():
            preview = shot.with_name(shot.stem + '-preview.png')
            try:
                record['preview'] = dict(path=str(preview), **make_preview(shot, preview))
            except (OSError, ValueError) as error:
                record['preview_error'] = str(error)
        else:
            record['preview_error'] = 'No screenshot was produced by this run'
    stem.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    return result


if __name__ == '__main__':
    raise SystemExit(main())
