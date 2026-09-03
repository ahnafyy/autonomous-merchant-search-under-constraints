#!/usr/bin/env python3
"""Extract the multi-merchant panel from a full discovery snapshot.

A full snapshot is mostly noise for this paper: a product sold by one merchant
can never become an episode. This keeps only SKUs offered by two or more
independent merchants, which shrinks the data by more than an order of magnitude
and leaves exactly what the study replays.

The panel is the thing worth versioning and re-probing daily. The full snapshot
it came from is a discovery artifact and does not belong in git.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
from pathlib import Path

from autonomous_shopping_optimizer.panels import base_domain, load_snapshot


def build_panel(rows, *, min_merchants: int, single_currency: bool) -> dict[str, list]:
    by_sku: dict[str, list] = collections.defaultdict(list)
    for row in rows:
        if row.price_minor and row.currency:
            by_sku[row.sku].append(row)

    panel: dict[str, list] = {}
    for sku, entries in by_sku.items():
        if len({base_domain(entry.domain) for entry in entries}) < min_merchants:
            continue
        if single_currency and len({entry.currency for entry in entries}) != 1:
            continue
        panel[sku] = entries
    return panel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/ucp"))
    parser.add_argument("--prefix", default="deep-scan")
    parser.add_argument("--min-merchants", type=int, default=2)
    parser.add_argument(
        "--any-currency",
        action="store_true",
        help="Keep mixed-currency SKUs too (they cannot become episodes)",
    )
    args = parser.parse_args(argv)

    snapshot = load_snapshot(
        args.data_dir / f"{args.prefix}-rows-{args.date}.jsonl",
        args.data_dir / f"{args.prefix}-matches-{args.date}.json",
    )
    panel = build_panel(
        snapshot.rows,
        min_merchants=args.min_merchants,
        single_currency=not args.any_currency,
    )

    out = args.data_dir / f"panel-{args.date}.jsonl.gz"
    written = 0
    with gzip.open(out, "wt", encoding="utf-8") as handle:
        for sku in sorted(panel):
            for row in sorted(panel[sku], key=lambda r: r.domain):
                handle.write(
                    json.dumps(
                        {
                            "sku": sku,
                            "domain": row.domain,
                            "price_amount": row.price_minor,
                            "price_currency": row.currency,
                            "title": row.title,
                            "is_isbn_shaped": row.is_isbn_shaped,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                written += 1

    histogram = collections.Counter(
        len({base_domain(r.domain) for r in entries}) for entries in panel.values()
    )
    manifest = {
        "snapshot_date": snapshot.scan_date,
        "min_merchants": args.min_merchants,
        "single_currency": not args.any_currency,
        "products": len(panel),
        "observations": written,
        "merchants": len({r.domain for entries in panel.values() for r in entries}),
        "merchant_count_histogram": dict(sorted(histogram.items())),
    }
    manifest_path = args.data_dir / f"panel-{args.date}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"source snapshot : {len(snapshot.rows):>9} rows")
    print(f"panel           : {written:>9} observations across {len(panel)} products")
    print(f"reduction       : {len(snapshot.rows) / max(written, 1):.0f}x smaller")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB) and {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
