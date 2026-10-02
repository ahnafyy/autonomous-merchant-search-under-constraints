from __future__ import annotations

import gzip
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from fractions import Fraction
from functools import cache
from pathlib import Path
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


@cache
def run_analysis(seed: int) -> dict[str, Any]:
    """Load source-stratified Pandora and UCP evidence without pooling them."""
    from autonomous_shopping_optimizer.pandora import pandora_cost_table

    root = Path(__file__).resolve().parents[4]
    data_dir = root / "data" / "ucp"
    report_path = data_dir / "global-catalog-study-2026-09-18-deep.json"
    panel_quality_path = data_dir / "panel-observation-quality.json"
    results: dict[str, Any] = {
        "random_seed": seed,
        "study_design": "source_stratified_recalled_pandora_search",
        "empirical_claims_ready": False,
        "pandora": pandora_cost_table(),
        "shopify_global_catalog": {
            "status": "awaiting_registered_collection",
            "report": None,
        },
        "ucp_direct_panels": _ucp_panel_summary(panel_quality_path, data_dir, root),
        "ucp_cost_sensitivity": _ucp_cost_sensitivity(
            data_dir, root / "research" / "hidden-card-analysis.json"
        ),
    }
    if not report_path.is_file():
        return results
    report = json.loads(report_path.read_text(encoding="utf-8"))
    analysis = report.get("analysis", {})
    if analysis.get("random_seed") != seed:
        raise ValueError("hidden-card report seed does not match project.yml")
    study = report.get("study")
    if not isinstance(study, dict):
        results["shopify_global_catalog"] = {
            "status": "collected_insufficient_eligible_products",
            "report": report,
            "product_deck_count": report["deck_build"]["product_deck_count"],
            "seller_card_count": report["deck_build"]["seller_card_count"],
        }
        return results
    results["shopify_global_catalog"] = {
        "status": "exploratory_recovered_deep_query_prefix",
        "report": report,
        "collection_status": report["collection"].get("collection_status"),
        "planned_query_count": report["collection"].get("planned_query_count"),
        "completed_query_count": report["collection"].get("completed_query_count"),
        "product_deck_count": report["deck_build"]["product_deck_count"],
        "seller_card_count": report["deck_build"]["seller_card_count"],
        "calibration_product_count": study["calibration_product_count"],
        "held_out_product_count": study["held_out_product_count"],
        "permutations_per_product": study["permutations_per_product"],
        "independent_unit": study["independent_unit"],
        "cost_results": study["cost_results"],
    }
    return results


def _ucp_panel_summary(path: Path, data_dir: Path, root: Path) -> dict[str, object]:
    if not path.is_file():
        return {"status": "awaiting_panel_quality_report"}
    report = json.loads(path.read_text(encoding="utf-8"))
    excluded = report.get("excluded_dates", {})
    included = report.get("included_lifecycle_dates", [])
    lifecycle = report.get("lifecycle", {})
    summary: dict[str, object] = {
        "status": "collected_observability_context",
        "included_lifecycle_dates": included,
        "excluded_dates": excluded,
        "persistent_absence_at_horizon": lifecycle.get("persistent_absence_at_horizon"),
        "offers_that_reappeared": lifecycle.get("offers_that_reappeared"),
        "reappearance_events": lifecycle.get("reappearance_events"),
    }
    summary["cost_overlay"] = _ucp_cost_overlay(
        data_dir, included, root / "research" / "hidden-card-analysis.json"
    )
    summary["pandora_replay"] = _ucp_pandora_replay(
        data_dir, root / "research" / "hidden-card-analysis.json"
    )
    return summary


def _ucp_pandora_replay(data_dir: Path, config_path: Path) -> dict[str, object]:
    """Run a SKU-clustered recalled-search replay across frozen UCP panel dates."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    observation_dates = config.get("ucp_pandora_observation_dates")
    if not isinstance(observation_dates, list) or not all(
        isinstance(date, str) for date in observation_dates
    ):
        return {"status": "unavailable_no_registered_panel_dates"}
    from autonomous_shopping_optimizer.hidden_card_study import (
        run_hidden_card_study,
        split_panel_decks,
    )
    from autonomous_shopping_optimizer.ucp_pandora import build_ucp_panel_series

    decks, deck_counts = build_ucp_panel_series(data_dir, observation_dates)
    if len({deck.product_id for deck in decks}) < 4:
        return {
            "status": "insufficient_replayable_decks",
            "observation_dates": observation_dates,
            "product_deck_count": len({deck.product_id for deck in decks}),
            "deck_counts_by_date": deck_counts,
        }
    study = run_hidden_card_study(decks, config, splitter=split_panel_decks)
    return {
        "status": "analyzed_frozen_panel_series",
        "observation_dates": observation_dates,
        "product_deck_count": len({deck.product_id for deck in decks}),
        "repeated_date_deck_count": len(decks),
        "deck_counts_by_date": deck_counts,
        **study,
    }


def _ucp_cost_sensitivity(data_dir: Path, config_path: Path) -> dict[str, object]:
    """Replay one market-rate workload over registered total-cost multipliers."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sensitivity = config.get("ucp_cost_sensitivity")
    if not isinstance(sensitivity, dict):
        return {"status": "unavailable_no_registered_cost_sensitivity"}
    scenario_id = sensitivity.get("base_scenario_id")
    multipliers = sensitivity.get("multipliers_basis_points")
    if not isinstance(scenario_id, str) or not isinstance(multipliers, list):
        return {"status": "unavailable_invalid_cost_sensitivity"}
    base = next(
        (row for row in config["cost_scenarios"] if row.get("id") == scenario_id), None
    )
    if not isinstance(base, dict) or not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in multipliers
    ):
        return {"status": "unavailable_invalid_cost_sensitivity"}
    from autonomous_shopping_optimizer.hidden_card_study import (
        run_hidden_card_study,
        split_panel_decks,
    )
    from autonomous_shopping_optimizer.ucp_pandora import build_ucp_panel_series

    scenarios = [
        {
            **base,
            "id": f"{scenario_id}_x{multiplier / 10_000:g}",
            "cost_multiplier_basis_points": multiplier,
        }
        for multiplier in multipliers
    ]
    decks, _ = build_ucp_panel_series(data_dir, config["ucp_pandora_observation_dates"])
    study_config = {**config, "cost_scenarios": scenarios}
    study = run_hidden_card_study(decks, study_config, splitter=split_panel_decks)
    return {
        "status": "analyzed_registered_market_rate_multipliers",
        "base_scenario_id": scenario_id,
        "market_rate_multiplier_basis_points": multipliers,
        "interpretation": (
            "Multipliers scale the complete declared per-inspection cost while holding "
            "the dated provider-rate card and workload composition fixed."
        ),
        **study,
    }


def _ucp_cost_overlay(
    data_dir: Path, included_dates: object, config_path: Path
) -> dict[str, object]:
    """Apply registered declared per-call costs to frozen UCP probe manifests."""
    if not isinstance(included_dates, list):
        return {"status": "unavailable_no_included_dates"}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    calls_by_date: list[dict[str, object]] = []
    for observation_date in included_dates:
        if not isinstance(observation_date, str):
            continue
        manifest_path = data_dir / f"panel-observations-{observation_date}.manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            calls = manifest.get("merchants_probed")
            if isinstance(calls, int) and calls >= 0:
                calls_by_date.append(
                    {
                        "observation_date": observation_date,
                        "merchant_probe_calls": calls,
                        "call_count_source": "manifest.merchants_probed",
                    }
                )
                continue
        observation_path = data_dir / f"panel-observations-{observation_date}.jsonl.gz"
        if observation_path.is_file():
            with gzip.open(observation_path, "rt", encoding="utf-8") as handle:
                domains = {json.loads(line)["domain"] for line in handle}
            calls_by_date.append(
                {
                    "observation_date": observation_date,
                    "merchant_probe_calls": len(domains),
                    "call_count_source": "unique_observation_domains_lower_bound",
                }
            )
    total_calls = sum(item["merchant_probe_calls"] for item in calls_by_date)
    from autonomous_shopping_optimizer.hidden_card_study import scenario_cost_minor

    scenarios = []
    for scenario in config["cost_scenarios"]:
        cost_minor, components = scenario_cost_minor(scenario)
        scenarios.append(
            {
                "cost_scenario": scenario["id"],
                "cost_per_merchant_probe_minor": float(cost_minor),
                "cost_per_merchant_probe_usd": float(cost_minor / 100),
                "total_cost_minor": float(cost_minor * total_calls),
                "total_cost_usd": float(cost_minor * total_calls / 100),
                "cost_components_minor_per_probe": {
                    key: float(value) for key, value in components.items()
                },
            }
        )
    return {
        "status": "declared_historical_cost_overlay",
        "replay_unit": "one merchant-targeted catalog probe",
        "assumption": (
            "Every merchant probe is charged one registered scenario cost; this is a "
            "counterfactual cost allocation, not observed provider billing."
        ),
        "included_observation_dates": calls_by_date,
        "total_merchant_probe_calls": total_calls,
        "scenarios": scenarios,
    }


def reservation_price_for_conformance(
    observed_price: int,
    future_calibration: list[int],
    stockout_numerator: int,
    stockout_denominator: int,
) -> dict[str, Any]:
    """Exact reservation price as a rational, for cross-language conformance vectors."""
    from autonomous_shopping_optimizer.baselines import reservation_price

    value = reservation_price(
        observed_price,
        future_calibration,
        Fraction(stockout_numerator, stockout_denominator),
    )
    return _fraction_dict(value)


def mechanism_demonstration(seed: int) -> dict[str, Any]:
    """Exact hard-constraint planning evidence on a small declared instance."""
    merchants = _benchmark_forecasts()
    observed_price = 110
    failure_penalty = 220
    constraint_surface = hard_constraint_surface(
        merchants=merchants,
        scenarios=_hard_constraint_scenarios(),
        failure_penalty=failure_penalty,
        observed_price=observed_price,
    )
    routing_control = _equal_depth_routing_control()
    constrained_actions = [row["action"] for row in constraint_surface]
    constrained_action_map = {
        row["id"]: row["action"] for row in constraint_surface
    }
    constrained_action_signature = "|".join(
        f"{scenario_id}:{action}"
        for scenario_id, action in constrained_action_map.items()
    )
    return {
        "random_seed": seed,
        "algorithm": "finite_horizon_bellman_reservation_policy",
        "merchant_count": len(merchants),
        "observed_price": observed_price,
        "failure_penalty": failure_penalty,
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
        "decision_rule": {
            "buy_when": "observed_price <= reservation_price",
            "continue_when": "observed_price > reservation_price",
            "interpretation": (
                "Continue only when the current offer is worse than the expected "
                "purchase loss from feasible future search."
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


def _fraction_dict(value: Fraction) -> dict[str, int | float]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }