"""Tests for WebP / TIFF / GIF metadata detection and stripping."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remove-ai-marks" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from image_meta import (  # noqa: E402
    clean_image,
    detect_format,
    inspect_gif,
    inspect_image,
    inspect_tiff,
    inspect_webp,
    strip_gif,
    strip_tiff,
    strip_webp,
)


# --- fixtures (built programmatically; no binary assets in the repo) ---------


def _webp_chunk(fourcc: bytes, payload: bytes) -> bytes:
    return fourcc + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")


def _make_webp(exif: bytes | None = None) -> bytes:
    """Minimal extended WebP: VP8X (EXIF flag set) + VP8L + optional EXIF."""
    flags = 0x08 if exif is not None else 0x00
    vpx = bytes([flags, 0, 0, 0, 0, 0, 0, 0, 0, 0])  # flags + canvas 1x1
    body = b"WEBP" + _webp_chunk(b"VP8X", vpx) + _webp_chunk(b"VP8L", b"\x00" * 8)
    if exif is not None:
        body += _webp_chunk(b"EXIF", exif)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _make_tiff(software: str = "Anthropic Claude", big: str | None = None) -> bytes:
    """Little-endian TIFF with IFD0: ImageWidth/Length, Software (305), ImageDescription (270)."""
    entries = []
    values = bytearray()
    # Software / ImageDescription stored out-of-line so we exercise offsets
    for tag, text in ((305, software), (270, big if big is not None else "scene")):
        raw = text.encode() + b"\x00"
        entries.append((tag, 2, len(raw), None, raw))  # offset filled later
    entries.sort(key=lambda e: e[0])
    entry_count = 2 + 2  # + Width/Length below
    ifd_size = 2 + entry_count * 12 + 4
    data_start = 8 + ifd_size
    out = bytearray(b"II*\x00" + struct.pack("<I", 8))
    out += struct.pack("<H", entry_count)
    # inline tags first (Width 256, Length 257)
    out += struct.pack("<HHII", 256, 3, 1, 7)
    out += struct.pack("<HHII", 257, 3, 1, 7)
    for tag, typ, cnt, _, raw in entries:
        values += raw
    # patch value offsets
    patched = []
    off = data_start
    for tag, typ, cnt, _, raw in entries:
        patched.append((tag, typ, cnt, off, raw))
        off += len(raw)
    for tag, typ, cnt, voff, _raw in patched:
        out += struct.pack("<HHII", tag, typ, cnt, voff)
    out += struct.pack("<I", 0)  # next IFD
    out += values
    return bytes(out)


def _make_gif(comment: bytes | None = None, app_with_marker: bool = False) -> bytes:
    """Minimal GIF89a: LSD, optional comment extension, one image block, trailer."""
    out = bytearray(b"GIF89a" + struct.pack("<HHBBB", 1, 1, 0x00, 0, 0))
    if comment is not None:
        out += b"\x21\xFE"
        for i in range(0, len(comment), 255):
            chunk = comment[i : i + 255]
            out += bytes([len(chunk)]) + chunk
        out += b"\x00"
    if app_with_marker:
        out += b"\x21\xFF\x0B" + b"AI-MARKER\x00\x00" + b"\x04\x00c2pa" + b"\x00"
    # image descriptor 1x1, no local color table, 1 sub-block of LZW data
    out += b"\x2C" + struct.pack("<HHBBB", 0, 0, 1, 1, 0x00) + b"\x02" + b"\x02\x00\x00" + b"\x00"
    out += b"\x3B"
    return bytes(out)


# --- detection -----------------------------------------------------------------


def test_detect_format_new_magic():
    assert detect_format(_make_webp()) == "webp"
    assert detect_format(_make_tiff()) == "tiff"
    assert detect_format(_make_gif()) == "gif"


# --- WebP ----------------------------------------------------------------------


def test_webp_inspect_flags_ai_exif():
    c2, ai, findings = inspect_webp(_make_webp(exif=b"II*\x00\x00\x00\x00\x00Software\x00Claude Anthropic\x00"))
    assert ai
    assert any("EXIF" in f for f in findings)


def test_webp_strip_drops_exif_and_fixes_flags_and_size():
    raw = _make_webp(exif=b"II*\x00" + b"\x00" * 100)
    cleaned, actions = strip_webp(raw, strip_all_metadata=True)
    assert any("drop EXIF" in a for a in actions)
    assert b"EXIF" not in cleaned[12:]
    # RIFF size recomputed and consistent
    (riff_size,) = struct.unpack_from("<I", cleaned, 4)
    assert riff_size == len(cleaned) - 8
    # VP8X EXIF flag cleared
    vpx_flags = cleaned[20]
    assert vpx_flags & 0x08 == 0
    # re-inspect: clean
    c2, ai, _ = inspect_webp(cleaned)
    assert not c2 and not ai


def test_webp_strip_keep_mode_only_drops_marked_chunks():
    raw = _make_webp(exif=b"innocuous exif payload")
    cleaned, actions = strip_webp(raw, strip_all_metadata=False)
    assert b"EXIF" in cleaned  # no markers -> kept
    marked = _make_webp(exif=b"c2pa contentcredentials payload")
    cleaned2, _ = strip_webp(marked, strip_all_metadata=False)
    assert b"EXIF" not in cleaned2[12:]


# --- TIFF ----------------------------------------------------------------------


def test_tiff_inspect_flags_software():
    c2, ai, findings = inspect_tiff(_make_tiff(software="Anthropic Claude"))
    assert ai
    assert any("TIFF metadata tags" in f for f in findings)


def test_tiff_strip_zeroes_values_in_place():
    raw = _make_tiff(software="Anthropic Claude", big="Made with SynthID detector runs")
    cleaned, actions = strip_tiff(raw, strip_all_metadata=True)
    assert any("zero tag 305 (Software)" in a for a in actions)
    assert b"Anthropic" not in cleaned
    assert b"SynthID" not in cleaned
    # in-place zeroing: file size unchanged, header intact
    assert len(cleaned) == len(raw)
    assert cleaned[:4] == b"II*\x00"
    c2, ai, _ = inspect_tiff(cleaned)
    assert not c2 and not ai


def test_tiff_inline_value_zeroed():
    raw = _make_tiff(software="AI")  # 3 bytes -> inline in the entry
    cleaned, actions = strip_tiff(raw, strip_all_metadata=True)
    assert any("zero tag 305" in a for a in actions)
    assert b"\x00\x00\x00\x00AI" not in cleaned.replace(b"\x00\x00\x00\x00AI", b"")


# --- GIF -----------------------------------------------------------------------


def test_gif_inspect_flags_comment_marker():
    c2, ai, findings = inspect_gif(_make_gif(comment=b"Generated by Claude 3.5"))
    assert ai
    assert any("comment extension" in f for f in findings)


def test_gif_strip_drops_comment_keeps_image():
    raw = _make_gif(comment=b"Generated by Claude")
    cleaned, actions = strip_gif(raw, strip_all_metadata=True)
    assert any("drop comment extension" in a for a in actions)
    assert b"Generated by Claude" not in cleaned
    assert cleaned.endswith(b"\x3B")
    # image descriptor and trailer survive
    assert b"\x2C" in cleaned
    c2, ai, _ = inspect_gif(cleaned)
    assert not c2 and not ai


def test_gif_application_extension_with_marker_dropped():
    raw = _make_gif(app_with_marker=True)
    cleaned, actions = strip_gif(raw, strip_all_metadata=True)
    assert any("application extension" in a for a in actions)
    assert b"AI-MARKER" not in cleaned


# --- end-to-end through the unified API -----------------------------------------


def test_clean_image_webp_roundtrip(tmp_path: Path):
    src = tmp_path / "t.webp"
    src.write_bytes(_make_webp(exif=b"II*\x00SynthID visible watermark"))
    dest = tmp_path / "t.cleaned.webp"
    result = clean_image(src, dest, strip_all_metadata=True)
    assert result["format"] == "webp"
    assert not result["still_has_c2pa"]
    assert not result["still_has_ai_metadata"]
    assert detect_format(dest.read_bytes()) == "webp"


def test_inspect_image_reports_tiff(tmp_path: Path):
    src = tmp_path / "t.tiff"
    src.write_bytes(_make_tiff(software="OpenAI DALL-E"))
    report = inspect_image(src)
    assert report.format == "tiff"
    assert report.has_ai_metadata
