"""The stopping-rule study: measure ephemerality, replay policies, map the criteria.

Three parts, in the order the manuscript reports them:

1. `measure_ephemerality` compares two dated snapshots of the same merchants to
   establish that offers actually move. Without churn there is nothing to stop for.
2. `run_real_study` replays every policy arm against frozen held-out panels built
   from live UCP data. This is the primary result.
3. `run_simulation_sweep` extends coverage beyond what the live corpus spans, using
   a generator calibrated to the measured dispersion, churn, and stockout rates. It
   answers "when is adaptive stopping worth it" across merchant counts and budgets
   that the real data does not reach, and is always reported as simulation.

Everything is seeded from project metadata and returns structured values.
"""
from __future__ import annotations

import json
import random
from fractions import Fraction
from pathlib import Path
from typing import Any

from autonomous_shopping_optimizer.baselines import (
    ArmResult,
    query_cost_vector,
    run_arm,
)
from autonomous_shopping_optimizer.closed_form import (
    verify_closed_form_against_solver,
)
from autonomous_shopping_optimizer.domain import Offer, Price
from autonomous_shopping_optimizer.panels import (
    Episode,
    EpisodeFeatures,
    Snapshot,
    build_episodes,
    load_snapshot,
)
from autonomous_shopping_optimizer.replay import FrozenMerchantObservation, FrozenPanel

DATA_DIR = Path("data/ucp")
CALIBRATION_DATE = "2026-08-02"
EVALUATION_DATE = "2026-09-02"

FIXED_ARMS = ("accept_first", "fixed_depth", "fixed_threshold", "equal_split")
REPORTED_ARMS = (
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
BOOTSTRAP_REPLICATES = 2000
FAILURE_PENALTY_MULTIPLE = 2


# --------------------------------------------------------------------------- #
# 1. Ephemerality
# --------------------------------------------------------------------------- #


def measure_ephemerality(calibration: Snapshot, evaluation: Snapshot) -> dict[str, Any]:
    """How much do listings move between two dated snapshots of the same merchants?

    Restricted to merchants the later snapshot paginated in full, so a missing SKU
    means delisted rather than truncated.
    """
    comparable = {
        domain for domain, status in evaluation.domain_status.items() if status == "ok"
    }
    earlier = {
        key: row
        for key, row in calibration.by_domain_sku().items()
        if key[0] in comparable
    }
    later = evaluation.by_domain_sku()

    survived = [key for key in earlier if key in later]
    disappeared = len(earlier) - len(survived)
    changed = [
        key
        for key in survived
        if earlier[key].price_minor
        and later[key].price_minor
        and earlier[key].price_minor != later[key].price_minor
    ]
    relative = sorted(
        Fraction(abs(later[key].price_minor - earlier[key].price_minor), earlier[key].price_minor)
        for key in changed
        if earlier[key].price_minor
    )
    return {
        "calibration_date": calibration.scan_date,
        "evaluation_date": evaluation.scan_date,
        "fully_paginated_domains": len(comparable),
        "tracked_listings": len(earlier),
        "surviving_listings": len(survived),
        "delisted_listings": disappeared,
        "delisting_rate": _as_float(Fraction(disappeared, len(earlier))) if earlier else 0.0,
        "price_changed_listings": len(changed),
        "price_change_rate": (
            _as_float(Fraction(len(changed), len(survived))) if survived else 0.0
        ),
        "median_relative_price_change": (
            _as_float(relative[len(relative) // 2]) if relative else 0.0
        ),
    }


# --------------------------------------------------------------------------- #
# 2. Real study
# --------------------------------------------------------------------------- #


def _failure_penalty(episode: Episode) -> int:
    return FAILURE_PENALTY_MULTIPLE * episode.features.cheapest_calibration_price_minor


def _episode_stockout(episodes: list[Episode]) -> Fraction:
    unavailable = sum(
        1
        for episode in episodes
        for observation in episode.panel.observations
        if observation.offer is not None and not observation.offer.available
    )
    total = sum(len(episode.panel.observations) for episode in episodes)
    return Fraction(unavailable, total) if total else Fraction(0)


def _run_all_arms(
    episodes: list[Episode],
    *,
    seed: int,
    max_queries: int,
    fixed_depth: int,
    threshold_quantile: Fraction,
    stockout_rate: Fraction,
) -> dict[str, list[ArmResult]]:
    results: dict[str, list[ArmResult]] = {arm: [] for arm in REPORTED_ARMS}
    for episode in episodes:
        threshold = _episode_threshold(episode, threshold_quantile)
        for arm in REPORTED_ARMS:
            results[arm].append(
                run_arm(
                    episode,
                    arm,
                    max_queries=max_queries,
                    failure_penalty_minor=_failure_penalty(episode),
                    seed=seed,
                    fixed_depth=fixed_depth,
                    price_threshold_minor=threshold,
                    stockout_rate=stockout_rate,
                )
            )
    return results


def _episode_threshold(episode: Episode, quantile: Fraction) -> int:
    """A fixed price threshold expressed relative to calibration prices."""
    prices = sorted(price for _, price in episode.calibration_prices if price > 0)
    if not prices:
        return 0
    index = min(len(prices) - 1, int(quantile * len(prices)))
    return prices[index]


def _losses(results: list[ArmResult]) -> list[int]:
    return [result.metrics.purchase_loss_minor for result in results]


def paired_bootstrap(
    treatment: list[int],
    control: list[int],
    *,
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, Any]:
    """Percentile CI on the paired mean difference (treatment - control).

    Episodes are resampled with replacement as whole pairs, so the comparison is
    never contaminated by which episodes happened to be drawn.
    """
    if len(treatment) != len(control):
        raise ValueError("paired bootstrap requires equal-length samples")
    if not treatment:
        raise ValueError("paired bootstrap requires at least one pair")
    differences = [t - c for t, c in zip(treatment, control, strict=True)]
    observed = Fraction(sum(differences), len(differences))

    rng = random.Random(seed)
    size = len(differences)
    means: list[Fraction] = []
    for _ in range(replicates):
        total = 0
        for _ in range(size):
            total += differences[rng.randrange(size)]
        means.append(Fraction(total, size))
    means.sort()
    lower = means[int(0.025 * replicates)]
    upper = means[min(replicates - 1, int(0.975 * replicates))]
    return {
        "mean_difference_minor": _as_float(observed),
        "ci_lower_minor": _as_float(lower),
        "ci_upper_minor": _as_float(upper),
        "replicates": replicates,
        "pairs": size,
        "favors_treatment": upper < 0,
        "significant": upper < 0 or lower > 0,
    }


def _arm_summary(arm: str, results: list[ArmResult]) -> dict[str, Any]:
    losses = _losses(results)
    successes = sum(1 for result in results if result.metrics.purchase_success)
    regrets = [
        result.metrics.price_regret_minor
        for result in results
        if result.metrics.price_regret_minor is not None
    ]
    return {
        "arm": arm,
        "episodes": len(results),
        "mean_purchase_loss_minor": _as_float(Fraction(sum(losses), len(losses))),
        "purchase_success_rate": _as_float(Fraction(successes, len(results))),
        "mean_query_count": _as_float(
            Fraction(sum(result.query_count for result in results), len(results))
        ),
        "mean_price_regret_minor": (
            _as_float(Fraction(sum(regrets), len(regrets))) if regrets else 0.0
        ),
        "hard_budget_violations": sum(
            1 for result in results if result.metrics.hard_budget_violation
        ),
    }


def run_real_study(
    calibration: Snapshot,
    evaluation: Snapshot,
    *,
    seed: int,
    max_queries: int = 2,
) -> dict[str, Any]:
    episodes = build_episodes(
        calibration, evaluation, query_resources=query_cost_vector()
    )
    if not episodes:
        raise ValueError("no episodes could be built from the supplied snapshots")
    stockout = _episode_stockout(episodes)

    # Tune the deployable fixed rules on calibration prices only.
    tuning, held_out = _split_episodes(episodes, seed=seed)
    fixed_depth, threshold_quantile = _tune_fixed_rules(
        tuning, seed=seed, max_queries=max_queries, stockout_rate=stockout
    )

    results = _run_all_arms(
        held_out,
        seed=seed,
        max_queries=max_queries,
        fixed_depth=fixed_depth,
        threshold_quantile=threshold_quantile,
        stockout_rate=stockout,
    )
    summaries = [_arm_summary(arm, results[arm]) for arm in REPORTED_ARMS]
    best_fixed = min(
        (summary for summary in summaries if summary["arm"] in FIXED_ARMS),
        key=lambda summary: (summary["mean_purchase_loss_minor"], summary["arm"]),
    )
    comparison = paired_bootstrap(
        _losses(results["adaptive_stopping"]),
        _losses(results[best_fixed["arm"]]),
        seed=seed,
    )
    return {
        "episode_count": len(episodes),
        "tuning_episode_count": len(tuning),
        "held_out_episode_count": len(held_out),
        "max_queries": max_queries,
        "tuned_fixed_depth": fixed_depth,
        "tuned_threshold_quantile": _as_float(threshold_quantile),
        "measured_stockout_rate": _as_float(stockout),
        "arms": summaries,
        "best_fixed_arm": best_fixed["arm"],
        "adaptive_vs_best_fixed": comparison,
        "episode_features": _feature_summary(held_out),
        "total_hard_budget_violations": sum(
            summary["hard_budget_violations"] for summary in summaries
        ),
    }


def _split_episodes(
    episodes: list[Episode], *, seed: int
) -> tuple[list[Episode], list[Episode]]:
    ordered = sorted(episodes, key=lambda episode: episode.panel.panel_id)
    rng = random.Random(seed)
    tuning: list[Episode] = []
    held_out: list[Episode] = []
    for episode in ordered:
        (tuning if rng.random() < 0.5 else held_out).append(episode)
    return tuning, held_out


def _tune_fixed_rules(
    episodes: list[Episode],
    *,
    seed: int,
    max_queries: int,
    stockout_rate: Fraction,
) -> tuple[int, Fraction]:
    """Give the fixed baselines their best shot, using tuning episodes only."""
    best_depth, best_depth_loss = 1, None
    for depth in range(1, max_queries + 1):
        results = [
            run_arm(
                episode,
                "fixed_depth",
                max_queries=max_queries,
                failure_penalty_minor=_failure_penalty(episode),
                seed=seed,
                fixed_depth=depth,
                stockout_rate=stockout_rate,
            )
            for episode in episodes
        ]
        loss = sum(_losses(results))
        if best_depth_loss is None or loss < best_depth_loss:
            best_depth, best_depth_loss = depth, loss

    best_quantile, best_quantile_loss = Fraction(0), None
    for numerator in range(0, 5):
        quantile = Fraction(numerator, 4)
        results = [
            run_arm(
                episode,
                "fixed_threshold",
                max_queries=max_queries,
                failure_penalty_minor=_failure_penalty(episode),
                seed=seed,
                price_threshold_minor=_episode_threshold(episode, quantile),
                stockout_rate=stockout_rate,
            )
            for episode in episodes
        ]
        loss = sum(_losses(results))
        if best_quantile_loss is None or loss < best_quantile_loss:
            best_quantile, best_quantile_loss = quantile, loss
    return best_depth, best_quantile


def _feature_summary(episodes: list[Episode]) -> dict[str, Any]:
    if not episodes:
        return {}
    dispersions = sorted(episode.features.price_dispersion_ratio for episode in episodes)
    merchants = sorted(episode.features.merchant_count for episode in episodes)
    return {
        "median_price_dispersion_ratio": _as_float(dispersions[len(dispersions) // 2]),
        "max_price_dispersion_ratio": _as_float(dispersions[-1]),
        "episodes_with_meaningful_dispersion": sum(
            1 for value in dispersions if value > Fraction(21, 20)
        ),
        "median_merchant_count": merchants[len(merchants) // 2],
        "max_merchant_count": merchants[-1],
        "currencies": sorted({episode.currency for episode in episodes}),
    }


# --------------------------------------------------------------------------- #
# 3. Calibrated simulation sweep
# --------------------------------------------------------------------------- #


def simulate_episode(
    index: int,
    *,
    merchant_count: int,
    dispersion_ratio: Fraction,
    stockout_rate: Fraction,
    drift_rate: Fraction,
    base_price_minor: int,
    rng: random.Random,
) -> Episode:
    """One synthetic episode whose parameters come from the measured UCP corpus."""
    sku = f"SIM{index:06d}"
    calibration_prices: list[tuple[str, int]] = []
    observations: list[FrozenMerchantObservation] = []
    spread = float(dispersion_ratio) - 1.0

    for merchant in range(merchant_count):
        domain = f"merchant-{merchant:02d}.example"
        calibration_price = max(
            1, int(round(base_price_minor * (1.0 + spread * rng.random())))
        )
        calibration_prices.append((domain, calibration_price))

        if rng.random() < float(stockout_rate):
            offer = Offer(product_id=sku, merchant_id=domain, available=False, price=None)
        else:
            drift = 1.0 + float(drift_rate) * (rng.random() * 2.0 - 1.0)
            realized = max(1, int(round(calibration_price * drift)))
            offer = Offer(
                product_id=sku,
                merchant_id=domain,
                available=True,
                price=Price(item_minor=realized, currency="USD"),
            )
        observations.append(
            FrozenMerchantObservation(
                merchant_id=domain, offer=offer, resources=query_cost_vector()
            )
        )

    prices = [price for _, price in calibration_prices]
    stockouts = sum(
        1 for observation in observations if observation.offer is not None
        and not observation.offer.available
    )
    return Episode(
        panel=FrozenPanel(
            panel_id=sku, product_id=sku, observations=tuple(observations)
        ),
        features=EpisodeFeatures(
            merchant_count=merchant_count,
            price_dispersion_ratio=Fraction(max(prices), min(prices)),
            price_spread_minor=max(prices) - min(prices),
            calibration_stockout_rate=Fraction(stockouts, merchant_count),
            cheapest_calibration_price_minor=min(prices),
        ),
        currency="USD",
        is_isbn=False,
        calibration_prices=tuple(calibration_prices),
    )


def run_simulation_sweep(
    *,
    seed: int,
    stockout_rate: Fraction,
    drift_rate: Fraction,
    episodes_per_cell: int = 400,
    merchant_counts: tuple[int, ...] = (2, 3, 5, 8),
    dispersion_ratios: tuple[Fraction, ...] = (
        Fraction(101, 100),
        Fraction(11, 10),
        Fraction(13, 10),
        Fraction(2),
    ),
    budget_fractions: tuple[Fraction, ...] = (Fraction(1, 2), Fraction(1)),
    base_price_minor: int = 10_000,
) -> list[dict[str, Any]]:
    """Grid over the conditions an engineer can actually observe up front."""
    cells: list[dict[str, Any]] = []
    for merchant_count in merchant_counts:
        for dispersion in dispersion_ratios:
            for budget_fraction in budget_fractions:
                max_queries = max(1, int(budget_fraction * merchant_count))
                rng = random.Random(
                    f"{seed}:{merchant_count}:{dispersion}:{budget_fraction}"
                )
                episodes = [
                    simulate_episode(
                        index,
                        merchant_count=merchant_count,
                        dispersion_ratio=dispersion,
                        stockout_rate=stockout_rate,
                        drift_rate=drift_rate,
                        base_price_minor=base_price_minor,
                        rng=rng,
                    )
                    for index in range(episodes_per_cell)
                ]
                cells.append(
                    _evaluate_cell(
                        episodes,
                        seed=seed,
                        merchant_count=merchant_count,
                        dispersion=dispersion,
                        budget_fraction=budget_fraction,
                        max_queries=max_queries,
                        stockout_rate=stockout_rate,
                    )
                )
    return cells


def _evaluate_cell(
    episodes: list[Episode],
    *,
    seed: int,
    merchant_count: int,
    dispersion: Fraction,
    budget_fraction: Fraction,
    max_queries: int,
    stockout_rate: Fraction,
) -> dict[str, Any]:
    tuning, held_out = _split_episodes(episodes, seed=seed)
    fixed_depth, threshold_quantile = _tune_fixed_rules(
        tuning, seed=seed, max_queries=max_queries, stockout_rate=stockout_rate
    )
    results = _run_all_arms(
        held_out,
        seed=seed,
        max_queries=max_queries,
        fixed_depth=fixed_depth,
        threshold_quantile=threshold_quantile,
        stockout_rate=stockout_rate,
    )
    summaries = {arm: _arm_summary(arm, results[arm]) for arm in REPORTED_ARMS}
    best_fixed = min(
        (summaries[arm] for arm in FIXED_ARMS),
        key=lambda summary: (summary["mean_purchase_loss_minor"], summary["arm"]),
    )
    comparison = paired_bootstrap(
        _losses(results["adaptive_stopping"]),
        _losses(results[best_fixed["arm"]]),
        seed=seed,
    )
    baseline_loss = best_fixed["mean_purchase_loss_minor"]
    relative = (
        comparison["mean_difference_minor"] / baseline_loss if baseline_loss else 0.0
    )
    return {
        "merchant_count": merchant_count,
        "dispersion_ratio": _as_float(dispersion),
        "budget_fraction": _as_float(budget_fraction),
        "max_queries": max_queries,
        "held_out_episodes": len(held_out),
        "best_fixed_arm": best_fixed["arm"],
        "best_fixed_loss_minor": baseline_loss,
        "adaptive_loss_minor": summaries["adaptive_stopping"]["mean_purchase_loss_minor"],
        "oracle_loss_minor": summaries["exhaustive_oracle"]["mean_purchase_loss_minor"],
        "mean_difference_minor": comparison["mean_difference_minor"],
        "ci_lower_minor": comparison["ci_lower_minor"],
        "ci_upper_minor": comparison["ci_upper_minor"],
        "relative_improvement": round(-relative, 4),
        "adaptive_wins": comparison["favors_treatment"],
        "significant": comparison["significant"],
    }


def derive_criteria(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn the sweep into the advantage / no-advantage statement the paper makes.

    Three outcomes per cell: adaptive stopping helps (CI entirely below zero),
    hurts (CI entirely above zero), or is indistinguishable from the best tuned
    fixed rule. The reported rule is the simplest threshold pair that separates
    the helping cells from the rest, not a fitted model.
    """
    wins = [cell for cell in cells if cell["adaptive_wins"]]
    harms = [cell for cell in cells if cell["ci_lower_minor"] > 0]
    neutral = [
        cell for cell in cells if cell not in wins and cell not in harms
    ]

    dispersion_levels = sorted({cell["dispersion_ratio"] for cell in cells})
    budget_levels = sorted({cell["budget_fraction"] for cell in cells})

    win_rate_by_dispersion = {
        level: _win_rate(cells, "dispersion_ratio", level) for level in dispersion_levels
    }
    win_rate_by_budget = {
        level: _win_rate(cells, "budget_fraction", level) for level in budget_levels
    }
    never_helps_below = [
        level for level in dispersion_levels if win_rate_by_dispersion[level] == 0.0
    ]

    return {
        "cells_evaluated": len(cells),
        "cells_favoring_adaptive": len(wins),
        "cells_favoring_fixed": len(harms),
        "cells_indistinguishable": len(neutral),
        "advantage_rule": {
            "min_dispersion_ratio": min(
                (cell["dispersion_ratio"] for cell in wins), default=None
            ),
            "min_budget_fraction": min(
                (cell["budget_fraction"] for cell in wins), default=None
            ),
            "max_relative_improvement": max(
                (cell["relative_improvement"] for cell in wins), default=0.0
            ),
            "median_relative_improvement": _median(
                [cell["relative_improvement"] for cell in wins]
            ),
        },
        "no_advantage_rule": {
            "dispersion_ratio_at_or_below": max(never_helps_below, default=None),
            "worst_relative_change": min(
                (cell["relative_improvement"] for cell in harms), default=0.0
            ),
            "harm_cells": sorted(
                (
                    {
                        "merchant_count": cell["merchant_count"],
                        "dispersion_ratio": cell["dispersion_ratio"],
                        "budget_fraction": cell["budget_fraction"],
                        "relative_improvement": cell["relative_improvement"],
                    }
                    for cell in harms
                ),
                key=lambda row: (
                    row["merchant_count"],
                    row["dispersion_ratio"],
                    row["budget_fraction"],
                ),
            ),
        },
        "win_rate_by_dispersion": win_rate_by_dispersion,
        "win_rate_by_budget_fraction": win_rate_by_budget,
        "decision_table": sorted(
            (
                {
                    "merchant_count": cell["merchant_count"],
                    "dispersion_ratio": cell["dispersion_ratio"],
                    "budget_fraction": cell["budget_fraction"],
                    "relative_improvement": cell["relative_improvement"],
                    "verdict": (
                        "use_adaptive"
                        if cell["adaptive_wins"]
                        else "use_fixed"
                        if cell["ci_lower_minor"] > 0
                        else "no_difference"
                    ),
                }
                for cell in cells
            ),
            key=lambda row: (
                row["merchant_count"],
                row["dispersion_ratio"],
                row["budget_fraction"],
            ),
        ),
    }


def _win_rate(cells: list[dict[str, Any]], key: str, level: float) -> float:
    matching = [cell for cell in cells if cell[key] == level]
    if not matching:
        return 0.0
    wins = sum(1 for cell in matching if cell["adaptive_wins"])
    return round(wins / len(matching), 4)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[len(ordered) // 2], 6)


def _as_float(value: Fraction) -> float:
    return round(float(value), 6)


# --------------------------------------------------------------------------- #
# 4. Study entry point
# --------------------------------------------------------------------------- #


def resolve_data_dir(explicit: Path | None = None) -> Path:
    """Find `data/ucp` whether the build runs from the repo root or elsewhere."""
    if explicit is not None:
        return explicit
    candidates = (
        Path.cwd() / DATA_DIR,
        Path(__file__).resolve().parents[4] / DATA_DIR,
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"could not locate {DATA_DIR}")


def _snapshot_paths(data_dir: Path, date: str) -> tuple[Path, Path]:
    return (
        data_dir / f"deep-scan-rows-{date}.jsonl",
        data_dir / f"deep-scan-matches-{date}.json",
    )


def _corpus_stats(data_dir: Path, date: str) -> dict[str, Any]:
    _, matches_path = _snapshot_paths(data_dir, date)
    payload = json.loads(matches_path.read_text(encoding="utf-8"))
    return {
        "merchants_targeted": payload["domains_targeted"],
        "merchants_fully_paginated": payload.get("domains_ok", 0),
        "catalog_rows": payload["total_rows"],
        "unique_skus": payload["unique_skus"],
        "cross_merchant_skus": payload["cross_merchant_match_count"],
        "isbn_cross_merchant_skus": payload["isbn_cross_merchant_match_count"],
    }


def rule_comparison(
    *,
    seed: int,
    stockout_rate: Fraction,
    drift_rate: Fraction,
    merchant_count: int = 10,
    dispersion_ratio: Fraction = Fraction(2),
    episodes: int = 600,
    base_price_minor: int = 10_000,
) -> dict[str, Any]:
    """Head-to-head at a horizon long enough for exploration rules to differ.

    The live corpus has too few merchants per episode to separate the classical
    secretary rule from a threshold rule, so this comparison is run on the
    calibrated generator and reported as simulation.
    """
    rng = random.Random(f"rule-comparison:{seed}")
    population = [
        simulate_episode(
            index,
            merchant_count=merchant_count,
            dispersion_ratio=dispersion_ratio,
            stockout_rate=stockout_rate,
            drift_rate=drift_rate,
            base_price_minor=base_price_minor,
            rng=rng,
        )
        for index in range(episodes)
    ]
    tuning, held_out = _split_episodes(population, seed=seed)
    fixed_depth, threshold_quantile = _tune_fixed_rules(
        tuning, seed=seed, max_queries=merchant_count, stockout_rate=stockout_rate
    )
    results = _run_all_arms(
        held_out,
        seed=seed,
        max_queries=merchant_count,
        fixed_depth=fixed_depth,
        threshold_quantile=threshold_quantile,
        stockout_rate=stockout_rate,
    )
    summaries = {arm: _arm_summary(arm, results[arm]) for arm in REPORTED_ARMS}
    oracle = summaries["exhaustive_oracle"]["mean_purchase_loss_minor"]
    floor_ = summaries["accept_first"]["mean_purchase_loss_minor"]
    span = floor_ - oracle

    def captured(arm: str) -> float:
        """Share of the achievable saving this arm captures."""
        if span <= 0:
            return 0.0
        return round((floor_ - summaries[arm]["mean_purchase_loss_minor"]) / span, 4)

    return {
        "merchant_count": merchant_count,
        "dispersion_ratio": _as_float(dispersion_ratio),
        "held_out_episodes": len(held_out),
        "arms": [summaries[arm] for arm in REPORTED_ARMS],
        "savings_captured": {arm: captured(arm) for arm in REPORTED_ARMS},
        "secretary_vs_closed_form_minor": round(
            summaries["secretary_37"]["mean_purchase_loss_minor"]
            - summaries["closed_form"]["mean_purchase_loss_minor"],
            4,
        ),
        "closed_form_vs_solver_minor": round(
            summaries["closed_form"]["mean_purchase_loss_minor"]
            - summaries["adaptive_stopping"]["mean_purchase_loss_minor"],
            4,
        ),
    }


def run_study(seed: int, data_dir: Path | None = None) -> dict[str, Any]:
    """Full study: ephemerality, live-panel replay, and the calibrated sweep."""
    directory = resolve_data_dir(data_dir)
    calibration = load_snapshot(*_snapshot_paths(directory, CALIBRATION_DATE))
    evaluation = load_snapshot(*_snapshot_paths(directory, EVALUATION_DATE))

    ephemerality = measure_ephemerality(calibration, evaluation)
    corpus = _corpus_stats(directory, EVALUATION_DATE)
    real = run_real_study(calibration, evaluation, seed=seed)

    stockout = _rate(ephemerality["delisting_rate"])
    drift = _rate(ephemerality["median_relative_price_change"])
    cells = run_simulation_sweep(
        seed=seed,
        stockout_rate=stockout,
        drift_rate=drift,
    )
    criteria = derive_criteria(cells)
    comparison = real["adaptive_vs_best_fixed"]
    rules = rule_comparison(seed=seed, stockout_rate=stockout, drift_rate=drift)
    closed_form = verify_closed_form_against_solver()

    return {
        "study_seed": seed,
        "calibration_date": CALIBRATION_DATE,
        "evaluation_date": EVALUATION_DATE,
        # Corpus scale
        "merchants_targeted": corpus["merchants_targeted"],
        "merchants_fully_paginated": corpus["merchants_fully_paginated"],
        "catalog_rows": corpus["catalog_rows"],
        "unique_skus": corpus["unique_skus"],
        "cross_merchant_skus": corpus["cross_merchant_skus"],
        # Ephemerality
        "tracked_listings": ephemerality["tracked_listings"],
        "delisting_rate": ephemerality["delisting_rate"],
        "price_change_rate": ephemerality["price_change_rate"],
        "median_relative_price_change": ephemerality["median_relative_price_change"],
        # Live-panel result
        "episode_count": real["episode_count"],
        "held_out_episode_count": real["held_out_episode_count"],
        "best_fixed_arm": real["best_fixed_arm"],
        "adaptive_vs_fixed_difference_minor": comparison["mean_difference_minor"],
        "adaptive_vs_fixed_ci_lower_minor": comparison["ci_lower_minor"],
        "adaptive_vs_fixed_ci_upper_minor": comparison["ci_upper_minor"],
        "adaptive_beats_fixed_on_live_panels": comparison["favors_treatment"],
        "hard_budget_violations": real["total_hard_budget_violations"],
        "median_price_dispersion_ratio": real["episode_features"][
            "median_price_dispersion_ratio"
        ],
        "median_merchant_count": real["episode_features"]["median_merchant_count"],
        # Criteria
        "sweep_cells": criteria["cells_evaluated"],
        "sweep_cells_favoring_adaptive": criteria["cells_favoring_adaptive"],
        "sweep_cells_favoring_fixed": criteria["cells_favoring_fixed"],
        "advantage_min_dispersion_ratio": criteria["advantage_rule"][
            "min_dispersion_ratio"
        ],
        "advantage_max_relative_improvement": criteria["advantage_rule"][
            "max_relative_improvement"
        ],
        "no_advantage_dispersion_at_or_below": criteria["no_advantage_rule"][
            "dispersion_ratio_at_or_below"
        ],
        # Closed-form rule and the classical secretary comparison
        "closed_form_max_relative_error": closed_form["max_relative_error"],
        "closed_form_max_relative_error_percent": round(
            100 * closed_form["max_relative_error"], 3
        ),
        "closed_form_matches_solver": closed_form["within_tolerance"],
        "rule_comparison_merchant_count": rules["merchant_count"],
        "closed_form_savings_captured": rules["savings_captured"]["closed_form"],
        "solver_savings_captured": rules["savings_captured"]["adaptive_stopping"],
        "secretary_savings_captured": rules["savings_captured"]["secretary_37"],
        "closed_form_savings_captured_percent": round(
            100 * rules["savings_captured"]["closed_form"], 1
        ),
        "solver_savings_captured_percent": round(
            100 * rules["savings_captured"]["adaptive_stopping"], 1
        ),
        "secretary_savings_captured_percent": round(
            100 * rules["savings_captured"]["secretary_37"], 1
        ),
        "secretary_costs_more_than_closed_form_minor": rules[
            "secretary_vs_closed_form_minor"
        ],
        # Full structures
        "ephemerality": ephemerality,
        "corpus": corpus,
        "real_study": real,
        "simulation_cells": cells,
        "criteria": criteria,
        "rule_comparison": rules,
        "closed_form_verification": closed_form,
    }


def _rate(value: float) -> Fraction:
    """Convert a reported rate back to an exact fraction for the generator."""
    return Fraction(round(value * 1000), 1000)
