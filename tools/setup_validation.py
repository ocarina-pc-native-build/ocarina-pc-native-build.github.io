"""Optional local Khronos validation layer, with pinned MSYS2 runtime dependencies."""
from pathlib import Path
import argparse,hashlib,tarfile,urllib.request
import zstandard
BASE='https://repo.msys2.org/mingw/ucrt64/'
PINS={
 'vulkan-validation-layers-1.4.363.0-1':'b691de206e39130ad21141681540878806750c52f9ae5dfb94eb34caa5b13526',
 'spirv-tools-3~1.4.363.0-1':'d31d67fe918aeee21d1e930fd96360856a60146d23094e4ae8baf071a4049aaa',
 'libwinpthread-14.0.0.r598.ge3d18511f-1':'c35d6be83d141c8cfbb61f1637dd4b53aac8f5562d766aa26d0741c40bad4e4d',
 'libgcc-16.2.0-6':'80b2497f019977dd9528b1abc8621b1328a0115ab1f724047ccbb56bf323f11d',
 'libstdc++-16.2.0-6':'33c5e58a85a538cf843a8672991cce591f0231d66da3b66a57629712d64be17f',
}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'toolchain/validation');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    for component,want in PINS.items():
        name='mingw-w64-ucrt-x86_64-'+component+'-any.pkg.tar.zst';path=a.out/name
        if not path.exists():urllib.request.urlretrieve(BASE+name.replace('+','%2B'),path)
        with path.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=want:raise ValueError(f'{name}: SHA-256 mismatch')
        with path.open('rb') as f,zstandard.ZstdDecompressor().stream_reader(f) as s,tarfile.open(fileobj=s,mode='r|') as t:t.extractall(a.out,filter='data')
        print(component,'verified')
    print('Set VK_LAYER_PATH and prepend PATH to:',(a.out/'ucrt64/bin').resolve())
if __name__=='__main__':main()
