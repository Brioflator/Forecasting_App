"""Resolves APP_EDITION + per-concern overrides into concrete providers (doc 1 §2).

No service imports a concrete provider directly; they call make_*() at startup
and depend only on the Protocol. Production cases exist and raise
NotImplementedError so the seam shape is visible from day one (plan 05 §2.1).
"""

from shared.providers.auth import AuthProvider, LocalAuthProvider
from shared.providers.blob_store import BlobStore, LocalBlobStore
from shared.providers.event_bus import EventBus, InProcessEventBus, RedisEventBus
from shared.providers.secrets import DotenvSecretsProvider, SecretsProvider
from shared.settings import Settings


def make_secrets_provider(settings: Settings) -> SecretsProvider:
    match settings.secrets_impl:
        case "dotenv":
            return DotenvSecretsProvider(settings.secret_file)
        case "supabase_vault":
            raise NotImplementedError("SupabaseVaultSecretsProvider is doc 2 §4 scope")
    raise ValueError(f"unknown SECRETS_IMPL: {settings.secrets_impl}")


def make_event_bus(settings: Settings) -> EventBus:
    match settings.event_bus_impl:
        case "inproc":
            return InProcessEventBus()
        case "redis":
            return RedisEventBus(settings.redis_url)
        case "kafka":
            raise NotImplementedError("KafkaEventBus is doc 2 §4 scope")
    raise ValueError(f"unknown EVENT_BUS_IMPL: {settings.event_bus_impl}")


def make_blob_store(settings: Settings) -> BlobStore:
    match settings.blob_store_impl:
        case "local":
            return LocalBlobStore(settings.export_dir, settings.api_url)
        case "supabase":
            raise NotImplementedError("SupabaseBlobStore is doc 2 §4 scope")
    raise ValueError(f"unknown BLOB_STORE_IMPL: {settings.blob_store_impl}")


def make_auth_provider(settings: Settings) -> AuthProvider:
    match settings.auth_impl:
        case "local":
            return LocalAuthProvider(
                multi_tenant=settings.multi_tenant,
                jwt_secret=settings.supabase_jwt_secret,
            )
        case "supabase":
            raise NotImplementedError("SupabaseAuthProvider is doc 2 §4 scope")
    raise ValueError(f"unknown AUTH_IMPL: {settings.auth_impl}")
