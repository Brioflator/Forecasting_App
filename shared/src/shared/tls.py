"""Make Python's TLS validate against the OS trust store.

External pull connectors talk to public HTTPS APIs. On machines behind a
corporate TLS-intercepting proxy, the presented cert chains to a company root
that lives in the OS trust store but not in certifi's bundle, so the default
httpx verification fails. `truststore` routes verification through the OS store
(the same approach pip uses), which trusts both the public CAs and the
corporate root. A no-op-safe idempotent call: safe to invoke at every entry
point that makes outbound TLS calls (worker startup, seed scripts).
"""

from __future__ import annotations

_injected = False


def use_os_trust_store() -> None:
    global _injected
    if _injected:
        return
    import truststore

    truststore.inject_into_ssl()
    _injected = True
