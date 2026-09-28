"""
SSRF guards for fetching user-supplied URLs.

Two layers:
1. check_url() validates a URL (scheme, host, port) and resolves its host,
   refusing it if ANY address is not a public internet address. It runs on
   the submitted URL and again on every redirect target.
2. SafeNetworkBackend is plugged into httpx's connection pool. It resolves
   and checks the host again at connect time and then connects the socket to
   that checked IP, so a DNS answer that changes between the check and the
   connect (DNS rebinding) cannot reach an internal address. TLS still uses
   the hostname, so certificate verification is unaffected.
"""

import ipaddress
import re
import socket
from typing import List, Optional, Tuple, Union
from urllib.parse import urlsplit

import httpcore

from app.services.web.errors import WebPageError

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
MAX_URL_LENGTH = 2048

_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa")

# Things inet_aton accepts that aren't dotted-quad: "2130706433", "0x7f.1", "017700000001".
_LEGACY_IPV4_RE = re.compile(r"^(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+)){0,3}$", re.IGNORECASE)

_BLOCKED_MESSAGE = "This address points to a local or private network, which can't be imported"


def _blocked() -> WebPageError:
    return WebPageError("blocked_address", _BLOCKED_MESSAGE)


def is_public_ip(ip: IPAddress) -> bool:
    """True only for addresses routable on the public internet."""
    if isinstance(ip, ipaddress.IPv6Address):
        # IPv6 forms that wrap an IPv4 address are judged by that address.
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
        elif ip in ipaddress.ip_network("64:ff9b::/96"):  # NAT64
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def literal_ip(host: str) -> Optional[IPAddress]:
    """Parse a host that is an IP literal, including legacy IPv4 forms."""
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    if _LEGACY_IPV4_RE.match(host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None


def validate_url(url: str) -> Tuple[str, int]:
    """Check scheme, host and port without touching the network. Returns (host, port)."""
    if len(url) > MAX_URL_LENGTH or any(c.isspace() or ord(c) < 32 for c in url):
        raise WebPageError("invalid_url", "Please enter a valid web page link")

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise WebPageError("invalid_url", "Please enter a valid web page link")

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise WebPageError("invalid_url", "Only http:// and https:// links can be imported")

    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise WebPageError("invalid_url", "Please enter a valid web page link")
    if parts.username is not None or parts.password is not None:
        raise WebPageError("invalid_url", "Links containing a username or password can't be imported")

    port = port if port is not None else (443 if scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise WebPageError("invalid_url", "Only links on the standard web ports (80 and 443) can be imported")

    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        raise _blocked()

    return host, port


def _lookup(host: str, port: int) -> List[str]:
    """DNS lookup, split out so tests can replace it."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def resolve_and_check(host: str, port: int) -> List[IPAddress]:
    """Resolve host and return its addresses, refusing if any is not public."""
    ip = literal_ip(host)
    if ip is not None:
        addresses = [ip]
    else:
        try:
            raw = _lookup(host, port)
        except (socket.gaierror, UnicodeError, OSError):
            raise WebPageError("unreachable", "Could not find this website. Please check the link")
        # Windows can return IPv6 scoped addresses like "fe80::1%12".
        addresses = [ipaddress.ip_address(a.split("%", 1)[0]) for a in raw]
        if not addresses:
            raise WebPageError("unreachable", "Could not find this website. Please check the link")

    if not all(is_public_ip(a) for a in addresses):
        raise _blocked()
    return addresses


def check_url(url: str) -> None:
    """Full pre-request check: URL shape plus every resolved address."""
    host, port = validate_url(url)
    resolve_and_check(host, port)


class SafeNetworkBackend(httpcore.NetworkBackend):
    """Connects only to addresses that pass is_public_ip, pinned at connect time."""

    def __init__(self) -> None:
        self._inner = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if port not in ALLOWED_PORTS:
            raise _blocked()
        last_error: Optional[Exception] = None
        for ip in resolve_and_check(host, port):
            try:
                return self._inner.connect_tcp(str(ip), port, timeout, local_address, socket_options)
            except httpcore.ConnectError as e:
                last_error = e
        raise last_error

    def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore.ConnectError("Unix sockets are not allowed")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)
