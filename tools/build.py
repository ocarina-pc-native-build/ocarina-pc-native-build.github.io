"""Build and test the independent Windows runtime, recording command output and exit codes."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',choices=['Debug','Release'],default='Debug')
    p.add_argument('--deps',type=Path,default=ROOT/'toolchain')
    p.add_argument('--llvm',type=Path)
    p.add_argument('--out',type=Path)
    a=p.parse_args();deps=a.deps.resolve();llvm=(a.llvm or deps/'llvm/llvm-mingw-20261104-ucrt-x86_64').resolve()
    out=(a.out or ROOT/'build'/a.config.lower()).resolve();out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['PATH']=str(llvm/'bin')+os.pathsep+str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
    cmake=shutil.which('cmake',path=env['PATH']);ctest=shutil.which('ctest',path=env['PATH'])
    if not cmake or not ctest:raise SystemExit('Install requirements.txt in the active Python environment first')
    commands=[['configure',cmake,'-S',str(ROOT),'-B',str(out),'-G','Ninja',f'-DCMAKE_BUILD_TYPE={a.config}',
        f'-DCMAKE_C_COMPILER={llvm.as_posix()}/bin/clang.exe',f'-DCMAKE_CXX_COMPILER={llvm.as_posix()}/bin/clang++.exe',
        f'-DOOT_DEPS={deps.as_posix()}',f'-DPython3_EXECUTABLE={sys.executable}'],
        ['build',cmake,'--build',str(out)],['test',ctest,'--test-dir',str(out),'-V']]
    results=[]
    for label,*command in commands:
        with (out/f'{label}.log').open('w',encoding='utf-8') as f:
            f.write(json.dumps(command)+'\n');f.flush()
            r=subprocess.run(command,env=env,stdout=f,stderr=subprocess.STDOUT)
        results.append(dict(step=label,exit_code=r.returncode));(out/'result.json').write_text(json.dumps(results,indent=2))
        print(label,r.returncode,flush=True)
        if r.returncode:return r.returncode
    return 0
if __name__=='__main__':raise SystemExit(main())
