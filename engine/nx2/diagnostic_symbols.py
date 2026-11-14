"""Keep a code-free function index tied to the exact locally linked PE binary."""
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct


def export(binary, destination=None):
    binary = Path(binary)
    with binary.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            pe = struct.unpack_from('<I', data, 0x3c)[0]
            if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0':
                raise ValueError('Not a Windows PE binary')
            machine, count, timestamp, symbols, symbol_count, opt_size = struct.unpack_from('<HHIIIH', data, pe+4)
            opt = pe+24
            magic = struct.unpack_from('<H', data, opt)[0]
            image_base = struct.unpack_from('<Q' if magic == 0x20b else '<I', data, opt+(24 if magic == 0x20b else 28))[0]
            sections = []
            for i in range(count):
                offset = opt+opt_size+i*40
                size, address = struct.unpack_from('<II', data, offset+8)
                flags = struct.unpack_from('<I', data, offset+36)[0]
                sections.append((address, size, flags))
            strings = symbols+symbol_count*18
            if not symbols or strings+4 > len(data):
                raise ValueError('No COFF symbols; retain the linker map for this build')
            string_size = struct.unpack_from('<I', data, strings)[0]
            if string_size < 4 or strings+string_size > len(data):
                raise ValueError('Invalid COFF string table')
            functions = []
            i = 0
            while i < symbol_count:
                pos = symbols+i*18
                value, section, kind, storage, auxiliary = struct.unpack_from('<IhHBB', data, pos+8)
                if 1 <= section <= len(sections) and kind & 0x20 and storage in (2, 3):
                    va, size, flags = sections[section-1]
                    if flags & 0x20 and value < size:
                        name = bytes(data[pos:pos+8])
                        if name[:4] == b'\0'*4:
                            relative = struct.unpack_from('<I', name, 4)[0]
                            if 4 <= relative < string_size:
                                start = strings+relative
                                end = data.find(b'\0', start, min(strings+string_size, start+2048))
                                name = bytes(data[start:end]) if end >= start else b''
                            else:
                                name = b''
                        else:
                            name = name.split(b'\0', 1)[0]
                        if name:
                            functions.append([va+value, name.decode('utf-8', 'replace')])
                i += 1+auxiliary
    if not functions:
        raise ValueError('No named COFF functions found')
    result = dict(schema=1, module=binary.name, binary_sha256=digest, image_base=image_base,
                  machine=machine, pe_timestamp=timestamp, functions=sorted(functions),
                  note='Function names and RVAs only, no source or executable bytes. Addresses require this exact binary hash.')
    destination = Path(destination or binary.with_name(binary.name+'.symbols.json'))
    destination.write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(export(args.binary, args.output))
