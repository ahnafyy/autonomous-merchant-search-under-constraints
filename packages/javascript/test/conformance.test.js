import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  AutonomousShoppingOptimizer,
  planShoppingDecision,
  reservationPrice,
  ShoppingAgentMiddleware,
  simulatePolicy,
} from "../src/index.js";

const vectors = JSON.parse(
  await readFile(new URL("../../../artifacts/conformance/merchant-search.json", import.meta.url)),
);

for (const vector of vectors.cases) {
  test(`conforms for ${vector.input.policy} with ${vector.input.offers.length} offers`, () => {
    const result = simulatePolicy(
      vector.input.offers,
      vector.input.policy,
      vector.input.threshold,
      vector.input.budget,
    );
    assert.deepEqual(result, vector.expected);
  });
}

for (const vector of vectors.errors) {
  test(`rejects ${JSON.stringify(vector.input)}`, () => {
    assert.throws(() => simulatePolicy(
      vector.input.offers,
      vector.input.policy,
      vector.input.threshold,
      vector.input.budget,
    ));
  });
}

for (const [index, vector] of vectors.planner_cases.entries()) {
  test(`conforms for hard-budget planner case ${index + 1}`, () => {
    const result = planShoppingDecision(vector.input);
    assert.equal(result.action, vector.expected.action);
    assert.ok(Math.abs(result.reservation_price - vector.expected.reservation_price) < 1e-10);
    assert.ok(Math.abs(result.continuation_value - vector.expected.continuation_value) < 1e-10);
    assert.equal(result.next_merchant_index, vector.expected.next_merchant_index);
    assert.deepEqual(result.feasible_next_merchants, vector.expected.feasible_next_merchants);
    assert.deepEqual(result.remaining_after_observation, vector.expected.remaining_after_observation);
  });
}

test("middleware routes, accounts, and stops across a host tool loop", () => {
  const middleware = new AutonomousShoppingOptimizer({
    merchants: [
      { price_weights: [{ price: 120, weight: 1 }], time: 2, tokens: 4 },
      { price_weights: [{ price: 70, weight: 1 }], time: 1, tokens: 2 },
    ],
    budget: { time: 3, tokens: 6, api_calls: 2, api_cost: 0 },
    maxPurchasePrice: 100,
    failurePenalty: 180,
  });
  assert.deepEqual(middleware.nextQueryPermit(), {
    merchantIndex: 0,
    timeout: 2,
    maxTokens: 4,
    maxApiCalls: 1,
    maxApiSpend: 0,
  });
  const unavailable = middleware.observe(0, null);
  assert.equal(unavailable.action, "continue");
  assert.equal(unavailable.nextMerchantIndex, 1);
  const decision = middleware.observe(1, 70);
  assert.equal(decision.action, "buy");
  assert.deepEqual(decision.remainingBudget, {
    time: 0,
    tokens: 0,
    api_calls: 0,
    api_cost: 0,
  });
  assert.throws(() => middleware.observe(1, 70));
});

test("legacy middleware name aliases the optimizer", () => {
  assert.equal(ShoppingAgentMiddleware, AutonomousShoppingOptimizer);
});

for (const [index, vector] of vectors.reservation_cases.entries()) {
  test(`conforms for reservation price case ${index + 1}`, () => {
    const observed = reservationPrice(
      vector.input.observed_price,
      vector.input.future_calibration,
      vector.input.stockout[0] / vector.input.stockout[1],
    );
    // Python computes this exactly in rationals; JavaScript uses doubles.
    assert.ok(
      Math.abs(observed - vector.expected.value) <= vectors.reservation_tolerance,
      `expected ${vector.expected.value}, received ${observed}`,
    );
  });
}

test("reservation price rejects an impossible stockout rate", () => {
  assert.throws(() => reservationPrice(100, [80], 1), RangeError);
});