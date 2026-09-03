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
        artifacts / "tables" / "decision_table.tex": generated / "decision_table.tex",
        artifacts / "tables" / "arm_comparison.tex": generated / "arm_comparison.tex",
        artifacts / "tables" / "rule_comparison.tex": generated / "rule_comparison.tex",
        artifacts / "tables" / "references.bib": generated / "references.bib",
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
    paper_dir = root / "paper"

    latexmk = shutil.which("latexmk")
    tectonic = shutil.which("tectonic")
    if latexmk is not None:
        command = [
            latexmk,
            "-pdf",
            "-halt-on-error",
            "-file-line-error",
            "-interaction=nonstopmode",
            "main.tex",
        ]
        engine = "latexmk"
    elif tectonic is not None:
        # Tectonic resolves its own packages, so it needs no TeX distribution.
        command = [tectonic, "-X", "compile", "main.tex", "--outdir", str(paper_dir)]
        engine = "tectonic"
    else:
        raise PaperBuildError(
            "No LaTeX engine found. Install latexmk with a TeX distribution, or "
            "install tectonic (brew install tectonic)."
        )

    completed = subprocess.run(command, cwd=paper_dir, check=False)
    if completed.returncode != 0:
        raise PaperBuildError(f"{engine} failed with exit code {completed.returncode}")
    pdf = paper_dir / "main.pdf"
    if not pdf.is_file():
        raise PaperBuildError(f"{engine} completed without producing paper/main.pdf")
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    destination = dist / "paper.pdf"
    shutil.copyfile(pdf, destination)
    return destination
