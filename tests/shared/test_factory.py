import pytest

from shared import factory
from shared.providers.auth import LocalAuthProvider
from shared.providers.blob_store import LocalBlobStore
from shared.providers.event_bus import InProcessEventBus, RedisEventBus
from shared.providers.secrets import DotenvSecretsProvider
from shared.settings import Settings


def local_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_local_edition_defaults() -> None:
    s = local_settings()
    assert s.app_edition == "local"
    assert isinstance(factory.make_secrets_provider(s), DotenvSecretsProvider)
    assert isinstance(factory.make_event_bus(s), InProcessEventBus)
    assert isinstance(factory.make_blob_store(s), LocalBlobStore)
    assert isinstance(factory.make_auth_provider(s), LocalAuthProvider)


def test_redis_bus_selected_without_connecting() -> None:
    # constructing the bus must be lazy — no redis server needed to select it
    bus = factory.make_event_bus(local_settings(event_bus_impl="redis"))
    assert isinstance(bus, RedisEventBus)


def test_production_cases_visible_but_unbuilt() -> None:
    with pytest.raises(NotImplementedError):
        factory.make_secrets_provider(local_settings(secrets_impl="supabase_vault"))
    with pytest.raises(NotImplementedError):
        factory.make_event_bus(local_settings(event_bus_impl="kafka"))
    with pytest.raises(NotImplementedError):
        factory.make_blob_store(local_settings(blob_store_impl="supabase"))
    with pytest.raises(NotImplementedError):
        factory.make_auth_provider(local_settings(auth_impl="supabase"))


def test_unknown_impl_rejected() -> None:
    with pytest.raises(ValueError):
        factory.make_event_bus(local_settings(event_bus_impl="carrier_pigeon"))
