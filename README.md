# Research Paper and Package Template

An opinionated GitHub template for turning a computational or theoretical question
into a checked research release. One repository produces five coordinated outputs:

- an arXiv-ready paper and PDF;
- a Python distribution for PyPI;
- a JavaScript package for npm;
- deterministic evidence and conformance artifacts;
- an interactive Astro explainer for GitHub Pages.

The Python package under `packages/python/` is the canonical implementation used by
`paperkit build`. That build evaluates registered claims and generates `artifacts/`,
including language-neutral conformance vectors. The JavaScript package must pass those
same vectors. The paper and site consume generated artifacts rather than copying
headline values or reimplementing the model.

Human approval is required at scope, novelty, design, evidence, and release gates. The
checked-in occupancy example is intentionally unpublishable: `initialized: false`,
placeholders, and pending gates demonstrate that release and registry publication are
blocked until a real project is ready.

## Start a project

Use this repository as a GitHub template, clone the new repository, then run:

```bash
python3 -m venv .venv
. .venv/bin/activate
make install
python scripts/init_project.py
```

The initializer writes canonical paper and package metadata to `project.yml`, updates
both registry manifests, and renames the Python import package. It never approves a
research gate.

Replace the fixture API in `packages/python/` and `packages/javascript/`, register
claims in `research/claims.yml`, and update the generated conformance contract in
`src/paperkit/pipeline.py` for the public operations your packages share.

## Build and inspect

Python 3.11 or newer and Node 22.12 or newer are required.

```bash
paperkit build
paperkit validate
python -m pytest
python -m ruff check .
npm test --prefix packages/javascript

npm ci --prefix site
npm run check --prefix site
npm run dev --prefix site
```

The site is served at `http://localhost:4321`. Its benchmark, results, and claim table
come from `artifacts/site-data.json`; it is a publication surface, not a third model
implementation.

To stage generated manuscript inputs without TeX, run
`paperkit build-paper --stage-only`. To compile `dist/paper.pdf`, install a TeX
distribution containing `latexmk`, then run `paperkit build-paper`.

## Release

Use `paperkit release --dry-run` while developing. A release remains blocked until
metadata is initialized, placeholders are removed, executable claims pass, package
manifests match `project.yml`, and a human approves every gate.

A successful `paperkit release` creates:

- `dist/paper.pdf` and `dist/arxiv-source.tar.gz`;
- `dist/packages/python/` with a wheel and source distribution;
- `dist/packages/javascript/` with the npm tarball;
- `dist/reproducibility.zip`;
- `dist/site/`;
- `dist/CITATION.cff` and `dist/SHA256SUMS`.

GitHub Actions independently checks evidence, cross-language conformance, package
contents, manuscript compilation, browser behavior, accessibility, and Pages. A
published GitHub release can publish packages through
`.github/workflows/publish-packages.yml` after the `pypi` and `npm` environments and
trusted publishers are configured.

Before the first Pages deployment in a repository created from this template, open
**Settings > Pages** and select **GitHub Actions** as the source. This one-time setting
cannot be enabled by the workflow's least-privilege `GITHUB_TOKEN`.

## Guides

- [Research cycle](docs/research-cycle.md)
- [Claim taxonomy](docs/claim-taxonomy.md)
- [Customizing a study](docs/customizing-a-study.md)
- [Publication and release](docs/publication-and-release.md)
- [Contributing](CONTRIBUTING.md)
