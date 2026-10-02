# Autonomous Shopping Optimizer

Research and runtime utilities for autonomous shopping. The current study asks
whether another seller inspection earns its cost; the older hard-budget planner below
remains available as a separate no-recall runtime API.

The host owns LLM calls, merchant tools, credentials, and purchase execution. This
package makes the decision and enforces the budget; it never contacts a merchant.

## Legacy hard-budget planner

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

## Recalled Pandora study

`SellerDeck`, `replay_hidden_cards`, `fit_empirical_policy`, and
`run_hidden_card_study` implement the current research model. A policy retains the
best revealed seller card and compares the expected price improvement from another
card with a declared inspection cost. With free recall and zero inspection cost, it
opens every feasible card. The registered held-out comparison is adaptive stopping
versus costed search-all: at zero cost search-all is better, small positive-cost
intervals can be inconclusive, and material inspection costs can favor adaptive
stopping.

`AutonomousShoppingOptimizer` and the closed-form functions implement the older
commit-or-continue API: continuing does not retain an observed offer. They are not
the policy benchmark reported by the current paper.

## Recalled-search hook for LLM tool loops

Use `RecalledSearchHook` after each seller tool result when the agent can retain its
best observed offer. The hook implements the reported rule exactly:

```text
SEARCH iff the next inspection fits the remaining budget
     and E[max(best retained offer - next price, 0)] > inspection cost
```

Prices and API spend are integer USD minor units. Resource shadow prices may be exact
fractions: `time_ms` is a millisecond quantity whose shadow price is minor units per
second, and `tokens` is charged in minor units per thousand tokens. The host supplies
calibrated samples for the next seller, then owns tool dispatch, actual-usage charging,
credentials, and purchase execution.

```python
from autonomous_shopping_optimizer import RecalledSearchHook

after_offer = RecalledSearchHook(
  price_samples_minor=[8_900, 9_400, 10_200, 11_100],
  shadow_prices={"time_ms": 8, "api_calls": 2},
)

decision = after_offer(
  current_best_minor=10_000,
  next_inspection_resources={"time_ms": 12_000, "api_calls": 1, "api_cost_minor": 18},
  remaining_budget={"time_ms": 45_000, "api_calls": 3, "api_cost_minor": 100},
)
if decision["action"] == "SEARCH":
  next_seller = call_seller_tool()  # Host responsibility.
else:
  buy_best_retained_offer()         # Host responsibility.
```

`decision` contains the `expected_saving_minor`, each cost component,
`inspection_cost_minor`, `net_value_minor`, feasibility, and reservation price for
logging or an LLM tool response. Do not use seller observations from one product as
the calibrated price sample for another product.

### OpenAI/ChatGPT and Claude tool registration

`recalled_search_tool_schema()` returns a vendor-neutral name, description, and JSON
input schema. `run_recalled_search_tool()` executes exactly that payload. Adapt only
the outer tool envelope at the SDK boundary; no provider SDK is required.

```python
from autonomous_shopping_optimizer import (
  recalled_search_tool_schema,
  run_recalled_search_tool,
)

schema = recalled_search_tool_schema()

# OpenAI Chat Completions-style registration:
openai_tool = {
  "type": "function",
  "function": {
    "name": schema["name"],
    "description": schema["description"],
    "parameters": schema["input_schema"],
    "strict": True,
  },
}

# Anthropic Messages-style registration:
claude_tool = schema

# When either model emits decide_recalled_search arguments:
decision = run_recalled_search_tool(model_tool_arguments)
```

Treat the model as a caller, not as the decision implementation. Validate seller
identity and a calibrated same-product price sample before calling the tool, enforce
the actual tool permit separately, and never let model output authorize a purchase.

## Evidence boundary

The frozen Shopify seller-deck study has 40 product decks: 24 calibration decks and
16 held-out product clusters. It uses only the recovered complete 39-query prefix of
48 registered deep queries. Its title identity rule was revised after collection, so
it is a reproducible held-out study, not a deployment recommendation.
Direct-merchant UCP panels are separate catalog-observability evidence, not inputs to
the Shopify Pandora policy replay.

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

## Runtime API boundary

For production agent integrations, depend on `RecalledSearchHook`,
`recalled_search_tool_schema`, `run_recalled_search_tool`, `PermitLedger`, and the
legacy planner APIs only. Dataset readers, replay studies, bootstrap procedures, and
catalog-deck builders are reproducibility and research APIs; they are not required for
the runtime hook and may need a repository checkout with frozen study data.

Neither this package nor the npm package is published to a registry yet. Install from
source, or from a built wheel.
