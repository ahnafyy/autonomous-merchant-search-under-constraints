from __future__ import annotations

from fractions import Fraction

from autonomous_shopping_optimizer.verification import (
    enumerate_optimal_loss,
    solver_agreement_cases,
    verify_solver_against_enumeration,
)


def test_solver_matches_exhaustive_enumeration_on_every_case() -> None:
    report = verify_solver_against_enumeration()

    assert report["case_count"] == len(solver_agreement_cases())
    assert report["all_agree"]


def test_enumeration_prefers_the_cheaper_reachable_merchant() -> None:
    forecasts = [
        {"price_weights": [{"price": 100, "weight": 1}], "api_calls": 1},
        {"price_weights": [{"price": 80, "weight": 1}], "api_calls": 1},
    ]

    value = enumerate_optimal_loss(forecasts, price_cap=200, failure_penalty=300)

    assert value == Fraction(80)


def test_enumeration_respects_the_hard_price_cap() -> None:
    """An offer above the cap cannot be bought, so the penalty is incurred instead."""
    forecasts = [{"price_weights": [{"price": 150, "weight": 1}], "api_calls": 1}]

    value = enumerate_optimal_loss(forecasts, price_cap=100, failure_penalty=200)

    assert value == Fraction(200)
