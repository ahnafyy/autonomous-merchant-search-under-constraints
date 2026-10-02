from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from autonomous_shopping_optimizer.replay import (
    HiddenCardOutcome,
    HiddenCardState,
    SellerCard,
    SellerDeck,
    replay_hidden_cards,
    seller_order,
)

StateKey = tuple[int, int, int, int]
SCENARIO_FIELDS = (
    "time_ms",
    "time_value_minor_per_minute",
    "input_tokens",
    "input_cost_minor_per_million",
    "output_tokens",
    "output_cost_minor_per_million",
    "shopping_api_calls",
    "shopping_api_cost_minor_numerator_per_call",
    "shopping_api_cost_minor_denominator_per_call",
)


@dataclass(frozen=True)
class StateRecord:
    key: StateKey
    stop_loss: Fraction
    next_key: StateKey | None
    next_stop_loss: Fraction | None


@dataclass(frozen=True)
class EmpiricalPolicy:
    arm: str
    continue_states: frozenset[StateKey]
    relative_price_bin_basis_points: int

    def should_stop(self, state: HiddenCardState) -> bool:
        return (
            state_key(state, self.relative_price_bin_basis_points)
            not in self.continue_states
        )


def load_analysis_config(value: Mapping[str, object]) -> dict[str, object]:
    config = dict(value)
    if config.get("schema_version") != 1:
        raise ValueError("analysis schema_version must be 1")
    integer_fields = (
        "random_seed",
        "minimum_independent_sellers",
        "maximum_reveals",
        "permutations_per_product",
        "relative_price_bin_basis_points",
        "bootstrap_replicates",
    )
    for field in integer_fields:
        item = config.get(field)
        if not isinstance(item, int) or isinstance(item, bool) or item < 1:
            raise ValueError(f"{field} must be a positive integer")
    fraction = config.get("calibration_fraction")
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0 < fraction < 1:
        raise ValueError("calibration_fraction must be between zero and one")
    scenarios = config.get("cost_scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("cost_scenarios must be a non-empty array")
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
            raise ValueError("every cost scenario requires a string id")
        for field in SCENARIO_FIELDS:
            value = scenario.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"cost scenario {field} must be a non-negative integer")
        multiplier = scenario.get("cost_multiplier_basis_points", 10_000)
        if not isinstance(multiplier, int) or isinstance(multiplier, bool) or multiplier < 0:
            raise ValueError("cost_multiplier_basis_points must be a non-negative integer")
    values = config.get("threshold_basis_points")
    if not isinstance(values, list) or not values:
        raise ValueError("threshold_basis_points must be a non-empty array")
    if any(not isinstance(item, int) or isinstance(item, bool) for item in values):
        raise ValueError("threshold_basis_points must contain integers")
    return config


def scenario_cost_minor(
    scenario: Mapping[str, object],
) -> tuple[Fraction, dict[str, Fraction]]:
    """Calculate a declared per-reveal cost in currency minor units."""
    components = {
        "time": Fraction(
            int(scenario["time_ms"]) * int(scenario["time_value_minor_per_minute"]),
            60_000,
        ),
        "input_tokens": Fraction(
            int(scenario["input_tokens"]) * int(scenario["input_cost_minor_per_million"]),
            1_000_000,
        ),
        "output_tokens": Fraction(
            int(scenario["output_tokens"]) * int(scenario["output_cost_minor_per_million"]),
            1_000_000,
        ),
        "shopping_api": Fraction(
            int(scenario["shopping_api_calls"])
            * int(scenario["shopping_api_cost_minor_numerator_per_call"]),
            int(scenario["shopping_api_cost_minor_denominator_per_call"]),
        ),
    }
    multiplier = Fraction(int(scenario.get("cost_multiplier_basis_points", 10_000)), 10_000)
    scaled_components = {
        name: amount * multiplier for name, amount in components.items()
    }
    return sum(scaled_components.values(), Fraction()), scaled_components


def split_decks(
    decks: Iterable[SellerDeck], *, seed: int, calibration_fraction: float
) -> tuple[tuple[SellerDeck, ...], tuple[SellerDeck, ...]]:
    ordered = sorted(decks, key=lambda deck: deck.product_id)
    if len({deck.product_id for deck in ordered}) != len(ordered):
        raise ValueError("study input must contain at most one deck per product")
    if len(ordered) < 4:
        raise ValueError("study requires at least four independent products")
    random.Random(seed).shuffle(ordered)
    calibration_count = round(len(ordered) * calibration_fraction)
    calibration_count = min(len(ordered) - 2, max(2, calibration_count))
    return tuple(ordered[:calibration_count]), tuple(ordered[calibration_count:])


def split_panel_decks(
    decks: Iterable[SellerDeck], *, seed: int, calibration_fraction: float
) -> tuple[tuple[SellerDeck, ...], tuple[SellerDeck, ...]]:
    """Split a repeated-date panel by SKU, retaining all dates within one split."""
    by_product: dict[str, list[SellerDeck]] = defaultdict(list)
    for deck in decks:
        by_product[deck.product_id].append(deck)
    product_ids = sorted(by_product)
    if len(product_ids) < 4:
        raise ValueError("panel study requires at least four independent products")
    random.Random(seed).shuffle(product_ids)
    calibration_count = round(len(product_ids) * calibration_fraction)
    calibration_count = min(len(product_ids) - 2, max(2, calibration_count))
    calibration_ids = set(product_ids[:calibration_count])
    calibration = tuple(
        deck
        for product_id in product_ids
        for deck in by_product[product_id]
        if product_id in calibration_ids
    )
    held_out = tuple(
        deck
        for product_id in product_ids
        for deck in by_product[product_id]
        if product_id not in calibration_ids
    )
    return calibration, held_out


def state_key(state: HiddenCardState, bin_basis_points: int) -> StateKey:
    if bin_basis_points < 1:
        raise ValueError("bin_basis_points must be positive")
    first_price = state.revealed[0].price_minor
    ratio_basis_points = (state.best.price_minor * 10_000) // first_price
    ratio_bin = (ratio_basis_points // bin_basis_points) * bin_basis_points
    return (
        len(state.revealed),
        state.remaining_cards,
        state.reveal_budget_remaining,
        ratio_bin,
    )


def trajectory_records(
    deck: SellerDeck,
    order: tuple[str, ...],
    *,
    inspection_cost_minor: Fraction,
    max_reveals: int,
    bin_basis_points: int,
) -> list[StateRecord]:
    inspection_cost = inspection_cost_minor / deck.median_price_minor
    cards = {card.seller_id: card for card in deck.cards}
    revealed: list[SellerCard] = []
    states: list[HiddenCardState] = []
    stop_losses: list[Fraction] = []
    for seller_id in order[:max_reveals]:
        revealed.append(cards[seller_id])
        best = min(revealed, key=lambda card: (card.price_minor, card.seller_id))
        state = HiddenCardState(
            revealed=tuple(revealed),
            best=best,
            remaining_cards=len(deck.cards) - len(revealed),
            reveal_budget_remaining=max_reveals - len(revealed),
        )
        states.append(state)
        stop_losses.append(
            Fraction(best.price_minor, 1) / deck.median_price_minor
            + inspection_cost * len(revealed)
        )
    records: list[StateRecord] = []
    for index, state in enumerate(states):
        has_next = index + 1 < len(states)
        records.append(
            StateRecord(
                key=state_key(state, bin_basis_points),
                stop_loss=stop_losses[index],
                next_key=(
                    state_key(states[index + 1], bin_basis_points) if has_next else None
                ),
                next_stop_loss=stop_losses[index + 1] if has_next else None,
            )
        )
    return records


def fit_empirical_policy(
    decks: Iterable[SellerDeck],
    *,
    seed: int,
    permutations: int,
    inspection_cost_minor: Fraction,
    maximum_reveals: int,
    bin_basis_points: int,
    myopic: bool = False,
) -> EmpiricalPolicy:
    records: list[StateRecord] = []
    for deck in decks:
        budget = min(maximum_reveals, len(deck.cards))
        for replicate in range(permutations):
            order = seller_order(deck, seed=seed, replicate=replicate)
            records.extend(
                trajectory_records(
                    deck,
                    order,
                    inspection_cost_minor=inspection_cost_minor,
                    max_reveals=budget,
                    bin_basis_points=bin_basis_points,
                )
            )

    by_reveal: dict[int, list[StateRecord]] = defaultdict(list)
    for record in records:
        by_reveal[record.key[0]].append(record)
    values: dict[StateKey, Fraction] = {}
    continue_states: set[StateKey] = set()
    for reveal_count in sorted(by_reveal, reverse=True):
        by_key: dict[StateKey, list[StateRecord]] = defaultdict(list)
        for record in by_reveal[reveal_count]:
            by_key[record.key].append(record)
        for key, state_records in by_key.items():
            stop_value = _mean(record.stop_loss for record in state_records)
            continuing = [record for record in state_records if record.next_key is not None]
            if not continuing:
                values[key] = stop_value
                continue
            if myopic:
                continue_value = _mean(
                    record.next_stop_loss
                    for record in continuing
                    if record.next_stop_loss is not None
                )
            else:
                continue_value = _mean(
                    values.get(record.next_key, record.next_stop_loss)
                    for record in continuing
                    if record.next_key is not None and record.next_stop_loss is not None
                )
            if continue_value < stop_value:
                continue_states.add(key)
                values[key] = continue_value
            else:
                values[key] = stop_value
    return EmpiricalPolicy(
        arm="myopic_voi" if myopic else "adaptive_dynamic",
        continue_states=frozenset(continue_states),
        relative_price_bin_basis_points=bin_basis_points,
    )


def clustered_paired_bootstrap(
    treatment_by_product: Mapping[str, list[Fraction]],
    control_by_product: Mapping[str, list[Fraction]],
    *,
    seed: int,
    replicates: int,
) -> dict[str, object]:
    product_ids = sorted(treatment_by_product)
    if product_ids != sorted(control_by_product):
        raise ValueError("paired bootstrap requires identical product clusters")
    if not product_ids:
        raise ValueError("paired bootstrap requires products")
    differences = [
        _mean(treatment_by_product[product_id]) - _mean(control_by_product[product_id])
        for product_id in product_ids
    ]
    observed = _mean(differences)
    rng = random.Random(seed)
    bootstrap_means = sorted(
        _mean(differences[rng.randrange(len(differences))] for _ in differences)
        for _ in range(replicates)
    )
    lower = bootstrap_means[int(0.025 * replicates)]
    upper = bootstrap_means[min(replicates - 1, int(0.975 * replicates))]
    return {
        "mean_difference": float(observed),
        "ci_lower": float(lower),
        "ci_upper": float(upper),
        "product_clusters": len(product_ids),
        "permutations_are_independent": False,
        "bootstrap_replicates": replicates,
        "favors_treatment": upper < 0,
    }


def run_hidden_card_study(
    decks: Iterable[SellerDeck],
    config_value: Mapping[str, object],
    *,
    splitter: callable = split_decks,
) -> dict[str, object]:
    config = load_analysis_config(config_value)
    seed = int(config["random_seed"])
    permutations = int(config["permutations_per_product"])
    maximum_reveals = int(config["maximum_reveals"])
    bin_basis_points = int(config["relative_price_bin_basis_points"])
    calibration, held_out = splitter(
        decks,
        seed=seed,
        calibration_fraction=float(config["calibration_fraction"]),
    )
    cost_results: list[dict[str, object]] = []
    for scenario in config["cost_scenarios"]:
        cost_minor, components = scenario_cost_minor(scenario)
        adaptive = fit_empirical_policy(
            calibration,
            seed=seed,
            permutations=permutations,
            inspection_cost_minor=cost_minor,
            maximum_reveals=maximum_reveals,
            bin_basis_points=bin_basis_points,
        )
        outcomes = _evaluate(
            held_out,
            seed=seed,
            permutations=permutations,
            maximum_reveals=maximum_reveals,
            inspection_cost_minor=cost_minor,
            adaptive=adaptive,
        )
        comparison = clustered_paired_bootstrap(
            _losses_by_product(outcomes["adaptive_dynamic"]),
            _losses_by_product(outcomes["search_all"]),
            seed=seed + len(cost_results),
            replicates=int(config["bootstrap_replicates"]),
        )
        cost_results.append(
            {
                "cost_scenario": scenario["id"],
                "inspection_cost_minor": float(cost_minor),
                "inspection_cost_usd": float(cost_minor / 100),
                "cost_components_minor": {
                    key: float(value) for key, value in components.items()
                },
                "adaptive_continue_state_count": len(adaptive.continue_states),
                "arms": {
                    arm: _summarize_outcomes(arm_outcomes)
                    for arm, arm_outcomes in outcomes.items()
                },
                "adaptive_vs_search_all": comparison,
            }
        )
    return {
        "schema_version": 1,
        "random_seed": seed,
        "independent_unit": config.get("independent_unit", "catalog_product"),
        "calibration_product_count": len({deck.product_id for deck in calibration}),
        "held_out_product_count": len({deck.product_id for deck in held_out}),
        "calibration_replay_deck_count": len(calibration),
        "held_out_replay_deck_count": len(held_out),
        "permutations_per_product": permutations,
        "permutations_are_independent": False,
        "cost_results": cost_results,
    }


def _evaluate(
    decks: Iterable[SellerDeck],
    *,
    seed: int,
    permutations: int,
    maximum_reveals: int,
    inspection_cost_minor: Fraction,
    adaptive: EmpiricalPolicy,
) -> dict[str, list[tuple[str, HiddenCardOutcome]]]:
    results: dict[str, list[tuple[str, HiddenCardOutcome]]] = defaultdict(list)
    for deck in decks:
        budget = min(maximum_reveals, len(deck.cards))
        inspection_cost = inspection_cost_minor / deck.median_price_minor
        for replicate in range(permutations):
            order = seller_order(deck, seed=seed, replicate=replicate)
            arms = {
                "search_all": replay_hidden_cards(
                    deck,
                    order,
                    arm="search_all",
                    inspection_cost=inspection_cost,
                    max_reveals=budget,
                    should_stop=lambda _state: False,
                ),
                "adaptive_dynamic": replay_hidden_cards(
                    deck,
                    order,
                    arm="adaptive_dynamic",
                    inspection_cost=inspection_cost,
                    max_reveals=budget,
                    should_stop=adaptive.should_stop,
                ),
            }
            for arm, outcome in arms.items():
                results[arm].append((deck.product_id, outcome))
    return dict(results)


def _losses_by_product(
    outcomes: list[tuple[str, HiddenCardOutcome]],
) -> dict[str, list[Fraction]]:
    losses: dict[str, list[Fraction]] = defaultdict(list)
    for product_id, outcome in outcomes:
        losses[product_id].append(outcome.normalized_total_cost)
    return dict(losses)


def _summarize_outcomes(outcomes: list[tuple[str, HiddenCardOutcome]]) -> dict[str, Any]:
    values = [outcome for _, outcome in outcomes]
    return {
        "mean_normalized_total_cost": float(
            _mean(outcome.normalized_total_cost for outcome in values)
        ),
        "mean_normalized_item_price": float(
            _mean(outcome.normalized_item_price for outcome in values)
        ),
        "mean_price_regret_minor": float(
            _mean(Fraction(outcome.price_regret_minor) for outcome in values)
        ),
        "mean_reveals": float(_mean(Fraction(outcome.reveal_count) for outcome in values)),
        "oracle_hit_rate": float(
            _mean(Fraction(outcome.price_regret_minor == 0) for outcome in values)
        ),
        "replay_rows": len(values),
        "product_clusters": len({product_id for product_id, _ in outcomes}),
    }


def _mean(values: Iterable[Fraction | None]) -> Fraction:
    materialized = [value for value in values if value is not None]
    if not materialized:
        raise ValueError("mean requires at least one value")
    return sum(materialized, Fraction(0)) / len(materialized)