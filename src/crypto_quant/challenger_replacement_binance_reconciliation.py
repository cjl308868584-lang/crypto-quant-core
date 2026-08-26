"""Pure three-way reconciliation for fixed Binance private evidence."""

from dataclasses import dataclass
from decimal import Decimal
import hashlib, json
from types import MappingProxyType
from typing import Mapping

from .canonical import canonical_decimal, canonical_json
from .challenger_replacement_binance_private_lifecycle import _document, _number
_FACT_KEYS = frozenset({
    "product", "signed_quantity", "average_entry_price_or_null",
    "realized_pnl", "unrealized_pnl", "cumulative_fee", "funding",
    "wallet_balance", "available_balance", "open_order_count",
    "protective_stop_client_id_or_null", "fill_ids",
})
_ORDER_KEYS = frozenset({"symbol", "orderId", "clientOrderId", "status"})
_TRADE_KEYS = frozenset({
    "symbol", "id", "orderId", "qty", "price", "quoteQty", "commission",
    "commissionAsset", "realizedPnl", "time", "buyer",
})
_INCOME_KEYS = frozenset({
    "tranId", "symbol", "incomeType", "income", "asset", "time",
})
_ALGO_KEYS = frozenset({
    "algoId", "clientAlgoId", "symbol", "algoStatus", "side",
    "positionSide", "quantity", "triggerPrice", "workingType", "reduceOnly",
    "closePosition", "algoType", "orderType",
})
_AUTHORITY = {"network_requests": 0, "orders": 0, "state_writes": 0}
class BinanceReconciliationError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class EventProjection:
    values: Mapping[str, object]


@dataclass(frozen=True)
class VenueProjection:
    values: Mapping[str, object]


@dataclass(frozen=True)
class LedgerProjection:
    values: Mapping[str, object]


def _fail(reason, error=None):
    failure = BinanceReconciliationError(reason)
    if error is None:
        raise failure
    raise failure from error


def _decimal(value, *, signed=True, nullable=False):
    if nullable and value is None:
        return None
    try:
        number = _number(value, signed=signed)
    except ValueError as error:
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
    return canonical_decimal(number)


def _facts(value):
    if not isinstance(value, Mapping) or frozenset(value) != _FACT_KEYS:
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    product = value.get("product")
    if product not in {"SPOT", "PERPETUAL"}:
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    result = {
        "product": product,
        "signed_quantity": _decimal(value.get("signed_quantity")),
        "average_entry_price_or_null": _decimal(
            value.get("average_entry_price_or_null"), nullable=True,
        ),
        "realized_pnl": _decimal(value.get("realized_pnl")),
        "unrealized_pnl": _decimal(value.get("unrealized_pnl")),
        "cumulative_fee": _decimal(value.get("cumulative_fee"), signed=False),
        "funding": _decimal(value.get("funding")),
        "wallet_balance": _decimal(value.get("wallet_balance"), signed=False),
        "available_balance": _decimal(
            value.get("available_balance"), signed=False,
        ),
    }
    count, fill_ids = value.get("open_order_count"), value.get("fill_ids")
    client = value.get("protective_stop_client_id_or_null")
    if (isinstance(count, bool) or not isinstance(count, int) or count < 0
            or not isinstance(fill_ids, list)
            or any(isinstance(item, bool) or not isinstance(item, int)
                   or item < 0 for item in fill_ids)
            or fill_ids != sorted(set(fill_ids))
            or (client is not None and (not isinstance(client, str)
                or len(client) != 36 or not client.startswith("cq77")))):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    result.update(open_order_count=count,
                  protective_stop_client_id_or_null=client,
                  fill_ids=list(fill_ids))
    if ((Decimal(result["signed_quantity"]) == 0)
            != (result["average_entry_price_or_null"] is None)):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    return result


def _unique(documents, key, conflict):
    if not isinstance(documents, tuple):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    result = {}
    for raw in documents:
        try:
            item = _document(raw)
        except ValueError as error:
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
        identity = item.get(key)
        if isinstance(identity, bool) or not isinstance(identity, int) or identity < 0:
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        frozen = canonical_json(item)
        if identity in result and result[identity] != frozen:
            _fail(conflict)
        result[identity] = frozen
    return [json.loads(result[key]) for key in sorted(result)]


def _venue(event, orders, trades, account, position, incomes, algos):
    order_values = _unique(
        orders, "orderId", "BINANCE_RECONCILIATION_CONFLICTING_ORDER"
    )
    for order in order_values:
        if (frozenset(order) != _ORDER_KEYS or order["symbol"] != "ETHUSDT"
                or not isinstance(order["clientOrderId"], str)
                or order["status"] not in {
                    "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED",
                    "EXPIRED", "REJECTED",
                }):
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    trade_values = _unique(
        trades, "id", "BINANCE_RECONCILIATION_CONFLICTING_FILL"
    )
    fee = realized = weighted = total = Decimal("0")
    for trade in trade_values:
        if (frozenset(trade) != _TRADE_KEYS or trade["symbol"] != "ETHUSDT"
                or not isinstance(trade["buyer"], bool)
                or not isinstance(trade["commissionAsset"], str)):
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        quantity = _number(trade["qty"], positive=True)
        price = _number(trade["price"], positive=True)
        if _number(trade["quoteQty"]) != quantity * price:
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        total += quantity
        weighted += quantity * price
        fee += _number(trade["commission"])
        realized += _number(trade["realizedPnl"], signed=True)
    try:
        account_value, position_value = _document(account), _document(position)
    except ValueError as error:
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
    if (frozenset(account_value) != {"totalWalletBalance", "availableBalance"}
            or frozenset(position_value) != {
                "symbol", "positionSide", "positionAmt", "entryPrice",
                "unRealizedProfit",
            } or position_value["symbol"] != "ETHUSDT"
            or position_value["positionSide"] != "BOTH"):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    signed_quantity = _number(position_value["positionAmt"], signed=True)
    entry = _number(position_value["entryPrice"])
    income_values = _unique(
        incomes, "tranId", "BINANCE_RECONCILIATION_CONFLICTING_FUNDING"
    )
    funding = Decimal("0")
    for income in income_values:
        if (frozenset(income) != _INCOME_KEYS
                or income["symbol"] != "ETHUSDT"
                or income["incomeType"] != "FUNDING_FEE"
                or income["asset"] != "USDT"):
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        funding += _number(income["income"], signed=True)
    algo_values = _unique(
        algos, "algoId", "BINANCE_RECONCILIATION_CONFLICTING_STOP"
    )
    active = []
    for algo in algo_values:
        if frozenset(algo) != _ALGO_KEYS or algo["symbol"] != "ETHUSDT":
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        if algo["algoStatus"] == "NEW":
            active.append(algo)
    stop = None
    if signed_quantity < 0:
        if len(active) != 1:
            _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
        algo = active[0]
        if (algo["side"] != "BUY" or algo["positionSide"] != "BOTH"
                or _number(algo["quantity"], positive=True) != -signed_quantity
                or algo["workingType"] != "MARK_PRICE"
                or algo["reduceOnly"] is not True
                or algo["closePosition"] is not False
                or algo["algoType"] != "CONDITIONAL"
                or algo["orderType"] != "STOP_MARKET"):
            _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
        stop = algo["clientAlgoId"]
    elif active:
        _fail("VENUE_LOCAL_POSITION_MISMATCH")
    average = None if signed_quantity == 0 else canonical_decimal(entry)
    return {
        "product": event["product"],
        "signed_quantity": canonical_decimal(signed_quantity),
        "average_entry_price_or_null": average,
        "realized_pnl": canonical_decimal(realized),
        "unrealized_pnl": canonical_decimal(
            _number(position_value["unRealizedProfit"], signed=True)
        ),
        "cumulative_fee": canonical_decimal(fee),
        "funding": canonical_decimal(funding),
        "wallet_balance": canonical_decimal(
            _number(account_value["totalWalletBalance"])
        ),
        "available_balance": canonical_decimal(
            _number(account_value["availableBalance"])
        ),
        "open_order_count": sum(
            order["status"] in {"NEW", "PARTIALLY_FILLED"}
            for order in order_values
        ),
        "protective_stop_client_id_or_null": stop,
        "fill_ids": [trade["id"] for trade in trade_values],
    }


def _identity(document):
    core = dict(document)
    core.pop("reconciliation_id", None)
    return "binance_reconciliation_" + hashlib.sha256(
        canonical_json(core).encode()
    ).hexdigest()


def reconcile_binance_private_state(*, event_projection, order_documents,
                                    trade_documents, account_document,
                                    position_document, income_documents,
                                    algo_documents):
    """Require event, venue and ledger projections to agree exactly."""
    if not isinstance(event_projection, Mapping) or frozenset(event_projection) != (
        _FACT_KEYS | {"ledger_projection"}
    ):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    event = EventProjection(_facts({key: event_projection[key]
                                   for key in _FACT_KEYS}))
    ledger = LedgerProjection(_facts(event_projection["ledger_projection"]))
    if event.values != ledger.values:
        _fail("BINANCE_LEDGER_PROJECTION_MISMATCH")
    venue = VenueProjection(_venue(
        event.values, order_documents, trade_documents, account_document,
        position_document, income_documents, algo_documents,
    ))
    if event.values != venue.values:
        _fail("VENUE_LOCAL_POSITION_MISMATCH")
    document = {
        "$schema": "./challenger-replacement-binance-reconciliation-v1.schema.json",
        "schema_version": "1.0.0",
        "status": "BINANCE_PRIVATE_RECONCILIATION_MATCHED",
        "event_projection": dict(event.values),
        "venue_projection": dict(venue.values),
        "ledger_projection": dict(ledger.values),
        "authority": _AUTHORITY,
    }
    document["reconciliation_id"] = _identity(document)
    return (canonical_json(document) + "\n").encode()


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def load_binance_reconciliation_bytes(data):
    """Strictly replay one matched reconciliation artifact."""
    try:
        if not isinstance(data, bytes) or not data.endswith(b"\n"):
            raise ValueError
        document = _document(data[:-1])
        if (frozenset(document) != {
                "$schema", "schema_version", "reconciliation_id", "status",
                "event_projection", "venue_projection", "ledger_projection",
                "authority",
            } or document["$schema"]
                != "./challenger-replacement-binance-reconciliation-v1.schema.json"
                or document["schema_version"] != "1.0.0"
                or document["status"] != "BINANCE_PRIVATE_RECONCILIATION_MATCHED"
                or document["authority"] != _AUTHORITY
                or document["reconciliation_id"] != _identity(document)):
            raise ValueError
        event = _facts(document["event_projection"])
        venue = _facts(document["venue_projection"])
        ledger = _facts(document["ledger_projection"])
        if event != venue or venue != ledger:
            raise ValueError
        return _freeze(document)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, BinanceReconciliationError):
            raise
        _fail("BINANCE_RECONCILIATION_ARTIFACT_INVALID", error)
