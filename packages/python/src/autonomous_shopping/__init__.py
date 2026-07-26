"""Compatibility imports for Autonomous Shopping Optimizer."""

from example_study.analysis import adaptive_hard_budget_plan
from example_study.middleware import (
    AgentDecision,
    AutonomousShoppingOptimizer,
    QueryPermit,
    ShoppingAgentMiddleware,
)

__all__ = [
    "AgentDecision",
    "AutonomousShoppingOptimizer",
    "QueryPermit",
    "ShoppingAgentMiddleware",
    "adaptive_hard_budget_plan",
]

__version__ = "0.1.0"
