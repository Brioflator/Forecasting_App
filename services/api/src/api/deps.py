"""FastAPI dependencies: settings, DB session, and the injected providers.

The implicit org/user is injected by the LocalAuthProvider (doc 1 §6.6); every
tenant-scoped query filters on principal.org_id so the same route code enforces
tenancy once RLS + real auth land (plan 05 §4).
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from shared.db import session as session_mod
from shared.factory import make_auth_provider, make_blob_store
from shared.providers.auth import AuthProvider, Principal
from shared.providers.blob_store import BlobStore
from shared.settings import Settings, get_settings


@lru_cache
def _auth_provider() -> AuthProvider:
    return make_auth_provider(get_settings())


@lru_cache
def _blob_store() -> BlobStore:
    return make_blob_store(get_settings())


def get_db() -> Iterator[Session]:
    factory = session_mod.get_session_factory(get_settings())
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    return _auth_provider().authenticate(authorization)


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]
PrincipalDep = Annotated[Principal, Depends(current_principal)]
BlobDep = Annotated[BlobStore, Depends(_blob_store)]
