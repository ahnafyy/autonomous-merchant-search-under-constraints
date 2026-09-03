import assert from "node:assert/strict";
import test from "node:test";

import { PermitLedger, resourceVector } from "../src/index.js";

const BUDGET = { time: 30, tokens: 9000, api_calls: 6, api_cost: 12 };
const PERMIT = { time: 10, tokens: 3000, api_calls: 2, api_cost: 4 };

test("reserving deducts the whole permit up front", () => {
  const ledger = new PermitLedger(BUDGET);

  ledger.reserve("merchant-a", PERMIT);

  assert.deepEqual(ledger.remainingBudget, {
    time: 20,
    tokens: 6000,
    api_calls: 4,
    api_cost: 8,
  });
});

test("exact usage reclaims the unused capacity", () => {
  const ledger = new PermitLedger(BUDGET);
  const reservation = ledger.reserve("merchant-a", PERMIT);

  const result = ledger.reconcile(reservation, {
    usage: { time: 4, tokens: 1000, api_calls: 1, api_cost: 2 },
  });

  assert.deepEqual(result.chargedUsage, {
    time: 4,
    tokens: 1000,
    api_calls: 1,
    api_cost: 2,
  });
  assert.deepEqual(result.reclaimed, {
    time: 6,
    tokens: 2000,
    api_calls: 1,
    api_cost: 2,
  });
  assert.deepEqual(ledger.remainingBudget, {
    time: 26,
    tokens: 8000,
    api_calls: 5,
    api_cost: 10,
  });
});

test("censored usage is charged at the full permit", () => {
  const ledger = new PermitLedger(BUDGET);
  const reservation = ledger.reserve("merchant-a", PERMIT);

  // The call was cut off, so only the call count is known.
  const result = ledger.reconcile(reservation, {
    usage: { time: 4, tokens: 1000, api_calls: 1, api_cost: 2 },
    exactResources: ["api_calls"],
    status: "timeout",
  });

  assert.equal(result.chargedUsage.api_calls, 1);
  assert.equal(result.chargedUsage.time, PERMIT.time);
  assert.equal(result.chargedUsage.tokens, PERMIT.tokens);
  assert.equal(result.status, "timeout");
});

test("a permit larger than the remaining budget is refused atomically", () => {
  const ledger = new PermitLedger(BUDGET);
  const before = ledger.remainingBudget;

  assert.throws(() => ledger.reserve("merchant-a", { api_calls: 99 }), RangeError);
  assert.deepEqual(ledger.remainingBudget, before);
});

test("a reservation cannot be reconciled twice", () => {
  const ledger = new PermitLedger(BUDGET);
  const reservation = ledger.reserve("merchant-a", PERMIT);
  ledger.reconcile(reservation, { usage: { api_calls: 1 } });

  assert.throws(() => ledger.reconcile(reservation, { usage: { api_calls: 1 } }), RangeError);
});

test("usage above the permit is rejected", () => {
  const ledger = new PermitLedger(BUDGET);
  const reservation = ledger.reserve("merchant-a", PERMIT);

  assert.throws(
    () => ledger.reconcile(reservation, { usage: { api_calls: 5 } }),
    RangeError,
  );
});

test("a reservation from another ledger is refused", () => {
  const ledger = new PermitLedger(BUDGET);
  const other = new PermitLedger(BUDGET);
  const foreign = other.reserve("merchant-a", PERMIT);

  assert.throws(() => ledger.reconcile(foreign, { usage: { api_calls: 1 } }), RangeError);
});

test("cumulative charges never exceed the initial budget", () => {
  const ledger = new PermitLedger(BUDGET);
  for (let round = 0; round < 3; round += 1) {
    const reservation = ledger.reserve(`merchant-${round}`, { api_calls: 2, api_cost: 4 });
    ledger.reconcile(reservation, { usage: { api_calls: 1, api_cost: 1 }, status: "cancelled" });
  }

  const charged = ledger.chargedUsage;
  for (const field of Object.keys(charged)) {
    assert.ok(charged[field] <= BUDGET[field] ?? 0);
  }
});

test("resourceVector defaults absent resources to zero", () => {
  assert.deepEqual(resourceVector({ api_calls: 2 }), {
    time: 0,
    tokens: 0,
    api_calls: 2,
    api_cost: 0,
  });
});
