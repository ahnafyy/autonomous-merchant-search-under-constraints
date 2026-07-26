from __future__ import annotations

import json
from pathlib import Path

import pytest
from example_study import (
    AutonomousShoppingOptimizer,
    adaptive_hard_budget_plan,
    break_even_api_call_weight,
    hard_budget_stopping_plan,
    hard_constraint_surface,
    optimal_stopping_plan,
    reservation_surface,
    simulate_policy,
    stopping_decision,
    weighted_loss,
)

from paperkit.pipeline import build

ROOT = Path(__file__).resolve().parents[1]


def test_rejected_offers_expire() -> None:
    outcome = simulate_policy(
        [
            {"available": True, "price": 6},
            {"available": True, "price": 2},
        ],
        "fixed_threshold",
        threshold=1,
    )

    assert outcome.purchased is False
    assert outcome.accepted_price is None
    assert outcome.queries == 2
    assert outcome.terminal_reason == "merchants_exhausted"
    assert weighted_loss(outcome, {"failure_penalty": 100}) == 100


def test_resource_aware_policy_accepts_before_budget_exhaustion() -> None:
    offers = [
        {"available": True, "price": 6, "api_calls": 1},
        {"available": True, "price": 2, "api_calls": 1},
    ]

    aware = simulate_policy(
        offers,
        "resource_aware_threshold",
        threshold=2,
        budget={"api_calls": 1},
    )
    fixed = simulate_policy(
        offers,
        "fixed_threshold",
        threshold=2,
        budget={"api_calls": 1},
    )

    assert aware.purchased is True
    assert aware.accepted_price == 6
    assert aware.accepted_index == 0
    assert fixed.purchased is False
    assert fixed.terminal_reason == "resource_exhausted"


def test_backward_induction_produces_actionable_reservation_prices() -> None:
    merchants = [
        {
            "price_weights": [
                {"price": 70, "weight": 1},
                {"price": 100, "weight": 2},
                {"price": 140, "weight": 1},
            ],
            "unavailable_weight": 1,
            "api_calls": 1,
        },
        {
            "price_weights": [
                {"price": 60, "weight": 1},
                {"price": 90, "weight": 2},
                {"price": 130, "weight": 1},
            ],
            "unavailable_weight": 1,
            "api_calls": 1,
        },
        {
            "price_weights": [
                {"price": 50, "weight": 1},
                {"price": 80, "weight": 2},
                {"price": 120, "weight": 1},
            ],
            "unavailable_weight": 1,
            "api_calls": 1,
        },
    ]

    free = optimal_stopping_plan(merchants, {"api_calls": 0}, failure_penalty=180)
    costly = optimal_stopping_plan(merchants, {"api_calls": 20}, failure_penalty=180)

    assert free["stages"][0]["reservation_price"] == {
        "numerator": 444,
        "denominator": 5,
        "value": 88.8,
    }
    assert costly["stages"][0]["reservation_price"] == {
        "numerator": 584,
        "denominator": 5,
        "value": 116.8,
    }
    assert free["stages"][0]["stop_percentile"]["value"] == 0.25
    assert costly["stages"][0]["stop_percentile"]["value"] == 0.75
    assert stopping_decision(free, 0, 110)["action"] == "continue"
    assert stopping_decision(costly, 0, 110)["action"] == "buy"

    surface = reservation_surface(
        merchants,
        base_resource_weights={},
        api_call_weights=[0, 20],
        failure_penalty=180,
        observed_price=110,
    )
    assert [row["action"] for row in surface] == ["continue", "buy"]
    assert surface[0]["net_value_of_continuing"]["value"] == 21.2
    assert surface[1]["net_value_of_continuing"]["value"] == -6.8
    assert surface[1]["next_query_cost"] == {
        "numerator": 20,
        "denominator": 1,
        "value": 20.0,
    }
    assert surface[1]["next_query_cost_components"]["api_calls"] == {
        "numerator": 20,
        "denominator": 1,
        "value": 20.0,
    }
    break_even = break_even_api_call_weight(
        merchants,
        base_resource_weights={},
        failure_penalty=180,
        observed_price=110,
        lower_weight=0,
        upper_weight=20,
    )
    assert break_even["critical_api_call_weight"] == {
        "numerator": 106,
        "denominator": 7,
        "value": 106 / 7,
    }


def test_hard_budget_state_changes_the_stopping_decision() -> None:
    merchants = [
        {
            "price_weights": [{"price": 100, "weight": 1}],
            "unavailable_weight": 0,
            "api_calls": 1,
        },
        {
            "price_weights": [{"price": 60, "weight": 1}],
            "unavailable_weight": 0,
            "api_calls": 1,
        },
    ]

    one_call = hard_budget_stopping_plan(
        merchants, {"api_calls": 1}, max_purchase_price=150, failure_penalty=180
    )
    two_calls = hard_budget_stopping_plan(
        merchants, {"api_calls": 2}, max_purchase_price=150, failure_penalty=180
    )

    assert one_call["states"][0]["reservation_price"]["value"] == 150.0
    assert two_calls["states"][0]["reservation_price"]["value"] == 60.0
    assert one_call["states"][0]["reservation_price"]["value"] >= 100
    assert two_calls["states"][0]["reservation_price"]["value"] < 100

    surface = hard_constraint_surface(
        merchants,
        scenarios=[
            {
                "id": "price-capped",
                "budget": {"api_calls": 1},
                "max_purchase_price": 90,
            }
        ],
        failure_penalty=180,
        observed_price=100,
    )
    assert surface[0]["action"] == "reject_without_feasible_query"
    assert surface[0]["reservation_price"]["value"] == 90.0


def test_adaptive_routing_uses_resource_identity_at_equal_depth() -> None:
    merchants = [
        {"price_weights": [{"price": 100, "weight": 1}], "time": 1, "tokens": 1},
        {"price_weights": [{"price": 50, "weight": 1}], "time": 5, "tokens": 1},
        {"price_weights": [{"price": 60, "weight": 1}], "time": 1, "tokens": 5},
    ]
    common = {"api_calls": 2, "api_cost": 0}

    time_tight = adaptive_hard_budget_plan(
        merchants,
        {**common, "time": 2, "tokens": 10},
        max_purchase_price=150,
        failure_penalty=180,
    )
    token_tight = adaptive_hard_budget_plan(
        merchants,
        {**common, "time": 10, "tokens": 2},
        max_purchase_price=150,
        failure_penalty=180,
    )

    assert time_tight["feasible_next_merchants"] == [2]
    assert time_tight["next_merchant_index"] == 2
    assert token_tight["feasible_next_merchants"] == [1]
    assert token_tight["next_merchant_index"] == 1


def test_agent_middleware_routes_accounts_and_stops() -> None:
    middleware = AutonomousShoppingOptimizer(
        [
            {"price_weights": [{"price": 120, "weight": 1}], "time": 2, "tokens": 4},
            {"price_weights": [{"price": 70, "weight": 1}], "time": 1, "tokens": 2},
        ],
        {"time": 3, "tokens": 6, "api_calls": 2, "api_cost": 0},
        max_purchase_price=100,
        failure_penalty=180,
    )

    permit = middleware.next_query_permit()
    assert permit is not None
    assert permit.as_dict() == {
        "merchant_index": 0,
        "timeout": 2,
        "max_tokens": 4,
        "max_api_calls": 1,
        "max_api_spend": 0,
    }
    unavailable = middleware.observe(0, None)
    assert unavailable.action == "continue"
    assert unavailable.next_merchant_index == 1
    decision = middleware.observe(1, 70)

    assert decision.action == "buy"
    assert decision.next_merchant_index is None
    assert decision.remaining_budget == {
        "time": 0,
        "tokens": 0,
        "api_calls": 0,
        "api_cost": 0,
    }
    with pytest.raises(RuntimeError):
        middleware.observe(1, 70)


def test_public_optimizer_import_and_compatibility_alias() -> None:
    from autonomous_shopping import ShoppingAgentMiddleware
    from autonomous_shopping_optimizer import (
        AutonomousShoppingOptimizer as PublicOptimizer,
    )

    assert PublicOptimizer is AutonomousShoppingOptimizer
    assert ShoppingAgentMiddleware is AutonomousShoppingOptimizer


def test_python_package_matches_generated_conformance(tmp_path: Path) -> None:
    artifacts = build(ROOT, tmp_path / "artifacts")
    vectors = json.loads(
        (artifacts / "conformance" / "merchant-search.json").read_text(encoding="utf-8")
    )

    for vector in vectors["cases"]:
        result = simulate_policy(**vector["input"])
        assert result.as_dict() == vector["expected"]
    for vector in vectors["errors"]:
        with pytest.raises(ValueError):
            simulate_policy(**vector["input"])