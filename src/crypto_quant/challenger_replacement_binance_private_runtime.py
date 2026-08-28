"""Append-only orchestration for the fixed Binance private boundary."""
import base64
from datetime import datetime, timezone
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Mapping
from urllib.request import Request
from .canonical import canonical_decimal, canonical_json, utc_datetime
from .challenger_replacement_binance_private_lifecycle import (_ALGO_KEYS, _document,
    apply_binance_order_observation, build_binance_order_intent_from_opportunity,
    prepare_binance_order_attempt, prepare_binance_protective_stop,
    reconcile_binance_protective_stop)
from .challenger_replacement_binance_private_protocol import (build_binance_private_request,
    observe_binance_server_time, validate_binance_request_time)
from .challenger_replacement_binance_private_transport import (BinancePrivateTransportResult,
    execute_binance_private_request)
from .challenger_replacement_binance_preflight import BinanceAccountPreflightCapability
from .challenger_replacement_binance_reconciliation import (load_binance_reconciliation_bytes,
    load_binance_reconciliation_bytes_strict, load_binance_reconciliation_capture,
    reconcile_binance_private_state, _spot_market)
from .challenger_replacement_events import ChallengerReplacementEventRoot
from .challenger_replacement_opportunities import ChallengerReplacementOpportunityState
from .challenger_replacement_public_http import open_fixed_public_request
_TERMINAL_ORDERS = frozenset({"BINANCE_ORDER_FILLED", "BINANCE_ORDER_CANCELED",
                              "BINANCE_ORDER_EXPIRED", "BINANCE_ORDER_REJECTED"})
class BinancePrivateRuntimeError(RuntimeError):
    def __init__(self, reason_code): super().__init__(reason_code); self.reason_code = reason_code
@dataclass(frozen=True)
class _Context:
    credential: object; activation: object; build_identity: Mapping; recorded_at: str; timestamp_ms: int
def _fail(reason, error=None):
    failure = BinancePrivateRuntimeError(reason)
    if error is None: raise failure
    raise failure from error
def _require_identity(state, event_root, build_identity):
    if (not isinstance(state, ChallengerReplacementOpportunityState)
        or not isinstance(event_root, ChallengerReplacementEventRoot)
        or state.event_root is not event_root
        or not isinstance(build_identity, Mapping)
        or dict(build_identity) != state.build_identity):
        _fail("BINANCE_PRIVATE_RUNTIME_IDENTITY_INVALID")
    try:
        event_root.validate()
    except Exception as error:
        _fail("BINANCE_PRIVATE_RUNTIME_IDENTITY_INVALID", error)
def _require_decision_intent(state, intent, activation):
    try:
        slot = state.replay()["opportunities"][intent["opportunity_id"]]
        expected = build_binance_order_intent_from_opportunity(
            slot=slot, activation=activation,
            attempt_ordinal=intent["attempt_ordinal"],
        )
        if dict(intent) != expected: _fail("BINANCE_PRIVATE_RUNTIME_INTENT_DECISION_MISMATCH")
    except BinancePrivateRuntimeError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_INTENT_DECISION_MISMATCH", error)
def _wall_now(): return datetime.now(timezone.utc)
def _public_time_transport(request):
    url = "https://%s%s" % (request.host, request.path)
    response = open_fixed_public_request(Request(url, method="GET"), max_body_bytes=128)
    if response.final_url != url: _fail("BINANCE_PRIVATE_RUNTIME_SERVER_TIME_INVALID")
    return BinancePrivateTransportResult(
        "QUERY_SUCCEEDED" if response.status == 200 else "TRANSIENT_QUERY_FAILURE",
        response.status, response.body, hashlib.sha256(response.body).hexdigest(), (),
    )
def _fresh_context(state, attempt, credential, activation, build_identity,
                   recorded_at):
    try:
        evidence = observe_binance_server_time(
            product=attempt["product"], transport=_public_time_transport,
            local_clock=lambda: int(_wall_now().timestamp() * 1000),
        )
        payload = {key: getattr(evidence, key) for key in evidence.__dataclass_fields__}
        _append_intent(state, attempt, "BINANCE_SERVER_TIME_OBSERVED",
                       recorded_at, **payload)
        return _Context(credential, activation, build_identity, recorded_at,
                        evidence.server_time_ms)
    except (AttributeError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_SERVER_TIME_INVALID", error)
def _runtime_projection(state):
    projection = state._replay()
    active = None
    unresolved = []
    absent = []
    for slot in projection["opportunities"].values():
        private = slot.get("private")
        if not isinstance(private, dict):
            continue
        if private.get("absence_proven") is True:
            absent.append(private["venue_client_order_id"])
        if private["stage"] == "BINANCE_ORDER_UNKNOWN":
            unresolved.append(private["venue_client_order_id"])
        elif private["stage"] == "BINANCE_RECONCILIATION_SUCCEEDED":
            active = (
                private["product"]
                if private["action"] in {"OPEN_LONG", "OPEN_SHORT"}
                else None
            )
    return {
        "plan_hash": state.plan["plan_hash"],
        "active_product_or_null": active,
        "unresolved_client_order_ids": unresolved,
        "proven_absent_client_order_ids": absent,
    }
def _append(state, event_type, opportunity_id, payload, recorded_at):
    projection = state.replay()
    return state.append(event_type=event_type, opportunity_id=opportunity_id,
        worker_id="binance-private-runtime-v1", recorded_at=recorded_at,
        payload=payload, expected_last_event_hash=projection["last_event_hash"])
def _append_intent(state, attempt, event_type, recorded_at, **payload): return _append(state, event_type, attempt["opportunity_id"],
        {"intent_id": attempt["intent_id"], **payload}, recorded_at)
def _status(status, attempt, **extra): return {"status": status, "opportunity_id": attempt["opportunity_id"],
        "intent_id": attempt["intent_id"],
        "venue_client_order_id": attempt["venue_client_order_id"], **extra}
def _reconciliation_bytes(private, event_root):
    try:
        data = base64.b64decode(private["reconciliation_bytes_base64"], validate=True)
        loaded = load_binance_reconciliation_bytes_strict(data, event_root=event_root)
        if (hashlib.sha256(data).hexdigest()
                != private["reconciliation_sha256"]
                or loaded["reconciliation_id"]
                != private["reconciliation_id"]):
            raise ValueError
        return data, loaded
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID", error)
def _reconciliation(private, event_root): return _reconciliation_bytes(private, event_root)[1]
def _previous_reconciliation_bytes(state, *, product, before_opportunity_id):
    if (product not in {"SPOT", "PERPETUAL"}
            or not isinstance(before_opportunity_id, str)
            or not before_opportunity_id.startswith("ETHUSDT@")):
        _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
    try:
        opportunities = state.replay()["opportunities"]
        if not isinstance(opportunities, Mapping):
            raise TypeError
        candidates = []
        for opportunity_id, slot in opportunities.items():
            if (not isinstance(opportunity_id, str)
                    or opportunity_id >= before_opportunity_id
                    or not isinstance(slot, Mapping)):
                continue
            private = slot.get("private")
            if (isinstance(private, Mapping)
                    and private.get("stage")
                    == "BINANCE_RECONCILIATION_SUCCEEDED"
                    and private.get("product") == product):
                candidates.append((opportunity_id, private))
        if not candidates: return None
        return _reconciliation_bytes(max(candidates, key=lambda item: item[0])[1], state.event_root)[0]
    except BinancePrivateRuntimeError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID", error)
def _append_reconciliation_tail(state, attempt, loaded, required, client,
                                recorded_at):
    _append_intent(state, attempt, "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED",
                   recorded_at, required=required,
                   client_algo_id_or_null=client,
                   status="VERIFIED" if required else "NOT_REQUIRED")
    _append_intent(state, attempt, "BINANCE_RECONCILIATION_SUCCEEDED", recorded_at,
                   reconciliation_id=loaded["reconciliation_id"])
    return _status("TERMINAL_RECONCILED", attempt, reconciliation_id=loaded["reconciliation_id"])
def _publish_reconciliation(state, attempt, data, required, client, recorded_at):
    loaded = load_binance_reconciliation_bytes_strict(data, event_root=state.event_root)
    _append_intent(
        state, attempt, "BINANCE_POSITION_BALANCE_RECONCILED", recorded_at,
        reconciliation_id=loaded["reconciliation_id"],
        reconciliation_bytes_base64=base64.b64encode(data).decode("ascii"),
        reconciliation_sha256=hashlib.sha256(data).hexdigest(),
    )
    return _append_reconciliation_tail(state, attempt, loaded, required, client, recorded_at)
def _resume_reconciliation(state, attempt, private, recorded_at):
    loaded = _reconciliation(private, state.event_root)
    if private["stage"] == "BINANCE_POSITION_BALANCE_RECONCILED":
        client = None
        required = attempt["product"] == "PERPETUAL"
        if required:
            client = loaded["event_projection"][
                "protective_stop_client_id_or_null"
            ]
            if (not isinstance(client, str)
                    or Decimal(loaded["event_projection"]["signed_quantity"])
                    >= 0):
                _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
    else:
        required = attempt["product"] == "PERPETUAL"
        client = loaded["event_projection"][
            "protective_stop_client_id_or_null"
        ] if required else None
    return _append_reconciliation_tail(
        state, attempt, loaded, required, client, recorded_at,
    )
def _request(endpoint_id, attempt, timestamp_ms):
    if endpoint_id.endswith("ORDER_QUERY"):
        parameters = {
            "symbol": "ETHUSDT",
            "origClientOrderId": attempt["venue_client_order_id"],
        }
    elif endpoint_id == "SPOT_ORDER_CREATE":
        parameters = {
            "symbol": "ETHUSDT", "side": attempt["side"],
            "type": "MARKET", "quantity": attempt["quantity"],
            "newClientOrderId": attempt["venue_client_order_id"],
            "newOrderRespType": "FULL",
        }
    else:
        parameters = {
            "symbol": "ETHUSDT", "side": attempt["side"],
            "type": "MARKET", "quantity": attempt["quantity"],
            "newClientOrderId": attempt["venue_client_order_id"],
            "positionSide": "BOTH",
            "reduceOnly": "true" if attempt["reduce_only"] else "false",
        }
    return build_binance_private_request(endpoint_id, parameters, timestamp_ms=timestamp_ms)
def _proven_absent(result):
    try:
        document = json.loads(result.body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return False
    return (result.status_or_null == 400
            and document == {"code": -2013, "msg": "Order does not exist."})
def _existing_private(state, attempt):
    try:
        private = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ].get("private")
    except (AttributeError, KeyError, TypeError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_IDENTITY_INVALID", error)
    if private is None: return None
    expected = {
        "intent_id": attempt["intent_id"], "block_id": attempt["block_id"],
        "product": attempt["product"], "action": attempt["action"],
        "quantity": attempt["quantity"],
        "venue_client_order_id": attempt["venue_client_order_id"],
        "activation_id": attempt["activation_id"],
        "unsigned_intent_sha256": attempt["unsigned_intent_sha256"],
    }
    if any(private.get(key) != value for key, value in expected.items()): _fail("BINANCE_PRIVATE_RUNTIME_INTENT_CONFLICT")
    return private
def _execute(request, context):
    try:
        validate_binance_request_time(timestamp_ms=request.timestamp_ms,
                                      server_time_ms=context.timestamp_ms)
    except (AttributeError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_SERVER_TIME_INVALID", error)
    return execute_binance_private_request(request, credential=context.credential,
        activation=context.activation, expected_build_identity=context.build_identity,
        now=context.recorded_at)
def _recover_after_send(*, state, attempt, context):
    query = _request(attempt["required_first_endpoint"], attempt, context.timestamp_ms)
    result = _execute(query, context)
    if _proven_absent(result): _fail("BINANCE_PRIVATE_RUNTIME_ABSENT_AFTER_SEND_STARTED")
    if result.response_class != "QUERY_SUCCEEDED": _fail("BINANCE_PRIVATE_RUNTIME_RECOVERY_QUERY_UNRESOLVED")
    return _observe_order(state=state, attempt=attempt, order_result=result, context=context)
def _query(endpoint_id, parameters, context):
    request = build_binance_private_request(endpoint_id, parameters,
                                            timestamp_ms=context.timestamp_ms)
    result = _execute(request, context)
    if result.response_class != "QUERY_SUCCEEDED": _fail("BINANCE_PRIVATE_RUNTIME_RECOVERY_QUERY_UNRESOLVED")
    return result
def _tuple_documents(data):
    try:
        values = json.loads(data.decode("utf-8"))
        if not isinstance(values, list) or canonical_json(values).encode() != data:
            raise ValueError
        return tuple(canonical_json(value).encode() for value in values)
    except (AttributeError, TypeError, UnicodeDecodeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID", error)
def _private_payloads(state, opportunity_id):
    values = []
    for event in state._replay()["events"]:
        document = json.loads(event.final_bytes)
        if document["slot_id"] == opportunity_id and document["event_type"].startswith("BINANCE_"):
            values.append((document["event_type"], json.loads(base64.b64decode(
                document["payload_bytes_base64"], validate=True))))
    return values
def _encoded(value): return base64.b64encode(value).decode("ascii")
def _decoded(value): return base64.b64decode(value, validate=True)
def _runtime_reconcile(**inputs):
    try: return reconcile_binance_private_state(**inputs)
    except ValueError as error: _fail(getattr(error, "reason_code", "BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID"), error)
def _capture_inputs(state, attempt, activation, *, order_documents, trade_documents,
                    account_document, position_document, income_documents,
                    algo_documents, previous, stop):
    events = [{"event_type": kind, "payload": payload} for kind, payload in _private_payloads(state, attempt["opportunity_id"])]
    fills = [item["payload"] for item in events if item["event_type"] == "BINANCE_FILL_OBSERVED"]
    common = {"product": attempt["product"], "action": attempt["action"],
        "capital_usdt": activation.capital_usdt,
        "previous_reconciliation_bytes_base64_or_null": None if previous is None else _encoded(previous),
        "position_document_base64": _encoded(position_document),
        "income_documents_base64": [_encoded(item) for item in income_documents], "stop_or_null": stop}
    event_input = canonical_json({**common, "source": "EVENT", "private_events": events}).encode()
    ledger_input = canonical_json({**common, "source": "LEDGER", "fills": fills}).encode()
    venue_input = canonical_json({"source": "VENUE",
        "order_documents_base64": [_encoded(item) for item in order_documents],
        "trade_documents_base64": [_encoded(item) for item in trade_documents],
        "account_document_base64": _encoded(account_document),
        "position_document_base64": _encoded(position_document), "income_documents_base64": [_encoded(item) for item in income_documents],
        "algo_documents_base64": [_encoded(item) for item in algo_documents],
        "authorized_order": _order_authority(state, attempt), "authorized_stop_or_null": _stop_authority(stop)}).encode()
    return event_input, ledger_input, venue_input
def _capture(state, attempt, inputs, recorded_at):
    payload = {"capture_version": "1.0.0"}
    for selector, data in zip(("event_input", "ledger_input", "venue_input"), inputs):
        payload[selector + "_bytes_base64"] = _encoded(data)
        payload[selector + "_sha256"] = hashlib.sha256(data).hexdigest()
    _append_intent(state, attempt, "BINANCE_RECONCILIATION_INPUTS_CAPTURED", recorded_at, **payload)
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    return load_binance_reconciliation_capture(event_root=state.event_root,
        capture_event_sequence=private["capture_event_sequence"],
        capture_event_hash=private["capture_event_hash"])
def _reconcile_captured(state, attempt, activation, recorded_at):
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    captured = load_binance_reconciliation_capture(event_root=state.event_root,
        capture_event_sequence=private["capture_event_sequence"],
        capture_event_hash=private["capture_event_hash"])
    event_input, ledger_input, venue = (_document(captured[key]) for key in ("event_input", "ledger_input", "venue_input"))
    replayed_events = [{"event_type": kind, "payload": payload}
        for kind, payload in _private_payloads(state, attempt["opportunity_id"])
        if kind != "BINANCE_RECONCILIATION_INPUTS_CAPTURED"]
    if (event_input.get("source") != "EVENT" or ledger_input.get("source") != "LEDGER"
            or venue.get("source") != "VENUE"
            or event_input.get("private_events") != replayed_events
            or event_input.get("product") != attempt["product"]
            or event_input.get("action") != attempt["action"]
            or ledger_input.get("capital_usdt") != activation.capital_usdt):
        _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
    previous_encoded = ledger_input["previous_reconciliation_bytes_base64_or_null"]
    previous = None if previous_encoded is None else _decoded(previous_encoded)
    position = _decoded(ledger_input["position_document_base64"])
    incomes = tuple(_decoded(item) for item in ledger_input["income_documents_base64"])
    stop = ledger_input["stop_or_null"]
    event_facts = (_spot_facts(state, attempt, activation, market=position, previous_reconciliation_bytes_or_null=previous)
        if attempt["product"] == "SPOT" else _perpetual_facts(state, attempt, activation,
            position, incomes, stop, previous_reconciliation_bytes_or_null=previous))
    try:
        data = _runtime_reconcile(event_projection=event_facts,
            ledger_projection=(
            _spot_facts(state, attempt, activation, market=position, previous_reconciliation_bytes_or_null=previous,
                fills=ledger_input["fills"]) if attempt["product"] == "SPOT" else
            _perpetual_facts(state, attempt, activation, position, incomes,
                stop, previous_reconciliation_bytes_or_null=previous,
                fills=ledger_input["fills"])),
            authorized_order=venue["authorized_order"], authorized_stop_or_null=venue["authorized_stop_or_null"],
            order_documents=tuple(map(_decoded, venue["order_documents_base64"])),
            trade_documents=tuple(map(_decoded, venue["trade_documents_base64"])),
            account_document=_decoded(venue["account_document_base64"]),
            position_document=_decoded(venue["position_document_base64"]),
            income_documents=tuple(map(_decoded, venue["income_documents_base64"])),
            algo_documents=tuple(map(_decoded, venue["algo_documents_base64"])),
            previous_reconciliation_bytes_or_null=previous, capture_publications=captured["publications"])
    except BinancePrivateRuntimeError as error:
        _append_intent(state, attempt, "BINANCE_RECONCILIATION_FAILED",
                       recorded_at, reason_code=error.reason_code)
        raise
    client = event_facts["protective_stop_client_id_or_null"]
    return data, client is not None, client
def _order_authority(state, attempt):
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    if not isinstance(private.get("order_id"), int):
        _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
    return {"order_id": private["order_id"], "client_order_id": attempt["venue_client_order_id"]}
def _stop_authority(stop):
    if stop is None: return None
    return {key: stop[key] for key in ("client_algo_id", "side", "quantity",
                                       "trigger_price", "reduce_only")}
def _spot_facts(state, attempt, activation, *, market, previous_reconciliation_bytes_or_null=None, fills=None):
    fills = ([payload for event_type, payload in _private_payloads(state, attempt["opportunity_id"])
              if event_type == "BINANCE_FILL_OBSERVED"] if fills is None else fills)
    quantity = sum((Decimal(item["quantity"]) for item in fills), Decimal(0))
    quote = sum((Decimal(item["quote_quantity"]) for item in fills), Decimal(0))
    mark, _ask, marks = _spot_market(market)
    try:
        fee = sum((Decimal(item["fee"]) * marks[item["fee_asset"]]
                   for item in fills), Decimal(0))
    except KeyError as error: _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID", error)
    quote_fee = sum((Decimal(item["fee"]) for item in fills if item["fee_asset"] == "USDT"), Decimal(0))
    base_fee = sum((Decimal(item["fee"]) for item in fills if item["fee_asset"] == "ETH"), Decimal(0))
    previous = (None if previous_reconciliation_bytes_or_null is None else load_binance_reconciliation_bytes(previous_reconciliation_bytes_or_null)["event_projection"])
    prior_signed = Decimal("0" if previous is None else previous["signed_quantity"])
    prior_average = None if previous is None else previous["average_entry_price_or_null"]
    prior_average = (None if prior_average is None else Decimal(prior_average))
    prior_realized = Decimal("0" if previous is None else previous["realized_pnl"])
    prior_fee = Decimal("0" if previous is None else previous["cumulative_fee"])
    prior_wallet = Decimal(activation.capital_usdt if previous is None else previous["wallet_balance"])
    prior_available = Decimal(activation.capital_usdt if previous is None else previous["available_balance"])
    prior_fills = [] if previous is None else list(previous["fill_ids"])
    if attempt["action"] == "OPEN_LONG":
        signed = prior_signed + quantity - base_fee
        average = None if signed == 0 else (prior_signed * (prior_average or Decimal("0")) + quote) / signed
        realized = prior_realized; available = prior_available - quote - quote_fee
    else:
        if prior_average is None or quantity + base_fee > prior_signed: _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
        signed = prior_signed - quantity - base_fee
        average = None if signed == 0 else prior_average
        realized_increment = quote - (quantity + base_fee) * prior_average
        realized = prior_realized + realized_increment; available = prior_available + quote - quote_fee
    previous_mark = (mark if not prior_signed or prior_average is None else
        prior_average + Decimal("0" if previous is None else previous["unrealized_pnl"]) / prior_signed)
    direction = Decimal(1) if attempt["action"] == "OPEN_LONG" else Decimal(-1)
    fill_price = quote / quantity if quantity else mark
    wallet = prior_wallet + prior_signed * (mark - previous_mark) + direction * quantity * (mark - fill_price) - fee
    facts = {
        "product": "SPOT", "signed_quantity": canonical_decimal(signed),
        "average_entry_price_or_null": None if average is None else canonical_decimal(average), "realized_pnl": canonical_decimal(realized),
        "unrealized_pnl": canonical_decimal(Decimal(0) if average is None else signed * (mark - average)),
        "cumulative_fee": canonical_decimal(prior_fee + fee), "funding": "0",
        "wallet_balance": canonical_decimal(wallet),
        "available_balance": canonical_decimal(available),
        "open_order_count": 0, "protective_stop_client_id_or_null": None,
        "fill_ids": sorted(set(prior_fills + [item["trade_id"] for item in fills])),
    }
    return facts
def _append_fills_fees(state, attempt, recorded_at):
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    if private["stage"] == "BINANCE_FILLS_FEES_REPLAYED": return
    _append_intent(
        state, attempt, "BINANCE_FILLS_FEES_REPLAYED", recorded_at,
        fill_ids=private["fill_ids"], cumulative_fee=canonical_decimal(sum(
            (Decimal(payload["fee"])
             for event_type, payload in _private_payloads(
                 state, attempt["opportunity_id"]
             ) if event_type == "BINANCE_FILL_OBSERVED"), Decimal(0),
        )),
    )
def _finish_spot(state, attempt, activation, order, trades, account, recorded_at):
    _append_fills_fees(state, attempt, recorded_at)
    previous = _previous_reconciliation_bytes(
        state, product="SPOT", before_opportunity_id=attempt["opportunity_id"],
    )
    _capture(state, attempt, _capture_inputs(
        state, attempt, activation, order_documents=(order,),
        trade_documents=trades, account_document=account,
        position_document=_spot_market_document(state, attempt), income_documents=(), algo_documents=(),
        previous=previous, stop=None,
    ), recorded_at)
    data, required, client = _reconcile_captured(state, attempt, activation, recorded_at)
    return _publish_reconciliation(state, attempt, data, required, client, recorded_at)
def _spot_market_document(state, attempt):
    try:
        evidence = state.replay()["opportunities"][attempt["opportunity_id"]]["result_evidence"]
        mark = canonical_decimal(Decimal(evidence["decision"]["indicators"]["latest_close"]))
        ask = canonical_decimal(Decimal(evidence["accounting"]["fill_price"]))
        if Decimal(mark) <= 0 or Decimal(ask) <= 0: raise ValueError
        return canonical_json({"symbol": "ETHUSDT", "mark_price": mark,
            "ask_price": ask, "asset_marks_usdt": {"ETH": mark, "USDT": "1"}}).encode()
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID", error)
def _expected_stop(state, attempt):
    try:
        evidence = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ]["result_evidence"]
        decision = evidence["decision"]
        snapshot = evidence["next_snapshot"]
        protection = snapshot["protective_stop_or_null"]
        fills = [payload for event_type, payload in _private_payloads(
            state, attempt["opportunity_id"]
        ) if event_type == "BINANCE_FILL_OBSERVED"]
        filled = sum((Decimal(item["quantity"]) for item in fills), Decimal(0))
        if (evidence["$schema"]
                != "./challenger-replacement-public-simulation-result-v1.schema.json"
                or decision["action"] != "OPEN_PERP_SHORT"
                or snapshot["position_state"] != "PERP_SHORT"
                or not 0 < filled <= Decimal(attempt["quantity"])
                or protection["status"] != "CONFIRMED_SIMULATED"):
            raise ValueError
        return prepare_binance_protective_stop(short_quantity=canonical_decimal(filled),
            trigger_price=protection["trigger"], intent_identity={
                "plan_hash": state.plan["plan_hash"], "block_id": attempt["block_id"],
                "intent_id": attempt["intent_id"]})
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_STOP_EVIDENCE_REQUIRED", error)
def _stop_request(endpoint, stop, timestamp_ms):
    parameters = {"clientAlgoId": stop["client_algo_id"]}
    if endpoint == "FUTURES_ALGO_CREATE":
        parameters = {
            "algoType": stop["algo_type"], "symbol": stop["symbol"],
            "side": stop["side"], "positionSide": stop["position_side"],
            "type": stop["order_type"], "quantity": stop["quantity"],
            "triggerPrice": stop["trigger_price"],
            "workingType": stop["working_type"],
            "reduceOnly": "true", "closePosition": "false",
            "clientAlgoId": stop["client_algo_id"],
        }
    return build_binance_private_request(endpoint, parameters, timestamp_ms=timestamp_ms)
def _stop_position(position):
    try:
        values = _document(position, list)
        if len(values) != 1:
            raise ValueError
        return canonical_json({key: values[0][key] for key in (
            "symbol", "positionSide", "positionAmt", "entryPrice",
        )}).encode()
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID", error)
def _complete_stop_observation(state, attempt, stop, position, observed, context):
    if observed.response_class != "QUERY_SUCCEEDED": _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    algo = _document(observed.body)
    algo_id = algo.get("algoId")
    if isinstance(algo_id, bool) or not isinstance(algo_id, int) or algo_id <= 0: _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    current = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]["stop"]
    replacement = current.get("replacement")
    candidate = (replacement.get("candidate")
                 if isinstance(replacement, dict) else None)
    if (isinstance(candidate, dict)
            and candidate.get("client_algo_id") == stop["client_algo_id"]):
        current = candidate
    if current["stage"] == "BINANCE_STOP_REQUEST_SEND_STARTED":
        _append(state, "BINANCE_STOP_ACKNOWLEDGED", attempt["opportunity_id"], {
            "protected_intent_id": attempt["intent_id"],
            "client_algo_id": stop["client_algo_id"], "algo_id": algo_id,
        }, context.recorded_at)
    reconciled = reconcile_binance_protective_stop(position=_stop_position(position),
                                                    algo_order=observed.body, expected=stop)
    _append(state, "BINANCE_STOP_RECONCILED", attempt["opportunity_id"],
            reconciled, context.recorded_at)
    return _status("PROTECTION_VERIFIED_RECONCILIATION_PENDING", attempt,
                   client_algo_id=stop["client_algo_id"])
def _create_stop(state, attempt, position, context, stop):
    _append(state, "BINANCE_STOP_INTENT_AUTHORIZED",
            attempt["opportunity_id"], stop, context.recorded_at)
    query = _execute(_stop_request("FUTURES_ALGO_QUERY", stop, context.timestamp_ms), context)
    if not _proven_absent(query): _fail("BINANCE_PRIVATE_RUNTIME_STOP_ABSENCE_NOT_PROVEN")
    _append(state, "BINANCE_STOP_ABSENCE_CHECKED", attempt["opportunity_id"], {
        "protected_intent_id": attempt["intent_id"],
        "client_algo_id": stop["client_algo_id"],
        "query_response_sha256": query.response_sha256,
        "proven_absent": True,
    }, context.recorded_at)
    request = _stop_request("FUTURES_ALGO_CREATE", stop, context.timestamp_ms)
    _append(state, "BINANCE_STOP_SIGNED_REQUEST_PREPARED",
            attempt["opportunity_id"], {
        "protected_intent_id": attempt["intent_id"],
        "client_algo_id": stop["client_algo_id"],
        "request_id": request.request_id,
        "request_sha256": hashlib.sha256(request.encoded_parameters).hexdigest(),
        "timestamp_ms": context.timestamp_ms,
    }, context.recorded_at)
    _append(state, "BINANCE_STOP_REQUEST_SEND_STARTED",
            attempt["opportunity_id"], {
        "protected_intent_id": attempt["intent_id"],
        "client_algo_id": stop["client_algo_id"],
        "request_id": request.request_id,
    }, context.recorded_at)
    created = _execute(request, context)
    if created.response_class not in {"ACKNOWLEDGED", "UNKNOWN"}: _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    observed = _execute(_stop_request("FUTURES_ALGO_QUERY", stop, context.timestamp_ms), context)
    return _complete_stop_observation(state, attempt, stop, position, observed, context)
def _finish_stop_replacement(state, attempt, position, context):
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    old = private.get("stop"); replacement = old.get("replacement") if isinstance(old, dict) else None
    candidate = replacement.get("candidate") if isinstance(replacement, dict) else None
    if not isinstance(candidate, dict) or candidate.get("stage") != "BINANCE_STOP_RECONCILED": _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
    observed_candidate = _execute(_stop_request("FUTURES_ALGO_QUERY", candidate, context.timestamp_ms), context)
    if observed_candidate.response_class != "QUERY_SUCCEEDED": _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    identity = {"plan_hash": state.plan["plan_hash"], "block_id": attempt["block_id"],
                "intent_id": attempt["intent_id"]}
    expected = prepare_binance_protective_stop(short_quantity=candidate["quantity"],
        trigger_price=candidate["trigger_price"], intent_identity=identity)
    if expected["client_algo_id"] != candidate["client_algo_id"]: _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
    reconcile_binance_protective_stop(position=_stop_position(position),
        algo_order=observed_candidate.body, expected=expected)
    if replacement["stage"] == "BINANCE_STOP_REPLACEMENT_STARTED":
        request = _stop_request("FUTURES_ALGO_CANCEL", old, context.timestamp_ms)
        cancel = {"protected_intent_id": attempt["intent_id"],
            "old_client_algo_id": old["client_algo_id"], "new_client_algo_id": candidate["client_algo_id"],
            "request_id": request.request_id,
            "request_sha256": hashlib.sha256(request.encoded_parameters).hexdigest(),
            "timestamp_ms": context.timestamp_ms}
        _append(state, "BINANCE_STOP_REPLACEMENT_CANCEL_SEND_STARTED",
                attempt["opportunity_id"], cancel, context.recorded_at)
        result = _execute(request, context)
        if result.response_class not in {"ACKNOWLEDGED", "UNKNOWN"}: _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    elif replacement["stage"] != "BINANCE_STOP_REPLACEMENT_CANCEL_SEND_STARTED":
        _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
    observed_old = _execute(_stop_request("FUTURES_ALGO_QUERY", old, context.timestamp_ms), context)
    active, algo_id = _cleanup_query_observation(observed_old, old["client_algo_id"])
    if active or algo_id is not None and algo_id != old.get("algo_id"): _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    success = {"protected_intent_id": attempt["intent_id"],
        "old_client_algo_id": old["client_algo_id"], "new_client_algo_id": candidate["client_algo_id"],
        "reason_code_or_null": None}
    _append(state, "BINANCE_STOP_REPLACEMENT_SUCCEEDED", attempt["opportunity_id"], success, context.recorded_at)
    return _status("PROTECTION_VERIFIED_RECONCILIATION_PENDING", attempt, client_algo_id=candidate["client_algo_id"])
def _inherit_stop(state, attempt, position, context):
    previous = _previous_reconciliation_bytes(state, product="PERPETUAL",
        before_opportunity_id=attempt["opportunity_id"])
    if previous is None: _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
    loaded = load_binance_reconciliation_bytes(previous); prior = loaded["event_projection"]
    client = prior["protective_stop_client_id_or_null"]
    observed = _execute(_stop_request("FUTURES_ALGO_QUERY",
        {"client_algo_id": client}, context.timestamp_ms), context)
    if observed.response_class != "QUERY_SUCCEEDED": _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    algo = _document(observed.body); current = _document(_stop_position(position))
    try:
        prior_quantity = canonical_decimal(-Decimal(prior["signed_quantity"])); quantity = canonical_decimal(algo["quantity"])
        trigger = canonical_decimal(algo["triggerPrice"]); amount = Decimal(canonical_decimal(current["positionAmt"])); algo_id = algo["algoId"]
    except (KeyError, TypeError, ValueError) as error:
        _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP", error)
    static = (algo["algoType"], algo["orderType"], algo["symbol"], algo["side"],
              algo["positionSide"], algo["workingType"])
    exact = (frozenset(algo) == _ALGO_KEYS and algo["clientAlgoId"] == client
        and static == ("CONDITIONAL", "STOP_MARKET", "ETHUSDT", "BUY", "BOTH", "MARK_PRICE")
        and quantity == prior_quantity and algo["reduceOnly"] is True
        and algo["closePosition"] is False and algo["algoStatus"] == "NEW"
        and isinstance(algo_id, int) and not isinstance(algo_id, bool) and algo_id > 0
        and Decimal(prior["signed_quantity"]) < 0 and -Decimal(prior_quantity) <= amount < 0)
    if not exact: _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    payload = {"protected_intent_id": attempt["intent_id"], "prior_reconciliation_id": loaded["reconciliation_id"],
        "client_algo_id": client, "algo_id": algo_id, "quantity": quantity,
        "trigger_price": trigger, "query_response_sha256": observed.response_sha256}
    _append(state, "BINANCE_STOP_INHERITED", attempt["opportunity_id"], payload, context.recorded_at)
    return state.replay()["opportunities"][attempt["opportunity_id"]]["private"]["stop"]
def _desired_stop(state, attempt, position, current):
    if attempt["action"] == "OPEN_SHORT": return _expected_stop(state, attempt)
    try:
        amount = Decimal(_document(_stop_position(position))["positionAmt"])
        if amount >= 0 or not isinstance(current, Mapping): raise ValueError
        identity = {"plan_hash": state.plan["plan_hash"], "block_id": attempt["block_id"],
                    "intent_id": attempt["intent_id"]}
        return prepare_binance_protective_stop(short_quantity=canonical_decimal(-amount),
            trigger_price=current["trigger_price"], intent_identity=identity)
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_STOP_EVIDENCE_REQUIRED", error)
def _verify_current_stop(attempt, position, stop, context):
    observed = _execute(_stop_request("FUTURES_ALGO_QUERY", stop, context.timestamp_ms), context)
    if observed.response_class != "QUERY_SUCCEEDED": _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    reconcile_binance_protective_stop(position=_stop_position(position), algo_order=observed.body, expected=stop)
    return _status("PROTECTION_VERIFIED_RECONCILIATION_PENDING", attempt,
                   client_algo_id=stop["client_algo_id"])
def _ensure_stop(state, attempt, position, context):
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    current = private.get("stop")
    if current is None and attempt["action"] == "CLOSE_SHORT":
        current = _inherit_stop(state, attempt, position, context)
    desired = _desired_stop(state, attempt, position, current)
    if current is None: return _create_stop(state, attempt, position, context, desired)
    if current.get("client_algo_id") == desired["client_algo_id"]: return _verify_current_stop(attempt, position, desired, context)
    replacement = current.get("replacement")
    if replacement is None:
        payload = {"protected_intent_id": attempt["intent_id"],
            "old_client_algo_id": current["client_algo_id"], "new_client_algo_id": desired["client_algo_id"]}
        _append(state, "BINANCE_STOP_REPLACEMENT_STARTED", attempt["opportunity_id"], payload, context.recorded_at)
        replacement = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]["stop"]["replacement"]
    if replacement.get("new_client_algo_id") != desired["client_algo_id"]: _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
    candidate = replacement.get("candidate")
    if not isinstance(candidate, dict):
        _create_stop(state, attempt, position, context, desired)
    elif candidate.get("stage") != "BINANCE_STOP_RECONCILED":
        return _resume_stop(state, attempt, private, context,
                            stop=desired, position_bytes=position)
    return _finish_stop_replacement(state, attempt, position, context)
def _perpetual_facts(state, attempt, activation, position, incomes, stop, previous_reconciliation_bytes_or_null=None, fills=None):
    fills = ([payload for event_type, payload in _private_payloads(state,
        attempt["opportunity_id"]) if event_type == "BINANCE_FILL_OBSERVED"]
        if fills is None else fills)
    try:
        positions = _document(position, list)
        if len(positions) != 1: raise ValueError
        position_value = positions[0]
        income_values = [_document(item) for item in incomes]
        quantity = sum((Decimal(item["quantity"]) for item in fills), Decimal(0))
        weighted = sum((Decimal(item["quantity"]) * Decimal(item["price"]) for item in fills), Decimal(0))
        fee = sum((Decimal(item["fee"]) for item in fills), Decimal(0))
        current_realized = sum((Decimal(item["realized_pnl"]) for item in fills), Decimal(0))
        current_funding = sum((Decimal(item["income"]) for item in income_values), Decimal(0))
        previous = (None if previous_reconciliation_bytes_or_null is None else
                    load_binance_reconciliation_bytes(previous_reconciliation_bytes_or_null)["event_projection"])
        prior_signed = Decimal("0" if previous is None else previous["signed_quantity"])
        prior_average = None if previous is None else previous["average_entry_price_or_null"]
        prior_average = None if prior_average is None else Decimal(prior_average)
        prior_realized = Decimal("0" if previous is None else previous["realized_pnl"])
        prior_fee = Decimal("0" if previous is None else previous["cumulative_fee"])
        prior_funding = Decimal("0" if previous is None else previous["funding"])
        prior_wallet = Decimal(activation.capital_usdt if previous is None else previous["wallet_balance"])
        prior_fills = [] if previous is None else list(previous["fill_ids"])
        if attempt["action"] == "OPEN_SHORT":
            signed = prior_signed - quantity
            average = None if signed == 0 else (-prior_signed * (prior_average or Decimal("0")) + weighted) / -signed
        else:
            if prior_average is None or quantity > -prior_signed: _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
            signed = prior_signed + quantity
            average = None if signed == 0 else prior_average
        if Decimal(position_value["positionAmt"]) != signed: _fail("VENUE_LOCAL_POSITION_MISMATCH")
        realized = prior_realized + current_realized; funding = prior_funding + current_funding
        wallet = prior_wallet + current_realized - fee + current_funding; available = wallet - Decimal(position_value["isolatedMargin"])
        client = None
        if signed < 0:
            if not isinstance(stop, Mapping): _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
            client = stop["client_algo_id"]
        facts = {"product": "PERPETUAL", "signed_quantity": canonical_decimal(signed),
            "average_entry_price_or_null": None if average is None else canonical_decimal(average),
            "realized_pnl": canonical_decimal(realized),
            "unrealized_pnl": canonical_decimal(Decimal(position_value["unRealizedProfit"])),
            "cumulative_fee": canonical_decimal(prior_fee + fee),
            "funding": canonical_decimal(funding),
            "wallet_balance": canonical_decimal(wallet),
            "available_balance": canonical_decimal(available),
            "open_order_count": 0,
            "protective_stop_client_id_or_null": client,
            "fill_ids": sorted(set(prior_fills + [item["trade_id"] for item in fills]))}
        return facts
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID", error)
def _finish_perpetual(state, attempt, activation, stop, context,
                      previous_reconciliation_bytes_or_null=None):
    order_result = _query_order(attempt, context)
    order = _document(order_result.body)
    order_id = order.get("orderId")
    if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id <= 0: _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID")
    trades = _query("FUTURES_TRADES", {"symbol": "ETHUSDT", "orderId": str(order_id)}, context)
    account = _query("FUTURES_ACCOUNT", {}, context)
    position = _query("FUTURES_POSITION", {"symbol": "ETHUSDT"}, context)
    try:
        scheduled = datetime.fromisoformat(
            attempt["opportunity_id"].split("@", 1)[1].replace("Z", "+00:00")
        )
        start_ms = int(scheduled.timestamp() * 1000)
    except (IndexError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID", error)
    income = _query("FUTURES_INCOME", {
        "symbol": "ETHUSDT", "incomeType": "FUNDING_FEE",
        "startTime": str(start_ms), "endTime": str(context.timestamp_ms),
    }, context)
    algos = _query("FUTURES_OPEN_ALGO_ORDERS", {"symbol": "ETHUSDT"}, context)
    income_documents = _tuple_documents(income.body)
    algo_documents = _tuple_documents(algos.body)
    previous = (previous_reconciliation_bytes_or_null
                if previous_reconciliation_bytes_or_null is not None else
                _previous_reconciliation_bytes(
                    state, product="PERPETUAL",
                    before_opportunity_id=attempt["opportunity_id"],
                ))
    _capture(state, attempt, _capture_inputs(
        state, attempt, activation, order_documents=(order_result.body,),
        trade_documents=_tuple_documents(trades.body),
        account_document=account.body, position_document=position.body,
        income_documents=income_documents, algo_documents=algo_documents,
        previous=previous, stop=stop,
    ), context.recorded_at)
    data, required, client = _reconcile_captured(state, attempt, activation, context.recorded_at)
    return _publish_reconciliation(state, attempt, data, required, client, context.recorded_at)
def _cleanup_query_observation(result, client):
    if _proven_absent(result): return False, None
    if result.response_class != "QUERY_SUCCEEDED": _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    try:
        document = _document(result.body)
        algo_id = document["algoId"]
        if (document["clientAlgoId"] != client
                or isinstance(algo_id, bool) or not isinstance(algo_id, int)
                or algo_id <= 0):
            raise ValueError
        if document["algoStatus"] == "NEW": return True, algo_id
        if document["algoStatus"] in {
                "CANCELED", "REJECTED", "EXPIRED", "FINISHED",
            }:
            return False, algo_id
        raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP", error)
def _cleanup_perpetual_stop(state, attempt, previous, context):
    loaded = load_binance_reconciliation_bytes(previous)
    prior = loaded["event_projection"]
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    current = private.get("stop")
    client = (current["client_algo_id"] if isinstance(current, dict)
              and current.get("stage") == "BINANCE_STOP_RECONCILED" else
              prior["protective_stop_client_id_or_null"])
    if (Decimal(prior["signed_quantity"]) >= 0 or not isinstance(client, str)): _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
    cleanup = private.get("stop_cleanup")
    if cleanup is None:
        _append_intent(
            state, attempt, "BINANCE_STOP_CLEANUP_AUTHORIZED",
            context.recorded_at, client_algo_id=client,
            prior_reconciliation_id=loaded["reconciliation_id"],
        )
        cleanup = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ]["private"]["stop_cleanup"]
    if cleanup["client_algo_id"] != client: _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
    if cleanup["stage"] == "BINANCE_STOP_CLEANUP_AUTHORIZED":
        observed = _execute(_stop_request(
            "FUTURES_ALGO_QUERY", {"client_algo_id": client},
            context.timestamp_ms,
        ), context)
        active, algo_id = _cleanup_query_observation(observed, client)
        if active:
            request = _stop_request(
                "FUTURES_ALGO_CANCEL", {"client_algo_id": client},
                context.timestamp_ms,
            )
            _append_intent(
                state, attempt, "BINANCE_STOP_CLEANUP_REQUEST_PREPARED",
                context.recorded_at, client_algo_id=client,
                query_response_sha256=observed.response_sha256,
                algo_id=algo_id, request_id=request.request_id,
                request_sha256=hashlib.sha256(
                    request.encoded_parameters
                ).hexdigest(), timestamp_ms=context.timestamp_ms,
            )
        else:
            _append_intent(
                state, attempt, "BINANCE_STOP_CLEANUP_RECONCILED",
                context.recorded_at, client_algo_id=client,
                query_response_sha256=observed.response_sha256,
                status="BINANCE_FLAT_STOP_CLEANED",
            )
        cleanup = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ]["private"]["stop_cleanup"]
    if cleanup["stage"] == "BINANCE_STOP_CLEANUP_REQUEST_PREPARED":
        request = _stop_request(
            "FUTURES_ALGO_CANCEL", {"client_algo_id": client},
            cleanup["request_timestamp_ms"],
        )
        if (request.request_id != cleanup["request_id"]
                or hashlib.sha256(request.encoded_parameters).hexdigest()
                != cleanup["request_sha256"]):
            _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
        _append_intent(
            state, attempt, "BINANCE_STOP_CLEANUP_SEND_STARTED",
            context.recorded_at, client_algo_id=client,
            request_id=request.request_id,
        )
        result = _execute(request, context)
        if result.response_class not in {"ACKNOWLEDGED", "UNKNOWN"}: _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
        cleanup = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ]["private"]["stop_cleanup"]
    if cleanup["stage"] == "BINANCE_STOP_CLEANUP_SEND_STARTED":
        observed = _execute(_stop_request(
            "FUTURES_ALGO_QUERY", {"client_algo_id": client},
            context.timestamp_ms,
        ), context)
        active, algo_id = _cleanup_query_observation(observed, client)
        if active: _fail("BINANCE_FLAT_ORPHAN_STOP_ACTIVE")
        if algo_id is not None and algo_id != cleanup["algo_id"]: _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
        _append_intent(
            state, attempt, "BINANCE_STOP_CLEANUP_RECONCILED",
            context.recorded_at, client_algo_id=client,
            query_response_sha256=observed.response_sha256,
            status="BINANCE_FLAT_STOP_CLEANED",
        )
        cleanup = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ]["private"]["stop_cleanup"]
    if cleanup["stage"] != "BINANCE_STOP_CLEANUP_RECONCILED": _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
    return _finish_perpetual(
        state, attempt, context.activation, None, context,
        previous_reconciliation_bytes_or_null=previous,
    )
def _resume_stop(state, attempt, private, context, *, stop=None,
                 position_bytes=None):
    stop = _expected_stop(state, attempt) if stop is None else stop
    current = private.get("stop")
    replacement = current.get("replacement") if isinstance(current, dict) else None
    candidate = replacement.get("candidate") if isinstance(replacement, dict) else None
    replacing = isinstance(candidate, dict)
    if replacing: current = candidate
    if (not isinstance(current, dict)
            or any(current.get(key) != stop[key] for key in (
                "client_algo_id", "quantity", "trigger_price",
            ))
            or current.get("stage") not in {
                "BINANCE_STOP_SIGNED_REQUEST_PREPARED",
                "BINANCE_STOP_REQUEST_SEND_STARTED",
                "BINANCE_STOP_ACKNOWLEDGED", "BINANCE_STOP_RECONCILED",
            }):
        _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
    if current["stage"] == "BINANCE_STOP_RECONCILED":
        if replacing:
            if position_bytes is None:
                position_bytes = _query("FUTURES_POSITION", {"symbol": "ETHUSDT"}, context).body
            return _finish_stop_replacement(state, attempt, position_bytes, context)
        return _finish_perpetual(
            state, attempt, context.activation, stop, context,
        )
    if position_bytes is None:
        position_bytes = _query("FUTURES_POSITION", {"symbol": "ETHUSDT"}, context).body
    if current["stage"] == "BINANCE_STOP_SIGNED_REQUEST_PREPARED":
        request = _stop_request(
            "FUTURES_ALGO_CREATE", stop, current["request_timestamp_ms"],
        )
        if (request.request_id != current["request_id"]
                or hashlib.sha256(request.encoded_parameters).hexdigest()
                != current["request_sha256"]):
            _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
        _append(state, "BINANCE_STOP_REQUEST_SEND_STARTED",
                attempt["opportunity_id"], {
            "protected_intent_id": attempt["intent_id"],
            "client_algo_id": stop["client_algo_id"],
            "request_id": request.request_id,
        }, context.recorded_at)
        created = _execute(request, context)
        if created.response_class not in {"ACKNOWLEDGED", "UNKNOWN"}: _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    observed = _execute(_stop_request(
        "FUTURES_ALGO_QUERY", stop, context.timestamp_ms,
    ), context)
    result = _complete_stop_observation(
        state, attempt, stop, position_bytes, observed, context,
    )
    return (_finish_stop_replacement(state, attempt, position_bytes, context)
            if replacing else result)
def _observe_order(*, state, attempt, order_result, context):
    order = _document(order_result.body)
    order_id = order.get("orderId")
    if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id <= 0: _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID")
    spot = attempt["product"] == "SPOT"
    trades_result = _query("SPOT_TRADES" if spot else "FUTURES_TRADES", {"symbol": "ETHUSDT", "orderId": str(order_id)}, context)
    account_result = _query("SPOT_ACCOUNT" if spot else "FUTURES_POSITION", {} if spot else {"symbol": "ETHUSDT"}, context)
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    if private["stage"] == "BINANCE_ORDER_UNKNOWN":
        _append_intent(state, attempt, "BINANCE_UNKNOWN_QUERY_OBSERVED", context.recorded_at,
            venue_client_order_id=attempt["venue_client_order_id"],
            order_response_sha256=order_result.response_sha256,
            trades_response_sha256=trades_result.response_sha256,
            account_response_sha256=account_result.response_sha256)
        private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    events = apply_binance_order_observation(attempt=attempt, order=order_result.body, trades=_tuple_documents(trades_result.body), account=account_result.body)
    initial_stage = private["stage"]
    replaying_terminal = initial_stage in _TERMINAL_ORDERS
    new_fill = False
    for event in events:
        if (replaying_terminal
                or event["event_type"] == "BINANCE_ORDER_ACKNOWLEDGED"
                and initial_stage not in {"BINANCE_REQUEST_SEND_STARTED", "BINANCE_UNKNOWN_QUERY_OBSERVED"}):
            continue
        if (event["event_type"] == "BINANCE_FILL_OBSERVED"
                and event["payload"]["trade_id"] in private["fill_ids"]):
            continue
        if (initial_stage == "BINANCE_FILLS_FEES_REPLAYED"
                and event["event_type"].startswith("BINANCE_ORDER_")
                and not new_fill):
            continue
        _append(state, event["event_type"], attempt["opportunity_id"], event["payload"], context.recorded_at)
        new_fill = new_fill or event["event_type"] == "BINANCE_FILL_OBSERVED"
    terminal = events[-1]["event_type"] if events else None
    if (initial_stage == "BINANCE_FILLS_FEES_REPLAYED" and not new_fill
            and attempt["product"] == "PERPETUAL"
            and attempt["action"] == "OPEN_SHORT"):
        return _ensure_stop(state, attempt, account_result.body, context)
    if terminal in _TERMINAL_ORDERS:
        if spot: return _finish_spot(
                state, attempt, context.activation, order_result.body,
                _tuple_documents(trades_result.body), account_result.body,
                context.recorded_at,
            )
        _append_fills_fees(state, attempt, context.recorded_at)
        if attempt["action"] == "CLOSE_SHORT":
            previous = _previous_reconciliation_bytes(
                state, product="PERPETUAL",
                before_opportunity_id=attempt["opportunity_id"],
            )
            if previous is None: _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
            return _cleanup_perpetual_stop(
                state, attempt, previous, context,
            )
        return _ensure_stop(
            state, attempt, account_result.body, context,
        )
    if terminal == "BINANCE_ORDER_PARTIALLY_FILLED" and not spot:
        _append_fills_fees(state, attempt, context.recorded_at); return _ensure_stop(state, attempt, account_result.body, context)
    return _status(
        (
            "ORDER_IN_PROGRESS"
            if terminal in {"BINANCE_ORDER_ACKNOWLEDGED",
                            "BINANCE_ORDER_PARTIALLY_FILLED"}
            else "ORDER_TERMINAL_REQUIRES_RECONCILIATION"
        ),
        attempt, order_response_sha256=order_result.response_sha256,
    )
def _record_unknown(state, attempt, result, recorded_at):
    try:
        document = json.loads(result.body.decode("utf-8"))
        venue_code = document.get("code", -1000)
        if isinstance(venue_code, bool) or not isinstance(venue_code, int):
            venue_code = -1000
    except (UnicodeDecodeError, ValueError):
        venue_code = -1000
    _append_intent(state, attempt, "BINANCE_ORDER_UNKNOWN", recorded_at,
                   venue_code=venue_code, blocks_new_risk=True)
    return _status("UNRESOLVED_ECONOMIC_ORDER_UNKNOWN", attempt)
def _query_order(attempt, context): return _query(
        attempt["required_first_endpoint"], {
            "symbol": "ETHUSDT",
            "origClientOrderId": attempt["venue_client_order_id"],
        }, context,
    )
def _send_request(state, attempt, request, context):
    result = _execute(request, context)
    if result.response_class == "UNKNOWN": return _record_unknown(state, attempt, result, context.recorded_at)
    if result.response_class != "ACKNOWLEDGED": _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_REQUIRED")
    return _observe_order(
        state=state, attempt=attempt,
        order_result=_query_order(attempt, context), context=context,
    )
def _resume_perpetual_fills(state, attempt, existing, context):
    types = [event_type for event_type, _payload in _private_payloads(
        state, attempt["opportunity_id"]) if event_type in _TERMINAL_ORDERS | {
            "BINANCE_ORDER_PARTIALLY_FILLED"}]
    if not types: _fail("BINANCE_PRIVATE_RUNTIME_RECOVERY_STAGE_UNSUPPORTED")
    if types[-1] == "BINANCE_ORDER_PARTIALLY_FILLED":
        return _observe_order(state=state, attempt=attempt,
            order_result=_query_order(attempt, context), context=context)
    if attempt["action"] == "CLOSE_SHORT":
        previous = _previous_reconciliation_bytes(state, product="PERPETUAL",
            before_opportunity_id=attempt["opportunity_id"])
        if previous is None: _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
        return _cleanup_perpetual_stop(state, attempt, previous, context)
    if isinstance(existing.get("stop"), dict):
        return _resume_stop(state, attempt, existing, context)
    return _observe_order(state=state, attempt=attempt,
        order_result=_query_order(attempt, context), context=context)
def run_challenger_replacement_binance_private_intent(
    *, state, event_root, intent, preflight_capability, activation, credential,
    build_identity
):
    """Run one query-first intent through the fixed private transport."""
    _require_identity(state, event_root, build_identity)
    _require_decision_intent(state, intent, activation)
    if not isinstance(preflight_capability, BinanceAccountPreflightCapability): _fail("BINANCE_PRIVATE_RUNTIME_PREFLIGHT_AUTHORITY_INVALID")
    now = _wall_now()
    try:
        recorded_at = utc_datetime(now)
        preflight = preflight_capability.load(
            activation=activation, credential_identity=credential.identity,
            now=recorded_at,
        )
        attempt = prepare_binance_order_attempt(
            intent=intent,
            projection=_runtime_projection(state),
            preflight=preflight,
            activation=activation,
        )
        preflight_hash = hashlib.sha256(
            canonical_json(dict(preflight)).encode("utf-8")
        ).hexdigest()
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_INTENT_INVALID", error)
    existing = _existing_private(state, attempt)
    if existing is not None:
        if existing["stage"] == "BINANCE_RECONCILIATION_SUCCEEDED":
            loaded = _reconciliation(existing, state.event_root)
            return _status(
                "TERMINAL_RECONCILED", attempt,
                reconciliation_id=existing["reconciliation_id"],
            )
        if existing["stage"] in {
            "BINANCE_POSITION_BALANCE_RECONCILED",
            "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED",
        }:
            return _resume_reconciliation(
                state, attempt, existing, recorded_at,
            )
        if existing["stage"] == "BINANCE_RECONCILIATION_INPUTS_CAPTURED":
            data, required, client = _reconcile_captured(
                state, attempt, activation, recorded_at,
            )
            return _publish_reconciliation(
                state, attempt, data, required, client, recorded_at,
            )
    else:
        _append_intent(state, attempt, "BINANCE_INTENT_AUTHORIZED", recorded_at,
            opportunity_id=attempt["opportunity_id"], block_id=attempt["block_id"],
            product=attempt["product"], action=attempt["action"],
            quantity=attempt["quantity"],
            venue_client_order_id=attempt["venue_client_order_id"],
            activation_id=attempt["activation_id"], preflight_sha256=preflight_hash,
            unsigned_intent_sha256=attempt["unsigned_intent_sha256"],
        )
    context = _fresh_context(
        state, attempt, credential, activation, build_identity, recorded_at,
    )
    timestamp_ms = context.timestamp_ms
    if existing is not None:
        if existing["stage"] == "BINANCE_ORDER_UNKNOWN":
            observed = _execute(_request(attempt["required_first_endpoint"], attempt, context.timestamp_ms), context)
            if observed.response_class != "QUERY_SUCCEEDED": return _status("UNRESOLVED_ECONOMIC_ORDER_UNKNOWN", attempt)
            return _observe_order(state=state, attempt=attempt, order_result=observed, context=context)
        if (existing["stage"] in _TERMINAL_ORDERS | {
                "BINANCE_FILLS_FEES_REPLAYED",
            }
                and attempt["product"] == "SPOT"):
            return _observe_order(
                state=state, attempt=attempt,
                order_result=_query_order(attempt, context), context=context,
            )
        if (existing["stage"] == "BINANCE_FILLS_FEES_REPLAYED"
                and attempt["product"] == "PERPETUAL"):
            return _resume_perpetual_fills(state, attempt, existing, context)
        if existing["stage"] == "BINANCE_REQUEST_SEND_STARTED": return _recover_after_send(
                state=state, attempt=attempt, context=context,
            )
        if existing["stage"] == "BINANCE_SIGNED_REQUEST_PREPARED":
            request = _request(
                existing["request_endpoint_id"], attempt,
                existing["request_timestamp_ms"],
            )
            if (request.request_id != existing["request_id"]
                    or hashlib.sha256(request.encoded_parameters).hexdigest()
                    != existing["request_sha256"]):
                _fail("BINANCE_PRIVATE_RUNTIME_REQUEST_REPLAY_INVALID")
            _append_intent(
                state, attempt, "BINANCE_REQUEST_SEND_STARTED", recorded_at,
                request_id=request.request_id,
            )
            return _send_request(state, attempt, request, context)
        if existing["stage"] in {
            "BINANCE_ORDER_ACKNOWLEDGED", "BINANCE_FILL_OBSERVED",
            "BINANCE_ORDER_PARTIALLY_FILLED",
        }:
            return _observe_order(
                state=state, attempt=attempt,
                order_result=_query_order(attempt, context),
                context=context,
            )
        _fail("BINANCE_PRIVATE_RUNTIME_RECOVERY_STAGE_UNSUPPORTED")
    query = _request(attempt["required_first_endpoint"], attempt, timestamp_ms)
    query_result = _execute(query, context)
    if not _proven_absent(query_result): _fail("BINANCE_PRIVATE_RUNTIME_ORDER_ABSENCE_NOT_PROVEN")
    _append_intent(
        state, attempt, "BINANCE_ABSENCE_CHECKED", recorded_at,
        venue_client_order_id=attempt["venue_client_order_id"],
        query_response_sha256=query_result.response_sha256, proven_absent=True,
    )
    attempt = prepare_binance_order_attempt(
        intent=intent, projection=_runtime_projection(state),
        preflight=preflight, activation=activation,
    )
    endpoint = (
        "SPOT_ORDER_CREATE"
        if attempt["product"] == "SPOT"
        else "FUTURES_ORDER_CREATE"
    )
    request = _request(endpoint, attempt, timestamp_ms)
    _append_intent(
        state, attempt, "BINANCE_SIGNED_REQUEST_PREPARED", recorded_at,
        request_id=request.request_id, endpoint_id=request.endpoint_id,
        request_sha256=hashlib.sha256(request.encoded_parameters).hexdigest(),
        timestamp_ms=timestamp_ms,
    )
    _append_intent(state, attempt, "BINANCE_REQUEST_SEND_STARTED", recorded_at,
                   request_id=request.request_id)
    return _send_request(state, attempt, request, context)
