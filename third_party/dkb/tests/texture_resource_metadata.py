"""Exercise production reflection parsing with authored full-width texture handles."""
import argparse
from pathlib import Path
import subprocess
from nvn2_shader_control_test import function

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', required=True)
    args=parser.parse_args()
    source=(ROOT/'runtime/gfx_shader.c').read_text()
    before=r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include "gfx.h"
#include "nvn2_c0.h"
struct GfxShader { GfxShaderRes *res[GFX_RES_KINDS]; int nres[GFX_RES_KINDS],has_c0; Nvn2C0Layout c0; };
static int fmt_code(const char *s) { (void)s; return 0; }
'''
    pieces=[function(source,start) for start in (
        'static const char *json_key(', 'static long json_int(', 'static void json_str(',
        'static int handle_slot(', 'static void add_res(')]
    after=r'''
int main(void) {
    unsigned checks=0,failures=0; volatile int expected_slots=196610;
    const unsigned handles[]={0x40000000,0x40000040,0x10088008,0x20088008,0x30088008};
    for(unsigned i=0;i<sizeof handles/sizeof *handles;i++) {
        char json[256];
        snprintf(json,sizeof json,"{\"binding\":4,\"type\":3,\"cbuf_slot\":196610,\"handle\":%u,\"array\":32,\"separate\":true}",handles[i]);
        GfxShaderRes resource={0}; GfxShader shader={0}; shader.res[GFX_RES_TEX]=&resource;
        add_res(&shader,GFX_RES_TEX,json,json+strlen(json));
        checks++; failures+=resource.handle!=handles[i];
        checks++; failures+=resource.cbuf_slot!=expected_slots;
        checks++; failures+=resource.count!=32 || resource.type!=3 || !resource.separate;
    }
    // A direct pool index does not become a bound c2 slot even when its low bits
    // happen to equal the c2 slot-zero offset.
    checks++; failures+=handle_slot(GFX_RES_TEX,2,0x40000008,0)!=-1;
    checks++; failures+=handle_slot(GFX_RES_TEX,2,8,0)!=0;
    printf("texture resource metadata: %u checks, %u failures\n",checks,failures);
    return failures?1:0;
}
'''
    out=ROOT/'build/test/texture-resource-metadata'; out.mkdir(parents=True,exist_ok=True)
    src=out/'metadata.c'; src.write_text(before+'\n'.join(pieces)+after)
    exe=out/'metadata.exe'
    subprocess.run([args.cc,'-O2','-static','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime'),str(src),'-o',str(exe)],check=True)
    return subprocess.call([str(exe)])

if __name__=='__main__': raise SystemExit(main())
