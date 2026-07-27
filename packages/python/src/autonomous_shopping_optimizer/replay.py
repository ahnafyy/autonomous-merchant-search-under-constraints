from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from autonomous_shopping_optimizer.domain import Offer
from autonomous_shopping_optimizer.permits import ExecutionStatus, ResourceVector


@dataclass(frozen=True)
class FrozenMerchantObservation:
    merchant_id: str
    offer: Offer | None
    resources: ResourceVector
    status: ExecutionStatus = "completed"

    def __post_init__(self) -> None:
        if not self.merchant_id.strip():
            raise ValueError("merchant_id must be non-empty")
        if self.offer is not None and self.offer.merchant_id != self.merchant_id:
            raise ValueError("observation merchant_id must match its offer")
        if self.status != "completed" and self.offer is not None:
            raise ValueError("an incomplete observation must not expose an offer")


@dataclass(frozen=True)
class FrozenPanel:
    panel_id: str
    product_id: str
    observations: tuple[FrozenMerchantObservation, ...]

    def __post_init__(self) -> None:
        if not self.panel_id.strip() or not self.product_id.strip():
            raise ValueError("panel_id and product_id must be non-empty")
        if not self.observations:
            raise ValueError("a frozen panel requires at least one merchant observation")
        merchant_ids = [observation.merchant_id for observation in self.observations]
        if len(merchant_ids) != len(set(merchant_ids)):
            raise ValueError("merchant observations must be unique within a panel")
        for observation in self.observations:
            if observation.offer is not None and observation.offer.product_id != self.product_id:
                raise ValueError("every panel offer must match panel product_id")

    def observation_for(self, merchant_id: str) -> FrozenMerchantObservation:
        for observation in self.observations:
            if observation.merchant_id == merchant_id:
                return observation
        raise ValueError(f"unknown panel merchant: {merchant_id}")


@dataclass(frozen=True)
class OutcomeMetrics:
    purchase_success: bool
    oracle_available: bool
    exact_oracle_price_hit: bool | None
    within_tolerance: bool | None
    selected_price_minor: int | None
    oracle_price_minor: int | None
    price_regret_minor: int | None
    purchase_loss_minor: int
    savings_captured: Fraction | None
    savings_denominator_defined: bool
    query_count: int
    hard_budget_violation: bool


@dataclass(frozen=True)
class LossDecomposition:
    budget_effect_minor: int
    policy_error_minor: int
    total_regret_minor: int


def exhaustive_oracle(
    panel: FrozenPanel,
    *,
    use_landed_price: bool = False,
) -> Offer | None:
    candidates = [
        observation.offer
        for observation in panel.observations
        if observation.status == "completed"
        and observation.offer is not None
        and observation.offer.available
    ]
    if not candidates:
        return None
    _require_common_currency(candidates)
    return min(
        candidates,
        key=lambda offer: (
            _offer_price(offer, use_landed_price=use_landed_price),
            offer.merchant_id,
        ),
    )


def score_selection(
    panel: FrozenPanel,
    *,
    selected_merchant_id: str | None,
    initial_merchant_id: str | None,
    failure_penalty_minor: int,
    query_count: int,
    hard_budget_violation: bool = False,
    tolerance_minor: int = 0,
    use_landed_price: bool = False,
) -> OutcomeMetrics:
    _non_negative_integer(failure_penalty_minor, "failure_penalty_minor")
    _non_negative_integer(query_count, "query_count")
    _non_negative_integer(tolerance_minor, "tolerance_minor")

    oracle = exhaustive_oracle(panel, use_landed_price=use_landed_price)
    selected = _selected_offer(panel, selected_merchant_id)
    if selected is not None and not selected.available:
        raise ValueError("selected merchant does not have an available offer")
    if selected is not None and selected.price is None:
        raise ValueError("selected available offer has no price")

    comparable = [offer for offer in (selected, oracle) if offer is not None]
    if initial_merchant_id is not None:
        initial = panel.observation_for(initial_merchant_id).offer
        if initial is not None:
            comparable.append(initial)
    else:
        initial = None
    _require_common_currency(comparable)

    selected_price = (
        None
        if selected is None
        else _offer_price(selected, use_landed_price=use_landed_price)
    )
    oracle_price = (
        None if oracle is None else _offer_price(oracle, use_landed_price=use_landed_price)
    )
    price_regret = (
        None
        if selected_price is None or oracle_price is None
        else selected_price - oracle_price
    )
    exact_hit = None if oracle_price is None else selected_price == oracle_price
    within_tolerance = (
        None
        if price_regret is None
        else price_regret <= tolerance_minor
    )

    savings_captured: Fraction | None = None
    denominator_defined = False
    if (
        initial is not None
        and initial.available
        and selected_price is not None
        and oracle_price is not None
    ):
        initial_price = _offer_price(initial, use_landed_price=use_landed_price)
        denominator = initial_price - oracle_price
        if denominator > 0:
            denominator_defined = True
            savings_captured = Fraction(initial_price - selected_price, denominator)

    return OutcomeMetrics(
        purchase_success=selected is not None,
        oracle_available=oracle is not None,
        exact_oracle_price_hit=exact_hit,
        within_tolerance=within_tolerance,
        selected_price_minor=selected_price,
        oracle_price_minor=oracle_price,
        price_regret_minor=price_regret,
        purchase_loss_minor=(
            selected_price if selected_price is not None else failure_penalty_minor
        ),
        savings_captured=savings_captured,
        savings_denominator_defined=denominator_defined,
        query_count=query_count,
        hard_budget_violation=hard_budget_violation,
    )


def decompose_purchase_loss(
    constrained: OutcomeMetrics,
    nonbinding: OutcomeMetrics,
) -> LossDecomposition:
    if constrained.oracle_price_minor != nonbinding.oracle_price_minor:
        raise ValueError("loss decomposition requires the same frozen panel oracle")
    oracle_loss = (
        constrained.oracle_price_minor
        if constrained.oracle_price_minor is not None
        else constrained.purchase_loss_minor
    )
    return LossDecomposition(
        budget_effect_minor=(
            constrained.purchase_loss_minor - nonbinding.purchase_loss_minor
        ),
        policy_error_minor=nonbinding.purchase_loss_minor - oracle_loss,
        total_regret_minor=constrained.purchase_loss_minor - oracle_loss,
    )


def _selected_offer(panel: FrozenPanel, merchant_id: str | None) -> Offer | None:
    if merchant_id is None:
        return None
    observation = panel.observation_for(merchant_id)
    if observation.status != "completed":
        raise ValueError("selected merchant query did not complete")
    return observation.offer


def _offer_price(offer: Offer, *, use_landed_price: bool) -> int:
    assert offer.price is not None
    return offer.price.comparable_minor(use_landed_price=use_landed_price)


def _require_common_currency(offers: list[Offer]) -> None:
    currencies = {offer.price.currency for offer in offers if offer.price is not None}
    if len(currencies) > 1:
        raise ValueError("panel comparisons require one currency")


def _non_negative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value