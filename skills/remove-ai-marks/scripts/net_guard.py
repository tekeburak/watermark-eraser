"""Shared network guards: SSRF defense for the tools that make HTTP requests.

A hostname-string allowlist misses two classes of bypass, both fixed here:

1. *Check-side rebinding.* ``localhost.attacker.example`` is not the literal
   string "localhost", but it can resolve to 127.0.0.1 — and conversely an
   allowed name can flip to a public address between runs. Policy is
   therefore enforced against the **resolved** addresses, and a hostname is
   only as loopback/private as every address it resolves to.

2. *Check-to-connect TOCTOU.* Even a validated hostname can be re-resolved
   to a different address by the moment the HTTP client connects. The
   pinned connection classes below dial the already-validated IP directly,
   so urllib's own ``getaddrinfo`` is never reached. For HTTPS the TLS SNI
   and certificate verification still use the original hostname.

All policy helpers raise ``ValueError`` on refusal; callers translate that
into their own exit style. ``OSError`` from resolution propagates so callers
can fail closed with a clear message.
"""

from __future__ import annotations

import errno
import functools
import http.client
import ipaddress
import socket
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

Address = ipaddress.IPv4Address | ipaddress.IPv6Address


def parse_ip(host: str) -> Address | None:
    """Parse a literal IP (bracket-stripped, zone-id-stripped), else None."""
    text = host.strip("[]").split("%", 1)[0]
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def _normalize(ip: Address) -> Address:
    """Map IPv4-mapped IPv6 (::ffff:127.0.0.1) to its IPv4 form."""
    if ip.version == 6:
        mapped = ip.ipv4_mapped  # type: ignore[attr-defined]
        if mapped is not None:
            return mapped
    return ip


def is_loopback(ip: Address | str) -> bool:
    """True for the full 127.0.0.0/8 range, ::1, and IPv4-mapped forms.

    Takes an Address or a literal-IP string. Hostnames must be resolved
    first — a name is never "loopback" by itself.
    """
    if isinstance(ip, str):
        parsed = parse_ip(ip)
        if parsed is None:
            return False
        ip = parsed
    return _normalize(ip).is_loopback


def is_private_or_local(ip: Address | str) -> bool:
    """True for anything that is not a public unicast address.

    Covers loopback, private, link-local, reserved, unspecified and
    multicast ranges (RFC1918/4193, 169.254/fe80::, 100.64/10 CGNAT is
    matched by ``is_private`` on Python 3.12+). Unparseable input fails
    closed: treated as private.
    """
    if isinstance(ip, str):
        parsed = parse_ip(ip)
        if parsed is None:
            return True
        ip = parsed
    ip = _normalize(ip)
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def check_scheme(url: str) -> None:
    """Refuse any URL whose scheme is not http(s) (and hostless URLs).

    The minimal guard for user-supplied URLs; remote-controlled URLs need
    the full address policies below.
    """
    _scheme_host_port(url)


def _scheme_host_port(url: str) -> tuple[str, str, int]:
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http(s), got {u.scheme or '(none)'!r}: {url}")
    host = u.hostname or ""
    if not host:
        raise ValueError(f"URL has no host: {url}")
    try:
        port = u.port
    except ValueError as e:
        raise ValueError(f"URL has an invalid port: {url}") from e
    if port is None:
        port = 443 if u.scheme == "https" else 80
    return u.scheme, host, port


def resolve_addresses(host: str, port: int) -> list[Address]:
    """Resolve *host* (or parse it, when literal) to a deduped address list.

    Every address the name resolves to is returned — policy must hold for
    all of them, or a dual-stack answer set can smuggle one bad address
    past a check that only looked at the first.
    """
    literal = parse_ip(host)
    if literal is not None:
        return [literal]
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as e:
        raise OSError(f"cannot resolve {host!r}: {e}") from e
    addrs: list[Address] = []
    for _, _, _, _, sockaddr in infos:
        ip = parse_ip(sockaddr[0])
        if ip is not None and ip not in addrs:
            addrs.append(ip)
    if not addrs:
        raise OSError(f"no usable addresses for {host!r}")
    return addrs


def enforce_loopback(
    url: str, *, allow_remote: bool = False
) -> tuple[list[Address], bool]:
    """Loopback-only policy for the rewrite backends.

    Requires http(s) and, unless *allow_remote* is set, that every resolved
    address be loopback. Returns ``(addresses, is_remote)`` — the addresses
    are pre-validated for connection pinning; *is_remote* tells the caller
    to emit its off-machine warning.
    """
    _, host, port = _scheme_host_port(url)
    addrs = resolve_addresses(host, port)
    if allow_remote:
        return addrs, not all(is_loopback(a) for a in addrs)
    bad = [str(a) for a in addrs if not is_loopback(a)]
    if bad:
        raise ValueError(
            f"host '{host}' resolves to non-loopback address(es) "
            f"{', '.join(bad)}; refusing to send content off-machine"
        )
    return addrs, False


def enforce_public(url: str, *, allow_private: bool = False) -> list[Address]:
    """Public-only policy for crawler targets (remote-controlled URLs).

    Sitemap <loc> entries and redirect targets come from third-party
    content; they must not aim the crawler at internal services. Requires
    http(s) and, unless *allow_private* is set, that every resolved address
    be public. Returns the validated addresses.
    """
    _, host, port = _scheme_host_port(url)
    if allow_private:
        return resolve_addresses(host, port)
    addrs = resolve_addresses(host, port)
    bad = [str(a) for a in addrs if is_private_or_local(a)]
    if bad:
        raise ValueError(
            f"target '{host}' resolves to private/loopback address(es) "
            f"{', '.join(bad)}; refusing to fetch remote-controlled content "
            "from local networks (pass --allow-private-targets to override)"
        )
    return addrs


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse HTTP redirects.

    urllib's default handler re-sends the request headers on 301/302/303,
    which would forward the Authorization header (API key) to an unvalidated
    host behind the localhost allowlist. Any 3xx now surfaces as HTTPError.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that dials a pre-validated IP, not ``self.host``."""

    def __init__(self, *args, pinned_ip: Address | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        assert self._pinned_ip is not None, "pinned_ip is required"
        sys.audit("http.client.connect", self, self._pinned_ip, self.port)
        self.sock = socket.create_connection(
            (str(self._pinned_ip), self.port),
            timeout=self.timeout,
            source_address=self.source_address,
        )
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as e:
            if e.errno != errno.ENOPROTOOPT:
                raise
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection dialing a pre-validated IP.

    TLS still uses the original hostname for SNI and certificate
    verification — pinning changes where the packet goes, not who the
    server claims to be.
    """

    def __init__(self, *args, pinned_ip: Address | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        assert self._pinned_ip is not None, "pinned_ip is required"
        sys.audit("http.client.connect", self, self._pinned_ip, self.port)
        sock = socket.create_connection(
            (str(self._pinned_ip), self.port),
            timeout=self.timeout,
            source_address=self.source_address,
        )
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(sock, server_hostname=server_hostname)
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, pinned_ip: Address):
        super().__init__()
        self._pinned_ip = pinned_ip

    def http_open(self, req):  # noqa: N802
        factory = functools.partial(_PinnedHTTPConnection, pinned_ip=self._pinned_ip)
        return self.do_open(factory, req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip: Address):
        super().__init__()
        self._pinned_ip = pinned_ip

    def https_open(self, req):  # noqa: N802
        factory = functools.partial(_PinnedHTTPSConnection, pinned_ip=self._pinned_ip)
        return self.do_open(factory, req)


def make_pinned_opener(address: Address, *, no_redirect: bool = False):
    """Opener whose connections dial *address* (already policy-validated).

    DNS is bypassed entirely at connect time, so a hostname cannot rebind
    between the policy check and the TCP connection.
    """
    handlers: list[urllib.request.BaseHandler] = [
        _PinnedHTTPHandler(address),
        _PinnedHTTPSHandler(address),
    ]
    if no_redirect:
        handlers.append(NoRedirectHandler())
    return urllib.request.build_opener(*handlers)
