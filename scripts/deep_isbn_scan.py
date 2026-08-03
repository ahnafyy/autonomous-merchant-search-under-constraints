#!/usr/bin/env python3
"""Deep ISBN-focused scan: paginate several pages per domain, not just the
default top-10, to build a real-scale corpus of cross-merchant same-SKU
matches instead of a handful found by luck.

Targets: the 220 domains already confirmed to expose GTIN-shaped SKUs, plus
any books_media-keyword-tagged domains not yet confirmed (a second chance --
their default top-10 sample may simply not have surfaced a book).

For each domain, fetches up to MAX_PAGES pages of PAGE_SIZE products via
search_catalog(query="", pagination={limit, cursor}), stopping early if the
server reports no next page. Every variant SKU is kept (not just GTIN-shaped
ones, so we can inspect what a "no ISBN" bookstore looks like too). Matches
are computed by exact SKU value across domains with different base
(registrable) domains, with a specific ISBN-prefix (978/979) flag since that
is the identifier convention that actually produced real matches so far.
"""
from __future__ import annotations

import json
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_gtin_support import (  # noqa: E402
    GTIN_PATTERN,
    discover_mcp_endpoint,
    search_catalog_page,
)

MAX_PAGES = 5
PAGE_SIZE = 50
GTIN_SCAN_PATH = Path("data/ucp/gtin-scan-2026-08-02.json")
CATEGORY_PATH = Path("data/ucp/candidates-2026-04-02.by-category.json")
OUTPUT_ROWS_PATH = Path("data/ucp/deep-scan-rows-2026-08-02.jsonl")
OUTPUT_MATCHES_PATH = Path("data/ucp/deep-scan-matches-2026-08-02.json")
ISBN_PATTERN = __import__("re").compile(r"^97[89]\d{10}$")


def base_domain(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def target_domains() -> dict[str, str | None]:
    """Return {domain: known_mcp_endpoint_or_None}."""
    gtin_scan = json.loads(GTIN_SCAN_PATH.read_text(encoding="utf-8"))
    targets: dict[str, str | None] = {
        entry["domain"]: entry["mcp_endpoint"] for entry in gtin_scan["domains"]
    }
    categories = json.loads(CATEGORY_PATH.read_text(encoding="utf-8"))
    for domain in categories.get("books_media", []):
        targets.setdefault(domain, None)
    return targets


def deep_scan_domain(domain: str, known_endpoint: str | None) -> list[dict[str, object]]:
    endpoint = known_endpoint or discover_mcp_endpoint(domain)
    if endpoint is None:
        return []
    rows: list[dict[str, object]] = []
    cursor: str | None = None
    for _page in range(MAX_PAGES):
        products, cursor, has_next = search_catalog_page(
            endpoint, query="", limit=PAGE_SIZE, cursor=cursor
        )
        price_default = {}
        for product in products:
            price = product.get("price_range", {}).get("min", price_default)
            for variant in product.get("variants", []):
                sku = variant.get("sku")
                if not sku:
                    continue
                rows.append(
                    {
                        "domain": domain,
                        "sku": sku,
                        "is_isbn_shaped": bool(ISBN_PATTERN.fullmatch(sku)),
                        "is_gtin_shaped": bool(GTIN_PATTERN.fullmatch(sku)),
                        "title": product.get("title"),
                        "url": product.get("url"),
                        "price_amount": price.get("amount"),
                        "price_currency": price.get("currency"),
                    }
                )
        if not has_next or not cursor:
            break
    return rows


def main() -> int:
    targets = target_domains()
    print(f"deep-scanning {len(targets)} domains, up to {MAX_PAGES} pages of "
          f"{PAGE_SIZE} each")

    all_rows: list[dict[str, object]] = []
    lock = threading.Lock()
    completed = 0

    def run_one(item: tuple[str, str | None]) -> list[dict[str, object]]:
        domain, endpoint = item
        try:
            return deep_scan_domain(domain, endpoint)
        except Exception as exc:  # noqa: BLE001 - one bad domain must not abort the batch
            print(f"error on {domain}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return []

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(run_one, item): item for item in targets.items()}
        for future in as_completed(futures):
            rows = future.result()
            with lock:
                all_rows.extend(rows)
                completed += 1
                if completed % 25 == 0 or completed == len(targets):
                    print(f"progress: {completed}/{len(targets)}", file=sys.stderr)

    with OUTPUT_ROWS_PATH.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")

    by_sku: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in all_rows:
        by_sku[row["sku"]].append(row)

    cross_merchant_matches = {}
    for sku, rows in by_sku.items():
        companies = {base_domain(r["domain"]) for r in rows}
        if len(companies) >= 2:
            cross_merchant_matches[sku] = rows

    isbn_rows = [r for r in all_rows if r["is_isbn_shaped"]]
    isbn_matches = {
        sku: rows for sku, rows in cross_merchant_matches.items()
        if any(r["is_isbn_shaped"] for r in rows)
    }

    payload = {
        "schema_version": 1,
        "scan_date": "2026-08-02",
        "domains_targeted": len(targets),
        "total_rows": len(all_rows),
        "unique_skus": len(by_sku),
        "isbn_shaped_row_count": len(isbn_rows),
        "cross_merchant_match_count": len(cross_merchant_matches),
        "isbn_cross_merchant_match_count": len(isbn_matches),
        "isbn_cross_merchant_matches": isbn_matches,
        "all_cross_merchant_matches": cross_merchant_matches,
    }
    OUTPUT_MATCHES_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"\ntotal rows collected: {len(all_rows)}")
    print(f"unique SKUs: {len(by_sku)}")
    print(f"ISBN-shaped rows: {len(isbn_rows)}")
    print(f"cross-merchant matches (any SKU shape): {len(cross_merchant_matches)}")
    print(f"cross-merchant ISBN matches: {len(isbn_matches)}")
    print(f"wrote {OUTPUT_ROWS_PATH} and {OUTPUT_MATCHES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
