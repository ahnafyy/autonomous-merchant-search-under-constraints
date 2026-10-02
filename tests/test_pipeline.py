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
    assert site_data["results"]["study_design"] == "source_stratified_recalled_pandora_search"
    assert site_data["results"]["empirical_claims_ready"] is False
    assert site_data["results"]["shopify_global_catalog"]["product_deck_count"] == 40
    assert site_data["results"]["shopify_global_catalog"]["held_out_product_count"] == 16
    ucp_costs = site_data["results"]["ucp_direct_panels"]["cost_overlay"]
    assert ucp_costs["status"] == "declared_historical_cost_overlay"
    assert ucp_costs["total_merchant_probe_calls"] > 0
    assert [row["cost_scenario"] for row in ucp_costs["scenarios"]] == [
        "catalog_expansion",
        "agentic_review_2m",
        "long_horizon_research_5m",
    ]
    ucp_replay = site_data["results"]["ucp_direct_panels"]["pandora_replay"]
    assert ucp_replay["status"] == "analyzed_frozen_panel_series"
    assert ucp_replay["product_deck_count"] > 3445
    assert ucp_replay["held_out_product_count"] == 1381
    assert ucp_replay["held_out_replay_deck_count"] > ucp_replay["held_out_product_count"]
    assert len(ucp_replay["cost_results"]) == 3
    sensitivity = site_data["results"]["ucp_cost_sensitivity"]
    assert sensitivity["status"] == "analyzed_registered_market_rate_multipliers"
    assert [
        row["adaptive_vs_search_all"]["favors_treatment"]
        for row in sensitivity["cost_results"]
    ] == [False, False, False, True, True]
    claim_statuses = {claim["id"]: claim["status"] for claim in site_data["claims"]}
    assert claim_statuses == {
        "PANDORA-ADVANTAGE-001": "numerical",
        "SHOPIFY-SELLER-DECK-STUDY-001": "numerical",
        "UCP-MARKET-RATE-SENSITIVITY-001": "numerical",
        "UCP-OBSERVATION-QUALITY-001": "numerical",
        "UCP-PANDORA-REPLAY-001": "numerical",
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
    assert "PANDORA-ADVANTAGE-001" in claim_table
    source_table = (first / "tables" / "source_context.tex").read_text(encoding="utf-8")
    assert "not pooled with Shopify decks" in source_table
    study_table = (first / "tables" / "pandora_study.tex").read_text(encoding="utf-8")
    assert "search all" in study_table
    ucp_study_table = (first / "tables" / "ucp_pandora_study.tex").read_text(
        encoding="utf-8"
    )
    assert "Adaptive improvement" in ucp_study_table
    sensitivity_table = (first / "tables" / "ucp_cost_sensitivity.tex").read_text(
        encoding="utf-8"
    )
    assert "Adaptive improvement" in sensitivity_table
    assert "Search-all improvement" in sensitivity_table


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
    assert (generated / "ucp_cost_sensitivity.tex").is_file()
