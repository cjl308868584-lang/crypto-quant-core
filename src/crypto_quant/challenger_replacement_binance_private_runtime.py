"""Append-only orchestration for the fixed Binance private boundary."""
import base64
from datetime import datetime, timezone
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Mapping
from .canonical import canonical_decimal, canonical_json, utc_datetime
from .challenger_replacement_binance_private_lifecycle import (
    _document, apply_binance_order_observation,
    build_binance_order_intent_from_opportunity, prepare_binance_order_attempt,
    prepare_binance_protective_stop, reconcile_binance_protective_stop,
)
from .challenger_replacement_binance_private_protocol import (
    build_binance_private_request,
)
from .challenger_replacement_binance_private_transport import (
    execute_binance_private_request,
)
from .challenger_replacement_binance_preflight import (
    BinanceAccountPreflightCapability,
)
from .challenger_replacement_binance_reconciliation import (
    load_binance_reconciliation_bytes, reconcile_binance_private_state,
)
from .challenger_replacement_events import ChallengerReplacementEventRoot
from .challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
_TERMINAL_ORDERS = frozenset({
    "BINANCE_ORDER_FILLED", "BINANCE_ORDER_CANCELED",
    "BINANCE_ORDER_EXPIRED", "BINANCE_ORDER_REJECTED",
})
class BinancePrivateRuntimeError(RuntimeError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code
@dataclass(frozen=True)
class _Context:
    credential: object
    activation: object
    build_identity: Mapping
    recorded_at: str
    timestamp_ms: int
def _fail(reason, error=None):
    failure = BinancePrivateRuntimeError(reason)
    if error is None:
        raise failure
    raise failure from error
def _require_identity(state, event_root, build_identity):
    if (
        not isinstance(state, ChallengerReplacementOpportunityState)
        or not isinstance(event_root, ChallengerReplacementEventRoot)
        or state.event_root is not event_root
        or not isinstance(build_identity, Mapping)
        or dict(build_identity) != state.build_identity
    ):
        _fail("BINANCE_PRIVATE_RUNTIME_IDENTITY_INVALID")
    try:
        event_root.validate()
    except Exception as error:
        _fail("BINANCE_PRIVATE_RUNTIME_IDENTITY_INVALID", error)
def _require_decision_intent(state, intent, activation):
    try:
        slot = state.replay()["opportunities"][intent["opportunity_id"]]
        evidence = slot.get("result_evidence")
        if (isinstance(evidence, Mapping) and evidence.get("$schema")
                == "./challenger-replacement-public-simulation-result-v1.schema.json"):
            expected = build_binance_order_intent_from_opportunity(
                slot=slot, activation=activation,
                attempt_ordinal=intent["attempt_ordinal"],
            )
            if dict(intent) != expected:
                _fail("BINANCE_PRIVATE_RUNTIME_INTENT_DECISION_MISMATCH")
    except BinancePrivateRuntimeError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_INTENT_DECISION_MISMATCH", error)
def _wall_now():
    return datetime.now(timezone.utc)
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
    return state.append(
        event_type=event_type,
        opportunity_id=opportunity_id,
        worker_id="binance-private-runtime-v1",
        recorded_at=recorded_at,
        payload=payload,
        expected_last_event_hash=projection["last_event_hash"],
    )
def _append_intent(state, attempt, event_type, recorded_at, **payload):
    return _append(state, event_type, attempt["opportunity_id"], {
        "intent_id": attempt["intent_id"], **payload,
    }, recorded_at)
def _status(status, attempt, **extra):
    return {
        "status": status, "opportunity_id": attempt["opportunity_id"],
        "intent_id": attempt["intent_id"],
        "venue_client_order_id": attempt["venue_client_order_id"], **extra,
    }
def _reconciliation_bytes(private):
    try:
        data = base64.b64decode(
            private["reconciliation_bytes_base64"], validate=True,
        )
        loaded = load_binance_reconciliation_bytes(data)
        if (hashlib.sha256(data).hexdigest()
                != private["reconciliation_sha256"]
                or loaded["reconciliation_id"]
                != private["reconciliation_id"]):
            raise ValueError
        return data, loaded
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID", error)
def _reconciliation(private):
    return _reconciliation_bytes(private)[1]
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
        if not candidates:
            return None
        return _reconciliation_bytes(max(candidates, key=lambda item: item[0])[1])[0]
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
    _append_intent(state, attempt, "BINANCE_RECONCILIATION_SUCCEEDED",
                   recorded_at,
                   reconciliation_id=loaded["reconciliation_id"])
    return _status("TERMINAL_RECONCILED", attempt,
                   reconciliation_id=loaded["reconciliation_id"])
def _publish_reconciliation(state, attempt, data, required, client, recorded_at):
    loaded = load_binance_reconciliation_bytes(data)
    _append_intent(
        state, attempt, "BINANCE_POSITION_BALANCE_RECONCILED", recorded_at,
        reconciliation_id=loaded["reconciliation_id"],
        reconciliation_bytes_base64=base64.b64encode(data).decode("ascii"),
        reconciliation_sha256=hashlib.sha256(data).hexdigest(),
    )
    return _append_reconciliation_tail(
        state, attempt, loaded, required, client, recorded_at,
    )
def _resume_reconciliation(state, attempt, private, recorded_at):
    loaded = _reconciliation(private)
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
    return build_binance_private_request(
        endpoint_id, parameters, timestamp_ms=timestamp_ms
    )
def _proven_absent(result):
    try:
        document = json.loads(result.body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return False
    return (
        result.status_or_null == 400
        and document == {"code": -2013, "msg": "Order does not exist."}
    )
def _existing_private(state, attempt):
    try:
        private = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ].get("private")
    except (AttributeError, KeyError, TypeError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_IDENTITY_INVALID", error)
    if private is None:
        return None
    expected = {
        "intent_id": attempt["intent_id"], "block_id": attempt["block_id"],
        "product": attempt["product"], "action": attempt["action"],
        "quantity": attempt["quantity"],
        "venue_client_order_id": attempt["venue_client_order_id"],
        "activation_id": attempt["activation_id"],
        "unsigned_intent_sha256": attempt["unsigned_intent_sha256"],
    }
    if any(private.get(key) != value for key, value in expected.items()):
        _fail("BINANCE_PRIVATE_RUNTIME_INTENT_CONFLICT")
    return private
def _execute(request, context):
    return execute_binance_private_request(
        request, credential=context.credential, activation=context.activation,
        expected_build_identity=context.build_identity,
        now=context.recorded_at,
    )
def _recover_after_send(*, state, attempt, context):
    query = _request(
        attempt["required_first_endpoint"], attempt, context.timestamp_ms
    )
    result = _execute(query, context)
    if _proven_absent(result):
        _fail("BINANCE_PRIVATE_RUNTIME_ABSENT_AFTER_SEND_STARTED")
    if result.response_class != "QUERY_SUCCEEDED":
        _fail("BINANCE_PRIVATE_RUNTIME_RECOVERY_QUERY_UNRESOLVED")
    return _observe_order(
        state=state, attempt=attempt, order_result=result, context=context,
    )
def _query(endpoint_id, parameters, context):
    request = build_binance_private_request(
        endpoint_id, parameters, timestamp_ms=context.timestamp_ms
    )
    result = _execute(request, context)
    if result.response_class != "QUERY_SUCCEEDED":
        _fail("BINANCE_PRIVATE_RUNTIME_RECOVERY_QUERY_UNRESOLVED")
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
        if (document["slot_id"] == opportunity_id
                and document["event_type"].startswith("BINANCE_")):
            values.append((document["event_type"], json.loads(base64.b64decode(
                document["payload_bytes_base64"], validate=True,
            ))))
    return values
def _spot_facts(state, attempt, activation,
                previous_reconciliation_bytes_or_null=None):
    fills = [payload for event_type, payload in _private_payloads(
        state, attempt["opportunity_id"]
    ) if event_type == "BINANCE_FILL_OBSERVED"]
    quantity = sum((Decimal(item["quantity"]) for item in fills), Decimal(0))
    quote = sum((Decimal(item["quote_quantity"]) for item in fills), Decimal(0))
    fee = sum((Decimal(item["fee"]) for item in fills), Decimal(0))
    previous = (None if previous_reconciliation_bytes_or_null is None else
                load_binance_reconciliation_bytes(
                    previous_reconciliation_bytes_or_null
                )["event_projection"])
    prior_signed = Decimal("0" if previous is None else
                           previous["signed_quantity"])
    prior_average = (None if previous is None else
                     previous["average_entry_price_or_null"])
    prior_average = (None if prior_average is None else Decimal(prior_average))
    prior_realized = Decimal("0" if previous is None else
                             previous["realized_pnl"])
    prior_fee = Decimal("0" if previous is None else
                        previous["cumulative_fee"])
    prior_wallet = Decimal(activation.capital_usdt if previous is None else
                           previous["wallet_balance"])
    prior_available = Decimal(
        activation.capital_usdt if previous is None else
        previous["available_balance"]
    )
    prior_fills = [] if previous is None else list(previous["fill_ids"])
    if attempt["action"] == "OPEN_LONG":
        signed = prior_signed + quantity
        average = None if signed == 0 else (
            prior_signed * (prior_average or Decimal("0")) + quote
        ) / signed
        realized = prior_realized
        wallet = prior_wallet - fee
        available = prior_available - quote - fee
    else:
        if prior_average is None or quantity > prior_signed:
            _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
        signed = prior_signed - quantity
        average = None if signed == 0 else prior_average
        realized_increment = quote - quantity * prior_average
        realized = prior_realized + realized_increment
        wallet = prior_wallet + realized_increment - fee
        available = prior_available + quote - fee
    facts = {
        "product": "SPOT", "signed_quantity": canonical_decimal(signed),
        "average_entry_price_or_null": (
            None if average is None else canonical_decimal(average)
        ), "realized_pnl": canonical_decimal(realized),
        "unrealized_pnl": "0",
        "cumulative_fee": canonical_decimal(prior_fee + fee), "funding": "0",
        "wallet_balance": canonical_decimal(wallet),
        "available_balance": canonical_decimal(available),
        "open_order_count": 0,
        "protective_stop_client_id_or_null": None,
        "fill_ids": sorted(set(prior_fills + [
            item["trade_id"] for item in fills
        ])),
    }
    return {**facts, "ledger_projection": dict(facts)}
def _append_fills_fees(state, attempt, recorded_at):
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    if private["stage"] == "BINANCE_FILLS_FEES_REPLAYED":
        return
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
    data = reconcile_binance_private_state(
        event_projection=_spot_facts(
            state, attempt, activation,
            previous_reconciliation_bytes_or_null=previous,
        ),
        order_documents=(order,), trade_documents=trades,
        account_document=account, position_document=b"[]",
        income_documents=(), algo_documents=(),
        previous_reconciliation_bytes_or_null=previous,
    )
    return _publish_reconciliation(
        state, attempt, data, False, None, recorded_at,
    )
def _expected_stop(state, attempt):
    try:
        evidence = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ]["result_evidence"]
        decision = evidence["decision"]
        snapshot = evidence["next_snapshot"]
        protection = snapshot["protective_stop_or_null"]
        if (evidence["$schema"]
                != "./challenger-replacement-public-simulation-result-v1.schema.json"
                or decision["action"] != "OPEN_PERP_SHORT"
                or snapshot["position_state"] != "PERPETUAL_SHORT"
                or Decimal(snapshot["signed_quantity"])
                != -Decimal(attempt["quantity"])
                or protection["status"] != "CONFIRMED_SIMULATED"):
            raise ValueError
        return prepare_binance_protective_stop(
            short_quantity=attempt["quantity"],
            trigger_price=protection["trigger"],
            intent_identity={
                "plan_hash": state.plan["plan_hash"],
                "block_id": attempt["block_id"],
                "intent_id": attempt["intent_id"],
            },
        )
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
    return build_binance_private_request(
        endpoint, parameters, timestamp_ms=timestamp_ms,
    )
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
    if observed.response_class != "QUERY_SUCCEEDED":
        _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    algo = _document(observed.body)
    algo_id = algo.get("algoId")
    if isinstance(algo_id, bool) or not isinstance(algo_id, int) or algo_id <= 0:
        _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    current = state.replay()["opportunities"][
        attempt["opportunity_id"]
    ]["private"]["stop"]
    if current["stage"] == "BINANCE_STOP_REQUEST_SEND_STARTED":
        _append(state, "BINANCE_STOP_ACKNOWLEDGED", attempt["opportunity_id"], {
            "protected_intent_id": attempt["intent_id"],
            "client_algo_id": stop["client_algo_id"], "algo_id": algo_id,
        }, context.recorded_at)
    reconciled = reconcile_binance_protective_stop(
        position=_stop_position(position), algo_order=observed.body,
        expected=stop,
    )
    _append(state, "BINANCE_STOP_RECONCILED", attempt["opportunity_id"],
            reconciled, context.recorded_at)
    return _status(
        "PROTECTION_VERIFIED_RECONCILIATION_PENDING", attempt,
        client_algo_id=stop["client_algo_id"],
    )
def _ensure_stop(state, attempt, position, context):
    stop = _expected_stop(state, attempt)
    _append(state, "BINANCE_STOP_INTENT_AUTHORIZED",
            attempt["opportunity_id"], stop, context.recorded_at)
    query = _execute(_stop_request(
        "FUTURES_ALGO_QUERY", stop, context.timestamp_ms,
    ), context)
    if not _proven_absent(query):
        _fail("BINANCE_PRIVATE_RUNTIME_STOP_ABSENCE_NOT_PROVEN")
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
        "request_sha256": hashlib.sha256(
            request.encoded_parameters
        ).hexdigest(), "timestamp_ms": context.timestamp_ms,
    }, context.recorded_at)
    _append(state, "BINANCE_STOP_REQUEST_SEND_STARTED",
            attempt["opportunity_id"], {
        "protected_intent_id": attempt["intent_id"],
        "client_algo_id": stop["client_algo_id"],
        "request_id": request.request_id,
    }, context.recorded_at)
    created = _execute(request, context)
    if created.response_class not in {"ACKNOWLEDGED", "UNKNOWN"}:
        _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    observed = _execute(_stop_request(
        "FUTURES_ALGO_QUERY", stop, context.timestamp_ms,
    ), context)
    return _complete_stop_observation(
        state, attempt, stop, position, observed, context,
    )
def _perpetual_facts(state, attempt, activation, position, incomes, stop,
                     previous_reconciliation_bytes_or_null=None):
    fills = [payload for event_type, payload in _private_payloads(
        state, attempt["opportunity_id"]
    ) if event_type == "BINANCE_FILL_OBSERVED"]
    try:
        positions = _document(position, list)
        if len(positions) != 1:
            raise ValueError
        position_value = positions[0]
        income_values = [_document(item) for item in incomes]
        quantity = sum(
            (Decimal(item["quantity"]) for item in fills), Decimal(0)
        )
        weighted = sum(
            (Decimal(item["quantity"]) * Decimal(item["price"])
             for item in fills), Decimal(0),
        )
        fee = sum((Decimal(item["fee"]) for item in fills), Decimal(0))
        current_realized = sum(
            (Decimal(item["realized_pnl"]) for item in fills), Decimal(0)
        )
        current_funding = sum(
            (Decimal(item["income"]) for item in income_values), Decimal(0)
        )
        previous = (None if previous_reconciliation_bytes_or_null is None else
                    load_binance_reconciliation_bytes(
                        previous_reconciliation_bytes_or_null
                    )["event_projection"])
        prior_signed = Decimal("0" if previous is None else
                               previous["signed_quantity"])
        prior_average = (None if previous is None else
                         previous["average_entry_price_or_null"])
        prior_average = (None if prior_average is None
                         else Decimal(prior_average))
        prior_realized = Decimal("0" if previous is None else
                                 previous["realized_pnl"])
        prior_fee = Decimal("0" if previous is None else
                            previous["cumulative_fee"])
        prior_funding = Decimal("0" if previous is None else
                                previous["funding"])
        prior_wallet = Decimal(
            activation.capital_usdt if previous is None else
            previous["wallet_balance"]
        )
        prior_fills = [] if previous is None else list(previous["fill_ids"])
        if attempt["action"] == "OPEN_SHORT":
            signed = prior_signed - quantity
            average = None if signed == 0 else (
                -prior_signed * (prior_average or Decimal("0")) + weighted
            ) / -signed
        else:
            if prior_average is None or quantity > -prior_signed:
                _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
            signed = prior_signed + quantity
            average = None if signed == 0 else prior_average
        if Decimal(position_value["positionAmt"]) != signed:
            _fail("VENUE_LOCAL_POSITION_MISMATCH")
        realized = prior_realized + current_realized
        funding = prior_funding + current_funding
        wallet = prior_wallet + current_realized - fee + current_funding
        available = wallet - Decimal(position_value["isolatedMargin"])
        client = None
        if signed < 0:
            if not isinstance(stop, Mapping):
                _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
            client = stop["client_algo_id"]
        facts = {
            "product": "PERPETUAL",
            "signed_quantity": canonical_decimal(signed),
            "average_entry_price_or_null": (
                None if average is None else canonical_decimal(average)
            ), "realized_pnl": canonical_decimal(realized),
            "unrealized_pnl": canonical_decimal(Decimal(
                position_value["unRealizedProfit"]
            )), "cumulative_fee": canonical_decimal(prior_fee + fee),
            "funding": canonical_decimal(funding),
            "wallet_balance": canonical_decimal(wallet),
            "available_balance": canonical_decimal(available),
            "open_order_count": 0,
            "protective_stop_client_id_or_null": client,
            "fill_ids": sorted(set(prior_fills + [
                item["trade_id"] for item in fills
            ])),
        }
        return {**facts, "ledger_projection": dict(facts)}
    except (KeyError, TypeError, ValueError) as error:
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID", error)
def _finish_perpetual(state, attempt, activation, stop, context,
                      previous_reconciliation_bytes_or_null=None):
    order_result = _query_order(attempt, context)
    order = _document(order_result.body)
    order_id = order.get("orderId")
    if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id <= 0:
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID")
    trades = _query(
        "FUTURES_TRADES", {"symbol": "ETHUSDT", "orderId": str(order_id)},
        context,
    )
    account = _query("FUTURES_ACCOUNT", {}, context)
    position = _query(
        "FUTURES_POSITION", {"symbol": "ETHUSDT"}, context,
    )
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
    algos = _query(
        "FUTURES_OPEN_ALGO_ORDERS", {"symbol": "ETHUSDT"}, context,
    )
    income_documents = _tuple_documents(income.body)
    algo_documents = _tuple_documents(algos.body)
    previous = (previous_reconciliation_bytes_or_null
                if previous_reconciliation_bytes_or_null is not None else
                _previous_reconciliation_bytes(
                    state, product="PERPETUAL",
                    before_opportunity_id=attempt["opportunity_id"],
                ))
    facts = _perpetual_facts(
        state, attempt, activation, position.body, income_documents, stop,
        previous_reconciliation_bytes_or_null=previous,
    )
    data = reconcile_binance_private_state(
        event_projection=facts, order_documents=(order_result.body,),
        trade_documents=_tuple_documents(trades.body),
        account_document=account.body, position_document=position.body,
        income_documents=income_documents, algo_documents=algo_documents,
        previous_reconciliation_bytes_or_null=previous,
    )
    client = facts["protective_stop_client_id_or_null"]
    required = client is not None
    return _publish_reconciliation(
        state, attempt, data, required, client, context.recorded_at,
    )
def _cleanup_query_observation(result, client):
    if _proven_absent(result):
        return False, None
    if result.response_class != "QUERY_SUCCEEDED":
        _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    try:
        document = _document(result.body)
        algo_id = document["algoId"]
        if (document["clientAlgoId"] != client
                or isinstance(algo_id, bool) or not isinstance(algo_id, int)
                or algo_id <= 0):
            raise ValueError
        if document["algoStatus"] == "NEW":
            return True, algo_id
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
    client = prior["protective_stop_client_id_or_null"]
    if (Decimal(prior["signed_quantity"]) >= 0 or not isinstance(client, str)):
        _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
    private = state.replay()["opportunities"][attempt["opportunity_id"]][
        "private"
    ]
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
    if cleanup["client_algo_id"] != client:
        _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
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
        if result.response_class not in {"ACKNOWLEDGED", "UNKNOWN"}:
            _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
        cleanup = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ]["private"]["stop_cleanup"]
    if cleanup["stage"] == "BINANCE_STOP_CLEANUP_SEND_STARTED":
        observed = _execute(_stop_request(
            "FUTURES_ALGO_QUERY", {"client_algo_id": client},
            context.timestamp_ms,
        ), context)
        active, algo_id = _cleanup_query_observation(observed, client)
        if active:
            _fail("BINANCE_FLAT_ORPHAN_STOP_ACTIVE")
        if algo_id is not None and algo_id != cleanup["algo_id"]:
            _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
        _append_intent(
            state, attempt, "BINANCE_STOP_CLEANUP_RECONCILED",
            context.recorded_at, client_algo_id=client,
            query_response_sha256=observed.response_sha256,
            status="BINANCE_FLAT_STOP_CLEANED",
        )
        cleanup = state.replay()["opportunities"][
            attempt["opportunity_id"]
        ]["private"]["stop_cleanup"]
    if cleanup["stage"] != "BINANCE_STOP_CLEANUP_RECONCILED":
        _fail("BINANCE_PRIVATE_RUNTIME_STOP_REPLAY_INVALID")
    return _finish_perpetual(
        state, attempt, context.activation, None, context,
        previous_reconciliation_bytes_or_null=previous,
    )
def _resume_stop(state, attempt, private, context):
    stop = _expected_stop(state, attempt)
    current = private.get("stop")
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
        return _finish_perpetual(
            state, attempt, context.activation, stop, context,
        )
    position = _query(
        "FUTURES_POSITION", {"symbol": "ETHUSDT"}, context,
    )
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
        if created.response_class not in {"ACKNOWLEDGED", "UNKNOWN"}:
            _fail("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    observed = _execute(_stop_request(
        "FUTURES_ALGO_QUERY", stop, context.timestamp_ms,
    ), context)
    return _complete_stop_observation(
        state, attempt, stop, position.body, observed, context,
    )
def _observe_order(*, state, attempt, order_result, context):
    order = _document(order_result.body)
    order_id = order.get("orderId")
    if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id <= 0:
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID")
    spot = attempt["product"] == "SPOT"
    trades_result = _query(
        "SPOT_TRADES" if spot else "FUTURES_TRADES",
        {"symbol": "ETHUSDT", "orderId": str(order_id)},
        context,
    )
    account_result = _query(
        "SPOT_ACCOUNT" if spot else "FUTURES_POSITION",
        {} if spot else {"symbol": "ETHUSDT"},
        context,
    )
    events = apply_binance_order_observation(
        attempt=attempt, order=order_result.body,
        trades=_tuple_documents(trades_result.body), account=account_result.body,
    )
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    replaying_terminal = private["stage"] in _TERMINAL_ORDERS | {
        "BINANCE_FILLS_FEES_REPLAYED",
    }
    for event in events:
        if (replaying_terminal
                or event["event_type"] == "BINANCE_ORDER_ACKNOWLEDGED"
                and private["stage"] != "BINANCE_REQUEST_SEND_STARTED"):
            continue
        if (event["event_type"] == "BINANCE_FILL_OBSERVED"
                and event["payload"]["trade_id"] in private["fill_ids"]):
            continue
        _append(
            state, event["event_type"], attempt["opportunity_id"],
            event["payload"], context.recorded_at,
        )
    terminal = events[-1]["event_type"] if events else None
    if terminal in _TERMINAL_ORDERS:
        if spot:
            return _finish_spot(
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
            if previous is None:
                _fail("BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID")
            return _cleanup_perpetual_stop(
                state, attempt, previous, context,
            )
        return _ensure_stop(
            state, attempt, account_result.body, context,
        )
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
def _query_order(attempt, context):
    return _query(
        attempt["required_first_endpoint"], {
            "symbol": "ETHUSDT",
            "origClientOrderId": attempt["venue_client_order_id"],
        }, context,
    )
def _send_request(state, attempt, request, context):
    result = _execute(request, context)
    if result.response_class == "UNKNOWN":
        return _record_unknown(state, attempt, result, context.recorded_at)
    if result.response_class != "ACKNOWLEDGED":
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_REQUIRED")
    return _observe_order(
        state=state, attempt=attempt,
        order_result=_query_order(attempt, context), context=context,
    )
def run_challenger_replacement_binance_private_intent(
    *, state, event_root, intent, preflight, activation, credential,
    build_identity
):
    """Run one query-first intent through the fixed private transport."""

    _require_identity(state, event_root, build_identity)
    _require_decision_intent(state, intent, activation)
    if not isinstance(preflight, BinanceAccountPreflightCapability):
        _fail("BINANCE_PRIVATE_RUNTIME_PREFLIGHT_AUTHORITY_INVALID")
    now = _wall_now()
    try:
        recorded_at = utc_datetime(now)
        timestamp_ms = int(now.timestamp() * 1000)
        preflight = preflight.load(
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
    context = _Context(
        credential, activation, build_identity, recorded_at, timestamp_ms
    )
    if existing is not None:
        if existing["stage"] == "BINANCE_RECONCILIATION_SUCCEEDED":
            loaded = _reconciliation(existing)
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
            if attempt["action"] == "CLOSE_SHORT":
                previous = _previous_reconciliation_bytes(
                    state, product="PERPETUAL",
                    before_opportunity_id=attempt["opportunity_id"],
                )
                if previous is None:
                    _fail(
                        "BINANCE_PRIVATE_RUNTIME_RECONCILIATION_REPLAY_INVALID"
                    )
                return _cleanup_perpetual_stop(
                    state, attempt, previous, context,
                )
            if isinstance(existing.get("stop"), dict):
                return _resume_stop(state, attempt, existing, context)
        if existing["stage"] == "BINANCE_REQUEST_SEND_STARTED":
            return _recover_after_send(
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
        if existing["stage"] == "BINANCE_ORDER_UNKNOWN":
            return _status("UNRESOLVED_ECONOMIC_ORDER_UNKNOWN", attempt)
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
    _append_intent(state, attempt, "BINANCE_INTENT_AUTHORIZED", recorded_at,
        opportunity_id=attempt["opportunity_id"],
        block_id=attempt["block_id"],
        product=attempt["product"], action=attempt["action"],
        quantity=attempt["quantity"],
        venue_client_order_id=attempt["venue_client_order_id"],
        activation_id=attempt["activation_id"],
        preflight_sha256=preflight_hash,
        unsigned_intent_sha256=attempt["unsigned_intent_sha256"],
    )
    query = _request(attempt["required_first_endpoint"], attempt, timestamp_ms)
    query_result = _execute(query, context)
    if not _proven_absent(query_result):
        _fail("BINANCE_PRIVATE_RUNTIME_ORDER_ABSENCE_NOT_PROVEN")
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
