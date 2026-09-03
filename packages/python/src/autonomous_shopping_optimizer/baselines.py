"""Deployable stopping policies replayed against frozen merchant panels.

Every arm sees exactly the same panel, the same merchant order seed, and the same
hard budget. Only the stopping and routing decisions differ, so a paired comparison
across arms isolates the policy rather than the episode.

All arms operate under no-recall semantics: an available offer is accepted at the
moment it is seen or lost for the rest of the episode. The exhaustive oracle is the
only arm allowed to inspect unqueried merchants, and it is scored offline.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction

from autonomous_shopping_optimizer.analysis import hard_budget_stopping_plan
from autonomous_shopping_optimizer.closed_form import (
    closed_form_reservation_price,
    secretary_sample_size,
)
from autonomous_shopping_optimizer.panels import Episode
from autonomous_shopping_optimizer.permits import ResourceVector
from autonomous_shopping_optimizer.replay import (
    FrozenPanel,
    OutcomeMetrics,
    exhaustive_oracle,
    score_selection,
)

ARMS = (
    "accept_first",
    "fixed_depth",
    "fixed_threshold",
    "equal_split",
    "myopic_voi",
    "secretary_37",
    "closed_form",
    "adaptive_stopping",
    "exhaustive_oracle",
    "never_accept",
)


@dataclass(frozen=True)
class ArmResult:
    arm: str
    selected_merchant_id: str | None
    query_count: int
    metrics: OutcomeMetrics


def merchant_order(panel: FrozenPanel, seed: int) -> tuple[str, ...]:
    """Deterministic per-episode arrival order shared by every arm."""
    ids = sorted(observation.merchant_id for observation in panel.observations)
    rng = random.Random(f"{panel.panel_id}:{seed}")
    rng.shuffle(ids)
    return tuple(ids)


def _price_of(panel: FrozenPanel, merchant_id: str) -> int | None:
    offer = panel.observation_for(merchant_id).offer
    if offer is None or not offer.available or offer.price is None:
        return None
    return offer.price.item_minor


def run_arm(
    episode: Episode,
    arm: str,
    *,
    max_queries: int,
    failure_penalty_minor: int,
    seed: int,
    fixed_depth: int = 2,
    price_threshold_minor: int | None = None,
    stockout_rate: Fraction = Fraction(0),
) -> ArmResult:
    if arm not in ARMS:
        raise ValueError(f"unsupported arm: {arm}")
    panel = episode.panel
    order = merchant_order(panel, seed)
    budget = min(max_queries, len(order))

    if arm == "exhaustive_oracle":
        oracle = exhaustive_oracle(panel)
        return _score(
            episode,
            arm,
            oracle.merchant_id if oracle is not None else None,
            len(order),
            order,
            failure_penalty_minor,
        )
    if arm == "never_accept":
        return _score(episode, arm, None, 0, order, failure_penalty_minor)

    calibration = dict(episode.calibration_prices)
    selected: str | None = None
    queries = 0

    for position, merchant_id in enumerate(order):
        if queries >= budget:
            break
        queries += 1
        price = _price_of(panel, merchant_id)
        if price is None:
            continue

        remaining_after = budget - queries
        if _accepts(
            arm,
            price=price,
            position=position,
            seen_prices=[
                p for p in (_price_of(panel, m) for m in order[:position]) if p is not None
            ],
            remaining_after=remaining_after,
            fixed_depth=fixed_depth,
            price_threshold_minor=price_threshold_minor,
            future_calibration=[
                calibration[m] for m in order[position + 1 :] if m in calibration
            ][:remaining_after],
            stockout_rate=stockout_rate,
            budget=budget,
            all_calibration=[calibration[m] for m in order if m in calibration],
        ):
            selected = merchant_id
            break

    return _score(episode, arm, selected, queries, order, failure_penalty_minor)


def _accepts(
    arm: str,
    *,
    price: int,
    position: int,
    seen_prices: list[int],
    remaining_after: int,
    fixed_depth: int,
    price_threshold_minor: int | None,
    future_calibration: list[int],
    stockout_rate: Fraction,
    budget: int,
    all_calibration: list[int],
) -> bool:
    if remaining_after <= 0:
        # Last reachable query: accepting beats a certain purchase failure.
        return True
    if arm == "accept_first":
        return True
    if arm == "fixed_depth":
        # Classic explore-then-accept: learn from the first `fixed_depth` merchants,
        # then take the first offer better than everything seen during exploration.
        if position < fixed_depth:
            return False
        return not seen_prices or price < min(seen_prices)
    if arm == "fixed_threshold":
        if price_threshold_minor is None:
            raise ValueError("fixed_threshold requires price_threshold_minor")
        return price <= price_threshold_minor
    if arm == "equal_split":
        # Spend the query allowance evenly: stop once half the budget is consumed.
        return position + 1 >= max(1, (position + 1 + remaining_after) // 2)
    if arm == "myopic_voi":
        # One-step lookahead against the single cheapest reachable calibration price.
        if not future_calibration:
            return True
        return price <= min(future_calibration)
    if arm == "secretary_37":
        # Classical n/e rule: observe a sample, then take the next record low.
        sample = secretary_sample_size(budget)
        if position < sample:
            return False
        return not seen_prices or price < min(seen_prices)
    if arm == "closed_form":
        if not all_calibration:
            return True
        threshold = closed_form_reservation_price(
            min(all_calibration), max(all_calibration), remaining_after
        )
        return price <= threshold
    if arm == "adaptive_stopping":
        return price <= reservation_price(price, future_calibration, stockout_rate)
    raise ValueError(f"unsupported arm: {arm}")


def reservation_price(
    observed_price: int,
    future_calibration: list[int],
    stockout_rate: Fraction = Fraction(0),
) -> Fraction:
    """Exact threshold for accepting the offer in hand.

    Delegates to the canonical finite-horizon recurrence in `analysis`, forecasting
    each reachable merchant as a point mass at its last observed price with an
    availability weight taken from the measured stockout rate.
    """
    if not future_calibration:
        return Fraction(observed_price)
    if not 0 <= stockout_rate < 1:
        raise ValueError("stockout_rate must be in [0, 1)")
    unavailable = stockout_rate.numerator
    available = stockout_rate.denominator - unavailable
    forecasts: list[dict[str, object]] = [
        {
            "price_weights": [{"price": observed_price, "weight": 1}],
            "unavailable_weight": 0,
            "api_calls": 1,
        }
    ]
    forecasts.extend(
        {
            "price_weights": [{"price": price, "weight": available}],
            "unavailable_weight": unavailable,
            "api_calls": 1,
        }
        for price in future_calibration
    )
    cap = max([observed_price, *future_calibration]) + 1
    plan = hard_budget_stopping_plan(
        forecasts,
        {"api_calls": len(forecasts)},
        max_purchase_price=cap,
        failure_penalty=cap,
    )
    reservation = plan["states"][0]["reservation_price"]
    return Fraction(reservation["numerator"], reservation["denominator"])


def _score(
    episode: Episode,
    arm: str,
    selected: str | None,
    queries: int,
    order: tuple[str, ...],
    failure_penalty_minor: int,
) -> ArmResult:
    metrics = score_selection(
        episode.panel,
        selected_merchant_id=selected,
        initial_merchant_id=order[0],
        failure_penalty_minor=failure_penalty_minor,
        query_count=queries,
        hard_budget_violation=False,
    )
    return ArmResult(
        arm=arm, selected_merchant_id=selected, query_count=queries, metrics=metrics
    )


def query_cost_vector() -> ResourceVector:
    """Uniform per-query cost used across all replayed episodes."""
    return ResourceVector(time=1, tokens=1, api_calls=1, api_cost=1)
