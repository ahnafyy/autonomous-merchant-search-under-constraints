"""Independent check that the stopping solver is actually optimal.

The dynamic program in `analysis` claims to return the minimum expected purchase
loss. On instances small enough to enumerate, every deterministic policy is scored
by brute force and compared against the solver. A mismatch means the recurrence is
wrong, not that the instance is unusual.

A deterministic policy here is a decision for each (stage, observed price) pair:
accept the offer or keep searching. That is exactly the strategy space the solver
optimizes over, so agreement is a meaningful check rather than a tautology.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import Any

from autonomous_shopping_optimizer.analysis import (
    RESOURCE_FIELDS,
    hard_budget_stopping_plan,
)


def _forecast(prices_and_weights: list[tuple[int, int]], unavailable: int = 0) -> dict[str, Any]:
    return {
        "price_weights": [
            {"price": price, "weight": weight} for price, weight in prices_and_weights
        ],
        "unavailable_weight": unavailable,
        "api_calls": 1,
    }


def enumerate_optimal_loss(
    forecasts: list[dict[str, Any]],
    *,
    price_cap: int,
    failure_penalty: int,
) -> Fraction:
    """Minimum expected purchase loss over all deterministic accept/continue rules."""
    stages = []
    for forecast in forecasts:
        outcomes = [
            (int(item["price"]), int(item["weight"]))
            for item in forecast["price_weights"]
        ]
        stages.append((outcomes, int(forecast.get("unavailable_weight", 0))))

    # One accept/continue bit per (stage, price) pair.
    decision_space = [
        list(product([False, True], repeat=len(outcomes))) for outcomes, _ in stages
    ]

    best: Fraction | None = None
    for policy in product(*decision_space):
        value = _policy_loss(stages, policy, price_cap, Fraction(failure_penalty))
        if best is None or value < best:
            best = value
    assert best is not None
    return best


def _policy_loss(
    stages: list[tuple[list[tuple[int, int]], int]],
    policy: tuple[tuple[bool, ...], ...],
    price_cap: int,
    penalty: Fraction,
) -> Fraction:
    def value(stage: int) -> Fraction:
        if stage == len(stages):
            return penalty
        outcomes, unavailable = stages[stage]
        continuation = value(stage + 1)
        total_weight = unavailable + sum(weight for _, weight in outcomes)
        expected = Fraction(unavailable) * continuation
        for (price, weight), accept in zip(outcomes, policy[stage], strict=True):
            # An offer above the hard price cap can never be bought.
            takes = accept and price <= price_cap
            expected += Fraction(weight) * (Fraction(price) if takes else continuation)
        return expected / total_weight

    return value(0)


def solver_agreement_cases() -> list[dict[str, Any]]:
    """Small instances spanning ties, dominated merchants, stockouts, and the cap."""
    return [
        {
            "id": "two-merchants-distinct",
            "forecasts": [_forecast([(100, 1)]), _forecast([(80, 1)])],
            "price_cap": 200,
            "failure_penalty": 300,
        },
        {
            "id": "two-merchants-stockout",
            "forecasts": [_forecast([(100, 1)]), _forecast([(80, 3)], unavailable=1)],
            "price_cap": 200,
            "failure_penalty": 300,
        },
        {
            "id": "three-merchants-spread",
            "forecasts": [
                _forecast([(90, 1), (130, 1)]),
                _forecast([(70, 2), (150, 1)], unavailable=1),
                _forecast([(110, 1)]),
            ],
            "price_cap": 200,
            "failure_penalty": 400,
        },
        {
            "id": "price-cap-binds",
            "forecasts": [
                _forecast([(120, 1), (60, 1)]),
                _forecast([(90, 1), (140, 1)]),
            ],
            "price_cap": 100,
            "failure_penalty": 250,
        },
        {
            "id": "penalty-dominates",
            "forecasts": [
                _forecast([(190, 1)], unavailable=2),
                _forecast([(180, 1)], unavailable=2),
            ],
            "price_cap": 200,
            "failure_penalty": 210,
        },
    ]


def verify_solver_against_enumeration() -> dict[str, Any]:
    """Compare the solver with brute force on every registered small instance."""
    rows: list[dict[str, Any]] = []
    for case in solver_agreement_cases():
        plan = hard_budget_stopping_plan(
            case["forecasts"],
            {field: len(case["forecasts"]) for field in RESOURCE_FIELDS},
            max_purchase_price=case["price_cap"],
            failure_penalty=case["failure_penalty"],
        )
        solver = Fraction(
            plan["expected_purchase_loss"]["numerator"],
            plan["expected_purchase_loss"]["denominator"],
        )
        enumerated = enumerate_optimal_loss(
            case["forecasts"],
            price_cap=case["price_cap"],
            failure_penalty=case["failure_penalty"],
        )
        rows.append(
            {
                "id": case["id"],
                "solver_expected_loss": float(solver),
                "enumerated_expected_loss": float(enumerated),
                "agrees": solver == enumerated,
            }
        )
    return {
        "cases": rows,
        "case_count": len(rows),
        "all_agree": all(row["agrees"] for row in rows),
    }
