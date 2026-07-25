export interface ExpectedDistinct {
  numerator: bigint;
  denominator: bigint;
  value: number;
}

export function expectedDistinctChoices(options: number, choices: number): ExpectedDistinct;