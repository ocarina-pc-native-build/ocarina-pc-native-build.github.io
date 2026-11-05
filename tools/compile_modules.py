"""Compile generated modules to native COFF objects for diagnosis. Does not link or boot a game.

Unsupported-instruction counts remain visible in the report. Output must stay private.
"""
from pathlib import Path
import argparse
import concurrent.futures
import json
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generated',type=Path,required=True);p.add_argument('--llvm',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--sample',type=int,default=0,help='Compile first N chunks per module; 0 means all')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    compiler=a.llvm.resolve()/'bin/clang.exe';tasks=[];mods=[]
    for manifest in sorted(a.generated.glob('*/manifest.json')):
        d=json.loads(manifest.read_text());chunks=d['chunks'][:a.sample or None]
        mods.append(dict(module=d['module'],total_chunks=len(d['chunks']),selected_chunks=len(chunks),unsupported=d['stats']['unsupported'],traps=d['stats']['traps']))
        for name in chunks+[d['table']]:tasks.append(manifest.parent/name)
    if not tasks:p.error('No generated module manifests')
    def compile_one(src):
        target=out/(src.stem+'.obj');log=out/(src.stem+'.log')
        command=[str(compiler),'-c',str(src.resolve()),'-o',str(target),'-O1','-fno-strict-aliasing','-march=x86-64-v3','-I',str(ROOT/'third_party/dkb/runtime')]
        with log.open('w',encoding='utf-8') as f:
            f.write(json.dumps(command)+'\n');f.flush();r=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT)
        return dict(source=src.name,exit_code=r.returncode,object_bytes=target.stat().st_size if r.returncode==0 else 0)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,a.jobs)) as pool:
        for r in pool.map(compile_one,tasks):
            results.append(r);print(r['source'],r['exit_code'],flush=True)
    report=dict(scope='sample' if a.sample else 'all generated chunks',linked=False,booted=False,modules=mods,objects=results)
    (out/'compilation.json').write_text(json.dumps(report,indent=2)+'\n')
    return int(any(r['exit_code'] for r in results))
if __name__=='__main__':raise SystemExit(main())
