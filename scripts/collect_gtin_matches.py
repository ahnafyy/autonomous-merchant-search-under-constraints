#!/usr/bin/env python3
"""Cross-reference GTIN-like SKUs across the 220 domains found in the prior scan.

Re-queries `search_catalog(query="")` once per domain (reusing the already-
discovered MCP endpoint from data/ucp/gtin-scan-2026-08-02.json, so no new
discovery fetch is needed) and this time keeps every GTIN-like (product,
variant) pair instead of only the first 3. Then groups by SKU value to find
any SKU appearing under 2+ distinct domains -- a genuine, automatically
confirmable same-SKU match, not a guess from title similarity.

Only re-probes the 220 domains already confirmed to expose GTIN-shaped SKUs;
does not touch the other ~2800 scanned domains again.
"""
from __future__ import annotations

import json
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_gtin_support import GTIN_PATTERN, search_catalog  # noqa: E402

SCAN_PATH = Path("data/ucp/gtin-scan-2026-08-02.json")
OUTPUT_PATH = Path("data/ucp/gtin-cross-reference-2026-08-02.json")


def collect_domain_skus(domain: str, endpoint: str) -> list[dict[str, object]]:
    products = search_catalog(endpoint, query="")
    rows = []
    for product in products:
        price = product.get("price_range", {}).get("min", {})
        for variant in product.get("variants", []):
            sku = variant.get("sku")
            if sku and GTIN_PATTERN.fullmatch(sku):
                rows.append(
                    {
                        "domain": domain,
                        "sku": sku,
                        "title": product.get("title"),
                        "url": product.get("url"),
                        "price_amount": price.get("amount"),
                        "price_currency": price.get("currency"),
                        "size": variant.get("title"),
                    }
                )
    return rows


def main() -> int:
    scan = json.loads(SCAN_PATH.read_text(encoding="utf-8"))
    domains = scan["domains"]
    print(f"re-querying {len(domains)} domains for full GTIN-like SKU lists")

    all_rows: list[dict[str, object]] = []
    lock = threading.Lock()
    completed = 0

    def run_one(entry: dict[str, object]) -> list[dict[str, object]]:
        try:
            return collect_domain_skus(entry["domain"], entry["mcp_endpoint"])
        except Exception as exc:  # noqa: BLE001 - one bad domain must not abort the batch
            print(f"error on {entry['domain']}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return []

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(run_one, entry): entry for entry in domains}
        for future in as_completed(futures):
            rows = future.result()
            with lock:
                all_rows.extend(rows)
                completed += 1
                if completed % 25 == 0 or completed == len(domains):
                    print(f"progress: {completed}/{len(domains)}", file=sys.stderr)

    by_sku: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in all_rows:
        by_sku[row["sku"]].append(row)

    matches = {
        sku: rows
        for sku, rows in by_sku.items()
        if len({row["domain"] for row in rows}) >= 2
    }

    payload = {
        "schema_version": 1,
        "scan_date": "2026-08-02",
        "domains_reprobed": len(domains),
        "total_gtin_like_skus_observed": len(all_rows),
        "unique_gtin_values_observed": len(by_sku),
        "cross_merchant_matches": matches,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"\ntotal GTIN-like (product, variant) rows collected: {len(all_rows)}")
    print(f"unique GTIN values observed: {len(by_sku)}")
    print(f"SKUs appearing on 2+ distinct domains: {len(matches)}")
    for sku, rows in matches.items():
        domains_involved = sorted({row["domain"] for row in rows})
        print(f"\nSKU {sku} appears on: {domains_involved}")
        for row in rows:
            price = f"{row['price_amount']} {row['price_currency']}"
            print(f"  {row['domain']}: {row['title']} | {price} | {row['url']}")
    print(f"\nwrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
