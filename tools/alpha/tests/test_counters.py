"""Game-free tests of the actual native counter hooks, not copies of their logic."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ALPHA = Path(__file__).resolve().parents[1]
ROOT = ALPHA.parents[1]
spec = importlib.util.spec_from_file_location('ocr_counters', ALPHA / 'hud/ocr_counters.py')
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)


class CounterHooks(unittest.TestCase):
    def test_install_preserves_other_hooks_and_inventory_events(self):
        words = {pc: word for pc, word, _ in hooks.HOOKS} | dict(hooks.CHECKS)
        image = type('Image', (), {'word': lambda self, pc: words[pc]})()
        lifter = type('Lifter', (), {'after': {0x831f3200: 'view_hook();'}})()
        self.assertEqual(hooks.install(lifter, image, hooks.BUILD), 1)
        self.assertTrue(lifter.after[0x831f3200].startswith('view_hook();\n'))
        self.assertNotIn(0x80e5c440, lifter.after)
        self.assertNotIn('return;', lifter.after[0x80a87e50])

    def test_changed_opcode_layout_or_build_installs_nothing(self):
        correct = {pc: word for pc, word, _ in hooks.HOOKS} | dict(hooks.CHECKS)
        for mismatch in [None] + list(correct):
            words = dict(correct)
            if mismatch is not None:
                words[mismatch] ^= 1
            image = type('Image', (), {'word': lambda self, pc: words[pc]})()
            lifter = type('Lifter', (), {'after': {123: 'existing'}})()
            self.assertEqual(hooks.install(lifter, image, hooks.BUILD if mismatch is not None else 'other'), 0)
            self.assertEqual(lifter.after, {123: 'existing'})

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher host')
    def test_native_visibility_lifecycle_and_register_preservation(self):
        candidates = [ROOT / 'build/alpha/stage/engine/llvm-mingw/bin/clang.exe',
                      ROOT / 'build/alpha/hookshot-v2.2.0-rc.1/tools/llvm-mingw/bin/clang.exe']
        compiler = next((str(p) for p in candidates if p.is_file()), None) or shutil.which('clang')
        if not compiler:
            self.skipTest('clang is needed for the native hook test')
        with tempfile.TemporaryDirectory(prefix='ocr-counters-test-') as directory:
            tmp = Path(directory)
            (tmp / 'hos.h').write_text(STUB)
            source = '#include "' + (ALPHA / 'hud/ocr_counters.c').as_posix() + '"\n' + HARNESS
            (tmp / 'test.c').write_text(source)
            exe = tmp / 'test.exe'
            built = subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                                    '-I', str(tmp), '-I', str(ROOT / 'engine/host'), str(tmp / 'test.c'), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertIn('counter and photo HUD lifecycle, wallet bounds OK', ran.stdout)


STUB = r'''
#include <stdint.h>
typedef struct { uint64_t x[32], vreg[32][2]; uint64_t flags[8]; } Ctx;
uint64_t recomp_load64(Ctx *, uint64_t);
uint32_t recomp_load32(Ctx *, uint64_t);
void hos_log(const char *, ...);
'''

HARNESS = r'''
#include <assert.h>
#include <stdio.h>
typedef struct { uint64_t address, value; } Cell;
static Cell memory[1024];
static unsigned used;
static int enabled = 1, live, wallet = 94, shown = -99, reads, photo_on, ready;
static void put(uint64_t a, uint64_t v) {
    for (unsigned i=0; i<used; i++) if (memory[i].address==a) { memory[i].value=v; return; }
    assert(used < 1024); memory[used++] = (Cell){a,v};
}
uint64_t recomp_load64(Ctx *c, uint64_t a) {
    (void)c;
    for (unsigned i=0; i<used; i++) if (memory[i].address==a) return memory[i].value;
    return 0;
}
uint32_t recomp_load32(Ctx *c, uint64_t a) { return (uint32_t)recomp_load64(c,a); }
void hos_log(const char *format, ...) { (void)format; }
int rx_option(int id, int otherwise) { return id==4083 ? enabled : id==OCR_OPT_PHOTO ? photo_on : otherwise; }
void rx_option_set(int id, int v) { if (id==OCR_OPT_PHOTO_READY) ready=v; else { assert(id==4084); shown=v; } }
int hos_oot_story_event_active(void) { return 0; }
int hos_oot_flight_shortcut_ready(void) { return live; }
void f_80a87c30(Ctx *c) { reads++; memset(c,0xa7,sizeof *c); c->x[0]=(uint32_t)wallet; }
void f_802f8ac0(Ctx *c) {
    ocr_counters_alpha(c); /* simulate the real setter with the installed hook */
    uint32_t bits; memcpy(&bits,&c->vreg[0][0],4); put(c->x[0]+0x74,bits);
    memset(c,0xa5,sizeof *c); /* caller must preserve every guest register */
}
static void make_pickup(uint64_t owner, uint64_t root) {
    put(owner,0x84c0ac28ull); put(owner+0x28,owner+0x400);
    put(owner+0x480,owner+0x800); put(owner+0x900,root); put(root+0x74,0x3f800000);
}
static void animate(Ctx *c,uint64_t root,uint32_t bits) {
    c->x[0]=root; memcpy(&c->vreg[0][0],&bits,4); f_802f8ac0(c);
}
int main(void) {
    Ctx c, saved;
    memset(&c,0x5a,sizeof c); saved=c;
    put(0x84c9e0d0ull,0x100); put(0x100,0x200); /* manager exists at title */
    ocr_counters_frame(&c); assert(ready==0 && shown==-1 && reads==0 && !memcmp(&c,&saved,sizeof c));
    live=1; ocr_counters_frame(&c); assert(ready==1 && shown==94 && reads==1 && !memcmp(&c,&saved,sizeof c));
    for (int i=0;i<9;i++) ocr_counters_frame(&c);
    assert(reads==1);
    live=0; ocr_counters_frame(&c); assert(shown==-1 && reads==1); /* unload hides without polling */
    wallet=0; live=1; ocr_counters_frame(&c); assert(shown==0 && reads==2); /* zero is valid */
    enabled=0; ocr_counters_frame(&c); assert(shown==-1 && reads==2);
    wallet=99999; enabled=1; ocr_counters_frame(&c); assert(shown==-1);

    make_pickup(0x1000,0x2000); make_pickup(0x3000,0x4000);
    memset(&c,0x5a,sizeof c); c.x[0]=0x1000; saved=c;
    ocr_counters_pickup(&c); assert(recomp_load32(&c,0x2074)==0 && !memcmp(&c,&saved,sizeof c));
    c.x[0]=0x3000; saved=c; ocr_counters_pickup(&c);
    assert(recomp_load32(&c,0x4074)==0 && !memcmp(&c,&saved,sizeof c));
    animate(&c,0x2000,0x3f000000); assert(recomp_load32(&c,0x2074)==0); /* animation cannot show it */
    animate(&c,0x6000,0x3f400000); assert(recomp_load32(&c,0x6074)==0x3f400000); /* other UI unchanged */
    enabled=0; c.x[0]=0x1000; saved=c; ocr_counters_pickup(&c);
    assert(recomp_load32(&c,0x2074)==0x3f000000 && !memcmp(&c,&saved,sizeof c)); /* restore animation alpha */
    c.x[0]=0x3000; ocr_counters_pickup(&c); assert(recomp_load32(&c,0x4074)==0x3f800000);
    enabled=1; c.x[0]=0x1000; ocr_counters_pickup(&c);
    put(0x1000,0xdeadbeef); animate(&c,0x2000,0x3f400000);
    assert(recomp_load32(&c,0x2074)==0x3f400000); /* reused node belongs to another screen */
    for (int i=0;i<40;i++) { /* old layout instances are reclaimed, not accumulated forever */
        uint64_t owner=0x10000+(uint64_t)i*0x2000, root=owner+0x1000;
        make_pickup(owner,root); c.x[0]=owner; ocr_counters_pickup(&c);
        assert(recomp_load32(&c,root+0x74)==0); put(owner,0);
    }
    /* Photo HUD is independent of Classic counters; preserve animated alpha on exit. */
    enabled=0; photo_on=1;
    make_pickup(0x90000,0x91000); put(0x90000,0x84c08300ull);
    saved=c; ocr_photo_hud(&c,0x90000);
    assert(recomp_load32(&c,0x91074)==0 && !memcmp(&c,&saved,sizeof c));
    animate(&c,0x91000,0x3f400000); assert(recomp_load32(&c,0x91074)==0);
    photo_on=0; ocr_photo_hud(&c,0x90000);
    assert(recomp_load32(&c,0x91074)==0x3f400000);
    /* Unknown screens are never touched; a recycled HUD root is never restored. */
    photo_on=1; ocr_photo_hud(&c,0x90000); put(0x90000,0xdeadbeef);
    photo_on=0; animate(&c,0x91000,0x3f800000); ocr_photo_hud(&c,0x90000);
    assert(recomp_load32(&c,0x91074)==0x3f800000);
    const uint64_t hud_types[] = {0x84c08300ull,0x84c0b710ull,0x84c0afe0ull,0x84c07ec8ull,0x84c042e8ull};
    for (unsigned i=0;i<sizeof hud_types/sizeof *hud_types;i++) {
        const uint64_t owner=0xa0000+i*0x2000, root=owner+0x1000;
        make_pickup(owner,root); put(owner,hud_types[i]);
        photo_on=1; ocr_photo_hud(&c,owner); assert(recomp_load32(&c,root+0x74)==0);
        photo_on=0; ocr_photo_hud(&c,owner); assert(recomp_load32(&c,root+0x74)==0x3f800000);
    }
    for (int choice=0;choice<OCR_RUPEE_CHOICES;choice++) {
        assert(ocr_rupee_delta(choice,99,99)==0);
        assert(ocr_rupee_delta(choice,98,99)==1);
    }
    assert(ocr_rupee_delta(3,10,200)==100);
    assert(ocr_rupee_delta(5,10,500)==490);
    assert(ocr_rupee_delta(5,-1,500)==0);
    assert(ocr_rupee_delta(6,10,500)==0);
    assert(ocr_rupee_delta(5,0,10000)==0);
    puts("counter and photo HUD lifecycle, wallet bounds OK");
    return 0;
}
'''


if __name__ == '__main__':
    unittest.main()
