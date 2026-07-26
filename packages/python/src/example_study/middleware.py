from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from example_study.analysis import RESOURCE_FIELDS, adaptive_hard_budget_plan


@dataclass(frozen=True)
class AgentDecision:
    action: str
    observed_merchant_index: int
    observed_price: int | None
    reservation_price: float | None
    next_merchant_index: int | None
    remaining_budget: dict[str, int]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "observed_merchant_index": self.observed_merchant_index,
            "observed_price": self.observed_price,
            "reservation_price": self.reservation_price,
            "next_merchant_index": self.next_merchant_index,
            "remaining_budget": self.remaining_budget,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QueryPermit:
    merchant_index: int
    timeout: int
    max_tokens: int
    max_api_calls: int
    max_api_spend: int

    def as_dict(self) -> dict[str, int]:
        return {
            "merchant_index": self.merchant_index,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "max_api_calls": self.max_api_calls,
            "max_api_spend": self.max_api_spend,
        }


class AutonomousShoppingOptimizer:
    """Stateful hard-budget optimizer for an external shopping-agent loop.

    The host performs merchant or LLM calls. This controller selects the next
    merchant, accounts for actual resource use, and returns stopping decisions.
    """

    def __init__(
        self,
        merchants: Sequence[Mapping[str, object]],
        budget: Mapping[str, object],
        *,
        max_purchase_price: int,
        failure_penalty: int,
    ) -> None:
        if not merchants:
            raise ValueError("at least one merchant forecast is required")
        self._merchants = [dict(merchant) for merchant in merchants]
        self._remaining = {
            field: _non_negative_integer(budget.get(field, 0), f"{field} budget")
            for field in RESOURCE_FIELDS
        }
        self._max_purchase_price = _positive_integer(
            max_purchase_price, "max_purchase_price"
        )
        self._failure_penalty = _non_negative_integer(
            failure_penalty, "failure_penalty"
        )
        self._unqueried = list(range(len(self._merchants)))
        self._terminal = False

    @property
    def remaining_budget(self) -> dict[str, int]:
        return dict(self._remaining)

    @property
    def unqueried_merchants(self) -> tuple[int, ...]:
        return tuple(self._unqueried)

    def next_query(self) -> int | None:
        """Return the best feasible merchant index without consuming resources."""
        if self._terminal or not self._unqueried:
            return None
        local_merchants = [self._merchants[index] for index in self._unqueried]
        plan = adaptive_hard_budget_plan(
            local_merchants,
            self._remaining,
            max_purchase_price=self._max_purchase_price,
            failure_penalty=self._failure_penalty,
        )
        local_index = plan["first_merchant_index"]
        return None if local_index is None else self._unqueried[local_index]

    def next_query_permit(self) -> QueryPermit | None:
        """Return enforceable per-call limits for the next selected merchant."""
        merchant_index = self.next_query()
        if merchant_index is None:
            return None
        forecast = self._merchants[merchant_index]
        return QueryPermit(
            merchant_index=merchant_index,
            timeout=min(
                self._remaining["time"],
                _non_negative_integer(forecast.get("time", 0), "merchant time"),
            ),
            max_tokens=min(
                self._remaining["tokens"],
                _non_negative_integer(forecast.get("tokens", 0), "merchant tokens"),
            ),
            max_api_calls=min(
                self._remaining["api_calls"],
                _non_negative_integer(
                    forecast.get("api_calls", 1), "merchant api_calls"
                ),
            ),
            max_api_spend=min(
                self._remaining["api_cost"],
                _non_negative_integer(
                    forecast.get("api_cost", 0), "merchant api_cost"
                ),
            ),
        )

    def observe(
        self,
        merchant_index: int,
        observed_price: int | None,
        *,
        actual_resources: Mapping[str, object] | None = None,
    ) -> AgentDecision:
        """Record one completed query and return the constrained next action."""
        if self._terminal:
            raise RuntimeError("shopping session is already terminal")
        if merchant_index not in self._unqueried:
            raise ValueError("merchant has already been queried or is unknown")
        if observed_price is not None:
            observed_price = _positive_integer(observed_price, "observed_price")

        forecast = self._merchants[merchant_index]
        usage_source = actual_resources or forecast
        usage = {
            field: _non_negative_integer(
                usage_source.get(field, 1 if field == "api_calls" else 0),
                f"actual {field}",
            )
            for field in RESOURCE_FIELDS
        }
        if any(usage[field] > self._remaining[field] for field in RESOURCE_FIELDS):
            raise ValueError("actual query resources exceed the remaining budget")
        for field in RESOURCE_FIELDS:
            self._remaining[field] -= usage[field]
        self._unqueried.remove(merchant_index)

        next_index, continuation, reservation = self._continuation()
        if observed_price is not None and observed_price <= reservation:
            self._terminal = True
            return self._decision(
                "buy",
                merchant_index,
                observed_price,
                reservation,
                None,
                "offer_is_admissible_and_no_worse_than_continuation",
            )
        if next_index is not None:
            return self._decision(
                "continue",
                merchant_index,
                observed_price,
                reservation if observed_price is not None else None,
                next_index,
                "offer_unavailable_or_future_search_has_lower_expected_loss",
            )

        self._terminal = True
        reason = (
            "offer_exceeds_hard_price_cap_and_no_query_is_feasible"
            if observed_price is not None and observed_price > self._max_purchase_price
            else "no_purchase_and_no_query_is_feasible"
        )
        return self._decision(
            "reject_without_feasible_query",
            merchant_index,
            observed_price,
            reservation if observed_price is not None else None,
            None,
            reason,
        )

    def _continuation(self) -> tuple[int | None, float, float]:
        if not self._unqueried:
            continuation = float(self._failure_penalty)
            return None, continuation, float(
                min(self._max_purchase_price, self._failure_penalty)
            )
        local_merchants = [self._merchants[index] for index in self._unqueried]
        plan = adaptive_hard_budget_plan(
            local_merchants,
            self._remaining,
            max_purchase_price=self._max_purchase_price,
            failure_penalty=self._failure_penalty,
        )
        local_index = plan["first_merchant_index"]
        next_index = None if local_index is None else self._unqueried[local_index]
        continuation = plan["expected_purchase_loss"]["value"]
        return next_index, continuation, min(self._max_purchase_price, continuation)

    def _decision(
        self,
        action: str,
        merchant_index: int,
        observed_price: int | None,
        reservation_price: float | None,
        next_merchant_index: int | None,
        reason: str,
    ) -> AgentDecision:
        return AgentDecision(
            action=action,
            observed_merchant_index=merchant_index,
            observed_price=observed_price,
            reservation_price=reservation_price,
            next_merchant_index=next_merchant_index,
            remaining_budget=self.remaining_budget,
            reason=reason,
        )


ShoppingAgentMiddleware = AutonomousShoppingOptimizer


def _non_negative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _positive_integer(value: object, name: str) -> int:
    parsed = _non_negative_integer(value, name)
    if parsed == 0:
        raise ValueError(f"{name} must be positive")
    return parsed
