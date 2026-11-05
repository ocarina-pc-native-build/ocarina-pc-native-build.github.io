"""Stream one verified NUP package directly into the runtime's flat RomFS image."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/dkb/tools'))
from extract_nup import Nup,Zstd,NupError
def pack(source,out,package):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    n=Nup(source);z=Zstd();start=time.monotonic()
    try:
        pkg=n.packages[package];entries=sorted(n.package_files(pkg,'romfs'),key=lambda x:'/'.join(x[0]).encode())
        whole=hashlib.sha256();rows=[];offset=0;seen=set()
        temp=out/'romfs.bin.partial'
        with temp.open('wb') as dest:
            for i,(parts,index) in enumerate(entries):
                rel='/'.join(parts)
                if rel in seen:raise NupError('duplicate RomFS path')
                seen.add(rel)
                name,size,extent,stored,want,codec=n.files[index]
                pad=(-offset)%16;dest.write(bytes(pad));whole.update(bytes(pad));offset+=pad
                h=hashlib.sha256();written=0;n.f.seek(extent)
                def raw():
                    left=stored
                    while left:
                        block=n.f.read(min(left,4<<20))
                        if not block:raise NupError('truncated extent')
                        left-=len(block);yield block
                for block in (raw() if codec==0 else z.stream(n.f,stored)):
                    written+=len(block)
                    if written>size:raise NupError('decompressed size exceeds record')
                    dest.write(block);whole.update(block);h.update(block)
                if written!=size or h.digest()!=want:raise NupError(f'{rel}: size/hash mismatch')
                rows.append(dict(path=rel,offset=offset,size=size));offset+=size
                if i%20000==0:print(f'{i}/{len(entries)} verified; {offset/2**30:.2f} GiB',flush=True)
        manifest=dict(status='pass',source='NUP: table and every RomFS file SHA-256 verified',title_id=f'{pkg.title_id:016x}',version=pkg.display_version,romfs_size=offset,romfs_sha256=whole.hexdigest(),files=rows)
        temp.replace(out/'romfs.bin');(out/'index.json').write_text(json.dumps(manifest),encoding='utf-8')
        print(f'PASS {len(rows)} files, {offset} bytes, {time.monotonic()-start:.1f}s',flush=True)
    finally:n.close()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('nup',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--package',type=int,required=True);a=p.parse_args();pack(a.nup,a.out,a.package)
