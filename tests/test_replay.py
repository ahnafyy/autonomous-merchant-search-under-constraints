from __future__ import annotations

from fractions import Fraction

import pytest
from autonomous_shopping_optimizer.domain import Offer, Price
from autonomous_shopping_optimizer.permits import ResourceVector
from autonomous_shopping_optimizer.replay import (
    FrozenMerchantObservation,
    FrozenPanel,
    decompose_purchase_loss,
    exhaustive_oracle,
    score_selection,
)


def _panel() -> FrozenPanel:
    return FrozenPanel(
        panel_id="panel-1",
        product_id="sku-1",
        observations=(
            FrozenMerchantObservation(
                "merchant-a",
                Offer("sku-1", "merchant-a", True, Price(10_000, "USD")),
                ResourceVector(time=10, api_calls=1),
            ),
            FrozenMerchantObservation(
                "merchant-b",
                Offer("sku-1", "merchant-b", True, Price(8_000, "USD")),
                ResourceVector(time=20, api_calls=1),
            ),
            FrozenMerchantObservation(
                "merchant-c",
                Offer("sku-1", "merchant-c", False, None),
                ResourceVector(time=5, api_calls=1),
            ),
        ),
    )


def test_exhaustive_oracle_selects_cheapest_available_offer() -> None:
    oracle = exhaustive_oracle(_panel())

    assert oracle is not None
    assert oracle.merchant_id == "merchant-b"


def test_score_selection_reports_exact_regret_and_savings() -> None:
    metrics = score_selection(
        _panel(),
        selected_merchant_id="merchant-b",
        initial_merchant_id="merchant-a",
        failure_penalty_minor=20_000,
        query_count=2,
    )

    assert metrics.purchase_success is True
    assert metrics.exact_oracle_price_hit is True
    assert metrics.price_regret_minor == 0
    assert metrics.savings_captured == Fraction(1, 1)
    assert metrics.savings_denominator_defined is True


def test_score_selection_separates_failure_from_undefined_savings() -> None:
    metrics = score_selection(
        _panel(),
        selected_merchant_id=None,
        initial_merchant_id="merchant-a",
        failure_penalty_minor=20_000,
        query_count=1,
    )

    assert metrics.purchase_success is False
    assert metrics.purchase_loss_minor == 20_000
    assert metrics.exact_oracle_price_hit is False
    assert metrics.price_regret_minor is None
    assert metrics.savings_captured is None
    assert metrics.savings_denominator_defined is False


def test_loss_decomposition_distinguishes_budget_and_policy_error() -> None:
    constrained = score_selection(
        _panel(),
        selected_merchant_id=None,
        initial_merchant_id="merchant-a",
        failure_penalty_minor=20_000,
        query_count=1,
    )
    nonbinding = score_selection(
        _panel(),
        selected_merchant_id="merchant-a",
        initial_merchant_id="merchant-a",
        failure_penalty_minor=20_000,
        query_count=3,
    )

    decomposition = decompose_purchase_loss(constrained, nonbinding)

    assert decomposition.budget_effect_minor == 10_000
    assert decomposition.policy_error_minor == 2_000
    assert decomposition.total_regret_minor == 12_000


def test_landed_oracle_requires_complete_price_components() -> None:
    with pytest.raises(ValueError, match="requires both shipping and tax"):
        exhaustive_oracle(_panel(), use_landed_price=True)


def test_panel_rejects_duplicate_merchants() -> None:
    observation = FrozenMerchantObservation(
        "merchant-a",
        Offer("sku-1", "merchant-a", True, Price(10_000, "USD")),
        ResourceVector(api_calls=1),
    )

    with pytest.raises(ValueError, match="must be unique"):
        FrozenPanel("panel-1", "sku-1", (observation, observation))