# Autonomous Shopping Optimizer

Hard-budget planning middleware for autonomous shopping agents.

The optimizer decides whether an agent should buy the current offer, continue
searching, or stop without a purchase. It also selects the next merchant and issues
enforceable per-call limits for elapsed time, model tokens, API calls, and API spend.
The controller admits only calls and purchases that fit the remaining limits.

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

The canonical Python implementation generates deterministic evidence and conformance
vectors. The browser-safe npm implementation must pass those same vectors.

## Agent loop

```text
optimizer.next_query_permit()
						|
						v
host enforces timeout / token / call / spend ceilings
						|
						v
host invokes the LLM or merchant tool
						|
						v
optimizer.observe(merchant, price, actual resource use)
						|
						v
buy | continue | reject_without_feasible_query
```

The pre-call enforcement step is essential. Rejecting an overrun after a call has
already completed cannot preserve a hard budget.

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

permit = optimizer.next_query_permit()
if permit is not None:
		# Apply permit.timeout and permit.max_tokens to the host call before dispatch.
		decision = optimizer.observe(
				permit.merchant_index,
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

The Python distribution is `autonomous-shopping-optimizer`; its public import is
`autonomous_shopping_optimizer`.

## JavaScript usage

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

The software currently demonstrates an exact hard-budget optimizer and matching
Python/JavaScript middleware. Constraint sensitivity is implementation validation,
not a novel result.

The registered open claim, `MERCHANT-PERMIT-OPEN-001`, asks whether adaptive pre-call
permit allocation improves purchase loss or purchase success over fixed-split and
myopic feasible baselines while maintaining zero hard-budget violations under
uncertain realized query usage. The held-out usage traces and comparative evaluation
needed to resolve that claim have not yet been completed.

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
| `packages/python/` | Canonical optimizer and Python middleware |
| `packages/javascript/` | Browser-safe npm optimizer and conformance tests |
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
- [Contributing](CONTRIBUTING.md)

The interactive explainer is configured for
[GitHub Pages](https://ahnafyy.github.io/autonomous-merchant-search-under-constraints/).
