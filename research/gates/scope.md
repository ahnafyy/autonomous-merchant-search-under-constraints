# Scope Gate

Approve only when one avenue is selected, the research question is answerable,
the benchmark is small enough to inspect, falsifiers are explicit, and non-goals
prevent the paper from expanding without a decision.

## Prepared Material

- Selected avenue: `AVENUE-001`, adaptive hard-budget allocation for autonomous
  shopping agents.
- Primary question: whether adaptive pre-call permits improve purchase loss or
  purchase success over fixed feasible baselines while maintaining zero hard-budget
  violations under uncertain realized query usage.
- Minimal operational benchmark: one exact SKU, sequential no-recall merchant search,
  stochastic correlated query usage, enforceable per-call limits, hard episode
  budgets, and a hard purchase-price cap.
- Primary controls: equal resource splitting, worst-case reservation, myopic feasible
  querying, fixed-depth search, and a clairvoyant trace oracle.
- Deferred extensions: multi-attribute utility, parallel queries, learning across
  sessions, strategic merchants, baskets, and substitutions.
- Registered falsifier: reject the avenue if adaptive permits do not improve purchase
  loss or success over the strongest feasible baseline at zero violations on paired
  held-out traces after planner overhead and forecast misspecification are included.

The current packages issue enforceable pre-call limits and reconcile actual usage
afterward. Existing finite action maps validate the implementation but do not resolve
the registered open claim or establish market calibration, generality, or novelty.

Record approval in `status.yml`. Agents may prepare this gate but may not approve it.
