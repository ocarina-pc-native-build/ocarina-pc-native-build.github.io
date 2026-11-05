"""Fetch pinned, checksum-verified portable build dependencies. No system-wide installation."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/dkb/tools'))
from make_release import PINS
LLVM=('https://github.com/mstorsjo/llvm-mingw/releases/download/20261104/llvm-mingw-20261104-ucrt-x86_64.zip',
      '552191b5754c49a5a20723276a6fc56541ea1922c4c50b7b669022333fc1b40f')

def setup(dest):
    import zstandard
    dest=Path(dest).resolve();dest.mkdir(parents=True,exist_ok=True)
    pins={'llvm':LLVM,**{n:PINS[n] for n in ['sdl3-devel','vulkan-headers']}}
    for name,(url,want) in pins.items():
        folder=dest/name;archive=dest/url.rsplit('/',1)[1]
        if not archive.exists():
            partial=archive.with_suffix(archive.suffix+'.part')
            urllib.request.urlretrieve(url,partial)
            with partial.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=want:
                    raise ValueError(f'{name}: download SHA-256 mismatch')
            partial.replace(archive)
        with archive.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=want:raise ValueError(f'{name}: archive SHA-256 mismatch')
        stamp=folder/'.verified'
        if stamp.exists() and stamp.read_text()==want:continue
        folder.mkdir(parents=True,exist_ok=True)
        if archive.suffix=='.zip':
            with zipfile.ZipFile(archive) as z:
                for member in z.namelist():
                    if not (folder/member).resolve().is_relative_to(folder):raise ValueError('Unsafe ZIP path')
                z.extractall(folder)
        elif archive.name.endswith('.zst'):
            with archive.open('rb') as f,zstandard.ZstdDecompressor().stream_reader(f) as stream,tarfile.open(fileobj=stream,mode='r|') as t:
                t.extractall(folder,filter='data')
        else:
            with tarfile.open(archive) as t:t.extractall(folder,filter='data')
        stamp.write_text(want)
        print(f'{name}: downloaded, hash verified, extracted',flush=True)
    (dest/'dependency-lock.json').write_text(json.dumps(pins,indent=2)+'\n')
    return dest
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'toolchain');a=p.parse_args();setup(a.out)
