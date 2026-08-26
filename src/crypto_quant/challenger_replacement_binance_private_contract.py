"""Closed Binance endpoint and event contracts for replacement v3."""

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import json
from types import MappingProxyType
from typing import Mapping

from .canonical import canonical_decimal, canonical_json, utc_datetime
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)


BINANCE_PRIVATE_ENDPOINTS = MappingProxyType({
    "SPOT_SERVER_TIME": ("api.binance.com", "GET", "/api/v3/time", False),
    "SPOT_EXCHANGE_INFO": (
        "api.binance.com", "GET", "/api/v3/exchangeInfo", False,
    ),
    "FUTURES_SERVER_TIME": (
        "fapi.binance.com", "GET", "/fapi/v1/time", False,
    ),
    "FUTURES_EXCHANGE_INFO": (
        "fapi.binance.com", "GET", "/fapi/v1/exchangeInfo", False,
    ),
    "FUTURES_MARK_PRICE": (
        "fapi.binance.com", "GET", "/fapi/v1/premiumIndex", False,
    ),
    "API_RESTRICTIONS": (
        "api.binance.com", "GET", "/sapi/v1/account/apiRestrictions", False,
    ),
    "API_TRADING_STATUS": (
        "api.binance.com", "GET", "/sapi/v1/account/apiTradingStatus", False,
    ),
    "SPOT_ACCOUNT": ("api.binance.com", "GET", "/api/v3/account", False),
    "SPOT_OPEN_ORDERS": (
        "api.binance.com", "GET", "/api/v3/openOrders", False,
    ),
    "SPOT_ORDER_QUERY": (
        "api.binance.com", "GET", "/api/v3/order", False,
    ),
    "SPOT_TRADES": ("api.binance.com", "GET", "/api/v3/myTrades", False),
    "FUTURES_POSITION_MODE": (
        "fapi.binance.com", "GET", "/fapi/v1/positionSide/dual", False,
    ),
    "FUTURES_MULTI_ASSET_MODE": (
        "fapi.binance.com", "GET", "/fapi/v1/multiAssetsMargin", False,
    ),
    "FUTURES_SYMBOL_CONFIG": (
        "fapi.binance.com", "GET", "/fapi/v1/symbolConfig", False,
    ),
    "FUTURES_ACCOUNT": (
        "fapi.binance.com", "GET", "/fapi/v3/account", False,
    ),
    "FUTURES_POSITION": (
        "fapi.binance.com", "GET", "/fapi/v3/positionRisk", False,
    ),
    "FUTURES_OPEN_ORDERS": (
        "fapi.binance.com", "GET", "/fapi/v1/openOrders", False,
    ),
    "FUTURES_ORDER_QUERY": (
        "fapi.binance.com", "GET", "/fapi/v1/order", False,
    ),
    "FUTURES_TRADES": (
        "fapi.binance.com", "GET", "/fapi/v1/userTrades", False,
    ),
    "FUTURES_INCOME": (
        "fapi.binance.com", "GET", "/fapi/v1/income", False,
    ),
    "FUTURES_ALGO_QUERY": (
        "fapi.binance.com", "GET", "/fapi/v1/algoOrder", False,
    ),
    "FUTURES_OPEN_ALGO_ORDERS": (
        "fapi.binance.com", "GET", "/fapi/v1/openAlgoOrders", False,
    ),
    "SPOT_ORDER_CREATE": (
        "api.binance.com", "POST", "/api/v3/order", True,
    ),
    "SPOT_ORDER_CANCEL": (
        "api.binance.com", "DELETE", "/api/v3/order", True,
    ),
    "FUTURES_ORDER_CREATE": (
        "fapi.binance.com", "POST", "/fapi/v1/order", True,
    ),
    "FUTURES_ORDER_CANCEL": (
        "fapi.binance.com", "DELETE", "/fapi/v1/order", True,
    ),
    "FUTURES_ALGO_CREATE": (
        "fapi.binance.com", "POST", "/fapi/v1/algoOrder", True,
    ),
    "FUTURES_ALGO_CANCEL": (
        "fapi.binance.com", "DELETE", "/fapi/v1/algoOrder", True,
    ),
    "FUTURES_SET_LEVERAGE": (
        "fapi.binance.com", "POST", "/fapi/v1/leverage", True,
    ),
    "FUTURES_SET_MARGIN_TYPE": (
        "fapi.binance.com", "POST", "/fapi/v1/marginType", True,
    ),
})

PRIVATE_EVENT_TYPES = frozenset({
    "BINANCE_INTENT_AUTHORIZED",
    "BINANCE_ABSENCE_CHECKED",
    "BINANCE_SIGNED_REQUEST_PREPARED",
    "BINANCE_REQUEST_SEND_STARTED",
    "BINANCE_ORDER_ACKNOWLEDGED",
    "BINANCE_ORDER_REJECTED",
    "BINANCE_ORDER_UNKNOWN",
    "BINANCE_ORDER_PARTIALLY_FILLED",
    "BINANCE_ORDER_FILLED",
    "BINANCE_ORDER_CANCELED",
    "BINANCE_ORDER_EXPIRED",
    "BINANCE_FILL_OBSERVED",
    "BINANCE_FILLS_FEES_REPLAYED",
    "BINANCE_POSITION_BALANCE_RECONCILED",
    "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED",
    "BINANCE_RECONCILIATION_SUCCEEDED",
    "BINANCE_RECONCILIATION_FAILED",
    "BINANCE_STOP_INTENT_AUTHORIZED",
    "BINANCE_STOP_ACKNOWLEDGED",
    "BINANCE_STOP_RECONCILED",
    "BINANCE_STOP_REPLACEMENT_STARTED",
    "BINANCE_STOP_REPLACEMENT_SUCCEEDED",
    "BINANCE_STOP_REPLACEMENT_FAILED",
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


class ChallengerReplacementBinancePrivateContractError(ValueError):
    """A Binance-private event violated the closed projection contract."""

    reason_code = "CHALLENGER_REPLACEMENT_BINANCE_PRIVATE_EVENT_INVALID"

    def __init__(self):
        super().__init__(self.reason_code)


_LOWER_HEX = frozenset("0123456789abcdef")


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
        keys = {
            "$schema", "schema_version", "activation_id", "build_identity",
            "configuration_sha256", "account_approval_sha256", "block_id",
            "stage", "capital_usdt", "max_gross_exposure_usdt",
            "max_leverage", "expires_at", "production_activation",
        }
        limits = {
            "E0": ("100", "50", "0.5"),
            "E1": ("300", "300", "1"),
            "E2": ("1000", "2000", "2"),
        }
        if (
            not isinstance(document, dict)
            or set(document) != keys
            or document["$schema"]
            != "./challenger-replacement-binance-private-activation-v1.schema.json"
            or document["schema_version"] != "1.0.0"
            or document["build_identity"] != build_identity
            or document["stage"] not in limits
            or (
                document["capital_usdt"],
                document["max_gross_exposure_usdt"],
                document["max_leverage"],
            ) != limits[document["stage"]]
            or not _bounded_identity(document["activation_id"])
            or not _bounded_identity(document["block_id"])
            or not _lower_hash(document["configuration_sha256"])
            or not _lower_hash(document["account_approval_sha256"])
            or not isinstance(document["production_activation"], bool)
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
        keys = {
            "$schema", "schema_version", "account_identity_sha256",
            "key_fingerprint", "reviewed_egress_ip", "reviewer_uid",
            "reviewed_at", "expires_at", "spot_trading_approved",
            "futures_trading_approved",
        }
        reviewed = _canonical_time(document["reviewed_at"])
        expires = _canonical_time(document["expires_at"])
        observed = _canonical_time(now)
        egress = ipaddress.ip_address(document["reviewed_egress_ip"])
        if (
            not isinstance(document, dict)
            or set(document) != keys
            or document["$schema"]
            != "./challenger-replacement-binance-account-approval-v1.schema.json"
            or document["schema_version"] != "1.0.0"
            or not _lower_hash(document["account_identity_sha256"])
            or not _lower_hash(document["key_fingerprint"])
            or egress.version != 4
            or str(egress) != document["reviewed_egress_ip"]
            or isinstance(document["reviewer_uid"], bool)
            or not isinstance(document["reviewer_uid"], int)
            or document["reviewer_uid"] < 0
            or not reviewed <= observed < expires
            or document["spot_trading_approved"] is not True
            or document["futures_trading_approved"] is not True
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
    if event_type != "BINANCE_INTENT_AUTHORIZED":
        private = slot.get("private")
        if (slot.get("stage") != "OPPORTUNITY_OBSERVED"
                or not isinstance(private, dict)
                or private.get("terminal") is not False
                or payload.get("intent_id") != private.get("intent_id")):
            _invalid()
        _apply_private_transition(private, event_type, payload, event)
        return
    if slot.get("stage") != "OPPORTUNITY_OBSERVED":
        _invalid()
    expected_keys = {
        "opportunity_id",
        "intent_id",
        "block_id",
        "product",
        "action",
        "quantity",
        "venue_client_order_id",
        "activation_id",
        "preflight_sha256",
        "unsigned_intent_sha256",
    }
    product_actions = {
        "SPOT": {"OPEN_LONG", "CLOSE_LONG"},
        "PERPETUAL": {"OPEN_SHORT", "CLOSE_SHORT"},
    }
    try:
        quantity = canonical_decimal(payload["quantity"])
    except (KeyError, TypeError, ValueError) as error:
        _invalid(error)
    if (
        set(payload) != expected_keys
        or payload.get("opportunity_id") != opportunity_id
        or not _bounded_identity(payload.get("intent_id"))
        or not _bounded_identity(payload.get("block_id"))
        or not _bounded_identity(payload.get("activation_id"))
        or payload.get("product") not in product_actions
        or payload.get("action") not in product_actions[payload["product"]]
        or quantity != payload.get("quantity")
        or quantity == "0"
        or quantity.startswith("-")
        or not _lower_hash(payload.get("preflight_sha256"))
        or not _lower_hash(payload.get("unsigned_intent_sha256"))
        or not (
            isinstance(payload.get("venue_client_order_id"), str)
            and payload["venue_client_order_id"].startswith("cq77")
            and _lower_hash(payload["venue_client_order_id"][4:], length=32)
        )
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


def _private_payload_valid(event_type, payload, private):
    common = {"intent_id"}
    keys = {
        "BINANCE_ABSENCE_CHECKED": common | {
            "venue_client_order_id", "query_response_sha256", "proven_absent",
        },
        "BINANCE_SIGNED_REQUEST_PREPARED": common | {
            "request_id", "endpoint_id", "request_sha256", "timestamp_ms",
        },
        "BINANCE_REQUEST_SEND_STARTED": common | {"request_id"},
        "BINANCE_ORDER_ACKNOWLEDGED": common | {
            "order_id", "venue_client_order_id",
        },
        "BINANCE_FILL_OBSERVED": common | {
            "trade_id", "order_id", "quantity", "price", "quote_quantity",
            "fee", "fee_asset", "cumulative_filled_quantity",
        },
        "BINANCE_ORDER_PARTIALLY_FILLED": common | {
            "cumulative_filled_quantity", "cumulative_fee",
            "venue_terminal_status",
        },
        "BINANCE_ORDER_FILLED": common | {
            "cumulative_filled_quantity", "cumulative_fee",
            "venue_terminal_status",
        },
        "BINANCE_ORDER_CANCELED": common | {
            "cumulative_filled_quantity", "cumulative_fee",
            "venue_terminal_status",
        },
        "BINANCE_ORDER_EXPIRED": common | {
            "cumulative_filled_quantity", "cumulative_fee",
            "venue_terminal_status",
        },
        "BINANCE_ORDER_REJECTED": common | {"venue_code", "blocks_new_risk"},
        "BINANCE_ORDER_UNKNOWN": common | {"venue_code", "blocks_new_risk"},
        "BINANCE_FILLS_FEES_REPLAYED": common | {
            "fill_ids", "cumulative_fee",
        },
        "BINANCE_POSITION_BALANCE_RECONCILED": common | {"reconciliation_id"},
        "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED": common | {
            "required", "client_algo_id_or_null", "status",
        },
        "BINANCE_RECONCILIATION_SUCCEEDED": common | {"reconciliation_id"},
        "BINANCE_RECONCILIATION_FAILED": common | {"reason_code"},
    }
    if event_type not in keys or set(payload) != keys[event_type]:
        return False
    if event_type == "BINANCE_ABSENCE_CHECKED":
        return (payload["venue_client_order_id"]
                == private["venue_client_order_id"]
                and _lower_hash(payload["query_response_sha256"])
                and payload["proven_absent"] is True)
    if event_type == "BINANCE_SIGNED_REQUEST_PREPARED":
        return (payload["endpoint_id"] in {
            "SPOT_ORDER_CREATE", "FUTURES_ORDER_CREATE",
        } and _bounded_identity(payload["request_id"])
                and _lower_hash(payload["request_sha256"])
                and isinstance(payload["timestamp_ms"], int)
                and not isinstance(payload["timestamp_ms"], bool)
                and 0 <= payload["timestamp_ms"] <= (1 << 53) - 1)
    if event_type == "BINANCE_REQUEST_SEND_STARTED":
        return _bounded_identity(payload["request_id"])
    if event_type == "BINANCE_ORDER_ACKNOWLEDGED":
        return (isinstance(payload["order_id"], int)
                and not isinstance(payload["order_id"], bool)
                and payload["order_id"] > 0
                and payload["venue_client_order_id"]
                == private["venue_client_order_id"])
    if event_type == "BINANCE_FILL_OBSERVED":
        try:
            return (isinstance(payload["trade_id"], int)
                    and payload["trade_id"] >= 0
                    and all(canonical_decimal(payload[key]) == payload[key]
                            for key in ("quantity", "price", "quote_quantity",
                                        "fee", "cumulative_filled_quantity"))
                    and isinstance(payload["fee_asset"], str)
                    and bool(payload["fee_asset"]))
        except (TypeError, ValueError):
            return False
    if event_type.startswith("BINANCE_ORDER_") and event_type not in {
        "BINANCE_ORDER_REJECTED", "BINANCE_ORDER_UNKNOWN",
    }:
        try:
            return (all(canonical_decimal(payload[key]) == payload[key]
                        for key in ("cumulative_filled_quantity",
                                    "cumulative_fee"))
                    and payload["venue_terminal_status"] in {
                        "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED",
                    })
        except (TypeError, ValueError):
            return False
    if event_type in {"BINANCE_ORDER_REJECTED", "BINANCE_ORDER_UNKNOWN"}:
        return (isinstance(payload["venue_code"], int)
                and not isinstance(payload["venue_code"], bool)
                and payload["blocks_new_risk"]
                is (event_type == "BINANCE_ORDER_UNKNOWN"))
    if event_type == "BINANCE_FILLS_FEES_REPLAYED":
        try:
            return (payload["fill_ids"] == private["fill_ids"]
                    and canonical_decimal(payload["cumulative_fee"])
                    == payload["cumulative_fee"])
        except (TypeError, ValueError):
            return False
    if event_type in {
        "BINANCE_POSITION_BALANCE_RECONCILED",
        "BINANCE_RECONCILIATION_SUCCEEDED",
    }:
        return (isinstance(payload["reconciliation_id"], str)
                and payload["reconciliation_id"].startswith(
                    "binance_reconciliation_"
                ) and _lower_hash(payload["reconciliation_id"][23:]))
    if event_type == "BINANCE_PROTECTION_RECONCILED_IF_EXPOSED":
        return (isinstance(payload["required"], bool)
                and payload["status"] in {"NOT_REQUIRED", "VERIFIED"}
                and ((payload["required"] is False
                      and payload["client_algo_id_or_null"] is None
                      and payload["status"] == "NOT_REQUIRED")
                     or (payload["required"] is True
                         and isinstance(payload["client_algo_id_or_null"], str)
                         and payload["status"] == "VERIFIED")))
    return (event_type == "BINANCE_RECONCILIATION_FAILED"
            and _bounded_identity(payload["reason_code"]))


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
