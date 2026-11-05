"""Compact previews for the runtime's unfiltered RGBA8 PNG screenshots.

Uses only the Python standard library. This is intentionally not a general PNG
decoder: unsupported input fails rather than silently producing a wrong image.
"""
from pathlib import Path
import argparse
import struct
import zlib

SIGNATURE = b'\x89PNG\r\n\x1a\n'


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def make_preview(source, destination):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('The preview must not overwrite the original')
    data = source.read_bytes()
    if not data.startswith(SIGNATURE):
        raise ValueError('Not a PNG screenshot')
    position, image_data, header, ended = 8, [], None, False
    while position + 12 <= len(data):
        length = struct.unpack('>I', data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        end = position + 8 + length
        if end + 4 > len(data):
            raise ValueError('Truncated PNG chunk')
        body = data[position + 8:end]
        if zlib.crc32(kind + body) & 0xffffffff != struct.unpack('>I', data[end:end + 4])[0]:
            raise ValueError('PNG checksum mismatch')
        if kind == b'IHDR':
            header = body
        elif kind == b'IDAT':
            image_data.append(body)
        elif kind == b'IEND':
            ended = True
        position = end + 4
        if ended:
            break
    if header is None or len(header) != 13 or not ended or position != len(data):
        raise ValueError('Incomplete PNG screenshot')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', header)
    if (depth, color, compression, filtering, interlace) != (8, 6, 0, 0, 0):
        raise ValueError('Expected runtime RGBA8 non-interlaced PNG')
    stride = 1 + width * 4
    expected = stride * height
    if not width or not height or expected > 64 * 1024 * 1024:
        raise ValueError('Screenshot dimensions exceed the local preview budget')
    decoder = zlib.decompressobj()
    try:
        pixels = decoder.decompress(b''.join(image_data), expected + 1)
    except zlib.error as error:
        raise ValueError('Invalid PNG compression') from error
    if len(pixels) != expected or not decoder.eof or decoder.unused_data or any(pixels[::stride]):
        raise ValueError('Expected complete runtime PNG with unfiltered scanlines')
    max_edge = 960
    while True:
        scale = min(1.0, max_edge / max(width, height))
        out_width, out_height = max(1, round(width * scale)), max(1, round(height * scale))
        rows = bytearray()
        for y in range(out_height):
            rows.append(0)
            row_start = (y * height // out_height) * stride + 1
            for x in range(out_width):
                offset = row_start + (x * width // out_width) * 4
                rows.extend(pixels[offset:offset + 4])
        output = (SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', out_width, out_height, 8, 6, 0, 0, 0))
                  + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))
        if len(output) <= 512 * 1024:
            break
        max_edge //= 2
        if max_edge < 60:
            raise ValueError('Could not meet the local 512 KiB preview budget')
    destination.write_bytes(output)
    out_stride = 1 + out_width * 4
    nonblack = sum(any(rows[y*out_stride+1+x*4:y*out_stride+4+x*4]) for y in range(out_height) for x in range(out_width))
    return {'width': out_width, 'height': out_height, 'bytes': len(output), 'nonblack_pixels': nonblack}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    options = parser.parse_args()
    print(make_preview(options.source, options.destination))
