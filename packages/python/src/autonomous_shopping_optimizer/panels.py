"""Build frozen merchant panels from dated UCP catalog snapshots.

An episode is one exact SKU offered by at least two independent merchants in a
single currency. Merchant price and availability forecasts come from the earlier
calibration snapshot; the later snapshot is frozen as the held-out panel that every
policy is replayed against.

A SKU present in the calibration snapshot but absent from a *fully paginated* later
snapshot of the same merchant is a genuine delisting, and is represented as an
unavailable offer. If the later snapshot was truncated at the page cap for that
merchant, absence is uninformative and the merchant is dropped from the episode
rather than recorded as a stockout.
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, TextIO

from autonomous_shopping_optimizer.domain import Offer, Price
from autonomous_shopping_optimizer.permits import ResourceVector
from autonomous_shopping_optimizer.replay import FrozenMerchantObservation, FrozenPanel

ISBN_PREFIXES = ("978", "979")


@dataclass(frozen=True)
class SnapshotRow:
    domain: str
    sku: str
    price_minor: int | None
    currency: str | None
    is_isbn_shaped: bool
    title: str | None


@dataclass(frozen=True)
class Snapshot:
    scan_date: str
    rows: tuple[SnapshotRow, ...]
    domain_status: dict[str, str]

    def by_domain_sku(self) -> dict[tuple[str, str], SnapshotRow]:
        return {(row.domain, row.sku): row for row in self.rows}

    def fully_paginated(self, domain: str) -> bool:
        return self.domain_status.get(domain) == "ok"


@dataclass(frozen=True)
class EpisodeFeatures:
    """Pre-registered stratification features, computed from calibration data only."""

    merchant_count: int
    price_dispersion_ratio: Fraction
    price_spread_minor: int
    calibration_stockout_rate: Fraction
    cheapest_calibration_price_minor: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "merchant_count": self.merchant_count,
            "price_dispersion_ratio": float(self.price_dispersion_ratio),
            "price_spread_minor": self.price_spread_minor,
            "calibration_stockout_rate": float(self.calibration_stockout_rate),
            "cheapest_calibration_price_minor": self.cheapest_calibration_price_minor,
        }


@dataclass(frozen=True)
class Episode:
    panel: FrozenPanel
    features: EpisodeFeatures
    currency: str
    is_isbn: bool
    calibration_prices: tuple[tuple[str, int], ...]


def base_domain(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def load_snapshot(rows_path: Path, matches_path: Path) -> Snapshot:
    payload = json.loads(matches_path.read_text(encoding="utf-8"))
    rows: list[SnapshotRow] = []
    with _open_rows(rows_path) as handle:
        for line in handle:
            raw = json.loads(line)
            rows.append(
                SnapshotRow(
                    domain=raw["domain"],
                    sku=raw["sku"],
                    price_minor=raw.get("price_amount"),
                    currency=raw.get("price_currency"),
                    is_isbn_shaped=bool(raw.get("is_isbn_shaped")),
                    title=raw.get("title"),
                )
            )
    rows.sort(key=lambda row: (row.domain, row.sku))
    return Snapshot(
        scan_date=payload["scan_date"],
        rows=tuple(rows),
        domain_status=dict(payload.get("domain_status", {})),
    )


def _open_rows(rows_path: Path) -> TextIO:
    """Read a rows file, preferring a gzipped sibling when one exists.

    Snapshots are large and compress about tenfold, so they are stored gzipped.
    A freshly written `.jsonl` from the scan script is still accepted.
    """
    if rows_path.suffix == ".gz":
        return gzip.open(rows_path, "rt", encoding="utf-8")
    compressed = rows_path.with_suffix(rows_path.suffix + ".gz")
    if compressed.is_file():
        return gzip.open(compressed, "rt", encoding="utf-8")
    return rows_path.open(encoding="utf-8")


def build_episodes(
    calibration: Snapshot,
    evaluation: Snapshot,
    *,
    query_resources: ResourceVector,
    min_merchants: int = 2,
) -> list[Episode]:
    """Return one episode per SKU sold by >= min_merchants independent merchants."""
    calibration_index = calibration.by_domain_sku()
    evaluation_index = evaluation.by_domain_sku()

    by_sku: dict[str, list[SnapshotRow]] = defaultdict(list)
    for row in calibration.rows:
        if row.price_minor and row.currency:
            by_sku[row.sku].append(row)

    episodes: list[Episode] = []
    for sku in sorted(by_sku):
        candidate_rows = by_sku[sku]
        currency = _dominant_currency(candidate_rows)
        if currency is None:
            continue
        merchant_rows = [row for row in candidate_rows if row.currency == currency]
        if len({base_domain(row.domain) for row in merchant_rows}) < min_merchants:
            continue
        merchant_rows = _one_row_per_company(merchant_rows)

        observations: list[FrozenMerchantObservation] = []
        stockouts = 0
        for row in merchant_rows:
            later = evaluation_index.get((row.domain, sku))
            if later is None:
                # Absence only means "delisted" when the merchant was fully scanned.
                if not evaluation.fully_paginated(row.domain):
                    continue
                stockouts += 1
                offer = Offer(
                    product_id=sku, merchant_id=row.domain, available=False, price=None
                )
            elif later.price_minor and later.currency == currency:
                offer = Offer(
                    product_id=sku,
                    merchant_id=row.domain,
                    available=True,
                    price=Price(item_minor=later.price_minor, currency=currency),
                )
            else:
                continue
            observations.append(
                FrozenMerchantObservation(
                    merchant_id=row.domain, offer=offer, resources=query_resources
                )
            )

        if len({base_domain(o.merchant_id) for o in observations}) < min_merchants:
            continue

        calibration_prices = tuple(
            (row.domain, calibration_index[(row.domain, sku)].price_minor or 0)
            for row in merchant_rows
            if any(o.merchant_id == row.domain for o in observations)
        )
        prices = [price for _, price in calibration_prices if price > 0]
        if not prices:
            continue

        episodes.append(
            Episode(
                panel=FrozenPanel(
                    panel_id=f"{sku}@{evaluation.scan_date}",
                    product_id=sku,
                    observations=tuple(observations),
                ),
                features=EpisodeFeatures(
                    merchant_count=len(observations),
                    price_dispersion_ratio=Fraction(max(prices), min(prices)),
                    price_spread_minor=max(prices) - min(prices),
                    calibration_stockout_rate=Fraction(stockouts, len(observations)),
                    cheapest_calibration_price_minor=min(prices),
                ),
                currency=currency,
                is_isbn=sku.startswith(ISBN_PREFIXES) and len(sku) == 13,
                calibration_prices=calibration_prices,
            )
        )
    return episodes


def _dominant_currency(rows: list[SnapshotRow]) -> str | None:
    """Pick the currency shared by the most independent merchants."""
    counts: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.currency:
            counts[row.currency].add(base_domain(row.domain))
    if not counts:
        return None
    return max(sorted(counts), key=lambda currency: len(counts[currency]))


def _one_row_per_company(rows: list[SnapshotRow]) -> list[SnapshotRow]:
    """Keep the cheapest listing per registrable domain so companies are not double counted."""
    best: dict[str, SnapshotRow] = {}
    for row in sorted(rows, key=lambda item: (item.domain, item.price_minor or 0)):
        company = base_domain(row.domain)
        current = best.get(company)
        if current is None or (row.price_minor or 0) < (current.price_minor or 0):
            best[company] = row
    return [best[company] for company in sorted(best)]
