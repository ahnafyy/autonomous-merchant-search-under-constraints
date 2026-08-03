from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from autonomous_shopping_optimizer.ucp import (
    load_endpoint_inventory,
    screen_endpoint_inventory,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_ucp_inventory.py"

_CSV_HEADER = (
    "domain,status,ucp_url,http_status,version,has_checkout,has_identity_linking,"
    "has_cart_management,has_order,has_payment_token,capability_count,"
    "ai_bot_policies,transports,last_checked_at,last_success_at\n"
)


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text(_CSV_HEADER + "\n".join(rows) + "\n", encoding="utf-8")


def test_candidates_are_conservatively_ineligible(tmp_path: Path) -> None:
    csv_path = tmp_path / "scan.csv"
    _write_csv(
        csv_path,
        [
            'verified-shop.example,verified,https://verified-shop.example/.well-known/ucp,200,2026-01-23,1,0,0,1,0,2,{},["mcp"],2026-04-01T00:00:00+00:00,2026-04-01T00:00:00+00:00',
            "blocked-shop.example,blocked,https://blocked-shop.example/.well-known/ucp,403,,0,0,0,0,0,0,{},[],2026-04-01T00:00:00+00:00,",
        ],
    )
    output_path = tmp_path / "candidates.json"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(csv_path), str(output_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert [entry["endpoint_id"] for entry in payload["endpoints"]] == [
        "verified-shop.example"
    ]

    endpoints = load_endpoint_inventory(output_path)
    for endpoint in endpoints:
        assert endpoint.permission_status == "unknown"
        assert endpoint.exact_product_lookup is False
        assert endpoint.side_effect_free is False

    report = screen_endpoint_inventory(endpoints)
    assert report.eligible == ()
    assert len(report.excluded) == 1
    assert set(report.excluded[0].reasons) == {
        "permission_unknown",
        "no_exact_product_lookup",
        "operation_has_side_effects",
    }


def test_duplicate_domains_are_rejected(tmp_path: Path) -> None:
    csv_path = tmp_path / "scan.csv"
    _write_csv(
        csv_path,
        [
            'dup.example,verified,https://dup.example/.well-known/ucp,200,2026-01-23,1,0,0,1,0,2,{},["mcp"],2026-04-01T00:00:00+00:00,2026-04-01T00:00:00+00:00',
            'dup.example,verified,https://dup.example/.well-known/ucp,200,2026-01-23,1,0,0,1,0,2,{},["mcp"],2026-04-01T00:00:00+00:00,2026-04-01T00:00:00+00:00',
        ],
    )
    output_path = tmp_path / "candidates.json"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(csv_path), str(output_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "duplicate domains" in result.stderr
    assert not output_path.exists()
