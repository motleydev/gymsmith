"""Accepting photographs from outside, safely.

Photos of someone's home carry their GPS position, the camera's serial number and the time they
were taken. Uploads are also attacker-shaped input to everything downstream — agents read them,
browsers display them, image models receive them. So every upload is:

  1. identified by its bytes, never by its name or the browser's claimed type — JPEG, PNG and
     WebP only (no SVG: it is a document that can carry script);
  2. checked for a sane pixel count, so a 100 000 × 100 000 decompression bomb is refused before
     anything decodes it;
  3. stripped of metadata: EXIF (keeping only orientation, so the photo still stands the right
     way up), XMP, IPTC, comments and PNG text chunks.

Standard library only. Pixel data is copied byte for byte; nothing is re-encoded.
"""
from __future__ import annotations

import struct

MAX_BYTES = 40 * 1024 * 1024
MAX_PIXELS = 80_000_000


class Rejected(ValueError):
    pass


def sniff(data):
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        raise Rejected("HEIC photos are not supported yet — export as JPEG (on an iPhone: "
                       "Settings → Camera → Formats → Most Compatible)")
    raise Rejected("not a JPEG, PNG or WebP image")


EXT = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def clean(data):
    """(kind, cleaned_bytes, (width, height)). Raises Rejected."""
    if len(data) > MAX_BYTES:
        raise Rejected(f"over {MAX_BYTES // 1_048_576} MB")
    kind = sniff(data)
    out, size = {"jpeg": _jpeg, "png": _png, "webp": _webp}[kind](data)
    if not size or size[0] <= 0 or size[1] <= 0:
        raise Rejected("could not read the image dimensions")
    if size[0] * size[1] > MAX_PIXELS:
        raise Rejected(f"{size[0]}×{size[1]} is too many pixels")
    return kind, out, size


# ---------------------------------------------------------------- jpeg

def _orientation(app1):
    """The EXIF orientation value from an APP1 payload, or None."""
    if app1[:6] != b"Exif\x00\x00":
        return None
    t = app1[6:]
    if len(t) < 8:
        return None
    end = {b"II": "<", b"MM": ">"}.get(t[:2])
    if not end:
        return None
    try:
        ifd = struct.unpack(end + "I", t[4:8])[0]
        n = struct.unpack(end + "H", t[ifd:ifd + 2])[0]
        for i in range(min(n, 512)):
            e = t[ifd + 2 + 12 * i: ifd + 14 + 12 * i]
            tag, typ = struct.unpack(end + "HH", e[:4])
            if tag == 0x0112 and typ == 3:
                v = struct.unpack(end + "H", e[8:10])[0]
                return v if 1 <= v <= 8 else None
    except struct.error:
        return None
    return None


def _exif_orientation_only(v):
    tiff = b"MM\x00*" + struct.pack(">I", 8) + struct.pack(">H", 1) \
        + struct.pack(">HHIHH", 0x0112, 3, 1, v, 0) + struct.pack(">I", 0)
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


# Kept: APP0 (JFIF), APP2 (ICC colour profile), APP14 (Adobe colour transform), and every
# non-APP segment. Dropped: other APPn (EXIF, XMP, IPTC, maker notes) and comments.
_KEEP_APP = {0xE0, 0xE2, 0xEE}


def _jpeg(data):
    out = bytearray(b"\xff\xd8")
    i, orient, size = 2, None, None
    while i < len(data):
        if data[i] != 0xFF:
            raise Rejected("corrupt JPEG")
        m = data[i + 1]
        if m == 0xFF:               # fill byte
            i += 1
            continue
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            out += data[i:i + 2]
            i += 2
            continue
        if m == 0xD9:
            out += data[i:i + 2]
            break
        if i + 4 > len(data):
            raise Rejected("truncated JPEG")
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        seg = data[i:i + 2 + ln]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC) and ln >= 7:
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            size = (w, h)
        if m == 0xDA:               # start of scan: the rest is entropy-coded image data
            if orient and orient != 1:
                out += _exif_orientation_only(orient)
            out += data[i:]
            return bytes(out), size
        if m == 0xE1 and orient is None:
            orient = _orientation(data[i + 4:i + 2 + ln])
        if (0xE0 <= m <= 0xEF and m not in _KEEP_APP) or m == 0xFE:
            i += 2 + ln
            continue
        out += seg
        i += 2 + ln
    return bytes(out), size


# ---------------------------------------------------------------- png

_PNG_DROP = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}


def _png(data):
    out = bytearray(data[:8])
    i, size = 8, None
    while i + 8 <= len(data):
        ln = struct.unpack(">I", data[i:i + 4])[0]
        typ = data[i + 4:i + 8]
        chunk = data[i:i + 12 + ln]
        if len(chunk) < 12 + ln:
            raise Rejected("truncated PNG")
        if typ == b"IHDR":
            size = struct.unpack(">II", data[i + 8:i + 16])
        if typ not in _PNG_DROP:
            out += chunk
        i += 12 + ln
        if typ == b"IEND":
            break
    return bytes(out), size


# ---------------------------------------------------------------- webp

def _webp(data):
    body = bytearray()
    i, size, vp8x_at = 12, None, None
    while i + 8 <= len(data):
        fourcc = data[i:i + 4]
        ln = struct.unpack("<I", data[i + 4:i + 8])[0]
        payload = data[i + 8:i + 8 + ln]
        total = 8 + ln + (ln & 1)
        if fourcc == b"VP8X" and ln >= 10:
            size = (int.from_bytes(payload[4:7], "little") + 1,
                    int.from_bytes(payload[7:10], "little") + 1)
            vp8x_at = len(body) + 8
        elif fourcc == b"VP8 " and ln >= 10 and not size:
            size = (struct.unpack("<H", payload[6:8])[0] & 0x3FFF,
                    struct.unpack("<H", payload[8:10])[0] & 0x3FFF)
        elif fourcc == b"VP8L" and ln >= 5 and not size:
            b = int.from_bytes(payload[1:5], "little")
            size = ((b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1)
        if fourcc not in (b"EXIF", b"XMP "):
            body += data[i:i + total]
        i += total
    if vp8x_at is not None:
        body[vp8x_at] &= ~0x0C & 0xFF       # clear the EXIF and XMP present flags
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + bytes(body), size
