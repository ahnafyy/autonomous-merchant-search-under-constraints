from fractions import Fraction

from autonomous_shopping_optimizer.pandora import (
    RecalledSearchHook,
    empirical_reservation_price,
    expected_improvement,
    pandora_cost_table,
    pandora_decision,
    recalled_search_tool_schema,
    run_recalled_search_tool,
    scalarized_inspection_cost,
)


def test_expected_improvement_uses_free_recall() -> None:
    assert expected_improvement(100, [80, 90, 110, 120]) == Fraction(15, 2)


def test_empirical_reservation_price_solves_pandora_equation() -> None:
    samples = [80, 90, 110, 120]
    reservation = empirical_reservation_price(samples, Fraction(15, 2))

    assert reservation == 100
    assert expected_improvement(int(reservation), samples) == Fraction(15, 2)


def test_scalarized_cost_keeps_resource_dimensions_explicit() -> None:
    cost = scalarized_inspection_cost(
        {"time_ms": 5_000, "tokens": 1_200, "api_calls": 2, "api_cost_minor": 3},
        {"time_ms": 5, "tokens": 2, "api_calls": 2, "api_cost_minor": 0},
    )

    assert cost == Fraction(172, 5)


def test_decision_stops_when_hard_budget_blocks_a_positive_value_search() -> None:
    result = pandora_decision(
        current_best_minor=100,
        price_samples=[80, 90, 110, 120],
        resources={"api_calls": 1},
        shadow_prices={},
        remaining_budget={"api_calls": 0},
    )

    assert result["expected_saving_minor"] > result["inspection_cost_minor"]
    assert result["feasible"] is False
    assert result["action"] == "STOP"


def test_cost_table_contains_both_stop_and_search_actions() -> None:
    table = pandora_cost_table()

    assert {row["action"] for row in table["rows"]} == {"SEARCH", "STOP"}
    assert table["time_value_minor_per_minute"] == 500
    assert table["rows"][1]["inspection_cost_minor"] == 1021.0
    for row in table["rows"]:
        assert sum(row["cost_components_minor"].values()) == row["inspection_cost_minor"]


def test_recalled_search_hook_is_host_callable_after_each_offer() -> None:
    hook = RecalledSearchHook(
        price_samples_minor=[80, 90, 110, 120], shadow_prices={"api_calls": 2}
    )

    result = hook(
        current_best_minor=100,
        next_inspection_resources={"api_calls": 1},
        remaining_budget={"api_calls": 1},
    )

    assert result["action"] == "SEARCH"
    assert result["net_value_minor"] == 5.5


def test_recalled_search_tool_schema_and_adapter_are_vendor_neutral() -> None:
    schema = recalled_search_tool_schema()
    result = run_recalled_search_tool(
        {
            "current_best_minor": 100,
            "price_samples_minor": [80, 90, 110, 120],
            "resources": {"api_calls": 1},
            "shadow_prices": {"api_calls": 2.5},
            "remaining_budget": {"api_calls": 1},
        }
    )

    assert schema["name"] == "decide_recalled_search"
    assert result["action"] == "SEARCH"
    assert result["inspection_cost_minor"] == 2.5