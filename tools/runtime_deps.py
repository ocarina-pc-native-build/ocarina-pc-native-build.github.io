"""Prepare pinned libraries for the inherited full Windows host (no global install)."""
from pathlib import Path
import argparse,hashlib,sys,tarfile,urllib.request,shutil,json
import zstandard
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/dkb/tools'))
from make_release import PINS,SDL_VERSION
PINS = {**PINS, 'dav1d': ('https://mirror.msys2.org/mingw/ucrt64/mingw-w64-ucrt-x86_64-dav1d-1.5.4-1-any.pkg.tar.zst',
                        'ccf26c6f29fd36f5692d57fd5e0fe3becec492e0b875fd5e04f47a9582eb8b37')}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--sdl',type=Path,required=True);a=p.parse_args()
    dest=a.out.resolve();cache=dest/'downloads';cache.mkdir(parents=True,exist_ok=True)
    for n in ('include','lib','bin'): (dest/n).mkdir(exist_ok=True)
    sdl=a.sdl.resolve()/f'SDL3-{SDL_VERSION}'/'x86_64-w64-mingw32'
    shutil.copytree(sdl/'include',dest/'include',dirs_exist_ok=True)
    shutil.copy2(sdl/'lib/libSDL3.dll.a',dest/'lib');shutil.copy2(sdl/'bin/SDL3.dll',dest/'bin')
    selected=['opus','libvpx','vulkan-headers','vulkan-loader','vma','zstd','dav1d']
    for name in selected:
        url,want=PINS[name];archive=cache/url.rsplit('/',1)[1]
        if not archive.exists():urllib.request.urlretrieve(url,archive)
        with archive.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=want:raise ValueError(f'{name}: SHA mismatch')
        extracted=cache/name
        with archive.open('rb') as f,zstandard.ZstdDecompressor().stream_reader(f) as stream,tarfile.open(fileobj=stream,mode='r|') as t:t.extractall(extracted,filter='data')
        prefix=extracted/'ucrt64'
        if (prefix/'include').exists():shutil.copytree(prefix/'include',dest/'include',dirs_exist_ok=True)
        libs={'opus':['libopus.dll.a'],'libvpx':['libvpx.a'],'vulkan-headers':[],'vulkan-loader':['libvulkan-1.dll.a'],'vma':[],'zstd':['libzstd.a'],'dav1d':['libdav1d.dll.a']}[name]
        for lib in libs:shutil.copy2(prefix/'lib'/lib,dest/'lib')
        if name=='opus':shutil.copy2(prefix/'bin/libopus-0.dll',dest/'bin')
        if name=='dav1d':shutil.copy2(prefix/'bin/libdav1d-7.dll',dest/'bin')
        print(name,'verified',flush=True)
    (dest/'pins.json').write_text(json.dumps({n:PINS[n] for n in selected},indent=2))
if __name__=='__main__':main()
