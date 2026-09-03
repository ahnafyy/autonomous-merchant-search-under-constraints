from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from paperkit.config import ProjectConfig
from paperkit.validation import validate_project

ROOT = Path(__file__).resolve().parents[1]


def test_initializer_is_idempotent(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    shutil.copy(ROOT / "project.yml", project_root / "project.yml")
    shutil.copytree(ROOT / "packages", project_root / "packages")
    analysis_packages = sorted(
        path.parent.name
        for path in (project_root / "packages" / "python" / "src").glob(
            "*/analysis.py"
        )
    )
    assert analysis_packages == ["autonomous_shopping_optimizer"]
    command = [
        sys.executable,
        str(ROOT / "scripts" / "init_project.py"),
        "--root",
        str(project_root),
        "--config",
        str(ROOT / "tests" / "fixtures" / "init.json"),
        "--non-interactive",
        "--force",
    ]

    first = subprocess.run(command, check=False, capture_output=True, text=True)
    first_contents = (project_root / "project.yml").read_bytes()
    second = subprocess.run(command, check=False, capture_output=True, text=True)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (project_root / "project.yml").read_bytes() == first_contents
    config = ProjectConfig.from_file(project_root / "project.yml")
    assert config.initialized is True
    assert config.version == "0.2.0"
    assert config.python_distribution == "verified-paper"
    assert config.python_import_name == "verified_paper"
    assert config.javascript_package == "@example/verified-paper"
    python_project = tomllib.loads(
        (project_root / "packages" / "python" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )["project"]
    assert python_project["name"] == "verified-paper"
    assert python_project["version"] == "0.2.0"
    assert (project_root / "packages" / "python" / "src" / "verified_paper").is_dir()
    javascript_project = json.loads(
        (project_root / "packages" / "javascript" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    assert javascript_project["name"] == "@example/verified-paper"
    assert javascript_project["version"] == "0.2.0"


def test_development_validation_passes() -> None:
    report = validate_project(ROOT)

    assert report.ok, report.errors


def test_release_validation_requires_generated_manifest(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    shutil.copy(ROOT / "project.yml", project_root / "project.yml")
    shutil.copytree(ROOT / "packages", project_root / "packages")
    shutil.copytree(ROOT / "research", project_root / "research")

    report = validate_project(project_root, release=True)

    assert not report.ok
    assert any("manifest is missing" in error for error in report.errors)
