"""Link all locally translated modules with the inherited Horizon/NVN2 Windows host."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('exefs','romfs','generated','out','profile','deps','llvm','ninja'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--translator',type=Path,help='Directory containing totk_xlate.exe and totk_xlate.id')
    parser.add_argument('--jobs',type=int,default=4)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.is_relative_to(ROOT) and out.relative_to(ROOT).parts[0] not in ('local','generated','build'):
        parser.error('Game-derived build output inside this repository must be in local/, generated/ or build/')
    # Fail before linking if any decoded instruction still lacks an implementation.
    manifests = list(args.generated.glob('*/manifest.json'))
    if not manifests or not (args.generated/'layout.json').is_file():
        parser.error('No translated module manifests/layout found')
    for path in manifests:
        manifest = json.loads(path.read_text())
        if manifest['stats']['unsupported']:
            parser.error(f'{path.parent.name}: unsupported instructions remain; regenerate first')
    out.mkdir(parents=True,exist_ok=True)
    hashes = {}
    for path in args.exefs.iterdir():
        if path.name in ('main','sdk','rtld','main.npdm') or path.name.startswith('subsdk'):
            with path.open('rb') as stream:
                hashes[path.name] = hashlib.file_digest(stream,'sha256').hexdigest()
    expected = out/'expected.json'
    expected.write_text(json.dumps({'exefs_sha256':hashes},indent=2)+'\n')
    command = [sys.executable,str(ROOT/'third_party/dkb/tools/build_game.py'),'--version','oot111',
               '--expected',str(expected),'--jobs',str(max(1,args.jobs))]
    for name,upstream in [('exefs','exefs'),('romfs','romfs'),('generated','gen'),('out','out'),
                          ('profile','profile'),('deps','deps'),('llvm','toolchain'),('ninja','ninja')]:
        command += ['--'+upstream,str(getattr(args,name).resolve())]
    result = subprocess.run(command)
    if result.returncode:return result.returncode
    if args.translator:
        for name in ('totk_xlate.exe','totk_xlate.id'):
            shutil.copy2(args.translator/name,out/name)
    print(f'Linked {out / "oot2026.exe"}. This is a build result, not proof of a game boot.')
    return 0

if __name__=='__main__':raise SystemExit(main())
