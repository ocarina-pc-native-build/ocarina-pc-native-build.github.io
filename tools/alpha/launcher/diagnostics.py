"""Bounded per-run diagnostics. No full environment, keys, saves or memory dumps."""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import time
import uuid
import struct
import performance
import crash_symbols

ENV_KEYS = ('PROTON_VERSION', 'WINEVERSION', 'SteamGameId', 'SteamAppId', 'DXVK_VERSION',
            'HOS_HEADLESS', 'HOS_FPS_MAX', 'HOS_AUDIO_TRACE', 'RX_VK_CAP_PREWARM',
            'RX_VK_CAP_SPARE_MB', 'OCR_RAM_RESERVE_MB', 'OCR_DIAGNOSTICS', 'HOS_NATIVE_ZSTD')


def binary_identity(path, cache):
    """Hash each exact binary once per size/mtime; never package executable bytes."""
    path = Path(path)
    try:
        stat = path.stat()
        stamp = [str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
        old = cache.get(path.name, {})
        if old.get('stamp') == stamp:
            return old['identity']
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            stream.seek(0)
            header = stream.read(4096)
        result = dict(name=path.name, bytes=stat.st_size, sha256=digest)
        if header[:2] == b'MZ':
            pe = struct.unpack_from('<I', header, 0x3c)[0]
            if header[pe:pe+4] == b'PE\0\0':
                result.update(machine=struct.unpack_from('<H', header, pe+4)[0],
                              pe_timestamp=struct.unpack_from('<I', header, pe+8)[0],
                              image_base=struct.unpack_from('<Q', header, pe+24+24)[0])
        cache[path.name] = dict(stamp=stamp, identity=result)
        return result
    except (OSError, ValueError, struct.error) as exc:
        return dict(name=path.name, unavailable=type(exc).__name__)


def identities(game, folder):
    cache_file = Path(folder) / 'binary-identities-cache.json'
    try:
        cache = json.loads(cache_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        cache = {}
    result = [binary_identity(Path(game) / name, cache) for name in ('ocarina_reborn.exe', 'ocarina_reborn_vk.dll')]
    try:
        cache_file.write_text(json.dumps(cache, indent=2), encoding='utf-8')
    except OSError:
        pass
    return result


def mod_inventory(game):
    import mods_manager
    try:
        return [dict(name=m['path'].name, enabled=bool(m.get('enabled')), romfs=m.get('romfs'), exefs=m.get('exefs'))
                for m in mods_manager.list_mods(Path(game) / 'mods', count_files=False)][:100]
    except (OSError, ValueError):
        return []


def runtime_info(env):
    wine = None
    if os.name == 'nt':
        try:
            import ctypes
            fn = ctypes.CDLL('ntdll').wine_get_version
            fn.restype = ctypes.c_char_p
            wine = fn().decode('utf-8', 'replace')[:200]
        except (AttributeError, OSError):
            pass
    return dict(platform=platform.platform(), wine_version=wine,
                environment={k: str(env[k])[:200] for k in ENV_KEYS if k in env})


def tail(path, limit=65536):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - limit))
            data = stream.read(limit)
        return data.decode('utf-8', 'replace')
    except OSError:
        return ''


def log_fingerprints(game):
    result = {}
    for name in ('ocarina_reborn_log.txt', 'hookshot_log.txt'):
        try:
            stat = (Path(game) / name).stat()
            result[name] = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        except OSError:
            pass
    return result


def start(folder, game, build, settings, hardware, env):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = 'run-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    path = folder / (name + '.json')
    native = folder / (name + '-native.txt')
    timeline = folder / (name + '-timeline.jsonl')
    env['OCR_CRASH_FILE'] = str(native.resolve())
    env['OCR_TRACE_FILE'] = str(timeline.resolve())
    env['OCR_RUN_ID'] = name
    env.setdefault('OCR_DIAGNOSTICS', '1')
    record = dict(schema=2, run_id=name, started=datetime.datetime.now().astimezone().isoformat(),
                  build=build, settings=settings, hardware=hardware, runtime=runtime_info(env),
                  state='running', native_report=native.name, timeline=timeline.name,
                  binaries=identities(game, folder), mods=mod_inventory(game))
    record['symbol_indexes'] = crash_symbols.retain(game, folder, record['binaries'])
    try:
        ready = json.loads((Path(game) / 'ready.json').read_text(encoding='utf-8'))
        record['game_build'] = {k: ready[k] for k in ('built_by', 'version', 'commit') if k in ready}
    except (OSError, ValueError):
        pass
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    return dict(path=path, native=native, timeline=timeline, record=record, clock=time.monotonic(), logs_before=log_fingerprints(game))


def finish(run, code, game):
    record = run['record']
    record.update(state='finished', exit_code=code, exit_hex=f'{code & 0xffffffff:#x}',
                  seconds=round(time.monotonic() - run['clock'], 3))
    changed = [name for name, stat in log_fingerprints(game).items() if run['logs_before'].get(name) != stat]
    record['runtime_log_updated'] = bool(changed) and 'launch_error' not in record
    text = tail(Path(game) / changed[0]) if record['runtime_log_updated'] else ''
    # Preserve the current run's evidence before later starts rotate the game logs.
    record['last_runtime_lines'] = text.splitlines()[-150:]
    native = tail(run['native'])
    record['native_failure_recorded'] = 'FAILURE: ' in native
    if record['native_failure_recorded']:
        run['path'].with_name(run['path'].stem + '-resolved.txt').write_text(
            crash_symbols.resolve(native, run['path'].parent, record), encoding='utf-8')
    record['timeline_available'] = run['timeline'].is_file()
    record['timeline_summary'] = timeline_summary(run['timeline'])
    try:
        import game_settings
        options = game_settings.read(game)
        record['settings_at_exit'] = {k: options.get(k, game_settings.DEFAULTS.get(k, 'game default'))
                                      for k in record.get('settings') or {}}
    except (OSError, ValueError):
        record['settings_at_exit'] = None
    record['gpu_errors'] = performance.gpu_failures(text.splitlines())
    if 'launch_error' in record:
        record['result'] = 'launch_failed'
    elif code == 0:
        record['result'] = 'runtime_errors_on_exit' if any(record['gpu_errors'].values()) else 'normal_exit'
    elif record['native_failure_recorded']:
        record['result'] = 'native_failure_recorded'
    elif 'FATAL:' in text or 'CRASH:' in text:
        record['result'] = 'runtime_failure_recorded'
    else:
        record['result'] = 'nonzero_exit_without_recorded_cause'
    if code == 3:
        record['note'] = 'Exit 3 alone does not identify a Vulkan, memory or driver failure.'
    run['path'].write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
    # Keep the last 20 runs, including their paired native report.
    for old in sorted(run['path'].parent.glob('run-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[20:]:
        try:
            old.unlink()
            old.with_name(old.stem + '-native.txt').unlink(missing_ok=True)
            old.with_name(old.stem + '-timeline.jsonl').unlink(missing_ok=True)
            old.with_name(old.stem + '-timeline.jsonl.previous.jsonl').unlink(missing_ok=True)
            old.with_name(old.stem + '-resolved.txt').unlink(missing_ok=True)
        except OSError:
            pass


def timeline_summary(path):
    samples, incidents, malformed, capped = {}, [], 0, False
    ended = False
    try:
        if Path(path).stat().st_size > 8 * 1024 * 1024:
            return {'unavailable': 'timeline exceeds expected size limit'}
        with Path(path).open(encoding='utf-8', errors='replace') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError('expected object')
                    if row.get('type') == 'sample':
                        if not isinstance(row['seq'], int):
                            raise ValueError('expected sample sequence')
                        samples[row['seq']] = row
                    elif row.get('type') == 'incident':
                        incidents.append({k: row[k] for k in ('t_ms', 'reason') if k in row})
                    elif row.get('type') in ('limit', 'continuation'):
                        capped = True
                    elif row.get('type') == 'end':
                        ended = True
                except (ValueError, TypeError, KeyError):
                    malformed += 1
    except OSError:
        return {'unavailable': 'no timeline; engine may predate diagnostics or collection was disabled'}
    rows = list(samples.values())
    def maximum(key):
        values = (r.get(key, 0) for r in rows)
        return max((v for v in values if isinstance(v, (int, float)) and math.isfinite(v)), default=0)
    return dict(coverage='Retained snapshots, not whole-session FPS statistics. Duplicate history samples removed.',
                samples=len(rows), incidents=incidents[:200], malformed_lines=malformed, size_limit_reached=capped,
                graceful_recorder_end=ended, previous_segment_available=Path(str(path) + '.previous.jsonl').is_file(),
                largest_recorded_frame_ms=maximum('worst_ms'), dropped_frames=maximum('dropped_frames'),
                dropped_events=maximum('dropped_events'), largest_sampler_work_ms=maximum('sample_work_ms'),
                largest_writer_work_ms=maximum('previous_writer_work_ms'))


def package_files(crash, game):
    for path in sorted(Path(crash).glob('*'), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
        if path.is_file() and path.name.startswith(('run-', 'crash-', 'stderr-')) and path.suffix in ('.txt', '.json', '.jsonl') and path.stat().st_size <= 8 * 1024 * 1024:
            yield path, 'crash/' + path.name
    # Direct game launches have no launcher-supplied report path.
    for path in sorted(Path(game).glob('ocarina_reborn_crash_*.txt'), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        if path.stat().st_size <= 2 * 1024 * 1024:
            yield path, 'crash/native/' + path.name
