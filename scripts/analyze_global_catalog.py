#!/usr/bin/env python3
"""Build seller decks and run the registered hidden-card study."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from statistics import median

from autonomous_shopping_optimizer.catalog_decks import (
    build_seller_decks,
    load_catalog_offer_rows,
)
from autonomous_shopping_optimizer.hidden_card_study import run_hidden_card_study

MINIMUM_STUDY_PRODUCTS = 4


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_cost_rate_card(
    config: dict[str, object], analysis_config_path: Path
) -> dict[str, object]:
    rate_card_path = analysis_config_path.parent.parent / str(config["cost_rate_card"])
    rate_card = json.loads(rate_card_path.read_text(encoding="utf-8"))
    model_rates = {rate["id"]: rate for rate in rate_card["model_rates"]}
    shopping_api_rates = {rate["id"]: rate for rate in rate_card["shopping_api_rates"]}
    for scenario in config["cost_scenarios"]:
        model_rate = model_rates[scenario["model_rate_id"]]
        shopping_api_rate = shopping_api_rates[scenario["shopping_api_rate_id"]]
        if (
            scenario["input_cost_minor_per_million"]
            != model_rate["input_cost_minor_per_million"]
            or scenario["output_cost_minor_per_million"]
            != model_rate["output_cost_minor_per_million"]
            or scenario["shopping_api_cost_minor_numerator_per_call"]
            != shopping_api_rate["cost_minor_numerator_per_call"]
            or scenario["shopping_api_cost_minor_denominator_per_call"]
            != shopping_api_rate["cost_minor_denominator_per_call"]
        ):
            raise ValueError("cost scenario rates must match the registered cost rate card")
    return {
        "path": str(config["cost_rate_card"]),
        "as_of": rate_card["as_of"],
        "sha256": _sha256(rate_card_path),
    }


def analyze(collection_dir: Path, analysis_config_path: Path) -> dict[str, object]:
    collection_path = collection_dir / "collection.json"
    offers_path = collection_dir / "offers.jsonl"
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    if _sha256(offers_path) != collection.get("offers_sha256"):
        raise ValueError("offers.jsonl does not match its collection manifest hash")
    config = json.loads(analysis_config_path.read_text(encoding="utf-8"))
    cost_rate_card = _validate_cost_rate_card(config, analysis_config_path)
    product_identity = config.get("product_identity", {})
    merge_exact_model_titles = product_identity.get("strategy") == (
        "exact_normalized_model_title_or_catalog_product_option"
    )
    excluded_title_phrases = product_identity.get("excluded_title_phrases", [])
    deck_result = build_seller_decks(
        load_catalog_offer_rows(offers_path),
        currency=config["target_currency"],
        min_sellers=config["minimum_independent_sellers"],
        merge_exact_model_titles=merge_exact_model_titles,
        excluded_title_phrases=excluded_title_phrases,
    )
    enough_products = len(deck_result.decks) >= MINIMUM_STUDY_PRODUCTS
    study = run_hidden_card_study(deck_result.decks, config) if enough_products else None
    return {
        "schema_version": 1,
        "analysis": {
            "status": "analyzed" if enough_products else "insufficient_eligible_products",
            "random_seed": config["random_seed"],
            "minimum_required_product_decks": MINIMUM_STUDY_PRODUCTS,
            "cost_rate_card": cost_rate_card,
        },
        "collection": {
            "collection_id": collection["collection_id"],
            "collection_status": collection.get("collection_status", "complete"),
            "planned_query_count": collection.get("planned_query_count"),
            "completed_query_count": collection.get("completed_query_count"),
            "collection_manifest_sha256": _sha256(collection_path),
            "offers_sha256": collection["offers_sha256"],
            "offer_row_count": collection["offer_row_count"],
            "eligible_offer_row_count": collection["eligible_offer_row_count"],
        },
        "deck_build": {
            "product_identity": product_identity,
            "input_rows": deck_result.input_rows,
            "eligible_rows": deck_result.eligible_rows,
            "product_deck_count": len(deck_result.decks),
            "seller_card_count": sum(len(deck.cards) for deck in deck_result.decks),
            "seller_count_distribution": {
                str(count): sum(1 for deck in deck_result.decks if len(deck.cards) == count)
                for count in sorted({len(deck.cards) for deck in deck_result.decks})
            },
            "deck_audit": [
                {
                    "title": deck.title,
                    "seller_count": len(deck.cards),
                    "source_queries": list(deck.source_queries),
                    "price_minor": {
                        "min": min(card.price_minor for card in deck.cards),
                        "median": median(card.price_minor for card in deck.cards),
                        "max": max(card.price_minor for card in deck.cards),
                        "currency": config["target_currency"],
                    },
                }
                for deck in deck_result.decks
            ],
            "exclusion_counts": deck_result.exclusion_counts,
        },
                    "cost_rate_card": cost_rate_card,
        "study": study,
    }


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-dir", type=Path, required=True)
    parser.add_argument(
        "--analysis-config",
        type=Path,
        default=Path("research/hidden-card-analysis.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze(args.collection_dir, args.analysis_config)
    _write_atomic(args.output, result)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())