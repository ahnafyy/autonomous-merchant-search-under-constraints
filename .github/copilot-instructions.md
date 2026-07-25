# Project Guidelines

## Research Integrity

- Register a claim in `research/claims.yml` before presenting it as a finding.
- Never invent a citation, DOI, URL, theorem, result, or verification outcome.
- Distinguish analytic results, exact computations, numerical results,
  computational patterns, conjectures, and open questions in every artifact.
- A grid observation is not a theorem. State the tested domain and retain
  counterexamples or failed checks that change interpretation.
- Agents may prepare gate material but only a human may mark a gate approved.

## Evidence Architecture

- Scientific values originate in `packages/python/` and flow through `paperkit build`.
- The JavaScript package must pass the Python-generated vectors under
  `artifacts/conformance/`; never duplicate expected values between implementations.
- The paper and site consume generated files under `artifacts/`; do not copy
  headline values or reimplement model logic in publication surfaces.
- Exploratory notebooks cannot be the sole evidence for a released claim.
- Keep deterministic outputs stable: explicit seeds, tolerances, ordering, and
  no wall-clock timestamps in generated manifests.

## Build And Test

- Install with `make install`.
- Run `python -m paperkit.cli build`, `python -m pytest`, and
  `python -m ruff check .` for the current implementation.
- Run `python -m paperkit.cli validate --release` before packaging public work.
