"""Statistics over a folder of NVN 2 control dumps (*.ctl, with *.bin code). usage: python ctlstats.py <dir> [words]
Prints the control size histogram and, per u32 offset of the header, how many distinct values it takes, the most
common ones and whether it equals the code size, the control size or a code offset."""
import collections, glob, os, struct, sys

d = sys.argv[1]
nw = int(sys.argv[2]) if len(sys.argv) > 2 else 64
ctls = []
for p in glob.glob(os.path.join(d, "*.ctl")):
    c = open(p, "rb").read()
    b = os.path.getsize(p[:-4] + ".bin")
    ctls.append((c, b))
print(len(ctls), "controls")
print("control sizes:", collections.Counter(len(c) for c, _ in ctls).most_common(10))
for i in range(nw):
    vals = [struct.unpack_from("<I", c, 4 * i)[0] for c, _ in ctls if len(c) >= 4 * i + 4]
    if not vals:
        break
    cnt = collections.Counter(vals)
    eq_code = sum(1 for (c, b), v in zip(ctls, vals) if v == b)
    eq_ctl = sum(1 for (c, b), v in zip(ctls, vals) if v == len(c))
    tops = ", ".join(f"{v:#x}x{n}" for v, n in cnt.most_common(4))
    note = (f" ==code {eq_code}" if eq_code > len(vals) // 2 else "") + (f" ==ctl {eq_ctl}" if eq_ctl > len(vals) // 2 else "")
    print(f"+{4*i:#05x} distinct {len(cnt):5}  {tops}{note}")
