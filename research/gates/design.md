# Design Gate

Approve only when assumptions, timing, controls, outcomes, boundary cases,
random seeds, tolerances, and the cheapest decisive checks are written down.
Every planned public claim should have a claim ID before the main analysis begins.

## Prepared Material

- Registered claim: `MERCHANT-PERMIT-OPEN-001`, currently `open`.
- Unit of evaluation: a complete shopping episode replayed on the same merchant and
	resource-usage trace for every policy.
- Treatments: adaptive permits, equal split, worst-case reserve, myopic feasible, and
	fixed-depth policies; the clairvoyant trace oracle is an unattainable bound.
- Outcomes: purchase loss, purchase success, terminal failure, timeout, truncation,
	planner latency, and hard-budget violations.
- Correctness rule: any episode-level time, token, API-call, API-spend, or purchase-cap
	violation is a failure, not an objective tradeoff.
- Robustness axes: total budgets, correlated usage, held-out usage, and forecast
	misspecification.

## Approval Blockers

- The trace source, train/calibration/test split, random seeds, and sample sizes are not
	yet registered.
- Permit cancellation and timeout semantics need explicit benchmark definitions.

Record approval in `status.yml`. Agents may prepare this gate but may not approve it.
