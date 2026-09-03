#!/usr/bin/env python3
"""Report how many products are offered by 2, 3, 5, 8 or more merchants.

This is the metric that decides whether the stopping policies can be separated on
real data. With two merchants an optimal rule and a one-step lookahead are the
same rule, so episodes with three or more independent sellers are the ones that
carry information.

Counts independent sellers by registrable domain, so two storefronts of the same
company are not counted twice, and reports the distribution both for all SKUs and
for the single-currency subset that can actually become an episode.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from autonomous_shopping_optimizer.panels import base_domain, load_snapshot

BUCKETS = (2, 3, 4, 5, 8, 10)


def overlap_distribution(rows) -> tuple[dict[str, list], dict[str, list]]:
    """Return (sku -> rows) for all SKUs and for single-currency SKUs."""
    by_sku: dict[str, list] = collections.defaultdict(list)
    for row in rows:
        if row.price_minor and row.currency:
            by_sku[row.sku].append(row)

    multi = {
        sku: entries
        for sku, entries in by_sku.items()
        if len({base_domain(entry.domain) for entry in entries}) >= 2
    }
    single_currency = {
        sku: entries
        for sku, entries in multi.items()
        if len({entry.currency for entry in entries}) == 1
    }
    return multi, single_currency


def _histogram(groups: dict[str, list]) -> collections.Counter:
    return collections.Counter(
        len({base_domain(entry.domain) for entry in entries})
        for entries in groups.values()
    )


def _render(label: str, groups: dict[str, list]) -> None:
    histogram = _histogram(groups)
    total = sum(histogram.values())
    print(f"\n{label}: {total} products with 2+ independent merchants")
    if not total:
        return
    print(f"  {'merchants':>10}  {'products':>9}  {'at least':>9}")
    for bucket in BUCKETS:
        exact = histogram.get(bucket, 0)
        at_least = sum(count for size, count in histogram.items() if size >= bucket)
        print(f"  {bucket:>10}  {exact:>9}  {at_least:>9}")
    widest = max(histogram)
    print(f"  widest overlap observed: {widest} merchants")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Snapshot date suffix")
    parser.add_argument("--data-dir", type=Path, default=Path("data/ucp"))
    parser.add_argument("--prefix", default="deep-scan")
    parser.add_argument(
        "--compare-date", help="Optional earlier snapshot to compare against"
    )
    args = parser.parse_args(argv)

    def load(date: str):
        return load_snapshot(
            args.data_dir / f"{args.prefix}-rows-{date}.jsonl",
            args.data_dir / f"{args.prefix}-matches-{date}.json",
        )

    snapshot = load(args.date)
    multi, single_currency = overlap_distribution(snapshot.rows)
    merchants = len({row.domain for row in snapshot.rows})
    print(f"snapshot {args.date}: {len(snapshot.rows)} rows from {merchants} merchants")
    _render("All cross-merchant products", multi)
    _render("Single-currency (episode-eligible)", single_currency)

    if args.compare_date:
        before = load(args.compare_date)
        before_multi, before_single = overlap_distribution(before.rows)
        print(f"\n=== change against {args.compare_date} ===")
        for label, old, new in (
            ("cross-merchant products", before_multi, multi),
            ("episode-eligible", before_single, single_currency),
        ):
            old_three = sum(
                1
                for entries in old.values()
                if len({base_domain(e.domain) for e in entries}) >= 3
            )
            new_three = sum(
                1
                for entries in new.values()
                if len({base_domain(e.domain) for e in entries}) >= 3
            )
            print(
                f"  {label:24} {len(old):>6} -> {len(new):>6}   "
                f"(3+ merchants: {old_three} -> {new_three})"
            )

    payload = {
        "snapshot_date": snapshot.scan_date,
        "merchants_with_rows": merchants,
        "cross_merchant_products": len(multi),
        "episode_eligible_products": len(single_currency),
        "histogram_all": dict(sorted(_histogram(multi).items())),
        "histogram_single_currency": dict(sorted(_histogram(single_currency).items())),
    }
    out = args.data_dir / f"overlap-report-{args.date}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
