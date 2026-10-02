from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from autonomous_shopping_optimizer.replay import SellerCard, SellerDeck


@dataclass(frozen=True)
class UcpDeckBuildResult:
    decks: tuple[SellerDeck, ...]
    input_rows: int
    exclusion_counts: dict[str, int]


def build_ucp_panel_decks(
    path: Path, *, observation_date: str, currency: str = "USD", min_sellers: int = 3
) -> UcpDeckBuildResult:
    """Build one same-SKU seller deck per product from a frozen UCP panel date."""
    if not observation_date:
        raise ValueError("observation_date must be non-empty")
    if min_sellers < 2:
        raise ValueError("min_sellers must be at least two")
    rows = _load_rows(path)
    by_sku: dict[str, dict[str, int]] = defaultdict(dict)
    exclusions: Counter[str] = Counter()
    for row in rows:
        if row.get("present") is not True:
            exclusions["not_present"] += 1
            continue
        sku = row.get("sku")
        domain = row.get("domain")
        amount = row.get("price_amount")
        if not isinstance(sku, str) or not sku:
            exclusions["missing_sku"] += 1
            continue
        if not isinstance(domain, str) or not domain:
            exclusions["missing_domain"] += 1
            continue
        if row.get("price_currency") != currency:
            exclusions["non_target_currency"] += 1
            continue
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            exclusions["missing_or_invalid_price"] += 1
            continue
        by_sku[sku].setdefault(domain, amount)

    decks: list[SellerDeck] = []
    for sku, prices_by_domain in sorted(by_sku.items()):
        if len(prices_by_domain) < min_sellers:
            exclusions["insufficient_sellers"] += len(prices_by_domain)
            continue
        cards = tuple(
            SellerCard(
                seller_id=domain,
                company_id=domain,
                variant_id=sku,
                price_minor=amount,
                currency=currency,
            )
            for domain, amount in sorted(prices_by_domain.items())
        )
        product_id = sku
        decks.append(
            SellerDeck(
                deck_id=f"{product_id}@{observation_date}::ucp-panel",
                product_id=product_id,
                title=None,
                option_key=f"sku={sku}",
                cards=cards,
            )
        )
    return UcpDeckBuildResult(
        decks=tuple(decks),
        input_rows=len(rows),
        exclusion_counts=dict(sorted(exclusions.items())),
    )


def build_ucp_panel_series(
    data_dir: Path, observation_dates: Iterable[str]
) -> tuple[tuple[SellerDeck, ...], dict[str, int]]:
    """Load registered daily panel snapshots as repeated seller decks per SKU."""
    decks: list[SellerDeck] = []
    deck_counts: dict[str, int] = {}
    for observation_date in observation_dates:
        result = build_ucp_panel_decks(
            data_dir / f"panel-observations-{observation_date}.jsonl.gz",
            observation_date=observation_date,
        )
        decks.extend(result.decks)
        deck_counts[observation_date] = len(result.decks)
    return tuple(decks), deck_counts


def _load_rows(path: Path) -> list[dict[str, object]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]