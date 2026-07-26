# Research Question

Complete this charter before approving the scope gate. Prefer a small mechanism
that can be inspected, calculated, and falsified over a broad topic description.

## Phenomenon

An autonomous shopper must often buy before it can inspect every merchant. Each
merchant query consumes elapsed time, model tokens, and an API call, while the price
and availability revealed by that query may change before a later return. Continuing
can discover a lower price, but it can also exhaust a resource budget or turn a
currently purchasable offer into terminal purchase failure. Treating every combination
of constraints as a separate problem obscures the common online stopping mechanism.

## Research Question

How should an autonomous shopping agent behave under actual hard time, token, API,
and purchase-price constraints when merchant prices and availability are unknown
until queried and rejected offers cannot be recalled?

## Minimal Benchmark

An episode contains a known finite set of unqueried merchants. Calls are sequential,
and the policy chooses the next feasible merchant adaptively. An externally fixed
order is retained as a control. Querying merchant \(t\) consumes a declared resource vector containing
elapsed time, tokens, API-call count, and optional monetary API cost, then reveals
current availability and the landed price of one exact SKU. Before execution, each
call receives enforceable limits for elapsed time, tokens, API calls, and API spend.
Realized usage may be lower and is reconciled afterward; uncertain, correlated, and
misspecified usage is part of the primary evaluation.

If the item is available, the policy must accept the offer immediately or reject it
forever. An unavailable offer forces continuation when another feasible call exists.
Rejected offers cannot be recalled because their price or availability may change.
The episode ends with a purchase, an exhausted merchant sequence, or a resource limit.
Ending without acceptance is an explicit purchase failure rather than a zero-cost
outcome.

The optimizer minimizes purchase loss and purchase failure subject to hard episode
budgets. Resource limits are never traded away in the objective. The host must enforce
the issued timeout, maximum-token, call, and spend permit before invoking a model or
merchant tool.

The smallest operational domain uses a finite merchant horizon with discrete
merchant-specific price and stockout forecasts plus decomposed resource costs. Exact
backward induction must agree with exhaustive policy enumeration on reduced horizons
before larger forecast sets or numerical experiments are admitted.

## Comparisons And Controls

- Accept the first available offer as the resource-minimal baseline.
- Split each remaining resource equally across remaining merchants.
- Reserve worst-case resources for every remaining call.
- Use a myopic value-of-information policy that queries only when its next call fits.
- Compare fixed-depth and fixed-threshold rules with horizon-aware and
	resource-aware stopping policies.
- Use a clairvoyant trace oracle as an unattainable offline bound, with purchase
	failure scored under the same objective as online policies.
- Under an explicitly declared synthetic generator, compare with finite-horizon
	dynamic programming that knows that generator; do not label it distribution-free.
- Compare adaptive merchant selection with externally fixed and uniformly random
	orders to isolate gains from routing rather than stopping alone.
- Score a never-accept policy to verify that terminal failure handling prevents it
	from appearing artificially optimal.

## Contribution Hypothesis

The selected hypothesis is that adaptive pre-call permit allocation can improve
purchase loss or purchase success over deployable fixed-split and myopic baselines
while maintaining zero hard-budget violations under uncertain realized query usage.
The result is not established until paired held-out traces include planner overhead,
timeouts, truncation, forecast error, and terminal purchase failure.

## Falsifiers

- Reject the avenue if adaptive permits do not improve purchase loss or success over
	the strongest feasible baseline at zero violations.
- Reject gains that disappear on paired held-out traces, after charging planner
	latency, or under reasonable usage-forecast misspecification.
- Treat any total-budget overrun as a correctness failure, not a performance tradeoff.
- Resource-aware policies should reduce to their unconstrained counterparts when all
	budgets are nonbinding; failure to do so indicates a model or implementation error.
- Compare against policies indexed only by the number of remaining merchants. If they
	explain all apparent gains, resource identity is not the operative mechanism.
- Evaluate common traces and seeds across policies. If rankings disappear under this
	paired control, sampling noise rather than the constraints caused the pattern.
- Seek instances on which every deterministic routing and threshold rule has poor
	price or failure performance; such counterexamples would limit any
	distribution-free optimality claim.

## Non-Goals

- Learning reusable merchant price or availability distributions across shopping
	sessions; the motivating environment is nonstationary.
- Issuing parallel calls or revisiting a rejected offer in the base benchmark.
- Strategic merchant behavior, personalized-price responses, browser automation, and
	production API reliability engineering.
- Claiming that synthetic stochastic generators describe real merchant markets
	without separately collected evidence.
- Multi-product baskets, substitutions, and multi-attribute utility in the core
	hard-budget analysis. Shipping, delivery, trust, returns, and condition are a
	labeled second-stage extension.
