# Scope Gate

Approve only when one avenue is selected, the research question is answerable,
the benchmark is small enough to inspect, falsifiers are explicit, and non-goals
prevent the paper from expanding without a decision.

## Prepared Material

- Selected avenue: `AVENUE-001`, joint merchant routing and enforceable permit
  allocation for autonomous shopping agents.
- Primary question: whether joint UCP merchant and permit selection improves a
  preregistered purchase outcome over fixed feasible baselines while maintaining zero
  hard-budget violations under uncertain realized query usage.
- Minimal operational benchmark: one exact SKU, a finite eligible UCP merchant set,
  sequential no-recall search, uncertain correlated query usage, a discrete permit
  grid, hard episode budgets, and a hard purchase-price cap.
- Primary controls: equal resource splitting, worst-case reservation, myopic feasible
  querying, fixed-depth search, routing and permit ablations, the same policy under
  nonbinding budgets, and an exhaustive frozen-panel oracle.
- Deferred extensions: multi-attribute utility, parallel queries, learning across
  sessions, strategic merchants, baskets, and substitutions.
- Registered falsifier: reject the avenue if adaptive permits do not improve purchase
  loss or success over the strongest feasible baseline at zero violations on paired
  held-out traces after planner overhead and forecast misspecification are included.

The Python package now atomically reserves pre-call limits and conservatively
reconciles actual or censored usage. Existing finite action maps and lifecycle tests
validate the implementation but do not resolve any registered open claim or establish
market calibration, generality, or novelty.

Record approval in `status.yml`. Agents may prepare this gate but may not approve it.
