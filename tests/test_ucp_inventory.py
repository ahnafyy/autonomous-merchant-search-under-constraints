from __future__ import annotations

import json
from pathlib import Path

import pytest
from autonomous_shopping_optimizer import EndpointCapability as PublicEndpointCapability
from autonomous_shopping_optimizer.ucp import (
    EndpointCapability,
    load_endpoint_inventory,
    screen_endpoint_inventory,
)


def _endpoint(**overrides: object) -> EndpointCapability:
    values: dict[str, object] = {
        "endpoint_id": "endpoint-a",
        "merchant_id": "merchant-a",
        "capability_url": "https://merchant.example/.well-known/ucp",
        "protocol_version": "1",
        "read_operation": "product_lookup",
        "auth_env_var": "MERCHANT_A_API_KEY",
        "rate_limit_per_minute": 30,
        "permission_status": "verified",
        "exact_product_lookup": True,
        "side_effect_free": True,
    }
    values.update(overrides)
    return EndpointCapability.from_mapping(values)


def test_screen_inventory_excludes_unverified_or_inexact_endpoints() -> None:
    report = screen_endpoint_inventory(
        [
            _endpoint(),
            _endpoint(endpoint_id="endpoint-b", permission_status="unknown"),
            _endpoint(endpoint_id="endpoint-c", exact_product_lookup=False),
        ]
    )

    assert [endpoint.endpoint_id for endpoint in report.eligible] == ["endpoint-a"]
    assert report.excluded[0].reasons == ("permission_unknown",)
    assert report.excluded[1].reasons == ("no_exact_product_lookup",)


def test_inventory_rejects_duplicate_endpoint_ids() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        screen_endpoint_inventory([_endpoint(), _endpoint()])


def test_inventory_rejects_embedded_url_credentials() -> None:
    with pytest.raises(ValueError, match="must not contain credentials"):
        _endpoint(capability_url="https://user:secret@merchant.example/ucp")


def test_inventory_accepts_secret_names_but_not_secret_values() -> None:
    assert _endpoint(auth_env_var="MERCHANT_API_KEY").auth_env_var == "MERCHANT_API_KEY"
    with pytest.raises(ValueError, match="uppercase environment variable"):
        _endpoint(auth_env_var="ss_live_secret-value")


def test_load_inventory_requires_versioned_list(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "endpoints": [
                    {
                        "endpoint_id": "endpoint-a",
                        "merchant_id": "merchant-a",
                        "capability_url": "https://merchant.example/.well-known/ucp",
                        "protocol_version": "1",
                        "read_operation": "product_lookup",
                        "auth_env_var": None,
                        "rate_limit_per_minute": 10,
                        "permission_status": "verified",
                        "exact_product_lookup": True,
                        "side_effect_free": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert load_endpoint_inventory(inventory)[0].endpoint_id == "endpoint-a"


def test_inventory_contract_is_public() -> None:
    assert PublicEndpointCapability is EndpointCapability