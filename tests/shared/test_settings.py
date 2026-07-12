"""Settings behavior that isn't a plain default — edition-dependent knobs."""

from shared.settings import Settings


def make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_local_edition_allows_private_hosts_by_default() -> None:
    # The local edition's bundled demo connector polls this API's own
    # localhost endpoint; a False default would make a fresh install
    # collect nothing out of the box.
    assert make().connector_allow_private_hosts is True
    assert make(app_edition="local").connector_allow_private_hosts is True


def test_production_edition_keeps_ssrf_guard_by_default() -> None:
    assert make(app_edition="production").connector_allow_private_hosts is False


def test_explicit_override_beats_edition_default() -> None:
    assert (
        make(app_edition="local", connector_allow_private_hosts=False).connector_allow_private_hosts
        is False
    )
    assert (
        make(
            app_edition="production", connector_allow_private_hosts=True
        ).connector_allow_private_hosts
        is True
    )
