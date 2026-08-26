"""Append-only orchestration for the fixed Binance private boundary."""
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
import json
from typing import Mapping
from .canonical import canonical_json, utc_datetime
from .challenger_replacement_binance_private_lifecycle import (
    _document, apply_binance_order_observation, prepare_binance_order_attempt,
)
from .challenger_replacement_binance_private_protocol import (
    build_binance_private_request,
)
from .challenger_replacement_binance_private_transport import (
    execute_binance_private_request,
)
from .challenger_replacement_events import ChallengerReplacementEventRoot
from .challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
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
def _status(status, attempt, **extra):
    return {
        "status": status, "opportunity_id": attempt["opportunity_id"],
        "intent_id": attempt["intent_id"],
        "venue_client_order_id": attempt["venue_client_order_id"], **extra,
    }
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
def _observe_order(*, state, attempt, order_result, context):
    order = _document(order_result.body)
    order_id = order.get("orderId")
    if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id <= 0:
        _fail("BINANCE_PRIVATE_RUNTIME_OBSERVATION_INVALID")
    spot = attempt["product"] == "SPOT"
    trades = _query(
        "SPOT_TRADES" if spot else "FUTURES_TRADES",
        {"symbol": "ETHUSDT", "orderId": str(order_id)},
        context,
    )
    account = _query(
        "SPOT_ACCOUNT" if spot else "FUTURES_POSITION",
        {} if spot else {"symbol": "ETHUSDT"},
        context,
    )
    events = apply_binance_order_observation(
        attempt=attempt, order=order_result.body,
        trades=_tuple_documents(trades.body), account=account.body,
    )
    private = state.replay()["opportunities"][attempt["opportunity_id"]]["private"]
    for event in events:
        if (event["event_type"] == "BINANCE_ORDER_ACKNOWLEDGED"
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
    _append(state, "BINANCE_ORDER_UNKNOWN", attempt["opportunity_id"], {
        "intent_id": attempt["intent_id"], "venue_code": venue_code,
        "blocks_new_risk": True,
    }, recorded_at)
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
    now = _wall_now()
    try:
        recorded_at = utc_datetime(now)
        timestamp_ms = int(now.timestamp() * 1000)
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
            _append(
                state, "BINANCE_REQUEST_SEND_STARTED",
                attempt["opportunity_id"], {
                    "intent_id": attempt["intent_id"],
                    "request_id": request.request_id,
                }, recorded_at,
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
    _append(state, "BINANCE_INTENT_AUTHORIZED", attempt["opportunity_id"], {
        "opportunity_id": attempt["opportunity_id"],
        "intent_id": attempt["intent_id"], "block_id": attempt["block_id"],
        "product": attempt["product"], "action": attempt["action"],
        "quantity": attempt["quantity"],
        "venue_client_order_id": attempt["venue_client_order_id"],
        "activation_id": attempt["activation_id"],
        "preflight_sha256": preflight_hash,
        "unsigned_intent_sha256": attempt["unsigned_intent_sha256"],
    }, recorded_at)
    query = _request(attempt["required_first_endpoint"], attempt, timestamp_ms)
    query_result = _execute(query, context)
    if not _proven_absent(query_result):
        _fail("BINANCE_PRIVATE_RUNTIME_ORDER_ABSENCE_NOT_PROVEN")
    _append(state, "BINANCE_ABSENCE_CHECKED", attempt["opportunity_id"], {
        "intent_id": attempt["intent_id"],
        "venue_client_order_id": attempt["venue_client_order_id"],
        "query_response_sha256": query_result.response_sha256,
        "proven_absent": True,
    }, recorded_at)
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
    _append(state, "BINANCE_SIGNED_REQUEST_PREPARED", attempt["opportunity_id"], {
        "intent_id": attempt["intent_id"], "request_id": request.request_id,
        "endpoint_id": request.endpoint_id,
        "request_sha256": hashlib.sha256(
            request.encoded_parameters
        ).hexdigest(),
        "timestamp_ms": timestamp_ms,
    }, recorded_at)
    _append(state, "BINANCE_REQUEST_SEND_STARTED", attempt["opportunity_id"], {
        "intent_id": attempt["intent_id"], "request_id": request.request_id,
    }, recorded_at)
    return _send_request(state, attempt, request, context)
