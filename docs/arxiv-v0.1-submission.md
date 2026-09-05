# arXiv v0.1 Submission Record

## Scope

This preprint is the `v0.1` evidence release for *When Should a Shopping Agent Stop
Searching?* It reports the verified two-snapshot catalog-search analysis and its
registered claims. Daily panel re-observation and weekly discovery are ongoing; they
are not evidence in this version.

Future conference submissions may revise this work after sufficient longitudinal
observations support additional analyses. They are future plans, not submission or
acceptance claims.

## Release Checks

Run these from the repository root before creating the arXiv source archive:

```bash
.venv/bin/python -m paperkit.cli validate --release
.venv/bin/python -m paperkit.cli build
.venv/bin/python -m paperkit.cli build-paper
```

The resulting PDF is `dist/paper.pdf`. The source archive must include the manuscript
sources, generated `paper/generated/` inputs, and the generated bibliography, but not
local virtual environments, output PDFs, credentials, or live collection outputs that
are still running.

## Manual arXiv Submission

1. Create the source archive from the validated working tree.
2. Upload it through the author's arXiv account under the category recorded in
   `project.yml`.
3. Confirm that arXiv's compilation preview matches `dist/paper.pdf` and that all
   citations and tables render.
4. Record the arXiv identifier and submission date in a follow-up release commit only
   after arXiv assigns them.

## Future Conference Revisions

Before revising for a conference, regenerate and evaluate the accumulated daily panel
series. Add only analyses with registered claims and executable evaluators; do not
retrofit results into the v0.1 preprint.