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