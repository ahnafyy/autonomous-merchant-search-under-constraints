import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  acceptanceFraction,
  affordableQueries,
  closedFormReservationPrice,
  secretarySampleSize,
} from "../src/index.js";

const vectors = JSON.parse(
  await readFile(new URL("../../../artifacts/conformance/closed-form.json", import.meta.url)),
);

for (const [index, vector] of vectors.acceptance_fraction_cases.entries()) {
  test(`acceptance fraction matches Python for k=${index}`, () => {
    const observed = acceptanceFraction(vector.input.affordable_queries);
    assert.ok(
      Math.abs(observed - vector.expected.value) <= vectors.tolerance,
      `expected ${vector.expected.value}, received ${observed}`,
    );
  });
}

for (const [index, vector] of vectors.affordable_queries_cases.entries()) {
  test(`affordable queries matches Python for case ${index + 1}`, () => {
    // A horizon is a whole number of queries, so this must agree exactly.
    assert.equal(
      affordableQueries(vector.input.remaining, vector.input.per_query),
      vector.expected,
    );
  });
}

for (const [index, vector] of vectors.reservation_threshold_cases.entries()) {
  test(`closed-form threshold matches Python for case ${index + 1}`, () => {
    const observed = closedFormReservationPrice(
      vector.input.price_floor,
      vector.input.price_ceiling,
      vector.input.affordable_queries,
    );
    assert.ok(
      Math.abs(observed - vector.expected.value) <= vectors.tolerance,
      `expected ${vector.expected.value}, received ${observed}`,
    );
  });
}

for (const [index, vector] of vectors.secretary_sample_size_cases.entries()) {
  test(`secretary sample size matches Python for case ${index + 1}`, () => {
    assert.equal(secretarySampleSize(vector.input.candidate_count), vector.expected);
  });
}

test("the binding resource sets the horizon", () => {
  const remaining = { time: 30, tokens: 8000, api_calls: 6, api_cost: 12 };
  const perQuery = { time: 4, tokens: 900, api_calls: 1, api_cost: 2 };

  assert.equal(affordableQueries(remaining, perQuery), 6);
});

test("a query consuming nothing is rejected", () => {
  assert.throws(() => affordableQueries({ api_calls: 5 }, {}), RangeError);
});

test("the threshold rises as the budget drains", () => {
  const thresholds = [0, 1, 2, 3, 4].map((k) => closedFormReservationPrice(8000, 12000, k));

  assert.equal(thresholds[0], 12000);
  for (let index = 1; index < thresholds.length; index += 1) {
    assert.ok(thresholds[index] < thresholds[index - 1]);
  }
});
