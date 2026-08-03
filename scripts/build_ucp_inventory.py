#!/usr/bin/env python3
"""Convert a UCP endpoint scan CSV into a candidate inventory file.

The scan CSV records whether a domain exposes a schema-valid UCP endpoint. That
protocol-detection result is not the same thing as this project's
``permission_status``: a domain can run UCP correctly while still having no
confirmed authorization for automated research collection, and no confirmed
side-effect-free read operation. Every candidate produced here is therefore
written with ``permission_status="unknown"``, ``exact_product_lookup=False``,
and ``side_effect_free=False`` so that ``screen_endpoint_inventory`` excludes
all of them until a human confirms permission and operation semantics per
merchant.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SCHEMA_VERSION = 1
PLACEHOLDER_READ_OPERATION = "product_lookup"
PLACEHOLDER_RATE_LIMIT_PER_MINUTE = 1


def _parse_transports(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        return []
    return parsed


def _build_endpoint(row: dict[str, str]) -> dict[str, object]:
    domain = row["domain"].strip()
    version = row.get("version", "").strip()
    return {
        "endpoint_id": domain,
        "merchant_id": domain,
        "capability_url": row["ucp_url"].strip(),
        "protocol_version": version or "unknown",
        "read_operation": PLACEHOLDER_READ_OPERATION,
        "auth_env_var": None,
        "rate_limit_per_minute": PLACEHOLDER_RATE_LIMIT_PER_MINUTE,
        "permission_status": "unknown",
        "exact_product_lookup": False,
        "side_effect_free": False,
        "scan_status": row["status"].strip(),
        "scan_has_checkout": row.get("has_checkout") == "1",
        "scan_has_order": row.get("has_order") == "1",
        "scan_transports": _parse_transports(row.get("transports", "")),
        "scan_last_success_at": row.get("last_success_at") or None,
    }


def build_inventory(rows: list[dict[str, str]]) -> dict[str, object]:
    seen: dict[str, dict[str, object]] = {}
    duplicates: list[str] = []
    for row in rows:
        if row.get("status") != "verified":
            continue
        endpoint = _build_endpoint(row)
        endpoint_id = endpoint["endpoint_id"]
        if endpoint_id in seen:
            duplicates.append(endpoint_id)
            continue
        seen[endpoint_id] = endpoint
    if duplicates:
        raise ValueError(f"duplicate domains in scan CSV: {sorted(set(duplicates))}")
    endpoints = sorted(seen.values(), key=lambda item: item["endpoint_id"])
    return {"schema_version": SCHEMA_VERSION, "endpoints": endpoints}


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Path to the UCP scan CSV")
    parser.add_argument(
        "output_path",
        type=Path,
        help="Path to write the candidate inventory JSON",
    )
    args = parser.parse_args(argv)

    with args.csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    inventory = build_inventory(rows)
    _write_json_atomic(args.output_path, inventory)

    total = len(rows)
    candidates = len(inventory["endpoints"])
    print(f"scanned rows: {total}")
    print(f"verified-protocol candidates written: {candidates}")
    print(f"wrote: {args.output_path}")
    print(
        "every candidate has permission_status=unknown, exact_product_lookup=False, "
        "side_effect_free=False; none are eligible until a human confirms permission "
        "and read-operation semantics per merchant"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
