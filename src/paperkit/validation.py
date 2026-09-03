from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from paperkit.claims import load_claims
from paperkit.config import ConfigurationError, ProjectConfig, contains_placeholder, load_yaml

RELEASE_TEXT_PATHS = (
    "project.yml",
    "research/avenues.yml",
    "research/question.md",
    "research/literature.yml",
    "research/claims.yml",
    "paper",
)


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_project(root: Path, *, release: bool = False) -> ValidationReport:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    try:
        config = ProjectConfig.from_file(root / "project.yml")
        raw_config = load_yaml(root / "project.yml")
    except ConfigurationError as error:
        return ValidationReport(errors=(str(error),), warnings=())

    try:
        claims = load_claims(root / "research" / "claims.yml")
    except ConfigurationError as error:
        errors.append(str(error))
        claims = []

    if not claims:
        warnings.append("No claims are registered.")

    if not config.initialized:
        message = "Project has not been initialized."
        if release:
            errors.append(message)
        else:
            warnings.append(message)
    if contains_placeholder(raw_config):
        message = "Project metadata still contains template placeholders."
        if release:
            errors.append(message)
        else:
            warnings.append(message)

    _validate_package_metadata(root, config, errors)

    if release:
        placeholder_paths = _placeholder_paths(root)
        if placeholder_paths:
            errors.append(
                "Template placeholders remain in release inputs: "
                + ", ".join(path.as_posix() for path in placeholder_paths)
            )
        manifest_path = root / "artifacts" / "manifest.json"
        if not manifest_path.is_file():
            errors.append("Verified artifact manifest is missing; run paperkit build.")
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as error:
                errors.append(f"Artifact manifest is unreadable: {error}")
            else:
                if manifest.get("project", {}).get("slug") != config.slug:
                    errors.append("Artifact manifest was generated for different project metadata.")
                if manifest.get("all_executable_claims_passed") is not True:
                    errors.append("One or more executable claims failed.")

    return ValidationReport(errors=tuple(errors), warnings=tuple(warnings))


def _validate_package_metadata(
    root: Path, config: ProjectConfig, errors: list[str]
) -> None:
    python_manifest = root / "packages" / "python" / "pyproject.toml"
    javascript_manifest = root / "packages" / "javascript" / "package.json"
    try:
        python_project = tomllib.loads(python_manifest.read_text(encoding="utf-8"))["project"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        errors.append(f"Python package manifest is unreadable: {error}")
    else:
        if python_project.get("name") != config.python_distribution:
            errors.append("Python package name does not match project.yml.")
        if python_project.get("version") != config.version:
            errors.append("Python package version does not match project.yml.")
    try:
        javascript_project = json.loads(javascript_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"JavaScript package manifest is unreadable: {error}")
    else:
        if javascript_project.get("name") != config.javascript_package:
            errors.append("JavaScript package name does not match project.yml.")
        if javascript_project.get("version") != config.version:
            errors.append("JavaScript package version does not match project.yml.")

    python_module = (
        root
        / "packages"
        / "python"
        / "src"
        / config.python_import_name
        / "__init__.py"
    )
    if not python_module.is_file():
        errors.append("Configured Python import package does not exist.")


def _placeholder_paths(root: Path) -> list[Path]:
    found: list[Path] = []
    for relative in RELEASE_TEXT_PATHS:
        path = root / relative
        candidates = path.rglob("*") if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() not in {
                ".md",
                ".tex",
                ".yml",
                ".yaml",
            }:
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "TODO" in text.upper() or "OWNER/REPOSITORY" in text.upper():
                found.append(candidate.relative_to(root))
    return sorted(found)

