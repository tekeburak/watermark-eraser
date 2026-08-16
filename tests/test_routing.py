"""Tests for the shared format routing module (inspect_file/clean_file)."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remove-ai-marks" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import routing  # noqa: E402
from routing import classify  # noqa: E402

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    + b"\x00" * 13
    + b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_docx_bytes(min_size: int = 8192) -> bytes:
    """Build a DOCX zip whose central directory sits well past byte 4096.

    Guards that content detection uses the full buffer: a zip's central
    directory lives at the END of the archive, so a prefix slice would
    never see it. The pad is random so it cannot compress below the size
    we need.
    """
    import io
    import os

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
        zf.writestr("pad.bin", os.urandom(min_size))
    return buf.getvalue()


def test_extension_sets_are_pairwise_disjoint():
    # Container classification runs first, so any extension in both sets is
    # unreachable text config that silently misleads readers.
    assert not routing.IMAGE_EXTS & routing.CONTAINER_EXTS
    assert not routing.IMAGE_EXTS & routing.TEXT_EXTS
    assert not routing.CONTAINER_EXTS & routing.TEXT_EXTS


def test_html_and_markdown_route_to_container_not_text():
    # The old inspect_file TEXT_EXTS wrongly listed these too.
    for ext in (".html", ".htm", ".md", ".markdown", ".mdx"):
        assert ext in routing.CONTAINER_EXTS
        assert ext not in routing.TEXT_EXTS


def test_classify_by_extension(tmp_path: Path):
    assert classify(tmp_path / "photo.PNG") == "image"
    assert classify(tmp_path / "doc.htm") == "container"
    assert classify(tmp_path / "notes.txt") == "text"
    assert classify(tmp_path / "cfg.yaml") == "text"


def test_classify_sniffs_png_magic_without_extension(tmp_path: Path):
    p = tmp_path / "mystery.bin"
    p.write_bytes(PNG_BYTES)
    assert classify(p) == "image"


def test_classify_sniffs_docx_zip_beyond_4096_bytes(tmp_path: Path):
    p = tmp_path / "mystery.bin"
    data = make_docx_bytes()
    assert len(data) > 4096
    p.write_bytes(data)
    assert classify(p) == "container"


def test_classify_falls_back_to_text(tmp_path: Path):
    p = tmp_path / "plain.bin"
    p.write_bytes(b"just some words\n")
    assert classify(p) == "text"


def test_classify_reuses_caller_buffer(tmp_path: Path, monkeypatch):
    p = tmp_path / "mystery.bin"
    p.write_bytes(make_docx_bytes())
    reads = []
    real_read = Path.read_bytes

    def counting_read(self):
        reads.append(self)
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read)
    assert classify(p) == "container"
    # no data given: classify read the file exactly once itself
    assert len(reads) == 1
    data = real_read(p)  # unpatched original -> not counted
    assert classify(p, data) == "container"
    # data provided: classify must not touch the filesystem again
    assert len(reads) == 1
