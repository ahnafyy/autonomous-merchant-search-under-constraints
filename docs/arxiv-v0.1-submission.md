# arXiv v0.1 Preparation Record

## Scope

This branch prepares, but does not submit, the `v0.1` preprint for *When Should a
Shopping Agent Stop Searching?* The intended evidence release reports an exploratory
costly-search study on frozen Shopify seller decks and source-stratified UCP
catalog-observation context. The policy retains the best observed seller offer and
compares another reveal's expected improvement with its declared inspection cost.

The current study has a post-collection title identity revision and four held-out
product clusters. It finds no reliably detected adaptive improvement across the
registered cost grid. UCP panels
are not pooled with the Shopify replay and do not establish checkout persistence or
universal seller coverage. Future releases should preregister identity, cost, and
advantage criteria before collecting a confirmatory seller-deck sample.

Future conference submissions may revise this work after sufficient longitudinal
observations support additional analyses. They are future plans, not submission or
acceptance claims.

## Release Checks

Choose and record a collection cutoff before creating the arXiv source archive. Run
these from the repository root against that frozen, validated working tree:

```bash
.venv/bin/python -m paperkit.cli validate --release
.venv/bin/python -m paperkit.cli build
.venv/bin/python -m paperkit.cli build-paper
```

The resulting PDF is `dist/paper.pdf`. The source archive must include the manuscript
sources, generated `paper/generated/` inputs, and the generated bibliography, but not
local virtual environments, output PDFs, credentials, or live collection outputs that
are still running. Raw ongoing collection data remains in the repository unless it is
deliberately evaluated and registered for a later release.

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