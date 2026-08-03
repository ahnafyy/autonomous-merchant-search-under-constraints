# Design Gate

Approve only when assumptions, timing, controls, outcomes, boundary cases,
random seeds, tolerances, and the cheapest decisive checks are written down.
Every planned public claim should have a claim ID before the main analysis begins.

## Prepared Material

- Registered claims: pathwise safety is a conjecture; joint-solver correctness and
  held-out UCP performance remain open.
- Unit of evaluation: a complete shopping episode replayed on the same merchant and
	resource-usage trace for every policy.
- Treatments: constrained ARVP, the same learned policy under nonbinding budgets,
  equal split, tuned fixed split, worst-case reserve, myopic feasible, fixed depth,
  routing and permit ablations, and an exhaustive frozen-panel oracle.
- Outcomes: purchase loss, purchase success, exact and tolerance-based oracle hit,
  item-price regret, savings captured, calls or resources needed to capture 90% and
  95% of exhaustive savings, terminal failure, timeout, truncation, planner latency,
  and hard-budget violations.
- Correctness rule: any episode-level time, token, API-call, API-spend, or purchase-cap
	violation is a failure, not an objective tradeoff.
- Robustness axes: total budgets, correlated usage, held-out usage, and forecast
	misspecification.
- Evidence decomposition: constrained policy versus its nonbinding-budget counterpart
	measures the budget effect; nonbinding policy versus exhaustive panel oracle measures
	routing and stopping error; constrained policy versus oracle measures total regret.
- Offer semantics: no-recall is primary; held-offer behavior is reported separately.
- Data boundary: ShopSavvy and other historical price datasets are excluded. UCP
	calibration rounds and chronologically later frozen panels are the only planned
	empirical source.

## Approval Blockers

- A declared-capability merchant panel candidate now exists (240 domains, live
	UCP `search_catalog` probing, 2026-08-02), but case-by-case verified
	permission, exact-SKU overlap cohort sampling depth beyond the current
	pagination-limited sample, round cadence, and sample sizes are not yet
	registered.
- The calibration/test cutoff, frozen snapshot hashes, budget grid, primary outcome,
	and paired uncertainty procedure are not yet registered.
- Live exhaustive shadow collection remains conditional on endpoint permission and
	rate limits; frozen-panel oracle evaluation is mandatory.
- Permit enforcement adapters still need to demonstrate timeout, stream/token limits,
	cancellation, and conservative reconciliation against fixtures and a pilot.

Record approval in `status.yml`. Agents may prepare this gate but may not approve it.
