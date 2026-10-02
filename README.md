# When Should a Shopping Agent Stop Searching?

This repository studies one practical shopping-agent question: is another merchant
inspection worth its cost? The agent keeps its best observed offer and compares the
expected saving from another seller with the time, calls, money, and attention needed
to inspect it.

## Current evidence

The policy benchmark uses a recovered complete 39-query prefix of a frozen deep
Shopify Global Catalog snapshot to build single-currency seller decks. The current
analysis yields 40 title-normalized decks and 172 seller cards under a disclosed
post-collection identity revision: 24 decks calibrate adaptive stopping and 16
independent product clusters are held out for evaluation. The reported comparison is
adaptive stopping versus costed search-all, not a fixed-depth heuristic. The two
lower-cost Shopify intervals are inconclusive; the long-horizon scenario favors
adaptive stopping.

This study also uses UCP direct-merchant panels to characterize catalog observability
and collection quality in the wider search environment. The datasets are analyzed
separately rather than pooled: an aggregator's visible product--seller graph is not
evidence of universal market coverage, seller independence, checkout availability,
shipping, tax, or returns.

## Model

A recalled-search state is $(p^\star, S, b)$: the best retained price, unopened
sellers, and remaining inspection budget. With free recall and zero inspection cost,
opening every feasible card weakly improves the retained price. Cost must therefore
enter the objective for stopping to be meaningful:

```text
search iff expected improvement from another card > inspection cost
```

The Python research package supplies `SellerDeck`, `replay_hidden_cards`,
`fit_empirical_policy`, and `run_hidden_card_study`. The legacy Python and JavaScript
hard-budget planners use commit-or-continue semantics and are separate runtime APIs.

## Reproduce

```bash
make install
.venv/bin/python -m paperkit.cli build
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m paperkit.cli build-paper
npm run check --prefix site
npm run build --prefix site
```

Scientific values originate in Python and flow into `artifacts/`. The manuscript and
site consume those generated artifacts. Registered claims live in
`research/claims.yml`; each reported numerical claim has an executable evaluator.

## Limits

The seller identity rule is title-based and was revised after collection. Seller
domains do not prove independent companies or equivalent products. The model assumes
that a retained offer remains actionable at the observed price and does not measure
revalidation, checkout, or price persistence. A future confirmatory collection must
preregister the identity rule, inspection-cost scenario, and advantage criterion.