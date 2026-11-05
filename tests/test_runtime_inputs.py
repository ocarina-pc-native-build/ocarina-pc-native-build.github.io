"""Synthetic checks for RomFS packing and the application identity build input."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zstandard

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'third_party/dkb/tools'))
import nup_romfs
import build_game
import romfs_index


class RuntimeInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, corrupt=False):
        plain = [b'original raw fixture', b'compressed fixture' * 100]
        stored = [plain[0], zstandard.ZstdCompressor().compress(plain[1])]
        n = SimpleNamespace()
        n.f = io.BytesIO(b''.join(stored))
        n.close = n.f.close
        n.packages = [SimpleNamespace(title_id=0x1234, display_version='test')]
        n.files = [('raw',len(plain[0]),0,len(stored[0]),hashlib.sha256(plain[0]).digest(),0),
                   ('zstd',len(plain[1]),len(stored[0]),len(stored[1]),
                    bytes(32) if corrupt else hashlib.sha256(plain[1]).digest(),1)]
        n.package_files = lambda package, section: [(['b','zstd'],1),(['a','raw'],0)]
        return n, plain

    def test_romfs_raw_compressed_alignment_and_index(self):
        n, plain = self.fixture()
        with patch.object(nup_romfs, 'Nup', return_value=n):
            nup_romfs.pack('synthetic',self.root,0)
        manifest = json.loads((self.root/'index.json').read_text())
        image = (self.root/'romfs.bin').read_bytes()
        self.assertEqual(manifest['romfs_sha256'],hashlib.sha256(image).hexdigest())
        for row, data in zip(manifest['files'],plain):
            self.assertEqual(row['offset']%16,0)
            self.assertEqual(image[row['offset']:row['offset']+row['size']],data)
        self.assertTrue(romfs_index.build_index(manifest).startswith(b'TOTKRFS1'))

    def test_romfs_corruption_never_publishes_verified_image(self):
        n, _ = self.fixture(corrupt=True)
        with patch.object(nup_romfs, 'Nup', return_value=n):
            with self.assertRaisesRegex(nup_romfs.NupError,'hash mismatch'):
                nup_romfs.pack('synthetic',self.root,0)
        self.assertFalse((self.root/'index.json').exists())
        self.assertFalse((self.root/'romfs.bin').exists())

    def npdm(self):
        data=bytearray(0xc0);data[:4]=b'META'
        data[0x70:0x74]=(0x80).to_bytes(4,'little')
        data[0x74:0x78]=(0x40).to_bytes(4,'little')
        data[0x80:0x84]=b'ACI0';data[0x90:0x98]=(0x123456789).to_bytes(8,'little')
        return data

    def glue(self, data):
        (self.root/'main.npdm').write_bytes(data)
        return build_game.module_glue([],[],{},dict(exefs=self.root,romfs=self.root,profile=self.root),'custom')

    def test_application_id_comes_from_npdm(self):
        self.assertIn('rt_application_id = 0x123456789ull',self.glue(self.npdm()))

    def test_display_version_comes_from_package_metadata(self):
        (self.root/'index.json').write_text(json.dumps({'version':'test-1.2.3'}))
        self.assertIn('rt_display_version[] = "test-1.2.3"',self.glue(self.npdm()))
        for version in ('x'*16, 'bad\0version', 123):
            (self.root/'index.json').write_text(json.dumps({'version':version}))
            with self.subTest(version=version), self.assertRaises(ValueError):self.glue(self.npdm())

    def test_invalid_npdm_rejected(self):
        for mutation in ('magic','offset','size','aci','id'):
            data=self.npdm()
            start,end,value={'magic':(0,4,b'FAIL'),'offset':(0x70,0x74,b'\xff'*4),
                'size':(0x74,0x78,b'\xff'*4),'aci':(0x80,0x84,b'FAIL'),
                'id':(0x90,0x98,bytes(8))}[mutation]
            data[start:end]=value
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.glue(data)

if __name__=='__main__':unittest.main()
