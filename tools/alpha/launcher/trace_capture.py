"""Explicit, short WPR capture in a private named session. Never touches other traces."""
import ctypes
import datetime
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


def available():
    if os.name != 'nt':
        return None, 'Windows Performance Recorder is only available on Windows.'
    executable = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/wpr.exe'
    if not executable.is_file():
        return None, 'Windows Performance Recorder is not installed.'
    if not ctypes.windll.shell32.IsUserAnAdmin():
        return None, 'For this optional Windows trace, close and run the launcher as administrator. Normal diagnostics do not require this.'
    return executable, None


def record(executable, folder, notify=lambda text: None, run=subprocess.run, sleep=time.sleep):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    instance = 'OcarinaReborn-' + uuid.uuid4().hex
    base = 'trace-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + instance[-8:]
    output = folder / (base + '.etl')
    metadata = dict(schema=1, instance=instance, profile='GeneralProfile.Light', duration_seconds=30,
                    explicitly_requested=True, state='starting', etl=output.name,
                    warning='ETL contains system-wide process/file activity and is shared separately, not in the normal Debug Package.')

    def command(*args):
        return run([str(executable), *args, '-instancename', instance], capture_output=True,
                   text=True, errors='replace', timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    started = False
    try:
        for remaining in range(5, 0, -1):
            notify(f'Switch to the game. Capture starts in {remaining} s.'); sleep(1)
        result = command('-start', 'GeneralProfile.Light')  # memory mode, bounded by WPR profile buffers
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[-1800:])
        started = True
        metadata['started'] = datetime.datetime.now().astimezone().isoformat()
        for remaining in range(30, 0, -1):
            notify(f'Recording: reproduce the problem ({remaining} s remaining).'); sleep(1)
        notify('Saving Windows trace…')
        result = command('-stop', str(output))
        if result.returncode or not output.is_file():
            raise RuntimeError((result.stdout + result.stderr)[-1800:])
        started = False
        metadata.update(state='saved', bytes=output.stat().st_size)
        return output
    except Exception as exc:
        metadata.update(state='failed', error=str(exc))
        raise
    finally:
        if started:
            try:
                command('-cancel')  # always OUR unique instance; never global -cancel
            except Exception as exc:
                metadata['cleanup_error'] = str(exc)
        (folder / (base + '.json')).write_text(json.dumps(metadata, indent=2), encoding='utf-8')
