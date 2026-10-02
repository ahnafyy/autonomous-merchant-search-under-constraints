from __future__ import annotations

from fractions import Fraction

from autonomous_shopping_optimizer.baselines import (
    buy_first_hidden_card,
    fixed_threshold_hidden_card,
)
from autonomous_shopping_optimizer.catalog_decks import build_seller_decks
from autonomous_shopping_optimizer.replay import (
    SellerCard,
    SellerDeck,
    hidden_card_oracle,
    replay_fixed_depth,
    replay_hidden_cards,
    seller_order,
)


def _deck() -> SellerDeck:
    return SellerDeck(
        deck_id="product-1::size=10",
        product_id="product-1",
        title="Road Shoe",
        option_key="size=10",
        cards=(
            SellerCard("a.example", "a.example", "va", 100, "USD"),
            SellerCard("b.example", "b.example", "vb", 80, "USD"),
            SellerCard("c.example", "c.example", "vc", 90, "USD"),
        ),
    )


def _row(
    seller: str,
    price: int,
    *,
    query: str = "running shoes",
    currency: str = "USD",
    option: str = "10",
    eligible: bool = True,
    product_id: str = "product-1",
    title: str = "Road Shoe",
) -> dict[str, object]:
    return {
        "analysis_eligible": eligible,
        "exclusion_reasons": [] if eligible else ["unavailable"],
        "source": {"query": query},
        "product": {"id": product_id, "title": title, "selected": None},
        "variant": {
            "id": f"variant-{seller}-{option}",
            "title": option,
            "inputs": [{"name": "Size", "label": option}],
        },
        "seller": {"domain": seller},
        "price": {"amount": price, "currency": currency},
    }


def test_fixed_depth_uses_free_recall_and_adds_each_reveal_cost() -> None:
    outcome = replay_fixed_depth(
        _deck(),
        ("a.example", "c.example", "b.example"),
        depth=2,
        inspection_cost=Fraction(1, 100),
    )

    assert outcome.selected_seller_id == "c.example"
    assert outcome.selected_price_minor == 90
    assert outcome.price_regret_minor == 10
    assert outcome.reveal_count == 2
    assert outcome.normalized_item_price == 1
    assert outcome.inspection_cost == Fraction(1, 50)
    assert outcome.normalized_total_cost == Fraction(51, 50)


def test_oracle_is_a_cost_free_offline_bound() -> None:
    oracle = hidden_card_oracle(_deck())

    assert oracle.selected_seller_id == "b.example"
    assert oracle.reveal_count == 0
    assert oracle.normalized_total_cost == Fraction(8, 9)


def test_online_rule_stops_at_hard_reveal_budget() -> None:
    outcome = replay_hidden_cards(
        _deck(),
        ("a.example", "b.example", "c.example"),
        arm="never_stop_early",
        inspection_cost=Fraction(0),
        max_reveals=2,
        should_stop=lambda _state: False,
    )

    assert outcome.reveal_count == 2
    assert outcome.selected_seller_id == "b.example"
    assert outcome.hard_budget_violation is False


def test_buy_first_and_threshold_rules_use_only_revealed_prices() -> None:
    order = ("a.example", "c.example", "b.example")
    buy_first = buy_first_hidden_card(
        _deck(), order, inspection_cost=Fraction(1, 100), max_reveals=3
    )
    threshold = fixed_threshold_hidden_card(
        _deck(),
        order,
        threshold=Fraction(9, 10),
        inspection_cost=Fraction(1, 100),
        max_reveals=3,
    )

    assert buy_first.selected_seller_id == "a.example"
    assert buy_first.reveal_count == 1
    assert threshold.selected_seller_id == "c.example"
    assert threshold.reveal_count == 2


def test_seller_permutations_are_deterministic_and_product_scoped() -> None:
    assert seller_order(_deck(), seed=7, replicate=3) == seller_order(
        _deck(), seed=7, replicate=3
    )
    assert {
        seller_order(_deck(), seed=7, replicate=replicate) for replicate in range(8)
    } != {seller_order(_deck(), seed=7, replicate=0)}


def test_deck_builder_deduplicates_query_hits_and_rejects_mixed_currency() -> None:
    rows = [
        _row("alpha.myshopify.com", 100, query="running shoes"),
        _row("alpha.myshopify.com", 100, query="road shoes"),
        _row("beta.myshopify.com", 90),
        _row("gamma.myshopify.com", 80),
        _row("delta.myshopify.com", 70, currency="EUR"),
        _row("epsilon.myshopify.com", 60, eligible=False),
    ]

    result = build_seller_decks(rows, currency="USD", min_sellers=3)

    assert len(result.decks) == 1
    deck = result.decks[0]
    assert [card.seller_id for card in deck.cards] == [
        "alpha.myshopify.com",
        "beta.myshopify.com",
        "gamma.myshopify.com",
    ]
    assert deck.source_queries == ("road shoes", "running shoes")
    assert result.exclusion_counts == {"non_target_currency": 1, "unavailable": 1}


def test_deck_builder_selects_one_option_per_product_without_using_price() -> None:
    rows = [
        _row("a.example", 100, option="10"),
        _row("b.example", 90, option="10"),
        _row("c.example", 80, option="10"),
        _row("a.example", 1, option="11"),
        _row("b.example", 1, option="11"),
        _row("c.example", 1, option="11"),
        _row("d.example", 1, option="11"),
    ]

    result = build_seller_decks(rows, min_sellers=3)

    assert len(result.decks) == 1
    assert result.decks[0].option_key == "size=11"
    assert len(result.decks[0].cards) == 4
    assert result.exclusion_counts["additional_option_deck"] == 3


def test_deck_builder_merges_exact_model_titles_across_product_ids() -> None:
    rows = [
        _row(
            "a.example",
            100,
            product_id="product-a",
            title="Apple AirPods 4 Wireless Earbuds",
            option="white",
        ),
        _row(
            "b.example",
            90,
            product_id="product-b",
            title="APPLE AIRPODS 4 - WIRELESS EARBUDS",
            option="black",
        ),
        _row(
            "c.example",
            80,
            product_id="product-c",
            title="Apple AirPods 4 Wireless Earbuds",
            option="default",
        ),
    ]

    result = build_seller_decks(
        rows, min_sellers=3, merge_exact_model_titles=True
    )

    assert len(result.decks) == 1
    assert result.decks[0].product_id.startswith("title::apple airpods 4")
    assert result.decks[0].option_key == "product-level-offer"
    assert len(result.decks[0].cards) == 3


def test_deck_builder_does_not_merge_generic_exact_titles() -> None:
    rows = [
        _row("a.example", 100, product_id="product-a", title="Shampoo"),
        _row("b.example", 90, product_id="product-b", title="SHAMPOO"),
        _row("c.example", 80, product_id="product-c", title="shampoo"),
    ]

    result = build_seller_decks(
        rows, min_sellers=3, merge_exact_model_titles=True
    )

    assert result.decks == ()


def test_deck_builder_excludes_declared_multi_configuration_titles() -> None:
    rows = [
        _row(
            seller,
            price,
            product_id=f"product-{seller}",
            title="Dumbbells - multiple weight ranges available",
        )
        for seller, price in (("a.example", 100), ("b.example", 200), ("c.example", 300))
    ]

    result = build_seller_decks(
        rows,
        min_sellers=3,
        merge_exact_model_titles=True,
        excluded_title_phrases=("multiple weight ranges",),
    )

    assert result.decks == ()