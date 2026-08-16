"""Tests for the shared network guard (SSRF defenses)."""

from __future__ import annotations

import ipaddress
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "remove-ai-marks" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import net_guard  # noqa: E402


def _ip(text: str):
    return ipaddress.ip_address(text)


# --- is_loopback / is_private_or_local --------------------------------------

@pytest.mark.parametrize(
    "text",
    ["127.0.0.1", "127.0.0.2", "127.42.0.9", "127.255.255.254", "::1", "::ffff:127.0.0.1"],
)
def test_is_loopback_accepts_full_range(text):
    assert net_guard.is_loopback(text)


@pytest.mark.parametrize(
    "text",
    ["10.0.0.1", "192.168.1.1", "169.254.1.1", "8.8.8.8", "::", "fe80::1", "example.com", ""],
)
def test_is_loopback_rejects_non_loopback(text):
    assert not net_guard.is_loopback(text)


@pytest.mark.parametrize(
    "text",
    ["127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1", "169.254.1.1", "fd00::1",
     "fe80::1", "224.0.0.1", "0.0.0.0", "::ffff:10.0.0.1"],
)
def test_is_private_or_local_matches_non_public(text):
    assert net_guard.is_private_or_local(text)


@pytest.mark.parametrize("text", ["8.8.8.8", "93.184.216.34", "2001:4860:4860::8888"])
def test_is_private_or_local_accepts_public(text):
    assert not net_guard.is_private_or_local(text)


def test_is_private_or_local_fails_closed_on_garbage():
    assert net_guard.is_private_or_local("not-an-ip")


# --- resolve_addresses -------------------------------------------------------

def test_resolve_addresses_literal_skips_dns():
    assert net_guard.resolve_addresses("127.0.0.5", 80) == [_ip("127.0.0.5")]
    assert net_guard.resolve_addresses("::1", 443) == [_ip("::1")]


def test_resolve_addresses_dedups_and_strips_zones(monkeypatch):
    def fake(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1%lo0", port)),
        ]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake)
    addrs = net_guard.resolve_addresses("h.example", 80)
    assert addrs == [_ip("127.0.0.1"), _ip("fe80::1")]


def test_resolve_addresses_raises_on_dns_failure(monkeypatch):
    def fake(host, port, *args, **kwargs):
        raise socket.gaierror("NXDOMAIN")

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake)
    with pytest.raises(OSError):
        net_guard.resolve_addresses("gone.invalid", 80)


# --- policy helpers ----------------------------------------------------------

def test_enforce_loopback_via_resolution(monkeypatch):
    monkeypatch.setattr(
        net_guard.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.9", port))
        ],
    )
    addrs, is_remote = net_guard.enforce_loopback("http://rebind.example:1")
    assert addrs == [_ip("127.0.0.9")] and not is_remote


def test_enforce_loopback_rejects_public_resolution(monkeypatch):
    monkeypatch.setattr(
        net_guard.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))
        ],
    )
    with pytest.raises(ValueError, match="off-machine"):
        net_guard.enforce_loopback("http://rebind.example:1")


def test_enforce_loopback_flags_remote_when_allowed(monkeypatch):
    monkeypatch.setattr(
        net_guard.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
        ],
    )
    _, is_remote = net_guard.enforce_loopback(
        "http://api.example:1", allow_remote=True
    )
    assert is_remote


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x/y", "http://", ""])
def test_enforce_policies_reject_bad_urls(url):
    with pytest.raises(ValueError):
        net_guard.enforce_loopback(url)
    with pytest.raises(ValueError):
        net_guard.enforce_public(url)


def test_enforce_public_rejects_private_resolution(monkeypatch):
    for private in ("127.0.0.1", "10.1.2.3", "169.254.9.9", "fd00::5"):
        monkeypatch.setattr(
            net_guard.socket,
            "getaddrinfo",
            lambda host, port, *a, addr=private, **k: [
                (socket.AF_INET6 if ":" in addr else socket.AF_INET,
                 socket.SOCK_STREAM, 6, "", (addr, port))
            ],
        )
        with pytest.raises(ValueError, match="private/loopback"):
            net_guard.enforce_public(f"http://intranet.example/{private}")


def test_enforce_public_accepts_public_resolution(monkeypatch):
    monkeypatch.setattr(
        net_guard.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
        ],
    )
    addrs = net_guard.enforce_public("http://site.example/page")
    assert addrs == [_ip("93.184.216.34")]


# --- pinned opener ------------------------------------------------------------

def test_make_pinned_opener_uses_pinned_handlers():
    opener = net_guard.make_pinned_opener(_ip("127.0.0.2"), no_redirect=True)
    handlers = opener.handlers
    http = [h for h in handlers if isinstance(h, net_guard._PinnedHTTPHandler)]
    https = [h for h in handlers if isinstance(h, net_guard._PinnedHTTPSHandler)]
    redirect = [h for h in handlers if isinstance(h, net_guard.NoRedirectHandler)]
    assert http and http[0]._pinned_ip == _ip("127.0.0.2")
    assert https and https[0]._pinned_ip == _ip("127.0.0.2")
    assert redirect, "no_redirect=True must install the refusing redirect handler"
