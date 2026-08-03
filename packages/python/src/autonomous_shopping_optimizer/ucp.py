from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

PermissionStatus = Literal["verified", "declared_capability", "unknown", "denied"]
_ENVIRONMENT_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_PERMISSION_STATUSES = {"verified", "declared_capability", "unknown", "denied"}
_ELIGIBLE_PERMISSION_STATUSES = {"verified", "declared_capability"}


@dataclass(frozen=True)
class EndpointCapability:
    endpoint_id: str
    merchant_id: str
    capability_url: str
    protocol_version: str
    read_operation: str
    auth_env_var: str | None
    rate_limit_per_minute: int
    permission_status: PermissionStatus
    exact_product_lookup: bool
    side_effect_free: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> EndpointCapability:
        permission = value.get("permission_status")
        if permission not in _PERMISSION_STATUSES:
            raise ValueError(
                "permission_status must be verified, declared_capability, unknown, or denied"
            )
        auth_env_var = value.get("auth_env_var")
        if auth_env_var is not None and not isinstance(auth_env_var, str):
            raise ValueError("auth_env_var must be a string or null")
        return cls(
            endpoint_id=_required_string(value, "endpoint_id"),
            merchant_id=_required_string(value, "merchant_id"),
            capability_url=_required_string(value, "capability_url"),
            protocol_version=_required_string(value, "protocol_version"),
            read_operation=_required_string(value, "read_operation"),
            auth_env_var=auth_env_var,
            rate_limit_per_minute=_positive_integer(
                value.get("rate_limit_per_minute"), "rate_limit_per_minute"
            ),
            permission_status=permission,
            exact_product_lookup=_required_boolean(value, "exact_product_lookup"),
            side_effect_free=_required_boolean(value, "side_effect_free"),
        )

    def __post_init__(self) -> None:
        parsed_url = urlparse(self.capability_url)
        is_local_http = parsed_url.scheme == "http" and parsed_url.hostname in {
            "127.0.0.1",
            "localhost",
        }
        if parsed_url.scheme != "https" and not is_local_http:
            raise ValueError("capability_url must use HTTPS or local HTTP")
        if not parsed_url.netloc or parsed_url.username or parsed_url.password:
            raise ValueError("capability_url must not contain credentials")
        if self.auth_env_var is not None and not _ENVIRONMENT_VARIABLE.fullmatch(
            self.auth_env_var
        ):
            raise ValueError("auth_env_var must name an uppercase environment variable")


@dataclass(frozen=True)
class EndpointExclusion:
    endpoint_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class InventoryReport:
    eligible: tuple[EndpointCapability, ...]
    excluded: tuple[EndpointExclusion, ...]


def load_endpoint_inventory(path: Path) -> tuple[EndpointCapability, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("UCP inventory requires schema_version 1")
    endpoints = raw.get("endpoints")
    if not isinstance(endpoints, list):
        raise ValueError("UCP inventory endpoints must be a list")
    parsed = tuple(
        EndpointCapability.from_mapping(value)
        for value in endpoints
        if isinstance(value, Mapping)
    )
    if len(parsed) != len(endpoints):
        raise ValueError("every UCP inventory endpoint must be a mapping")
    _require_unique_endpoint_ids(parsed)
    return parsed


def screen_endpoint_inventory(
    endpoints: Sequence[EndpointCapability],
) -> InventoryReport:
    _require_unique_endpoint_ids(endpoints)
    eligible: list[EndpointCapability] = []
    excluded: list[EndpointExclusion] = []
    for endpoint in sorted(endpoints, key=lambda item: item.endpoint_id):
        reasons: list[str] = []
        if endpoint.permission_status not in _ELIGIBLE_PERMISSION_STATUSES:
            reasons.append(f"permission_{endpoint.permission_status}")
        if not endpoint.exact_product_lookup:
            reasons.append("no_exact_product_lookup")
        if not endpoint.side_effect_free:
            reasons.append("operation_has_side_effects")
        if reasons:
            excluded.append(EndpointExclusion(endpoint.endpoint_id, tuple(reasons)))
        else:
            eligible.append(endpoint)
    return InventoryReport(tuple(eligible), tuple(excluded))


def _require_unique_endpoint_ids(endpoints: Sequence[EndpointCapability]) -> None:
    endpoint_ids = [endpoint.endpoint_id for endpoint in endpoints]
    if len(endpoint_ids) != len(set(endpoint_ids)):
        raise ValueError("UCP inventory endpoint_id values must be unique")


def _required_string(value: Mapping[str, object], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return result


def _required_boolean(value: Mapping[str, object], field: str) -> bool:
    result = value.get(field)
    if not isinstance(result, bool):
        raise ValueError(f"{field} must be a boolean")
    return result


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value