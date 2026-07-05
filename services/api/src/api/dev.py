"""Local-only dev endpoint powering the offline demo loop (plan 05 §2.5).

`GET /dev/sample-metric` returns a value following a fixed sinusoid of period 12
+ seeded noise. Enabled only when APP_EDITION=local; 404 otherwise. The worker's
seeded connector polls this so `docker compose up` is self-contained.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import DbDep
from api.schemas import SampleMetricOut
from shared.settings import get_settings
from shared.synthetic import DEMO_PERIOD, sample_value

router = APIRouter(tags=["dev"])


@router.get("/dev/sample-metric", response_model=SampleMetricOut)
def sample_metric() -> SampleMetricOut:
    settings = get_settings()
    if settings.app_edition != "local":
        raise HTTPException(404, "not found")
    now = datetime.now(tz=UTC)
    # Index the sinusoid on minute-since-epoch so the period-12 signal advances
    # one step per 1-minute demo poll.
    step = int(now.timestamp() // 60)
    return SampleMetricOut(value=sample_value(step, m=DEMO_PERIOD), timestamp=now)


class DevTokenIn(BaseModel):
    org_name: str = "Dev Org"
    email: str = "dev@forecast.local"
    role: str = "owner"


class DevTokenOut(BaseModel):
    token: str
    org_id: str
    user_id: str
    role: str


@router.post("/dev/token", response_model=DevTokenOut)
def dev_token(body: DevTokenIn, db: DbDep) -> DevTokenOut:
    """Local-only: mint a dev JWT for exercising MULTI_TENANT=true (plan 05 §4).
    Creates the org, user, and membership if they don't exist, so the token is
    immediately usable against RLS-scoped queries."""
    settings = get_settings()
    if settings.app_edition != "local":
        raise HTTPException(404, "not found")

    from sqlalchemy import select

    from shared.db.models import AuthUser, Organization
    from shared.providers.auth import mint_dev_token

    user = db.scalar(select(AuthUser).where(AuthUser.email == body.email))
    if user is None:
        user = AuthUser(email=body.email)
        db.add(user)
        db.flush()
    org = db.scalar(select(Organization).where(Organization.name == body.org_name))
    if org is None:
        org = Organization(name=body.org_name)
        db.add(org)
        db.flush()
    db.execute(
        text(
            "INSERT INTO organization_members (organization_id, user_id, role) "
            "VALUES (:org, :usr, :role) ON CONFLICT DO NOTHING"
        ),
        {"org": str(org.id), "usr": str(user.id), "role": body.role},
    )

    token = mint_dev_token(
        user_id=str(user.id),
        org_id=str(org.id),
        role=body.role,
        secret=settings.supabase_jwt_secret,
    )
    return DevTokenOut(token=token, org_id=str(org.id), user_id=str(user.id), role=body.role)
