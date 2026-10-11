#!/usr/bin/env python3
"""Convert a small PNG logo into an MDS 32x24 machine sprite (no PIL needed).

python png_sprite.py logo.png [--show] [--threshold 128] [--invert]
Prints the 32 column words as a JSON list for the "bitmap" field; dark pixels draw.
"""
import argparse
import json
import struct
import zlib


def read_png(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, plte, trns = 8, b"", None, None
    while pos + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
        if kind == b"IEND":
            break
    assert interlace == 0, "interlaced PNG not supported"
    raw = zlib.decompress(idat)
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, chans * depth // 8)
    stride = (w * chans * depth + 7) // 8
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b, c = prev[x], prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    lum = []
    for line in rows:
        out = []
        for x in range(w):
            if depth < 8:
                bit = x * depth
                v = (line[bit // 8] >> (8 - depth - bit % 8)) & ((1 << depth) - 1)
                vals = plte[v] if ctype == 3 else (v * 255 // ((1 << depth) - 1),) * 3
                alpha = trns[v] if (ctype == 3 and trns and v < len(trns)) else 255
            else:
                px = line[x * bpp:(x + 1) * bpp]
                if ctype == 3:
                    vals, alpha = plte[px[0]], (trns[px[0]] if trns and px[0] < len(trns) else 255)
                elif ctype in (0, 4):
                    vals, alpha = (px[0],) * 3, (px[1] if ctype == 4 else 255)
                else:
                    vals, alpha = px[:3], (px[3] if ctype == 6 else 255)
            l = sum(vals) / 3
            out.append(255 - (255 - l) * alpha / 255)    # transparent = white
        lum.append(out)
    return w, h, lum


def write_png(path, rows):
    """rows: lists of (r, g, b) pixels; writes an 8-bit RGB PNG."""
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in rows)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png")
    ap.add_argument("--threshold", type=float, default=128)
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--pbm", help="also write the sprite as an ASCII P1 PBM (for mds_pack.py --bitmap)")
    ap.add_argument("--web", help="also write a web PNG: the sprite scaled up, black on --bg")
    ap.add_argument("--scale", type=int, default=6)
    ap.add_argument("--bg", default="CD2824", help="web background colour, RRGGBB")
    a = ap.parse_args()
    w, h, lum = read_png(a.png)
    assert w <= 32 and h <= 24, f"image is {w}x{h}, sprites are 32x24"
    on = [[(lum[y][x] < a.threshold) != a.invert for x in range(w)] for y in range(h)]
    cols = []
    for x in range(32):
        word = 0
        for y in range(24):
            if x < w and y < h and on[y][x]:
                word |= 1 << (y + 8)
        cols.append(word)
    if a.show:
        print(f"{w}x{h}")
        for y in range(24):
            print("".join("#" if cols[x] >> (y + 8) & 1 else "." for x in range(32)))
    if a.pbm:
        rows = [" ".join("1" if cols[x] >> (y + 8) & 1 else "0" for x in range(32)) for y in range(24)]
        with open(a.pbm, "w", newline="\n") as f:
            f.write("P1\n32 24\n" + "\n".join(rows) + "\n")
    if a.web:
        bg = tuple(int(a.bg[i:i + 2], 16) for i in (0, 2, 4))
        rows = [[(0, 0, 0) if cols[x // a.scale] >> (y // a.scale + 8) & 1 else bg
                 for x in range(32 * a.scale)] for y in range(24 * a.scale)]
        write_png(a.web, rows)
    print(json.dumps(cols))


if __name__ == "__main__":
    main()
