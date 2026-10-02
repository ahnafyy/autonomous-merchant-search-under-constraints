#!/usr/bin/env python3
"""Analyze offer lifecycles and common-mode anomalies in daily panel data."""
from __future__ import annotations

import argparse
import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

from autonomous_shopping_optimizer.panel_quality import (
    Snapshot,
    lifecycle_summary,
    transition_quality,
)


def _observation_date(path: Path) -> str:
    value = path.name[len("panel-observations-") : -len(".jsonl.gz")]
    date.fromisoformat(value)
    return value


def _load(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            rows[(row["domain"], row["sku"])] = row
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/ucp"))
    parser.add_argument("--domain-fraction-threshold", type=float, default=0.15)
    parser.add_argument("--offer-fraction-threshold", type=float, default=0.15)
    args = parser.parse_args(argv)

    snapshots: list[Snapshot] = []
    for path in sorted(args.data_dir.glob("panel-observations-*.jsonl.gz")):
        rows = _load(path)
        if rows:
            snapshots.append((_observation_date(path), rows))

    exclusions_path = args.data_dir / "offer-survival-exclusions.json"
    exclusions = (
        json.loads(exclusions_path.read_text(encoding="utf-8"))
        if exclusions_path.is_file()
        else {}
    )
    included = [snapshot for snapshot in snapshots if snapshot[0] not in exclusions]
    transitions = [
        transition_quality(
            prior,
            current,
            domain_fraction_threshold=args.domain_fraction_threshold,
            offer_fraction_threshold=args.offer_fraction_threshold,
        )
        for prior, current in zip(snapshots, snapshots[1:], strict=False)
    ]
    payload = {
        "included_lifecycle_dates": [observation_date for observation_date, _ in included],
        "excluded_dates": exclusions,
        "lifecycle": lifecycle_summary(included),
        "transitions": transitions,
        "flagged_common_mode_dates": [
            row["current_date"] for row in transitions if row["common_mode_anomaly"]
        ],
    }
    output = args.data_dir / "panel-observation-quality.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())