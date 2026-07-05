"""Cross-org RLS isolation tests (plan 05 §4, doc 2 §4.4 written early).

Connects as a dedicated NON-superuser role (`rls_probe`) — the app's own owner
connection legitimately bypasses RLS — and sets the `request.jwt.claim.sub` GUC
the auth.uid() shim reads, mimicking exactly how Supabase resolves the caller.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine


@dataclass
class TwoOrgs:
    user_a: uuid.UUID
    user_b: uuid.UUID
    org_a: uuid.UUID
    org_b: uuid.UUID
    connector_a: uuid.UUID
    connector_b: uuid.UUID


@pytest.fixture
def two_orgs(db_session) -> TwoOrgs:
    ids = TwoOrgs(
        user_a=uuid.uuid4(),
        user_b=uuid.uuid4(),
        org_a=uuid.uuid4(),
        org_b=uuid.uuid4(),
        connector_a=uuid.uuid4(),
        connector_b=uuid.uuid4(),
    )
    definition_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO auth.users (id, email) VALUES (:a, 'a@x'), (:b, 'b@x')"),
        {"a": str(ids.user_a), "b": str(ids.user_b)},
    )
    db_session.execute(
        text("INSERT INTO organizations (id, name) VALUES (:a, 'Org A'), (:b, 'Org B')"),
        {"a": str(ids.org_a), "b": str(ids.org_b)},
    )
    db_session.execute(
        text(
            "INSERT INTO organization_members (organization_id, user_id, role) "
            "VALUES (:oa, :ua, 'owner'), (:ob, :ub, 'owner')"
        ),
        {"oa": str(ids.org_a), "ua": str(ids.user_a), "ob": str(ids.org_b), "ub": str(ids.user_b)},
    )
    db_session.execute(
        text(
            "INSERT INTO connector_definitions (id, key, name, config_schema) "
            "VALUES (:d, 'rls_probe_def', 'RLS', '{}'::jsonb)"
        ),
        {"d": str(definition_id)},
    )
    db_session.execute(
        text(
            "INSERT INTO connectors (id, organization_id, connector_definition_id, name, ingestion_method) "
            "VALUES (:ca, :oa, :d, 'A conn', 'pull'), (:cb, :ob, :d, 'B conn', 'pull')"
        ),
        {
            "ca": str(ids.connector_a),
            "oa": str(ids.org_a),
            "cb": str(ids.connector_b),
            "ob": str(ids.org_b),
            "d": str(definition_id),
        },
    )
    db_session.commit()
    return ids


@pytest.fixture
def probe_engine(_migrated_db: str, db_session) -> Iterator[Engine]:
    """A NON-superuser engine subject to RLS."""
    db_session.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_probe') THEN
                    CREATE ROLE rls_probe LOGIN PASSWORD 'probe' NOSUPERUSER NOBYPASSRLS;
                END IF;
            END
            $$;
            """
        )
    )
    db_session.execute(text("GRANT USAGE ON SCHEMA public, auth TO rls_probe"))
    db_session.execute(
        text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rls_probe")
    )
    db_session.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA auth TO rls_probe"))
    db_session.commit()

    url = make_url(_migrated_db).set(username="rls_probe", password="probe")
    engine = create_engine(url)
    yield engine
    engine.dispose()


def _as_user(conn, user_id: uuid.UUID | None) -> None:
    conn.execute(
        text("SELECT set_config('request.jwt.claim.sub', :uid, false)"),
        {"uid": str(user_id) if user_id else ""},
    )


def test_user_sees_only_their_orgs_rows(two_orgs: TwoOrgs, probe_engine: Engine) -> None:
    with probe_engine.connect() as conn:
        _as_user(conn, two_orgs.user_a)
        names = conn.execute(text("SELECT name FROM connectors")).scalars().all()
        assert names == ["A conn"]

        orgs = conn.execute(text("SELECT name FROM organizations")).scalars().all()
        assert orgs == ["Org A"]

    with probe_engine.connect() as conn:
        _as_user(conn, two_orgs.user_b)
        names = conn.execute(text("SELECT name FROM connectors")).scalars().all()
        assert names == ["B conn"]


def test_anonymous_sees_nothing(two_orgs: TwoOrgs, probe_engine: Engine) -> None:
    with probe_engine.connect() as conn:
        _as_user(conn, None)
        assert conn.execute(text("SELECT count(*) FROM connectors")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM organizations")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM data_points")).scalar() == 0


def test_cannot_insert_into_foreign_org(two_orgs: TwoOrgs, probe_engine: Engine) -> None:
    from sqlalchemy.exc import ProgrammingError

    with probe_engine.connect() as conn:
        _as_user(conn, two_orgs.user_a)
        with pytest.raises(ProgrammingError):  # WITH CHECK violation
            conn.execute(
                text(
                    "INSERT INTO metrics (organization_id, connector_id, name, key) "
                    "VALUES (:org, :conn, 'sneaky', 'sneaky')"
                ),
                {"org": str(two_orgs.org_b), "conn": str(two_orgs.connector_b)},
            )


def test_owner_connection_bypasses_rls(two_orgs: TwoOrgs, db_session) -> None:
    # The app's own (owner) connection sees everything — app-layer filtering is
    # its guard locally; RLS bites for non-owner roles (Supabase authenticated).
    count = db_session.execute(text("SELECT count(*) FROM connectors")).scalar()
    assert count == 2
