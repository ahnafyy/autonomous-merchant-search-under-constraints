# Autonomous Shopping Optimizer

An exact finite-horizon merchant-search algorithm with reusable open-source Python
and npm implementations.

The algorithm decides which merchant an autonomous shopping agent should query next
and whether it should buy the current offer, continue searching, or stop without a
purchase under hard time, token, API-call, API-spend, and purchase-price limits.

The Python and npm packages implement the current exact fixed-requirement planner and
expose permits that a host can enforce around each merchant or model call. The Python
package additionally provides atomic reservation receipts, exact or censored usage
reconciliation, and reclamation of known unused capacity. Equivalent receipt behavior
in the npm package remains open work.

The host application remains responsible for LLM calls, merchant tools, credentials,
timeouts, and purchase execution. The optimizer does not contact merchants or make a
purchase.

## Why this exists

An autonomous shopper cannot inspect every merchant when calls consume limited time,
tokens, API quota, and money. Searching again may reveal a better price, but it can
also consume the resources needed to complete the purchase. This project models that
choice as an exact finite-horizon decision problem with:

- adaptive merchant routing;
- no recall after an offer is rejected;
- merchant-specific price and availability forecasts;
- hard time, token, API-call, API-spend, and purchase-price limits; and
- an explicit penalty for ending without a purchase.

The canonical Python package generates deterministic evidence and shared conformance
vectors. The browser-safe npm package is checked against those same planner vectors.

## Agent loop

```text
optimizer.reserve_next_query()
						|
						v
host enforces timeout / token / call / spend ceilings
						|
						v
host invokes the LLM or merchant tool
						|
						v
optimizer.reconcile(receipt, price, actual resource use)
						|
						v
buy | continue | reject_without_feasible_query
```

The pre-call reservation and enforcement steps are essential. Rejecting an overrun
after a call has already completed cannot preserve a hard budget. If cancellation
leaves a resource component unknown, the Python ledger charges the full reserved
amount for that component rather than treating the lower bound as exact usage.

## Python usage

```python
from autonomous_shopping_optimizer import AutonomousShoppingOptimizer

optimizer = AutonomousShoppingOptimizer(
		merchants=[
				{
						"price_weights": [
								{"price": 80, "weight": 1},
								{"price": 110, "weight": 1},
						],
						"unavailable_weight": 1,
						"time": 4,
						"tokens": 800,
						"api_calls": 1,
						"api_cost": 2,
				},
				{
						"price_weights": [{"price": 90, "weight": 1}],
						"time": 2,
						"tokens": 400,
						"api_calls": 1,
						"api_cost": 1,
				},
		],
		budget={"time": 8, "tokens": 1600, "api_calls": 2, "api_cost": 4},
		max_purchase_price=100,
		failure_penalty=180,
)

reserved = optimizer.reserve_next_query()
if reserved is not None:
		permit = reserved.permit
		# Apply every permit ceiling to the host call before dispatch.
		decision = optimizer.reconcile(
				reserved.reservation,
				observed_price=92,
				actual_resources={
						"time": 3,
						"tokens": 620,
						"api_calls": 1,
						"api_cost": 2,
				},
		)
		print(decision.action)
```

For completed calls, `next_query_permit()` and `observe()` remain guarded convenience
methods. `next_query_permit()` reserves the returned permit, and every `observe()` must
match an active reservation. The receipt API is required for timeout, cancellation,
truncation, or partially censored resource observations.

The Python distribution is `autonomous-shopping-optimizer`; its public import is
`autonomous_shopping_optimizer`.

## JavaScript usage

The npm package currently conforms for the existing planner and completed-call
middleware operations. Atomic reservation receipts and censored reconciliation are
implemented in Python first and remain pending JavaScript conformance work.

```js
import { AutonomousShoppingOptimizer } from "autonomous-shopping-optimizer";

const optimizer = new AutonomousShoppingOptimizer({
	merchants: [
		{
			price_weights: [{ price: 80, weight: 1 }, { price: 110, weight: 1 }],
			unavailable_weight: 1,
			time: 4,
			tokens: 800,
			api_calls: 1,
			api_cost: 2,
		},
	],
	budget: { time: 8, tokens: 1600, api_calls: 2, api_cost: 4 },
	maxPurchasePrice: 100,
	failurePenalty: 180,
});

const permit = optimizer.nextQueryPermit();
if (permit) {
	// Enforce all four permit ceilings before invoking the host tool.
	const decision = optimizer.observe(permit.merchantIndex, 92, {
		time: 3,
		tokens: 620,
		api_calls: 1,
		api_cost: 2,
	});
	console.log(decision.action);
}
```

## Reproduce the project

Prerequisites are Python 3.11 or newer, Node 22.12 or newer, and npm. The Makefile
creates and uses a local `.venv`.

```bash
make install
make build
make check
make site
```

- `make build` regenerates JSON, CSV, TeX, site data, and cross-language conformance
	vectors under `artifacts/`.
- `make check` runs Ruff, Python tests, project validation, package builds, npm tests,
	and npm package inspection.
- `make site` synchronizes verified artifacts and builds the static Astro explainer.

For local exploration, run `npm run dev --prefix site` with Node 22.12 or newer and
open `http://127.0.0.1:4321/`.

## Research status

The open-source release includes an exact hard-budget planner in Python and JavaScript,
an atomic Python permit ledger, commerce-native product and offer types, frozen-panel
exhaustive-oracle metrics, and offline endpoint-inventory screening. The npm package
matches the existing planner vectors but not the Python receipt lifecycle. Constraint
sensitivity and passing unit tests are implementation validation, not novel findings.

Three claims are preregistered. Pathwise permit safety remains a conjecture pending a
manuscript proof; agreement between the planned joint `(merchant, permit)` solver and
exhaustive enumeration remains open; and `MERCHANT-PERMIT-OPEN-001` asks whether joint
adaptive routing and permit allocation improves the preregistered outcome over the
strongest fixed feasible baseline on frozen held-out merchant panels at zero
violations. No empirical performance result is currently claimed.

Gate status:

| Gate | Status |
| --- | --- |
| Scope | Approved by Ahnaf prio on 2026-07-25 |
| Novelty | Pending |
| Design | Pending |
| Evidence | Pending |
| Release | Pending |

Only a human may approve a research gate.

## Repository layout

| Path | Purpose |
| --- | --- |
| `packages/python/` | Canonical Python optimizer, permit ledger, and evidence source |
| `packages/javascript/` | Browser-safe npm optimizer and shared conformance tests |
| `data/ucp/` | Public-safe UCP inventory templates and snapshot documentation |
| `research/` | Question, avenues, claims, literature, and human gates |
| `artifacts/` | Deterministically generated evidence and conformance vectors |
| `paper/` | Claim-aware LaTeX manuscript |
| `site/` | Interactive Astro research explainer |
| `src/paperkit/` | Evidence, validation, publication, and release pipeline |

## Publication boundaries

- Scientific values originate in the canonical Python package and flow through
	`paperkit build`.
- The paper and site consume generated artifacts instead of reimplementing the model.
- Synthetic benchmark values are not presented as market estimates.
- An open claim is not presented as a finding.
- A release remains blocked until metadata is initialized, placeholders are removed,
	evidence is complete, and all human gates are approved.

## Documentation

- [Research question](research/question.md)
- [Research cycle](docs/research-cycle.md)
- [Claim taxonomy](docs/claim-taxonomy.md)
- [Publication and release](docs/publication-and-release.md)
- [UCP input data](data/ucp/README.md)
- [Contributing](CONTRIBUTING.md)

The interactive explainer is configured for
[GitHub Pages](https://ahnafyy.github.io/autonomous-merchant-search-under-constraints/).
