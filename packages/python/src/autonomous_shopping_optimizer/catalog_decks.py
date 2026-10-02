from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from autonomous_shopping_optimizer.panels import base_domain
from autonomous_shopping_optimizer.replay import SellerCard, SellerDeck

TITLE_GENERIC_TOKENS = frozenset(
    {
        "and",
        "black",
        "carry",
        "calculator",
        "charger",
        "cookware",
        "driver",
        "earbuds",
        "fitness",
        "for",
        "headphones",
        "large",
        "maker",
        "medium",
        "men",
        "mens",
        "new",
        "on",
        "pack",
        "paper",
        "printer",
        "protein",
        "set",
        "shampoo",
        "shoes",
        "size",
        "small",
        "the",
        "with",
        "women",
        "womens",
    }
)


@dataclass(frozen=True)
class DeckBuildResult:
    decks: tuple[SellerDeck, ...]
    input_rows: int
    eligible_rows: int
    exclusion_counts: dict[str, int]


def load_catalog_offer_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON on line {line_number}") from error
            if not isinstance(value, dict):
                raise ValueError(f"offer row {line_number} must be an object")
            rows.append(value)
    return rows


def option_key(row: Mapping[str, object]) -> str | None:
    product = _mapping(row.get("product"))
    variant = _mapping(row.get("variant"))
    for candidate in (
        variant.get("inputs"),
        variant.get("options"),
        product.get("selected"),
    ):
        pairs = _option_pairs(candidate)
        if pairs:
            return "|".join(f"{name}={label}" for name, label in sorted(pairs))
    title = _normalized_text(variant.get("title"))
    return f"variant-title={title}" if title else None


def exact_model_title_key(
    row: Mapping[str, object], *, excluded_title_phrases: Iterable[str] = ()
) -> str | None:
    title = _normalized_text(_mapping(row.get("product")).get("title"))
    if any(_normalized_text(phrase) in title for phrase in excluded_title_phrases):
        return None
    informative = set(title.split()) - TITLE_GENERIC_TOKENS
    if len(informative) < 3 or not any(
        any(character.isdigit() for character in token) for token in informative
    ):
        return None
    return title


def build_seller_decks(
    rows: Iterable[Mapping[str, object]],
    *,
    currency: str = "USD",
    min_sellers: int = 3,
    merge_exact_model_titles: bool = False,
    excluded_title_phrases: Iterable[str] = (),
) -> DeckBuildResult:
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency must be an ISO 4217 code")
    if isinstance(min_sellers, bool) or min_sellers < 2:
        raise ValueError("min_sellers must be at least two")

    materialized = list(rows)
    exclusions: Counter[str] = Counter()
    grouped: dict[tuple[str, str], list[tuple[Mapping[str, object], str]]] = defaultdict(list)
    eligible_rows = 0
    for row in materialized:
        if row.get("analysis_eligible") is not True:
            reasons = row.get("exclusion_reasons")
            if isinstance(reasons, list) and reasons:
                exclusions.update(str(reason) for reason in reasons)
            else:
                exclusions["collector_ineligible"] += 1
            continue
        product = _mapping(row.get("product"))
        price = _mapping(row.get("price"))
        product_id = product.get("id")
        if not isinstance(product_id, str) or not product_id:
            exclusions["missing_product_id"] += 1
            continue
        if price.get("currency") != currency:
            exclusions["non_target_currency"] += 1
            continue
        model_title = (
            exact_model_title_key(
                row, excluded_title_phrases=excluded_title_phrases
            )
            if merge_exact_model_titles
            else None
        )
        key = "product-level-offer" if model_title else option_key(row)
        if key is None:
            exclusions["missing_option_identity"] += 1
            continue
        eligible_rows += 1
        identity = f"title::{model_title}" if model_title else product_id
        grouped[(identity, key)].append((row, _company_id(row)))

    by_product: dict[str, list[SellerDeck]] = defaultdict(list)
    for (product_id, key), candidates in grouped.items():
        by_company: dict[str, Mapping[str, object]] = {}
        for row, company_id in sorted(candidates, key=lambda item: _record_key(item[0])):
            by_company.setdefault(company_id, row)
        if len(by_company) < min_sellers:
            exclusions["insufficient_independent_sellers"] += len(candidates)
            continue
        cards = tuple(
            _card(by_company[company_id], company_id, currency)
            for company_id in sorted(by_company)
        )
        first_product = _mapping(candidates[0][0].get("product"))
        queries = sorted(
            {
                str(_mapping(row.get("source")).get("query"))
                for row, _ in candidates
                if _mapping(row.get("source")).get("query")
            }
        )
        by_product[product_id].append(
            SellerDeck(
                deck_id=f"{product_id}::{key}",
                product_id=product_id,
                title=(
                    first_product.get("title")
                    if isinstance(first_product.get("title"), str)
                    else None
                ),
                option_key=key,
                cards=cards,
                source_queries=tuple(queries),
            )
        )

    decks: list[SellerDeck] = []
    for product_id in sorted(by_product):
        candidates = by_product[product_id]
        selected = min(candidates, key=lambda deck: (-len(deck.cards), deck.option_key))
        decks.append(selected)
        for deck in candidates:
            if deck is not selected:
                exclusions["additional_option_deck"] += len(deck.cards)
    return DeckBuildResult(
        decks=tuple(decks),
        input_rows=len(materialized),
        eligible_rows=eligible_rows,
        exclusion_counts=dict(sorted(exclusions.items())),
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _option_pairs(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        return []
    pairs: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return []
        name = _normalized_text(item.get("name"))
        label = _normalized_text(item.get("label", item.get("value")))
        if not name or not label:
            return []
        pairs.append((name, label))
    return pairs


def _seller_domain(row: Mapping[str, object]) -> str:
    domain = _mapping(row.get("seller")).get("domain")
    if not isinstance(domain, str) or not domain:
        raise ValueError("eligible offer row has no seller domain")
    return domain


def _company_id(row: Mapping[str, object]) -> str:
    seller = _mapping(row.get("seller"))
    seller_id = seller.get("id")
    if isinstance(seller_id, str) and seller_id:
        return seller_id
    domain = _seller_domain(row)
    if domain.endswith(".myshopify.com"):
        return domain
    return base_domain(domain)


def _record_key(row: Mapping[str, object]) -> tuple[str, str]:
    variant_id = _mapping(row.get("variant")).get("id")
    return _seller_domain(row), str(variant_id or "")


def _card(row: Mapping[str, object], company_id: str, currency: str) -> SellerCard:
    variant = _mapping(row.get("variant"))
    price = _mapping(row.get("price"))
    amount = price.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ValueError("eligible offer row has no integer price")
    return SellerCard(
        seller_id=_seller_domain(row),
        company_id=company_id,
        variant_id=str(variant["id"]),
        price_minor=amount,
        currency=currency,
    )