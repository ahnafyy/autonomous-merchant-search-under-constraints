#!/usr/bin/env python3
"""Promote today's live-confirmed UCP domains into a declared_capability inventory.

Reads the domains that successfully returned real `search_catalog` data during
the 2026-08-02 live-collection session (data/ucp/deep-scan-rows-2026-08-02.jsonl)
and builds a schema-valid EndpointCapability inventory for them with
`permission_status: "declared_capability"` (see data/ucp/README.md for exactly
what that status does and does not mean -- it is a documented assumption, not a
case-by-case Terms-of-Service review).

Important honesty note preserved in the output: this session only live-tested
`search_catalog` (free-text search). `exact_product_lookup` is set True because
the merchants' discovery profiles separately declare
`dev.ucp.shopping.catalog.lookup` and every observed product has a stable
identifier -- but `lookup_catalog`/`get_product` were not independently
exercised. That caveat is recorded per-entry, not silently assumed away.

`rate_limit_per_minute` has no observed/declared value from any merchant this
session; a conservative default is used and flagged as assumed, not measured.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEEP_SCAN_ROWS_PATH = Path("data/ucp/deep-scan-rows-2026-08-02.jsonl")
CANDIDATES_PATH = Path("data/ucp/candidates-2026-04-02.json")
OUTPUT_PATH = Path("data/ucp/inventory-declared-capability-2026-08-02.json")
FALLBACK_PROTOCOL_VERSION = "2026-04-08"
ASSUMED_RATE_LIMIT_PER_MINUTE = 30


def _live_confirmed_domains() -> list[str]:
    domains: set[str] = set()
    with DEEP_SCAN_ROWS_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            domains.add(json.loads(line)["domain"])
    return sorted(domains)


def _known_protocol_versions() -> dict[str, str]:
    candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    return {
        entry["endpoint_id"]: entry.get("protocol_version") or FALLBACK_PROTOCOL_VERSION
        for entry in candidates["endpoints"]
    }


def build_entry(domain: str, protocol_version: str) -> dict[str, object]:
    return {
        "endpoint_id": domain,
        "merchant_id": domain,
        "capability_url": f"https://{domain}/.well-known/ucp",
        "protocol_version": protocol_version,
        "read_operation": "search_catalog",
        "auth_env_var": None,
        "rate_limit_per_minute": ASSUMED_RATE_LIMIT_PER_MINUTE,
        "rate_limit_is_assumed": True,
        "permission_status": "declared_capability",
        "exact_product_lookup": True,
        "exact_product_lookup_note": (
            "declared in discovery profile (dev.ucp.shopping.catalog.lookup); "
            "live-tested via search_catalog only this session, lookup_catalog/"
            "get_product not independently confirmed"
        ),
        "side_effect_free": True,
        "confirmed_live_on": "2026-08-02",
    }


def main() -> int:
    domains = _live_confirmed_domains()
    protocol_versions = _known_protocol_versions()

    entries = [
        build_entry(domain, protocol_versions.get(domain, FALLBACK_PROTOCOL_VERSION))
        for domain in domains
    ]
    payload = {"schema_version": 1, "endpoints": entries}

    tmp_path = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(OUTPUT_PATH)

    print(f"live-confirmed domains: {len(domains)}")
    print(f"wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
