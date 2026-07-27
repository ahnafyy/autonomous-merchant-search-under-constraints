"""Hard-constraint optimizer middleware for autonomous shopping."""

from autonomous_shopping_optimizer.analysis import (
    ResourceBudget,
    ResourceUsage,
    SearchOutcome,
    adaptive_hard_budget_plan,
    hard_budget_stopping_plan,
    hard_constraint_surface,
    simulate_policy,
)
from autonomous_shopping_optimizer.domain import (
    Buy,
    Merchant,
    Offer,
    Price,
    Product,
    ProductIdentifier,
    Query,
    ShoppingAction,
    Stop,
)
from autonomous_shopping_optimizer.middleware import (
    AgentDecision,
    AutonomousShoppingOptimizer,
    QueryPermit,
    ReservedQuery,
    ShoppingAgentMiddleware,
)
from autonomous_shopping_optimizer.permits import (
    PermitLedger,
    PermitReservation,
    ReconciliationResult,
    ResourceVector,
    UsageObservation,
)
from autonomous_shopping_optimizer.replay import (
    FrozenMerchantObservation,
    FrozenPanel,
    LossDecomposition,
    OutcomeMetrics,
    decompose_purchase_loss,
    exhaustive_oracle,
    score_selection,
)
from autonomous_shopping_optimizer.ucp import (
    EndpointCapability,
    EndpointExclusion,
    InventoryReport,
    load_endpoint_inventory,
    screen_endpoint_inventory,
)

__all__ = [
    "AgentDecision",
    "AutonomousShoppingOptimizer",
    "Buy",
    "EndpointCapability",
    "EndpointExclusion",
    "FrozenMerchantObservation",
    "FrozenPanel",
    "InventoryReport",
    "LossDecomposition",
    "Merchant",
    "Offer",
    "OutcomeMetrics",
    "PermitLedger",
    "PermitReservation",
    "Price",
    "Product",
    "ProductIdentifier",
    "Query",
    "QueryPermit",
    "ReconciliationResult",
    "ReservedQuery",
    "ResourceBudget",
    "ResourceUsage",
    "ResourceVector",
    "SearchOutcome",
    "ShoppingAgentMiddleware",
    "ShoppingAction",
    "Stop",
    "UsageObservation",
    "adaptive_hard_budget_plan",
    "decompose_purchase_loss",
    "exhaustive_oracle",
    "hard_budget_stopping_plan",
    "hard_constraint_surface",
    "load_endpoint_inventory",
    "screen_endpoint_inventory",
    "simulate_policy",
    "score_selection",
]

__version__ = "0.1.0"
