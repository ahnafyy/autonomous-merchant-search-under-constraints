/**
 * Enforceable resource accounting for a shopping agent's tool loop.
 *
 * Reserve the full permit before dispatching a call, then reconcile once the call
 * returns. Capacity known to be unused is reclaimed; capacity whose true usage is
 * unknown, because the call was cancelled or truncated, is charged at the full
 * permit. Overruns are therefore prevented rather than detected afterwards.
 *
 * Mirrors the canonical Python `PermitLedger`.
 */

const RESOURCE_FIELDS = ["time", "tokens", "api_calls", "api_cost"];
const EXECUTION_STATUSES = new Set([
  "completed",
  "timeout",
  "truncated",
  "cancelled",
  "failed",
]);

function nonNegativeInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new TypeError(`${name} must be a non-negative integer`);
  }
  return value;
}

/** Normalise a resource mapping, defaulting absent resources to zero. */
export function resourceVector(values = {}) {
  const vector = {};
  for (const field of RESOURCE_FIELDS) {
    vector[field] = nonNegativeInteger(values?.[field] ?? 0, field);
  }
  return vector;
}

function addVectors(left, right) {
  const total = {};
  for (const field of RESOURCE_FIELDS) total[field] = left[field] + right[field];
  return total;
}

function subtractVectors(left, right) {
  const difference = {};
  for (const field of RESOURCE_FIELDS) {
    const value = left[field] - right[field];
    if (value < 0) throw new RangeError("resource subtraction would go negative");
    difference[field] = value;
  }
  return difference;
}

function fitsWithin(candidate, limit) {
  return RESOURCE_FIELDS.every((field) => candidate[field] <= limit[field]);
}

export class PermitLedger {
  #token = Symbol("permit-ledger");
  #initial;
  #remaining;
  #charged;
  #active = new Map();
  #nextId = 1;

  constructor(budget) {
    this.#initial = resourceVector(budget);
    this.#remaining = this.#initial;
    this.#charged = resourceVector();
  }

  get initialBudget() {
    return { ...this.#initial };
  }

  get remainingBudget() {
    return { ...this.#remaining };
  }

  get chargedUsage() {
    return { ...this.#charged };
  }

  /** Deduct the whole permit up front, or fail without changing the ledger. */
  reserve(merchantId, permit) {
    if (typeof merchantId !== "string" || merchantId.length === 0) {
      throw new TypeError("merchantId must be a non-empty string");
    }
    const parsed = resourceVector(permit);
    if (!fitsWithin(parsed, this.#remaining)) {
      throw new RangeError("permit exceeds the remaining budget");
    }
    const reservation = {
      reservationId: this.#nextId,
      merchantId,
      permit: parsed,
      ledgerToken: this.#token,
    };
    this.#remaining = subtractVectors(this.#remaining, parsed);
    this.#active.set(reservation.reservationId, reservation);
    this.#nextId += 1;
    return reservation;
  }

  /**
   * Settle a reservation. `exactResources` lists the resources whose usage is
   * known; everything else is charged at the permit.
   */
  reconcile(reservation, { usage, exactResources = RESOURCE_FIELDS, status = "completed" }) {
    if (!reservation || reservation.ledgerToken !== this.#token) {
      throw new RangeError("reservation belongs to a different permit ledger");
    }
    const active = this.#active.get(reservation.reservationId);
    if (active === undefined || active !== reservation) {
      throw new RangeError("reservation is unknown or already reconciled");
    }
    if (!EXECUTION_STATUSES.has(status)) {
      throw new RangeError(`unsupported execution status: ${status}`);
    }
    const unknown = [...exactResources].filter((field) => !RESOURCE_FIELDS.includes(field));
    if (unknown.length > 0) {
      throw new RangeError(`unknown exact resources: ${unknown.sort().join(", ")}`);
    }
    const observed = resourceVector(usage);
    if (!fitsWithin(observed, reservation.permit)) {
      throw new RangeError("observed usage exceeds the reserved permit");
    }

    const exact = new Set(exactResources);
    const charged = {};
    for (const field of RESOURCE_FIELDS) {
      charged[field] = exact.has(field) ? observed[field] : reservation.permit[field];
    }
    const reclaimed = subtractVectors(reservation.permit, charged);
    this.#remaining = addVectors(this.#remaining, reclaimed);
    this.#charged = addVectors(this.#charged, charged);
    this.#active.delete(reservation.reservationId);

    return {
      reservationId: reservation.reservationId,
      merchantId: reservation.merchantId,
      status,
      observedUsage: observed,
      chargedUsage: charged,
      reclaimed,
      remainingBudget: { ...this.#remaining },
    };
  }
}
