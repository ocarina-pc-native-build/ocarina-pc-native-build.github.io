"""Validate and lift discovered modules. Incomplete translation returns a nonzero status."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from inspect_dump import inspect,locate
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('exefs',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--jobs',type=int,default=4);a=p.parse_args()
    exefs=locate(a.exefs);report=inspect(exefs)
    names={m['name'] for m in report['modules']}
    known=['main']+[f'subsdk{i}' for i in range(10)]+['sdk']
    unknown=names-set(known)-{'rtld'}
    if unknown:p.error(f'Unsupported module names: {sorted(unknown)}; extend the layout deliberately')
    out=a.out.resolve()
    if out.is_relative_to(ROOT) and out.relative_to(ROOT).parts[0] not in ('build','generated','local'):
        p.error('Game-derived output inside this repository must be under build/, generated/ or local/')
    command=[sys.executable,str(ROOT/'third_party/dkb/recomp/gen.py'),'--exefs',str(exefs.resolve()),'--out',str(out),'--modules',','.join(n for n in known if n in names),'--jobs',str(max(1,a.jobs))]
    result=subprocess.run(command)
    if result.returncode:return result.returncode
    summary=[]
    for path in sorted(out.glob('*/manifest.json')):
        m=json.loads(path.read_text());summary.append({k:m[k] for k in ['module','function_count','stats','unsupported_census']})
    (out/'translation-status.json').write_text(json.dumps(summary,indent=2)+'\n')
    unsupported=sum(m['stats']['unsupported'] for m in summary)
    if unsupported:
        print(f'INCOMPLETE: {unsupported} unsupported instructions remain. Generated trap paths are not successful translations.',file=sys.stderr)
        return 3
    print('Translation emitted. Trap sites, indirect dispatch and runtime services still require validation before boot.')
    return 0
if __name__=='__main__':raise SystemExit(main())
