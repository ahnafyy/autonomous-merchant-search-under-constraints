from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

from autonomous_shopping_optimizer.hidden_card_study import (
    clustered_paired_bootstrap,
    load_analysis_config,
    run_hidden_card_study,
    scenario_cost_minor,
    split_decks,
)
from autonomous_shopping_optimizer.replay import SellerCard, SellerDeck

ROOT = Path(__file__).resolve().parents[1]


def _decks(count: int = 10) -> list[SellerDeck]:
    decks: list[SellerDeck] = []
    for index in range(count):
        base = 100 + index * 3
        decks.append(
            SellerDeck(
                deck_id=f"product-{index}::featured",
                product_id=f"product-{index}",
                title=f"Product {index}",
                option_key="variant-title=featured",
                cards=(
                    SellerCard(f"a{index}.example", f"a{index}.example", "a", base, "USD"),
                    SellerCard(
                        f"b{index}.example", f"b{index}.example", "b", base - 10, "USD"
                    ),
                    SellerCard(
                        f"c{index}.example", f"c{index}.example", "c", base + 15, "USD"
                    ),
                    SellerCard(
                        f"d{index}.example", f"d{index}.example", "d", base - 20, "USD"
                    ),
                ),
            )
        )
    return decks


def _config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "random_seed": 7,
        "target_currency": "USD",
        "minimum_independent_sellers": 3,
        "maximum_reveals": 4,
        "calibration_fraction": 0.6,
        "permutations_per_product": 4,
        "cost_scenarios": [
            {
                "id": "short",
                "time_ms": 60_000,
                "time_value_minor_per_minute": 100,
                "input_tokens": 1_000,
                "input_cost_minor_per_million": 1_000,
                "output_tokens": 1_000,
                "output_cost_minor_per_million": 1_000,
                "shopping_api_calls": 1,
                "shopping_api_cost_minor_numerator_per_call": 10,
                "shopping_api_cost_minor_denominator_per_call": 1,
            },
            {
                "id": "long",
                "time_ms": 120_000,
                "time_value_minor_per_minute": 100,
                "input_tokens": 2_000,
                "input_cost_minor_per_million": 1_000,
                "output_tokens": 2_000,
                "output_cost_minor_per_million": 1_000,
                "shopping_api_calls": 2,
                "shopping_api_cost_minor_numerator_per_call": 10,
                "shopping_api_cost_minor_denominator_per_call": 1,
            },
        ],
        "threshold_basis_points": [8000, 9000, 10000],
        "relative_price_bin_basis_points": 500,
        "bootstrap_replicates": 200,
    }


def test_registered_analysis_config_is_valid() -> None:
    path = ROOT / "research" / "hidden-card-analysis.json"
    config = load_analysis_config(json.loads(path.read_text(encoding="utf-8")))

    assert config["random_seed"] == 20260723
    assert config["permutations_per_product"] == 32
    assert [scenario["id"] for scenario in config["cost_scenarios"]] == [
        "catalog_expansion",
        "agentic_review_2m",
        "long_horizon_research_5m",
    ]


def test_two_minute_scenario_prices_time_tokens_and_search() -> None:
    cost, components = scenario_cost_minor(_config()["cost_scenarios"][1])

    assert components == {
        "time": Fraction(200),
        "input_tokens": Fraction(2),
        "output_tokens": Fraction(2),
        "shopping_api": Fraction(20),
    }
    assert cost == Fraction(224)


def test_split_is_product_level_and_deterministic() -> None:
    first = split_decks(_decks(), seed=7, calibration_fraction=0.6)
    second = split_decks(_decks(), seed=7, calibration_fraction=0.6)

    assert first == second
    calibration, held_out = first
    assert len(calibration) == 6
    assert len(held_out) == 4
    assert {deck.product_id for deck in calibration}.isdisjoint(
        deck.product_id for deck in held_out
    )


def test_clustered_bootstrap_averages_permutations_within_product() -> None:
    treatment = {"p1": [Fraction(1), Fraction(3)], "p2": [Fraction(2), Fraction(4)]}
    control = {"p1": [Fraction(2), Fraction(4)], "p2": [Fraction(3), Fraction(5)]}

    result = clustered_paired_bootstrap(treatment, control, seed=1, replicates=200)

    assert result["mean_difference"] == -1.0
    assert result["product_clusters"] == 2
    assert result["permutations_are_independent"] is False


def test_study_tunes_on_calibration_and_reports_product_clustered_results() -> None:
    result = run_hidden_card_study(_decks(), _config())

    assert result["calibration_product_count"] == 6
    assert result["held_out_product_count"] == 4
    assert result["calibration_replay_deck_count"] == 6
    assert result["held_out_replay_deck_count"] == 4
    assert result["permutations_are_independent"] is False
    assert len(result["cost_results"]) == 2
    for cost_result in result["cost_results"]:
        assert cost_result["adaptive_vs_search_all"]["product_clusters"] == 4
        assert set(cost_result["arms"]) == {
            "adaptive_dynamic",
            "search_all",
        }
        assert all(
            arm["replay_rows"] == 16 for arm in cost_result["arms"].values()
        )
        assert all(
            arm["product_clusters"] == 4 for arm in cost_result["arms"].values()
        )