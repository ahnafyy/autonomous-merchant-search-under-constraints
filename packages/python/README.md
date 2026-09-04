# Autonomous Shopping Optimizer

Decide when an autonomous shopping agent should stop searching and buy, under hard
time, token, API-call, and spend budgets.

The host owns LLM calls, merchant tools, credentials, and purchase execution. This
package makes the decision and enforces the budget; it never contacts a merchant.

## The decision rule in ten lines

```python
from autonomous_shopping_optimizer import (
    affordable_queries, closed_form_reservation_price, ResourceVector,
)

# 1. Your budget is one number, not four: whichever resource runs out first binds.
k = affordable_queries(
    ResourceVector(time=30, tokens=8000, api_calls=6, api_cost=12),
    ResourceVector(time=4, tokens=900, api_calls=1, api_cost=2),
)                                                     # -> 6

# 2. Accept below a fraction of the price range you expect.
threshold = closed_form_reservation_price(8_000, 12_000, k)   # -> 8798, i.e. $87.98

if observed_price <= threshold:
    buy()
else:
    query_next_merchant()
```

The acceptance fractions come from `u(0) = 1`, `u(k+1) = u(k) - u(k)**2 / 2`, giving
`0.500, 0.375, 0.305, 0.258, ...`. The threshold *rises* as the budget drains, because
failing to buy costs more than overpaying.

This recursion is not new: it is the Cayley-Moser problem (Cayley 1875, Moser 1956).
We reproduce it in a price-minimization form and verify it against the exact solver.

If you have per-merchant price forecasts rather than a range, `reservation_price`
runs the exact dynamic program instead and returns a `Fraction`.

## Is it worth using?

The repository's calibrated simulation sweep reports evidence, not a universal
deployment prescription:

| Simulation condition | Evidence against the tuned fixed rule |
| --- | --- |
| Price spread at or below 1.01× | No cell favors adaptive stopping |
| Modest 1.10× spread | Fixed rule wins in two cells, at both constrained and full budgets |
| Larger spread in selected cells | Adaptive stopping is favored |

The table is simulation calibrated to the measured corpus, not a measurement of retail
outcomes. Each row includes its paired interval and sample size in the generated paper
and site tables. In the replay model, a catalog offer is accepted for an immediate
purchase attempt or not reserved; a later query is a new observation.

## Enforcing budgets

```python
from autonomous_shopping_optimizer import AutonomousShoppingOptimizer

reserved = optimizer.reserve_next_query()   # deducts the full permit up front
# ... host enforces every ceiling on reserved.permit, then dispatches ...
optimizer.reconcile(reserved, offer=offer, usage=usage, status="completed")
```

The ledger reserves capacity atomically, refuses repeated reconciliation, reclaims
capacity known to be unused, and charges censored usage at the full permit. Overruns
are prevented rather than detected afterwards. `next_query_permit()` and `observe()`
remain convenience methods for completed calls with exact usage.

## Also included

- `closed_form_reservation_price`, `affordable_queries`, `acceptance_fraction` --
  the hand-computable rule above.
- `secretary_sample_size` -- the classical `n/e` rule, provided so it can be compared
  against the threshold rule rather than confused with it.
- `hard_budget_stopping_plan` / `adaptive_hard_budget_plan` -- exact rational dynamic
  programs over remaining merchants and remaining budget.
- `verify_solver_against_enumeration`, `verify_closed_form_against_solver` -- checks
  against brute force and against the solver.
- `build_episodes` / `load_snapshot` -- turn dated merchant catalog snapshots into
  replayable episodes.
- `run_arm`, `ARMS` -- ten stopping policies replayed against frozen panels.
- `run_study`, `paired_bootstrap`, `derive_criteria` — the full study pipeline.
- `score_selection`, `exhaustive_oracle` — frozen-panel outcome metrics.
- `load_endpoint_inventory`, `screen_endpoint_inventory` — UCP endpoint screening.

## Status

Everything above works from a plain `pip install`. The study functions
(`run_study`, `run_real_study`, `measure_ephemerality`, `build_episodes`) are the
exception: they read dated merchant snapshots that are research inputs, not shipped
in the wheel. Run them from a clone of the repository, or pass
`data_dir=Path(...)` explicitly. The stopping rule itself needs no data.

The stopping solver is verified against exhaustive enumeration on small fixed-order
instances only; that is not a general optimality proof, and it does not cover adaptive
merchant routing. The closed-form recursion is a known result reproduced here, not a
new one. Permit safety is supported by observing zero violations across every replayed
episode, which is evidence rather than a proof.

Neither this package nor the npm package is published to a registry yet. Install from
source, or from a built wheel.
