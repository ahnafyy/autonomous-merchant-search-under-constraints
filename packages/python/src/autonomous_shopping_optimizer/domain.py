from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from autonomous_shopping_optimizer.permits import ResourceVector

IdentifierScheme = Literal["gtin", "upc", "ean", "isbn", "asin", "mpn"]
StopReason = Literal[
    "purchased",
    "merchants_exhausted",
    "resource_exhausted",
    "price_cap_exceeded",
]


@dataclass(frozen=True)
class ProductIdentifier:
    scheme: IdentifierScheme
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("product identifier value must be non-empty")


@dataclass(frozen=True)
class Product:
    product_id: str
    identifiers: tuple[ProductIdentifier, ...]
    title: str
    variant: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.product_id.strip():
            raise ValueError("product_id must be non-empty")
        if not self.identifiers:
            raise ValueError("an exact product requires at least one identifier")
        if not self.title.strip():
            raise ValueError("product title must be non-empty")
        if any(not key.strip() or not value.strip() for key, value in self.variant):
            raise ValueError("variant keys and values must be non-empty")


@dataclass(frozen=True)
class Merchant:
    merchant_id: str
    name: str
    endpoint_id: str

    def __post_init__(self) -> None:
        for field_name in ("merchant_id", "name", "endpoint_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True)
class Price:
    item_minor: int
    currency: str
    shipping_minor: int | None = None
    tax_minor: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.item_minor, bool) or not isinstance(self.item_minor, int):
            raise ValueError("item_minor must be an integer")
        if self.item_minor <= 0:
            raise ValueError("item_minor must be positive")
        if len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
            raise ValueError("currency must be a three-letter uppercase code")
        for field_name in ("shipping_minor", "tax_minor"):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")

    @property
    def has_landed_price(self) -> bool:
        return self.shipping_minor is not None and self.tax_minor is not None

    @property
    def landed_minor(self) -> int:
        if not self.has_landed_price:
            raise ValueError("landed price requires both shipping and tax")
        assert self.shipping_minor is not None
        assert self.tax_minor is not None
        return self.item_minor + self.shipping_minor + self.tax_minor

    def comparable_minor(self, *, use_landed_price: bool) -> int:
        return self.landed_minor if use_landed_price else self.item_minor


@dataclass(frozen=True)
class Offer:
    product_id: str
    merchant_id: str
    available: bool
    price: Price | None

    def __post_init__(self) -> None:
        if not self.product_id.strip() or not self.merchant_id.strip():
            raise ValueError("offer product_id and merchant_id must be non-empty")
        if self.available and self.price is None:
            raise ValueError("an available offer requires a price")
        if not self.available and self.price is not None:
            raise ValueError("an unavailable offer must not have a price")


@dataclass(frozen=True)
class Query:
    merchant_id: str
    permit: ResourceVector

    def __post_init__(self) -> None:
        if not self.merchant_id.strip():
            raise ValueError("merchant_id must be non-empty")


@dataclass(frozen=True)
class Buy:
    offer: Offer

    def __post_init__(self) -> None:
        if not self.offer.available:
            raise ValueError("cannot buy an unavailable offer")


@dataclass(frozen=True)
class Stop:
    reason: StopReason


ShoppingAction = Query | Buy | Stop