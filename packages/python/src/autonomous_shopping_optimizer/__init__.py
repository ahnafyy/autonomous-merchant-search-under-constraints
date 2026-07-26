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
from autonomous_shopping_optimizer.middleware import (
    AgentDecision,
    AutonomousShoppingOptimizer,
    QueryPermit,
    ShoppingAgentMiddleware,
)

__all__ = [
    "AgentDecision",
    "AutonomousShoppingOptimizer",
    "QueryPermit",
    "ResourceBudget",
    "ResourceUsage",
    "SearchOutcome",
    "ShoppingAgentMiddleware",
    "adaptive_hard_budget_plan",
    "hard_budget_stopping_plan",
    "hard_constraint_surface",
    "simulate_policy",
]

__version__ = "0.1.0"
