# SPDX-License-Identifier: MIT
"""Separate preprocessing tool: validate with nxnative, write uncompressed NSOs for the DKB lifter.

Input remains untouched. Output is local game-derived material, never a release artifact.
ZBIC is an optional externally installed decoder, not part of the native runtime.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/nxnative'))
import nso_reader

def normalize(source,destination):
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Input and output must differ')
    raw=source.read_bytes()
    if len(raw)>512*1024*1024:raise ValueError('Module exceeds 512 MiB limit')
    if len(raw)<0x100 or raw[:4]!=b'NSO0':raise ValueError('Expected NSO0 header')
    memory,size=struct.unpack_from('<II',raw,0x34)
    if memory+size>512*1024*1024:raise ValueError('Decoded image exceeds 512 MiB limit')
    mod=nso_reader.load(raw,source.name)
    # Preserve all metadata/hash fields and offsets within memory; only the file
    # layout and compression bits change. No code or patch address is invented.
    header=bytearray(raw[:0x100]);flags=struct.unpack_from('<I',header,0xc)[0]
    struct.pack_into('<I',header,0xc,flags & ~(0x80|7))
    data=bytearray(header)
    for i,(memory,size) in enumerate(mod.segments):
        struct.pack_into('<I',data,0x10+i*16,len(data))
        struct.pack_into('<I',data,0x60+i*4,size)
        data.extend(mod.image[memory:memory+size])
    # Reparse and compare the complete image before writing the normalized file.
    check=nso_reader.load(data,source.name)
    if check!=mod:raise ValueError('Normalized module changed its decoded contents')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(data)
    return dict(name=source.name,original_sha256=hashlib.sha256(raw).hexdigest(),normalized_sha256=hashlib.sha256(data).hexdigest(),image_sha256=hashlib.sha256(mod.image).hexdigest())

if __name__=='__main__':
    import json,shutil
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('exefs',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.exefs.resolve()==a.out.resolve():p.error('Input and output must differ')
    a.out.mkdir(parents=True,exist_ok=True);report=[]
    for f in sorted(a.exefs.iterdir()):
        if not f.is_file():continue
        with f.open('rb') as stream:magic=stream.read(4)
        if magic==b'NSO0':report.append(normalize(f,a.out/f.name))
        elif f.name=='main.npdm':shutil.copy2(f,a.out/f.name)
    (a.out/'normalization.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'Validated and normalized {len(report)} NSO modules. Input unchanged.')
