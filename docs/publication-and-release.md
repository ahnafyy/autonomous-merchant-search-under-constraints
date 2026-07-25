# Publication and Release

## Manuscript

The manuscript is modular under `paper/sections/`. Generated metadata, result macros,
and the claim table are staged into `paper/generated/`. Keep claims in prose consistent
with their registered status and use `references.bib` only for verified citations.

`paperkit build-paper --stage-only` works without TeX. Full compilation requires
`latexmk`; CI installs a TeX environment and compiles the manuscript independently.

## Interactive explainer

The Astro site imports `site/src/generated/site-data.json`, copied from
`artifacts/site-data.json` by `npm run sync`. Public pages may format and interact with
results, but must not recompute the study model. The included Playwright suite checks
desktop and mobile rendering, interaction, horizontal page overflow, console errors,
and axe accessibility rules.

Use Node 22.12 or newer:

```bash
npm ci --prefix site
npm run check --prefix site
npm run build --prefix site
npx --prefix site playwright install chromium
npm run test:e2e --prefix site
```

## Registry packages

The Python distribution in `packages/python/` is the canonical scientific
implementation. The npm package in `packages/javascript/` implements the same public
operations and is checked against `artifacts/conformance/`.

```bash
python -m build packages/python
npm ci --prefix packages/javascript
npm test --prefix packages/javascript
npm run pack:check --prefix packages/javascript
```

`project.yml` owns the shared release version and both registry names. Run the
initializer rather than editing package manifests independently. Configure GitHub
environments named `pypi` and `npm`, then register
`.github/workflows/publish-packages.yml` as a trusted publisher with each registry.
The workflow uses OIDC and stores no registry token in the repository.

## Release gate

`paperkit release --dry-run` always rebuilds evidence before validation. A real release
also compiles the paper and site, builds both registry packages, then atomically
replaces `dist/` with deterministic archives, citation metadata, and SHA-256
checksums. It never approves a gate.

Before release, verify that:

- all five gate records contain a human approver and ISO date;
- all manuscript and research placeholders are removed;
- every claim has accurate scope, status, limitations, and evidence;
- literature records and bibliography entries are verifiable;
- the extracted arXiv source compiles in a clean environment;
- Python and JavaScript package APIs pass the generated conformance vectors;
- wheel, sdist, and npm tarball contain only intended public files;
- the repository and site links in `project.yml` resolve to the public project.
