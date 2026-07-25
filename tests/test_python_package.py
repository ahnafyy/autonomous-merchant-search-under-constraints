from __future__ import annotations

import json
from pathlib import Path

import pytest
from example_study import expected_distinct_choices

from paperkit.pipeline import build

ROOT = Path(__file__).resolve().parents[1]


def test_python_package_matches_generated_conformance(tmp_path: Path) -> None:
    artifacts = build(ROOT, tmp_path / "artifacts")
    vectors = json.loads(
        (artifacts / "conformance" / "expected-distinct.json").read_text(encoding="utf-8")
    )

    for vector in vectors["cases"]:
        result = expected_distinct_choices(**vector["input"])
        assert result.as_dict() == vector["expected"]
    for vector in vectors["errors"]:
        with pytest.raises(ValueError):
            expected_distinct_choices(**vector["input"])