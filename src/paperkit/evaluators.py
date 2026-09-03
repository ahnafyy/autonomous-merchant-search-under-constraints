from __future__ import annotations

from typing import Any

from paperkit.claims import Claim, ClaimEvaluation


def evaluate_registered_result(results: dict[str, Any], claim: Claim) -> ClaimEvaluation:
    """Compare a generated result with the expectation registered on a claim."""
    if claim.result_key is None or claim.expected is None:
        raise ValueError(f"{claim.id} requires result_key and expected values")
    observed = results[claim.result_key]
    expected = claim.expected
    if isinstance(observed, int | float) and isinstance(expected, int | float):
        tolerance = claim.tolerance if claim.tolerance is not None else 0.0
        difference = abs(observed - expected)
        return ClaimEvaluation(
            passed=difference <= tolerance,
            observed=observed,
            expected=expected,
            detail=f"Absolute difference {difference:.3g} <= tolerance {tolerance:.3g}.",
        )
    return ClaimEvaluation(
        passed=observed == expected,
        observed=observed,
        expected=expected,
        detail=(
            "Observed and registered values match." if observed == expected else "Values differ."
        ),
    )


def evaluate_live_panel_advantage(results: dict[str, Any], claim: Claim) -> ClaimEvaluation:
    """Adaptive stopping must beat the best tuned fixed rule on held-out live panels.

    The whole bootstrap interval has to sit below zero; a favourable point estimate
    alone is not evidence.
    """
    upper = results["adaptive_vs_fixed_ci_upper_minor"]
    difference = results["adaptive_vs_fixed_difference_minor"]
    episodes = results["held_out_episode_count"]
    passed = upper < 0
    return ClaimEvaluation(
        passed=passed,
        observed=upper,
        expected=claim.expected,
        detail=(
            f"Paired mean difference {difference:.2f} minor units over {episodes} "
            f"held-out episodes; 95% CI upper bound {upper:.2f} "
            f"{'excludes' if passed else 'includes'} zero."
        ),
    )


def evaluate_zero_budget_violations(results: dict[str, Any], claim: Claim) -> ClaimEvaluation:
    """Any hard-budget overrun is a correctness failure, not a performance tradeoff."""
    violations = results["hard_budget_violations"]
    return ClaimEvaluation(
        passed=violations == 0,
        observed=violations,
        expected=0,
        detail=(
            f"{violations} hard-budget violations across every replayed episode and arm."
        ),
    )


def evaluate_no_advantage_region(results: dict[str, Any], claim: Claim) -> ClaimEvaluation:
    """There must be a measured region where adaptive stopping does not help.

    A method that always wins on every grid cell usually means the baselines were
    not tuned honestly, so this negative result is checked as strictly as the
    positive one.
    """
    criteria = results["criteria"]
    threshold = criteria["no_advantage_rule"]["dispersion_ratio_at_or_below"]
    win_rates = criteria["win_rate_by_dispersion"]
    flat_cells = [
        level for level, rate in win_rates.items() if float(rate) == 0.0
    ]
    passed = threshold is not None and bool(flat_cells)
    return ClaimEvaluation(
        passed=passed,
        observed=threshold,
        expected=claim.expected,
        detail=(
            f"Adaptive stopping never wins at price dispersion at or below "
            f"{threshold}; {criteria['cells_favoring_fixed']} of "
            f"{criteria['cells_evaluated']} cells favour the fixed rule outright."
        ),
    )


def evaluate_solver_agreement(results: dict[str, Any], claim: Claim) -> ClaimEvaluation:
    """The dynamic program must reproduce brute-force optimal values exactly."""
    verification = results["solver_verification"]
    disagreements = [row["id"] for row in verification["cases"] if not row["agrees"]]
    return ClaimEvaluation(
        passed=verification["all_agree"],
        observed=verification["case_count"] - len(disagreements),
        expected=verification["case_count"],
        detail=(
            f"{verification['case_count']} enumerated instances checked; "
            + (
                "all agree with the solver in exact arithmetic."
                if not disagreements
                else f"disagreements: {', '.join(disagreements)}."
            )
        ),
    )


def evaluate_closed_form_rule(results: dict[str, Any], claim: Claim) -> ClaimEvaluation:
    """The hand-computable rule must track the exact solver and capture most savings."""
    verification = results["closed_form_verification"]
    worst = verification["max_relative_error"]
    captured = results["closed_form_savings_captured"]
    solver = results["solver_savings_captured"]
    passed = verification["within_tolerance"] and captured >= 0.75 * solver
    return ClaimEvaluation(
        passed=passed,
        observed=round(worst, 8),
        expected=verification["tolerance"],
        detail=(
            f"Closed form matches the solver to {worst:.2%} across "
            f"{verification['case_count']} horizons, and captures {captured:.1%} of "
            f"achievable savings against the solver's {solver:.1%}."
        ),
    )


def evaluate_secretary_rule_mismatch(
    results: dict[str, Any], claim: Claim
) -> ClaimEvaluation:
    """The classical n/e rule should underperform once price levels are known."""
    secretary = results["secretary_savings_captured"]
    closed_form = results["closed_form_savings_captured"]
    gap = results["secretary_costs_more_than_closed_form_minor"]
    comparison = results["rule_comparison"]
    arms = {arm["arm"]: arm for arm in comparison["arms"]}
    passed = secretary < closed_form
    return ClaimEvaluation(
        passed=passed,
        observed=round(secretary, 4),
        expected=claim.expected,
        detail=(
            f"At {comparison['merchant_count']} merchants the n/e rule captures "
            f"{secretary:.1%} of achievable savings versus {closed_form:.1%} for the "
            f"closed-form threshold, costing {gap:.0f} more minor units while using "
            f"{arms['secretary_37']['mean_query_count']:.2f} queries against "
            f"{arms['closed_form']['mean_query_count']:.2f}."
        ),
    )


def evaluate_offer_ephemerality(results: dict[str, Any], claim: Claim) -> ClaimEvaluation:
    """Offers must actually move between snapshots, or stopping is not a real decision."""
    delisting = results["delisting_rate"]
    price_change = results["price_change_rate"]
    passed = delisting > 0 and price_change > 0
    return ClaimEvaluation(
        passed=passed,
        observed=round(delisting + price_change, 6),
        expected=claim.expected,
        detail=(
            f"Between snapshots {results['calibration_date']} and "
            f"{results['evaluation_date']}, {delisting:.1%} of tracked listings were "
            f"delisted and {price_change:.1%} of survivors changed price."
        ),
    )