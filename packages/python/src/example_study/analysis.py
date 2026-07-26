from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from fractions import Fraction
from functools import cache
from itertools import pairwise
from typing import Any

RESOURCE_FIELDS = ("time", "tokens", "api_calls", "api_cost")
POLICIES = {"accept_first", "fixed_threshold", "resource_aware_threshold"}


@dataclass(frozen=True)
class ResourceUsage:
    time: int = 0
    tokens: int = 0
    api_calls: int = 0
    api_cost: int = 0

    def add(self, other: ResourceUsage) -> ResourceUsage:
        return ResourceUsage(
            time=self.time + other.time,
            tokens=self.tokens + other.tokens,
            api_calls=self.api_calls + other.api_calls,
            api_cost=self.api_cost + other.api_cost,
        )


@dataclass(frozen=True)
class ResourceBudget:
    time: int | None = None
    tokens: int | None = None
    api_calls: int | None = None
    api_cost: int | None = None


@dataclass(frozen=True)
class Offer:
    available: bool
    price: int | None
    resources: ResourceUsage


@dataclass(frozen=True)
class SearchOutcome:
    purchased: bool
    accepted_price: int | None
    accepted_index: int | None
    queries: int
    resources: ResourceUsage
    terminal_reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MerchantForecast:
    price_weights: tuple[tuple[int, int], ...]
    unavailable_weight: int
    resources: ResourceUsage

    @property
    def total_weight(self) -> int:
        return self.unavailable_weight + sum(weight for _, weight in self.price_weights)


def optimal_stopping_plan(
    merchants: Sequence[Mapping[str, object]],
    resource_weights: Mapping[str, object],
    failure_penalty: int,
) -> dict[str, Any]:
    """Compute exact finite-horizon reservation prices by backward induction.

    Prices, the failure penalty, and scalarized query costs share one monetary unit.
    Resource weights may be integers, Fractions, or ``{numerator, denominator}`` mappings.
    """
    parsed_merchants = tuple(_parse_forecast(value) for value in merchants)
    if not parsed_merchants:
        raise ValueError("at least one merchant forecast is required")
    penalty = Fraction(_non_negative_integer(failure_penalty, "failure_penalty"))
    weights = {
        field: _non_negative_fraction(resource_weights.get(field, 0), f"{field} weight")
        for field in RESOURCE_FIELDS
    }

    continuation = penalty
    reversed_stages: list[dict[str, Any]] = []
    for index in range(len(parsed_merchants) - 1, -1, -1):
        merchant = parsed_merchants[index]
        query_components = {
            field: weights[field] * getattr(merchant.resources, field)
            for field in RESOURCE_FIELDS
        }
        query_cost = sum(query_components.values(), start=Fraction())
        available_weight = sum(weight for _, weight in merchant.price_weights)
        stop_weight = sum(
            weight for price, weight in merchant.price_weights if price <= continuation
        )
        expected_after_query = Fraction(merchant.unavailable_weight) * continuation
        expected_after_query += sum(
            Fraction(weight) * min(Fraction(price), continuation)
            for price, weight in merchant.price_weights
        )
        expected_after_query /= merchant.total_weight
        value_before_query = query_cost + expected_after_query
        reversed_stages.append(
            {
                "merchant_index": index,
                "reservation_price": _fraction_dict(continuation),
                "stop_percentile": _fraction_dict(Fraction(stop_weight, available_weight)),
                "query_cost": _fraction_dict(query_cost),
                "query_cost_components": {
                    field: _fraction_dict(value) for field, value in query_components.items()
                },
                "value_before_query": _fraction_dict(value_before_query),
                "availability_probability": _fraction_dict(
                    Fraction(available_weight, merchant.total_weight)
                ),
            }
        )
        continuation = value_before_query

    stages = list(reversed(reversed_stages))
    return {
        "expected_loss": _fraction_dict(continuation),
        "failure_penalty": failure_penalty,
        "merchant_count": len(parsed_merchants),
        "rule": "buy_if_price_lte_reservation_price",
        "stages": stages,
    }


def hard_budget_stopping_plan(
    merchants: Sequence[Mapping[str, object]],
    budget: Mapping[str, object],
    max_purchase_price: int,
    failure_penalty: int,
) -> dict[str, Any]:
    """Compute exact reservation prices with remaining resources in the Bellman state."""
    parsed_merchants = tuple(_parse_forecast(value) for value in merchants)
    if not parsed_merchants:
        raise ValueError("at least one merchant forecast is required")
    price_cap = Fraction(_positive_integer(max_purchase_price, "max_purchase_price"))
    penalty = Fraction(_non_negative_integer(failure_penalty, "failure_penalty"))
    initial_budget = tuple(
        _non_negative_integer(budget.get(field, 0), f"{field} budget")
        for field in RESOURCE_FIELDS
    )

    @cache
    def value_before_query(index: int, remaining: tuple[int, ...]) -> Fraction:
        if index == len(parsed_merchants):
            return penalty
        merchant = parsed_merchants[index]
        usage = tuple(getattr(merchant.resources, field) for field in RESOURCE_FIELDS)
        if any(required > available for required, available in zip(usage, remaining, strict=True)):
            return penalty
        after_query = tuple(
            available - required for required, available in zip(usage, remaining, strict=True)
        )
        continuation = value_before_query(index + 1, after_query)
        expected = Fraction(merchant.unavailable_weight) * continuation
        expected += sum(
            Fraction(weight)
            * (
                min(Fraction(price), continuation)
                if price <= price_cap
                else continuation
            )
            for price, weight in merchant.price_weights
        )
        return expected / merchant.total_weight

    states: list[dict[str, Any]] = []
    remaining = initial_budget
    for index, merchant in enumerate(parsed_merchants):
        usage = tuple(getattr(merchant.resources, field) for field in RESOURCE_FIELDS)
        feasible = all(
            required <= available
            for required, available in zip(usage, remaining, strict=True)
        )
        if not feasible:
            break
        after_query = tuple(
            available - required for required, available in zip(usage, remaining, strict=True)
        )
        continuation = value_before_query(index + 1, after_query)
        reservation = min(price_cap, continuation)
        states.append(
            {
                "merchant_index": index,
                "remaining_before_query": dict(zip(RESOURCE_FIELDS, remaining, strict=True)),
                "remaining_after_query": dict(zip(RESOURCE_FIELDS, after_query, strict=True)),
                "reservation_price": _fraction_dict(reservation),
                "continuation_value": _fraction_dict(continuation),
            }
        )
        remaining = after_query

    return {
        "expected_purchase_loss": _fraction_dict(value_before_query(0, initial_budget)),
        "failure_penalty": failure_penalty,
        "max_purchase_price": max_purchase_price,
        "merchant_count": len(parsed_merchants),
        "budget": dict(zip(RESOURCE_FIELDS, initial_budget, strict=True)),
        "rule": "buy_if_price_lte_reservation_price",
        "states": states,
    }


def adaptive_hard_budget_plan(
    merchants: Sequence[Mapping[str, object]],
    budget: Mapping[str, object],
    max_purchase_price: int,
    failure_penalty: int,
    observed_merchant_index: int = 0,
) -> dict[str, Any]:
    """Choose the next merchant and stopping threshold under hard resource budgets."""
    parsed_merchants = tuple(_parse_forecast(value) for value in merchants)
    if not parsed_merchants:
        raise ValueError("at least one merchant forecast is required")
    if not 0 <= observed_merchant_index < len(parsed_merchants):
        raise ValueError("observed_merchant_index is outside the merchant set")
    price_cap = Fraction(_positive_integer(max_purchase_price, "max_purchase_price"))
    penalty = Fraction(_non_negative_integer(failure_penalty, "failure_penalty"))
    initial_budget = tuple(
        _non_negative_integer(budget.get(field, 0), f"{field} budget")
        for field in RESOURCE_FIELDS
    )

    def usage(index: int) -> tuple[int, ...]:
        resources = parsed_merchants[index].resources
        return tuple(getattr(resources, field) for field in RESOURCE_FIELDS)

    def fits(index: int, remaining: tuple[int, ...]) -> bool:
        return all(
            required <= available
            for required, available in zip(usage(index), remaining, strict=True)
        )

    def subtract(index: int, remaining: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(
            available - required
            for required, available in zip(usage(index), remaining, strict=True)
        )

    @cache
    def solve(
        remaining_merchants: tuple[int, ...], remaining: tuple[int, ...]
    ) -> tuple[Fraction, int | None]:
        candidates: list[tuple[Fraction, int]] = []
        for index in remaining_merchants:
            if not fits(index, remaining):
                continue
            merchant = parsed_merchants[index]
            after_query = subtract(index, remaining)
            future = tuple(
                candidate for candidate in remaining_merchants if candidate != index
            )
            continuation, _ = solve(future, after_query)
            expected = Fraction(merchant.unavailable_weight) * continuation
            expected += sum(
                Fraction(weight)
                * (
                    min(Fraction(price), continuation)
                    if price <= price_cap
                    else continuation
                )
                for price, weight in merchant.price_weights
            )
            candidates.append((expected / merchant.total_weight, index))
        if not candidates:
            return penalty, None
        return min(candidates, key=lambda candidate: (candidate[0], candidate[1]))

    if not fits(observed_merchant_index, initial_budget):
        raise ValueError("budget cannot query the observed merchant")
    after_observation = subtract(observed_merchant_index, initial_budget)
    remaining_indices = tuple(
        index for index in range(len(parsed_merchants)) if index != observed_merchant_index
    )
    continuation, next_merchant = solve(remaining_indices, after_observation)
    feasible_next = tuple(
        index for index in remaining_indices if fits(index, after_observation)
    )
    expected_loss, first_merchant = solve(
        tuple(range(len(parsed_merchants))), initial_budget
    )
    return {
        "expected_purchase_loss": _fraction_dict(expected_loss),
        "first_merchant_index": first_merchant,
        "observed_merchant_index": observed_merchant_index,
        "next_merchant_index": next_merchant,
        "feasible_next_merchants": list(feasible_next),
        "remaining_after_observation": dict(
            zip(RESOURCE_FIELDS, after_observation, strict=True)
        ),
        "reservation_price": _fraction_dict(min(price_cap, continuation)),
        "continuation_value": _fraction_dict(continuation),
        "budget": dict(zip(RESOURCE_FIELDS, initial_budget, strict=True)),
        "max_purchase_price": max_purchase_price,
        "failure_penalty": failure_penalty,
        "rule": "buy_if_price_lte_reservation_else_query_best_feasible_merchant",
    }


def hard_constraint_surface(
    merchants: Sequence[Mapping[str, object]],
    scenarios: Sequence[Mapping[str, object]],
    failure_penalty: int,
    observed_price: int,
) -> list[dict[str, Any]]:
    """Evaluate one observed offer under declared hard-resource scenarios."""
    observed = _positive_integer(observed_price, "observed_price")
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError("scenario id must be a non-empty string")
        budget = scenario.get("budget")
        if not isinstance(budget, Mapping):
            raise ValueError("scenario budget must be a mapping")
        max_price = _positive_integer(
            scenario.get("max_purchase_price"), "max_purchase_price"
        )
        plan = adaptive_hard_budget_plan(
            merchants,
            budget,
            max_purchase_price=max_price,
            failure_penalty=failure_penalty,
        )
        reservation = plan["reservation_price"]
        if observed <= reservation["value"]:
            action = "buy"
        elif plan["next_merchant_index"] is not None:
            action = "continue"
        else:
            action = "reject_without_feasible_query"
        rows.append(
            {
                "id": scenario_id,
                "label": scenario.get("label", scenario_id),
                "budget": plan["budget"],
                "max_purchase_price": max_price,
                "observed_price": observed,
                "action": action,
                "reservation_price": reservation,
                "continuation_value": plan["continuation_value"],
                "remaining_after_observation": plan["remaining_after_observation"],
                "next_merchant_index": plan["next_merchant_index"],
                "feasible_next_merchants": plan["feasible_next_merchants"],
                "feasible_next_merchant_count": len(plan["feasible_next_merchants"]),
                "expected_purchase_loss": plan["expected_purchase_loss"],
            }
        )
    return rows


def stopping_decision(
    plan: Mapping[str, object], merchant_index: int, price: int
) -> dict[str, Any]:
    """Apply a generated reservation-price plan to one observed offer."""
    price = _positive_integer(price, "price")
    stages = plan.get("stages")
    if not isinstance(stages, list) or not 0 <= merchant_index < len(stages):
        raise ValueError("merchant_index is outside the stopping plan")
    stage = stages[merchant_index]
    if not isinstance(stage, dict):
        raise ValueError("invalid stopping plan stage")
    reservation = stage.get("reservation_price")
    if not isinstance(reservation, dict):
        raise ValueError("invalid reservation price")
    threshold = Fraction(
        _non_negative_integer(reservation.get("numerator"), "reservation numerator"),
        _positive_integer(reservation.get("denominator"), "reservation denominator"),
    )
    margin = Fraction(price) - threshold
    return {
        "action": "buy" if margin <= 0 else "continue",
        "observed_price": price,
        "reservation_price": _fraction_dict(threshold),
        "net_value_of_continuing": _fraction_dict(margin),
    }


def reservation_surface(
    merchants: Sequence[Mapping[str, object]],
    base_resource_weights: Mapping[str, object],
    api_call_weights: Sequence[int],
    failure_penalty: int,
    observed_price: int,
    merchant_index: int = 0,
) -> list[dict[str, Any]]:
    """Evaluate an observed offer over an exact API-call shadow-cost grid."""
    if not api_call_weights:
        raise ValueError("api_call_weights must not be empty")
    rows: list[dict[str, Any]] = []
    for api_call_weight in api_call_weights:
        parsed_weight = _non_negative_integer(api_call_weight, "api_call_weight")
        weights = dict(base_resource_weights)
        weights["api_calls"] = parsed_weight
        plan = optimal_stopping_plan(merchants, weights, failure_penalty)
        decision = stopping_decision(plan, merchant_index, observed_price)
        stage = plan["stages"][merchant_index]
        rows.append(
            {
                "api_call_weight": parsed_weight,
                "action": decision["action"],
                "reservation_price": decision["reservation_price"],
                "net_value_of_continuing": decision["net_value_of_continuing"],
                "stop_percentile": stage["stop_percentile"],
                "next_query_cost": plan["stages"][merchant_index + 1]["query_cost"],
                "next_query_cost_components": plan["stages"][merchant_index + 1][
                    "query_cost_components"
                ],
                "expected_loss_before_first_query": plan["expected_loss"],
            }
        )
    return rows


def break_even_api_call_weight(
    merchants: Sequence[Mapping[str, object]],
    base_resource_weights: Mapping[str, object],
    failure_penalty: int,
    observed_price: int,
    lower_weight: int,
    upper_weight: int,
    merchant_index: int = 0,
) -> dict[str, Any]:
    """Solve an exact affine Bellman segment where buy and continue have equal loss."""
    lower = Fraction(_non_negative_integer(lower_weight, "lower_weight"))
    upper = Fraction(_non_negative_integer(upper_weight, "upper_weight"))
    if lower >= upper:
        raise ValueError("lower_weight must be less than upper_weight")

    def reservation_at(api_weight: Fraction) -> Fraction:
        weights = dict(base_resource_weights)
        weights["api_calls"] = api_weight
        plan = optimal_stopping_plan(merchants, weights, failure_penalty)
        stage = plan["stages"][merchant_index]
        reservation = stage["reservation_price"]
        return Fraction(reservation["numerator"], reservation["denominator"])

    lower_reservation = reservation_at(lower)
    upper_reservation = reservation_at(upper)
    price = Fraction(_positive_integer(observed_price, "observed_price"))
    if not lower_reservation < price <= upper_reservation:
        raise ValueError("weight interval does not bracket a continue-to-buy switch")
    slope = (upper_reservation - lower_reservation) / (upper - lower)
    if slope <= 0:
        raise ValueError("reservation price must increase inside the bracket")
    critical = lower + (price - lower_reservation) / slope
    if reservation_at(critical) != price:
        raise ValueError("weight interval crosses a Bellman policy breakpoint")
    return {
        "critical_api_call_weight": _fraction_dict(critical),
        "lower_weight": _fraction_dict(lower),
        "upper_weight": _fraction_dict(upper),
        "observed_price": observed_price,
        "rule": "continue_below_critical_weight_buy_at_or_above",
    }


def simulate_policy(
    offers: Sequence[Mapping[str, object]],
    policy: str,
    threshold: int | None = None,
    budget: Mapping[str, object] | None = None,
) -> SearchOutcome:
    """Run one deterministic buy-or-continue policy over non-recallable offers."""
    if policy not in POLICIES:
        raise ValueError(f"unsupported policy: {policy}")
    if policy != "accept_first":
        threshold = _non_negative_integer(threshold, "threshold")

    parsed_offers = tuple(_parse_offer(offer) for offer in offers)
    parsed_budget = _parse_budget(budget)
    resources = ResourceUsage()
    queries = 0

    for index, offer in enumerate(parsed_offers):
        next_resources = resources.add(offer.resources)
        if not _within_budget(next_resources, parsed_budget):
            return SearchOutcome(
                purchased=False,
                accepted_price=None,
                accepted_index=None,
                queries=queries,
                resources=resources,
                terminal_reason="resource_exhausted",
            )

        resources = next_resources
        queries += 1
        if not offer.available:
            continue

        assert offer.price is not None
        should_accept = policy == "accept_first" or offer.price <= threshold
        if policy == "resource_aware_threshold" and not _has_feasible_next_call(
            parsed_offers, index, resources, parsed_budget
        ):
            should_accept = True
        if should_accept:
            return SearchOutcome(
                purchased=True,
                accepted_price=offer.price,
                accepted_index=index,
                queries=queries,
                resources=resources,
                terminal_reason="purchased",
            )

    return SearchOutcome(
        purchased=False,
        accepted_price=None,
        accepted_index=None,
        queries=queries,
        resources=resources,
        terminal_reason="merchants_exhausted",
    )


def weighted_loss(outcome: SearchOutcome, weights: Mapping[str, object]) -> int:
    """Score price, resource use, and purchase failure with integer shadow prices."""
    failure_penalty = _non_negative_integer(weights.get("failure_penalty"), "failure_penalty")
    loss = outcome.accepted_price if outcome.purchased else failure_penalty
    assert loss is not None
    for field in RESOURCE_FIELDS:
        weight = _non_negative_integer(weights.get(field, 0), f"{field} weight")
        loss += weight * getattr(outcome.resources, field)
    return loss


def run_analysis(seed: int) -> dict[str, Any]:
    """Generate exact hard-constraint and scalarized comparator surfaces."""
    merchants = _benchmark_forecasts()
    base_resource_weights = {
        "time": {"numerator": 1, "denominator": 2},
        "tokens": {"numerator": 1, "denominator": 1000},
        "api_cost": 1,
    }
    api_call_weights = tuple(range(0, 31, 2))
    observed_price = 110
    failure_penalty = 220
    surface = reservation_surface(
        merchants=merchants,
        base_resource_weights=base_resource_weights,
        api_call_weights=api_call_weights,
        failure_penalty=failure_penalty,
        observed_price=observed_price,
    )
    break_even = break_even_api_call_weight(
        merchants=merchants,
        base_resource_weights=base_resource_weights,
        failure_penalty=failure_penalty,
        observed_price=observed_price,
        lower_weight=6,
        upper_weight=8,
    )
    constraint_surface = hard_constraint_surface(
        merchants=merchants,
        scenarios=_hard_constraint_scenarios(),
        failure_penalty=failure_penalty,
        observed_price=observed_price,
    )
    routing_control = _equal_depth_routing_control()
    reservation_values = [row["reservation_price"]["value"] for row in surface]
    actions = [row["action"] for row in surface]
    constrained_actions = [row["action"] for row in constraint_surface]
    constrained_action_map = {
        row["id"]: row["action"] for row in constraint_surface
    }
    constrained_action_signature = "|".join(
        f"{scenario_id}:{action}"
        for scenario_id, action in constrained_action_map.items()
    )
    switch_row = next((row for row in surface if row["action"] == "buy"), None)
    return {
        "random_seed": seed,
        "algorithm": "finite_horizon_bellman_reservation_policy",
        "merchant_count": len(merchants),
        "observed_price": observed_price,
        "failure_penalty": failure_penalty,
        "base_resource_weights": base_resource_weights,
        "merchant_forecasts": merchants,
        "hard_constraint_surface": constraint_surface,
        "hard_constraint_scenario_count": len(constraint_surface),
        "hard_constraint_actions": constrained_action_map,
        "hard_constraint_action_signature": constrained_action_signature,
        "hard_constraint_action_switch": (
            "buy" in constrained_actions and "continue" in constrained_actions
        ),
        "hard_constraint_buy_count": constrained_actions.count("buy"),
        "hard_constraint_continue_count": constrained_actions.count("continue"),
        "equal_depth_routing_control": routing_control,
        "equal_depth_routing_signature": routing_control["signature"],
        "price_capped_limit": next(
            row["max_purchase_price"]
            for row in constraint_surface
            if row["id"] == "price-capped"
        ),
        "reservation_surface": surface,
        "break_even": break_even,
        "critical_api_call_weight_numerator": break_even[
            "critical_api_call_weight"
        ]["numerator"],
        "critical_api_call_weight_denominator": break_even[
            "critical_api_call_weight"
        ]["denominator"],
        "critical_api_call_weight": break_even["critical_api_call_weight"]["value"],
        "reservation_surface_monotone": all(
            left <= right
            for left, right in pairwise(reservation_values)
        ),
        "observed_offer_action_switch": "continue" in actions and "buy" in actions,
        "first_buy_api_call_weight": (
            switch_row["api_call_weight"] if switch_row is not None else None
        ),
        "decision_rule": {
            "buy_when": "observed_price <= reservation_price",
            "continue_when": "observed_price > reservation_price",
            "interpretation": (
                "Continue only when expected price improvement exceeds the fully "
                "scalarized cost and failure risk of searching onward."
            ),
        },
    }


def _hard_constraint_scenarios() -> list[dict[str, Any]]:
    relaxed = {"time": 31, "tokens": 10000, "api_calls": 8, "api_cost": 20}
    return [
        {
            "id": "relaxed",
            "label": "All budgets relaxed",
            "budget": relaxed,
            "max_purchase_price": 140,
        },
        {
            "id": "time-tight",
            "label": "Tight deadline",
            "budget": {**relaxed, "time": 6},
            "max_purchase_price": 140,
        },
        {
            "id": "token-tight",
            "label": "Tight token budget",
            "budget": {**relaxed, "tokens": 1900},
            "max_purchase_price": 140,
        },
        {
            "id": "api-tight",
            "label": "Two API calls available",
            "budget": {**relaxed, "api_calls": 2},
            "max_purchase_price": 140,
        },
        {
            "id": "api-spend-tight",
            "label": "Tight API spending cap",
            "budget": {**relaxed, "api_cost": 4},
            "max_purchase_price": 140,
        },
        {
            "id": "combined",
            "label": "Combined operating limits",
            "budget": {"time": 10, "tokens": 3000, "api_calls": 3, "api_cost": 7},
            "max_purchase_price": 140,
        },
        {
            "id": "price-capped",
            "label": "Hard purchase-price cap",
            "budget": relaxed,
            "max_purchase_price": 100,
        },
    ]


def _equal_depth_routing_control() -> dict[str, Any]:
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
    return {
        "remaining_query_depth": 1,
        "time_tight_next_merchant_index": time_tight["next_merchant_index"],
        "token_tight_next_merchant_index": token_tight["next_merchant_index"],
        "signature": "time-tight:merchant-3|token-tight:merchant-2",
    }


def _benchmark_forecasts() -> list[dict[str, Any]]:
    price_grids = (
        ((72, 1), (88, 2), (104, 3), (118, 2), (145, 1)),
        ((66, 1), (84, 2), (101, 3), (121, 2), (150, 1)),
        ((61, 1), (82, 2), (99, 3), (125, 2), (154, 1)),
        ((58, 1), (80, 2), (97, 3), (127, 2), (158, 1)),
        ((55, 1), (78, 2), (95, 3), (130, 2), (163, 1)),
        ((52, 1), (76, 2), (93, 3), (134, 2), (168, 1)),
        ((49, 1), (74, 2), (91, 3), (138, 2), (174, 1)),
        ((46, 1), (72, 2), (89, 3), (142, 2), (180, 1)),
    )
    forecasts: list[dict[str, Any]] = []
    for index, price_grid in enumerate(price_grids):
        forecasts.append(
            {
                "price_weights": [
                    {"price": price, "weight": weight} for price, weight in price_grid
                ],
                "unavailable_weight": 1 + index // 3,
                "time": 3 + index % 3,
                "tokens": 900 + 100 * index,
                "api_calls": 1,
                "api_cost": 2 + index % 2,
            }
        )
    return forecasts


def _parse_offer(value: Mapping[str, object]) -> Offer:
    available = value.get("available")
    if not isinstance(available, bool):
        raise ValueError("offer availability must be boolean")
    price = value.get("price")
    if available:
        price = _positive_integer(price, "available offer price")
    elif price is not None:
        raise ValueError("unavailable offers must not have a price")
    resources = ResourceUsage(
        time=_non_negative_integer(value.get("time", 0), "offer time"),
        tokens=_non_negative_integer(value.get("tokens", 0), "offer tokens"),
        api_calls=_non_negative_integer(value.get("api_calls", 1), "offer api_calls"),
        api_cost=_non_negative_integer(value.get("api_cost", 0), "offer api_cost"),
    )
    return Offer(available=available, price=price, resources=resources)


def _parse_forecast(value: Mapping[str, object]) -> MerchantForecast:
    outcomes = value.get("price_weights")
    if not isinstance(outcomes, list) or not outcomes:
        raise ValueError("price_weights must be a non-empty list")
    parsed_outcomes: list[tuple[int, int]] = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            raise ValueError("each price outcome must be a mapping")
        parsed_outcomes.append(
            (
                _positive_integer(outcome.get("price"), "forecast price"),
                _positive_integer(outcome.get("weight"), "forecast weight"),
            )
        )
    unavailable_weight = _non_negative_integer(
        value.get("unavailable_weight", 0), "unavailable_weight"
    )
    resources = ResourceUsage(
        time=_non_negative_integer(value.get("time", 0), "forecast time"),
        tokens=_non_negative_integer(value.get("tokens", 0), "forecast tokens"),
        api_calls=_non_negative_integer(value.get("api_calls", 1), "forecast api_calls"),
        api_cost=_non_negative_integer(value.get("api_cost", 0), "forecast api_cost"),
    )
    return MerchantForecast(
        price_weights=tuple(sorted(parsed_outcomes)),
        unavailable_weight=unavailable_weight,
        resources=resources,
    )


def _parse_budget(value: Mapping[str, object] | None) -> ResourceBudget:
    if value is None:
        return ResourceBudget()
    parsed: dict[str, int | None] = {}
    for field in RESOURCE_FIELDS:
        limit = value.get(field)
        parsed[field] = None if limit is None else _non_negative_integer(limit, field)
    return ResourceBudget(**parsed)


def _within_budget(resources: ResourceUsage, budget: ResourceBudget) -> bool:
    return all(
        getattr(budget, field) is None
        or getattr(resources, field) <= getattr(budget, field)
        for field in RESOURCE_FIELDS
    )


def _has_feasible_next_call(
    offers: tuple[Offer, ...],
    current_index: int,
    resources: ResourceUsage,
    budget: ResourceBudget,
) -> bool:
    next_index = current_index + 1
    if next_index >= len(offers):
        return False
    return _within_budget(resources.add(offers[next_index].resources), budget)


def _non_negative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _positive_integer(value: object, name: str) -> int:
    value = _non_negative_integer(value, name)
    if value == 0:
        raise ValueError(f"{name} must be positive")
    return value


def _non_negative_fraction(value: object, name: str) -> Fraction:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative rational number")
    if isinstance(value, int | Fraction):
        result = Fraction(value)
    elif isinstance(value, Mapping):
        result = Fraction(
            _non_negative_integer(value.get("numerator"), f"{name} numerator"),
            _positive_integer(value.get("denominator"), f"{name} denominator"),
        )
    else:
        raise ValueError(f"{name} must be a non-negative rational number")
    if result < 0:
        raise ValueError(f"{name} must be a non-negative rational number")
    return result


def _fraction_dict(value: Fraction) -> dict[str, int | float]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }