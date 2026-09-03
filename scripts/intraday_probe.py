#!/usr/bin/env python3
"""Intraday probe: does anything change within an agent's search window?

The published price series are daily at best, so nothing is known about
e-commerce offer volatility below one day. That matters here because an agent
search lasts seconds to minutes, not days: if offers are perfectly stable at that
scale, no-recall cannot be defended by churn and must rest on quote expiry
instead.

Probes a small high-overlap sample at log-spaced offsets within one window, so
the request count stays low while covering three orders of magnitude in time.
A negative result is as useful as a positive one and should be reported either
way.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deep_isbn_scan import DATA_DIR, deep_scan_domain, load_denylist  # noqa: E402
from probe_gtin_support import MerchantRefused  # noqa: E402

DEFAULT_OFFSETS = (0, 1, 5, 15, 30, 60)


def select_sample(panel: Path, *, merchants: int, min_overlap: int) -> dict[str, set[str]]:
    """Pick the highest-overlap products, then the merchants carrying them."""
    by_sku: dict[str, set[str]] = collections.defaultdict(set)
    with gzip.open(panel, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            by_sku[row["sku"]].add(row["domain"])

    ranked = sorted(
        (sku for sku, domains in by_sku.items() if len(domains) >= min_overlap),
        key=lambda sku: (-len(by_sku[sku]), sku),
    )
    chosen: dict[str, set[str]] = collections.defaultdict(set)
    for sku in ranked:
        for domain in by_sku[sku]:
            chosen[domain].add(sku)
        if len(chosen) >= merchants:
            break
    return dict(chosen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--label", required=True, help="Window label, e.g. 2026-09-03T14")
    parser.add_argument("--merchants", type=int, default=40)
    parser.add_argument("--min-overlap", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument(
        "--offsets",
        type=int,
        nargs="+",
        default=list(DEFAULT_OFFSETS),
        help="Minutes after start at which to sample",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report the plan without probing"
    )
    args = parser.parse_args(argv)

    denied = load_denylist()
    sample = {
        domain: skus
        for domain, skus in select_sample(
            args.panel, merchants=args.merchants, min_overlap=args.min_overlap
        ).items()
        if domain not in denied
    }
    tracked = sum(len(skus) for skus in sample.values())
    span = max(args.offsets)
    print(
        f"{len(sample)} merchants, {tracked} tracked offers, "
        f"offsets {args.offsets} minutes ({len(args.offsets)} passes over {span} min)"
    )
    if args.dry_run:
        return 0

    out = args.data_dir / f"intraday-{args.label}.jsonl.gz"
    start = time.monotonic()
    with gzip.open(out, "wt", encoding="utf-8") as handle:
        for offset in args.offsets:
            target = start + offset * 60
            while time.monotonic() < target:
                time.sleep(min(15.0, target - time.monotonic()))
            for domain in sorted(sample):
                try:
                    rows, status = deep_scan_domain(
                        domain,
                        None,
                        max_pages=args.max_pages,
                        page_size=args.page_size,
                        delay_seconds=args.delay_seconds,
                    )
                except MerchantRefused as refusal:
                    print(f"  {domain}: refused {refusal.status}", file=sys.stderr)
                    continue
                except Exception as exc:  # noqa: BLE001 - keep the window on schedule
                    print(f"  {domain}: {type(exc).__name__}", file=sys.stderr)
                    continue
                if status not in ("ok", "truncated"):
                    continue
                seen = {row["sku"]: row for row in rows}
                for sku in sorted(sample[domain]):
                    row = seen.get(sku)
                    handle.write(
                        json.dumps(
                            {
                                "offset_minutes": offset,
                                "domain": domain,
                                "sku": sku,
                                "present": row is not None,
                                "price_amount": row.get("price_amount") if row else None,
                                "merchant_fully_paginated": status == "ok",
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
            print(f"pass at +{offset} min complete", file=sys.stderr)

    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")
    print("Compare passes with scripts/offer_survival.py logic, or inspect directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
