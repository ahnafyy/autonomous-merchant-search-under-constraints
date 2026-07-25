from __future__ import annotations

import argparse
from pathlib import Path

from paperkit.paper import PaperBuildError, build_paper, stage_generated_files
from paperkit.pipeline import build
from paperkit.release import ReleaseError, release
from paperkit.validation import validate_project


def main() -> None:
    parser = argparse.ArgumentParser(prog="paperkit")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="Evaluate claims and generate artifacts")
    build_parser.add_argument("--root", type=Path, default=Path.cwd())
    build_parser.add_argument("--output", type=Path)
    validate_parser = subparsers.add_parser("validate", help="Validate project contracts")
    validate_parser.add_argument("--root", type=Path, default=Path.cwd())
    validate_parser.add_argument(
        "--release", action="store_true", help="Apply publication release gates"
    )
    paper_parser = subparsers.add_parser("build-paper", help="Stage and compile the manuscript")
    paper_parser.add_argument("--root", type=Path, default=Path.cwd())
    paper_parser.add_argument(
        "--stage-only", action="store_true", help="Stage generated TeX without compiling"
    )
    release_parser = subparsers.add_parser("release", help="Validate and assemble release files")
    release_parser.add_argument("--root", type=Path, default=Path.cwd())
    release_parser.add_argument(
        "--dry-run", action="store_true", help="Rebuild and check release gates without packaging"
    )
    args = parser.parse_args()

    if args.command == "build":
        output = build(args.root, args.output)
        print(f"Generated verified artifacts in {output}")
    elif args.command == "validate":
        report = validate_project(args.root, release=args.release)
        for warning in report.warnings:
            print(f"warning: {warning}")
        for error in report.errors:
            print(f"error: {error}")
        if not report.ok:
            raise SystemExit(1)
        print("Project contracts are valid.")
    elif args.command == "build-paper":
        try:
            output = stage_generated_files(args.root) if args.stage_only else build_paper(args.root)
        except PaperBuildError as error:
            print(f"error: {error}")
            raise SystemExit(1) from error
        print(f"Paper output ready at {output}")
    elif args.command == "release":
        try:
            output = release(args.root, dry_run=args.dry_run)
        except ReleaseError as error:
            print(f"error: {error}")
            raise SystemExit(1) from error
        if args.dry_run:
            print("Release checks passed; no package was created.")
        else:
            print(f"Release package ready at {output}")



if __name__ == "__main__":
    main()
