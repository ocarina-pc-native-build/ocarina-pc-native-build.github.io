"""Reviewable bounded text-only export. ETW traces are deliberately shared separately."""
import datetime
import json
import os
from pathlib import Path
import re
import zipfile

FILE_LIMIT = 8 * 1024 * 1024
SYMBOL_LIMIT = 16 * 1024 * 1024  # the complete Windows game function index exceeds 8 MiB
TOTAL_LIMIT = 64 * 1024 * 1024


def recent(paths, root, count):
    found = []
    for path in paths:
        try:
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(Path(root).resolve()):
                continue
            found.append((path.stat().st_mtime_ns, path))
        except OSError:
            continue
    return [p for _, p in sorted(found, reverse=True)[:count]]


def redact(text, replacements):
    for path, alias in sorted(replacements, key=lambda p: len(str(p[0])), reverse=True):
        value = str(path)
        if not value or value == '.':
            continue
        # Plain log paths and JSON-escaped paths; Windows case-insensitive.
        for variant in (value.replace('\\', '\\\\'), value, value.replace('\\', '/')):
            text = re.sub(re.escape(variant), lambda _: alias, text, flags=re.IGNORECASE)
    return text


def candidates(game, folders):
    game = Path(game)
    specs = [
        # Newest evidence from each category before any historical backlog.
        (folders['CrashDumps'], 'crash', ('run-*.json', 'run-*-native.txt', 'run-*-resolved.txt', 'crash-*.txt', 'stderr-*.txt'), 20),
        (folders['Reports'], 'reports', ('performance-*.json', 'reborn-auto-*.json', 'diagnostic-note-*.json', 'trace-*.json'), 10),
        (folders['CrashDumps'], 'crash', ('run-*-timeline.jsonl', 'run-*-timeline.jsonl.previous.jsonl'), 2),
        (folders['Logs'], 'launcher-logs', ('*.log',), 1),
        (game, 'game-logs', ('ocarina_reborn_log*.txt', 'hookshot_log*.txt'), 1),
        (folders['CrashDumps'], 'symbols', ('symbols-*.json',), 2),
        (game, 'crash/native', ('ocarina_reborn_crash_*.txt',), 5),
        (game, 'timeline/direct', ('ocarina_reborn_diagnostics.jsonl', 'ocarina_reborn_diagnostics.jsonl.previous.jsonl'), 2),
        (folders['PrepareLogs'], 'prepare-logs', ('*.log',), 5),
        (folders['Logs'], 'launcher-logs', ('*.log',), 10),
        (game, 'game-logs', ('ocarina_reborn_log*.txt', 'hookshot_log*.txt'), 10),
        (folders['CrashDumps'], 'crash', ('run-*.json', 'run-*-native.txt', 'run-*-resolved.txt', 'run-*-timeline.jsonl', 'run-*-timeline.jsonl.previous.jsonl', 'crash-*.txt', 'stderr-*.txt'), 100),
        (folders['Reports'], 'reports', ('performance-*.json', 'reborn-auto-*.json', 'diagnostic-note-*.json', 'trace-*.json'), 30),
        (folders['CrashDumps'], 'symbols', ('symbols-*.json',), 20),
    ]
    seen = set()
    for root, prefix, patterns, limit in specs:
        root = Path(root)
        paths = {p for pattern in patterns for p in root.glob(pattern)}
        for path in recent(paths, root, limit):
            name = prefix + '/' + path.name
            if name not in seen:
                seen.add(name)
                yield path, name
    # Text shader errors only, bounded; never compiled shaders, recordings or game assets.
    root = Path(folders['ShaderDumps'])
    for path in recent(root.rglob('*.txt'), root, 20):
        if path.is_file() and not path.is_symlink():
            yield path, 'shader-dumps/' + path.relative_to(root).as_posix()
    reports = game / 'bug-reports'
    for path in recent(reports.glob('*/report.txt'), reports, 3):
        if path.is_file() and not path.is_symlink():
            yield path, 'f1-reports/' + path.parent.name + '/report.txt'


def create(destination, game, folders, build, system, settings, note='', replacements=()):
    destination = Path(destination)
    manifest = dict(schema=2, created=datetime.datetime.now().astimezone().isoformat(),
                    per_file_limit=FILE_LIMIT, symbol_file_limit=SYMBOL_LIMIT, total_limit=TOTAL_LIMIT, files=[], omitted=[], notes=[
                        'Observations are not proof of a cause. Stage times overlap; GPU timing can be delayed.',
                        'Timeline sample seq IDs may repeat in incident history; deduplicate by run and seq.',
                        'ETL traces are not included; they may contain system-wide activity and paths.',
                        'No executables, game assets, saves, keys, recordings, or raw memory dumps are included.'])
    total = 0
    temporary = destination.with_name(destination.name + '.partial')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        def write(name, text):
            archive.writestr(name, redact(text, replacements))
        write('build-info.json', json.dumps(build, indent=2))
        write('system.txt', '\n'.join(system))
        write('settings-at-export.json', json.dumps(settings, indent=2))
        write('problem-description.txt', note[:8000] or 'No description supplied. Ask for room/boss/song, steps and the marker time.')
        write('READ-ME.txt', 'Start with problem-description.txt and crash/run-*.json. Match run_id, binary SHA256 and timeline filename.\n'
              'Performance reports are in reports/. Incidents, Ctrl+F8/F1 markers and surrounding samples are in *-timeline.jsonl.\n'
              'Timeline sample times are milliseconds since recorder startup, recorded in the paired run metadata UTC/local start window.\n'
              'Each sample contains interval totals, not per-frame averages. CPU is process-wide CPU time across cores.\n'
              'Stage durations overlap across threads and nested operations; GPU measurements can arrive late. Do not sum them as exclusive frame costs.\n'
              'context_age_ms shows the age of the last game-provided room/event snapshot; it can be stale while loading.\n'
              'Native zstd timing excludes the lifted decompressor. Unknown data is not zero work. Thread phases cover instrumented waits only.\n'
              'No-frame incidents can also reflect loading, a background window or shader preparation; they do not prove deadlock.\n'
              'Exact SHA256-matched function indexes support *-resolved.txt; nearest functions are not source lines or proof of a culprit.\n'
              'Timelines rotate at 8 MiB and retain the two latest segments; .previous.jsonl is the older one.\n'
              'Check package-manifest.json, dropped counters and timeline limit/continuation records before concluding that no error occurred.\n')
        for path, name in candidates(game, folders):
            try:
                size = path.stat().st_size
                if TOTAL_LIMIT-total < 128:
                    manifest['omitted'].append(dict(name=name, reason='package size budget'))
                    continue
                allowance = min(SYMBOL_LIMIT if name.startswith('symbols/') else FILE_LIMIT, TOTAL_LIMIT-total)
                if size > allowance and path.suffix in ('.json', '.jsonl'):
                    manifest['omitted'].append(dict(name=name, reason='structured report exceeds size budget', bytes=size))
                    continue
                with path.open('rb') as stream:
                    if size > allowance:
                        notice = b'\n[DEBUG EXPORT: middle omitted; see manifest]\n'
                        head = min(65536, allowance//2)
                        raw = stream.read(head)
                        stream.seek(size-(allowance-head-len(notice)))
                        raw += notice + stream.read(allowance-head-len(notice))
                    else:
                        raw = stream.read(allowance)
                total += len(raw)
                write(name, raw.decode('utf-8', 'replace'))
                manifest['files'].append(dict(name=name, source_bytes=size, exported_bytes=len(raw), truncated=size>allowance))
            except OSError as exc:
                manifest['omitted'].append(dict(name=name, reason=type(exc).__name__))
        manifest['source_bytes_read'] = total
        write('package-manifest.json', json.dumps(manifest, indent=2))
    os.replace(temporary, destination)
    return manifest
