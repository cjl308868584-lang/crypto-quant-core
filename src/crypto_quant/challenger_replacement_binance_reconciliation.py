"""Pure three-way reconciliation for fixed Binance private evidence."""
import base64
from decimal import Decimal
import hashlib, json, stat
from types import MappingProxyType
from typing import Mapping
from .canonical import canonical_decimal, canonical_json
from .challenger_replacement_binance_private_lifecycle import _FUTURES_ORDER_KEYS, _SPOT_ORDER_KEYS, _SPOT_TRADE_KEYS, _document, _normalize_spot_order, _normalize_spot_trade, _number, _strict_pairs
from .challenger_replacement_binance_preflight import _FUTURES_ACCOUNT_KEYS, _FUTURES_ASSET_KEYS, _POSITION_KEYS, _SPOT_KEYS
from .challenger_replacement_events import ChallengerReplacementEventRoot, _read_final
_FACT_KEYS = frozenset({"product", "signed_quantity", "average_entry_price_or_null",
    "realized_pnl", "unrealized_pnl", "cumulative_fee", "funding", "wallet_balance",
    "available_balance", "open_order_count", "protective_stop_client_id_or_null", "fill_ids"})
_TRADE_KEYS = frozenset({"symbol", "id", "orderId", "qty", "price", "quoteQty",
    "commission", "commissionAsset", "realizedPnl", "time", "buyer"})
_INCOME_KEYS = frozenset({"tranId", "symbol", "incomeType", "income", "asset", "time"})
_ALGO_KEYS = frozenset({"algoId", "clientAlgoId", "symbol", "algoStatus", "side", "positionSide", "quantity", "triggerPrice", "workingType", "reduceOnly", "closePosition", "algoType", "orderType"})
_ORDER_AUTH_KEYS = frozenset({"order_id", "client_order_id"})
_STOP_AUTH_KEYS = frozenset({"client_algo_id", "side", "quantity", "trigger_price", "reduce_only"})
_AUTHORITY = {"network_requests": 0, "orders": 0, "state_writes": 0}
class BinanceReconciliationError(ValueError):
    def __init__(self, reason_code): super().__init__(reason_code); self.reason_code = reason_code
def _fail(reason, error=None):
    failure = BinanceReconciliationError(reason)
    if error is None: raise failure
    raise failure from error
_CAPTURE_SELECTORS = ("event_input", "ledger_input", "venue_input")
_CAPTURE_RECORD_KEYS = frozenset({"capture_event_sequence", "capture_event_hash",
    "device", "inode", "uid", "mode_octal", "link_count", "event_size",
    "event_sha256", "payload_selector", "decoded_size", "decoded_sha256"})
def load_binance_reconciliation_capture(*, event_root, capture_event_sequence, capture_event_hash):
    """Reopen one exact immutable capture event and derive selector identities."""
    try:
        if (not isinstance(event_root, ChallengerReplacementEventRoot) or isinstance(capture_event_sequence, bool)
                or not isinstance(capture_event_sequence, int) or capture_event_sequence < 1 or not isinstance(capture_event_hash, str) or len(capture_event_hash) != 64
                or any(character not in "0123456789abcdef" for character in capture_event_hash)):
            raise ValueError
        event_root.validate()
        loaded = _read_final(event_root, f"{capture_event_sequence:020d}.event.json")
        if loaded is None: raise ValueError
        event, entry = loaded
        outer = json.loads(event.final_bytes.decode("utf-8")); payload = _document(base64.b64decode(outer["payload_bytes_base64"], validate=True))
        expected = {"intent_id", "capture_version"}
        for selector in _CAPTURE_SELECTORS: expected.update({selector + "_bytes_base64", selector + "_sha256"})
        if (event.sequence != capture_event_sequence or event.event_hash != capture_event_hash
                or outer["event_type"] != "BINANCE_RECONCILIATION_INPUTS_CAPTURED"
                or frozenset(payload) != expected or payload["capture_version"] != "1.0.0"):
            raise ValueError
        publications, decoded = {}, {}
        for selector in _CAPTURE_SELECTORS:
            body = base64.b64decode(payload[selector + "_bytes_base64"], validate=True); digest = hashlib.sha256(body).hexdigest()
            if (not 1 <= len(body) <= 1_048_576
                    or digest != payload[selector + "_sha256"]
                    or canonical_json(_document(body)).encode() != body): raise ValueError
            decoded[selector] = body
            publications[selector] = {
                "capture_event_sequence": event.sequence, "capture_event_hash": event.event_hash,
                "device": entry.st_dev, "inode": entry.st_ino, "uid": entry.st_uid,
                "mode_octal": format(stat.S_IMODE(entry.st_mode), "04o"),
                "link_count": entry.st_nlink, "event_size": entry.st_size,
                "event_sha256": hashlib.sha256(event.final_bytes).hexdigest(),
                "payload_selector": selector, "decoded_size": len(body), "decoded_sha256": digest}
        event_root.validate(); return _freeze({**decoded, "publications": publications})
    except (KeyError, TypeError, ValueError, OSError) as error:
        if isinstance(error, BinanceReconciliationError) and error.reason_code == "BINANCE_RECONCILIATION_CAPTURE_UNTRUSTED": raise
        _fail("BINANCE_RECONCILIATION_CAPTURE_UNTRUSTED", error)
def verify_binance_reconciliation_capture(*, event_root, publications):
    """Verify caller records against the currently attached capture inode."""
    try:
        if not isinstance(publications, Mapping) or frozenset(publications) != frozenset(_CAPTURE_SELECTORS): raise ValueError
        records = {key: publications[key] for key in _CAPTURE_SELECTORS}
        if any(not isinstance(record, Mapping) or frozenset(record) != _CAPTURE_RECORD_KEYS for record in records.values()): raise ValueError
        first = records[_CAPTURE_SELECTORS[0]]
        loaded = load_binance_reconciliation_capture(event_root=event_root,
            capture_event_sequence=first["capture_event_sequence"], capture_event_hash=first["capture_event_hash"])
        if any(dict(loaded["publications"][key]) != dict(records[key]) for key in _CAPTURE_SELECTORS): raise ValueError
        return loaded
    except (KeyError, TypeError, ValueError, OSError) as error:
        if isinstance(error, BinanceReconciliationError) and error.reason_code == "BINANCE_RECONCILIATION_CAPTURE_UNTRUSTED": raise
        _fail("BINANCE_RECONCILIATION_CAPTURE_UNTRUSTED", error)
def _capture_records(value):
    if not isinstance(value, Mapping) or frozenset(value) != frozenset(_CAPTURE_SELECTORS): raise ValueError
    records = {selector: dict(value[selector]) for selector in _CAPTURE_SELECTORS}
    if any(not isinstance(value[selector], Mapping) or frozenset(records[selector]) != _CAPTURE_RECORD_KEYS
           or records[selector]["payload_selector"] != selector for selector in _CAPTURE_SELECTORS): raise ValueError
    shared = {key for key in _CAPTURE_RECORD_KEYS if key not in {"payload_selector", "decoded_size", "decoded_sha256"}}
    if any({key: records[selector][key] for key in shared}
           != {key: records[_CAPTURE_SELECTORS[0]][key] for key in shared}
           for selector in _CAPTURE_SELECTORS[1:]): raise ValueError
    return records
def _decimal(value, *, signed=True, nullable=False):
    if nullable and value is None: return None
    try:
        number = _number(value, signed=signed)
    except ValueError as error:
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
    return canonical_decimal(number)
def _facts(value):
    if not isinstance(value, Mapping) or frozenset(value) != _FACT_KEYS:
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    product = value.get("product")
    if product not in {"SPOT", "PERPETUAL"}: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    result = {
        "product": product, "signed_quantity": _decimal(value.get("signed_quantity")),
        "average_entry_price_or_null": _decimal(value.get("average_entry_price_or_null"), nullable=True),
        "realized_pnl": _decimal(value.get("realized_pnl")), "unrealized_pnl": _decimal(value.get("unrealized_pnl")),
        "cumulative_fee": _decimal(value.get("cumulative_fee"), signed=False), "funding": _decimal(value.get("funding")),
        "wallet_balance": _decimal(value.get("wallet_balance"), signed=False),
        "available_balance": _decimal(value.get("available_balance"), signed=False),
    }
    count, fill_ids = value.get("open_order_count"), value.get("fill_ids")
    client = value.get("protective_stop_client_id_or_null")
    if (isinstance(count, bool) or not isinstance(count, int) or count < 0
            or not isinstance(fill_ids, list)
            or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in fill_ids)
            or fill_ids != sorted(set(fill_ids))
            or (client is not None and (not isinstance(client, str)
                or len(client) != 36 or not client.startswith("cq77")))):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    result.update(open_order_count=count, protective_stop_client_id_or_null=client, fill_ids=list(fill_ids))
    if (Decimal(result["signed_quantity"]) == 0) != (result["average_entry_price_or_null"] is None): _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    return result
def _unique(documents, key, conflict):
    if not isinstance(documents, tuple): _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    result = {}
    for raw in documents:
        try: item = _document(raw)
        except ValueError as error: _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
        identity = item.get(key)
        if isinstance(identity, bool) or not isinstance(identity, int) or identity < 0: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        frozen = canonical_json(item)
        if identity in result and result[identity] != frozen: _fail(conflict)
        result[identity] = frozen
    return [json.loads(result[key]) for key in sorted(result)]
def _array_document(data):
    try:
        if not isinstance(data, bytes) or not 1 <= len(data) <= 1_048_576: raise ValueError
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_pairs)
        if not isinstance(value, list) or canonical_json(value).encode() != data: raise ValueError
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
def _spot_market(data):
    try:
        value = _document(data)
        if frozenset(value) != {"symbol", "mark_price", "ask_price", "asset_marks_usdt"} or value["symbol"] != "ETHUSDT" or not isinstance(value["asset_marks_usdt"], dict): raise ValueError
        mark, ask = _number(value["mark_price"], positive=True), _number(value["ask_price"], positive=True)
        marks = {asset: _number(price, positive=True) for asset, price in value["asset_marks_usdt"].items()
                 if isinstance(asset, str) and asset}
        if len(marks) != len(value["asset_marks_usdt"]) or marks.get("USDT") != 1 or marks.get("ETH") != mark: raise ValueError
        return mark, ask, marks
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
def _spot_venue(event, orders, trades, account, position, incomes, algos, previous, order_auth):
    if incomes or algos: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    mark, _ask, marks = _spot_market(position)
    order_values = [_normalize_spot_order(value) for value in
                    _unique(orders, "orderId", "BINANCE_RECONCILIATION_CONFLICTING_ORDER")]
    if len(order_values) != 1: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    order = order_values[0]
    if (frozenset(order) != _SPOT_ORDER_KEYS or order["symbol"] != "ETHUSDT"
            or order["orderId"] != order_auth["order_id"]
            or order["clientOrderId"] != order_auth["client_order_id"]
            or order["type"] != "MARKET" or order["side"] not in {"BUY", "SELL"}
            or order["status"] not in {
                "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED",
            }):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    trade_values = [_normalize_spot_trade(value) for value in
                    _unique(trades, "id", "BINANCE_RECONCILIATION_CONFLICTING_FILL")]
    quantity = quote = fee = base_fee = Decimal("0")
    for trade in trade_values:
        if (frozenset(trade) != _SPOT_TRADE_KEYS
                or trade["symbol"] != "ETHUSDT"
                or trade["orderId"] != order["orderId"]
                or trade["isBuyer"] is not (order["side"] == "BUY")):
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        item_quantity = _number(trade["qty"], positive=True); item_price = _number(trade["price"], positive=True); item_quote = _number(trade["quoteQty"])
        if item_quote != item_quantity * item_price: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        asset, commission = trade["commissionAsset"], _number(trade["commission"])
        if not isinstance(asset, str) or asset not in marks: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        quantity += item_quantity; quote += item_quote; fee += commission * marks[asset]
        if asset == "ETH": base_fee += commission
    if (_number(order["executedQty"]) != quantity
            or _number(order["cummulativeQuoteQty"]) != quote):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    account_value = _document(account)
    if frozenset(account_value) != _SPOT_KEYS or not isinstance(account_value["balances"], list): _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    balances = {}
    for item in account_value["balances"]:
        if (not isinstance(item, dict)
                or frozenset(item) != {"asset", "free", "locked"}
                or item["asset"] in balances):
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        balances[item["asset"]] = (_number(item["free"]), _number(item["locked"]))
    if not {"ETH", "USDT"}.issubset(balances): _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    signed = sum(balances["ETH"])
    prior_signed = Decimal("0") if previous is None else Decimal(previous["signed_quantity"])
    prior_average = None if previous is None else previous["average_entry_price_or_null"]
    prior_average = (None if prior_average is None else Decimal(prior_average))
    prior_realized = Decimal("0") if previous is None else Decimal(previous["realized_pnl"])
    prior_fee = Decimal("0") if previous is None else Decimal(previous["cumulative_fee"])
    prior_fills = [] if previous is None else previous["fill_ids"]
    if order["side"] == "BUY":
        expected_signed = prior_signed + quantity - base_fee
        average = None if expected_signed == 0 else (prior_signed * (prior_average or Decimal("0")) + quote) / expected_signed
        realized = prior_realized
    else:
        if prior_average is None or quantity + base_fee > prior_signed: _fail("VENUE_LOCAL_POSITION_MISMATCH")
        expected_signed = prior_signed - quantity - base_fee
        average = None if expected_signed == 0 else prior_average
        realized = prior_realized + quote - (quantity + base_fee) * prior_average
    if signed != expected_signed: _fail("VENUE_LOCAL_POSITION_MISMATCH")
    available = balances["USDT"][0]
    wallet = Decimal("0")
    for asset, amounts in balances.items():
        total = sum(amounts)
        if total and asset not in marks: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        wallet += total * marks.get(asset, Decimal("0"))
    unrealized = Decimal("0") if average is None else signed * (mark - average)
    return {
        "product": "SPOT", "signed_quantity": canonical_decimal(signed),
        "average_entry_price_or_null": None if average is None else canonical_decimal(average), "realized_pnl": canonical_decimal(realized),
        "unrealized_pnl": canonical_decimal(unrealized),
        "cumulative_fee": canonical_decimal(prior_fee + fee), "funding": "0",
        "wallet_balance": canonical_decimal(wallet),
        "available_balance": canonical_decimal(available),
        "open_order_count": int(order["status"] in {"NEW", "PARTIALLY_FILLED"}),
        "protective_stop_client_id_or_null": None,
        "fill_ids": sorted(set(list(prior_fills) + [trade["id"] for trade in trade_values])),
    }
def _venue(event, orders, trades, account, position, incomes, algos, previous, order_auth, stop_auth):
    if event["product"] == "SPOT": return _spot_venue(event, orders, trades, account, position, incomes, algos, previous, order_auth)
    order_values = _unique(orders, "orderId", "BINANCE_RECONCILIATION_CONFLICTING_ORDER")
    for order in order_values:
        if (frozenset(order) != _FUTURES_ORDER_KEYS
                or order["symbol"] != "ETHUSDT"
                or order["orderId"] != order_auth["order_id"]
                or order["clientOrderId"] != order_auth["client_order_id"]
                or not isinstance(order["clientOrderId"], str)
                or order["type"] != "MARKET"
                or order["positionSide"] != "BOTH"
                or not isinstance(order["reduceOnly"], bool)
                or order["side"] not in {"BUY", "SELL"}
                or order["status"] not in {
                    "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED",
                    "EXPIRED", "REJECTED",
                }):
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    trade_values = _unique(trades, "id", "BINANCE_RECONCILIATION_CONFLICTING_FILL")
    prior_signed = Decimal("0") if previous is None else Decimal(previous["signed_quantity"])
    prior_realized = Decimal("0") if previous is None else Decimal(previous["realized_pnl"])
    prior_fee = Decimal("0") if previous is None else Decimal(previous["cumulative_fee"])
    prior_funding = Decimal("0") if previous is None else Decimal(previous["funding"])
    prior_fills = [] if previous is None else list(previous["fill_ids"])
    fee = realized = weighted = total = Decimal("0")
    for trade in trade_values:
        if (frozenset(trade) != _TRADE_KEYS or trade["symbol"] != "ETHUSDT"
                or not isinstance(trade["buyer"], bool)
                or not isinstance(trade["commissionAsset"], str)):
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        quantity = _number(trade["qty"], positive=True); price = _number(trade["price"], positive=True)
        if _number(trade["quoteQty"]) != quantity * price: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        total += quantity; weighted += quantity * price; fee += _number(trade["commission"]); realized += _number(trade["realizedPnl"], signed=True)
    try:
        account_value, position_value = _document(account), _array_document(position)
    except ValueError as error: _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
    if (frozenset(account_value) != _FUTURES_ACCOUNT_KEYS
            or not isinstance(account_value["assets"], list)
            or len(account_value["assets"]) != 1
            or frozenset(account_value["assets"][0]) != _FUTURES_ASSET_KEYS
            or account_value["assets"][0]["asset"] != "USDT"
            or not isinstance(account_value["positions"], list)
            or not isinstance(position_value, list) or len(position_value) != 1
            or frozenset(position_value[0]) != _POSITION_KEYS):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    position_value = position_value[0]
    if (position_value["symbol"] != "ETHUSDT"
            or position_value["positionSide"] != "BOTH"
            or position_value["marginAsset"] != "USDT"
            or any(isinstance(position_value[key], bool)
                   or not isinstance(position_value[key], int) for key in ("adl", "updateTime"))): _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    account_numbers = _FUTURES_ACCOUNT_KEYS - {"assets", "positions"}
    asset = account_value["assets"][0]
    asset_numbers = _FUTURES_ASSET_KEYS - {"asset", "updateTime"}
    if (any(_number(account_value[key], signed=True) < 0
            for key in account_numbers - {"totalUnrealizedProfit", "totalCrossUnPnl"})
            or any(_number(asset[key], signed=True) < 0
                   for key in asset_numbers - {"unrealizedProfit", "crossUnPnl"})
            or isinstance(asset["updateTime"], bool)
            or not isinstance(asset["updateTime"], int)
            or _number(account_value["totalWalletBalance"])
            != _number(asset["walletBalance"])
            or _number(account_value["availableBalance"])
            != _number(asset["availableBalance"])
            or _number(account_value["totalUnrealizedProfit"], signed=True)
            != _number(asset["unrealizedProfit"], signed=True)): _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    signed_quantity = _number(position_value["positionAmt"], signed=True)
    if order_values:
        order = order_values[0]
        if order["side"] == "BUY":
            if (order["reduceOnly"] is not True or prior_signed >= 0 or total > -prior_signed
                    or signed_quantity != prior_signed + total): _fail("VENUE_LOCAL_POSITION_MISMATCH")
        elif order["reduceOnly"] is not False or signed_quantity != prior_signed - total: _fail("VENUE_LOCAL_POSITION_MISMATCH")
    entry = _number(position_value["entryPrice"])
    income_values = _unique(incomes, "tranId", "BINANCE_RECONCILIATION_CONFLICTING_FUNDING")
    funding = Decimal("0")
    for income in income_values:
        if (frozenset(income) != _INCOME_KEYS
                or income["symbol"] != "ETHUSDT"
                or income["incomeType"] != "FUNDING_FEE"
                or income["asset"] != "USDT"):
            _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        funding += _number(income["income"], signed=True)
    algo_values = _unique(algos, "algoId", "BINANCE_RECONCILIATION_CONFLICTING_STOP")
    active = []
    for algo in algo_values:
        if frozenset(algo) != _ALGO_KEYS or algo["symbol"] != "ETHUSDT": _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
        if algo["algoStatus"] == "NEW": active.append(algo)
    stop = None
    if signed_quantity < 0:
        if len(active) != 1: _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
        algo = active[0]
        if (stop_auth is None or frozenset(stop_auth) != _STOP_AUTH_KEYS
                or algo["clientAlgoId"] != stop_auth["client_algo_id"]
                or algo["side"] != stop_auth["side"]
                or _decimal(stop_auth["quantity"], signed=False)
                != canonical_decimal(-signed_quantity)
                or _decimal(stop_auth["trigger_price"], signed=False)
                != _decimal(algo["triggerPrice"], signed=False)
                or stop_auth["reduce_only"] is not True
                or algo["side"] != "BUY" or algo["positionSide"] != "BOTH"
                or _number(algo["quantity"], positive=True) != -signed_quantity
                or algo["workingType"] != "MARK_PRICE"
                or algo["reduceOnly"] is not True
                or algo["closePosition"] is not False
                or algo["algoType"] != "CONDITIONAL"
                or algo["orderType"] != "STOP_MARKET"):
            _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
        stop = algo["clientAlgoId"]
    elif active: _fail("VENUE_LOCAL_POSITION_MISMATCH")
    average = None if signed_quantity == 0 else canonical_decimal(entry)
    return {
        "product": event["product"],
        "signed_quantity": canonical_decimal(signed_quantity),
        "average_entry_price_or_null": average,
        "realized_pnl": canonical_decimal(prior_realized + realized),
        "unrealized_pnl": canonical_decimal(_number(position_value["unRealizedProfit"], signed=True)),
        "cumulative_fee": canonical_decimal(prior_fee + fee),
        "funding": canonical_decimal(prior_funding + funding),
        "wallet_balance": canonical_decimal(_number(account_value["totalWalletBalance"])),
        "available_balance": canonical_decimal(_number(account_value["availableBalance"])),
        "open_order_count": sum(order["status"] in {"NEW", "PARTIALLY_FILLED"} for order in order_values),
        "protective_stop_client_id_or_null": stop,
        "fill_ids": sorted(set(prior_fills + [trade["id"] for trade in trade_values])),
    }
def _identity(document):
    core = dict(document)
    core.pop("reconciliation_id", None)
    return "binance_reconciliation_" + hashlib.sha256(canonical_json(core).encode()).hexdigest()
def reconcile_binance_private_state(*, event_projection, ledger_projection, authorized_order,
                                    authorized_stop_or_null, order_documents, trade_documents,
                                    account_document, position_document, income_documents, algo_documents,
                                    previous_reconciliation_bytes_or_null=None,
                                    capture_publications=None):
    """Require event, venue and ledger projections to agree exactly."""
    if (not isinstance(event_projection, Mapping)
            or frozenset(event_projection) != _FACT_KEYS
            or not isinstance(ledger_projection, Mapping)
            or not isinstance(authorized_order, Mapping)
            or frozenset(authorized_order) != _ORDER_AUTH_KEYS
            or isinstance(authorized_order.get("order_id"), bool)
            or not isinstance(authorized_order.get("order_id"), int)
            or authorized_order["order_id"] <= 0
            or not isinstance(authorized_order.get("client_order_id"), str)):
        _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    if capture_publications is None: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    event = _facts(event_projection); ledger = _facts(ledger_projection)
    if event != ledger: _fail("BINANCE_LEDGER_PROJECTION_MISMATCH")
    previous = None
    if previous_reconciliation_bytes_or_null is not None:
        previous = dict(load_binance_reconciliation_bytes(previous_reconciliation_bytes_or_null)["event_projection"])
        if previous["product"] != event["product"]: _fail("BINANCE_RECONCILIATION_INPUT_INVALID")
    venue = _venue(event, order_documents, trade_documents, account_document, position_document,
                   income_documents, algo_documents, previous, authorized_order, authorized_stop_or_null)
    if event != venue: _fail("VENUE_LOCAL_POSITION_MISMATCH")
    document = {
        "$schema": "./challenger-replacement-binance-reconciliation-v1.schema.json",
        "schema_version": "1.0.0",
        "status": "BINANCE_PRIVATE_RECONCILIATION_MATCHED",
        "event_projection": event, "venue_projection": venue,
        "ledger_projection": ledger,
        "authority": _AUTHORITY,
    }
    try: document["capture_publications"] = _capture_records(capture_publications)
    except (KeyError, TypeError, ValueError) as error: _fail("BINANCE_RECONCILIATION_INPUT_INVALID", error)
    document["reconciliation_id"] = _identity(document)
    return (canonical_json(document) + "\n").encode()
def _freeze(value):
    if isinstance(value, dict): return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list): return tuple(_freeze(item) for item in value)
    return value
def load_binance_reconciliation_bytes(data):
    """Strictly replay one matched reconciliation artifact."""
    try:
        if not isinstance(data, bytes) or not data.endswith(b"\n"): raise ValueError
        document = _document(data[:-1])
        required = {
                "$schema", "schema_version", "reconciliation_id", "status",
                "event_projection", "venue_projection", "ledger_projection",
                "capture_publications", "authority",
            }
        if (frozenset(document) != frozenset(required)
                or document["$schema"]
                != "./challenger-replacement-binance-reconciliation-v1.schema.json"
                or document["schema_version"] != "1.0.0"
                or document["status"] != "BINANCE_PRIVATE_RECONCILIATION_MATCHED"
                or document["authority"] != _AUTHORITY
                or document["reconciliation_id"] != _identity(document)):
            raise ValueError
        event = _facts(document["event_projection"]); venue = _facts(document["venue_projection"]); ledger = _facts(document["ledger_projection"])
        if event != venue or venue != ledger: raise ValueError
        _capture_records(document["capture_publications"])
        return _freeze(document)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, BinanceReconciliationError): raise
        _fail("BINANCE_RECONCILIATION_ARTIFACT_INVALID", error)
def load_binance_reconciliation_bytes_strict(data, *, event_root):
    """Authorize reconciliation only after reopening its exact capture event."""
    loaded = load_binance_reconciliation_bytes(data)
    try: publications = loaded["capture_publications"]
    except KeyError as error: _fail("BINANCE_RECONCILIATION_CAPTURE_UNTRUSTED", error)
    verify_binance_reconciliation_capture(event_root=event_root, publications=publications)
    return loaded
