# Research Question

## The Practical Problem

An agent that shops on a user's behalf can retain the best seller offer it has found
while deciding whether to inspect another seller. Another inspection can improve the
retained price, but it costs time, calls, money, or user attention.

An always-search agent opens every available seller card, even when the expected
saving from the next card is smaller than its cost. This project asks whether an
adaptive stop-or-continue rule can avoid those unproductive inspections without
giving up worthwhile price improvements.

## Research Question

**When should an autonomous shopping agent stop inspecting sellers and buy the best
offer it has retained?**

The deliverable is a recall-aware Pandora-search rule: given a retained best offer,
the likely value of unopened sellers, and the cost of another inspection, should the
agent inspect again or buy now?

## Why This Is Answerable Now

Shopify Global Catalog provides seller offers for the same product in one structured
response, making contemporaneous seller decks observable. The Shopify stratum uses
the recovered complete 39-query prefix of a deeper frozen collection; it does not
silently treat its nine uncollected planned queries as absent. This can remove discovery
work inside the graph it covers, but the collection does not establish universal
merchant coverage. A separate UCP direct-merchant panel documents a fragmented,
partially reachable catalog surface and collection discontinuities; it is not pooled
with the Shopify replay data.

## Benchmark

An episode is one product deck with seller cards in one currency. A card reveals a
seller and price. The agent retains the cheapest revealed card, then either buys that
best offer or pays a declared inspection cost to reveal another card. Product decks,
not seller-order permutations, are the independent units. Both online policies face
the same deterministic seller orders and full deck horizon. Search-all reveals every
card and pays every declared inspection cost; adaptive stopping may buy after any
reveal. Held-out seller prices remain hidden from both online policies.

## Policies Compared

| Arm | Role |
| --- | --- |
| Search all | Online control: reveal every available seller and pay every inspection cost |
| Adaptive stopping | Recall-aware dynamic policy fitted only on calibration decks |

## Primary Outcome

Normalized total acquisition cost: retained best item price plus declared inspection
cost, compared between adaptive stopping and costed search-all using product-clustered
paired bootstrap intervals. The inspection-cost grid is sensitivity analysis, not
observed Shopify billing.

## Falsifiers

- A comparative advantage is not reportable unless its product-clustered held-out
  interval excludes zero under a preregistered inspection-cost scenario.
- Seller-order permutations are not independent evidence; the product deck is the
  resampling unit.
- If inspection cost is zero and recall is free, every feasible card should be opened;
  failure indicates an implementation error.
- A product identity rule introduced after collection makes the resulting analysis
  exploratory until reproduced on a preregistered collection.

## Non-Goals

- Cross-episode bandit learning during the held-out evaluation.
- Parallel queries, strategic merchant behavior, and personalized pricing.
- Universal merchant coverage by any aggregator.
- Checkout persistence, shipping, tax, returns, or paid revalidation.
- Third-party historical price datasets.
- Multi-product baskets and multi-attribute utility. Shipping, tax, and returns
  enter only where landed price is completely observed.
- Any claim that the merchants observed here represent retail commerce generally.
