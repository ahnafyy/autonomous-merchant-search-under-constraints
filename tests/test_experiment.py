from __future__ import annotations

import random
from fractions import Fraction

import pytest
from autonomous_shopping_optimizer.baselines import reservation_price, run_arm
from autonomous_shopping_optimizer.experiment import (
    derive_criteria,
    paired_bootstrap,
    simulate_episode,
)


def test_reservation_price_ignores_dearer_future_merchants() -> None:
    # Continuing is only worth it when something cheaper is reachable.
    assert reservation_price(100, [120]) == 120
    assert reservation_price(100, [80]) == 80


def test_reservation_price_rises_with_stockout_risk() -> None:
    patient = reservation_price(100, [80], Fraction(0))
    cautious = reservation_price(100, [80], Fraction(1, 2))
    reckless = reservation_price(100, [80], Fraction(9, 10))

    assert patient < cautious < reckless


def test_reservation_price_rejects_impossible_stockout_rate() -> None:
    with pytest.raises(ValueError):
        reservation_price(100, [80], Fraction(1))


def test_last_reachable_query_always_accepts() -> None:
    """A purchase failure is worse than any purchasable offer."""
    rng = random.Random(7)
    episode = simulate_episode(
        1,
        merchant_count=3,
        dispersion_ratio=Fraction(2),
        stockout_rate=Fraction(0),
        drift_rate=Fraction(0),
        base_price_minor=10_000,
        rng=rng,
    )
    result = run_arm(
        episode,
        "adaptive_stopping",
        max_queries=1,
        failure_penalty_minor=99_999,
        seed=1,
    )

    assert result.metrics.purchase_success
    assert result.query_count == 1


def test_never_accept_arm_is_scored_as_failure() -> None:
    rng = random.Random(3)
    episode = simulate_episode(
        2,
        merchant_count=2,
        dispersion_ratio=Fraction(2),
        stockout_rate=Fraction(0),
        drift_rate=Fraction(0),
        base_price_minor=5_000,
        rng=rng,
    )
    result = run_arm(
        episode, "never_accept", max_queries=2, failure_penalty_minor=12_345, seed=1
    )

    assert not result.metrics.purchase_success
    assert result.metrics.purchase_loss_minor == 12_345


def test_oracle_is_never_beaten_by_an_online_arm() -> None:
    rng = random.Random(11)
    episodes = [
        simulate_episode(
            index,
            merchant_count=4,
            dispersion_ratio=Fraction(2),
            stockout_rate=Fraction(1, 20),
            drift_rate=Fraction(1, 10),
            base_price_minor=10_000,
            rng=rng,
        )
        for index in range(40)
    ]
    for episode in episodes:
        penalty = 4 * episode.features.cheapest_calibration_price_minor
        oracle = run_arm(
            episode,
            "exhaustive_oracle",
            max_queries=4,
            failure_penalty_minor=penalty,
            seed=5,
        )
        online = run_arm(
            episode,
            "adaptive_stopping",
            max_queries=4,
            failure_penalty_minor=penalty,
            seed=5,
        )
        assert oracle.metrics.purchase_loss_minor <= online.metrics.purchase_loss_minor


def test_paired_bootstrap_detects_a_constant_shift() -> None:
    treatment = [100] * 50
    control = [150] * 50

    report = paired_bootstrap(treatment, control, seed=1, replicates=200)

    assert report["mean_difference_minor"] == -50.0
    assert report["ci_upper_minor"] < 0
    assert report["favors_treatment"]


def test_paired_bootstrap_reports_no_effect_for_identical_samples() -> None:
    report = paired_bootstrap([10] * 30, [10] * 30, seed=1, replicates=200)

    assert report["mean_difference_minor"] == 0.0
    assert not report["favors_treatment"]
    assert not report["significant"]


def test_paired_bootstrap_requires_matched_pairs() -> None:
    with pytest.raises(ValueError):
        paired_bootstrap([1, 2], [1], seed=1)


def test_derive_criteria_separates_wins_from_harm() -> None:
    cells = [
        {
            "merchant_count": 2,
            "dispersion_ratio": 1.0,
            "budget_fraction": 1.0,
            "relative_improvement": 0.0,
            "mean_difference_minor": 0.0,
            "ci_lower_minor": 0.0,
            "ci_upper_minor": 0.0,
            "adaptive_wins": False,
        },
        {
            "merchant_count": 8,
            "dispersion_ratio": 2.0,
            "budget_fraction": 1.0,
            "relative_improvement": 0.05,
            "mean_difference_minor": -50.0,
            "ci_lower_minor": -80.0,
            "ci_upper_minor": -20.0,
            "adaptive_wins": True,
        },
        {
            "merchant_count": 5,
            "dispersion_ratio": 1.1,
            "budget_fraction": 0.5,
            "relative_improvement": -0.02,
            "mean_difference_minor": 30.0,
            "ci_lower_minor": 10.0,
            "ci_upper_minor": 60.0,
            "adaptive_wins": False,
        },
    ]

    criteria = derive_criteria(cells)

    assert criteria["cells_favoring_adaptive"] == 1
    assert criteria["cells_favoring_fixed"] == 1
    assert criteria["cells_indistinguishable"] == 1
    assert criteria["no_advantage_rule"]["dispersion_ratio_at_or_below"] == 1.1
    verdicts = {row["verdict"] for row in criteria["decision_table"]}
    assert verdicts == {"use_adaptive", "use_fixed", "no_difference"}
