# Research Cycle

The template uses eight stages. Iteration is expected; gate approval is not.

1. **Generate avenues.** Record candidate mechanisms, minimal models, decisive
   calculations, expected value, and rejection criteria in `research/avenues.yml`.
2. **Select a question.** Define the phenomenon, benchmark, controls, falsifiers, and
   non-goals in `research/question.md`.
3. **Search adjacent work.** Preserve databases, dates, queries, URLs or DOIs, overlap,
   distinction, and confidence in `research/literature.yml`. Never fill missing
   bibliographic details from memory.
4. **Approve scope and novelty.** A human evaluates the material in
   `research/gates/scope.md` and `research/gates/novelty.md`, then edits only the
   corresponding records in `research/gates/status.yml`.
5. **Design evidence.** Specify exact calculations, numerical experiments, controls,
   seeds, tolerances, and failure conditions. Register intended claims before calling
   them findings.
6. **Implement and falsify.** Put the canonical model in `packages/python/`, implement
   the npm API in `packages/javascript/`, run shared conformance and claim checks, and
   retain counterexamples or failed checks that alter interpretation.
7. **Approve evidence.** A human checks the evidence gate. Generated values then flow
   into the manuscript and site through `paperkit build`.
8. **Approve and package release.** Remove placeholders, audit claims, citations, and
   package APIs, approve the release gate, and build the paper, registry packages,
   reproducibility archive, and site with `paperkit release`.

The workspace skill in `.github/skills/research-cycle/SKILL.md` gives Copilot the same
workflow. The Research Lead may coordinate the hidden Literature Scout and
Falsification Reviewer, but no agent may mark a gate approved.
