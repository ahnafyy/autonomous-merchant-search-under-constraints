from __future__ import annotations

import pytest
from autonomous_shopping_optimizer.permits import (
    PermitLedger,
    ResourceVector,
    UsageObservation,
)


def test_completed_call_reclaims_exact_unused_resources() -> None:
    ledger = PermitLedger({"time": 100, "tokens": 1000, "api_calls": 3, "api_cost": 20})
    reservation = ledger.reserve(
        "merchant-a",
        {"time": 40, "tokens": 500, "api_calls": 1, "api_cost": 8},
    )

    assert ledger.remaining_budget == ResourceVector(60, 500, 2, 12)

    result = ledger.reconcile(
        reservation,
        UsageObservation.exact(ResourceVector(25, 300, 1, 6)),
    )

    assert result.charged_usage == ResourceVector(25, 300, 1, 6)
    assert result.reclaimed == ResourceVector(15, 200, 0, 2)
    assert result.remaining_budget == ResourceVector(75, 700, 2, 14)
    assert ledger.charged_usage == ResourceVector(25, 300, 1, 6)


def test_cancelled_call_conservatively_charges_censored_resources() -> None:
    ledger = PermitLedger(ResourceVector(100, 1000, 3, 20))
    reservation = ledger.reserve("merchant-a", ResourceVector(40, 500, 1, 8))

    result = ledger.reconcile(
        reservation,
        UsageObservation(
            usage=ResourceVector(40, 120, 1, 3),
            exact_resources=frozenset({"time", "api_calls"}),
            status="cancelled",
        ),
    )

    assert result.charged_usage == ResourceVector(40, 500, 1, 8)
    assert result.reclaimed == ResourceVector()
    assert result.remaining_budget == ResourceVector(60, 500, 2, 12)


def test_failed_reservation_is_atomic() -> None:
    ledger = PermitLedger(ResourceVector(api_calls=1))

    with pytest.raises(ValueError, match="exceeds the remaining budget"):
        ledger.reserve("merchant-a", ResourceVector(api_calls=2))

    assert ledger.remaining_budget == ResourceVector(api_calls=1)


def test_reservation_can_only_be_reconciled_once() -> None:
    ledger = PermitLedger(ResourceVector(api_calls=1))
    reservation = ledger.reserve("merchant-a", ResourceVector(api_calls=1))
    observation = UsageObservation.exact(ResourceVector(api_calls=1))

    ledger.reconcile(reservation, observation)

    with pytest.raises(ValueError, match="unknown or already reconciled"):
        ledger.reconcile(reservation, observation)


def test_usage_above_permit_is_rejected_without_mutating_reservation() -> None:
    ledger = PermitLedger(ResourceVector(tokens=100))
    reservation = ledger.reserve("merchant-a", ResourceVector(tokens=50))

    with pytest.raises(ValueError, match="exceeds the reserved permit"):
        ledger.reconcile(
            reservation,
            UsageObservation.exact(ResourceVector(tokens=51)),
        )

    assert ledger.remaining_budget == ResourceVector(tokens=50)
    result = ledger.reconcile(
        reservation,
        UsageObservation.exact(ResourceVector(tokens=40)),
    )
    assert result.remaining_budget == ResourceVector(tokens=60)