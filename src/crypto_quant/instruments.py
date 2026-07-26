"""Versioned instrument metadata and fail-closed pre-submit order planning."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .canonical import business_hash, canonical_decimal, utc_datetime
from .decimal_math import (
    as_decimal,
    round_down_to_step,
    round_price_down,
    round_price_up,
)
from .errors import ContractError


class MarketType(str, Enum):
    SPOT = "SPOT"
    USDT_PERP = "USDT_PERP"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderPlanStatus(str, Enum):
    READY = "READY"
    NO_TRADE_BELOW_MIN_QUANTITY = "NO_TRADE_BELOW_MIN_QUANTITY"
    NO_TRADE_BELOW_MIN_NOTIONAL = "NO_TRADE_BELOW_MIN_NOTIONAL"


@dataclass(frozen=True)
class InstrumentMetadata:
    schema_version: str
    instrument_id: str
    exchange: str
    market_type: MarketType
    symbol: str
    base_asset: str
    quote_asset: str
    settlement_asset: str
    effective_from: datetime
    effective_to_or_null: Optional[datetime]
    price_tick: Decimal
    quantity_step: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal
    contract_multiplier: Decimal
    supported_order_types: Tuple[str, ...]
    supported_time_in_force: Tuple[str, ...]
    supports_reduce_only: bool
    supports_stop_market: bool
    maker_fee: Decimal
    taker_fee: Decimal
    metadata_source: str

    def __post_init__(self) -> None:
        if not isinstance(self.market_type, MarketType):
            raise ContractError("market_type must use the frozen MarketType enum")
        string_fields = (
            "schema_version",
            "instrument_id",
            "exchange",
            "symbol",
            "base_asset",
            "quote_asset",
            "settlement_asset",
            "metadata_source",
        )
        if any(
            not isinstance(getattr(self, field_name), str)
            or not getattr(self, field_name)
            for field_name in string_fields
        ):
            raise ContractError("instrument identity and source fields must be non-empty")
        if not isinstance(self.supports_reduce_only, bool) or not isinstance(
            self.supports_stop_market,
            bool,
        ):
            raise ContractError("instrument capability flags must be booleans")
        utc_datetime(self.effective_from)
        if self.effective_to_or_null is not None:
            utc_datetime(self.effective_to_or_null)
        decimal_fields = (
            "price_tick",
            "quantity_step",
            "min_quantity",
            "max_quantity",
            "min_notional",
            "contract_multiplier",
            "maker_fee",
            "taker_fee",
        )
        for field_name in decimal_fields:
            object.__setattr__(self, field_name, as_decimal(getattr(self, field_name)))
        if self.effective_to_or_null is not None:
            if self.effective_to_or_null <= self.effective_from:
                raise ContractError("metadata effective_to must follow effective_from")
        if self.instrument_id != (
            f"{self.exchange}:{self.market_type.value}:{self.symbol}"
        ):
            raise ContractError("instrument_id does not match exchange/market/symbol")
        if (
            self.base_asset != "ETH"
            or self.quote_asset != "USDT"
            or self.settlement_asset != "USDT"
        ):
            raise ContractError("V1 InstrumentMetadata is restricted to ETH/USDT")
        if self.market_type is MarketType.SPOT:
            if self.supports_reduce_only:
                raise ContractError("spot metadata cannot advertise reduce-only")
        elif not self.supports_reduce_only:
            raise ContractError("V1 USDT perpetual must support reduce-only")
        if any(
            value <= 0
            for value in (
                self.price_tick,
                self.quantity_step,
                self.min_quantity,
                self.max_quantity,
                self.min_notional,
                self.contract_multiplier,
            )
        ):
            raise ContractError("instrument price/quantity/notional units must be positive")
        if self.min_quantity > self.max_quantity:
            raise ContractError("min_quantity cannot exceed max_quantity")
        if self.min_quantity != round_down_to_step(
            self.min_quantity,
            self.quantity_step,
        ):
            raise ContractError("min_quantity must align to quantity_step")
        if not self.supported_order_types or not self.supported_time_in_force:
            raise ContractError("instrument metadata requires order and TIF capabilities")
        if any(
            not isinstance(value, str) or not value
            for value in self.supported_order_types
        ):
            raise ContractError("supported order types must be non-empty strings")
        if any(
            not isinstance(value, str) or not value
            for value in self.supported_time_in_force
        ):
            raise ContractError("supported time-in-force values must be non-empty strings")
        if len(set(self.supported_order_types)) != len(self.supported_order_types):
            raise ContractError("supported_order_types contains duplicates")
        if len(set(self.supported_time_in_force)) != len(
            self.supported_time_in_force
        ):
            raise ContractError("supported_time_in_force contains duplicates")
        if any(value != value.upper() for value in self.supported_order_types):
            raise ContractError("order type names must be uppercase")
        if any(value != value.upper() for value in self.supported_time_in_force):
            raise ContractError("time-in-force names must be uppercase")
        if not Decimal("0") <= self.maker_fee <= Decimal("1"):
            raise ContractError("maker_fee must be a unit ratio")
        if not Decimal("0") <= self.taker_fee <= Decimal("1"):
            raise ContractError("taker_fee must be a unit ratio")
        if not self.metadata_source:
            raise ContractError("metadata_source is required")

    def is_effective(self, at: datetime) -> bool:
        return self.effective_from <= at and (
            self.effective_to_or_null is None or at < self.effective_to_or_null
        )

    def assert_effective(self, at: datetime) -> None:
        utc_datetime(at)
        if not self.is_effective(at):
            raise ContractError("InstrumentMetadata is not effective at decision time")

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "instrument_id": self.instrument_id,
            "exchange": self.exchange,
            "market_type": self.market_type.value,
            "symbol": self.symbol,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "settlement_asset": self.settlement_asset,
            "effective_from": utc_datetime(self.effective_from),
            "effective_to_or_null": (
                None
                if self.effective_to_or_null is None
                else utc_datetime(self.effective_to_or_null)
            ),
            "price_tick": canonical_decimal(self.price_tick),
            "quantity_step": canonical_decimal(self.quantity_step),
            "min_quantity": canonical_decimal(self.min_quantity),
            "max_quantity": canonical_decimal(self.max_quantity),
            "min_notional": canonical_decimal(self.min_notional),
            "contract_multiplier": canonical_decimal(self.contract_multiplier),
            "supported_order_types": self.supported_order_types,
            "supported_time_in_force": self.supported_time_in_force,
            "supports_reduce_only": self.supports_reduce_only,
            "supports_stop_market": self.supports_stop_market,
            "maker_fee": canonical_decimal(self.maker_fee),
            "taker_fee": canonical_decimal(self.taker_fee),
            "metadata_source": self.metadata_source,
        }

    @property
    def metadata_hash(self) -> str:
        return business_hash(self.business_payload())


class InstrumentMetadataCatalog:
    """Keep every historical metadata interval available for deterministic replay."""

    def __init__(self) -> None:
        self._versions: Dict[str, Tuple[InstrumentMetadata, ...]] = {}

    def register(self, metadata: InstrumentMetadata) -> None:
        versions = self._versions.get(metadata.instrument_id, ())
        if any(item.metadata_hash == metadata.metadata_hash for item in versions):
            return
        for item in versions:
            if _intervals_overlap(item, metadata):
                raise ContractError("InstrumentMetadata effective intervals overlap")
        self._versions[metadata.instrument_id] = tuple(
            sorted(
                versions + (metadata,),
                key=lambda item: item.effective_from,
            )
        )

    def effective_at(
        self,
        instrument_id: str,
        at: datetime,
    ) -> InstrumentMetadata:
        utc_datetime(at)
        matches = tuple(
            item
            for item in self._versions.get(instrument_id, ())
            if item.is_effective(at)
        )
        if len(matches) != 1:
            raise ContractError(
                "exactly one InstrumentMetadata version must be effective"
            )
        return matches[0]

    def versions(self, instrument_id: str) -> Tuple[InstrumentMetadata, ...]:
        return self._versions.get(instrument_id, ())


@dataclass(frozen=True)
class RoundedOrderPlan:
    instrument_id: str
    metadata_hash: str
    side: OrderSide
    order_type: str
    time_in_force_or_null: Optional[str]
    risk_increasing: bool
    reduce_only: bool
    requested_quantity: Decimal
    rounded_quantity: Decimal
    requested_price_or_null: Optional[Decimal]
    rounded_price_or_null: Optional[Decimal]
    notional_reference_price: Decimal
    rounded_notional: Decimal
    status: OrderPlanStatus
    is_dust: bool
    was_clamped_to_max_quantity: bool
    was_clamped_to_approved_notional: bool

    @property
    def tradable(self) -> bool:
        return self.status is OrderPlanStatus.READY

    @property
    def plan_hash(self) -> str:
        return business_hash(
            {
                "instrument_id": self.instrument_id,
                "metadata_hash": self.metadata_hash,
                "side": self.side.value,
                "order_type": self.order_type,
                "time_in_force_or_null": self.time_in_force_or_null,
                "risk_increasing": self.risk_increasing,
                "reduce_only": self.reduce_only,
                "requested_quantity": canonical_decimal(self.requested_quantity),
                "rounded_quantity": canonical_decimal(self.rounded_quantity),
                "requested_price_or_null": (
                    None
                    if self.requested_price_or_null is None
                    else canonical_decimal(self.requested_price_or_null)
                ),
                "rounded_price_or_null": (
                    None
                    if self.rounded_price_or_null is None
                    else canonical_decimal(self.rounded_price_or_null)
                ),
                "notional_reference_price": canonical_decimal(
                    self.notional_reference_price
                ),
                "rounded_notional": canonical_decimal(self.rounded_notional),
                "status": self.status.value,
                "is_dust": self.is_dust,
                "was_clamped_to_max_quantity": self.was_clamped_to_max_quantity,
                "was_clamped_to_approved_notional": (
                    self.was_clamped_to_approved_notional
                ),
            }
        )


def plan_order(
    *,
    metadata: InstrumentMetadata,
    decision_time: datetime,
    side: OrderSide,
    order_type: str,
    time_in_force_or_null: Optional[str],
    requested_quantity: Any,
    requested_price_or_null: Optional[Any],
    notional_reference_price: Any,
    risk_increasing: bool,
    reduce_only: bool,
    approved_notional_usdt_or_null: Optional[Any],
) -> RoundedOrderPlan:
    """Round once at the submit boundary without ever increasing approved risk."""

    metadata.assert_effective(decision_time)
    if not isinstance(side, OrderSide):
        raise ContractError("side must use the frozen OrderSide enum")
    if not isinstance(risk_increasing, bool) or not isinstance(reduce_only, bool):
        raise ContractError("risk and reduce-only flags must be booleans")
    if not isinstance(order_type, str) or not order_type:
        raise ContractError("order type must be a non-empty string")
    normalized_order_type = order_type.upper()
    if normalized_order_type not in metadata.supported_order_types:
        raise ContractError("order type is not supported by effective metadata")
    if normalized_order_type == "STOP_MARKET" and not metadata.supports_stop_market:
        raise ContractError("effective metadata does not support stop-market")
    if time_in_force_or_null is not None and (
        not isinstance(time_in_force_or_null, str) or not time_in_force_or_null
    ):
        raise ContractError("time in force must be null or a non-empty string")
    normalized_tif = (
        None if time_in_force_or_null is None else time_in_force_or_null.upper()
    )
    if normalized_order_type == "LIMIT":
        if normalized_tif not in metadata.supported_time_in_force:
            raise ContractError("LIMIT order requires a supported time in force")
        if requested_price_or_null is None:
            raise ContractError("LIMIT order requires a requested price")
    else:
        if normalized_tif is not None:
            raise ContractError("non-LIMIT order must not carry time in force")
        if requested_price_or_null is not None:
            raise ContractError("non-LIMIT order must not carry a requested price")
    if metadata.market_type is MarketType.SPOT and reduce_only:
        raise ContractError("spot order cannot set exchange reduce-only")
    if reduce_only and risk_increasing:
        raise ContractError("reduce-only order cannot be risk increasing")
    if (
        metadata.market_type is MarketType.USDT_PERP
        and not risk_increasing
        and not reduce_only
    ):
        raise ContractError("perpetual risk reduction must set reduce-only")

    requested_qty = as_decimal(requested_quantity)
    if requested_qty <= 0:
        raise ContractError("requested order quantity must be positive")
    reference_price = as_decimal(notional_reference_price)
    if reference_price <= 0:
        raise ContractError("notional reference price must be positive")
    requested_price = (
        None
        if requested_price_or_null is None
        else as_decimal(requested_price_or_null)
    )
    rounded_price = _round_limit_price(
        side=side,
        requested_price=requested_price,
        risk_increasing=risk_increasing,
        price_tick=metadata.price_tick,
    )
    notional_price = rounded_price or reference_price

    max_quantity = round_down_to_step(
        metadata.max_quantity,
        metadata.quantity_step,
    )
    quantity = round_down_to_step(
        min(requested_qty, max_quantity),
        metadata.quantity_step,
    )
    clamped_max = quantity < round_down_to_step(
        requested_qty,
        metadata.quantity_step,
    )
    clamped_notional = False
    if risk_increasing:
        if approved_notional_usdt_or_null is None:
            raise ContractError("risk-increasing order requires approved notional")
        approved_notional = as_decimal(approved_notional_usdt_or_null)
        if approved_notional <= 0:
            raise ContractError("approved notional must be positive")
        notional_quantity_cap = round_down_to_step(
            approved_notional
            / (notional_price * metadata.contract_multiplier),
            metadata.quantity_step,
        )
        if quantity > notional_quantity_cap:
            quantity = notional_quantity_cap
            clamped_notional = True

    rounded_notional = (
        quantity * notional_price * metadata.contract_multiplier
    )
    if quantity < metadata.min_quantity:
        status = OrderPlanStatus.NO_TRADE_BELOW_MIN_QUANTITY
    elif rounded_notional < metadata.min_notional:
        status = OrderPlanStatus.NO_TRADE_BELOW_MIN_NOTIONAL
    else:
        status = OrderPlanStatus.READY
    return RoundedOrderPlan(
        instrument_id=metadata.instrument_id,
        metadata_hash=metadata.metadata_hash,
        side=side,
        order_type=normalized_order_type,
        time_in_force_or_null=normalized_tif,
        risk_increasing=risk_increasing,
        reduce_only=reduce_only,
        requested_quantity=requested_qty,
        rounded_quantity=quantity,
        requested_price_or_null=requested_price,
        rounded_price_or_null=rounded_price,
        notional_reference_price=reference_price,
        rounded_notional=rounded_notional,
        status=status,
        is_dust=not risk_increasing and status is not OrderPlanStatus.READY,
        was_clamped_to_max_quantity=clamped_max,
        was_clamped_to_approved_notional=clamped_notional,
    )


def instrument_metadata_from_payload(
    payload: Dict[str, Any],
    *,
    schema_version: str,
) -> InstrumentMetadata:
    """Parse the frozen JSON fixture shape without accepting silent extra fields."""

    expected_fields = {
        "instrument_id",
        "exchange",
        "market_type",
        "symbol",
        "base_asset",
        "quote_asset",
        "settlement_asset",
        "effective_from",
        "effective_to_or_null",
        "price_tick",
        "quantity_step",
        "min_quantity",
        "max_quantity",
        "min_notional",
        "contract_multiplier",
        "supported_order_types",
        "supported_time_in_force",
        "supports_reduce_only",
        "supports_stop_market",
        "maker_fee",
        "taker_fee",
        "metadata_source",
    }
    if set(payload) != expected_fields:
        missing = sorted(expected_fields - set(payload))
        extra = sorted(set(payload) - expected_fields)
        raise ContractError(
            f"InstrumentMetadata fields mismatch; missing={missing}, extra={extra}"
        )
    return InstrumentMetadata(
        schema_version=schema_version,
        instrument_id=payload["instrument_id"],
        exchange=payload["exchange"],
        market_type=MarketType(payload["market_type"]),
        symbol=payload["symbol"],
        base_asset=payload["base_asset"],
        quote_asset=payload["quote_asset"],
        settlement_asset=payload["settlement_asset"],
        effective_from=_parse_utc_datetime(payload["effective_from"]),
        effective_to_or_null=(
            None
            if payload["effective_to_or_null"] is None
            else _parse_utc_datetime(payload["effective_to_or_null"])
        ),
        price_tick=payload["price_tick"],
        quantity_step=payload["quantity_step"],
        min_quantity=payload["min_quantity"],
        max_quantity=payload["max_quantity"],
        min_notional=payload["min_notional"],
        contract_multiplier=payload["contract_multiplier"],
        supported_order_types=tuple(payload["supported_order_types"]),
        supported_time_in_force=tuple(payload["supported_time_in_force"]),
        supports_reduce_only=payload["supports_reduce_only"],
        supports_stop_market=payload["supports_stop_market"],
        maker_fee=payload["maker_fee"],
        taker_fee=payload["taker_fee"],
        metadata_source=payload["metadata_source"],
    )


def _round_limit_price(
    *,
    side: OrderSide,
    requested_price: Optional[Decimal],
    risk_increasing: bool,
    price_tick: Decimal,
) -> Optional[Decimal]:
    if requested_price is None:
        return None
    if risk_increasing:
        return (
            round_price_down(requested_price, price_tick)
            if side is OrderSide.BUY
            else round_price_up(requested_price, price_tick)
        )
    return (
        round_price_up(requested_price, price_tick)
        if side is OrderSide.BUY
        else round_price_down(requested_price, price_tick)
    )


def _intervals_overlap(
    left: InstrumentMetadata,
    right: InstrumentMetadata,
) -> bool:
    left_end = left.effective_to_or_null
    right_end = right.effective_to_or_null
    return (
        (right_end is None or left.effective_from < right_end)
        and (left_end is None or right.effective_from < left_end)
    )


def _parse_utc_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError("metadata timestamps must be UTC strings ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("metadata timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError("metadata timestamp must be UTC")
    return parsed
