from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

RESOURCE_FIELDS = ("time", "tokens", "api_calls", "api_cost")
ExecutionStatus = Literal["completed", "timeout", "truncated", "cancelled", "failed"]


@dataclass(frozen=True)
class ResourceVector:
    time: int = 0
    tokens: int = 0
    api_calls: int = 0
    api_cost: int = 0

    def __post_init__(self) -> None:
        for resource in RESOURCE_FIELDS:
            value = getattr(self, resource)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{resource} must be a non-negative integer")

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> ResourceVector:
        return cls(**{resource: values.get(resource, 0) for resource in RESOURCE_FIELDS})

    def as_dict(self) -> dict[str, int]:
        return {resource: getattr(self, resource) for resource in RESOURCE_FIELDS}

    def fits_within(self, other: ResourceVector) -> bool:
        return all(
            getattr(self, resource) <= getattr(other, resource)
            for resource in RESOURCE_FIELDS
        )

    def add(self, other: ResourceVector) -> ResourceVector:
        return ResourceVector(
            **{
                resource: getattr(self, resource) + getattr(other, resource)
                for resource in RESOURCE_FIELDS
            }
        )

    def subtract(self, other: ResourceVector) -> ResourceVector:
        if not other.fits_within(self):
            raise ValueError("resource subtraction would produce a negative value")
        return ResourceVector(
            **{
                resource: getattr(self, resource) - getattr(other, resource)
                for resource in RESOURCE_FIELDS
            }
        )


@dataclass(frozen=True)
class PermitReservation:
    reservation_id: int
    merchant_id: str
    permit: ResourceVector
    _ledger_token: object = field(repr=False, compare=False)


@dataclass(frozen=True)
class UsageObservation:
    usage: ResourceVector
    exact_resources: frozenset[str]
    status: ExecutionStatus

    def __post_init__(self) -> None:
        unknown = self.exact_resources.difference(RESOURCE_FIELDS)
        if unknown:
            raise ValueError(f"unknown exact resources: {sorted(unknown)}")

    @classmethod
    def exact(
        cls,
        usage: ResourceVector,
        *,
        status: ExecutionStatus = "completed",
    ) -> UsageObservation:
        return cls(usage, frozenset(RESOURCE_FIELDS), status)


@dataclass(frozen=True)
class ReconciliationResult:
    reservation_id: int
    merchant_id: str
    status: ExecutionStatus
    observed_usage: ResourceVector
    charged_usage: ResourceVector
    reclaimed: ResourceVector
    remaining_budget: ResourceVector


class PermitLedger:
    """Atomically reserve hard budgets and conservatively reconcile call usage."""

    def __init__(self, budget: ResourceVector | Mapping[str, object]) -> None:
        self._initial = (
            budget if isinstance(budget, ResourceVector) else ResourceVector.from_mapping(budget)
        )
        self._remaining = self._initial
        self._ledger_token = object()
        self._next_reservation_id = 1
        self._active: dict[int, PermitReservation] = {}
        self._charged = ResourceVector()

    @property
    def initial_budget(self) -> ResourceVector:
        return self._initial

    @property
    def remaining_budget(self) -> ResourceVector:
        return self._remaining

    @property
    def charged_usage(self) -> ResourceVector:
        return self._charged

    def reserve(
        self,
        merchant_id: str,
        permit: ResourceVector | Mapping[str, object],
    ) -> PermitReservation:
        if not isinstance(merchant_id, str) or not merchant_id:
            raise ValueError("merchant_id must be a non-empty string")
        parsed_permit = (
            permit if isinstance(permit, ResourceVector) else ResourceVector.from_mapping(permit)
        )
        if not parsed_permit.fits_within(self._remaining):
            raise ValueError("permit exceeds the remaining budget")

        reservation = PermitReservation(
            reservation_id=self._next_reservation_id,
            merchant_id=merchant_id,
            permit=parsed_permit,
            _ledger_token=self._ledger_token,
        )
        self._remaining = self._remaining.subtract(parsed_permit)
        self._active[reservation.reservation_id] = reservation
        self._next_reservation_id += 1
        return reservation

    def reconcile(
        self,
        reservation: PermitReservation,
        observation: UsageObservation,
    ) -> ReconciliationResult:
        if reservation._ledger_token is not self._ledger_token:
            raise ValueError("reservation belongs to a different permit ledger")
        active = self._active.get(reservation.reservation_id)
        if active is None or active is not reservation:
            raise ValueError("reservation is unknown or already reconciled")
        if not observation.usage.fits_within(reservation.permit):
            raise ValueError("observed usage exceeds the reserved permit")

        charged = ResourceVector(
            **{
                resource: (
                    getattr(observation.usage, resource)
                    if resource in observation.exact_resources
                    else getattr(reservation.permit, resource)
                )
                for resource in RESOURCE_FIELDS
            }
        )
        reclaimed = reservation.permit.subtract(charged)
        self._remaining = self._remaining.add(reclaimed)
        self._charged = self._charged.add(charged)
        del self._active[reservation.reservation_id]

        return ReconciliationResult(
            reservation_id=reservation.reservation_id,
            merchant_id=reservation.merchant_id,
            status=observation.status,
            observed_usage=observation.usage,
            charged_usage=charged,
            reclaimed=reclaimed,
            remaining_budget=self._remaining,
        )