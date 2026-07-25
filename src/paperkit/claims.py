from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from paperkit.config import ConfigurationError, load_yaml

CLAIM_STATUSES = {
    "analytic",
    "exact-computational",
    "numerical",
    "computational-pattern",
    "conjecture",
    "open",
}


@dataclass(frozen=True)
class Claim:
    id: str
    statement: str
    status: str
    scope: str
    evaluator: str | None
    tolerance: float | None
    evidence: tuple[str, ...]
    manuscript_labels: tuple[str, ...]
    site_visible: bool
    limitations: tuple[str, ...]
    result_key: str | None
    expected: float | int | str | bool | None


@dataclass(frozen=True)
class ClaimEvaluation:
    passed: bool
    observed: float | int | str | bool | None
    expected: float | int | str | bool | None
    detail: str


Evaluator = Callable[[dict[str, Any], Claim], ClaimEvaluation]


def load_claims(path: Path) -> list[Claim]:
    raw = load_yaml(path)
    if raw.get("schema_version") != 1 or not isinstance(raw.get("claims"), list):
        raise ConfigurationError("claims.yml requires schema_version 1 and a claims list")

    claims: list[Claim] = []
    seen: set[str] = set()
    for index, item in enumerate(raw["claims"]):
        context = f"claims[{index}]"
        if not isinstance(item, dict):
            raise ConfigurationError(f"{context} must be a mapping")
        claim_id = item.get("id")
        statement = item.get("statement")
        status = item.get("status")
        scope = item.get("scope")
        required_values = (claim_id, statement, scope)
        if not all(isinstance(value, str) and value.strip() for value in required_values):
            raise ConfigurationError(f"{context} requires non-empty id, statement, and scope")
        assert isinstance(claim_id, str)
        assert isinstance(status, str)
        if claim_id in seen:
            raise ConfigurationError(f"Duplicate claim id: {claim_id}")
        if status not in CLAIM_STATUSES:
            raise ConfigurationError(f"{claim_id} has unsupported status: {status}")
        evaluator = item.get("evaluator")
        executable_statuses = {"exact-computational", "numerical", "computational-pattern"}
        if status in executable_statuses and (
            not isinstance(evaluator, str) or ":" not in evaluator
        ):
            raise ConfigurationError(f"{claim_id} requires an evaluator module:function")
        if status == "analytic" and not item.get("manuscript_labels"):
            raise ConfigurationError(f"{claim_id} requires a proof manuscript label")
        tolerance = item.get("tolerance")
        if tolerance is not None and not isinstance(tolerance, int | float):
            raise ConfigurationError(f"{claim_id} tolerance must be numeric")
        evidence = _string_tuple(item.get("evidence", []), f"{claim_id}.evidence")
        labels = _string_tuple(item.get("manuscript_labels", []), f"{claim_id}.manuscript_labels")
        limitations = _string_tuple(item.get("limitations", []), f"{claim_id}.limitations")
        result_key = item.get("result_key")
        if result_key is not None and not isinstance(result_key, str):
            raise ConfigurationError(f"{claim_id}.result_key must be a string")
        expected = item.get("expected")
        if expected is not None and not isinstance(expected, float | int | str | bool):
            raise ConfigurationError(f"{claim_id}.expected must be a scalar")
        claims.append(
            Claim(
                id=claim_id,
                statement=statement.strip(),
                status=status,
                scope=scope.strip(),
                evaluator=evaluator if isinstance(evaluator, str) else None,
                tolerance=float(tolerance) if tolerance is not None else None,
                evidence=evidence,
                manuscript_labels=labels,
                site_visible=item.get("site_visible") is True,
                limitations=limitations,
                result_key=result_key,
                expected=expected,
            )
        )
        seen.add(claim_id)
    return claims


def _string_tuple(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(f"{context} must be a list of strings")
    return tuple(value)


def load_evaluator(reference: str) -> Evaluator:
    module_name, function_name = reference.split(":", 1)
    function = getattr(import_module(module_name), function_name, None)
    if not callable(function):
        raise ConfigurationError(f"Claim evaluator is not callable: {reference}")
    return function


def evaluate_claims(results: dict[str, Any], claims: list[Claim]) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for claim in claims:
        if claim.evaluator:
            evaluation = load_evaluator(claim.evaluator)(results, claim)
        else:
            evaluation = ClaimEvaluation(
                passed=claim.status in {"conjecture", "open"},
                observed=None,
                expected=None,
                detail="No executable evaluator; status is documentary.",
            )
        evaluations.append(
            {
                "id": claim.id,
                "status": claim.status,
                "statement": claim.statement,
                "scope": claim.scope,
                "passed": evaluation.passed,
                "observed": evaluation.observed,
                "expected": evaluation.expected,
                "detail": evaluation.detail,
                "site_visible": claim.site_visible,
                "limitations": list(claim.limitations),
            }
        )
    return evaluations
