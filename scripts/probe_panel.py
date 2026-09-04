#!/usr/bin/env python3
"""Daily re-probe of the multi-merchant panel.

Answers a question the price-rigidity literature does not: how fast do offers
*disappear*? Published work measures price changes, at daily resolution at best,
and finds them sticky. Availability is a different hazard, and no published rate
exists below month scale.

Only merchants that carry a panel product are contacted, which is roughly a third
of the discovery crawl, and only panel SKUs are recorded. Each run appends one
compact observation file, so a month of daily runs costs a few megabytes rather
than re-storing the whole catalog.

Consecutive runs also form calibration/evaluation pairs, so every extra day adds
another set of replayable episodes.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deep_isbn_scan import (  # noqa: E402
    DATA_DIR,
    deep_scan_domain,
    load_denylist,
    record_refusal,
)
from probe_gtin_support import MerchantRefused  # noqa: E402


def load_panel(path: Path) -> dict[str, set[str]]:
    """Return {domain: {sku, ...}} for everything currently tracked."""
    tracked: dict[str, set[str]] = collections.defaultdict(set)
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            tracked[row["domain"]].add(row["sku"])
    return tracked


def _write_json_atomically(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Observation date, YYYY-MM-DD")
    parser.add_argument(
        "--panel",
        type=Path,
        required=True,
        help="Panel file produced by extract_panel.py",
    )
    parser.add_argument("--max-pages", type=int, default=12)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-domain-seconds", type=float, default=90.0)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)

    tracked = load_panel(args.panel)
    denied = load_denylist()
    targets = {d: skus for d, skus in tracked.items() if d not in denied}
    status_path = args.data_dir / f"panel-observations-{args.date}.status.json"
    _write_json_atomically(
        status_path,
        {
            "status": "running",
            "observation_date": args.date,
            "panel_source": args.panel.name,
            "merchants_targeted": len(targets),
            "started_unix_seconds": round(time.time()),
        },
    )
    print(
        f"probing {len(targets)} panel merchants for "
        f"{sum(len(s) for s in targets.values())} tracked offers"
    )

    observations: list[dict[str, object]] = []
    domain_status: dict[str, str] = {}
    lock = threading.Lock()
    completed = 0

    def run_one(item: tuple[str, set[str]]):
        domain, skus = item
        try:
            rows, status = deep_scan_domain(
                domain,
                None,
                max_pages=args.max_pages,
                page_size=args.page_size,
                delay_seconds=args.delay_seconds,
                request_timeout_seconds=args.request_timeout_seconds,
                max_domain_seconds=args.max_domain_seconds,
            )
        except MerchantRefused as refusal:
            with lock:
                record_refusal(domain, str(refusal.status))
            return domain, [], f"refused:{refusal.status}", skus
        except Exception as exc:  # noqa: BLE001 - one bad merchant must not stop the run
            print(f"error on {domain}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return domain, [], f"error:{type(exc).__name__}", skus
        return domain, rows, status, skus

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_one, item) for item in targets.items()]
        for future in as_completed(futures):
            domain, rows, status, skus = future.result()
            seen = {row["sku"]: row for row in rows}
            with lock:
                domain_status[domain] = status
                # A tracked offer is only "gone" when the merchant answered.
                if status in ("ok", "truncated"):
                    for sku in sorted(skus):
                        row = seen.get(sku)
                        observations.append(
                            {
                                "sku": sku,
                                "domain": domain,
                                "present": row is not None,
                                "price_amount": row.get("price_amount") if row else None,
                                "price_currency": (
                                    row.get("price_currency") if row else None
                                ),
                                "merchant_fully_paginated": status == "ok",
                            }
                        )
                completed += 1
                if completed % 50 == 0 or completed == len(targets):
                    print(f"progress: {completed}/{len(targets)}", file=sys.stderr)

    observations.sort(key=lambda row: (row["domain"], row["sku"]))
    out = args.data_dir / f"panel-observations-{args.date}.jsonl.gz"
    temporary_out = out.with_suffix(out.suffix + ".partial")
    with gzip.open(temporary_out, "wt", encoding="utf-8") as handle:
        for row in observations:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    temporary_out.replace(out)

    answered = [row for row in observations if row["merchant_fully_paginated"]]
    present = sum(1 for row in answered if row["present"])
    manifest = {
        "observation_date": args.date,
        "panel_source": args.panel.name,
        "merchants_probed": len(targets),
        "merchants_answered": sum(
            1 for status in domain_status.values() if status in ("ok", "truncated")
        ),
        "merchants_fully_paginated": sum(
            1 for status in domain_status.values() if status == "ok"
        ),
        "offers_checked": len(observations),
        "offers_on_fully_paginated_merchants": len(answered),
        "offers_still_present": present,
        "offers_gone": len(answered) - present,
        "domain_status": dict(sorted(domain_status.items())),
    }
    manifest_path = args.data_dir / f"panel-observations-{args.date}.manifest.json"
    _write_json_atomically(manifest_path, manifest)
    _write_json_atomically(
        status_path,
        {
            "status": "completed",
            "observation_date": args.date,
            "panel_source": args.panel.name,
            "merchants_targeted": len(targets),
            "finished_unix_seconds": round(time.time()),
            "manifest": manifest_path.name,
        },
    )

    if answered:
        gone_rate = (len(answered) - present) / len(answered)
        print(f"\ntracked offers checked : {len(observations)}")
        print(f"on fully paginated     : {len(answered)}")
        print(f"still present          : {present}")
        print(f"gone                   : {len(answered) - present} ({gone_rate:.2%})")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
