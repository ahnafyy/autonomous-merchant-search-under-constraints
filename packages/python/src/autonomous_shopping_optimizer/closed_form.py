"""A closed-form stopping rule you can compute without running the solver.

The dynamic program in `analysis` is exact but needs merchant-by-merchant
forecasts. In practice an engineer knows three things: roughly what the cheapest
and dearest offers look like, and how many more merchants the budget can afford.
That is enough.

Two steps.

**1. Collapse the budget to a query count.** Resources are consumed in fixed
amounts per query, so a four-dimensional budget reduces to a single integer: the
number of further queries you can afford. It is a minimum, not a sum -- whichever
resource runs out first is the one that binds.

**2. Accept below a fraction of the price range.** With `k` further queries
affordable, accept the offer in hand when

    price <= price_floor + u_k * (price_ceiling - price_floor)

where `u_0 = 1` and `u_{k+1} = u_k - u_k^2 / 2`.

The recurrence follows from the reservation-price identity `R_k = E[min(P, R_k-1)]`
for prices uniform on `[a, b]`: substituting `u = (R - a) / (b - a)` gives
`E[min(P, R)] = R - (R - a)^2 / (2(b - a))`, which is the map above.

This is not a new result. Under `mu_k = 1 - u_k` the map is exactly the classical
Cayley-Moser recursion `mu_n = E[max(X, mu_n-1)] = (1 + mu_n-1^2) / 2` for uniform
offers, a problem posed by Cayley in 1875 and solved by Moser in 1956; see Gilbert
and Mosteller (1966) and Ferguson's optimal-stopping notes, section 2.4. The
asymptotic `u_k ~ 2/k` is the leading term of a published expansion. What is
specific to this project is the instantiation: mapping a multi-resource query
budget onto the horizon parameter, and measuring the rule against alternatives on
merchant data.

Note that the recurrence carries no per-query cost term. Cost does not enter the
objective here; it enters only through `affordable_queries`, which converts the
budget into how many further queries remain. A model that charged inspection cost
in the objective would instead give `R_k = E[min(P, R_k-1)] + c`.

The classical secretary rule -- inspect `n/e` (about 37%) of the candidates, then
take the next record -- answers a different question: it maximizes the probability
of selecting the single best option using only ordinal comparisons and no price
knowledge. When price levels are known even roughly, the threshold rule above uses
strictly more information, and the optimal cutoff under a cardinal objective is not
`n/e` (Bearden 2006). `secretary_sample_size` is provided so the two can be
compared rather than conflated.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

from autonomous_shopping_optimizer.analysis import hard_budget_stopping_plan
from autonomous_shopping_optimizer.permits import RESOURCE_FIELDS, ResourceVector


def acceptance_fraction(affordable_queries: int) -> Fraction:
    """`u_k`: how far above the cheapest expected price to still accept."""
    if affordable_queries < 0:
        raise ValueError("affordable_queries must be non-negative")
    value = Fraction(1)
    for _ in range(affordable_queries):
        value = value - value * value / 2
    return value


def affordable_queries(
    remaining: ResourceVector, per_query: ResourceVector
) -> int:
    """How many further queries the remaining budget allows.

    The binding resource is whichever runs out first, so this is a minimum over
    resources. Resources the query does not consume place no limit. This is a
    modelling convention rather than a result, and it assumes deterministic
    per-query cost, no partial queries, no substitution between resources, and a
    budget that is never replenished.
    """
    limits = [
        getattr(remaining, field) // getattr(per_query, field)
        for field in RESOURCE_FIELDS
        if getattr(per_query, field) > 0
    ]
    if not limits:
        raise ValueError("a query must consume at least one resource")
    return max(0, min(limits))


def closed_form_reservation_price(
    price_floor: int, price_ceiling: int, affordable_queries: int
) -> Fraction:
    """Accept the offer in hand when its price is at or below this threshold."""
    if price_floor <= 0 or price_ceiling < price_floor:
        raise ValueError("require 0 < price_floor <= price_ceiling")
    fraction = acceptance_fraction(affordable_queries)
    return price_floor + fraction * (price_ceiling - price_floor)


def secretary_sample_size(candidate_count: int) -> int:
    """The classical `n/e` sample size, for comparison against the threshold rule."""
    if candidate_count < 1:
        raise ValueError("candidate_count must be positive")
    return max(1, round(candidate_count / math.e))


def conformance_vectors() -> dict[str, Any]:
    """Exact expectations the JavaScript port must reproduce."""
    acceptance = [
        {
            "input": {"affordable_queries": k},
            "expected": {
                "numerator": acceptance_fraction(k).numerator,
                "denominator": acceptance_fraction(k).denominator,
                "value": float(acceptance_fraction(k)),
            },
        }
        for k in range(9)
    ]
    horizon = [
        {
            "input": {
                "remaining": {"time": 30, "tokens": 8000, "api_calls": 6, "api_cost": 12},
                "per_query": {"time": 4, "tokens": 900, "api_calls": 1, "api_cost": 2},
            },
            "expected": 6,
        },
        {
            "input": {
                "remaining": {"time": 10, "tokens": 0, "api_calls": 3, "api_cost": 0},
                "per_query": {"time": 2, "tokens": 0, "api_calls": 1, "api_cost": 0},
            },
            "expected": 3,
        },
        {
            "input": {
                "remaining": {"time": 0, "tokens": 0, "api_calls": 0, "api_cost": 0},
                "per_query": {"time": 1, "tokens": 1, "api_calls": 1, "api_cost": 1},
            },
            "expected": 0,
        },
    ]
    thresholds = [
        {
            "input": {
                "price_floor": floor_,
                "price_ceiling": ceiling,
                "affordable_queries": k,
            },
            "expected": {
                "numerator": closed_form_reservation_price(floor_, ceiling, k).numerator,
                "denominator": closed_form_reservation_price(
                    floor_, ceiling, k
                ).denominator,
                "value": float(closed_form_reservation_price(floor_, ceiling, k)),
            },
        }
        for floor_, ceiling in ((8_000, 12_000), (9_900, 9_900), (1_000, 25_000))
        for k in range(5)
    ]
    return {
        "acceptance_fraction_cases": acceptance,
        "affordable_queries_cases": horizon,
        "reservation_threshold_cases": thresholds,
        "secretary_sample_size_cases": [
            {"input": {"candidate_count": n}, "expected": secretary_sample_size(n)}
            for n in (1, 2, 3, 5, 10, 20, 100)
        ],
        "tolerance": 1e-9,
    }


def verify_closed_form_against_solver(
    *,
    price_floor: int = 8_000,
    price_ceiling: int = 12_000,
    support_points: int = 800,
    max_affordable: int = 8,
    tolerance: float = 1e-3,
) -> dict[str, Any]:
    """Compare the closed form against the exact dynamic program.

    The solver takes a discrete price support while the closed form is derived for
    the continuous uniform law, so agreement is checked to a relative tolerance
    rather than exactly; the residual is price-grid discretization and shrinks as
    `support_points` grows.
    """
    span = price_ceiling - price_floor
    support = [
        price_floor + span * index // (support_points - 1)
        for index in range(support_points)
    ]
    cap = price_ceiling + 1

    rows: list[dict[str, Any]] = []
    for reachable in range(1, max_affordable + 1):
        forecasts: list[dict[str, Any]] = [
            {"price_weights": [{"price": price_floor, "weight": 1}], "api_calls": 1}
        ]
        forecasts.extend(
            {
                "price_weights": [{"price": price, "weight": 1} for price in support],
                "api_calls": 1,
            }
            for _ in range(reachable)
        )
        plan = hard_budget_stopping_plan(
            forecasts,
            {"api_calls": len(forecasts)},
            max_purchase_price=cap,
            failure_penalty=cap,
        )
        solver = plan["states"][0]["reservation_price"]["value"]
        closed = float(
            closed_form_reservation_price(price_floor, price_ceiling, reachable)
        )
        error = abs(solver - closed) / solver
        rows.append(
            {
                "affordable_queries": reachable,
                "acceptance_fraction": round(float(acceptance_fraction(reachable)), 6),
                "solver_reservation_price": round(solver, 4),
                "closed_form_reservation_price": round(closed, 4),
                "relative_error": round(error, 8),
            }
        )

    worst = max(row["relative_error"] for row in rows)
    return {
        "cases": rows,
        "case_count": len(rows),
        "support_points": support_points,
        "tolerance": tolerance,
        "max_relative_error": worst,
        "within_tolerance": worst <= tolerance,
    }
