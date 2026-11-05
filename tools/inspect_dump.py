"""Validate decrypted NSOs before invoking the upstream parser; never execute guest code."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'third_party/dkb/recomp'))
LIMIT = 512 * 1024 * 1024

class InvalidDump(ValueError):
    pass

def inspect_nso(path):
    import lz4.block
    path = Path(path)
    if path.stat().st_size > LIMIT:
        raise InvalidDump(f'{path.name}: module exceeds the 512 MiB inspection limit')
    raw = path.read_bytes()
    if len(raw) < 0x100 or raw[:4] != b'NSO0':
        raise InvalidDump(f'{path.name}: missing NSO0 header or truncated header')
    version, reserved, flags = struct.unpack_from('<III', raw, 4)
    if flags & 0x80:
        raise InvalidDump(f'{path.name}: ZBIC compression; first run tools/normalize_nso.py')
    if version != 0 or reserved or flags & ~0x7f:
        raise InvalidDump(f'{path.name}: unsupported NSO header version/flags')
    segments, mem_ranges, file_ranges = [], [], []
    for i, name in enumerate(('text','rodata','data')):
        off, mem, size = struct.unpack_from('<III', raw, 0x10 + i*0x10)
        stored = struct.unpack_from('<I', raw, 0x60 + i*4)[0] if flags & (1<<i) else size
        if size > LIMIT or mem + size > LIMIT or (size and (off < 0x100 or off + stored > len(raw))):
            raise InvalidDump(f'{path.name}: {name} segment outside file/memory limits')
        if size and not stored:
            raise InvalidDump(f'{path.name}: empty compressed {name} segment')
        for a,b in mem_ranges:
            if size and mem < b and mem + size > a:
                raise InvalidDump(f'{path.name}: overlapping memory segments')
        for a,b in file_ranges:
            if stored and off < b and off + stored > a:
                raise InvalidDump(f'{path.name}: overlapping file segments')
        mem_ranges.append((mem,mem+size))
        file_ranges.append((off,off+stored))
        data = raw[off:off+stored]
        if flags & (1<<i):
            try:
                data = lz4.block.decompress(data, uncompressed_size=size)
            except Exception as exc:
                raise InvalidDump(f'{path.name}: invalid LZ4 {name}') from exc
        if len(data) != size:
            raise InvalidDump(f'{path.name}: incorrect {name} decompressed size')
        digest = hashlib.sha256(data).hexdigest()
        if flags & (1<<(i+3)) and bytes.fromhex(digest) != raw[0xa0+i*32:0xc0+i*32]:
            raise InvalidDump(f'{path.name}: {name} SHA-256 mismatch')
        segments.append(dict(name=name,offset=off,address=mem,size=size,stored=stored,sha256=digest))
    bss = struct.unpack_from('<I', raw, 0x3c)[0]
    if segments[2]['address'] + segments[2]['size'] + bss > LIMIT:
        raise InvalidDump(f'{path.name}: BSS exceeds memory limit')
    return dict(name=path.name,sha256=hashlib.sha256(raw).hexdigest(),build_id=raw[0x40:0x60].hex(),segments=segments,bss_size=bss)

def locate(root):
    root = Path(root)
    if not root.is_dir():
        raise InvalidDump('Expected a decrypted ExeFS directory, not an encrypted package or missing path')
    choices = [root] + [p for p in root.iterdir() if p.is_dir() and p.name.casefold() == 'exefs']
    valid = [p for p in choices if (p/'main').is_file()]
    if len(valid) != 1:
        raise InvalidDump('Expected exactly one ExeFS containing main; select the intended version explicitly')
    return valid[0]

def inspect(root, analyze=False):
    exefs = locate(root)
    report = dict(schema=1, compatibility='unverified', modules=[], diagnostics=[])
    for path in sorted(exefs.iterdir()):
        if not path.is_file():
            continue
        with path.open('rb') as f:
            magic = f.read(4)
        if magic != b'NSO0':
            if path.name in ('main','sdk','rtld') or path.name.startswith('subsdk'):
                raise InvalidDump(f'{path.name}: expected NSO0, found incompatible file')
            continue
        row = inspect_nso(path)
        if analyze:
            from nso import Nso
            from module import Module
            from gen import discover
            from lifter import Unsupported
            from collections import Counter
            # This deeper upstream parser assumes trusted structural metadata. The CLI
            # labels this analysis separately from the bounded segment validation above.
            nso = Nso(str(path))
            mod = Module(path.name, path, 0x7000000000)
            discovery = discover(mod)
            row['function_candidates'] = len(discovery[0])
            row['imports'] = [s[0] for s in nso.imports()]
            row['export_count'] = len(nso.exports())
            row['relocations'] = dict(Counter(r[1] for r in nso.relocs))
            counts = Counter()
            errors = []
            # All text words, including literal pools/padding. Trap words are explicitly
            # separate; successful decoding is not proof that a function can execute.
            for i,w in enumerate(mod.words):
                try:
                    counts[mod.lifter.lift(int(w),mod.lo+i*4).kind] += 1
                except Unsupported as exc:
                    counts['unsupported'] += 1
                    if len(errors)<32:
                        errors.append(dict(offset=i*4,word=f'{int(w):08x}',reason=str(exc)))
            row['instruction_kinds'] = dict(counts)
            row['unsupported_examples'] = errors
        report['modules'].append(row)
    if not any(m['name']=='main' for m in report['modules']):
        raise InvalidDump('main is not an NSO module')
    if not (exefs/'main.npdm').is_file():
        report['diagnostics'].append('main.npdm missing; process metadata not verified')
    else:
        report['npdm_sha256'] = hashlib.sha256((exefs/'main.npdm').read_bytes()).hexdigest()
    report['diagnostics'].append('Build IDs identify content; no supported OoT version registry exists yet')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--analyze',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        result=inspect(a.directory,a.analyze)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(f'Validated {len(result["modules"])} modules. Report: {a.output}')
        return 0
    except (InvalidDump,OSError,ValueError,AssertionError,struct.error) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 2
if __name__=='__main__':
    raise SystemExit(main())
