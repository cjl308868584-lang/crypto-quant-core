"""Closed Binance endpoint and event contracts for replacement v3."""
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from importlib import resources
import ipaddress
import json
from types import MappingProxyType
from typing import Mapping
from jsonschema import Draft202012Validator
from .canonical import canonical_decimal, canonical_json, utc_datetime
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)
_SPOT, _FUTURES = "api.binance.com", "fapi.binance.com"
_ENDPOINT_ROWS = (
    ("SPOT_SERVER_TIME", _SPOT, "GET", "/api/v3/time", False),
    ("SPOT_EXCHANGE_INFO", _SPOT, "GET", "/api/v3/exchangeInfo", False),
    ("FUTURES_SERVER_TIME", _FUTURES, "GET", "/fapi/v1/time", False),
    ("FUTURES_EXCHANGE_INFO", _FUTURES, "GET", "/fapi/v1/exchangeInfo", False),
    ("FUTURES_MARK_PRICE", _FUTURES, "GET", "/fapi/v1/premiumIndex", False),
    ("API_RESTRICTIONS", _SPOT, "GET", "/sapi/v1/account/apiRestrictions", False),
    ("API_TRADING_STATUS", _SPOT, "GET", "/sapi/v1/account/apiTradingStatus", False),
    ("SPOT_ACCOUNT", _SPOT, "GET", "/api/v3/account", False),
    ("SPOT_OPEN_ORDERS", _SPOT, "GET", "/api/v3/openOrders", False),
    ("SPOT_ORDER_QUERY", _SPOT, "GET", "/api/v3/order", False),
    ("SPOT_TRADES", _SPOT, "GET", "/api/v3/myTrades", False),
    ("FUTURES_POSITION_MODE", _FUTURES, "GET", "/fapi/v1/positionSide/dual", False),
    ("FUTURES_MULTI_ASSET_MODE", _FUTURES, "GET", "/fapi/v1/multiAssetsMargin", False),
    ("FUTURES_SYMBOL_CONFIG", _FUTURES, "GET", "/fapi/v1/symbolConfig", False),
    ("FUTURES_ACCOUNT", _FUTURES, "GET", "/fapi/v3/account", False),
    ("FUTURES_POSITION", _FUTURES, "GET", "/fapi/v3/positionRisk", False),
    ("FUTURES_OPEN_ORDERS", _FUTURES, "GET", "/fapi/v1/openOrders", False),
    ("FUTURES_ORDER_QUERY", _FUTURES, "GET", "/fapi/v1/order", False),
    ("FUTURES_TRADES", _FUTURES, "GET", "/fapi/v1/userTrades", False),
    ("FUTURES_INCOME", _FUTURES, "GET", "/fapi/v1/income", False),
    ("FUTURES_ALGO_QUERY", _FUTURES, "GET", "/fapi/v1/algoOrder", False),
    ("FUTURES_OPEN_ALGO_ORDERS", _FUTURES, "GET", "/fapi/v1/openAlgoOrders", False),
    ("SPOT_ORDER_CREATE", _SPOT, "POST", "/api/v3/order", True),
    ("SPOT_ORDER_CANCEL", _SPOT, "DELETE", "/api/v3/order", True),
    ("FUTURES_ORDER_CREATE", _FUTURES, "POST", "/fapi/v1/order", True),
    ("FUTURES_ORDER_CANCEL", _FUTURES, "DELETE", "/fapi/v1/order", True),
    ("FUTURES_ALGO_CREATE", _FUTURES, "POST", "/fapi/v1/algoOrder", True),
    ("FUTURES_ALGO_CANCEL", _FUTURES, "DELETE", "/fapi/v1/algoOrder", True),
    ("FUTURES_SET_LEVERAGE", _FUTURES, "POST", "/fapi/v1/leverage", True),
    ("FUTURES_SET_MARGIN_TYPE", _FUTURES, "POST", "/fapi/v1/marginType", True),
)
BINANCE_PRIVATE_ENDPOINTS = MappingProxyType({
    key: tuple(values) for key, *values in _ENDPOINT_ROWS
})
@dataclass(frozen=True)
class BinanceAccountApproval:
    account_identity_sha256: str
    key_fingerprint: str
    reviewed_egress_ip: str
    reviewer_uid: int
    reviewed_at: str
    expires_at: str
    spot_trading_approved: bool
    futures_trading_approved: bool
@dataclass(frozen=True)
class BinancePrivateActivation:
    activation_id: str
    build_identity: Mapping[str, str]
    configuration_sha256: str
    account_approval_sha256: str
    block_id: str
    stage: str
    capital_usdt: str
    max_gross_exposure_usdt: str
    max_leverage: str
    expires_at: str
    production_activation: bool
    _authority_token: object = field(default=None, repr=False, compare=False)
_ACTIVATION_AUTHORITY_TOKEN = object()
def _is_loaded_binance_private_activation(value):
    return (isinstance(value, BinancePrivateActivation)
            and value._authority_token is _ACTIVATION_AUTHORITY_TOKEN)
class ChallengerReplacementBinancePrivateContractError(ValueError):
    """A Binance-private event violated the closed projection contract."""
    reason_code = "CHALLENGER_REPLACEMENT_BINANCE_PRIVATE_EVENT_INVALID"
    def __init__(self):
        super().__init__(self.reason_code)
_LOWER_HEX = frozenset("0123456789abcdef")
@lru_cache(maxsize=3)
def _validator(filename):
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", filename,
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)
PRIVATE_EVENT_TYPES = frozenset(
    _validator("challenger-replacement-binance-private-event-v1.schema.json")
    .schema["properties"]["event_type"]["enum"]
)
def _invalid(error=None):
    if error is None:
        raise ChallengerReplacementBinancePrivateContractError()
    raise ChallengerReplacementBinancePrivateContractError() from error
def _payload(header):
    try:
        data = base64.b64decode(header["payload_bytes_base64"], validate=True)
        value = _strict_json_bytes(data)
    except (
        ChallengerReplacementPlanError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        _invalid(error)
    if not isinstance(value, dict):
        _invalid()
    return value
def _lower_hash(value, length=64):
    return (
        isinstance(value, str)
        and len(value) == length
        and not set(value) - _LOWER_HEX
    )
def _bounded_identity(value):
    return isinstance(value, str) and 1 <= len(value) <= 256
def _canonical_time(value):
    if not isinstance(value, str):
        raise ValueError("CHALLENGER_REPLACEMENT_BINANCE_ACTIVATION_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            "CHALLENGER_REPLACEMENT_BINANCE_ACTIVATION_INVALID"
        ) from error
    parsed = parsed.astimezone(timezone.utc)
    if utc_datetime(parsed) != value:
        raise ValueError("CHALLENGER_REPLACEMENT_BINANCE_ACTIVATION_INVALID")
    return parsed
def load_binance_private_activation_bytes(data, *, build_identity, now):
    """Load one exact, time-bounded stage activation document."""
    reason = "CHALLENGER_REPLACEMENT_BINANCE_ACTIVATION_INVALID"
    try:
        if not isinstance(data, bytes) or not data.endswith(b"\n"):
            raise ValueError(reason)
        document = _strict_json_bytes(data[:-1])
        if (canonical_json(document) + "\n").encode("utf-8") != data:
            raise ValueError(reason)
        limits = {
            "E0": ("100", "50", "0.5"),
            "E1": ("300", "300", "1"),
            "E2": ("1000", "2000", "2"),
        }
        if (
            tuple(_validator(
                "challenger-replacement-binance-private-activation-v1.schema.json"
            ).iter_errors(document))
            or document["build_identity"] != build_identity
            or (
                document["capital_usdt"],
                document["max_gross_exposure_usdt"],
                document["max_leverage"],
            ) != limits[document["stage"]]
            or _canonical_time(document["expires_at"]) <= _canonical_time(now)
        ):
            raise ValueError(reason)
        return BinancePrivateActivation(
            activation_id=document["activation_id"],
            build_identity=MappingProxyType(dict(document["build_identity"])),
            configuration_sha256=document["configuration_sha256"],
            account_approval_sha256=document["account_approval_sha256"],
            block_id=document["block_id"],
            stage=document["stage"],
            capital_usdt=document["capital_usdt"],
            max_gross_exposure_usdt=document["max_gross_exposure_usdt"],
            max_leverage=document["max_leverage"],
            expires_at=document["expires_at"],
            production_activation=document["production_activation"],
            _authority_token=_ACTIVATION_AUTHORITY_TOKEN,
        )
    except (ChallengerReplacementPlanError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error) == reason:
            raise
        raise ValueError(reason) from error
def load_binance_account_approval_bytes(data, *, now):
    """Load the owner's bounded account/IP/key-fingerprint attestation."""
    reason = "CHALLENGER_REPLACEMENT_BINANCE_ACCOUNT_APPROVAL_INVALID"
    try:
        if not isinstance(data, bytes) or not data.endswith(b"\n"):
            raise ValueError(reason)
        document = _strict_json_bytes(data[:-1])
        if (canonical_json(document) + "\n").encode("utf-8") != data:
            raise ValueError(reason)
        if tuple(_validator(
            "challenger-replacement-binance-account-approval-v1.schema.json"
        ).iter_errors(document)):
            raise ValueError(reason)
        reviewed = _canonical_time(document["reviewed_at"])
        expires = _canonical_time(document["expires_at"])
        observed = _canonical_time(now)
        egress = ipaddress.ip_address(document["reviewed_egress_ip"])
        if (
            egress.version != 4
            or str(egress) != document["reviewed_egress_ip"]
            or not reviewed <= observed < expires
        ):
            raise ValueError(reason)
        return BinanceAccountApproval(
            account_identity_sha256=document["account_identity_sha256"],
            key_fingerprint=document["key_fingerprint"],
            reviewed_egress_ip=document["reviewed_egress_ip"],
            reviewer_uid=document["reviewer_uid"],
            reviewed_at=document["reviewed_at"],
            expires_at=document["expires_at"],
            spot_trading_approved=True,
            futures_trading_approved=True,
        )
    except (
        ChallengerReplacementPlanError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        if isinstance(error, ValueError) and str(error) == reason:
            raise
        raise ValueError(reason) from error
def apply_challenger_replacement_private_event(projection, event):
    """Apply one private event only after its opportunity is observed."""
    try:
        header = json.loads(event.final_bytes.decode("utf-8"))
        event_type = header["event_type"]
        opportunity_id = header["slot_id"]
        slot = projection["opportunities"][opportunity_id]
    except (AttributeError, KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
        raise ChallengerReplacementBinancePrivateContractError() from error
    if (event_type not in PRIVATE_EVENT_TYPES
            or slot.get("outcome") != "OBSERVED"):
        _invalid()
    payload = _payload(header)
    envelope = {
        "$schema": "./challenger-replacement-binance-private-event-v1.schema.json",
        "schema_version": "1.0.0", "event_type": event_type,
        "opportunity_id": opportunity_id, "payload": payload,
    }
    if tuple(_validator(
        "challenger-replacement-binance-private-event-v1.schema.json"
    ).iter_errors(envelope)):
        _invalid()
    if event_type != "BINANCE_INTENT_AUTHORIZED":
        private = slot.get("private")
        if (slot.get("stage") != "OPPORTUNITY_OBSERVED"
                or not isinstance(private, dict)
                or private.get("terminal") is not False):
            _invalid()
        if event_type == "BINANCE_SERVER_TIME_OBSERVED":
            before, after = payload["local_before_ms"], payload["local_after_ms"]
            midpoint = before + (after - before) // 2
            if (payload["intent_id"] != private["intent_id"]
                    or payload["product"] != private["product"]
                    or before > after or after - before > 1000
                    or payload["midpoint_ms"] != midpoint
                    or payload["skew_ms"] != payload["server_time_ms"] - midpoint):
                _invalid()
            private["server_time_evidence"] = {
                key: payload[key] for key in payload if key != "intent_id"
            }
            private["last_private_event_hash"] = event.event_hash
            private["last_private_event_sequence"] = event.sequence
            return
        if event_type.startswith("BINANCE_STOP_"):
            _apply_stop_transition(private, event_type, payload, event)
            return
        if payload.get("intent_id") != private.get("intent_id"):
            _invalid()
        _apply_private_transition(private, event_type, payload, event)
        return
    if slot.get("stage") != "OPPORTUNITY_OBSERVED":
        _invalid()
    try:
        quantity = canonical_decimal(payload["quantity"])
    except (KeyError, TypeError, ValueError) as error:
        _invalid(error)
    if (
        payload["opportunity_id"] != opportunity_id
        or quantity != payload["quantity"]
        or "private" in slot
    ):
        _invalid()
    slot["private"] = {
        "stage": event_type,
        "intent_id": payload["intent_id"],
        "block_id": payload["block_id"],
        "product": payload["product"],
        "action": payload["action"],
        "quantity": quantity,
        "venue_client_order_id": payload["venue_client_order_id"],
        "activation_id": payload["activation_id"],
        "preflight_sha256": payload["preflight_sha256"],
        "unsigned_intent_sha256": payload["unsigned_intent_sha256"],
        "intent_event_hash": event.event_hash,
        "intent_event_sequence": event.sequence,
        "last_private_event_hash": event.event_hash,
        "last_private_event_sequence": event.sequence,
        "fill_ids": [],
        "unresolved_unknown": False,
        "terminal": False,
    }
_PRIVATE_TRANSITIONS = {
    "BINANCE_ABSENCE_CHECKED": {"BINANCE_INTENT_AUTHORIZED"},
    "BINANCE_SIGNED_REQUEST_PREPARED": {"BINANCE_ABSENCE_CHECKED"},
    "BINANCE_REQUEST_SEND_STARTED": {"BINANCE_SIGNED_REQUEST_PREPARED"},
    "BINANCE_ORDER_ACKNOWLEDGED": {"BINANCE_REQUEST_SEND_STARTED"},
    "BINANCE_FILL_OBSERVED": {
        "BINANCE_ORDER_ACKNOWLEDGED", "BINANCE_FILL_OBSERVED",
        "BINANCE_ORDER_PARTIALLY_FILLED",
    },
    "BINANCE_ORDER_PARTIALLY_FILLED": {
        "BINANCE_ORDER_ACKNOWLEDGED", "BINANCE_FILL_OBSERVED",
    },
    "BINANCE_ORDER_FILLED": {
        "BINANCE_ORDER_ACKNOWLEDGED", "BINANCE_FILL_OBSERVED",
        "BINANCE_ORDER_PARTIALLY_FILLED",
    },
    "BINANCE_ORDER_CANCELED": {
        "BINANCE_ORDER_ACKNOWLEDGED", "BINANCE_FILL_OBSERVED",
        "BINANCE_ORDER_PARTIALLY_FILLED",
    },
    "BINANCE_ORDER_EXPIRED": {
        "BINANCE_ORDER_ACKNOWLEDGED", "BINANCE_FILL_OBSERVED",
        "BINANCE_ORDER_PARTIALLY_FILLED",
    },
    "BINANCE_ORDER_REJECTED": {"BINANCE_REQUEST_SEND_STARTED"},
    "BINANCE_ORDER_UNKNOWN": {
        "BINANCE_REQUEST_SEND_STARTED", "BINANCE_ORDER_ACKNOWLEDGED",
        "BINANCE_FILL_OBSERVED", "BINANCE_ORDER_PARTIALLY_FILLED",
    },
    "BINANCE_FILLS_FEES_REPLAYED": {
        "BINANCE_ORDER_FILLED", "BINANCE_ORDER_CANCELED",
        "BINANCE_ORDER_EXPIRED", "BINANCE_ORDER_REJECTED",
    },
    "BINANCE_POSITION_BALANCE_RECONCILED": {
        "BINANCE_FILLS_FEES_REPLAYED",
    },
    "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED": {
        "BINANCE_POSITION_BALANCE_RECONCILED",
    },
    "BINANCE_RECONCILIATION_SUCCEEDED": {
        "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED",
    },
    "BINANCE_RECONCILIATION_FAILED": {
        "BINANCE_POSITION_BALANCE_RECONCILED",
        "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED",
    },
}
def _stop_target(stop, stage):
    if isinstance(stop, dict) and stop.get("stage") == stage:
        return stop
    replacement = stop.get("replacement") if isinstance(stop, dict) else None
    candidate = (replacement.get("candidate")
                 if isinstance(replacement, dict) else None)
    if isinstance(candidate, dict) and candidate.get("stage") == stage:
        return candidate
    return None
_STOP_CHAIN = {
    "BINANCE_STOP_ABSENCE_CHECKED": (
        "BINANCE_STOP_INTENT_AUTHORIZED", ("query_response_sha256",),
    ),
    "BINANCE_STOP_SIGNED_REQUEST_PREPARED": (
        "BINANCE_STOP_ABSENCE_CHECKED",
        ("request_id", "request_sha256", "timestamp_ms"),
    ),
    "BINANCE_STOP_REQUEST_SEND_STARTED": (
        "BINANCE_STOP_SIGNED_REQUEST_PREPARED", (),
    ),
    "BINANCE_STOP_ACKNOWLEDGED": (
        "BINANCE_STOP_REQUEST_SEND_STARTED", ("algo_id",),
    ),
    "BINANCE_STOP_RECONCILED": ("BINANCE_STOP_ACKNOWLEDGED", ()),
}
def _advance_stop(stop, private, event_type, payload):
    previous, copied = _STOP_CHAIN[event_type]
    target = _stop_target(stop, previous)
    valid = (target is not None
             and payload.get("client_algo_id") == target.get("client_algo_id")
             and (event_type == "BINANCE_STOP_RECONCILED"
                  or payload.get("protected_intent_id") == private["intent_id"]))
    if event_type == "BINANCE_STOP_REQUEST_SEND_STARTED":
        valid = valid and payload.get("request_id") == target.get("request_id")
    elif event_type == "BINANCE_STOP_RECONCILED":
        valid = valid and all((
            payload.get("status") == "BINANCE_PROTECTIVE_STOP_VERIFIED",
            payload.get("exposed") is True,
            payload.get("algo_id") == target.get("algo_id"),
            payload.get("quantity") == target.get("quantity"),
            payload.get("trigger_price") == target.get("trigger_price"),
        ))
    if not valid:
        _invalid()
    updates = {name: payload[name] for name in copied}
    if "timestamp_ms" in updates:
        updates["request_timestamp_ms"] = updates.pop("timestamp_ms")
    target.update(stage=event_type, **updates)
def _apply_stop_transition(private, event_type, payload, event):
    stop = private.get("stop")
    if event_type.startswith("BINANCE_STOP_CLEANUP_"):
        cleanup = private.get("stop_cleanup")
        if event_type == "BINANCE_STOP_CLEANUP_AUTHORIZED":
            if (cleanup is not None or private["product"] != "PERPETUAL"
                    or private["action"] != "CLOSE_SHORT"
                    or private["stage"] != "BINANCE_FILLS_FEES_REPLAYED"
                    or payload["intent_id"] != private["intent_id"]):
                _invalid()
            private["stop_cleanup"] = {
                "stage": event_type,
                "client_algo_id": payload["client_algo_id"],
                "prior_reconciliation_id": payload["prior_reconciliation_id"],
            }
        elif (not isinstance(cleanup, dict)
              or payload["intent_id"] != private["intent_id"]
              or payload["client_algo_id"] != cleanup["client_algo_id"]):
            _invalid()
        elif event_type == "BINANCE_STOP_CLEANUP_REQUEST_PREPARED":
            if cleanup["stage"] != "BINANCE_STOP_CLEANUP_AUTHORIZED":
                _invalid()
            cleanup.update(
                stage=event_type, request_id=payload["request_id"],
                request_sha256=payload["request_sha256"],
                request_timestamp_ms=payload["timestamp_ms"],
                query_response_sha256=payload["query_response_sha256"],
                algo_id=payload["algo_id"],
            )
        elif event_type == "BINANCE_STOP_CLEANUP_SEND_STARTED":
            if (cleanup["stage"] != "BINANCE_STOP_CLEANUP_REQUEST_PREPARED"
                    or payload["request_id"] != cleanup["request_id"]):
                _invalid()
            cleanup["stage"] = event_type
        elif event_type == "BINANCE_STOP_CLEANUP_RECONCILED":
            if cleanup["stage"] not in {
                    "BINANCE_STOP_CLEANUP_AUTHORIZED",
                    "BINANCE_STOP_CLEANUP_SEND_STARTED",
                }:
                _invalid()
            cleanup.update(
                stage=event_type,
                query_response_sha256=payload["query_response_sha256"],
                status=payload["status"],
            )
        else:
            _invalid()
    elif event_type == "BINANCE_STOP_INTENT_AUTHORIZED":
        try:
            quantity = canonical_decimal(payload["quantity"])
            trigger = canonical_decimal(payload["trigger_price"])
        except (KeyError, TypeError, ValueError) as error:
            _invalid(error)
        replacement = stop.get("replacement") if isinstance(stop, dict) else None
        replacing = (
            isinstance(replacement, dict)
            and replacement.get("stage") == "BINANCE_STOP_REPLACEMENT_STARTED"
            and "candidate" not in replacement
            and payload.get("client_algo_id") == replacement.get(
                "new_client_algo_id"
            )
        )
        if ((stop is not None and not replacing)
                or private["product"] != "PERPETUAL"
                or private["stage"] != "BINANCE_FILLS_FEES_REPLAYED"
                or payload["protected_intent_id"] != private["intent_id"]
                or quantity != payload["quantity"]
                or trigger != payload["trigger_price"]):
            _invalid()
        candidate = {
            "stage": event_type, "client_algo_id": payload["client_algo_id"],
            "quantity": quantity, "trigger_price": trigger,
        }
        if replacing:
            replacement["candidate"] = candidate
        else:
            private["stop"] = candidate
    elif event_type in _STOP_CHAIN:
        _advance_stop(stop, private, event_type, payload)
    elif event_type == "BINANCE_STOP_REPLACEMENT_STARTED":
        if (not isinstance(stop, dict)
                or stop["stage"] != "BINANCE_STOP_RECONCILED"
                or "replacement" in stop
                or payload["protected_intent_id"] != private["intent_id"]
                or payload["old_client_algo_id"] != stop["client_algo_id"]
                or payload["new_client_algo_id"] == stop["client_algo_id"]):
            _invalid()
        stop["replacement"] = {
            "stage": event_type,
            "old_client_algo_id": payload["old_client_algo_id"],
            "new_client_algo_id": payload["new_client_algo_id"],
        }
    elif event_type == "BINANCE_STOP_REPLACEMENT_SUCCEEDED":
        replacement = stop.get("replacement") if isinstance(stop, dict) else None
        candidate = (replacement.get("candidate")
                     if isinstance(replacement, dict) else None)
        if (not isinstance(candidate, dict)
                or candidate.get("stage") != "BINANCE_STOP_RECONCILED"
                or payload["protected_intent_id"] != private["intent_id"]
                or payload["old_client_algo_id"] != stop["client_algo_id"]
                or payload["old_client_algo_id"] != replacement.get(
                    "old_client_algo_id"
                )
                or payload["new_client_algo_id"] != candidate["client_algo_id"]
                or payload["new_client_algo_id"] != replacement.get(
                    "new_client_algo_id"
                )
                or payload["reason_code_or_null"] is not None):
            _invalid()
        replacement.pop("candidate")
        replacement["stage"] = event_type
        candidate["replacement"] = replacement
        private["stop"] = candidate
    elif event_type == "BINANCE_STOP_REPLACEMENT_FAILED":
        replacement = stop.get("replacement") if isinstance(stop, dict) else None
        reason = payload.get("reason_code_or_null")
        if (not isinstance(replacement, dict)
                or replacement.get("stage")
                != "BINANCE_STOP_REPLACEMENT_STARTED"
                or payload["protected_intent_id"] != private["intent_id"]
                or payload["old_client_algo_id"] != stop["client_algo_id"]
                or payload["old_client_algo_id"] != replacement.get(
                    "old_client_algo_id"
                )
                or payload["new_client_algo_id"] != replacement.get(
                    "new_client_algo_id"
                )
                or not isinstance(reason, str)):
            _invalid()
        stop["replacement"] = {
            "stage": event_type,
            "old_client_algo_id": payload["old_client_algo_id"],
            "new_client_algo_id": payload["new_client_algo_id"],
            "reason_code": reason,
        }
    else:
        _invalid()
    private["last_private_event_hash"] = event.event_hash
    private["last_private_event_sequence"] = event.sequence
def _private_payload_valid(event_type, payload, private):
    if event_type == "BINANCE_ABSENCE_CHECKED":
        return payload["venue_client_order_id"] == private["venue_client_order_id"]
    if event_type in {"BINANCE_SIGNED_REQUEST_PREPARED",
                      "BINANCE_REQUEST_SEND_STARTED"}:
        return True
    if event_type == "BINANCE_ORDER_ACKNOWLEDGED":
        return payload["venue_client_order_id"] == private["venue_client_order_id"]
    if event_type == "BINANCE_FILL_OBSERVED":
        return (("realized_pnl" in payload)
                is (private["product"] == "PERPETUAL"))
    if event_type.startswith("BINANCE_ORDER_") and event_type not in {
        "BINANCE_ORDER_REJECTED", "BINANCE_ORDER_UNKNOWN",
    }:
        return True
    if event_type in {"BINANCE_ORDER_REJECTED", "BINANCE_ORDER_UNKNOWN"}:
        return ("venue_code" in payload and payload["blocks_new_risk"]
                is (event_type == "BINANCE_ORDER_UNKNOWN"))
    if event_type == "BINANCE_FILLS_FEES_REPLAYED":
        return payload["fill_ids"] == private["fill_ids"]
    if event_type == "BINANCE_POSITION_BALANCE_RECONCILED":
        try:
            data = base64.b64decode(
                payload["reconciliation_bytes_base64"], validate=True,
            )
            from .challenger_replacement_binance_reconciliation import (
                load_binance_reconciliation_bytes,
            )
            loaded = load_binance_reconciliation_bytes(data)
            return (
                hashlib.sha256(data).hexdigest()
                == payload["reconciliation_sha256"]
                and loaded["reconciliation_id"]
                == payload["reconciliation_id"]
            )
        except (TypeError, ValueError):
            return False
    if event_type == "BINANCE_RECONCILIATION_SUCCEEDED":
        return payload["reconciliation_id"] == private.get("reconciliation_id")
    if event_type == "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED":
        return True
    return event_type == "BINANCE_RECONCILIATION_FAILED"
def _apply_private_transition(private, event_type, payload, event):
    if (event_type not in _PRIVATE_TRANSITIONS
            or private["stage"] not in _PRIVATE_TRANSITIONS[event_type]
            or not _private_payload_valid(event_type, payload, private)):
        _invalid()
    if event_type == "BINANCE_FILL_OBSERVED":
        if payload["trade_id"] in private["fill_ids"]:
            _invalid()
        private["fill_ids"].append(payload["trade_id"])
    elif event_type == "BINANCE_ABSENCE_CHECKED":
        private["absence_proven"] = True
    elif event_type == "BINANCE_SIGNED_REQUEST_PREPARED":
        private["request_id"] = payload["request_id"]
        private["request_endpoint_id"] = payload["endpoint_id"]
        private["request_sha256"] = payload["request_sha256"]
        private["request_timestamp_ms"] = payload["timestamp_ms"]
    elif event_type == "BINANCE_POSITION_BALANCE_RECONCILED":
        private["reconciliation_id"] = payload["reconciliation_id"]
        private["reconciliation_bytes_base64"] = payload[
            "reconciliation_bytes_base64"
        ]
        private["reconciliation_sha256"] = payload["reconciliation_sha256"]
    private["stage"] = event_type
    private["last_private_event_hash"] = event.event_hash
    private["last_private_event_sequence"] = event.sequence
    if event_type == "BINANCE_ORDER_UNKNOWN":
        private["unresolved_unknown"] = True
        private["terminal"] = True
    elif event_type in {
        "BINANCE_RECONCILIATION_SUCCEEDED", "BINANCE_RECONCILIATION_FAILED",
    }:
        private["terminal"] = True
def require_binance_private_endpoint(endpoint_id):
    """Return one frozen endpoint tuple or fail before request construction."""
    try:
        return BINANCE_PRIVATE_ENDPOINTS[endpoint_id]
    except (KeyError, TypeError) as error:
        raise ValueError("BINANCE_ENDPOINT_FORBIDDEN") from error
