#!/usr/bin/env python3
"""Deep catalog scan: paginate several pages per domain, not just the default
top-10, to build a real-scale corpus of cross-merchant same-SKU matches instead
of a handful found by luck.

Targets: the domains already confirmed to expose GTIN-shaped SKUs, plus any
books_media-keyword-tagged domains not yet confirmed (a second chance -- their
default top-10 sample may simply not have surfaced a book), plus every endpoint
in the declared-capability inventory.

For each domain, fetches up to --max-pages pages of --page-size products via
search_catalog(query="", pagination={limit, cursor}), stopping early if the
server reports no next page. Every variant SKU is kept (not just GTIN-shaped
ones, so we can inspect what a "no ISBN" bookstore looks like too). Matches are
computed by exact SKU value across domains with different base (registrable)
domains, with a specific ISBN-prefix (978/979) flag since that is the identifier
convention that actually produced real matches so far.

Output paths are derived from --date so repeated runs produce comparable
snapshots rather than overwriting earlier evidence. Per-domain reachability is
recorded so a later snapshot can distinguish "merchant unreachable" from "SKU no
longer offered".

This performs real network requests against live merchant infrastructure. Only
run this against domains explicitly approved for live calls.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_gtin_support import (  # noqa: E402
    GTIN_PATTERN,
    MerchantRefused,
    discover_mcp_endpoint,
    search_catalog_page,
)

DATA_DIR = Path("data/ucp")
GTIN_SCAN_PATH = DATA_DIR / "gtin-scan-2026-08-02.json"
CATEGORY_PATH = DATA_DIR / "candidates-2026-04-02.by-category.json"
INVENTORY_PATH = DATA_DIR / "inventory-declared-capability-2026-08-02.json"
CANDIDATES_PATH = DATA_DIR / "candidates-2026-04-02.json"
# Domains that refused us once are never contacted again.
DENYLIST_PATH = DATA_DIR / "crawler-denylist.txt"
ISBN_PATTERN = re.compile(r"^97[89]\d{10}$")


def load_denylist() -> set[str]:
    if not DENYLIST_PATH.is_file():
        return set()
    return {
        line.split("#", 1)[0].strip()
        for line in DENYLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }


def record_refusal(domain: str, reason: str) -> None:
    with DENYLIST_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{domain}  # {reason}\n")


def base_domain(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def target_domains(
    *, include_inventory: bool = True, include_candidates: bool = False
) -> dict[str, str | None]:
    """Return {domain: known_mcp_endpoint_or_None}."""
    gtin_scan = json.loads(GTIN_SCAN_PATH.read_text(encoding="utf-8"))
    targets: dict[str, str | None] = {
        entry["domain"]: entry.get("mcp_endpoint") for entry in gtin_scan["domains"]
    }
    categories = json.loads(CATEGORY_PATH.read_text(encoding="utf-8"))
    for domain in categories.get("books_media", []):
        targets.setdefault(domain, None)
    if include_inventory and INVENTORY_PATH.is_file():
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        for entry in inventory.get("endpoints", []):
            domain = entry.get("domain")
            if domain:
                targets.setdefault(domain, entry.get("endpoint"))
    if include_candidates and CANDIDATES_PATH.is_file():
        # Every domain whose .well-known document advertised the protocol.
        payload = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
        entries = payload["endpoints"] if isinstance(payload, dict) else payload
        for entry in entries:
            raw = entry.get("capability_url") or entry.get("merchant_id") or ""
            domain = re.sub(r"^https?://", "", raw).split("/")[0]
            if domain:
                targets.setdefault(domain, None)

    denied = load_denylist()
    return {
        domain: endpoint
        for domain, endpoint in targets.items()
        if domain not in denied
    }


def deep_scan_domain(
    domain: str,
    known_endpoint: str | None,
    *,
    max_pages: int,
    page_size: int,
    delay_seconds: float,
    request_timeout_seconds: float = 15.0,
    max_domain_seconds: float | None = None,
) -> tuple[list[dict[str, object]], str]:
    """Return (rows, status) for one domain."""
    started_at = time.monotonic()
    endpoint = known_endpoint or discover_mcp_endpoint(
        domain, timeout_seconds=request_timeout_seconds
    )
    if endpoint is None:
        return [], "no_mcp_endpoint"
    rows: list[dict[str, object]] = []
    cursor: str | None = None
    for page_index in range(max_pages):
        if (
            max_domain_seconds is not None
            and time.monotonic() - started_at >= max_domain_seconds
        ):
            return rows, "timed_out"
        if page_index and delay_seconds:
            time.sleep(delay_seconds)
        products, cursor, has_next = search_catalog_page(
            endpoint,
            query="",
            limit=page_size,
            cursor=cursor,
            timeout_seconds=request_timeout_seconds,
        )
        for product in products:
            price = product.get("price_range", {}).get("min", {})
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
            return rows, "ok"
    # Cap reached while more pages remained: a SKU missing from this snapshot may
    # be truncated rather than delisted.
    return rows, "truncated"


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    temporary.replace(path)


def summarize(
    rows: list[dict[str, object]],
    domain_status: dict[str, str],
    *,
    scan_date: str,
    max_pages: int,
    page_size: int,
) -> dict[str, object]:
    by_sku: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_sku[str(row["sku"])].append(row)

    cross_merchant_matches = {
        sku: sku_rows
        for sku, sku_rows in by_sku.items()
        if len({base_domain(str(r["domain"])) for r in sku_rows}) >= 2
    }
    isbn_matches = {
        sku: sku_rows
        for sku, sku_rows in cross_merchant_matches.items()
        if any(r["is_isbn_shaped"] for r in sku_rows)
    }
    isbn_rows = [r for r in rows if r["is_isbn_shaped"]]

    return {
        "schema_version": 2,
        "scan_date": scan_date,
        "max_pages": max_pages,
        "page_size": page_size,
        "domains_targeted": len(domain_status),
        "domains_ok": sum(1 for status in domain_status.values() if status == "ok"),
        "domains_truncated": sum(
            1 for status in domain_status.values() if status == "truncated"
        ),
        "domains_refused": sum(
            1 for status in domain_status.values() if status.startswith("refused")
        ),
        "domain_status": dict(sorted(domain_status.items())),
        "total_rows": len(rows),
        "unique_skus": len(by_sku),
        "isbn_shaped_row_count": len(isbn_rows),
        "cross_merchant_match_count": len(cross_merchant_matches),
        "isbn_cross_merchant_match_count": len(isbn_matches),
        "isbn_cross_merchant_matches": dict(sorted(isbn_matches.items())),
        "all_cross_merchant_matches": dict(sorted(cross_merchant_matches.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Snapshot date, YYYY-MM-DD")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--workers", type=int, default=15)
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Pause between paginated calls to the same merchant",
    )
    parser.add_argument(
        "--include-candidates",
        action="store_true",
        help="Also scan every domain whose .well-known document advertised the protocol",
    )
    parser.add_argument(
        "--limit-domains", type=int, help="Scan only the first N targets (pilot runs)"
    )
    parser.add_argument(
        "--output-prefix",
        default="deep-scan",
        help="Basename prefix for the generated rows and matches files",
    )
    args = parser.parse_args(argv)

    rows_path = DATA_DIR / f"{args.output_prefix}-rows-{args.date}.jsonl"
    matches_path = DATA_DIR / f"{args.output_prefix}-matches-{args.date}.json"

    targets = target_domains(include_candidates=args.include_candidates)
    if args.limit_domains is not None:
        targets = dict(sorted(targets.items())[: args.limit_domains])
    print(
        f"deep-scanning {len(targets)} domains, up to {args.max_pages} pages of "
        f"{args.page_size} each -> {rows_path}"
    )

    all_rows: list[dict[str, object]] = []
    domain_status: dict[str, str] = {}
    lock = threading.Lock()
    completed = 0

    def run_one(item: tuple[str, str | None]) -> tuple[str, list[dict[str, object]], str]:
        domain, endpoint = item
        try:
            rows, status = deep_scan_domain(
                domain,
                endpoint,
                max_pages=args.max_pages,
                page_size=args.page_size,
                delay_seconds=args.delay_seconds,
            )
        except MerchantRefused as refusal:
            # Do not contact this merchant again, in this run or any future one.
            with lock:
                record_refusal(domain, str(refusal.status))
            return domain, [], f"refused:{refusal.status}"
        except Exception as exc:  # noqa: BLE001 - one bad domain must not abort the batch
            print(f"error on {domain}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return domain, [], f"error:{type(exc).__name__}"
        return domain, rows, status

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_one, item) for item in targets.items()]
        for future in as_completed(futures):
            domain, rows, status = future.result()
            with lock:
                all_rows.extend(rows)
                domain_status[domain] = status
                completed += 1
                if completed % 25 == 0 or completed == len(targets):
                    print(f"progress: {completed}/{len(targets)}", file=sys.stderr)

    all_rows.sort(key=lambda row: (str(row["domain"]), str(row["sku"])))
    _write_rows(rows_path, all_rows)

    payload = summarize(
        all_rows,
        domain_status,
        scan_date=args.date,
        max_pages=args.max_pages,
        page_size=args.page_size,
    )
    matches_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"\ntotal rows collected: {payload['total_rows']}")
    print(f"fully paginated domains: {payload['domains_ok']}/{payload['domains_targeted']}")
    print(f"truncated at page cap: {payload['domains_truncated']}")
    print(f"unique SKUs: {payload['unique_skus']}")
    print(f"ISBN-shaped rows: {payload['isbn_shaped_row_count']}")
    print(f"cross-merchant matches: {payload['cross_merchant_match_count']}")
    print(f"cross-merchant ISBN matches: {payload['isbn_cross_merchant_match_count']}")
    print(f"wrote {rows_path} and {matches_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
