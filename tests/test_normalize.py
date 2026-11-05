from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from normalize_nso import normalize
from test_inspect import fixture
from inspect_dump import inspect_nso

class NormalizeTests(unittest.TestCase):
    def test_zbic_roundtrip(self):
        try:import zbic
        except ImportError:self.skipTest('optional standalone zbic decoder not installed')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);src=p/'main';dst=p/'normalized/main'
            data=fixture();headers=bytearray(data[:0x100]);payload=bytearray()
            struct.pack_into('<I',headers,0xc,0xff)
            # nxnative requires compressed data <= decoded size; use larger blocks.
            import hashlib
            for i in range(3):
                raw=bytes([i+1])*0x1000;compressed=zbic.compress(raw)
                struct.pack_into('<III',headers,0x10+i*16,0x100+len(payload),i*0x1000,len(raw))
                struct.pack_into('<I',headers,0x60+i*4,len(compressed))
                headers[0xa0+i*32:0xc0+i*32]=hashlib.sha256(raw).digest();payload.extend(compressed)
            src.write_bytes(headers+payload);original=src.read_bytes()
            normalize(src,dst);self.assertEqual(src.read_bytes(),original)
            self.assertEqual(inspect_nso(dst)['segments'][0]['size'],0x1000)
            damaged=bytearray(original);damaged[0xa0]^=1;src.write_bytes(damaged)
            with self.assertRaisesRegex(ValueError,'SHA-256'):normalize(src,p/'bad')
    def test_same_path_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'main';p.write_bytes(fixture())
            with self.assertRaises(ValueError):normalize(p,p)
