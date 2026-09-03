#!/usr/bin/env python3
"""Survival curve for tracked offers: how fast do they disappear?

Published price-rigidity work measures how often prices *change*, at daily
resolution at best, and finds them sticky. This measures something different and,
as far as the literature review found, unmeasured: the hazard rate at which an
offer stops being available at all.

Reads every `panel-observations-*.jsonl.gz` and reports, per elapsed day, the
share of originally tracked offers still present. Offers on merchants that did
not answer, or that were truncated at the page cap, are excluded rather than
counted as gone, so an unreachable merchant never inflates the hazard.
"""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            rows[(row["domain"], row["sku"])] = row
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/ucp"))
    args = parser.parse_args(argv)

    files = sorted(args.data_dir.glob("panel-observations-*.jsonl.gz"))
    if len(files) < 2:
        print(
            f"found {len(files)} observation file(s); need at least 2 to measure "
            "survival. Run probe_panel.py on separate days."
        )
        return 0

    def observed_on(path: Path) -> date:
        return date.fromisoformat(path.name[len("panel-observations-") : -len(".jsonl.gz")])

    baseline_path = files[0]
    baseline = _load(baseline_path)
    baseline_date = observed_on(baseline_path)
    start = {key for key, row in baseline.items() if row["present"]}

    print(f"baseline {baseline_date}: {len(start)} offers present\n")
    header = (
        f"{'date':>12} {'days':>5} {'checked':>8} {'present':>8} "
        f"{'survival':>9} {'daily hazard':>13}"
    )
    print(header)

    rows: list[dict[str, Any]] = []
    previous_survival = 1.0
    for path in files[1:]:
        current = _load(path)
        observation_date = observed_on(path)
        elapsed = (observation_date - baseline_date).days
        # Only judge offers whose merchant answered fully on this date.
        checkable = {
            key
            for key in start
            if key in current and current[key]["merchant_fully_paginated"]
        }
        if not checkable:
            continue
        present = sum(1 for key in checkable if current[key]["present"])
        survival = present / len(checkable)
        hazard = (
            1 - (survival / previous_survival)
            if previous_survival > 0
            else 0.0
        )
        per_day = hazard / max(elapsed, 1)
        previous_survival = survival
        print(
            f"{observation_date!s:>12} {elapsed:>5} {len(checkable):>8} {present:>8} "
            f"{survival:>8.2%} {per_day:>12.3%}"
        )
        rows.append(
            {
                "observation_date": observation_date.isoformat(),
                "elapsed_days": elapsed,
                "offers_checked": len(checkable),
                "offers_present": present,
                "survival": round(survival, 6),
            }
        )

    payload = {
        "baseline_date": baseline_date.isoformat(),
        "baseline_offers": len(start),
        "observations": rows,
    }
    out = args.data_dir / "offer-survival.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
