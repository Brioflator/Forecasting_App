"""AuthProvider seam (plan 05 §2.1).

Local, MULTI_TENANT=false: fixed implicit principal, zero login friction
(doc 1 §6.6).
Local, MULTI_TENANT=true: validates a dev HS256 JWT so the multi-tenant path is
exercisable before production auth exists (plan 05 §4). Claims mirror what the
Supabase JWT will carry: `sub` (user id), `org_id`, `role`.
Production: Supabase JWT validation (doc 2 §4) — factory case exists, impl
doesn't yet.
"""

from dataclasses import dataclass
from typing import Protocol

from shared.constants import LOCAL_ORG_ID, LOCAL_USER_ID

DEV_JWT_ALGORITHM = "HS256"
# local-only; prod uses SUPABASE_JWT_SECRET. 32+ bytes to satisfy RFC 7518.
DEV_JWT_DEFAULT_SECRET = "dev-secret-change-me-not-for-production-0123456789"


class Unauthorized(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    org_id: str
    user_id: str
    role: str  # 'owner' | 'admin' | 'member'  (guide §5 organization_members.role)


class AuthProvider(Protocol):
    def authenticate(self, authorization_header: str | None) -> Principal: ...


class LocalAuthProvider:
    """Single-tenant: ignores the header, returns the seeded implicit principal.
    Multi-tenant: validates a dev JWT (mint one via POST /dev/token)."""

    def __init__(self, multi_tenant: bool = False, jwt_secret: str | None = None):
        self._multi_tenant = multi_tenant
        self._jwt_secret = jwt_secret or DEV_JWT_DEFAULT_SECRET

    def authenticate(self, authorization_header: str | None) -> Principal:
        if not self._multi_tenant:
            return Principal(org_id=LOCAL_ORG_ID, user_id=LOCAL_USER_ID, role="owner")

        if not authorization_header or not authorization_header.lower().startswith("bearer "):
            raise Unauthorized("missing bearer token")
        token = authorization_header.split(" ", 1)[1].strip()

        import jwt as pyjwt

        try:
            claims = pyjwt.decode(token, self._jwt_secret, algorithms=[DEV_JWT_ALGORITHM])
        except pyjwt.PyJWTError as exc:
            raise Unauthorized(f"invalid token: {exc}") from exc

        user_id = claims.get("sub")
        org_id = claims.get("org_id")
        if not user_id or not org_id:
            raise Unauthorized("token missing sub/org_id claims")
        return Principal(
            org_id=str(org_id), user_id=str(user_id), role=claims.get("role", "member")
        )


def mint_dev_token(
    user_id: str, org_id: str, role: str = "member", secret: str | None = None
) -> str:
    """Mint a dev JWT (used by /dev/token and tests)."""
    import jwt as pyjwt

    return pyjwt.encode(
        {"sub": user_id, "org_id": org_id, "role": role},
        secret or DEV_JWT_DEFAULT_SECRET,
        algorithm=DEV_JWT_ALGORITHM,
    )
