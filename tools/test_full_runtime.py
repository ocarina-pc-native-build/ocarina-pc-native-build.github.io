"""Run the real linked runtime's host integration probes, recording every exit code."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

# The donor's probe-ipc / probe-services contain TotK constructor offsets and
# symbol-count goldens. They remain available explicitly, but are not portable
# Zelda regression fixtures. These probes exercise the integrated host instead.
DEFAULT = ['selftest','probe-loader','probe-kernel','probe-ipc-lifetime','probe-ipc-domains',
           'probe-system-core','probe-audio-device','probe-nifm','probe-bsd','probe-fs','probe-gfx-abi','probe-nvn','probe-codec']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('exe',type=Path);p.add_argument('--logs',type=Path,required=True)
    p.add_argument('--modes',nargs='+',default=DEFAULT)
    p.add_argument('--timeout',type=int,default=120)
    a=p.parse_args();exe=a.exe.resolve();a.logs.mkdir(parents=True,exist_ok=True)
    rows=[]
    for mode in a.modes:
        if mode != 'selftest' and not mode.startswith('probe-'):p.error('Only selftest/probe modes are accepted')
        start=time.monotonic();log=a.logs/(mode+'.log')
        with log.open('wb') as stream:
            proc=subprocess.Popen([str(exe),'--'+mode],cwd=exe.parent,stdout=stream,stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                code=proc.wait(timeout=a.timeout);status='pass' if code==0 else 'failed'
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait();code=None;status='timeout'
        row=dict(mode=mode,status=status,exit_code=code,seconds=round(time.monotonic()-start,3))
        rows.append(row);print(json.dumps(row),flush=True)
        (a.logs/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    return int(any(row['status']!='pass' for row in rows))

if __name__=='__main__':raise SystemExit(main())
