"""Shared format routing for the unified inspect_file/clean_file tools.

Single source of truth for the extension sets and the magic-byte
classification both routers use, so routing rules live in exactly one
place and the three extension sets stay pairwise disjoint.
"""

from __future__ import annotations

from pathlib import Path

from container_meta import detect_container_format
from image_meta import detect_format as detect_image_format

IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif"})
CONTAINER_EXTS = frozenset(
    {
        ".svg",
        ".pdf",
        ".docx",
        ".odt",
        ".html",
        ".htm",
        ".md",
        ".markdown",
        ".mdx",
        ".pptx",
        ".xlsx",
        ".odp",
        ".ods",
    }
)
# Deliberately disjoint from CONTAINER_EXTS: container classification runs
# first, so a shared entry here would be unreachable config that only misleads.
TEXT_EXTS = frozenset(
    {
        ".txt",
        ".text",
        ".css",
        ".js",
        ".py",
        ".rs",
        ".go",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".csv",
    }
)


def classify(path: Path, data: bytes | None = None) -> str:
    """Classify a file as ``"image"``, ``"container"`` or ``"text"``.

    Extension first, then a magic sniff. The sniff reads the file at most
    once and passes the full buffer to the zip detector: a central
    directory sits at the *end* of an OOXML/ODF archive, so a prefix
    slice can never identify DOCX/ODT by content. Callers bound the
    read via MAX_INPUT_BYTES before invoking this.
    """
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in CONTAINER_EXTS:
        # html/md are handled as containers (metadata + optional text body)
        return "container"
    if ext in TEXT_EXTS:
        return "text"
    if data is None:
        data = path.read_bytes()
    if detect_image_format(data[:8]) != "unknown":
        return "image"
    if detect_container_format(path, data) != "unknown":
        return "container"
    return "text"
