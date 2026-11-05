"""Create an explicit source/runtime archive without local game files or generated game code."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'third_party/dkb/tools'))
import check_content

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    allowed={'src','tools','tests','third_party','docs','logs','bin','.github','patches','licenses'}
    skip={'build','generated','local','toolchain','.venv','.git','__pycache__'}
    files=[]
    for f in sorted(ROOT.rglob('*')):
        if not f.is_file():continue
        rel=f.relative_to(ROOT)
        if any(x in skip for x in rel.parts) or f.suffix=='.pyc':continue
        if len(rel.parts)>1 and rel.parts[0] not in allowed:continue
        errors=check_content.problems_for(f,allow_large=True)
        if f.suffix.lower()=='.nup':errors.append('NUP container')
        if errors:raise ValueError(f'{rel}: {errors}')
        files.append((f,rel))
    manifest={rel.as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f,rel in files}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f,rel in files:z.write(f,Path(ROOT.name)/rel)
        z.writestr(ROOT.name+'/SHA256SUMS.json',json.dumps(manifest,indent=2)+'\n')
    digest=hashlib.sha256(a.out.read_bytes()).hexdigest()
    a.out.with_suffix(a.out.suffix+'.sha256').write_text(digest+'  '+a.out.name+'\n')
    print(f'Packaged {len(files)} files; content guard passed; SHA-256 {digest}')
if __name__=='__main__':main()
