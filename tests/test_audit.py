"""Tests for finding confidence and aggregate audit scripts."""

from __future__ import annotations

import gzip
import http.server
import ipaddress
import socket
import struct
import sys
import threading
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remove-ai-marks" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import net_guard  # noqa: E402
from audit_lib import aggregate, is_actionable, scan_file  # noqa: E402
from audit_website import collect_urls, fetch, guess_kind, inspect_remote, parse_sitemap  # noqa: E402
from common import classify_finding_confidence  # noqa: E402
from container_meta import inspect_container  # noqa: E402
from text_unicode import inspect_text  # noqa: E402


def test_classify_finding_confidence_buckets():
    cases = {
        "c2patool reports a C2PA-related manifest": "confirmed",
        "PNG chunk caBX (possible C2PA container)": "confirmed",
        "JPEG APP11 segment (JUMBF/C2PA common)": "confirmed",
        "pdf-structured:ai:digitalSourceType": "confirmed",
        "pdf-structured:ai:AIGC": "probable",
        "PNG tEXt: c2pa, contentcredentials": "probable",
        "frontmatter key: generator": "probable",
        "info: cms generator: <meta name=\"generator\" content=\"WordPress\">": "informational",
        "customXml parts: 1": "informational",
        "unsupported container: woff2": "informational",
        "svg <metadata> present": "informational",
        "byte-scan C2PA markers: c2pa": "likely_false_positive",
    }
    for finding, expected in cases.items():
        assert classify_finding_confidence(finding) == expected, finding


def test_text_report_hit_confidence():
    report = inspect_text("a\u200bb")
    assert report.to_dict()["hits"][0]["confidence"] == "probable"

    # Exotic space homoglyphs are weaker context.
    report = inspect_text("a\u2003b")
    assert report.to_dict()["hits"][0]["confidence"] == "informational"


def test_container_report_findings_confidence(tmp_path: Path):
    src = tmp_path / "cms.html"
    src.write_text(
        '<html><head><meta name="generator" content="WordPress 6.0"></head></html>',
        encoding="utf-8",
    )
    report = inspect_container(src)
    assert report.to_dict()["findings_confidence"] == ["informational"]


def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(ctype)
    crc = zlib.crc32(payload, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", crc)


def _minimal_png_with_text() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00")
    text = b"Comment\x00c2pa contentcredentials"
    return (
        sig
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"tEXt", text)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def test_image_report_findings_confidence(tmp_path: Path):
    from image_meta import inspect_image

    src = tmp_path / "t.png"
    src.write_bytes(_minimal_png_with_text())
    report = inspect_image(src)
    d = report.to_dict()
    assert "findings_confidence" in d
    assert any(c in ("probable", "confirmed") for c in d["findings_confidence"])


def test_scan_file_text_and_html(tmp_path: Path):
    text = tmp_path / "a.txt"
    text.write_text("Hello\u200bWorld\n", encoding="utf-8")
    item = scan_file(text)
    assert item["kind"] == "text"
    assert is_actionable(item)

    html = tmp_path / "b.html"
    html.write_text(
        '<html><head><meta name="generator" content="WordPress"></head><body>ok</body></html>',
        encoding="utf-8",
    )
    item = scan_file(html)
    assert item["kind"] == "html"
    assert not is_actionable(item)


def test_aggregate_summary():
    files = [
        {
            "path": "a.txt",
            "kind": "text",
            "has_c2pa": False,
            "has_ai_metadata": False,
            "suspicious_total": 1,
            "findings": ["layer-a [zwj_family] U+200B ZERO WIDTH SPACE (Cf) x1"],
            "confidence": ["probable"],
        },
        {
            "path": "b.html",
            "kind": "html",
            "has_c2pa": False,
            "has_ai_metadata": False,
            "suspicious_total": 0,
            "findings": ["info: cms generator: <meta>"],
            "confidence": ["informational"],
        },
    ]
    summary = aggregate(files)
    assert summary["total"] == 2
    assert summary["actionable_files"] == 1
    assert summary["findings_by_confidence"]["probable"] == 1
    assert summary["findings_by_confidence"]["informational"] == 1
    assert summary["with_suspicious_text"] == 1


def test_parse_sitemap_urlset_and_index():
    data = (
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b'<url><loc>https://x.test/a</loc></url></urlset>'
    )
    kind, urls = parse_sitemap(data)
    assert kind == "urlset"
    assert urls == ["https://x.test/a"]

    idx = (
        b'<sitemapindex><sitemap><loc>https://x.test/s1.xml</loc></sitemap>'
        b"</sitemapindex>"
    )
    assert parse_sitemap(idx) == ("sitemapindex", ["https://x.test/s1.xml"])

    assert parse_sitemap(gzip.compress(data))[0] == "urlset"


def test_guess_kind():
    assert guess_kind("https://x.test/a", b"<html>x</html>", "text/html") == "html"
    assert guess_kind("https://x.test/a.png", b"\x89PNG\r\n\x1a\n", None) == "png"
    assert guess_kind("https://x.test/a", b"%PDF-1.4", None) == "pdf"


def test_inspect_remote_html_cms_informational():
    result = inspect_remote(
        "https://x.test/page",
        b'<html><head><meta name="generator" content="WordPress"></head><body>hi</body></html>',
        "text/html",
    )
    assert result["kind"] == "html"
    assert result["confidence"] == ["informational"]
    assert not is_actionable(result)


# ---------------------------------------------------------------------------
# fetch() SSRF guard: scheme allowlist + resolved-IP policy for remote content
# ---------------------------------------------------------------------------


def _patch_dns(monkeypatch, mapping: dict):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host in mapping:
            ips = mapping[host]
        else:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                raise socket.gaierror(f"no such host {host!r}") from None
            ips = [host]
        return [
            (
                socket.AF_INET6 if ":" in ip else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (ip, port),
            )
            for ip in ips
        ]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_getaddrinfo)


def _start_loopback_server(handler) -> http.server.ThreadingHTTPServer:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class _Body(http.server.BaseHTTPRequestHandler):
    body = b"hello"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format, *args):  # noqa: A002
        pass


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x.test/y", "gopher://x"])
def test_fetch_refuses_non_http_schemes(url):
    with pytest.raises(ValueError):
        fetch(url, 2, 1024)


def test_fetch_user_supplied_url_skips_ip_policy_but_checks_scheme():
    # Scheme-only for user-supplied URLs; no exception expected from policy
    # (the connection itself will fail fast on a bogus-but-http host).
    with pytest.raises(Exception):
        fetch("http://nonexistent.invalid/x", 2, 1024)  # socket error, not policy


def test_fetch_denies_remote_controlled_private_target(monkeypatch):
    _patch_dns(monkeypatch, {"evil.example": ["10.0.0.7"]})
    with pytest.raises(ValueError, match="private/loopback"):
        fetch("http://evil.example/x", 2, 1024, validate_public=True)


def test_fetch_denies_remote_controlled_loopback_target(monkeypatch):
    _patch_dns(monkeypatch, {"rebind.example": ["127.0.0.1"]})
    with pytest.raises(ValueError, match="private/loopback"):
        fetch("http://rebind.example/x", 2, 1024, validate_public=True)


def test_fetch_allow_private_opt_in(monkeypatch):
    _patch_dns(monkeypatch, {"intranet.local": ["127.0.0.1"]})
    server = _start_loopback_server(_Body)
    try:
        body, _ = fetch(
            f"http://intranet.local:{server.server_address[1]}/x",
            5,
            4096,
            validate_public=True,
            allow_private=True,
        )
        assert body == b"hello"
    finally:
        server.shutdown()


def test_redirect_handler_blocks_private_hop_target(monkeypatch):
    """A redirect must not re-aim the crawler at private space mid-hop.

    Tested at the handler level: the *initial* URL passes policy (it
    resolves publicly), and only the redirect target is private.
    """
    from audit_website import _ValidatingRedirectHandler

    _patch_dns(monkeypatch, {"public.example": ["93.184.216.34"], "internal.local": ["192.168.0.10"]})
    handler = _ValidatingRedirectHandler(allow_private=False)
    net_guard.enforce_public("http://public.example/page")  # initial URL passes
    with pytest.raises(ValueError, match="private/loopback"):
        handler.redirect_request(
            None, None, 302, "Found", {}, "http://internal.local/secret"
        )


def test_redirect_handler_allows_private_hop_with_opt_in(monkeypatch):
    from audit_website import _ValidatingRedirectHandler

    _patch_dns(monkeypatch, {"internal.local": ["192.168.0.10"]})
    handler = _ValidatingRedirectHandler(allow_private=True)
    # must not raise; super() handles the actual redirect mechanics
    try:
        handler.redirect_request(None, None, 302, "Found", {}, "http://internal.local/x")
    except (AttributeError, TypeError):
        pass  # super() needs a real Request; policy check already passed


def test_collect_urls_validates_nested_sitemap_index(monkeypatch):
    """Nested sitemap-index <loc> entries are remote-controlled and checked."""
    index = (
        b"<sitemapindex><sitemap><loc>http://nested.example/s1.xml</loc>"
        b"</sitemap></sitemapindex>"
    )

    def fake_fetch(url, timeout, max_bytes, *, validate_public=False, allow_private=False):
        if validate_public:
            net_guard.enforce_public(url, allow_private=allow_private)
        return index, "application/xml"

    _patch_dns(monkeypatch, {"nested.example": ["169.254.1.1"]})
    monkeypatch.setattr("audit_website.fetch", fake_fetch)
    with pytest.raises(ValueError, match="private/loopback"):
        collect_urls("http://sitemap.example/index.xml", 2, 10)
