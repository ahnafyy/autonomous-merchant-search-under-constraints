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

Can an autonomous shopping agent jointly choose which UCP merchant to query and what
enforceable resource permit to issue so that it captures more exhaustive-search value
than fixed feasible allocation under hard episode budgets?

## Minimal Benchmark

An episode contains one exact SKU and a known finite set of eligible UCP merchants.
Calls are sequential, and the policy chooses the next feasible merchant and a permit
vector adaptively. Querying merchant \(t\) consumes elapsed time, response or model
tokens, API-call count, and genuine monetary API cost when the protocol exposes it,
then reveals current availability and item price. Landed price is used only when
shipping and tax are consistently observed. Before dispatch, the runtime atomically
reserves enforceable limits for every active resource. Realized usage may be lower;
known unused capacity is reclaimed, while usage left unknown by cancellation is
charged conservatively at its permit.

Early randomized UCP rounds are calibration data. Chronologically later rounds are
frozen as held-out merchant panels before policy comparison. Every policy is replayed
against the same latent panel. Unqueried merchant outcomes remain hidden from online
policies, preventing the exhaustive oracle from leaking into routing or stopping.

In the primary no-recall mode, an available offer must be accepted immediately or
rejected forever. A held-offer mode, evaluated separately as robustness, permits the
best observed offer to remain purchasable until episode termination. An unavailable
offer forces continuation when another feasible call exists. The episode ends with a
purchase, an exhausted merchant sequence, or a resource limit. Ending without
acceptance is an explicit purchase failure rather than a zero-cost outcome.

The optimizer minimizes purchase loss and purchase failure subject to hard episode
budgets. Resource limits are never traded away in the objective. The host must enforce
the issued timeout, maximum-token, call, and spend permit before invoking a model or
merchant tool.

The smallest operational domain uses a finite merchant horizon, a registered discrete
permit grid, merchant-specific price and stockout forecasts estimated without held-out
panels, and decomposed resource demand. Exact backward induction over joint
\((merchant, permit)\) actions must agree with exhaustive policy enumeration on
reduced horizons before larger forecast sets or numerical experiments are admitted.

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
- Compare adaptive routing with fixed permits and fixed routing with adaptive permits
	to isolate the contribution of permit sizing.
- Run the identical learned policy with nonbinding budgets to isolate the cost of hard
	constraints from routing and stopping error.
- Use an exhaustive held-out panel oracle to select the cheapest eligible available
	merchant. Keep this oracle hidden until an online episode terminates.
- Score a never-accept policy to verify that terminal failure handling prevents it
	from appearing artificially optimal.

Primary reports include purchase success, exact and tolerance-based oracle hit rates,
item-price regret, failure-penalized purchase loss, savings captured, hard-budget
violations, and the calls or resources needed to capture 90% and 95% of exhaustive
savings. Undefined savings denominators are counted separately rather than assigned
zero.

## Contribution Hypothesis

The selected hypothesis is that joint adaptive merchant and permit selection can
improve a preregistered purchase outcome over deployable fixed-split and myopic
baselines while maintaining zero hard-budget violations under uncertain realized UCP
usage. The result is not established until frozen held-out panels include planner
overhead, timeouts, truncation, forecast error, and terminal purchase failure.

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
- Require the constrained policy to match its nonbinding-budget counterpart whenever
	all resource limits are nonbinding.
- Report constrained-versus-nonbinding, nonbinding-versus-oracle, and
	constrained-versus-oracle comparisons separately; reject interpretations that call
	all three gaps a budget effect.
- Seek instances on which every deterministic routing and threshold rule has poor
	price or failure performance; such counterexamples would limit any
	distribution-free optimality claim.

## Non-Goals

- Online cross-episode bandit learning during the held-out test; forecasts are frozen
	from earlier calibration rounds.
- Issuing parallel calls or revisiting a rejected offer in the base benchmark.
- Strategic merchant behavior, personalized-price responses, browser automation, and
	production API reliability engineering.
- ShopSavvy or any other third-party historical price dataset.
- Claiming that synthetic stochastic generators describe real merchant markets
	without separately collected evidence.
- Multi-product baskets, substitutions, and multi-attribute utility in the core
	hard-budget analysis. Shipping, delivery, trust, returns, and condition are a
	labeled second-stage extension.
