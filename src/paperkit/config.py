from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    """Raised when a project contract is missing or invalid."""


VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[a-zA-Z0-9.-]+)?$")
PYTHON_DISTRIBUTION_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PYTHON_IMPORT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
NPM_PACKAGE_PATTERN = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$"
)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigurationError(f"Required file does not exist: {path}")
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected a YAML mapping in {path}")
    return value


def _require_string(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{context}.{key} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class ProjectConfig:
    title: str
    slug: str
    initialized: bool
    random_seed: int
    version: str
    python_distribution: str
    python_import_name: str
    javascript_package: str

    @classmethod
    def from_file(cls, path: Path) -> ProjectConfig:
        raw = load_yaml(path)
        if raw.get("schema_version") != 1:
            raise ConfigurationError("project.yml schema_version must be 1")
        project = raw.get("project")
        research = raw.get("research")
        release = raw.get("release")
        packages = raw.get("packages")
        if not all(isinstance(value, dict) for value in (project, research, release, packages)):
            raise ConfigurationError(
                "project.yml requires project, research, release, and packages mappings"
            )
        assert isinstance(project, dict)
        assert isinstance(research, dict)
        assert isinstance(release, dict)
        assert isinstance(packages, dict)
        python_package = packages.get("python")
        javascript_package = packages.get("javascript")
        if not isinstance(python_package, dict) or not isinstance(javascript_package, dict):
            raise ConfigurationError("packages requires python and javascript mappings")
        random_seed = research.get("random_seed")
        if not isinstance(random_seed, int) or isinstance(random_seed, bool):
            raise ConfigurationError("research.random_seed must be an integer")
        version = _require_string(release, "version", "release")
        python_distribution = _require_string(
            python_package, "distribution", "packages.python"
        )
        python_import_name = _require_string(
            python_package, "import_name", "packages.python"
        )
        javascript_name = _require_string(
            javascript_package, "name", "packages.javascript"
        )
        patterns = (
            (version, VERSION_PATTERN, "release.version"),
            (
                python_distribution,
                PYTHON_DISTRIBUTION_PATTERN,
                "packages.python.distribution",
            ),
            (python_import_name, PYTHON_IMPORT_PATTERN, "packages.python.import_name"),
            (javascript_name, NPM_PACKAGE_PATTERN, "packages.javascript.name"),
        )
        for value, pattern, context in patterns:
            if not pattern.fullmatch(value):
                raise ConfigurationError(f"{context} has invalid syntax: {value}")
        return cls(
            title=_require_string(project, "title", "project"),
            slug=_require_string(project, "slug", "project"),
            initialized=raw.get("initialized") is True,
            random_seed=random_seed,
            version=version,
            python_distribution=python_distribution,
            python_import_name=python_import_name,
            javascript_package=javascript_name,
        )


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        upper = value.upper()
        return "TODO" in upper or "OWNER/REPOSITORY" in upper
    if isinstance(value, dict):
        return any(contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_placeholder(item) for item in value)
    return False
