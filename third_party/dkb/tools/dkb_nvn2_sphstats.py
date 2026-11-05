"""Stage of each NVN 2 code dump from its SPH word 0, crossed with control +0x08. usage: python sphstats.py <dir>"""
import collections, glob, os, struct, sys

d = sys.argv[1]
names = {1: "vertex", 2: "tess-ctl", 3: "tess-eval", 4: "geometry", 5: "pixel"}
cross = collections.Counter()
for p in glob.glob(os.path.join(d, "*.bin")):
    code = open(p, "rb").read()
    ctl = open(p[:-4] + ".ctl", "rb").read()
    w0 = struct.unpack_from("<I", code, 0)[0]
    sph_type, version, stype = w0 & 31, (w0 >> 5) & 31, (w0 >> 10) & 15
    stage = names.get(stype, "?") if sph_type in (1, 2) else "compute/none"
    cross[(stage, sph_type, version, struct.unpack_from("<I", ctl, 8)[0])] += 1
for (stage, t, v, f8), n in cross.most_common():
    print(f"{n:5}  {stage:12} sph_type {t} version {v}  ctl+8 {f8:#x}")
