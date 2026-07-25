from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from paperkit.config import ProjectConfig
from paperkit.release import ReleaseError, release
from paperkit.validation import validate_project

ROOT = Path(__file__).resolve().parents[1]


def test_initializer_is_idempotent(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    shutil.copy(ROOT / "project.yml", project_root / "project.yml")
    shutil.copytree(ROOT / "packages", project_root / "packages")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "init_project.py"),
        "--root",
        str(project_root),
        "--config",
        str(ROOT / "tests" / "fixtures" / "init.json"),
        "--non-interactive",
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


def test_release_validation_blocks_template() -> None:
    development = validate_project(ROOT)
    release = validate_project(ROOT, release=True)

    assert development.ok
    assert any("Pending human gates" in warning for warning in development.warnings)
    assert not release.ok
    assert any("not been initialized" in error for error in release.errors)
    assert any("Pending human gates" in error for error in release.errors)


def test_release_dry_run_does_not_bypass_template_gates() -> None:
    try:
        release(ROOT, dry_run=True)
    except ReleaseError as error:
        message = str(error)
    else:
        raise AssertionError("Template release unexpectedly passed")

    assert "Pending human gates" in message
    assert "Project has not been initialized" in message
