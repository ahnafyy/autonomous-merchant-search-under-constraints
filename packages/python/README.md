# Autonomous Shopping Optimizer

Hard-budget optimizer middleware for autonomous shopping loops. Install
`autonomous-shopping-optimizer`, then import `AutonomousShoppingOptimizer` from
`autonomous_shopping_optimizer`. The host owns LLM calls, merchant tools, credentials,
and purchase execution. Call `next_query_permit()` before dispatch, enforce its timeout,
token, call, and spend ceilings in the host runtime, then pass actual usage to
`observe()`. The optimizer tracks the remaining episode budgets and returns constrained
actions.