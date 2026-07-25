from __future__ import annotations

import json
from pathlib import Path

from paperkit.pipeline import build

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_build_is_deterministic_and_claims_pass(tmp_path: Path) -> None:
    first = build(ROOT, tmp_path / "first")
    second = build(ROOT, tmp_path / "second")

    assert _snapshot(first) == _snapshot(second)
    claim_results = json.loads((first / "claim-results.json").read_text(encoding="utf-8"))
    assert claim_results["claims"][0]["passed"] is True
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["all_executable_claims_passed"] is True
    assert "results.json" in manifest["files"]
    assert "conformance/expected-distinct.json" in manifest["files"]
    site_data = json.loads((first / "site-data.json").read_text(encoding="utf-8"))
    assert site_data["results"]["expected_distinct"] == 3.310546875
    assert site_data["claims"][0]["id"] == "EXAMPLE-COMPUTATION-001"
    assert site_data["packages"]["python"]["distribution"] == "example-study"
    assert site_data["packages"]["javascript"]["name"] == "@example/example-study"
    metadata = (first / "tables" / "project_metadata.tex").read_text(encoding="utf-8")
    assert "\\newcommand{\\PaperTitle}" in metadata
    claim_table = (first / "tables" / "claim_status.tex").read_text(encoding="utf-8")
    assert "EXAMPLE-COMPUTATION-001" in claim_table


def test_generated_tex_can_be_staged(tmp_path: Path) -> None:
    from paperkit.paper import stage_generated_files

    project = tmp_path / "project"
    project.mkdir()
    build(ROOT, project / "artifacts")
    (project / "paper" / "generated").mkdir(parents=True)
    (project / "artifacts" / "figures").mkdir()
    (project / "artifacts" / "figures" / "fixture.pdf").write_bytes(b"figure")
    for name in ("project_metadata.tex", "result_macros.tex", "claim_status.tex"):
        source = project / "artifacts" / "tables" / name
        assert source.is_file()
    project_generated = stage_generated_files(project)
    assert (project_generated / "figures" / "fixture.pdf").read_bytes() == b"figure"
    # Exercise staging against the real tree after a normal build.
    build(ROOT)
    generated = stage_generated_files(ROOT)
    assert (generated / "claim_status.tex").is_file()
