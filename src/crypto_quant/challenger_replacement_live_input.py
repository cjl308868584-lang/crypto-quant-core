"""Strict live-input boundary for the replacement Challenger."""

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .challenger_replacement_plan_v2 import challenger_replacement_plan_v2_reasons
from .evidence import artifact_self_hash
from .errors import CanonicalizationError
from .runtime_health import server_time_probe_reasons, server_time_probe_trust_hash


_CAPABILITY_TOKEN = object()
_CAPTURE_SCHEMA = "./challenger-replacement-live-capture-v1.schema.json"
_QUALIFICATION = "REPLACEMENT_CONFIRMATORY_COHORT_INPUT"
_MAX_CAPTURE_BYTES = 2 * 1024 * 1024
_MAX_RESPONSE_BYTES = 256 * 1024
_BUILD_KEYS = {
    "release_tag",
    "peeled_commit",
    "package_version",
    "manifest_version",
    "build_input_tree_hash",
    "manifest_hash",
    "manifest_file_sha256",
}
_SLOT_KEYS = {"slot_id", "sequence", "scheduled_for", "captured_at"}
_AUTHORITY_KEYS = {
    "network_request_count",
    "credentials_allowed",
    "account_requests_allowed",
    "broker_requests_allowed",
    "orders_allowed",
}
_REQUEST_KEYS = {
    "request_id",
    "method",
    "url",
    "symbol",
    "interval",
    "limit",
    "end_time_ms",
}
_ATTEMPT_KEYS = {
    "sequence",
    "request_started_at",
    "response_received_at",
    "status",
    "final_url",
    "selected_headers",
    "body_size_bytes",
    "body_sha256",
    "response_body_utf8",
}
_HEADER_KEYS = {
    "http_date_or_null",
    "etag_or_null",
    "last_modified_or_null",
    "retry_after_or_null",
}
_ROW_DESCRIPTOR = {
    "provider": "BINANCE_PUBLIC_DATA",
    "market": "SPOT",
    "data_family": "KLINES",
    "symbol": "ETHUSDT",
    "interval": "4h",
}
_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


class ChallengerReplacementLiveInputError(ValueError):
    """The replacement live-input boundary failed closed."""

    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _build_live_capture_document(
    *,
    plan,
    build_identity,
    slot,
    clock_records,
    kline_request,
    attempts,
    selected_attempt_index,
    rows,
):
    document = {
        "$schema": _CAPTURE_SCHEMA,
        "schema_version": "1.0.0",
        "capture_id": "",
        "capture_hash": "",
        "evidence_qualification": _QUALIFICATION,
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "build_identity": deepcopy(dict(build_identity)),
        "slot": deepcopy(dict(slot)),
        "clock": deepcopy(dict(clock_records)),
        "kline_request": deepcopy(dict(kline_request)),
        "attempts": deepcopy(list(attempts)),
        "selected_success_attempt_index": selected_attempt_index,
        "rows": deepcopy(list(rows)),
        "authority": {
            "network_request_count": 3 + len(attempts),
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "broker_requests_allowed": False,
            "orders_allowed": False,
        },
    }
    document["capture_id"] = stable_id(
        "challenger_replacement_live_capture",
        {
            "plan": document["plan"],
            "build_identity": document["build_identity"],
            "slot": document["slot"],
        },
    )
    document["capture_hash"] = artifact_self_hash(document, "capture_hash")
    return document


def _grant_live_capture(*, document, canonical_bytes, token):
    if token is not _CAPABILITY_TOKEN:
        raise TypeError("live capture capability grant is private")
    if canonical_bytes != canonical_json(document).encode("utf-8"):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_CANONICAL_BYTES_REQUIRED"
        )
    return ChallengerReplacementLiveCapture(
        _token=_CAPABILITY_TOKEN,
        document=document,
        canonical_bytes=canonical_bytes,
    )


@lru_cache(maxsize=1)
def _capture_validator():
    schema = json.loads(
        resources.files("crypto_quant")
        .joinpath("schemas", "challenger-replacement-live-capture-v1.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _strict_json(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_CAPTURE_BYTES:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SIZE_INVALID"
        )

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ChallengerReplacementLiveInputError(
                    "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
        )

    try:
        document = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except ChallengerReplacementLiveInputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
        ) from error
    if not isinstance(document, Mapping):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
        )
    return document


def load_challenger_replacement_live_capture_bytes(
    data, *, plan, build_identity, previous_source_bundle
):
    """Load bounded canonical bytes without granting runtime authority."""

    document = _strict_json(data)
    if data != canonical_json(document).encode("utf-8"):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_CANONICAL_BYTES_REQUIRED"
        )
    if tuple(_capture_validator().iter_errors(document)):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SCHEMA_INVALID"
        )
    if (
        not _lowerhex(document["capture_hash"], 64)
        or document["capture_hash"] != artifact_self_hash(document, "capture_hash")
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_HASH_INVALID"
        )
    if (
        not isinstance(plan, Mapping)
        or challenger_replacement_plan_v2_reasons(plan)
        or document["plan"]
        != {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]}
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_PLAN_BINDING_INVALID"
        )
    if (
        not isinstance(build_identity, Mapping)
        or set(build_identity) != _BUILD_KEYS
        or document["build_identity"] != dict(build_identity)
        or build_identity["release_tag"] != "v0.67.0"
        or build_identity["package_version"] != "0.67.0"
        or build_identity["manifest_version"] != "1.61.0"
        or not _lowerhex(build_identity["peeled_commit"], 40)
        or any(
            not _lowerhex(build_identity[name], 64)
            for name in (
                "build_input_tree_hash",
                "manifest_hash",
                "manifest_file_sha256",
            )
        )
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_BUILD_BINDING_INVALID"
        )
    slot = document["slot"]
    try:
        scheduled = _utc_millis(slot["scheduled_for"])
        captured = _utc_millis(slot["captured_at"])
        expected_slot_id = stable_id(
            "challenger_replacement_slot",
            {
                "plan_hash": plan["plan_hash"],
                "scheduled_for": slot["scheduled_for"],
            },
        )
    except (KeyError, TypeError, ValueError):
        _invalid_slot()
    if (
        not isinstance(slot, Mapping)
        or set(slot) != _SLOT_KEYS
        or not isinstance(slot["sequence"], int)
        or isinstance(slot["sequence"], bool)
        or not 1 <= slot["sequence"] <= 2**53 - 1
        or scheduled.minute != 0
        or scheduled.second != 0
        or scheduled.microsecond != 0
        or scheduled.hour % 4
        or not scheduled + timedelta(minutes=2)
        <= captured
        <= scheduled + timedelta(minutes=10)
        or slot["slot_id"] != expected_slot_id
    ):
        _invalid_slot()
    clock = document["clock"]
    if not isinstance(clock, Mapping) or set(clock) != {"probe", "trust_hash"}:
        _invalid_clock()
    probe = clock["probe"]
    trust_hash = clock["trust_hash"]
    try:
        trusted_completed = _utc_millis(probe["trusted_completed_at_or_null"])
    except (KeyError, TypeError, ValueError):
        _invalid_clock()
    if (
        not _lowerhex(trust_hash, 64)
        or server_time_probe_trust_hash(probe) != trust_hash
        or server_time_probe_reasons(probe, trust_hash)
        or probe.get("health_status")
        not in {"HEALTHY_ALIGNED", "HEALTHY_CORRECTED"}
        or probe.get("sample_count") != 3
        or probe.get("valid_sample_count") != 3
        or trusted_completed < scheduled + timedelta(minutes=2)
        or trusted_completed > captured
    ):
        _invalid_clock()
    end_time_ms = int(scheduled.timestamp() * 1000) - 1
    expected_request_identity = {
        "method": "GET",
        "url": (
            "https://data-api.binance.vision/api/v3/klines?"
            f"endTime={end_time_ms}&interval=4h&limit=21&symbol=ETHUSDT"
        ),
        "symbol": "ETHUSDT",
        "interval": "4h",
        "limit": 21,
        "end_time_ms": end_time_ms,
    }
    request = document["kline_request"]
    if (
        not isinstance(request, Mapping)
        or set(request) != _REQUEST_KEYS
        or request
        != {
            "request_id": stable_id(
                "challenger_replacement_kline_request",
                expected_request_identity,
            ),
            **expected_request_identity,
        }
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_REQUEST_INVALID"
        )
    selected_payload = _validated_attempt_payload(
        document,
        request=request,
        trusted_completed=trusted_completed,
        captured=captured,
    )
    expected_rows = _normalize_kline_payload(
        selected_payload, scheduled=scheduled, captured=captured
    )
    if document["rows"] != expected_rows:
        _invalid_rows()
    if previous_source_bundle is not None:
        if (
            not isinstance(previous_source_bundle, Mapping)
            or not isinstance(previous_source_bundle.get("klines"), list)
            or len(previous_source_bundle["klines"]) != 21
            or previous_source_bundle["klines"][1:] != document["rows"][:20]
        ):
            raise ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_OVERLAP_INVALID"
            )
    authority = document["authority"]
    if (
        not isinstance(authority, Mapping)
        or set(authority) != _AUTHORITY_KEYS
        or not isinstance(authority["network_request_count"], int)
        or isinstance(authority["network_request_count"], bool)
        or authority["network_request_count"] != 3 + len(document["attempts"])
        or not 4 <= authority["network_request_count"] <= 6
        or any(authority[name] is not False for name in _AUTHORITY_KEYS - {"network_request_count"})
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_AUTHORITY_INVALID"
        )
    expected_capture_id = stable_id(
        "challenger_replacement_live_capture",
        {
            "plan": document["plan"],
            "build_identity": document["build_identity"],
            "slot": document["slot"],
        },
    )
    if document["capture_id"] != expected_capture_id:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ID_INVALID"
        )
    return deepcopy(dict(document))


def _utc_millis(value):
    if not isinstance(value, str):
        raise ValueError("UTC millisecond text required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    parsed = parsed.astimezone(timezone.utc)
    if value != utc_datetime(parsed):
        raise ValueError("canonical UTC milliseconds required")
    return parsed


def _validated_attempt_payload(document, *, request, trusted_completed, captured):
    attempts = document["attempts"]
    selected = document["selected_success_attempt_index"]
    if (
        not isinstance(attempts, list)
        or not 1 <= len(attempts) <= 3
        or not isinstance(selected, int)
        or isinstance(selected, bool)
        or selected != len(attempts) - 1
    ):
        _invalid_attempt()
    previous_received = trusted_completed
    selected_body = None
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, Mapping) or set(attempt) != _ATTEMPT_KEYS:
            _invalid_attempt()
        try:
            started = _utc_millis(attempt["request_started_at"])
            received = _utc_millis(attempt["response_received_at"])
            body = attempt["response_body_utf8"].encode("utf-8")
        except (AttributeError, TypeError, ValueError):
            _invalid_attempt()
        headers = attempt["selected_headers"]
        status = attempt["status"]
        if (
            attempt["sequence"] != index + 1
            or not isinstance(status, int)
            or isinstance(status, bool)
            or attempt["final_url"] != request["url"]
            or not isinstance(headers, Mapping)
            or set(headers) != _HEADER_KEYS
            or any(value is not None and not isinstance(value, str) for value in headers.values())
            or not previous_received <= started <= received <= captured
            or not 0 < len(body) <= _MAX_RESPONSE_BYTES
            or attempt["body_size_bytes"] != len(body)
            or attempt["body_sha256"] != hashlib.sha256(body).hexdigest()
            or (index < selected and status not in _TRANSIENT_STATUS)
            or (index == selected and status != 200)
        ):
            _invalid_attempt()
        previous_received = received
        if index == selected:
            selected_body = body
    try:
        payload = _strict_response_json(selected_body)
    except (ChallengerReplacementLiveInputError, TypeError):
        _invalid_rows()
    if not isinstance(payload, list) or len(payload) != 21:
        _invalid_rows()
    return payload


def _strict_response_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _invalid_rows()
            result[key] = value
        return result

    def reject_number(_value):
        _invalid_rows()

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except ChallengerReplacementLiveInputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ROWS_INVALID"
        ) from error
    try:
        canonical = canonical_json(value).encode("utf-8")
    except CanonicalizationError:
        _invalid_rows()
    if data != canonical:
        _invalid_rows()
    return value


def _normalize_kline_payload(payload, *, scheduled, captured):
    rows = []
    previous_open = None
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for raw in payload:
        if (
            not isinstance(raw, list)
            or len(raw) != 12
            or any(
                not isinstance(raw[index], int) or isinstance(raw[index], bool)
                for index in (0, 6, 8)
            )
            or raw[8] < 0
            or raw[11] != "0"
        ):
            _invalid_rows()
        try:
            opened = epoch + timedelta(milliseconds=raw[0])
            closed = epoch + timedelta(milliseconds=raw[6])
            opening, high, low, close = (
                Decimal(raw[index]) for index in (1, 2, 3, 4)
            )
            volumes = tuple(Decimal(raw[index]) for index in (5, 7, 9, 10))
            normalized_prices = tuple(
                canonical_decimal(value) for value in (opening, high, low, close)
            )
            normalized_volumes = tuple(canonical_decimal(value) for value in volumes)
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            _invalid_rows()
        if (
            tuple(raw[index] for index in (1, 2, 3, 4)) != normalized_prices
            or tuple(raw[index] for index in (5, 7, 9, 10)) != normalized_volumes
            or any(value <= 0 or not value.is_finite() for value in (opening, high, low, close))
            or any(value < 0 or not value.is_finite() for value in volumes)
            or high < max(opening, close)
            or low > min(opening, close)
            or closed != opened + timedelta(hours=4) - timedelta(milliseconds=1)
            or (previous_open is not None and opened != previous_open + timedelta(hours=4))
            or opened + timedelta(hours=4) > captured
        ):
            _invalid_rows()
        normalized = {
            **_ROW_DESCRIPTOR,
            "open_time": utc_datetime(opened),
            "close_time": utc_datetime(closed),
            "available_at": utc_datetime(opened + timedelta(hours=4)),
            "open": normalized_prices[0],
            "high": normalized_prices[1],
            "low": normalized_prices[2],
            "close": normalized_prices[3],
        }
        normalized["source_row_hash"] = business_hash(normalized)
        rows.append(normalized)
        previous_open = opened
    if rows[-1]["close_time"] != utc_datetime(scheduled - timedelta(milliseconds=1)):
        _invalid_rows()
    return rows


def _invalid_attempt():
    raise ChallengerReplacementLiveInputError(
        "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ATTEMPT_INVALID"
    )


def _invalid_rows():
    raise ChallengerReplacementLiveInputError(
        "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_ROWS_INVALID"
    )


def _invalid_slot():
    raise ChallengerReplacementLiveInputError(
        "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SLOT_INVALID"
    )


def _invalid_clock():
    raise ChallengerReplacementLiveInputError(
        "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_CLOCK_INVALID"
    )


def _lowerhex(value, length):
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, init=False)
class ChallengerReplacementLiveCapture:
    """Adapter-derived bytes which may enter the cohort runtime."""

    _document: Mapping[str, Any]
    _canonical_bytes: bytes

    def __init__(self, *, _token, document, canonical_bytes):
        if _token is not _CAPABILITY_TOKEN:
            raise TypeError("live capture capability is adapter-derived")
        object.__setattr__(self, "_document", deepcopy(dict(document)))
        object.__setattr__(self, "_canonical_bytes", bytes(canonical_bytes))

    @property
    def document(self):
        return deepcopy(dict(self._document))

    @property
    def canonical_bytes(self):
        return bytes(self._canonical_bytes)
