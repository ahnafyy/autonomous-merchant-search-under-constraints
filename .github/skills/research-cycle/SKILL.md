---
name: research-cycle
description: "Plan and execute a small computational or theoretical paper from candidate avenues through literature review, claim registration, analysis, falsification, manuscript, explainer, and release gates. Use when starting research, selecting a benchmark, evaluating novelty, or preparing a reproducible paper release."
argument-hint: "Research question, observation, or current stage"
---

# Research Cycle

Use the project records as durable state. Do not rely on chat history as the only
record of a decision or result.

## Procedure

1. Read `research/gates/status.yml` and stop at the first unapproved transition.
2. Diverge into candidate mechanisms in `research/avenues.yml`; do not commit to
   the first plausible framing.
3. Select the smallest benchmark capable of discriminating the chosen mechanism
   and complete `research/question.md`.
4. Delegate prior-art search to the literature scout and update
   `research/literature.yml` plus `paper/references.bib` only with verified works.
5. Register intended findings and falsifiers in `research/claims.yml` before the
   main analysis. Use [claim taxonomy](./references/claim-taxonomy.md).
6. Implement the canonical analysis under `packages/python/`, the matching npm API
   under `packages/javascript/`, and generate shared conformance vectors.
7. Run `paperkit build`, then delegate an independent falsification review using
   [review protocol](./references/falsification.md).
8. Draft the manuscript and explainer from generated artifacts, preserving claim status.
9. Run release validation. Prepare the relevant gate, but ask a human to approve it.

## Required Output At Every Stage

- Updated durable research record
- Cheapest next check that could change the conclusion
- Known limitations and unresolved counterevidence
- Current gate and the evidence needed for human approval
