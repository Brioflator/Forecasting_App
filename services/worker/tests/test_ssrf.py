"""SSRF guard for connector fetches (worker/ssrf.py).

A tenant-controlled base_url must not be able to reach internal/link-local/
loopback hosts — that would turn the poller into an internal-recon oracle.
"""

from __future__ import annotations

import socket

import pytest

from shared.settings import Settings
from worker import extractors
from worker.extractors import GenericRestExtractor
from worker.ssrf import SsrfError, assert_public_url


def test_public_ip_literal_passes() -> None:
    assert_public_url("https://8.8.8.8/anything")  # no raise


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",  # loopback
        "http://10.0.0.5/",  # private
        "http://192.168.1.1/",  # private
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata / link-local
        "https://[::1]/",  # ipv6 loopback
    ],
)
def test_internal_ip_literals_blocked(url: str) -> None:
    with pytest.raises(SsrfError):
        assert_public_url(url)


def test_non_http_scheme_blocked() -> None:
    with pytest.raises(SsrfError):
        assert_public_url("file:///etc/passwd")
    with pytest.raises(SsrfError):
        assert_public_url("gopher://internal/")


def test_hostname_resolving_to_private_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    # postgres:5433 style internal name → resolves to a private address.
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(SsrfError):
        assert_public_url("http://postgres:5433/")


def test_unresolvable_host_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a, **k):
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(SsrfError):
        assert_public_url("http://does-not-exist.invalid/")


def test_real_egress_client_is_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    # No injected client → the guard runs; a private base_url raises before any GET.
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    extractor = GenericRestExtractor()
    with pytest.raises(SsrfError):
        extractor.fetch({"base_url": "http://ml:8100", "value_path": "$.v"}, None, "* * * * *")


def test_allow_private_hosts_opts_out() -> None:
    # Explicit opt-out disables the guard even on the real client path.
    extractor = GenericRestExtractor(allow_private_hosts=True)
    assert extractor._guard_ssrf is False


def _registry_for_edition(monkeypatch: pytest.MonkeyPatch, edition: str) -> GenericRestExtractor:
    monkeypatch.setattr(extractors, "_REGISTRY", {})
    monkeypatch.setattr(
        "shared.settings.get_settings",
        lambda: Settings(_env_file=None, app_edition=edition),  # type: ignore[call-arg]
    )
    extractor = extractors.default_registry()["generic_rest"]
    assert isinstance(extractor, GenericRestExtractor)
    return extractor


def test_local_edition_demo_connector_can_poll_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: the bundled demo connector polls this API's own
    # /dev/sample-metric on localhost. A fresh local install must not have the
    # SSRF guard reject it (it did when the guard first shipped).
    assert _registry_for_edition(monkeypatch, "local")._guard_ssrf is False


def test_production_edition_registry_stays_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _registry_for_edition(monkeypatch, "production")._guard_ssrf is True
