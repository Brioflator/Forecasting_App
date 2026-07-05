"""Engine/session factory shared by api and worker (ml never imports this)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from shared.settings import Settings, get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine
    if _engine is None:
        settings = settings or get_settings()
        # pool_pre_ping guards against stale connections after a DB restart —
        # the "zero data loss on restart" property (plan 05 §5) starts here.
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(settings), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Test hook: drop cached engine/session so a new DATABASE_URL takes effect."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
