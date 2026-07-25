from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PaperBuildError(RuntimeError):
    """Raised when the manuscript cannot be staged or compiled."""


def stage_generated_files(root: Path) -> Path:
    root = root.resolve()
    artifacts = root / "artifacts"
    generated = root / "paper" / "generated"
    required = {
        artifacts / "tables" / "project_metadata.tex": generated / "project_metadata.tex",
        artifacts / "tables" / "result_macros.tex": generated / "result_macros.tex",
        artifacts / "tables" / "claim_status.tex": generated / "claim_status.tex",
    }
    missing = [str(source) for source in required if not source.is_file()]
    if missing:
        raise PaperBuildError(
            "Generated manuscript inputs are missing; run paperkit build first: "
            + ", ".join(missing)
        )
    generated.mkdir(parents=True, exist_ok=True)
    for source, destination in required.items():
        shutil.copyfile(source, destination)
    generated_figures = generated / "figures"
    if generated_figures.exists():
        shutil.rmtree(generated_figures)
    artifact_figures = artifacts / "figures"
    if artifact_figures.is_dir():
        shutil.copytree(artifact_figures, generated_figures)
    return generated


def build_paper(root: Path) -> Path:
    root = root.resolve()
    stage_generated_files(root)
    latexmk = shutil.which("latexmk")
    if latexmk is None:
        raise PaperBuildError(
            "latexmk is not installed. Install a TeX distribution with latexmk "
            "to compile the paper."
        )
    paper_dir = root / "paper"
    command = [
        latexmk,
        "-pdf",
        "-halt-on-error",
        "-file-line-error",
        "-interaction=nonstopmode",
        "main.tex",
    ]
    completed = subprocess.run(command, cwd=paper_dir, check=False)
    if completed.returncode != 0:
        raise PaperBuildError(f"latexmk failed with exit code {completed.returncode}")
    pdf = paper_dir / "main.pdf"
    if not pdf.is_file():
        raise PaperBuildError("latexmk completed without producing paper/main.pdf")
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    destination = dist / "paper.pdf"
    shutil.copyfile(pdf, destination)
    return destination
