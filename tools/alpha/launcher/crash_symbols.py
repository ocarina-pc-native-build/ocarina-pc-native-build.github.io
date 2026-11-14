"""Resolve recorded module-relative stacks only against the exact binary hash."""
import bisect
import json
from pathlib import Path
import re
import shutil

MAX_INDEX = 16 * 1024 * 1024


def retain(game, folder, identities):
    kept = []
    for binary in identities:
        sha = binary.get('sha256')
        if not sha:
            continue
        source = Path(game) / (binary['name'] + '.symbols.json')
        try:
            if source.is_symlink() or source.stat().st_size > MAX_INDEX:
                continue
            data = json.loads(source.read_text(encoding='utf-8'))
            if data.get('binary_sha256') != sha or data.get('module') != binary['name']:
                continue
            dest = Path(folder) / ('symbols-' + sha[:16] + '-' + binary['name'] + '.json')
            if not dest.exists():
                shutil.copy2(source, dest)
            kept.append(dest.name)
        except (OSError, ValueError, AttributeError):
            continue
    for old in sorted(Path(folder).glob('symbols-*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)[20:]:
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass
    return kept


def resolve(native, folder, record):
    modules = {}
    for name in record.get('symbol_indexes', []):
        if Path(name).name != name:
            continue
        try:
            path = Path(folder) / name
            if path.stat().st_size > MAX_INDEX:
                continue
            index = json.loads(path.read_text(encoding='utf-8'))
            expected = next((b.get('sha256') for b in record['binaries'] if b.get('name') == index.get('module')), None)
            if not expected or expected != index.get('binary_sha256'):
                continue
            functions = sorted(index['functions'])
            modules[index['module'].lower()] = ([f[0] for f in functions], functions)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    output = ['Function lookup for run ' + record.get('run_id', '?'),
              'Nearest named function, not a source line. Unwound frames may be incomplete. Exact binary SHA256 required.']
    for line in native.splitlines():
        match = re.fullmatch(r'(.+\.(?:exe|dll))\+(0x[0-9a-fA-F]+)', line.strip())
        if not match:
            continue
        module, offset = match[1], int(match[2], 16)
        entry = modules.get(module.lower())
        if not entry:
            output.append(line + ' -> no matching function index')
            continue
        addresses, functions = entry
        i = bisect.bisect_right(addresses, offset)-1
        if i < 0:
            output.append(line + ' -> outside named functions')
        else:
            address, name = functions[i]
            output.append(line + ' -> nearest ' + name + f'+0x{offset-address:x}')
    return '\n'.join(output) + '\n'
