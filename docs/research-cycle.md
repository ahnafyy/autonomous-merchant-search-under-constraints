# Research Cycle

The project uses six stages. Iteration is expected.

1. **Generate avenues.** Record candidate mechanisms, minimal models, decisive
   calculations, expected value, and rejection criteria in `research/avenues.yml`.
2. **Select a question.** Define the phenomenon, benchmark, controls, falsifiers, and
   non-goals in `research/question.md`.
3. **Search adjacent work.** Preserve databases, dates, queries, URLs or DOIs, overlap,
   distinction, and confidence in `research/literature.yml`. Never fill missing
   bibliographic details from memory.
4. **Design evidence.** Specify exact calculations, numerical experiments, controls,
   seeds, tolerances, and failure conditions. Register intended claims in
   `research/claims.yml` before calling them findings.
5. **Implement and falsify.** Put the canonical model in `packages/python/`, implement
   the npm API in `packages/javascript/`, run shared conformance and claim checks, and
   retain counterexamples or failed checks that alter interpretation.
6. **Package the release.** Remove placeholders, audit claims, citations, and package
   APIs, then build the paper, registry packages, reproducibility archive, and site
   with `paperkit release`.

The workspace skill in `.github/skills/research-cycle/SKILL.md` gives Copilot the same
workflow. The Research Lead may coordinate the hidden Literature Scout and
Falsification Reviewer.

Every registered claim must be backed by an executable evaluator so that
`paperkit build` fails when a claim stops holding.
