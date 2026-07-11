"""SSRF guard for outbound connector fetches.

Connector `base_url` is tenant-controlled free text (only `format: uri` in the
JSON Schema). Without a guard, any org member who can create/edit a connector
could point the worker at internal services (`ml:8100`, `postgres`), a cloud
metadata endpoint (`169.254.169.254`), or another tenant's box, and read the
JSONPath-selected response back as their own metric data. `assert_public_url`
blocks that: http(s) only, and every IP the host resolves to must be globally
routable.

Note on DNS rebinding: we validate the resolved addresses but httpx re-resolves
on connect, so a host that flips its record between check and connect isn't
fully defeated here. Blocking all non-global resolutions still removes the
straightforward attack (literal internal IPs / hostnames); pinning the checked
IP into the connection would close the residual gap.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class SsrfError(ValueError):
    """Raised when a connector URL targets a non-public / disallowed host."""


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    # Reject loopback, private, link-local (incl. 169.254.169.254 metadata),
    # multicast, reserved, and unspecified ranges — anything not globally routable.
    return addr.is_global and not addr.is_multicast


def assert_public_url(url: str) -> None:
    """Raise SsrfError unless `url` is http(s) and resolves only to public IPs."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise SsrfError(f"connector URL scheme must be http/https: {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise SsrfError(f"connector URL has no host: {url!r}")

    try:
        infos = socket.getaddrinfo(host, parts.port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SsrfError(f"connector host did not resolve: {host!r}") from exc

    resolved = {str(info[4][0]) for info in infos}
    for ip in resolved:
        if not _is_public_ip(ip):
            raise SsrfError(f"connector host {host!r} resolves to non-public address {ip}")
