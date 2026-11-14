"""The mods page's logic: the engine's own mod loader (host/mods.c) reads <game>\\mods in the layout emulators use, any folder
that holds a romfs (or exefs) folder is a mod, and a folder whose name starts with '_' or '-' is off. This lists them, turns
them on and off by that name, and adds a mod from a folder or a .zip. Nothing here deletes a mod: off, or the folder itself.
exefs patches are listed but the engine leaves them out (its code is compiled ahead of time)."""
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

OFF = ('_', '-')


def mods_root(game):
    return Path(game) / 'mods'


def _is_mod(d):
    return (d / 'romfs').is_dir() or (d / 'exefs').is_dir()


def list_mods(root, count_files=True):
    """[dict(name, path, enabled, romfs, exefs, files, bytes)], sorted by path as the engine orders them (the last wins)"""
    root = Path(root)
    found = []

    def walk(d, depth, on):
        if depth > 6:
            return
        try:
            subs = sorted(p for p in d.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return
        for p in subs:
            enabled = on and not p.name.startswith(OFF)
            if _is_mod(p):
                files = size = 0
                for base, _, names in os.walk(p / 'romfs') if count_files else ():
                    for n in names:
                        files += 1
                        try:
                            size += (Path(base) / n).stat().st_size
                        except OSError:
                            pass
                found.append(dict(name=p.name.lstrip(''.join(OFF)) or p.name, path=p, enabled=enabled,
                                  romfs=(p / 'romfs').is_dir(), exefs=(p / 'exefs').is_dir(), files=files, bytes=size))
            elif p.name.lower() not in ('romfs', 'exefs'):
                walk(p, depth + 1, enabled)
    if root.is_dir():
        walk(root, 0, True)
    return found


def set_enabled(path, on):
    """on/off by the folder's name ('_' in front: off). Returns the new path"""
    path = Path(path)
    bare = path.name.lstrip(''.join(OFF)) or path.name
    new = path.with_name(bare if on else '_' + bare)
    if new == path:
        return path
    if new.exists():
        raise FileExistsError(f'{new.name} exists already')
    path.rename(new)
    return new


def _safe_extract(zf, dest):
    dest = Path(dest).resolve()
    for info in zf.infolist():
        target = (dest / info.filename).resolve()
        if dest != target and dest not in target.parents:
            raise ValueError(f'unsafe path in the archive: {info.filename}')
    zf.extractall(dest)


def _free_name(root, name):
    name = ''.join(c for c in name if c not in '<>:"/\\|?*').strip() or 'mod'
    candidate, n = name, 2
    while (root / candidate).exists() or (root / ('_' + candidate)).exists():
        candidate, n = f'{name} ({n})', n + 1
    return candidate


def add_mod(source, root):
    """a mod folder or .zip copied into root: one holding romfs/exefs at its top becomes one mod named after it; one holding
    mod folders adds each. Returns the names added; ValueError when there is no mod in it"""
    source, root = Path(source), Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='.adding-') as tmp:
        tmp = Path(tmp)
        if source.is_file() and source.suffix.lower() == '.zip':
            with zipfile.ZipFile(source) as zf:
                _safe_extract(zf, tmp / 'x')
            top = tmp / 'x'
            stem = source.stem
        elif source.is_dir():
            top, stem = source, source.name
        else:
            raise ValueError('a folder or a .zip file')
        # (a zip often wraps everything in one folder: look inside it)
        while not _is_mod(top):
            subs = [p for p in top.iterdir() if p.is_dir()] if top.is_dir() else []
            if len(subs) == 1 and not any(p.is_file() for p in top.iterdir()):
                top = subs[0]
                stem = top.name
            else:
                break
        if _is_mod(top):
            pieces = [(top, stem)]
        else:
            pieces = [(m['path'], m['path'].name) for m in list_mods(top)]
        if not pieces:
            raise ValueError('no mod in it (a mod is a folder that holds a romfs folder)')
        added = []
        for path, name in pieces:
            name = _free_name(root, name)
            shutil.copytree(path, root / name)
            added.append(name)
        return added
