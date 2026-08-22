"""Strict live-input boundary for the replacement Challenger."""

import base64
import hashlib
import json
import os
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .challenger_replacement_plan_v2 import challenger_replacement_plan_v2_reasons
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes as _strict_mapping_bytes,
)
from .evidence import artifact_self_hash
from .errors import CanonicalizationError
from .runtime_health import server_time_probe_reasons, server_time_probe_trust_hash
from .runtime_health import (
    PublicServerTimeHttpResponse,
    RuntimeHealthError,
    build_server_time_probe,
)

_CAPABILITY_TOKEN = object()
_CAPTURE_SCHEMA = "./challenger-replacement-live-capture-v1.schema.json"
_QUALIFICATION = "REPLACEMENT_CONFIRMATORY_COHORT_INPUT"
_MAX_CAPTURE_BYTES = 2 * 1024 * 1024
_MAX_RESPONSE_BYTES = 256 * 1024
_BUILD_KEYS = {"release_tag", "peeled_commit", "package_version", "manifest_version", "build_input_tree_hash", "manifest_hash", "manifest_file_sha256"}
_SLOT_KEYS = {"slot_id", "sequence", "scheduled_for", "captured_at"}
_AUTHORITY_KEYS = {"network_request_count", "credentials_allowed", "account_requests_allowed", "broker_requests_allowed", "orders_allowed"}
_REQUEST_KEYS = {"request_id", "method", "url", "symbol", "interval", "limit", "end_time_ms"}
_ATTEMPT_KEYS = {"sequence", "outcome", "error_reason_or_null", "request_started_at", "response_received_at", "status", "final_url", "selected_headers", "body_size_bytes", "body_sha256", "response_body_base64"}
_HEADER_KEYS = {"http_date_or_null", "etag_or_null", "last_modified_or_null", "retry_after_or_null"}
_ROW_DESCRIPTOR = {
    "provider": "BINANCE_PUBLIC_DATA",
    "market": "SPOT",
    "data_family": "KLINES",
    "symbol": "ETHUSDT",
    "interval": "4h",
}
_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
_TIME_URL = "https://data-api.binance.vision/api/v3/time"
_CAPTURE_OPEN = timedelta(minutes=2)
_CAPTURE_CLOSE = timedelta(minutes=10)
_HTTP_TIMEOUT_SECONDS = 15
_FORBIDDEN_ENVIRONMENT_FRAGMENTS = {
    "proxy",
    "credential",
    "api_key",
    "secret",
    "token",
    "authorization",
    "cookie",
    "binance_key",
    "binance_secret",
}

class ChallengerReplacementLiveInputError(ValueError):
    """The replacement live-input boundary failed closed."""

    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code

class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_REDIRECT_FORBIDDEN"
        )

@dataclass(frozen=True)
class _PublicKlineHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    request_started_at: str
    response_received_at: str

def _wall_now():
    return datetime.now(timezone.utc)

def _monotonic():
    return time.monotonic_ns()

def _sleep(seconds):
    time.sleep(seconds)

def _open_public_request(request):
    if not isinstance(request, Request) or request.get_method() != "GET":
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_REQUEST_INVALID"
        )
    opener = build_opener(ProxyHandler({}), _RejectRedirects())
    started = _wall_now()
    monotonic_started = _monotonic()
    try:
        with opener.open(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            status = response.getcode()
            final_url = response.geturl()
            headers = dict(response.headers.items())
    except HTTPError as error:
        status = error.code
        final_url = error.geturl()
        headers = dict(error.headers.items()) if error.headers else {}
        body = error.read(_MAX_RESPONSE_BYTES + 1)
    except ChallengerReplacementLiveInputError:
        raise
    except (OSError, TimeoutError, URLError) as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE"
        ) from error
    received = _wall_now()
    monotonic_received = _monotonic()
    if (
        len(body) > _MAX_RESPONSE_BYTES
        or monotonic_received < monotonic_started
        or received < started
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_RESPONSE_INVALID"
        )
    common = {
        "status": status,
        "final_url": final_url,
        "headers": headers,
        "body": body,
        "request_started_at": utc_datetime(started),
        "response_received_at": utc_datetime(received),
    }
    if request.full_url == _TIME_URL:
        return PublicServerTimeHttpResponse(
            **common,
            monotonic_rtt_ms=(monotonic_received - monotonic_started + 999_999)
            // 1_000_000,
        )
    return _PublicKlineHttpResponse(**common)

class _LiveTimeTransport:
    def get(self):
        response = _open_public_request(
            Request(
                _TIME_URL,
                method="GET",
                headers={"Accept": "application/json"},
            )
        )
        if response.status in _TRANSIENT_STATUS:
            raise ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE"
            )
        try:
            headers = {key.lower(): value for key, value in response.headers.items()}
            content_type = headers.get("content-type")
        except (AttributeError, TypeError, ValueError) as error:
            raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID") from error
        if (
            not isinstance(content_type, str)
            or content_type.split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID")
        return response

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

def acquire_challenger_replacement_live_capture(*, state):
    """Acquire one fixed public ETH 4h input for the next natural slot."""

    from .challenger_replacement_runtime import ChallengerReplacementRuntimeState

    if not isinstance(state, ChallengerReplacementRuntimeState):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_STATE_INVALID"
        )
    if any(
        fragment in name.lower()
        for name in os.environ
        for fragment in _FORBIDDEN_ENVIRONMENT_FRAGMENTS
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_ENVIRONMENT_FORBIDDEN"
        )
    projection = state._replay()
    if projection.get("failed_slot_count"):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_STREAM_FAILED"
        )
    if projection.get("active_slot_id") is not None:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_ACTIVE_SLOT_REQUIRES_RESUME"
        )
    next_required = projection.get("next_required_slot")
    if not isinstance(next_required, Mapping):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_STREAM_TERMINAL"
        )
    scheduled_text = next_required.get("scheduled_for")
    if scheduled_text is not None:
        try:
            scheduled = _utc_millis(scheduled_text)
            local_now = _wall_now().astimezone(timezone.utc)
        except (AttributeError, TypeError, ValueError) as error:
            raise ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_STATE_INVALID"
            ) from error
        latest_boundary = local_now.replace(
            hour=(local_now.hour // 4) * 4,
            minute=0,
            second=0,
            microsecond=0,
        )
        if scheduled < latest_boundary:
            raise ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_CONTINUITY_GAP"
            )
        if not scheduled + _CAPTURE_OPEN <= local_now <= scheduled + _CAPTURE_CLOSE:
            raise ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_WINDOW_INVALID"
            )
    try:
        probe = build_server_time_probe(transport=_LiveTimeTransport())
        trust_hash = server_time_probe_trust_hash(probe)
        if server_time_probe_reasons(probe, trust_hash):
            raise RuntimeHealthError("clock probe replay failed")
        trusted = _utc_millis(probe["trusted_completed_at_or_null"])
    except ChallengerReplacementLiveInputError:
        raise
    except (RuntimeHealthError, TypeError, ValueError) as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_CLOCK_INVALID"
        ) from error
    sequence = next_required.get("sequence")
    if scheduled_text is None:
        scheduled = trusted.replace(
            hour=(trusted.hour // 4) * 4,
            minute=0,
            second=0,
            microsecond=0,
        )
        scheduled_text = utc_datetime(scheduled)
    else:
        try:
            scheduled = _utc_millis(scheduled_text)
        except (TypeError, ValueError) as error:
            raise ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_STATE_INVALID"
            ) from error
    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or not 1 <= sequence <= 2**53 - 1
        or not scheduled + _CAPTURE_OPEN <= trusted <= scheduled + _CAPTURE_CLOSE
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_WINDOW_INVALID"
        )
    end_time_ms = int(scheduled.timestamp() * 1000) - 1
    request_identity = {
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
    request_document = {
        "request_id": stable_id(
            "challenger_replacement_kline_request", request_identity
        ),
        **request_identity,
    }
    attempts = []
    selected_index = None
    for index in range(3):
        transport_started = _wall_now()
        try:
            response = _open_public_request(
                Request(
                    request_identity["url"],
                    method="GET",
                    headers={"Accept": "application/json"},
                )
            )
        except ChallengerReplacementLiveInputError as error:
            if error.reason_code != "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE":
                raise
            attempts.append(
                _transport_attempt_document(
                    index + 1,
                    started=transport_started,
                    received=_wall_now(),
                )
            )
            if index < 2:
                _sleep(index + 1)
                continue
            break
        attempt = _attempt_document(response, index + 1)
        attempts.append(attempt)
        if response.status == 200:
            selected_index = index
            break
        if response.status not in _TRANSIENT_STATUS:
            raise ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_RESPONSE_INVALID"
            )
        if index < 2:
            _sleep(index + 1)
    if selected_index is None:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_RETRIES_EXHAUSTED"
        )
    captured = _utc_millis(attempts[selected_index]["response_received_at"])
    try:
        payload = _strict_response_json(
            base64.b64decode(attempts[selected_index]["response_body_base64"], validate=True)
        )
        rows = _normalize_kline_payload(
            payload, scheduled=scheduled, captured=captured
        )
    except ChallengerReplacementLiveInputError as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_JSON_INVALID"
        ) from error
    slot = {
        "slot_id": stable_id(
            "challenger_replacement_slot",
            {"plan_hash": state.plan["plan_hash"], "scheduled_for": scheduled_text},
        ),
        "sequence": sequence,
        "scheduled_for": scheduled_text,
        "captured_at": utc_datetime(captured),
    }
    document = _build_live_capture_document(
        plan=state.plan,
        build_identity=state.build_identity,
        slot=slot,
        clock_records={"probe": probe, "trust_hash": trust_hash},
        kline_request=request_document,
        attempts=attempts,
        selected_attempt_index=selected_index,
        rows=rows,
    )
    canonical_bytes = canonical_json(document).encode("utf-8")
    loaded = load_challenger_replacement_live_capture_bytes(
        canonical_bytes,
        plan=state.plan,
        build_identity=state.build_identity,
        previous_source_bundle=projection.get("_previous_source_bundle"),
    )
    return _grant_live_capture(
        document=loaded,
        canonical_bytes=canonical_bytes,
        token=_CAPABILITY_TOKEN,
    )

def _attempt_document(response, sequence):
    try:
        headers = {key.lower(): value for key, value in response.headers.items()}
        body = bytes(response.body)
    except (AttributeError, TypeError, ValueError) as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_RESPONSE_INVALID"
        ) from error
    content_type = headers.get("content-type")
    if response.status == 200 and (
        not isinstance(content_type, str)
        or content_type.split(";", 1)[0].strip().lower() != "application/json"
    ):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_RESPONSE_INVALID"
        )
    return {
        "sequence": sequence,
        "outcome": "HTTP_RESPONSE",
        "error_reason_or_null": None,
        "request_started_at": response.request_started_at,
        "response_received_at": response.response_received_at,
        "status": response.status,
        "final_url": response.final_url,
        "selected_headers": {
            "http_date_or_null": headers.get("date"),
            "etag_or_null": headers.get("etag"),
            "last_modified_or_null": headers.get("last-modified"),
            "retry_after_or_null": headers.get("retry-after"),
        },
        "body_size_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "response_body_base64": base64.b64encode(body).decode("ascii"),
    }

def _transport_attempt_document(sequence, *, started, received):
    try:
        started_text = utc_datetime(started)
        received_text = utc_datetime(received)
    except (AttributeError, TypeError, ValueError) as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_INPUT_CLOCK_INVALID"
        ) from error
    return {
        "sequence": sequence,
        "outcome": "TRANSPORT_ERROR",
        "error_reason_or_null": "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE",
        "request_started_at": started_text,
        "response_received_at": received_text,
        "status": None,
        "final_url": None,
        "selected_headers": {
            "http_date_or_null": None,
            "etag_or_null": None,
            "last_modified_or_null": None,
            "retry_after_or_null": None,
        },
        "body_size_bytes": 0,
        "body_sha256": hashlib.sha256(b"").hexdigest(),
        "response_body_base64": "",
    }

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

    try:
        return _strict_mapping_bytes(data)
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
        ) from error

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
            body = base64.b64decode(attempt["response_body_base64"], validate=True)
        except (AttributeError, TypeError, ValueError):
            _invalid_attempt()
        headers = attempt["selected_headers"]
        status = attempt["status"]
        if (
            attempt["sequence"] != index + 1
            or not isinstance(headers, Mapping)
            or set(headers) != _HEADER_KEYS
            or any(value is not None and not isinstance(value, str) for value in headers.values())
            or not previous_received <= started <= received <= captured
            or len(body) > _MAX_RESPONSE_BYTES
            or attempt["body_size_bytes"] != len(body)
            or attempt["body_sha256"] != hashlib.sha256(body).hexdigest()
            or attempt["response_body_base64"] != base64.b64encode(body).decode("ascii")
        ):
            _invalid_attempt()
        if attempt["outcome"] == "TRANSPORT_ERROR":
            if (
                index >= selected
                or attempt["error_reason_or_null"]
                != "CHALLENGER_REPLACEMENT_LIVE_INPUT_TRANSPORT_FAILURE"
                or status is not None
                or attempt["final_url"] is not None
                or any(value is not None for value in headers.values())
                or body
            ):
                _invalid_attempt()
        elif attempt["outcome"] == "HTTP_RESPONSE":
            if (
                attempt["error_reason_or_null"] is not None
                or not isinstance(status, int)
                or isinstance(status, bool)
                or attempt["final_url"] != request["url"]
                or (index == selected and not body)
                or (index < selected and status not in _TRANSIENT_STATUS)
                or (index == selected and status != 200)
            ):
                _invalid_attempt()
        else:
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
    try:
        value = _strict_mapping_bytes(b'{"rows":' + data + b"}")["rows"]
    except (ChallengerReplacementPlanError, KeyError, TypeError):
        _invalid_rows()
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

def _invalid(suffix):
    raise ChallengerReplacementLiveInputError(
        "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_" + suffix + "_INVALID")

def _invalid_attempt(): _invalid("ATTEMPT")
def _invalid_rows(): _invalid("ROWS")
def _invalid_slot(): _invalid("SLOT")
def _invalid_clock(): _invalid("CLOCK")

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
