from __future__ import annotations

from fractions import Fraction

import pytest
from autonomous_shopping_optimizer.closed_form import (
    acceptance_fraction,
    affordable_queries,
    closed_form_reservation_price,
    secretary_sample_size,
    verify_closed_form_against_solver,
)
from autonomous_shopping_optimizer.permits import ResourceVector


def test_acceptance_fraction_matches_published_cayley_moser_values() -> None:
    """Under mu = 1 - u this is the classical recursion mu(n) = (1 + mu(n-1)^2)/2."""
    assert acceptance_fraction(0) == Fraction(1)
    assert acceptance_fraction(1) == Fraction(1, 2)
    assert acceptance_fraction(2) == Fraction(3, 8)
    assert acceptance_fraction(3) == Fraction(39, 128)


def test_acceptance_fraction_equals_the_mirrored_recursion() -> None:
    mu = Fraction(0)
    for k in range(1, 12):
        mu = (1 + mu * mu) / 2
        assert acceptance_fraction(k) == 1 - mu


def test_acceptance_fraction_is_strictly_decreasing() -> None:
    values = [acceptance_fraction(k) for k in range(12)]
    assert all(later < earlier for earlier, later in zip(values, values[1:], strict=False))


def test_budget_collapses_to_the_binding_resource() -> None:
    budget = ResourceVector(time=30, tokens=8000, api_calls=6, api_cost=12)
    per_query = ResourceVector(time=4, tokens=900, api_calls=1, api_cost=2)

    # time allows 7 and tokens 8, but calls and spend allow only 6.
    assert affordable_queries(budget, per_query) == 6


def test_unconsumed_resources_do_not_constrain_the_horizon() -> None:
    budget = ResourceVector(time=10, tokens=0, api_calls=3, api_cost=0)
    per_query = ResourceVector(time=2, tokens=0, api_calls=1, api_cost=0)

    assert affordable_queries(budget, per_query) == 3


def test_exhausted_budget_allows_no_further_queries() -> None:
    assert affordable_queries(
        ResourceVector(api_calls=0), ResourceVector(api_calls=1)
    ) == 0


def test_a_free_query_is_rejected() -> None:
    with pytest.raises(ValueError):
        affordable_queries(ResourceVector(api_calls=5), ResourceVector())


def test_threshold_rises_as_the_budget_drains() -> None:
    """With nothing reachable left the agent should accept rather than fail."""
    thresholds = [closed_form_reservation_price(8_000, 12_000, k) for k in range(6)]

    assert thresholds[0] == 12_000
    assert all(
        later < earlier
        for earlier, later in zip(thresholds, thresholds[1:], strict=False)
    )


def test_threshold_stays_inside_the_price_range() -> None:
    for k in range(10):
        value = closed_form_reservation_price(8_000, 12_000, k)
        assert 8_000 <= value <= 12_000


def test_flat_prices_make_the_threshold_degenerate() -> None:
    assert closed_form_reservation_price(9_900, 9_900, 5) == 9_900


def test_closed_form_agrees_with_the_exact_solver() -> None:
    report = verify_closed_form_against_solver()

    assert report["within_tolerance"]
    assert report["max_relative_error"] <= report["tolerance"]


def test_secretary_sample_size_follows_n_over_e() -> None:
    assert secretary_sample_size(10) == 4
    assert secretary_sample_size(100) == 37
    assert secretary_sample_size(1) == 1
