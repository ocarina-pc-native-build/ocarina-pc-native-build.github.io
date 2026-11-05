from pathlib import Path
import hashlib
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from inspect_dump import inspect_nso,inspect,InvalidDump

def fixture():
    b=bytearray(0x10c);b[:4]=b'NSO0'
    struct.pack_into('<I',b,0xc,0x38)
    for i in range(3):
        struct.pack_into('<III',b,0x10+i*16,0x100+i*4,i*0x1000,4)
        struct.pack_into('<I',b,0x60+i*4,4)
        b[0x100+i*4:0x104+i*4]=bytes([i+1])*4
        b[0xa0+i*32:0xc0+i*32]=hashlib.sha256(bytes([i+1])*4).digest()
    return b

class NsoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'main'
    def parse(self,data):
        self.path.write_bytes(data);return inspect_nso(self.path)
    def test_valid(self):
        row=self.parse(fixture());self.assertEqual(row['segments'][0]['size'],4)
    def test_truncated(self):
        for size in (0,4,0xff,0x101):
            with self.assertRaises(InvalidDump):self.parse(fixture()[:size])
    def test_hash_mismatch(self):
        b=fixture();b[-1]^=1
        with self.assertRaisesRegex(InvalidDump,'SHA-256'):self.parse(b)
    def test_memory_overlap(self):
        b=fixture();struct.pack_into('<I',b,0x24,0)
        with self.assertRaisesRegex(InvalidDump,'overlapping'):self.parse(b)
    def test_bounds(self):
        b=fixture();struct.pack_into('<I',b,0x18,0xffffffff)
        with self.assertRaises(InvalidDump):self.parse(b)
    def test_header_version(self):
        b=fixture();struct.pack_into('<I',b,4,1)
        with self.assertRaises(InvalidDump):self.parse(b)
    def test_nested_and_ambiguous(self):
        exe=self.root/'ExeFS';exe.mkdir();(exe/'main').write_bytes(fixture())
        self.assertEqual(len(inspect(self.root)['modules']),1)
        self.path.write_bytes(fixture())
        with self.assertRaises(InvalidDump):inspect(self.root)
    def test_corrupt_sdk_rejected(self):
        self.path.write_bytes(fixture());(self.root/'sdk').write_bytes(b'bad')
        with self.assertRaises(InvalidDump):inspect(self.root)
    def test_missing_main(self):
        with self.assertRaises(InvalidDump):inspect(self.root)
    def test_lz4(self):
        import lz4.block
        b=fixture();compressed=lz4.block.compress(bytes([3])*4,store_size=False)
        b[0x108:]=compressed
        struct.pack_into('<I',b,0xc,0x3c);struct.pack_into('<I',b,0x68,len(compressed))
        self.assertEqual(self.parse(b)['segments'][2]['size'],4)
if __name__=='__main__':unittest.main()
