from __future__ import annotations

import pytest
from autonomous_shopping_optimizer.domain import (
    Buy,
    Offer,
    Price,
    Product,
    ProductIdentifier,
)


def test_product_requires_an_exact_identifier() -> None:
    with pytest.raises(ValueError, match="at least one identifier"):
        Product(product_id="sku-1", identifiers=(), title="Example")

    product = Product(
        product_id="sku-1",
        identifiers=(ProductIdentifier("upc", "012345678905"),),
        title="Example",
        variant=(("color", "black"),),
    )
    assert product.identifiers[0].value == "012345678905"


def test_price_does_not_imply_landed_price_when_components_are_missing() -> None:
    price = Price(item_minor=10_000, currency="USD")

    assert price.comparable_minor(use_landed_price=False) == 10_000
    assert price.has_landed_price is False
    with pytest.raises(ValueError, match="requires both shipping and tax"):
        price.comparable_minor(use_landed_price=True)


def test_complete_landed_price_is_explicit() -> None:
    price = Price(
        item_minor=10_000,
        currency="USD",
        shipping_minor=500,
        tax_minor=825,
    )

    assert price.has_landed_price is True
    assert price.landed_minor == 11_325


def test_offer_availability_and_price_are_consistent() -> None:
    with pytest.raises(ValueError, match="available offer requires"):
        Offer(product_id="sku-1", merchant_id="merchant-a", available=True, price=None)
    with pytest.raises(ValueError, match="unavailable offer must not"):
        Offer(
            product_id="sku-1",
            merchant_id="merchant-a",
            available=False,
            price=Price(100, "USD"),
        )


def test_buy_requires_an_available_offer() -> None:
    unavailable = Offer(
        product_id="sku-1",
        merchant_id="merchant-a",
        available=False,
        price=None,
    )

    with pytest.raises(ValueError, match="cannot buy"):
        Buy(unavailable)