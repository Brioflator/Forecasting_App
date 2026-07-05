from alembic import context
from sqlalchemy import create_engine

from shared.settings import Settings


def get_url() -> str:
    # Settings reads DATABASE_URL from the environment / .env, so migrations
    # always target the same database the services do.
    return Settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=get_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
