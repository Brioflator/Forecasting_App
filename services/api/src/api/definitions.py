"""Load connector definition YAML seeds into connector_definitions at startup.

"Connectors are data, not schema" (guide §5): a new source type is a YAML file
here, upserted by `key` — never a migration.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import ConnectorDefinition


def load_connector_definitions(session: Session, connectors_dir: str | Path) -> int:
    directory = Path(connectors_dir)
    if not directory.exists():
        return 0
    loaded = 0
    for path in sorted(directory.glob("*.yaml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        existing = session.scalar(
            select(ConnectorDefinition).where(ConnectorDefinition.key == spec["key"])
        )
        if existing is None:
            session.add(
                ConnectorDefinition(
                    key=spec["key"],
                    name=spec["name"],
                    description=spec.get("description"),
                    config_schema=spec["config_schema"],
                    supports_push=spec.get("supports_push", False),
                    supports_pull=spec.get("supports_pull", True),
                    supports_agent=spec.get("supports_agent", True),
                )
            )
        else:
            existing.name = spec["name"]
            existing.description = spec.get("description")
            existing.config_schema = spec["config_schema"]
            existing.supports_push = spec.get("supports_push", False)
            existing.supports_pull = spec.get("supports_pull", True)
            existing.supports_agent = spec.get("supports_agent", True)
        loaded += 1
    session.commit()
    return loaded
