"""Pure Binance-specific order preparation and observation normalization."""

from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Mapping

from .canonical import canonical_decimal, canonical_json
from .challenger_replacement_binance_private_contract import (
    BinancePrivateActivation,
)


_HEX = frozenset("0123456789abcdef")
_PRODUCT_ACTION = {
    ("SPOT", "OPEN_LONG"): ("BUY", False, "SPOT_ORDER_QUERY"),
    ("SPOT", "CLOSE_LONG"): ("SELL", False, "SPOT_ORDER_QUERY"),
    ("PERPETUAL", "OPEN_SHORT"): ("SELL", False, "FUTURES_ORDER_QUERY"),
    ("PERPETUAL", "CLOSE_SHORT"): ("BUY", True, "FUTURES_ORDER_QUERY"),
}
_ATTEMPT_KEYS = frozenset({
    "opportunity_id", "intent_id", "block_id", "product", "action",
    "side", "reduce_only", "quantity", "attempt_ordinal", "symbol",
    "venue_client_order_id", "activation_id", "preflight_id",
    "unsigned_intent_sha256", "required_first_endpoint", "send_permitted",
})
_SPOT_ORDER_KEYS = frozenset({
    "symbol", "orderId", "clientOrderId", "price", "origQty",
    "executedQty", "cummulativeQuoteQty", "status", "timeInForce", "type",
    "side", "transactTime",
})
_FUTURES_ORDER_KEYS = frozenset({
    "symbol", "orderId", "clientOrderId", "avgPrice", "origQty",
    "executedQty", "cumQuote", "status", "type", "side", "positionSide",
    "reduceOnly", "updateTime",
})
_SPOT_TRADE_KEYS = frozenset({
    "symbol", "id", "orderId", "qty", "price", "quoteQty", "commission",
    "commissionAsset", "time", "isBuyer",
})
_FUTURES_TRADE_KEYS = frozenset({
    "symbol", "id", "orderId", "qty", "price", "quoteQty", "commission",
    "commissionAsset", "realizedPnl", "time", "buyer",
})


class BinancePrivateLifecycleError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _fail(reason, error=None):
    failure = BinancePrivateLifecycleError(reason)
    if error is None:
        raise failure
    raise failure from error


def _hash(value, length=64):
    return (isinstance(value, str) and len(value) == length
            and not set(value) - _HEX)


def _identity(value):
    return isinstance(value, str) and 1 <= len(value) <= 256


def _number(value, *, positive=False, signed=False):
    if not isinstance(value, str):
        _fail("BINANCE_ORDER_OBSERVATION_INVALID")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        _fail("BINANCE_ORDER_OBSERVATION_INVALID", error)
    if (not number.is_finite() or (not signed and number < 0)
            or (positive and number <= 0)):
        _fail("BINANCE_ORDER_OBSERVATION_INVALID")
    return number


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("BINANCE_ORDER_OBSERVATION_INVALID")
        result[key] = value
    return result


def _document(data):
    try:
        if not isinstance(data, bytes) or not 1 <= len(data) <= 1_048_576:
            raise ValueError
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_pairs)
        if not isinstance(value, dict) or canonical_json(value).encode() != data:
            raise ValueError
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        if isinstance(error, BinancePrivateLifecycleError):
            raise
        _fail("BINANCE_ORDER_OBSERVATION_INVALID", error)


def derive_binance_client_order_id(*, plan_hash, block_id, intent_id,
                                   attempt_ordinal, product):
    """Derive the fixed 36-character venue alias for a full internal intent."""
    if (not _hash(plan_hash) or not _identity(block_id)
            or not _identity(intent_id) or product not in {"SPOT", "PERPETUAL"}
            or isinstance(attempt_ordinal, bool)
            or not isinstance(attempt_ordinal, int)
            or not 1 <= attempt_ordinal <= (1 << 53) - 1):
        _fail("BINANCE_ORDER_INTENT_INVALID")
    body = canonical_json({
        "attempt_ordinal": attempt_ordinal, "block_id": block_id,
        "intent_id": intent_id, "plan_hash": plan_hash, "product": product,
    }).encode()
    return "cq77" + hashlib.sha256(body).hexdigest()[:32]


def prepare_binance_order_attempt(*, intent, projection, preflight,
                                  activation):
    """Prepare one query-first order attempt without signing or sending it."""
    intent_keys = frozenset({
        "opportunity_id", "intent_id", "block_id", "product", "action",
        "quantity", "attempt_ordinal", "unsigned_intent_sha256",
    })
    projection_keys = frozenset({
        "plan_hash", "active_product_or_null", "unresolved_client_order_ids",
        "proven_absent_client_order_ids",
    })
    try:
        if (not isinstance(intent, Mapping) or frozenset(intent) != intent_keys
                or not isinstance(projection, Mapping)
                or frozenset(projection) != projection_keys
                or not isinstance(preflight, Mapping)
                or not isinstance(activation, BinancePrivateActivation)):
            raise ValueError
        mapping = _PRODUCT_ACTION[(intent["product"], intent["action"])]
        side, reduce_only, query_endpoint = mapping
        quantity = canonical_decimal(intent["quantity"])
        if quantity == "0" or quantity.startswith("-"):
            raise ValueError
        if (not _identity(intent["opportunity_id"])
                or not _identity(intent["intent_id"])
                or not _identity(intent["block_id"])
                or intent["block_id"] != activation.block_id
                or not _hash(intent["unsigned_intent_sha256"])
                or not _hash(projection["plan_hash"])
                or isinstance(intent["attempt_ordinal"], bool)
                or not isinstance(intent["attempt_ordinal"], int)
                or not 1 <= intent["attempt_ordinal"] <= (1 << 53) - 1
                or preflight.get("status")
                != "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT"
                or not _identity(preflight.get("preflight_id"))
                or preflight.get("configuration") not in (
                    {"position_mode": "ONE_WAY", "asset_mode": "SINGLE_ASSET",
                     "symbol": "ETHUSDT", "margin_type": "ISOLATED",
                     "leverage": 1, "auto_add_margin": False},
                    {"position_mode": "ONE_WAY", "asset_mode": "SINGLE_ASSET",
                     "symbol": "ETHUSDT", "margin_type": "ISOLATED",
                     "leverage": 2, "auto_add_margin": False},
                )):
            raise ValueError
        active = projection["active_product_or_null"]
        unresolved = projection["unresolved_client_order_ids"]
        absent = projection["proven_absent_client_order_ids"]
        if (active not in (None, "SPOT", "PERPETUAL")
                or not isinstance(unresolved, list)
                or not isinstance(absent, list)
                or any(not isinstance(item, str) for item in unresolved + absent)):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_ORDER_INTENT_INVALID", error)
    if unresolved:
        _fail("UNRESOLVED_ECONOMIC_ORDER_UNKNOWN")
    if ((intent["action"] in {"OPEN_LONG", "OPEN_SHORT"}
         and active not in (None, intent["product"]))
            or (intent["action"] in {"CLOSE_LONG", "CLOSE_SHORT"}
                and active != intent["product"])):
        _fail("BINANCE_PRODUCT_MUTUAL_EXCLUSION_BLOCKED")
    client_id = derive_binance_client_order_id(
        plan_hash=projection["plan_hash"], block_id=intent["block_id"],
        intent_id=intent["intent_id"],
        attempt_ordinal=intent["attempt_ordinal"], product=intent["product"],
    )
    if intent["attempt_ordinal"] > 1 and client_id not in absent:
        _fail("BINANCE_ORDER_ABSENCE_NOT_PROVEN")
    return {
        "opportunity_id": intent["opportunity_id"],
        "intent_id": intent["intent_id"], "block_id": intent["block_id"],
        "product": intent["product"], "action": intent["action"],
        "side": side, "reduce_only": reduce_only, "quantity": quantity,
        "attempt_ordinal": intent["attempt_ordinal"], "symbol": "ETHUSDT",
        "venue_client_order_id": client_id,
        "activation_id": activation.activation_id,
        "preflight_id": preflight["preflight_id"],
        "unsigned_intent_sha256": intent["unsigned_intent_sha256"],
        "required_first_endpoint": query_endpoint,
        "send_permitted": client_id in absent,
    }


def _valid_attempt(value):
    if (not isinstance(value, Mapping)
            or frozenset(value) != _ATTEMPT_KEYS
            or (value.get("product"), value.get("action")) not in _PRODUCT_ACTION):
        return False
    side, reduce_only, query = _PRODUCT_ACTION[
        (value["product"], value["action"])
    ]
    try:
        quantity = canonical_decimal(value["quantity"])
    except (TypeError, ValueError):
        return False
    client_id = value.get("venue_client_order_id")
    return (value.get("symbol") == "ETHUSDT"
            and value.get("side") == side
            and value.get("reduce_only") is reduce_only
            and value.get("required_first_endpoint") == query
            and isinstance(value.get("send_permitted"), bool)
            and quantity == value.get("quantity") and quantity != "0"
            and isinstance(value.get("attempt_ordinal"), int)
            and not isinstance(value.get("attempt_ordinal"), bool)
            and 1 <= value["attempt_ordinal"] <= (1 << 53) - 1
            and all(_identity(value.get(key)) for key in {
                "opportunity_id", "intent_id", "block_id", "activation_id",
                "preflight_id",
            })
            and _hash(value.get("unsigned_intent_sha256"))
            and isinstance(client_id, str) and len(client_id) == 36
            and client_id.startswith("cq77")
            and not set(client_id[4:]) - _HEX)


def _validate_order(attempt, order):
    product = attempt["product"]
    expected = _SPOT_ORDER_KEYS if product == "SPOT" else _FUTURES_ORDER_KEYS
    if frozenset(order) != expected:
        _fail("BINANCE_ORDER_OBSERVATION_INVALID")
    integer = "transactTime" if product == "SPOT" else "updateTime"
    if (order["symbol"] != "ETHUSDT"
            or order["clientOrderId"] != attempt["venue_client_order_id"]
            or order["side"] != attempt["side"]
            or order["type"] != "MARKET"
            or isinstance(order["orderId"], bool)
            or not isinstance(order["orderId"], int) or order["orderId"] <= 0
            or isinstance(order[integer], bool)
            or not isinstance(order[integer], int) or order[integer] < 0):
        _fail("BINANCE_ORDER_IDENTITY_MISMATCH")
    if product == "SPOT":
        if order["timeInForce"] != "GTC":
            _fail("BINANCE_ORDER_OBSERVATION_INVALID")
        _number(order["price"]); _number(order["cummulativeQuoteQty"])
    else:
        if (order["positionSide"] != "BOTH"
                or order["reduceOnly"] is not attempt["reduce_only"]):
            _fail("BINANCE_ORDER_IDENTITY_MISMATCH")
        _number(order["avgPrice"]); _number(order["cumQuote"])
    original = _number(order["origQty"], positive=True)
    executed = _number(order["executedQty"])
    if original != Decimal(attempt["quantity"]):
        _fail("BINANCE_ORDER_IDENTITY_MISMATCH")
    return original, executed


def _validate_account(product, account):
    key = "balances" if product == "SPOT" else "positions"
    if frozenset(account) != {key} or not isinstance(account[key], list):
        _fail("BINANCE_ORDER_OBSERVATION_INVALID")


def _trade_payloads(attempt, order_id, documents):
    expected = _SPOT_TRADE_KEYS if attempt["product"] == "SPOT" else _FUTURES_TRADE_KEYS
    seen = {}
    for document in documents:
        trade = _document(document)
        if frozenset(trade) != expected:
            _fail("BINANCE_ORDER_OBSERVATION_INVALID")
        trade_id = trade.get("id")
        if (isinstance(trade_id, bool) or not isinstance(trade_id, int)
                or trade_id < 0 or trade.get("orderId") != order_id
                or trade.get("symbol") != "ETHUSDT"
                or not isinstance(trade.get("time"), int)
                or isinstance(trade.get("time"), bool)
                or not isinstance(trade.get(
                    "isBuyer" if attempt["product"] == "SPOT" else "buyer"
                ), bool)):
            _fail("BINANCE_ORDER_OBSERVATION_INVALID")
        canonical = canonical_json(trade)
        if trade_id in seen:
            if seen[trade_id] != canonical:
                _fail("BINANCE_CONFLICTING_DUPLICATE_FILL")
            continue
        seen[trade_id] = canonical
    result = []
    cumulative = Decimal("0")
    cumulative_fee = Decimal("0")
    for trade_id in sorted(seen):
        trade = json.loads(seen[trade_id])
        quantity = _number(trade["qty"], positive=True)
        price = _number(trade["price"], positive=True)
        quote = _number(trade["quoteQty"])
        fee = _number(trade["commission"])
        if (quote != quantity * price
                or not isinstance(trade["commissionAsset"], str)
                or not trade["commissionAsset"]):
            _fail("BINANCE_ORDER_OBSERVATION_INVALID")
        cumulative += quantity; cumulative_fee += fee
        payload = {
            "trade_id": trade_id, "order_id": order_id,
            "quantity": canonical_decimal(quantity),
            "price": canonical_decimal(price),
            "quote_quantity": canonical_decimal(quote),
            "fee": canonical_decimal(fee),
            "fee_asset": trade["commissionAsset"],
            "cumulative_filled_quantity": canonical_decimal(cumulative),
        }
        if attempt["product"] == "PERPETUAL":
            payload["realized_pnl"] = canonical_decimal(
                _number(trade["realizedPnl"], signed=True)
            )
        payload["intent_id"] = attempt["intent_id"]
        result.append({"event_type": "BINANCE_FILL_OBSERVED", "payload": payload})
    return result, cumulative, cumulative_fee


def apply_binance_order_observation(*, attempt, order, trades, account):
    """Normalize one query plus exact trade/account replay into private events."""
    if not _valid_attempt(attempt) or not isinstance(trades, tuple):
        _fail("BINANCE_ORDER_OBSERVATION_INVALID")
    order_value = _document(order)
    account_value = _document(account)
    _validate_account(attempt["product"], account_value)
    if frozenset(order_value) == {"code", "msg"}:
        if (isinstance(order_value["code"], bool)
                or not isinstance(order_value["code"], int)
                or not isinstance(order_value["msg"], str)):
            _fail("BINANCE_ORDER_OBSERVATION_INVALID")
        event_type = ("BINANCE_ORDER_UNKNOWN"
                      if order_value["code"] == -1007
                      else "BINANCE_ORDER_REJECTED")
        return ({
            "event_type": event_type,
            "payload": {"intent_id": attempt["intent_id"],
                        "venue_code": order_value["code"],
                        "blocks_new_risk": event_type == "BINANCE_ORDER_UNKNOWN"},
        },)
    original, executed = _validate_order(attempt, order_value)
    fill_events, filled, fee = _trade_payloads(
        attempt, order_value["orderId"], trades
    )
    if filled > original:
        _fail("BINANCE_ORDER_OVERFILL")
    if filled != executed:
        _fail("BINANCE_ORDER_FILL_REPLAY_MISMATCH")
    if order_value.get("status") == "FILLED" and filled != original:
        _fail("BINANCE_ORDER_FILL_REPLAY_MISMATCH")
    events = [{
        "event_type": "BINANCE_ORDER_ACKNOWLEDGED",
        "payload": {"intent_id": attempt["intent_id"],
                    "order_id": order_value["orderId"],
                    "venue_client_order_id": attempt["venue_client_order_id"]},
    }, *fill_events]
    status = order_value.get("status")
    if filled == original:
        event_type = "BINANCE_ORDER_FILLED"
    elif filled > 0:
        event_type = "BINANCE_ORDER_PARTIALLY_FILLED"
    else:
        event_type = {
            "CANCELED": "BINANCE_ORDER_CANCELED",
            "EXPIRED": "BINANCE_ORDER_EXPIRED",
            "REJECTED": "BINANCE_ORDER_REJECTED",
            "NEW": None,
        }.get(status)
        if status not in {"CANCELED", "EXPIRED", "REJECTED", "NEW"}:
            _fail("BINANCE_ORDER_OBSERVATION_INVALID")
    if event_type is not None:
        events.append({
            "event_type": event_type,
            "payload": {
                "intent_id": attempt["intent_id"],
                "cumulative_filled_quantity": canonical_decimal(filled),
                "cumulative_fee": canonical_decimal(fee),
                "venue_terminal_status": status,
            },
        })
    return tuple(events)
