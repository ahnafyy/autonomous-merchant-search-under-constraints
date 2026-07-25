function greatestCommonDivisor(left, right) {
  while (right !== 0n) {
    [left, right] = [right, left % right];
  }
  return left;
}

export function expectedDistinctChoices(options, choices) {
  if (!Number.isInteger(options) || !Number.isInteger(choices)) {
    throw new TypeError("options and choices must be integers");
  }
  if (options <= 0 || choices < 0) {
    throw new RangeError("options must be positive and choices must be non-negative");
  }
  const optionCount = BigInt(options);
  const denominator = optionCount ** BigInt(choices);
  const numerator = optionCount * (denominator - (optionCount - 1n) ** BigInt(choices));
  const divisor = greatestCommonDivisor(numerator, denominator);
  const reducedNumerator = numerator / divisor;
  const reducedDenominator = denominator / divisor;
  return {
    numerator: reducedNumerator,
    denominator: reducedDenominator,
    value: Number(reducedNumerator) / Number(reducedDenominator),
  };
}