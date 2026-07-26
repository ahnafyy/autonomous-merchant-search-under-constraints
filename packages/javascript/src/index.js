const RESOURCE_FIELDS = ["time", "tokens", "api_calls", "api_cost"];
const POLICIES = new Set(["accept_first", "fixed_threshold", "resource_aware_threshold"]);

function nonNegativeInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new RangeError(`${name} must be a non-negative integer`);
  }
  return value;
}

function parseOffer(value) {
  if (typeof value?.available !== "boolean") {
    throw new TypeError("offer availability must be boolean");
  }
  let price = value.price;
  if (value.available) {
    price = nonNegativeInteger(price, "available offer price");
    if (price === 0) {
      throw new RangeError("available offer price must be positive");
    }
  } else if (price !== null && price !== undefined) {
    throw new RangeError("unavailable offers must not have a price");
  }
  return {
    available: value.available,
    price: value.available ? price : null,
    resources: {
      time: nonNegativeInteger(value.time ?? 0, "offer time"),
      tokens: nonNegativeInteger(value.tokens ?? 0, "offer tokens"),
      api_calls: nonNegativeInteger(value.api_calls ?? 1, "offer api_calls"),
      api_cost: nonNegativeInteger(value.api_cost ?? 0, "offer api_cost"),
    },
  };
}

function parseBudget(value) {
  return Object.fromEntries(RESOURCE_FIELDS.map((field) => [
    field,
    value?.[field] == null ? null : nonNegativeInteger(value[field], field),
  ]));
}

function addResources(left, right) {
  return Object.fromEntries(RESOURCE_FIELDS.map((field) => [field, left[field] + right[field]]));
}

function withinBudget(resources, budget) {
  return RESOURCE_FIELDS.every(
    (field) => budget[field] === null || resources[field] <= budget[field],
  );
}

function parseForecast(value) {
  if (!Array.isArray(value?.price_weights) || value.price_weights.length === 0) {
    throw new TypeError("price_weights must be a non-empty array");
  }
  const priceWeights = value.price_weights.map((outcome) => ({
    price: positiveInteger(outcome?.price, "forecast price"),
    weight: positiveInteger(outcome?.weight, "forecast weight"),
  }));
  const unavailableWeight = nonNegativeInteger(
    value.unavailable_weight ?? 0,
    "unavailable_weight",
  );
  return {
    price_weights: priceWeights,
    unavailable_weight: unavailableWeight,
    total_weight: unavailableWeight + priceWeights.reduce((total, row) => total + row.weight, 0),
    resources: Object.fromEntries(RESOURCE_FIELDS.map((field) => [
      field,
      nonNegativeInteger(value[field] ?? (field === "api_calls" ? 1 : 0), field),
    ])),
  };
}

function positiveInteger(value, name) {
  const parsed = nonNegativeInteger(value, name);
  if (parsed === 0) throw new RangeError(`${name} must be positive`);
  return parsed;
}

export function planShoppingDecision({
  merchants,
  budget,
  observedPrice,
  maxPurchasePrice,
  failurePenalty,
  observedMerchantIndex = 0,
}) {
  if (!Array.isArray(merchants) || merchants.length === 0) {
    throw new TypeError("merchants must be a non-empty array");
  }
  const forecasts = merchants.map(parseForecast);
  const resources = Object.fromEntries(RESOURCE_FIELDS.map((field) => [
    field,
    nonNegativeInteger(budget?.[field] ?? 0, `${field} budget`),
  ]));
  const observed = positiveInteger(observedPrice, "observedPrice");
  const priceCap = positiveInteger(maxPurchasePrice, "maxPurchasePrice");
  const penalty = nonNegativeInteger(failurePenalty, "failurePenalty");
  if (!Number.isInteger(observedMerchantIndex)
      || observedMerchantIndex < 0
      || observedMerchantIndex >= forecasts.length) {
    throw new RangeError("observedMerchantIndex is outside the merchant set");
  }

  const usage = (index) => forecasts[index].resources;
  const fits = (index, remaining) => RESOURCE_FIELDS.every(
    (field) => usage(index)[field] <= remaining[field],
  );
  const subtract = (index, remaining) => Object.fromEntries(RESOURCE_FIELDS.map((field) => [
    field,
    remaining[field] - usage(index)[field],
  ]));
  const memo = new Map();
  const solve = (remainingMerchants, remaining) => {
    const key = `${remainingMerchants.join(",")}|${RESOURCE_FIELDS.map((field) => remaining[field]).join(",")}`;
    const cached = memo.get(key);
    if (cached) return cached;
    const candidates = [];
    for (const index of remainingMerchants) {
      if (!fits(index, remaining)) continue;
      const merchant = forecasts[index];
      const afterQuery = subtract(index, remaining);
      const future = remainingMerchants.filter((candidate) => candidate !== index);
      const continuation = solve(future, afterQuery).value;
      let expected = merchant.unavailable_weight * continuation;
      for (const outcome of merchant.price_weights) {
        const accepted = outcome.price <= priceCap
          ? Math.min(outcome.price, continuation)
          : continuation;
        expected += outcome.weight * accepted;
      }
      candidates.push({ value: expected / merchant.total_weight, index });
    }
    const result = candidates.length === 0
      ? { value: penalty, index: null }
      : candidates.sort((left, right) => left.value - right.value || left.index - right.index)[0];
    memo.set(key, result);
    return result;
  };

  if (!fits(observedMerchantIndex, resources)) {
    throw new RangeError("budget cannot query the observed merchant");
  }
  const afterObservation = subtract(observedMerchantIndex, resources);
  const remainingIndices = forecasts
    .map((_, index) => index)
    .filter((index) => index !== observedMerchantIndex);
  const continuation = solve(remainingIndices, afterObservation);
  const initial = solve(forecasts.map((_, index) => index), resources);
  const feasibleNextMerchants = remainingIndices.filter((index) => fits(index, afterObservation));
  const reservationPrice = Math.min(priceCap, continuation.value);
  const action = observed <= reservationPrice
    ? "buy"
    : continuation.index === null
      ? "reject_without_feasible_query"
      : "continue";
  return {
    action,
    first_merchant_index: initial.index,
    reservation_price: reservationPrice,
    continuation_value: continuation.value,
    next_merchant_index: continuation.index,
    feasible_next_merchants: feasibleNextMerchants,
    remaining_after_observation: afterObservation,
  };
}

export class AutonomousShoppingOptimizer {
  constructor({ merchants, budget, maxPurchasePrice, failurePenalty }) {
    if (!Array.isArray(merchants) || merchants.length === 0) {
      throw new TypeError("merchants must be a non-empty array");
    }
    this.merchants = merchants.map((merchant) => ({ ...merchant }));
    this.remainingBudget = Object.fromEntries(RESOURCE_FIELDS.map((field) => [
      field,
      nonNegativeInteger(budget?.[field] ?? 0, `${field} budget`),
    ]));
    this.maxPurchasePrice = positiveInteger(maxPurchasePrice, "maxPurchasePrice");
    this.failurePenalty = nonNegativeInteger(failurePenalty, "failurePenalty");
    this.unqueriedMerchants = this.merchants.map((_, index) => index);
    this.terminal = false;
  }

  nextQuery() {
    if (this.terminal || this.unqueriedMerchants.length === 0) return null;
    const localMerchants = this.unqueriedMerchants.map((index) => this.merchants[index]);
    const plan = planShoppingDecision({
      merchants: localMerchants,
      budget: this.remainingBudget,
      observedPrice: 1,
      maxPurchasePrice: this.maxPurchasePrice,
      failurePenalty: this.failurePenalty,
    });
    return plan.first_merchant_index === null
      ? null
      : this.unqueriedMerchants[plan.first_merchant_index];
  }

  nextQueryPermit() {
    const merchantIndex = this.nextQuery();
    if (merchantIndex === null) return null;
    const merchant = this.merchants[merchantIndex];
    return {
      merchantIndex,
      timeout: Math.min(this.remainingBudget.time, merchant.time ?? 0),
      maxTokens: Math.min(this.remainingBudget.tokens, merchant.tokens ?? 0),
      maxApiCalls: Math.min(this.remainingBudget.api_calls, merchant.api_calls ?? 1),
      maxApiSpend: Math.min(this.remainingBudget.api_cost, merchant.api_cost ?? 0),
    };
  }

  observe(merchantIndex, observedPrice, actualResources = null) {
    if (this.terminal) throw new Error("shopping session is already terminal");
    if (!this.unqueriedMerchants.includes(merchantIndex)) {
      throw new RangeError("merchant has already been queried or is unknown");
    }
    const price = observedPrice == null
      ? null
      : positiveInteger(observedPrice, "observedPrice");
    const source = actualResources ?? this.merchants[merchantIndex];
    const usage = Object.fromEntries(RESOURCE_FIELDS.map((field) => [
      field,
      nonNegativeInteger(source?.[field] ?? (field === "api_calls" ? 1 : 0), `actual ${field}`),
    ]));
    if (RESOURCE_FIELDS.some((field) => usage[field] > this.remainingBudget[field])) {
      throw new RangeError("actual query resources exceed the remaining budget");
    }
    for (const field of RESOURCE_FIELDS) this.remainingBudget[field] -= usage[field];
    this.unqueriedMerchants = this.unqueriedMerchants.filter((index) => index !== merchantIndex);

    const placeholder = {
      ...this.merchants[merchantIndex],
      time: 0,
      tokens: 0,
      api_calls: 0,
      api_cost: 0,
    };
    const localMerchants = [
      placeholder,
      ...this.unqueriedMerchants.map((index) => this.merchants[index]),
    ];
    const plan = planShoppingDecision({
      merchants: localMerchants,
      budget: this.remainingBudget,
      observedPrice: price ?? this.maxPurchasePrice + 1,
      maxPurchasePrice: this.maxPurchasePrice,
      failurePenalty: this.failurePenalty,
    });
    const nextMerchantIndex = plan.next_merchant_index === null
      ? null
      : this.unqueriedMerchants[plan.next_merchant_index - 1];
    let action;
    let reason;
    if (price !== null && price <= plan.reservation_price) {
      action = "buy";
      reason = "offer_is_admissible_and_no_worse_than_continuation";
      this.terminal = true;
    } else if (nextMerchantIndex !== null) {
      action = "continue";
      reason = "offer_unavailable_or_future_search_has_lower_expected_loss";
    } else {
      action = "reject_without_feasible_query";
      reason = price !== null && price > this.maxPurchasePrice
        ? "offer_exceeds_hard_price_cap_and_no_query_is_feasible"
        : "no_purchase_and_no_query_is_feasible";
      this.terminal = true;
    }
    return {
      action,
      observedMerchantIndex: merchantIndex,
      observedPrice: price,
      reservationPrice: price === null ? null : plan.reservation_price,
      nextMerchantIndex: action === "buy" ? null : nextMerchantIndex,
      remainingBudget: { ...this.remainingBudget },
      reason,
    };
  }
}

export const ShoppingAgentMiddleware = AutonomousShoppingOptimizer;

export function simulatePolicy(offers, policy, threshold = null, budget = null) {
  if (!Array.isArray(offers)) {
    throw new TypeError("offers must be an array");
  }
  if (!POLICIES.has(policy)) {
    throw new RangeError(`unsupported policy: ${policy}`);
  }
  if (policy !== "accept_first") {
    threshold = nonNegativeInteger(threshold, "threshold");
  }

  const parsedOffers = offers.map(parseOffer);
  const parsedBudget = parseBudget(budget);
  let resources = { time: 0, tokens: 0, api_calls: 0, api_cost: 0 };
  let queries = 0;

  for (const [index, offer] of parsedOffers.entries()) {
    const nextResources = addResources(resources, offer.resources);
    if (!withinBudget(nextResources, parsedBudget)) {
      return {
        purchased: false,
        accepted_price: null,
        accepted_index: null,
        queries,
        resources,
        terminal_reason: "resource_exhausted",
      };
    }

    resources = nextResources;
    queries += 1;
    if (!offer.available) {
      continue;
    }

    let shouldAccept = policy === "accept_first" || offer.price <= threshold;
    if (policy === "resource_aware_threshold") {
      const nextOffer = parsedOffers[index + 1];
      const hasFeasibleNextCall = nextOffer !== undefined
        && withinBudget(addResources(resources, nextOffer.resources), parsedBudget);
      shouldAccept ||= !hasFeasibleNextCall;
    }
    if (shouldAccept) {
      return {
        purchased: true,
        accepted_price: offer.price,
        accepted_index: index,
        queries,
        resources,
        terminal_reason: "purchased",
      };
    }
  }

  return {
    purchased: false,
    accepted_price: null,
    accepted_index: null,
    queries,
    resources,
    terminal_reason: "merchants_exhausted",
  };
}