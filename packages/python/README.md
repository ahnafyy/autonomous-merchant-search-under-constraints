# Autonomous Shopping Optimizer

Hard-budget optimizer middleware for autonomous shopping loops. Install
`autonomous-shopping-optimizer`, then import `AutonomousShoppingOptimizer` from
`autonomous_shopping_optimizer`. The host owns LLM calls, merchant tools, credentials,
and purchase execution. Call `reserve_next_query()` before dispatch, enforce every
ceiling on the returned permit, then call `reconcile()` with the reservation receipt,
observed offer, usage, status, and any resource components known exactly. The ledger
reserves capacity atomically, prevents repeated reconciliation, reclaims known unused
capacity, and conservatively charges censored components. `next_query_permit()` and
`observe()` remain convenience methods for completed calls with exact usage.

The package also exposes commerce-native product, merchant, price, and offer types;
frozen-panel exhaustive-oracle scoring; and offline UCP endpoint-inventory screening.
The joint merchant-and-permit solver and empirical UCP policy evaluation remain open
research work rather than released findings.