from __future__ import annotations

import gzip
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe_gtin_support.py"
RESTORE_SCRIPT = ROOT / "scripts" / "restore_transient_denylist.py"
SURVIVAL_SCRIPT = ROOT / "scripts" / "offer_survival.py"
SPEC = importlib.util.spec_from_file_location("probe_gtin_support", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
probe_gtin_support = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_gtin_support)

RESTORE_SPEC = importlib.util.spec_from_file_location(
    "restore_transient_denylist", RESTORE_SCRIPT
)
assert RESTORE_SPEC is not None and RESTORE_SPEC.loader is not None
restore_transient_denylist = importlib.util.module_from_spec(RESTORE_SPEC)
RESTORE_SPEC.loader.exec_module(restore_transient_denylist)

SURVIVAL_SPEC = importlib.util.spec_from_file_location("offer_survival", SURVIVAL_SCRIPT)
assert SURVIVAL_SPEC is not None and SURVIVAL_SPEC.loader is not None
offer_survival = importlib.util.module_from_spec(SURVIVAL_SPEC)
SURVIVAL_SPEC.loader.exec_module(offer_survival)


def test_dns_failure_is_not_a_permanent_merchant_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_dns(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("[Errno 8] nodename nor servname provided")

    monkeypatch.setattr(probe_gtin_support, "MAX_ATTEMPTS", 1)
    monkeypatch.setattr(probe_gtin_support.urllib.request, "urlopen", fail_dns)

    with pytest.raises(probe_gtin_support.MerchantUnavailable):
        probe_gtin_support._fetch_json("https://merchant.example/.well-known/ucp")


def test_restore_removes_only_manifested_dns_failures(tmp_path: Path) -> None:
    manifest_path = tmp_path / "failed.manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "domain_status": {
                    "dns-failed.example": "refused: unavailable after 3 attempts: "
                    "<urlopen error [Errno 8] nodename nor servname provided>",
                    "explicit-refusal.example": "refused:403",
                }
            }
        ),
        encoding="utf-8",
    )
    denylist_path = tmp_path / "crawler-denylist.txt"
    denylist_path.write_text(
        "dns-failed.example  # unavailable after 3 attempts: <urlopen error "
        "[Errno 8] nodename nor servname provided>\n"
        "explicit-refusal.example  # 403\n"
        "older-dns-failure.example  # nodename nor servname\n",
        encoding="utf-8",
    )

    removed = restore_transient_denylist.restore_domains(
        denylist_path,
        restore_transient_denylist.dns_failed_domains(manifest_path),
    )

    assert removed == ["dns-failed.example"]
    assert denylist_path.read_text(encoding="utf-8") == (
        "explicit-refusal.example  # 403\n"
        "older-dns-failure.example  # nodename nor servname\n"
    )


def test_survival_uses_a_fixed_fully_observed_cohort(tmp_path: Path) -> None:
    def write_observation(observation_date: str, rows: list[dict[str, object]]) -> None:
        path = tmp_path / f"panel-observations-{observation_date}.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    write_observation(
        "2026-09-01",
        [
            {"domain": "a.example", "sku": "a", "present": True},
            {"domain": "b.example", "sku": "b", "present": True},
        ],
    )
    write_observation(
        "2026-09-02",
        [
            {"domain": "a.example", "sku": "a", "present": True, "merchant_fully_paginated": True},
            {"domain": "b.example", "sku": "b", "present": False, "merchant_fully_paginated": True},
        ],
    )
    write_observation(
        "2026-09-03",
        [
            {"domain": "a.example", "sku": "a", "present": True, "merchant_fully_paginated": True},
            {"domain": "b.example", "sku": "b", "present": True, "merchant_fully_paginated": False},
        ],
    )

    assert offer_survival.main(["--data-dir", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "offer-survival.json").read_text(encoding="utf-8"))

    assert report["fixed_fully_observed_cohort"] == 1
    assert [row["survival"] for row in report["observations"]] == [1.0, 1.0]