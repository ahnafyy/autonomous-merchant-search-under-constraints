import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { expectedDistinctChoices } from "../src/index.js";

const vectors = JSON.parse(
  await readFile(new URL("../../../artifacts/conformance/expected-distinct.json", import.meta.url)),
);

for (const vector of vectors.cases) {
  test(`conforms for ${vector.input.options} options and ${vector.input.choices} choices`, () => {
    const result = expectedDistinctChoices(vector.input.options, vector.input.choices);
    assert.deepEqual({
      numerator: Number(result.numerator),
      denominator: Number(result.denominator),
      value: result.value,
    }, vector.expected);
  });
}

for (const vector of vectors.errors) {
  test(`rejects ${JSON.stringify(vector.input)}`, () => {
    assert.throws(() => expectedDistinctChoices(vector.input.options, vector.input.choices));
  });
}