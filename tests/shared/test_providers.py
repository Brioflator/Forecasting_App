from pathlib import Path

import pytest

from shared.constants import LOCAL_ORG_ID, LOCAL_USER_ID
from shared.providers.auth import LocalAuthProvider
from shared.providers.blob_store import LocalBlobStore
from shared.providers.event_bus import InProcessEventBus
from shared.providers.secrets import DotenvSecretsProvider, SecretNotFound


def test_dotenv_secrets_roundtrip(tmp_path: Path) -> None:
    provider = DotenvSecretsProvider(tmp_path / "connectors.env")
    provider.put_secret("org1", "braze_api_key", "s3cret")
    assert provider.get_secret("org1", "braze_api_key") == "s3cret"

    provider.put_secret("org1", "braze_api_key", "rotated")
    assert provider.get_secret("org1", "braze_api_key") == "rotated"

    provider.revoke_secret("org1", "braze_api_key")
    with pytest.raises(SecretNotFound):
        provider.get_secret("org1", "braze_api_key")


def test_dotenv_secrets_missing_file(tmp_path: Path) -> None:
    provider = DotenvSecretsProvider(tmp_path / "nope.env")
    with pytest.raises(SecretNotFound):
        provider.get_secret("org1", "anything")


def test_local_blob_store_roundtrip(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path, api_url="http://localhost:8000/")
    stored = store.put("exports/abc123.csv", b"a,b\n1,2\n", "text/csv")
    assert stored == "exports/abc123.csv"
    assert store.get("exports/abc123.csv") == b"a,b\n1,2\n"
    assert store.signed_url("abc123", expires_in=3600) == "http://localhost:8000/exports/abc123"
    store.delete("exports/abc123.csv")
    assert not (tmp_path / "exports" / "abc123.csv").exists()


def test_local_blob_store_rejects_escape(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "root", api_url="http://localhost:8000")
    with pytest.raises(ValueError):
        store.put("../outside.txt", b"x", "text/plain")


def test_inproc_event_bus_fanout() -> None:
    bus = InProcessEventBus()
    seen: list[dict] = []
    bus.subscribe("data_point.ingested", seen.append)
    bus.subscribe("data_point.ingested", seen.append)
    bus.publish("data_point.ingested", {"metric_id": "m1"})
    bus.publish("other.topic", {"ignored": True})
    assert seen == [{"metric_id": "m1"}, {"metric_id": "m1"}]


def test_local_auth_returns_implicit_principal() -> None:
    principal = LocalAuthProvider().authenticate(None)
    assert principal.org_id == LOCAL_ORG_ID
    assert principal.user_id == LOCAL_USER_ID
    assert principal.role == "owner"


def test_local_auth_multi_tenant_validates_dev_jwt() -> None:
    from shared.providers.auth import Unauthorized, mint_dev_token

    provider = LocalAuthProvider(multi_tenant=True)
    token = mint_dev_token(user_id="u-1", org_id="o-1", role="admin")

    principal = provider.authenticate(f"Bearer {token}")
    assert principal.user_id == "u-1"
    assert principal.org_id == "o-1"
    assert principal.role == "admin"

    with pytest.raises(Unauthorized):
        provider.authenticate(None)  # missing header
    with pytest.raises(Unauthorized):
        provider.authenticate("Bearer not-a-jwt")  # garbage
    with pytest.raises(Unauthorized):
        # signed with a different secret
        bad = mint_dev_token(
            user_id="u-1", org_id="o-1", secret="another-32-byte-or-longer-secret-value!"
        )
        provider.authenticate(f"Bearer {bad}")
