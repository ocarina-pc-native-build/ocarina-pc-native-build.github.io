"""Opcode table from Mesa NAK sm70_encode.rs (MIT) and its coverage of a folder of NVN 2 code dumps.
usage: python sm86_ops.py <sm70_encode.rs> <dump dir> [--table out.json]

Every `impl SM70Op for OpX` block is scanned for set_opcode(0x...) (12-bit opcode) and encode_*alu*(0x...) (9-bit
opcode, bits 9-11 the operand form 1-7). Graphics code starts after the 0x80-byte SPH; compute code at 0. Each
instruction is 16 bytes; the 12 low bits pick the opcode."""
import collections, glob, json, os, re, struct, sys

src = open(sys.argv[1], encoding="utf-8").read()
table = {}   # 12-bit opcode -> set of op names
for m in re.finditer(r"impl SM70Op for (Op\w+) \{(.*?)\n\}", src, re.S):
    name, body = m.group(1), m.group(2)
    for o in re.findall(r"set_opcode\(\s*(0x[0-9a-fA-F]+)", body):
        table.setdefault(int(o, 16), set()).add(name)
    for o in re.findall(r"encode_\w*alu\w*\(\s*(0x[0-9a-fA-F]+)", body):
        base = int(o, 16) & 0x1FF
        for form in range(1, 8):
            table.setdefault(base | form << 9, set()).add(name)
print(len(table), "12-bit opcodes from", len({n for v in table.values() for n in v}), "ops")

hist = collections.Counter()
total = 0
for p in glob.glob(os.path.join(sys.argv[2], "*.bin")):
    code = open(p, "rb").read()
    w0 = struct.unpack_from("<I", code, 0)[0]
    start = 0x80 if (w0 & 31) in (1, 2) and ((w0 >> 5) & 31) == 4 else 0
    for off in range(start, len(code) - 15, 16):
        lo = struct.unpack_from("<Q", code, off)[0]
        hist[lo & 0xFFF] += 1
        total += 1
known = sum(n for op, n in hist.items() if op in table)
print(f"{total} instructions, {len(hist)} distinct opcodes; {known / total:.1%} covered by the table")
print("most common unknown opcodes:", ", ".join(f"{op:#05x}x{n}" for op, n in hist.most_common() if op not in table)[:600])
print("most common known:", ", ".join(f"{'/'.join(sorted(table[op]))}x{n}" for op, n in hist.most_common(25) if op in table))
if "--table" in sys.argv:
    out = sys.argv[sys.argv.index("--table") + 1]
    json.dump({f"{k:#05x}": sorted(v) for k, v in sorted(table.items())}, open(out, "w"), indent=0)
