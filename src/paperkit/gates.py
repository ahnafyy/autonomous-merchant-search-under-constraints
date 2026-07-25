from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from paperkit.config import ConfigurationError, load_yaml

REQUIRED_GATES = ("scope", "novelty", "design", "evidence", "release")


@dataclass(frozen=True)
class Gate:
    name: str
    status: str
    approved_by: str | None
    approved_on: str | None


def load_gates(path: Path) -> list[Gate]:
    raw = load_yaml(path)
    gates = raw.get("gates")
    if raw.get("schema_version") != 1 or not isinstance(gates, dict):
        raise ConfigurationError("gate status requires schema_version 1 and a gates mapping")
    missing = set(REQUIRED_GATES) - set(gates)
    extra = set(gates) - set(REQUIRED_GATES)
    if missing or extra:
        raise ConfigurationError(
            f"gate names must be exactly {', '.join(REQUIRED_GATES)}; "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )

    parsed: list[Gate] = []
    for name in REQUIRED_GATES:
        item = gates[name]
        if not isinstance(item, dict):
            raise ConfigurationError(f"gate {name} must be a mapping")
        status = item.get("status")
        if status not in {"pending", "approved"}:
            raise ConfigurationError(f"gate {name} status must be pending or approved")
        approved_by = item.get("approved_by")
        approved_on = item.get("approved_on")
        if status == "approved":
            if not isinstance(approved_by, str) or not approved_by.strip():
                raise ConfigurationError(f"approved gate {name} requires approved_by")
            if not isinstance(approved_on, str):
                raise ConfigurationError(f"approved gate {name} requires approved_on")
            try:
                date.fromisoformat(approved_on)
            except ValueError as error:
                raise ConfigurationError(
                    f"approved gate {name} approved_on must use YYYY-MM-DD"
                ) from error
        parsed.append(
            Gate(
                name=name,
                status=status,
                approved_by=approved_by if isinstance(approved_by, str) else None,
                approved_on=approved_on if isinstance(approved_on, str) else None,
            )
        )
    return parsed


def pending_gate_names(gates: list[Gate]) -> list[str]:
    return [gate.name for gate in gates if gate.status != "approved"]


def gate_summary(gates: list[Gate]) -> dict[str, Any]:
    return {
        gate.name: {
            "status": gate.status,
            "approved_by": gate.approved_by,
            "approved_on": gate.approved_on,
        }
        for gate in gates
    }
