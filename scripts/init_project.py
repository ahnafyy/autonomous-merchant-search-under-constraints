#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[a-zA-Z0-9.-]+)?$")
PYTHON_IMPORT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
NPM_PACKAGE_PATTERN = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$"
)


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default or ""


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _require_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    title = _require_text(data, "title")
    subtitle = _require_text(data, "subtitle")
    slug = _require_text(data, "slug")
    abstract = _require_text(data, "abstract")
    author = _require_text(data, "author")
    affiliation = _require_text(data, "affiliation")
    repository = _require_text(data, "repository")
    site = _require_text(data, "site")
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError("slug must contain lowercase words separated by single hyphens")
    version = str(data.get("version", "0.1.0")).strip()
    python_distribution = str(data.get("python_distribution", slug)).strip()
    python_import_name = str(data.get("python_import_name", slug.replace("-", "_"))).strip()
    javascript_package = str(data.get("javascript_package", slug)).strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("version must use semantic version syntax such as 0.1.0")
    if not SLUG_PATTERN.fullmatch(python_distribution):
        raise ValueError("python_distribution must use lowercase hyphenated words")
    if not PYTHON_IMPORT_PATTERN.fullmatch(python_import_name):
        raise ValueError("python_import_name must be a valid lowercase Python identifier")
    if not NPM_PACKAGE_PATTERN.fullmatch(javascript_package):
        raise ValueError("javascript_package must be a valid lowercase npm package name")
    if not _valid_url(repository) or not _valid_url(site):
        raise ValueError("repository and site must be absolute https URLs")
    orcid = data.get("orcid")
    if orcid is not None and (not isinstance(orcid, str) or not ORCID_PATTERN.fullmatch(orcid)):
        raise ValueError("orcid must use the form 0000-0000-0000-000X")
    keywords = data.get("keywords", [])
    categories = data.get("arxiv_categories", ["cs.AI"])
    if (
        not isinstance(keywords, list)
        or not keywords
        or not all(isinstance(value, str) for value in keywords)
    ):
        raise ValueError("keywords must be a non-empty list of strings")
    if not isinstance(categories, list) or not categories or not all(
        isinstance(v, str) for v in categories
    ):
        raise ValueError("arxiv_categories must be a non-empty list of strings")
    seed = data.get("random_seed", 20260723)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("random_seed must be an integer")
    return {
        "title": title,
        "subtitle": subtitle,
        "slug": slug,
        "abstract": abstract,
        "author": author,
        "orcid": orcid,
        "affiliation": affiliation,
        "repository": repository,
        "site": site,
        "keywords": keywords,
        "arxiv_categories": categories,
        "random_seed": seed,
        "version": version,
        "python_distribution": python_distribution,
        "python_import_name": python_import_name,
        "javascript_package": javascript_package,
        "code_license": str(data.get("code_license", "MIT")),
        "content_license": str(data.get("content_license", "CC-BY-4.0")),
    }


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _render(data: dict[str, Any]) -> str:
    orcid = "null" if data["orcid"] is None else _quoted(data["orcid"])
    keyword_lines = "\n".join(f"    - {_quoted(value)}" for value in data["keywords"])
    category_lines = "\n".join(
        f"    - {_quoted(value)}" for value in data["arxiv_categories"]
    )
    return f"""schema_version: 1
initialized: true
project:
  title: {_quoted(data['title'])}
  subtitle: {_quoted(data['subtitle'])}
  slug: {_quoted(data['slug'])}
  abstract: {_quoted(data['abstract'])}
  keywords:
{keyword_lines}
  arxiv_categories:
{category_lines}
authors:
  - name: {_quoted(data['author'])}
    orcid: {orcid}
    affiliations:
      - {_quoted(data['affiliation'])}
links:
  repository: {_quoted(data['repository'])}
  site: {_quoted(data['site'])}
research:
  random_seed: {data['random_seed']}
release:
    version: {_quoted(data['version'])}
packages:
    python:
        distribution: {_quoted(data['python_distribution'])}
        import_name: {_quoted(data['python_import_name'])}
    javascript:
        name: {_quoted(data['javascript_package'])}
licenses:
  code: {_quoted(data['code_license'])}
  content: {_quoted(data['content_license'])}
"""


def _sync_package_metadata(root: Path, data: dict[str, Any]) -> None:
    python_root = root / "packages" / "python"
    if python_root.is_dir():
        source_root = python_root / "src"
        target = source_root / data["python_import_name"]
        if not target.is_dir():
            candidates = [
                path
                for path in source_root.iterdir()
                if path.is_dir() and (path / "__init__.py").is_file()
            ]
            if len(candidates) != 1:
                raise ValueError("cannot identify the Python package source directory")
            candidates[0].rename(target)
        (target / "__init__.py").write_text(
            f"from {data['python_import_name']}.analysis import ExpectedDistinct, "
            "expected_distinct_choices\n\n"
            '__all__ = ["ExpectedDistinct", "expected_distinct_choices"]\n'
            f'__version__ = "{data["version"]}"\n',
            encoding="utf-8",
        )
        (python_root / "pyproject.toml").write_text(
            f'''[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = {_quoted(data['python_distribution'])}
version = {_quoted(data['version'])}
description = {_quoted(data['subtitle'])}
readme = "README.md"
requires-python = ">=3.11"
license = {_quoted(data['code_license'])}
authors = [{{ name = {_quoted(data['author'])} }}]

[project.urls]
Repository = {_quoted(data['repository'])}
Paper = {_quoted(data['site'])}

[tool.hatch.build.targets.wheel]
packages = ["src/{data['python_import_name']}"]
''',
            encoding="utf-8",
        )

    javascript_root = root / "packages" / "javascript"
    if javascript_root.is_dir():
        package = {
            "name": data["javascript_package"],
            "version": data["version"],
            "description": data["subtitle"],
            "type": "module",
            "exports": {
                ".": {"types": "./src/index.d.ts", "import": "./src/index.js"}
            },
            "files": ["src", "README.md"],
            "scripts": {"test": "node --test", "pack:check": "npm pack --dry-run"},
            "engines": {"node": ">=22.12.0"},
            "license": data["code_license"],
            "repository": {"type": "git", "url": f"git+{data['repository']}.git"},
            "publishConfig": {"access": "public", "provenance": True},
        }
        (javascript_root / "package.json").write_text(
            json.dumps(package, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        lock = {
            "name": data["javascript_package"],
            "version": data["version"],
            "lockfileVersion": 3,
            "requires": True,
            "packages": {
                "": {
                    "name": data["javascript_package"],
                    "version": data["version"],
                    "license": data["code_license"],
                    "engines": {"node": ">=22.12.0"},
                }
            },
        }
        (javascript_root / "package-lock.json").write_text(
            json.dumps(lock, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )


def _interactive_values() -> dict[str, Any]:
    return {
        "title": _ask("Paper title"),
        "subtitle": _ask("One-sentence contribution"),
        "slug": _ask("Project slug"),
        "version": _ask("Package version", "0.1.0"),
        "python_distribution": _ask("PyPI distribution name"),
        "python_import_name": _ask("Python import name"),
        "javascript_package": _ask("npm package name"),
        "abstract": _ask("Initial abstract"),
        "author": _ask("Author name"),
        "orcid": _ask("ORCID (optional)") or None,
        "affiliation": _ask("Affiliation"),
        "repository": _ask("Repository URL"),
        "site": _ask("Site URL"),
        "keywords": [value.strip() for value in _ask("Keywords, comma separated").split(",")],
        "arxiv_categories": [
            value.strip() for value in _ask("arXiv categories, comma separated", "cs.AI").split(",")
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a research paper and package project")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, help="JSON file containing initialization values")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.non_interactive and args.config is None:
        parser.error("--non-interactive requires --config")
    if args.config:
        try:
            values = json.loads(args.config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Initialization config is unreadable: {error}", file=sys.stderr)
            return 2
        if not isinstance(values, dict):
            print("Initialization config must be a JSON object", file=sys.stderr)
            return 2
    else:
        values = _interactive_values()

    try:
        normalized = _normalize(values)
        rendered = _render(normalized)
    except ValueError as error:
        print(f"Invalid initialization values: {error}", file=sys.stderr)
        return 2

    destination = args.root.resolve() / "project.yml"
    if destination.exists():
        current = destination.read_text(encoding="utf-8")
        if current == rendered:
            _sync_package_metadata(args.root.resolve(), normalized)
            print(f"Already initialized: {destination}")
            return 0
        if "initialized: true" in current and not args.force:
            print(
                "Project is already initialized; pass --force to replace metadata.",
                file=sys.stderr,
            )
            return 2
    destination.write_text(rendered, encoding="utf-8")
    try:
        _sync_package_metadata(args.root.resolve(), normalized)
    except (OSError, ValueError) as error:
        print(f"Package metadata could not be initialized: {error}", file=sys.stderr)
        return 2
    print(f"Initialized project metadata in {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
