"""Strict composite public-market evidence for replacement simulation."""

import base64
import hashlib
import json
from time import sleep as _sleep
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping, Optional
from urllib.request import Request

from jsonschema import Draft202012Validator

from .canonical import canonical_decimal, canonical_json, stable_id, utc_datetime
from .challenger_replacement_live_input import (
    ChallengerReplacementLiveInputError,
    _strict_response_json,
    acquire_challenger_replacement_live_capture as _acquire_live_capture,
    load_challenger_replacement_live_capture_bytes,
)
from .challenger_replacement_opportunity_projection import opportunity_id_for
from .challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from .challenger_replacement_plan_v2 import build_challenger_replacement_plan_v2
from .challenger_replacement_plan_v3 import challenger_replacement_plan_v3_reasons
from .challenger_replacement_public_http import (
    PublicHttpError,
    attempt_document,
    open_fixed_public_request as _open_fixed_public_request,
    transport_failure_attempt,
)
from .challenger_replacement_runtime import ChallengerReplacementRuntimeState
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_CAPABILITY_TOKEN = object()
_SCHEMA = "challenger-replacement-public-market-capture-v2.schema.json"
_MAX_CAPTURE_BYTES = 16 * 1024 * 1024
_MAX_SAFE_INTEGER = 2**53 - 1
_MAX_JSON_CONTAINER_DEPTH = 64
_HASH_CHARS = frozenset("0123456789abcdef")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_BUILD_KEYS = {
    "release_tag", "peeled_commit", "package_version", "manifest_version",
    "build_input_tree_hash", "manifest_hash", "manifest_file_sha256",
}
_V067_BUILD = {
    "release_tag": "v0.67.0",
    "peeled_commit": "ca022edccdcbb2d28b1ea25002e5f19512795e3e",
    "package_version": "0.67.0",
    "manifest_version": "1.61.0",
    "build_input_tree_hash": (
        "5c2a98492aa45f311cea75617745ac6d1e0afe0ea2ff36a5950a0f5c00c4efa1"
    ),
    "manifest_hash": (
        "2b72a470a2f210461a3a6753fd3d603fee9b90df76e825deea3b9bde61a26110"
    ),
    "manifest_file_sha256": (
        "ec2ba2d48dd35676eb442ed80cd0e45a642a2b109626db2f54a25d25823a2bf8"
    ),
}
_REQUESTS = (
    ("spot_exchange_info", "https://data-api.binance.vision/api/v3/exchangeInfo?symbol=ETHUSDT", 1024 * 1024),
    ("spot_book_ticker", "https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=ETHUSDT", 1024 * 1024),
    ("perpetual_exchange_info", "https://fapi.binance.com/fapi/v1/exchangeInfo", 4 * 1024 * 1024),
    ("perpetual_book_ticker", "https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=ETHUSDT", 1024 * 1024),
    ("perpetual_mark", "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT", 1024 * 1024),
)
_ATTEMPT_KEYS = {
    "sequence", "outcome", "error_reason_or_null", "request_started_at",
    "response_received_at", "status", "final_url", "selected_headers",
    "body_size_bytes", "body_sha256", "response_body_base64",
}
_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
_HEADER_KEYS = {
    "content_type_or_null",
    "http_date_or_null", "etag_or_null", "last_modified_or_null",
    "retry_after_or_null",
}


class ChallengerReplacementPublicMarketCaptureError(ValueError):
    """The composite public-market capture failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, init=False)
class ChallengerReplacementPublicMarketCapture:
    """Strictly replayed public bytes admitted to the v0.76 simulation."""

    _document: Mapping[str, Any]
    _canonical_bytes: bytes

    def __init__(self, *, _token, document, canonical_bytes):
        if _token is not _CAPABILITY_TOKEN:
            raise TypeError("public market capture is adapter-derived")
        object.__setattr__(self, "_document", deepcopy(dict(document)))
        object.__setattr__(self, "_canonical_bytes", bytes(canonical_bytes))

    @property
    def document(self):
        return deepcopy(dict(self._document))

    @property
    def canonical_bytes(self):
        return bytes(self._canonical_bytes)


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(
        resources.files("crypto_quant").joinpath("schemas", _SCHEMA).read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _invalid(reason):
    raise ChallengerReplacementPublicMarketCaptureError(reason)


def _wall_now():
    return datetime.now(timezone.utc)


def _hash(value, length=64):
    return (
        isinstance(value, str)
        and len(value) == length
        and not set(value) - _HASH_CHARS
    )


def _utc(value):
    if not isinstance(value, str):
        _invalid("PUBLIC_MARKET_CAPTURE_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerReplacementPublicMarketCaptureError(
            "PUBLIC_MARKET_CAPTURE_TIME_INVALID"
        ) from error
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or utc_datetime(parsed) != value
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def _decimal(value, *, positive=False):
    if not isinstance(value, str):
        _invalid("PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID")
    try:
        number = Decimal(value)
        rendered = canonical_decimal(number)
    except (CanonicalizationError, InvalidOperation, ValueError) as error:
        raise ChallengerReplacementPublicMarketCaptureError(
            "PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID"
        ) from error
    if positive and number <= 0:
        _invalid("PUBLIC_MARKET_CAPTURE_DECIMAL_INVALID")
    return number, rendered


def _from_epoch_millis(value):
    return _EPOCH + timedelta(milliseconds=value)


def _to_epoch_millis(value):
    delta = value - _EPOCH
    if delta.microseconds % 1000:
        _invalid("PUBLIC_MARKET_CAPTURE_TIME_INVALID")
    return (
        delta.days * 86_400_000
        + delta.seconds * 1000
        + delta.microseconds // 1000
    )


def _strict_document(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_CAPTURE_BYTES:
        _invalid("PUBLIC_MARKET_CAPTURE_SIZE_INVALID")

    def pairs(items):
        result = {}
        for key, value in items:
            if not isinstance(key, str) or not key.isascii() or key in result:
                _invalid("PUBLIC_MARKET_CAPTURE_JSON_INVALID")
            result[key] = value
        return result

    def reject_number(_value):
        _invalid("PUBLIC_MARKET_CAPTURE_JSON_INVALID")

    def parse_integer(value):
        parsed = int(value)
        if abs(parsed) > _MAX_SAFE_INTEGER:
            _invalid("PUBLIC_MARKET_CAPTURE_JSON_INVALID")
        return parsed

    try:
        document = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_int=parse_integer,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except ChallengerReplacementPublicMarketCaptureError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ChallengerReplacementPublicMarketCaptureError(
            "PUBLIC_MARKET_CAPTURE_JSON_INVALID"
        ) from error
    if not isinstance(document, Mapping):
        _invalid("PUBLIC_MARKET_CAPTURE_JSON_INVALID")
    pending = [(document, 1)]
    while pending:
        candidate, depth = pending.pop()
        if isinstance(candidate, (Mapping, list)):
            if depth > _MAX_JSON_CONTAINER_DEPTH:
                _invalid("PUBLIC_MARKET_CAPTURE_JSON_INVALID")
            values = (
                candidate.values()
                if isinstance(candidate, Mapping)
                else candidate
            )
            pending.extend(
                (value, depth + 1)
                for value in values
                if isinstance(value, (Mapping, list))
            )
    if data != canonical_json(document).encode("utf-8"):
        _invalid("PUBLIC_MARKET_CAPTURE_CANONICAL_BYTES_REQUIRED")
    if tuple(_validator().iter_errors(document)):
        _invalid("PUBLIC_MARKET_CAPTURE_SCHEMA_INVALID")
    return document


def _validate_build(value):
    if (
        not isinstance(value, Mapping)
        or set(value) != _BUILD_KEYS
        or value["release_tag"] != "v0.76.0"
        or value["package_version"] != "0.76.0"
        or value["manifest_version"] != "1.70.0"
        or not _hash(value["peeled_commit"], 40)
        or any(
            not _hash(value[name])
            for name in (
                "build_input_tree_hash", "manifest_hash",
                "manifest_file_sha256",
            )
        )
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_BUILD_INVALID")


def _selected_payload(entry, expected, scheduled, captured):
    if not isinstance(entry, Mapping) or set(entry) != {
        "request", "attempts", "selected_success_attempt_index"
    }:
        _invalid("PUBLIC_MARKET_CAPTURE_REQUEST_INVALID")
    kind, url, limit = expected
    identity = {
        "request_kind": kind, "method": "GET", "url": url,
        "max_body_bytes": limit,
    }
    request = entry["request"]
    if request != {
        "request_id": stable_id(
            "challenger_replacement_public_market_request", identity
        ),
        **identity,
    }:
        _invalid("PUBLIC_MARKET_CAPTURE_REQUEST_INVALID")
    attempts = entry["attempts"]
    selected = entry["selected_success_attempt_index"]
    if (
        not isinstance(attempts, list)
        or not 1 <= len(attempts) <= 3
        or not isinstance(selected, int)
        or isinstance(selected, bool)
        or selected != len(attempts) - 1
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID")
    previous = None
    selected_body = None
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, Mapping) or set(attempt) != _ATTEMPT_KEYS:
            _invalid("PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID")
        try:
            started = _utc(attempt["request_started_at"])
            received = _utc(attempt["response_received_at"])
            body = base64.b64decode(
                attempt["response_body_base64"], validate=True
            )
        except (TypeError, ValueError) as error:
            raise ChallengerReplacementPublicMarketCaptureError(
                "PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID"
            ) from error
        headers = attempt["selected_headers"]
        if (
            attempt["sequence"] != index + 1
            or not isinstance(headers, Mapping)
            or set(headers) != _HEADER_KEYS
            or any(v is not None and not isinstance(v, str) for v in headers.values())
            or (previous is not None and started < previous)
            or received < started
            or started < scheduled
            or received > captured
            or len(body) > limit
            or attempt["body_size_bytes"] != len(body)
            or attempt["body_sha256"] != hashlib.sha256(body).hexdigest()
            or attempt["response_body_base64"] != base64.b64encode(body).decode("ascii")
        ):
            _invalid("PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID")
        if attempt["outcome"] == "TRANSPORT_ERROR":
            if (
                index == selected
                or attempt["error_reason_or_null"]
                != "PUBLIC_HTTP_TRANSPORT_FAILURE"
                or attempt["status"] is not None
                or attempt["final_url"] is not None
                or any(value is not None for value in headers.values())
                or body
            ):
                _invalid("PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID")
        elif attempt["outcome"] == "HTTP_RESPONSE":
            if (
                attempt["error_reason_or_null"] is not None
                or attempt["final_url"] != url
                or not isinstance(attempt["status"], int)
                or isinstance(attempt["status"], bool)
                or (index == selected and attempt["status"] != 200)
                or (
                    index == selected
                    and (
                        not isinstance(headers["content_type_or_null"], str)
                        or headers["content_type_or_null"].split(";", 1)[0].strip().lower()
                        != "application/json"
                    )
                )
                or (
                    index < selected
                    and attempt["status"]
                    not in {408, 425, 429, 500, 502, 503, 504}
                )
            ):
                _invalid("PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID")
        else:
            _invalid("PUBLIC_MARKET_CAPTURE_ATTEMPT_INVALID")
        previous = received
        if index == selected:
            selected_body = body
    try:
        return _strict_response_json(selected_body)
    except (ChallengerReplacementLiveInputError, TypeError) as error:
        raise ChallengerReplacementPublicMarketCaptureError(
            "PUBLIC_MARKET_CAPTURE_RESPONSE_INVALID"
        ) from error


def _one_symbol(payload, *, perpetual):
    if not isinstance(payload, Mapping) or not isinstance(payload.get("symbols"), list):
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    matches = [item for item in payload["symbols"] if isinstance(item, Mapping) and item.get("symbol") == "ETHUSDT"]
    if len(matches) != 1:
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    symbol = matches[0]
    expected = {
        "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "USDT",
    }
    if any(symbol.get(key) != value for key, value in expected.items()):
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    if perpetual and (
        symbol.get("pair") != "ETHUSDT"
        or symbol.get("contractType") != "PERPETUAL"
        or symbol.get("marginAsset") != "USDT"
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    if not isinstance(symbol.get("filters"), list):
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    return symbol


def _filter(filters, kind, *, optional=False):
    matches = [item for item in filters if isinstance(item, Mapping) and item.get("filterType") == kind]
    if not matches and optional:
        return None
    if len(matches) != 1:
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    return matches[0]


def _lot(filters):
    market = _filter(filters, "MARKET_LOT_SIZE", optional=True)
    chosen = market
    if market is None:
        chosen = _filter(filters, "LOT_SIZE")
    else:
        try:
            values = tuple(Decimal(market[name]) for name in ("minQty", "maxQty", "stepSize"))
        except (InvalidOperation, KeyError, TypeError, ValueError):
            _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
        if not all(value > 0 for value in values):
            chosen = _filter(filters, "LOT_SIZE")
    try:
        normalized = tuple(_decimal(chosen[name], positive=True)[1] for name in ("minQty", "maxQty", "stepSize"))
    except KeyError:
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    if Decimal(normalized[0]) > Decimal(normalized[1]):
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    return normalized


def _rules(symbol, *, perpetual):
    filters = symbol["filters"]
    price = _filter(filters, "PRICE_FILTER")
    try:
        tick = _decimal(price["tickSize"], positive=True)[1]
    except KeyError:
        _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    minimum, maximum, step = _lot(filters)
    if perpetual:
        minimum_notional = _filter(filters, "MIN_NOTIONAL")
        try:
            notional = _decimal(minimum_notional["notional"], positive=True)[1]
        except KeyError:
            _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
    else:
        applicable = []
        by_filter_type = {}
        for item in filters:
            if not isinstance(item, Mapping):
                _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
            applicability_key = {
                "NOTIONAL": "applyMinToMarket",
                "MIN_NOTIONAL": "applyToMarket",
            }.get(item.get("filterType"))
            if (
                applicability_key is not None
                and not isinstance(item.get(applicability_key), bool)
            ):
                _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
            if item.get("filterType") == "NOTIONAL" and item.get("applyMinToMarket") is True:
                value = _decimal(item.get("minNotional"), positive=True)[0]
                applicable.append(value)
                if (
                    "NOTIONAL" in by_filter_type
                    and by_filter_type["NOTIONAL"] != value
                ):
                    _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
                by_filter_type["NOTIONAL"] = value
            elif item.get("filterType") == "MIN_NOTIONAL" and item.get("applyToMarket") is True:
                value = _decimal(item.get("minNotional"), positive=True)[0]
                applicable.append(value)
                if (
                    "MIN_NOTIONAL" in by_filter_type
                    and by_filter_type["MIN_NOTIONAL"] != value
                ):
                    _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
                by_filter_type["MIN_NOTIONAL"] = value
        if not applicable:
            _invalid("PUBLIC_MARKET_CAPTURE_RULES_INVALID")
        notional = canonical_decimal(max(applicable))
    result = {
        "price_tick": tick, "min_quantity": minimum,
        "max_quantity": maximum, "quantity_step": step,
        "min_notional": notional,
    }
    if perpetual:
        result["contract_multiplier"] = "1"
    return result


def _quote(payload, *, mark=False, scheduled=None, captured=None):
    if not isinstance(payload, Mapping) or payload.get("symbol") != "ETHUSDT":
        _invalid("PUBLIC_MARKET_CAPTURE_QUOTE_INVALID")
    if mark:
        value, rendered = _decimal(payload.get("markPrice"), positive=True)
        timestamp = payload.get("time")
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            _invalid("PUBLIC_MARKET_CAPTURE_QUOTE_INVALID")
        when = _from_epoch_millis(timestamp)
        if (
            scheduled is None
            or captured is None
            or not max(scheduled, captured - timedelta(minutes=10))
            <= when
            <= captured
        ):
            _invalid("PUBLIC_MARKET_CAPTURE_QUOTE_INVALID")
        return rendered
    bid, bid_text = _decimal(payload.get("bidPrice"), positive=True)
    ask, ask_text = _decimal(payload.get("askPrice"), positive=True)
    if bid > ask:
        _invalid("PUBLIC_MARKET_CAPTURE_QUOTE_INVALID")
    return {"bid": bid_text, "ask": ask_text}


def _funding(payload, scheduled):
    if not isinstance(payload, list) or len(payload) > 16:
        _invalid("PUBLIC_MARKET_CAPTURE_FUNDING_INVALID")
    result = []
    previous = None
    lower = scheduled - timedelta(hours=4)
    for item in payload:
        if (
            not isinstance(item, Mapping)
            or set(item) != {
                "symbol", "fundingTime", "fundingRate", "markPrice",
                "fundingRateType",
            }
            or item.get("symbol") != "ETHUSDT"
            or item.get("fundingRateType") != "REGULAR"
        ):
            _invalid("PUBLIC_MARKET_CAPTURE_FUNDING_INVALID")
        millis = item.get("fundingTime")
        if not isinstance(millis, int) or isinstance(millis, bool):
            _invalid("PUBLIC_MARKET_CAPTURE_FUNDING_INVALID")
        when = _from_epoch_millis(millis)
        if not lower < when <= scheduled or (previous is not None and when <= previous):
            _invalid("PUBLIC_MARKET_CAPTURE_FUNDING_INVALID")
        _, rate = _decimal(item.get("fundingRate"))
        _, mark = _decimal(item.get("markPrice"), positive=True)
        result.append({"funding_time": utc_datetime(when), "rate": rate, "mark": mark})
        previous = when
    return result


def _expected_requests(scheduled):
    scheduled_millis = _to_epoch_millis(scheduled)
    return list(_REQUESTS) + [("funding_history", (
        "https://fapi.binance.com/fapi/v1/fundingRate?"
        f"endTime={scheduled_millis}&limit=16&"
        f"startTime={scheduled_millis - 14399999}&symbol=ETHUSDT"
    ), 1024 * 1024)]


def _normalized_capture(live, payloads, *, scheduled, captured):
    spot_symbol = _one_symbol(payloads[0], perpetual=False)
    perpetual_symbol = _one_symbol(payloads[2], perpetual=True)
    return {
        "bars": deepcopy(live["rows"]),
        "quotes": {
            "spot": _quote(payloads[1]),
            "perpetual": {
                **_quote(payloads[3]),
                "mark": _quote(
                    payloads[4], mark=True,
                    scheduled=scheduled, captured=captured,
                ),
            },
        },
        "funding_records": _funding(payloads[5], scheduled),
        "simulation_rules": {
            "spot": _rules(spot_symbol, perpetual=False),
            "perpetual": _rules(perpetual_symbol, perpetual=True),
        },
    }


def load_challenger_replacement_public_market_capture_bytes(
    data: bytes, *, plan: Mapping[str, Any], build_identity: Mapping[str, Any],
    previous_source_bundle: Optional[Mapping[str, Any]],
):
    """Strictly replay one canonical PublicMarketCaptureV2 document."""

    document = _strict_document(data)
    if document["capture_hash"] != artifact_self_hash(document, "capture_hash"):
        _invalid("PUBLIC_MARKET_CAPTURE_HASH_INVALID")
    if (
        not isinstance(plan, Mapping)
        or challenger_replacement_plan_v3_reasons(plan)
        or document["plan"] != {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]}
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_PLAN_INVALID")
    _validate_build(build_identity)
    if document["build_identity"] != dict(build_identity):
        _invalid("PUBLIC_MARKET_CAPTURE_BUILD_INVALID")
    opportunity = document["opportunity"]
    if not isinstance(opportunity, Mapping) or set(opportunity) != {
        "opportunity_id", "sequence", "scheduled_for", "captured_at"
    }:
        _invalid("PUBLIC_MARKET_CAPTURE_OPPORTUNITY_INVALID")
    scheduled = _utc(opportunity["scheduled_for"])
    captured = _utc(opportunity["captured_at"])
    if (
        opportunity["opportunity_id"] != opportunity_id_for(opportunity["scheduled_for"])
        or not isinstance(opportunity["sequence"], int)
        or isinstance(opportunity["sequence"], bool)
        or not 1 <= opportunity["sequence"] <= 2**53 - 1
        or not scheduled + timedelta(minutes=2) <= captured <= scheduled + timedelta(minutes=10)
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_OPPORTUNITY_INVALID")
    nested = document["nested_live_capture"]
    if not isinstance(nested, Mapping) or set(nested) != {
        "canonical_base64", "sha256", "capture_id", "capture_hash"
    }:
        _invalid("PUBLIC_MARKET_CAPTURE_NESTED_INVALID")
    try:
        nested_bytes = base64.b64decode(nested["canonical_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise ChallengerReplacementPublicMarketCaptureError(
            "PUBLIC_MARKET_CAPTURE_NESTED_INVALID"
        ) from error
    if (
        nested["canonical_base64"]
        != base64.b64encode(nested_bytes).decode("ascii")
        or nested["sha256"] != hashlib.sha256(nested_bytes).hexdigest()
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_NESTED_INVALID")
    try:
        live = load_challenger_replacement_live_capture_bytes(
            nested_bytes, plan=build_challenger_replacement_plan_v2(),
            build_identity=_V067_BUILD,
            previous_source_bundle=previous_source_bundle,
        )
    except ChallengerReplacementLiveInputError as error:
        raise ChallengerReplacementPublicMarketCaptureError(
            "PUBLIC_MARKET_CAPTURE_NESTED_INVALID"
        ) from error
    if (
        nested["capture_id"] != live["capture_id"]
        or nested["capture_hash"] != live["capture_hash"]
        or opportunity["sequence"] != live["slot"]["sequence"]
        or opportunity["scheduled_for"] != live["slot"]["scheduled_for"]
        or captured < _utc(live["slot"]["captured_at"])
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_NESTED_INVALID")
    expected = _expected_requests(scheduled)
    if not isinstance(document["requests"], list) or len(document["requests"]) != 6:
        _invalid("PUBLIC_MARKET_CAPTURE_REQUEST_INVALID")
    payloads = [
        _selected_payload(entry, expected[index], scheduled, captured)
        for index, entry in enumerate(document["requests"])
    ]
    normalized = _normalized_capture(
        live, payloads, scheduled=scheduled, captured=captured
    )
    if document["normalized"] != normalized:
        _invalid("PUBLIC_MARKET_CAPTURE_NORMALIZED_INVALID")
    authority = document["authority"]
    expected_count = live["authority"]["network_request_count"] + sum(
        len(entry["attempts"]) for entry in document["requests"]
    )
    if authority != {
        "network_request_count": expected_count,
        "credentials_allowed": False, "account_requests_allowed": False,
        "broker_requests_allowed": False, "orders_allowed": False,
        "fund_movement_allowed": False,
    } or not 10 <= expected_count <= 24:
        _invalid("PUBLIC_MARKET_CAPTURE_AUTHORITY_INVALID")
    identity = {
        "plan": document["plan"], "build_identity": document["build_identity"],
        "opportunity": document["opportunity"],
        "nested_live_capture_sha256": nested["sha256"],
    }
    if document["capture_id"] != stable_id(
        "challenger_replacement_public_market_capture", identity
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_ID_INVALID")
    return ChallengerReplacementPublicMarketCapture(
        _token=_CAPABILITY_TOKEN, document=document, canonical_bytes=data
    )


def _previous_v067_source_bundle(projection, *, plan, build_identity):
    previous_bytes = projection.get("_previous_observed_source_bytes")
    if previous_bytes is None:
        return None
    previous = load_challenger_replacement_public_market_capture_bytes(
        previous_bytes,
        plan=plan,
        build_identity=build_identity,
        previous_source_bundle=None,
    )
    return {"klines": previous.document["normalized"]["bars"]}


class _V067AcquisitionState(ChallengerReplacementRuntimeState):
    """Read-only shape adapter; the v3 event log remains the only authority."""

    def __init__(self, projection, previous_source_bundle):
        if not isinstance(projection, Mapping):
            _invalid("PUBLIC_MARKET_CAPTURE_STATE_INVALID")
        terminal_count = projection.get("terminal_opportunity_count", 0)
        next_required = projection.get("next_required_opportunity")
        if (
            not isinstance(terminal_count, int)
            or isinstance(terminal_count, bool)
            or terminal_count < 0
            or next_required is not None
            and not isinstance(next_required, Mapping)
        ):
            _invalid("PUBLIC_MARKET_CAPTURE_STATE_INVALID")
        scheduled_for = (
            None
            if next_required is None
            else next_required.get("scheduled_for")
        )
        self.plan = build_challenger_replacement_plan_v2()
        self.build_identity = deepcopy(_V067_BUILD)
        self._projection = {
            "failed_slot_count": 0,
            "active_slot_id": projection.get("active_opportunity_id"),
            "next_required_slot": {
                "sequence": terminal_count + 1,
                "scheduled_for": scheduled_for,
            },
            "_previous_source_bundle": deepcopy(previous_source_bundle),
        }

    def _replay(self):
        return deepcopy(self._projection)


def acquire_challenger_replacement_public_market_capture(*, state):
    """Acquire the fixed public evidence required by one natural opportunity."""

    if (
        not isinstance(state, ChallengerReplacementOpportunityState)
        or not isinstance(getattr(state, "plan", None), Mapping)
        or not isinstance(getattr(state, "build_identity", None), Mapping)
    ):
        _invalid("PUBLIC_MARKET_CAPTURE_STATE_INVALID")
    projection = state._replay()
    if not isinstance(projection, Mapping):
        _invalid("PUBLIC_MARKET_CAPTURE_STATE_INVALID")
    try:
        previous_source_bundle = _previous_v067_source_bundle(
            projection,
            plan=state.plan,
            build_identity=state.build_identity,
        )
        nested = _acquire_live_capture(
            state=_V067AcquisitionState(projection, previous_source_bundle)
        )
        nested_bytes = bytes(nested.canonical_bytes)
        live = deepcopy(dict(nested.document))
        replayed_live = load_challenger_replacement_live_capture_bytes(
            nested_bytes,
            plan=build_challenger_replacement_plan_v2(),
            build_identity=_V067_BUILD,
            previous_source_bundle=previous_source_bundle,
        )
        if live != replayed_live:
            _invalid("PUBLIC_MARKET_CAPTURE_NESTED_INVALID")
        scheduled = _utc(live["slot"]["scheduled_for"])
        captured = _utc(live["slot"]["captured_at"])
    except ChallengerReplacementPublicMarketCaptureError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementPublicMarketCaptureError(
            "PUBLIC_MARKET_CAPTURE_NESTED_INVALID"
        ) from error
    expected = _expected_requests(scheduled)
    ledgers = []
    payloads = []
    for kind, url, limit in expected:
        identity = {
            "request_kind": kind, "method": "GET", "url": url,
            "max_body_bytes": limit,
        }
        attempts = []
        selected = None
        selected_payload = None
        for index in range(3):
            transport_started = _wall_now()
            try:
                response = _open_fixed_public_request(
                    Request(
                        url, method="GET",
                        headers={"Accept": "application/json"},
                    ),
                    max_body_bytes=limit,
                )
                attempt = attempt_document(response, index + 1)
                headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
                attempt["selected_headers"]["content_type_or_null"] = (
                    headers.get("content-type")
                )
                if response.final_url != url:
                    _invalid("PUBLIC_MARKET_CAPTURE_RESPONSE_INVALID")
                started = _utc(response.request_started_at)
                received = _utc(response.response_received_at)
                if not scheduled <= started <= received:
                    _invalid("PUBLIC_MARKET_CAPTURE_TIME_INVALID")
            except PublicHttpError as error:
                if error.reason_code != "PUBLIC_HTTP_TRANSPORT_FAILURE":
                    raise ChallengerReplacementPublicMarketCaptureError(
                        "PUBLIC_MARKET_CAPTURE_RESPONSE_INVALID"
                    ) from error
                try:
                    attempt = transport_failure_attempt(
                        index + 1,
                        started=transport_started,
                        received=_wall_now(),
                    )
                except PublicHttpError as clock_error:
                    raise ChallengerReplacementPublicMarketCaptureError(
                        "PUBLIC_MARKET_CAPTURE_TIME_INVALID"
                    ) from clock_error
                attempt["selected_headers"]["content_type_or_null"] = None
                attempts.append(attempt)
                if index < 2:
                    _sleep(index + 1)
                    continue
                break
            attempts.append(attempt)
            if response.status == 200:
                try:
                    selected_payload = _strict_response_json(response.body)
                except ChallengerReplacementLiveInputError as error:
                    raise ChallengerReplacementPublicMarketCaptureError(
                        "PUBLIC_MARKET_CAPTURE_RESPONSE_INVALID"
                    ) from error
                selected = index
                break
            if response.status not in _TRANSIENT_STATUS:
                _invalid("PUBLIC_MARKET_CAPTURE_RESPONSE_INVALID")
            if index < 2:
                _sleep(index + 1)
        if selected is None:
            _invalid("PUBLIC_MARKET_CAPTURE_RETRIES_EXHAUSTED")
        ledgers.append({
            "request": {
                "request_id": stable_id(
                    "challenger_replacement_public_market_request", identity
                ),
                **identity,
            },
            "attempts": attempts,
            "selected_success_attempt_index": selected,
        })
        payloads.append(selected_payload)
    captured = max(
        [captured]
        + [_utc(attempt["response_received_at"])
           for ledger in ledgers for attempt in ledger["attempts"]]
    )
    captured_text = captured.isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
    normalized = _normalized_capture(
        live, payloads, scheduled=scheduled, captured=captured
    )
    opportunity = {
        "opportunity_id": opportunity_id_for(live["slot"]["scheduled_for"]),
        "sequence": live["slot"]["sequence"],
        "scheduled_for": live["slot"]["scheduled_for"],
        "captured_at": captured_text,
    }
    document = {
        "$schema": "./challenger-replacement-public-market-capture-v2.schema.json",
        "schema_version": "2.0.0",
        "capture_id": "",
        "capture_hash": "0" * 64,
        "evidence_qualification": (
            "PUBLIC_MARKET_CAPTURE_V2_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER"
        ),
        "plan": {
            "plan_id": state.plan["plan_id"],
            "plan_hash": state.plan["plan_hash"],
        },
        "build_identity": deepcopy(dict(state.build_identity)),
        "opportunity": opportunity,
        "nested_live_capture": {
            "canonical_base64": base64.b64encode(nested_bytes).decode("ascii"),
            "sha256": hashlib.sha256(nested_bytes).hexdigest(),
            "capture_id": live["capture_id"],
            "capture_hash": live["capture_hash"],
        },
        "requests": ledgers,
        "normalized": normalized,
        "authority": {
            "network_request_count": (
                live["authority"]["network_request_count"]
                + sum(len(item["attempts"]) for item in ledgers)
            ),
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "broker_requests_allowed": False,
            "orders_allowed": False,
            "fund_movement_allowed": False,
        },
    }
    identity = {
        "plan": document["plan"],
        "build_identity": document["build_identity"],
        "opportunity": opportunity,
        "nested_live_capture_sha256": document["nested_live_capture"]["sha256"],
    }
    document["capture_id"] = stable_id(
        "challenger_replacement_public_market_capture", identity
    )
    document["capture_hash"] = artifact_self_hash(document, "capture_hash")
    canonical_bytes = canonical_json(document).encode("utf-8")
    return load_challenger_replacement_public_market_capture_bytes(
        canonical_bytes,
        plan=state.plan,
        build_identity=state.build_identity,
        previous_source_bundle=previous_source_bundle,
    )
