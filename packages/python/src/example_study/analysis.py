from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Any


@dataclass(frozen=True)
class ExpectedDistinct:
    numerator: int
    denominator: int
    value: float

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def expected_distinct_choices(options: int, choices: int) -> ExpectedDistinct:
    """Return the exact expected occupied-option count for uniform independent choices."""
    if options <= 0 or choices < 0:
        raise ValueError("options must be positive and choices must be non-negative")
    exact = options * (1 - Fraction(options - 1, options) ** choices)
    return ExpectedDistinct(
        numerator=exact.numerator,
        denominator=exact.denominator,
        value=float(exact),
    )


def run_analysis(seed: int) -> dict[str, Any]:
    """Run the checked template fixture; replace this body for a real study."""
    options = 8
    choices = 4
    expected = expected_distinct_choices(options, choices)
    return {
        "choices": choices,
        "expected_distinct": expected.value,
        "expected_distinct_denominator": expected.denominator,
        "expected_distinct_numerator": expected.numerator,
        "options": options,
        "random_seed": seed,
    }