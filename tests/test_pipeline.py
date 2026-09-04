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
    assert all(claim["passed"] for claim in claim_results["claims"])
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["all_executable_claims_passed"] is True
    assert "results.json" in manifest["files"]
    assert "conformance/merchant-search.json" in manifest["files"]
    site_data = json.loads((first / "site-data.json").read_text(encoding="utf-8"))
    assert site_data["results"]["hard_constraint_action_signature"] == (
        "relaxed:continue|time-tight:buy|token-tight:buy|api-tight:buy|"
        "api-spend-tight:buy|combined:buy|price-capped:continue"
    )
    claim_statuses = {claim["id"]: claim["status"] for claim in site_data["claims"]}
    assert claim_statuses == {
        "CLOSED-FORM-RULE-001": "exact-computational",
        "NO-ADVANTAGE-REGION-001": "computational-pattern",
        "OFFER-EPHEMERALITY-001": "numerical",
        "OVERLAP-SPARSITY-001": "numerical",
        "PERMIT-SAFETY-001": "conjecture",
        "SECRETARY-RULE-001": "computational-pattern",
        "SOLVER-AGREEMENT-001": "exact-computational",
        "STOPPING-ADVANTAGE-001": "numerical",
    }
    assert site_data["packages"]["python"]["distribution"] == (
        "autonomous-shopping-optimizer"
    )
    assert site_data["packages"]["python"]["import_name"] == (
        "autonomous_shopping_optimizer"
    )
    assert site_data["packages"]["javascript"]["name"] == (
        "autonomous-shopping-optimizer"
    )
    metadata = (first / "tables" / "project_metadata.tex").read_text(encoding="utf-8")
    assert "\\newcommand{\\PaperTitle}" in metadata
    claim_table = (first / "tables" / "claim_status.tex").read_text(encoding="utf-8")
    assert "STOPPING-ADVANTAGE-001" in claim_table
    assert "MERCHANT-BELLMAN-002" not in claim_table
    decision_table = (first / "tables" / "decision_table.tex").read_text(encoding="utf-8")
    assert "95\\% CI" in decision_table
    assert "Favors adaptive" in decision_table
    episode_features = (first / "tables" / "episode_features.tex").read_text(
        encoding="utf-8"
    )
    assert "Held-out panel characteristic" in episode_features


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
