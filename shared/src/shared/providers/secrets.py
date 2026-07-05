"""SecretsProvider seam (guide §7.3, plan 05 §2.1).

Local implementation reads/writes a gitignored dotenv-style file. The critical
invariant, identical in both editions: the value is fetched at the moment of
the poll and never logged (doc 1 §6.4).
"""

from pathlib import Path
from typing import Protocol


class SecretNotFound(KeyError):
    pass


class SecretsProvider(Protocol):
    def get_secret(self, tenant_id: str, secret_key: str) -> str: ...
    def put_secret(self, tenant_id: str, secret_key: str, value: str) -> None: ...
    def revoke_secret(self, tenant_id: str, secret_key: str) -> None: ...


def _line_key(tenant_id: str, secret_key: str) -> str:
    # ':' is not valid in dotenv keys; '__' keeps the line parseable.
    return f"{tenant_id}__{secret_key}".replace("-", "_")


class DotenvSecretsProvider:
    """Reads KEY=VALUE lines from SECRET_FILE; re-read on every get so puts
    from another process (the api's dev flow) are visible."""

    def __init__(self, secret_file: str | Path):
        self._path = Path(secret_file)

    def _read_all(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        out: dict[str, str] = {}
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
        return out

    def _write_all(self, values: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"{k}={v}\n" for k, v in sorted(values.items()))
        self._path.write_text(body, encoding="utf-8")

    def get_secret(self, tenant_id: str, secret_key: str) -> str:
        key = _line_key(tenant_id, secret_key)
        values = self._read_all()
        if key not in values:
            raise SecretNotFound(secret_key)
        return values[key]

    def put_secret(self, tenant_id: str, secret_key: str, value: str) -> None:
        values = self._read_all()
        values[_line_key(tenant_id, secret_key)] = value
        self._write_all(values)

    def revoke_secret(self, tenant_id: str, secret_key: str) -> None:
        values = self._read_all()
        values.pop(_line_key(tenant_id, secret_key), None)
        self._write_all(values)
