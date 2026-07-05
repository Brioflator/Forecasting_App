"""BlobStore seam (plan 05 §2.1) — export files locally, Supabase Storage in prod."""

from pathlib import Path
from typing import Protocol


class BlobStore(Protocol):
    def put(self, path: str, data: bytes, content_type: str) -> str: ...
    def get(self, path: str) -> bytes: ...
    def signed_url(self, path: str, expires_in: int) -> str: ...
    def delete(self, path: str) -> None: ...


class LocalBlobStore:
    """Writes under EXPORT_DIR (mounted ./data/exports volume).

    signed_url returns {API_URL}/exports/{share_token} — the token IS the
    capability locally (doc 1 §6.5); expires_in is enforced by the api route
    against export_jobs.expires_at, not by the filesystem.
    """

    def __init__(self, root: str | Path, api_url: str):
        self._root = Path(root)
        self._api_url = api_url.rstrip("/")

    def _resolve(self, path: str) -> Path:
        full = (self._root / path).resolve()
        if not full.is_relative_to(self._root.resolve()):
            raise ValueError(f"path escapes blob root: {path}")
        return full

    def put(self, path: str, data: bytes, content_type: str) -> str:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return path

    def get(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def signed_url(self, path: str, expires_in: int) -> str:
        return f"{self._api_url}/exports/{path}"

    def delete(self, path: str) -> None:
        full = self._resolve(path)
        if full.exists():
            full.unlink()
