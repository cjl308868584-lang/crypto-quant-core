"""Public-only live input runner for the preregistered challenger."""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .challenger_forward import (
    ChallengerForwardError,
    ChallengerForwardState,
    build_challenger_forward_decision,
    challenger_decision_reasons,
    challenger_forward_policy,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes
from .runtime_health import (
    VerifiedRuntimeGate,
    open_verified_runtime_gate,
    server_time_probe_reasons,
    server_time_probe_trust_hash,
)


_SCHEMA = "challenger-forward-source-bundle-v1.schema.json"
_BASE_URL = "https://data-api.binance.vision"
_HOST = "data-api.binance.vision"
_PATH = "/api/v3/klines"
_START = datetime(2026, 7, 29, tzinfo=timezone.utc)
_FOUR_HOURS = timedelta(hours=4)
_ONE_MILLISECOND = timedelta(milliseconds=1)
_MAX_BODY_BYTES = 256 * 1024
_MAX_BUNDLE_BYTES = 2 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_HTTP_TIMEOUT_SECONDS = 15
_REQUEST_TOKEN = object()
_WARNINGS = (
    "BINANCE_TIME_RECEIPT_IS_NOT_INDEPENDENT_PUBLICATION",
    "UNANCHORED_LOCAL_PREQUENTIAL_ONLY",
    "NO_HISTORICAL_BACKFILL",
    "NO_OUTCOME_OR_PROFITABILITY_CLAIM",
    "NO_BROKER_OR_ORDER_AUTHORITY",
)


class ChallengerForwardRunnerError(ValueError):
    """The trusted clock, public input, bundle, or runner failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerForwardRunnerError(
                "CHALLENGER_RUNNER_TIME_INVALID"
            ) from error
    else:
        raise ChallengerForwardRunnerError("CHALLENGER_RUNNER_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerForwardRunnerError("CHALLENGER_RUNNER_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerForwardRunnerError("CHALLENGER_RUNNER_TIME_INVALID")
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerForwardRunnerError("CHALLENGER_RUNNER_TIME_INVALID")
    return converted, rendered


def _epoch_ms(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return int((value - epoch) // timedelta(milliseconds=1))


def _from_epoch_ms(value: object) -> Tuple[datetime, str]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_INVALID"
        )
    try:
        parsed = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            milliseconds=value
        )
    except (OverflowError, ValueError) as error:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_INVALID"
        ) from error
    return parsed, utc_datetime(parsed)


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_INVALID"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_INVALID"
        ) from error
    if (
        not parsed.is_finite()
        or (positive and parsed <= 0)
        or (parsed.is_zero() and parsed.is_signed())
    ):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_INVALID"
        )
    return parsed


def _strict_json(body: bytes) -> Any:
    if not isinstance(body, bytes) or len(body) > _MAX_BODY_BYTES:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_RESPONSE_TOO_LARGE"
        )

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ChallengerForwardRunnerError(
                    "CHALLENGER_RUNNER_JSON_INVALID"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_JSON_INVALID"
        )

    try:
        return json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except ChallengerForwardRunnerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_JSON_INVALID"
        ) from error


@dataclass(frozen=True, init=False)
class ChallengerKlineRequest:
    scheduled_for: str
    request_id: str
    method: str
    url: str

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _REQUEST_TOKEN:
            raise TypeError("ChallengerKlineRequest must be derived internally")
        for name in ("scheduled_for", "request_id", "method", "url"):
            object.__setattr__(self, name, kwargs[name])


@dataclass(frozen=True)
class ChallengerKlineHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    request_started_at: str
    response_received_at: str


def challenger_kline_request(scheduled_for: object) -> ChallengerKlineRequest:
    scheduled, scheduled_text = _utc(scheduled_for)
    if (
        scheduled < _START
        or scheduled.minute
        or scheduled.second
        or scheduled.microsecond
        or scheduled.hour % 4
    ):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_SLOT_INVALID"
        )
    query = {
        "endTime": str(_epoch_ms(scheduled) - 1),
        "interval": "4h",
        "limit": "21",
        "symbol": "ETHUSDT",
    }
    url = _BASE_URL + _PATH + "?" + urlencode(sorted(query.items()))
    identity = {
        "scheduled_for": scheduled_text,
        "method": "GET",
        "url": url,
    }
    return ChallengerKlineRequest(
        scheduled_for=scheduled_text,
        request_id=stable_id("challenger_kline_request", identity),
        method="GET",
        url=url,
        _token=_REQUEST_TOKEN,
    )


def _valid_request_url(value: object, expected: str) -> bool:
    if not isinstance(value, str) or value != expected:
        return False
    try:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname == _HOST
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and parsed.path == _PATH
            and not parsed.fragment
        )
    except ValueError:
        return False


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_REDIRECT_INVALID"
        )


def _read_bounded(response: object) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = response.read(
            min(_READ_CHUNK_BYTES, _MAX_BODY_BYTES - total + 1)
        )
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_BODY_BYTES:
            raise ChallengerForwardRunnerError(
                "CHALLENGER_RUNNER_RESPONSE_TOO_LARGE"
            )
        chunks.append(chunk)
    return b"".join(chunks)


class BinanceChallengerKlineTransport:
    """One-attempt, proxy-free transport for a derived public Kline request."""

    def __init__(self, *, clock=None, opener=None):
        self._clock = clock or (
            lambda: utc_datetime(datetime.now(timezone.utc))
        )
        self._opener = opener or build_opener(
            ProxyHandler({}), _NoRedirectHandler()
        )
        self.calls = 0

    def get(
        self, request: ChallengerKlineRequest
    ) -> ChallengerKlineHttpResponse:
        try:
            expected = challenger_kline_request(request.scheduled_for)
        except (AttributeError, ChallengerForwardRunnerError):
            expected = None
        if (
            not isinstance(request, ChallengerKlineRequest)
            or request != expected
            or not _valid_request_url(request.url, request.url)
        ):
            raise ChallengerForwardRunnerError(
                "CHALLENGER_RUNNER_REQUEST_INVALID"
            )
        self.calls += 1
        started = self._clock()
        try:
            with self._opener.open(
                Request(request.url, method="GET"),
                timeout=_HTTP_TIMEOUT_SECONDS,
            ) as response:
                return ChallengerKlineHttpResponse(
                    status=response.getcode(),
                    final_url=response.geturl(),
                    headers=dict(response.headers.items()),
                    body=_read_bounded(response),
                    request_started_at=started,
                    response_received_at=self._clock(),
                )
        except HTTPError as error:
            return ChallengerKlineHttpResponse(
                status=error.code,
                final_url=error.geturl(),
                headers=dict(error.headers.items()) if error.headers else {},
                body=b"",
                request_started_at=started,
                response_received_at=self._clock(),
            )
        except ChallengerForwardRunnerError:
            raise
        except (OSError, TimeoutError, URLError) as error:
            raise ChallengerForwardRunnerError(
                "CHALLENGER_RUNNER_TRANSPORT_FAILURE"
            ) from error


def _selected_headers(headers: object) -> Dict[str, Optional[str]]:
    if not isinstance(headers, Mapping):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_RESPONSE_INVALID"
        )
    lowered = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ChallengerForwardRunnerError(
                "CHALLENGER_RUNNER_RESPONSE_INVALID"
            )
        lowered[key.lower()] = value
    return {
        "http_date_or_null": lowered.get("date"),
        "etag_or_null": lowered.get("etag"),
        "last_modified_or_null": lowered.get("last-modified"),
        "retry_after_or_null": lowered.get("retry-after"),
    }


def _receipt(
    request: ChallengerKlineRequest,
    response: ChallengerKlineHttpResponse,
    *,
    recorded_at: object,
) -> Dict[str, Any]:
    if (
        not isinstance(response, ChallengerKlineHttpResponse)
        or response.status != 200
        or response.final_url != request.url
        or not _valid_request_url(response.final_url, request.url)
        or not isinstance(response.body, bytes)
        or len(response.body) > _MAX_BODY_BYTES
    ):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_RESPONSE_INVALID"
        )
    scheduled, _ = _utc(request.scheduled_for)
    started, started_text = _utc(response.request_started_at)
    received, received_text = _utc(response.response_received_at)
    recorded, recorded_text = _utc(recorded_at)
    if (
        started < scheduled
        or received < started
        or recorded < received
        or recorded >= scheduled + _FOUR_HOURS
    ):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_CLOCK_INVALID"
        )
    _strict_json(response.body)
    try:
        body_text = response.body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_JSON_INVALID"
        ) from error
    receipt = {
        "request_id": request.request_id,
        "scheduled_for": request.scheduled_for,
        "method": request.method,
        "url": request.url,
        "status": response.status,
        "final_url": response.final_url,
        "selected_headers": _selected_headers(response.headers),
        "request_started_at": started_text,
        "response_received_at": received_text,
        "recorded_at": recorded_text,
        "body_size_bytes": len(response.body),
        "body_sha256": hashlib.sha256(response.body).hexdigest(),
        "response_body_utf8": body_text,
        "receipt_hash": "0" * 64,
    }
    receipt["receipt_hash"] = artifact_self_hash(
        receipt, "receipt_hash"
    )
    return receipt


def _normalized_raw_row(
    raw: object,
    *,
    expected_open: datetime,
    available_at: str,
) -> Dict[str, Any]:
    if (
        not isinstance(raw, list)
        or len(raw) != 12
        or isinstance(raw[0], bool)
        or not isinstance(raw[0], int)
        or isinstance(raw[6], bool)
        or not isinstance(raw[6], int)
        or isinstance(raw[8], bool)
        or not isinstance(raw[8], int)
        or raw[8] < 0
        or raw[11] != "0"
    ):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_INVALID"
        )
    opened, opened_text = _from_epoch_ms(raw[0])
    closed, closed_text = _from_epoch_ms(raw[6])
    if (
        opened != expected_open
        or closed != opened + _FOUR_HOURS - _ONE_MILLISECOND
    ):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_INVALID"
        )
    opening = _decimal(raw[1], positive=True)
    high = _decimal(raw[2], positive=True)
    low = _decimal(raw[3], positive=True)
    close = _decimal(raw[4], positive=True)
    for index in (5, 7, 9, 10):
        if _decimal(raw[index]) < 0:
            raise ChallengerForwardRunnerError(
                "CHALLENGER_RUNNER_KLINE_INVALID"
            )
    if (
        high < max(opening, close)
        or low > min(opening, close)
        or low > high
    ):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_INVALID"
        )
    return {
        "provider": "BINANCE_PUBLIC_DATA",
        "market": "SPOT",
        "data_family": "KLINES",
        "symbol": "ETHUSDT",
        "interval": "4h",
        "open_time": opened_text,
        "close_time": closed_text,
        "available_at": available_at,
        "open": canonical_decimal(opening),
        "high": canonical_decimal(high),
        "low": canonical_decimal(low),
        "close": canonical_decimal(close),
        "source_row_hash": business_hash(raw),
    }


def _parse_klines(
    *,
    body: bytes,
    scheduled_for: str,
    response_received_at: str,
    previous_decision: Optional[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    payload = _strict_json(body)
    if not isinstance(payload, list) or len(payload) != 21:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_COUNT_INVALID"
        )
    scheduled, _ = _utc(scheduled_for)
    received, received_text = _utc(response_received_at)
    if received < scheduled:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_CLOCK_INVALID"
        )
    first_open = scheduled - 21 * _FOUR_HOURS
    parsed = tuple(
        _normalized_raw_row(
            raw,
            expected_open=first_open + index * _FOUR_HOURS,
            available_at=received_text,
        )
        for index, raw in enumerate(payload)
    )
    if _utc(parsed[-1]["close_time"])[0] != scheduled - _ONE_MILLISECOND:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_KLINE_WINDOW_INVALID"
        )
    if previous_decision is None:
        return parsed
    try:
        previous_rows = previous_decision["input_klines"][1:]
    except (KeyError, TypeError) as error:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_PREVIOUS_INVALID"
        ) from error
    if len(previous_rows) != 20:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_PREVIOUS_INVALID"
        )
    for current, previous in zip(parsed[:-1], previous_rows):
        comparison = dict(current)
        comparison["available_at"] = previous.get("available_at")
        if comparison != previous:
            raise ChallengerForwardRunnerError(
                "CHALLENGER_RUNNER_KLINE_REVISION"
            )
    return tuple(dict(row) for row in previous_rows) + (parsed[-1],)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def challenger_source_bundle_hash(bundle: Mapping[str, Any]) -> str:
    return artifact_self_hash(bundle, "bundle_hash")


def build_challenger_source_bundle(
    *,
    runtime_probe: Mapping[str, Any],
    kline_receipt: Mapping[str, Any],
    klines: Sequence[Mapping[str, Any]],
    candidate_decision: Mapping[str, Any],
    previous_decision: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    trust_hash = server_time_probe_trust_hash(runtime_probe)
    identity = {
        "runtime_probe_hash": runtime_probe.get("probe_hash"),
        "kline_receipt_hash": kline_receipt.get("receipt_hash"),
        "decision_hash": candidate_decision.get("decision_hash"),
    }
    bundle = {
        "$schema": "./challenger-forward-source-bundle-v1.schema.json",
        "schema_version": "1.0.0",
        "bundle_id": stable_id("challenger_forward_source_bundle", identity),
        "bundle_hash": "0" * 64,
        "recorded_at": candidate_decision.get("recorded_at"),
        "scheduled_for": candidate_decision.get("scheduled_for"),
        "runtime_probe": dict(runtime_probe),
        "runtime_probe_trust_hash": trust_hash,
        "kline_receipt": dict(kline_receipt),
        "klines": [dict(row) for row in klines],
        "candidate_decision": dict(candidate_decision),
        "previous_decision_or_null": (
            dict(previous_decision)
            if previous_decision is not None
            else None
        ),
        "policy_hash": challenger_forward_policy()["policy_hash"],
        "hypothesis_registration_hash": challenger_forward_policy()[
            "hypothesis_registration_hash"
        ],
        "time_anchor_status": "BINANCE_SERVER_TIME_RECEIPT_LOCAL_ONLY",
        "forward_evidence_eligibility": (
            "UNANCHORED_LOCAL_PREQUENTIAL_ONLY"
        ),
        "broker_eligibility": "INELIGIBLE_NO_BROKER_ACCESS",
        "warnings": list(_WARNINGS),
    }
    bundle["bundle_hash"] = challenger_source_bundle_hash(bundle)
    if tuple(_validator().iter_errors(bundle)):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_BUNDLE_SCHEMA_INVALID"
        )
    return bundle


def _response_from_receipt(
    receipt: Mapping[str, Any],
) -> ChallengerKlineHttpResponse:
    selected = receipt.get("selected_headers", {})
    header_map = {
        "http_date_or_null": "Date",
        "etag_or_null": "ETag",
        "last_modified_or_null": "Last-Modified",
        "retry_after_or_null": "Retry-After",
    }
    headers = {
        target: selected[source]
        for source, target in header_map.items()
        if selected.get(source) is not None
    }
    return ChallengerKlineHttpResponse(
        status=receipt.get("status"),
        final_url=receipt.get("final_url"),
        headers=headers,
        body=receipt.get("response_body_utf8", "").encode("utf-8"),
        request_started_at=receipt.get("request_started_at"),
        response_received_at=receipt.get("response_received_at"),
    )


def challenger_source_bundle_reasons(
    bundle: Mapping[str, Any],
) -> Tuple[str, ...]:
    if not isinstance(bundle, Mapping):
        return ("CHALLENGER_RUNNER_BUNDLE_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(bundle)):
            reasons.append("CHALLENGER_RUNNER_BUNDLE_SCHEMA_INVALID")
        if bundle.get("bundle_hash") != challenger_source_bundle_hash(bundle):
            reasons.append("CHALLENGER_RUNNER_BUNDLE_HASH_MISMATCH")
        probe = bundle["runtime_probe"]
        trust_hash = server_time_probe_trust_hash(probe)
        if bundle["runtime_probe_trust_hash"] != trust_hash:
            reasons.append("CHALLENGER_RUNNER_PROBE_BINDING_MISMATCH")
        if server_time_probe_reasons(probe, trust_hash):
            reasons.append("CHALLENGER_RUNNER_PROBE_INVALID")
        receipt = bundle["kline_receipt"]
        request = challenger_kline_request(bundle["scheduled_for"])
        expected_receipt = _receipt(
            request,
            _response_from_receipt(receipt),
            recorded_at=bundle["recorded_at"],
        )
        if expected_receipt != receipt:
            reasons.append("CHALLENGER_RUNNER_RECEIPT_REPLAY_MISMATCH")
        previous = bundle["previous_decision_or_null"]
        klines = _parse_klines(
            body=expected_receipt["response_body_utf8"].encode("utf-8"),
            scheduled_for=bundle["scheduled_for"],
            response_received_at=expected_receipt["response_received_at"],
            previous_decision=previous,
        )
        if list(klines) != bundle["klines"]:
            reasons.append("CHALLENGER_RUNNER_KLINE_REPLAY_MISMATCH")
        candidate = build_challenger_forward_decision(
            klines=klines,
            scheduled_for=bundle["scheduled_for"],
            recorded_at=bundle["recorded_at"],
            previous_decision=previous,
        )
        if (
            challenger_decision_reasons(
                bundle["candidate_decision"],
                previous_decision=previous,
            )
            or candidate != bundle["candidate_decision"]
        ):
            reasons.append("CHALLENGER_RUNNER_DECISION_REPLAY_MISMATCH")
        policy = challenger_forward_policy()
        if (
            bundle["policy_hash"] != policy["policy_hash"]
            or bundle["hypothesis_registration_hash"]
            != policy["hypothesis_registration_hash"]
        ):
            reasons.append("CHALLENGER_RUNNER_POLICY_MISMATCH")
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        ChallengerForwardError,
        ChallengerForwardRunnerError,
    ):
        reasons.append("CHALLENGER_RUNNER_BUNDLE_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def publish_challenger_source_bundle(
    *,
    bundle: Mapping[str, Any],
    output_root: Path,
) -> Path:
    if challenger_source_bundle_reasons(bundle):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_BUNDLE_INVALID"
        )
    requested = Path(output_root).expanduser()
    if requested.is_symlink():
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_OUTPUT_INVALID"
        )
    root = requested.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    directory = root / "challenger-forward" / "source-bundles"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory.parent, 0o700)
    os.chmod(directory, 0o700)
    path = directory / f"{bundle['bundle_id']}.json"
    try:
        _publish_exact(path, canonical_json(bundle).encode("utf-8"))
    except ValueError as error:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_BUNDLE_PUBLISH_CONFLICT"
        ) from error
    return path


def load_challenger_source_bundle(path: Path) -> Mapping[str, Any]:
    try:
        resolved = Path(path).expanduser().resolve()
        if resolved.stat().st_size > _MAX_BUNDLE_BYTES:
            raise ChallengerForwardRunnerError(
                "CHALLENGER_RUNNER_BUNDLE_READ_FAILED"
            )
        bundle = _strict_json_bytes(resolved.read_bytes())
    except (OSError, ValueError) as error:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_BUNDLE_READ_FAILED"
        ) from error
    if challenger_source_bundle_reasons(bundle):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_BUNDLE_INVALID"
        )
    return bundle


def _current_slot(value: object) -> Tuple[datetime, str]:
    current, _ = _utc(value)
    slot = current.replace(
        hour=current.hour - current.hour % 4,
        minute=0,
        second=0,
        microsecond=0,
    )
    return slot, utc_datetime(slot)


def run_challenger_forward_cycle(
    *,
    state_path: Path,
    output_root: Path,
    server_time_transport=None,
    kline_transport=None,
    runtime_gate: Optional[VerifiedRuntimeGate] = None,
) -> Mapping[str, Any]:
    if runtime_gate is not None and server_time_transport is not None:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_DEPENDENCY_INVALID"
        )
    try:
        gate = runtime_gate or open_verified_runtime_gate(
            server_time_transport=server_time_transport
        )
    except (TypeError, ValueError) as error:
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_CLOCK_BLOCKED"
        ) from error
    if not isinstance(gate, VerifiedRuntimeGate):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_CLOCK_INVALID"
        )
    trust_hash = server_time_probe_trust_hash(gate.probe)
    if server_time_probe_reasons(gate.probe, trust_hash):
        raise ChallengerForwardRunnerError(
            "CHALLENGER_RUNNER_CLOCK_INVALID"
        )
    now, current_slot_text = _current_slot(gate.clock())
    try:
        with ChallengerForwardState(Path(state_path)) as state:
            decisions = state.replay()
            previous = decisions[-1] if decisions else None
            next_slot = (
                _START
                if previous is None
                else _utc(previous["scheduled_for"])[0] + _FOUR_HOURS
            )
            next_slot_text = utc_datetime(next_slot)
            if now < next_slot:
                return {
                    "status": "NOT_DUE",
                    "current_slot": current_slot_text,
                    "next_required_slot": next_slot_text,
                    "decision_count": len(decisions),
                    "server_time_request_count": gate.probe_request_count,
                    "kline_request_count": 0,
                    "broker_request_count": 0,
                    "order_submission_count": 0,
                }
            if now > next_slot:
                raise ChallengerForwardRunnerError(
                    "CHALLENGER_RUNNER_MISSED_SLOT"
                )
            request = challenger_kline_request(next_slot_text)
            selected_transport = (
                kline_transport
                or BinanceChallengerKlineTransport(clock=gate.clock)
            )
            if not hasattr(selected_transport, "get"):
                raise ChallengerForwardRunnerError(
                    "CHALLENGER_RUNNER_TRANSPORT_INVALID"
                )
            try:
                response = selected_transport.get(request)
            except ChallengerForwardRunnerError:
                raise
            except Exception as error:
                raise ChallengerForwardRunnerError(
                    "CHALLENGER_RUNNER_TRANSPORT_FAILURE"
                ) from error
            recorded_at = gate.clock()
            receipt = _receipt(
                request,
                response,
                recorded_at=recorded_at,
            )
            klines = _parse_klines(
                body=response.body,
                scheduled_for=next_slot_text,
                response_received_at=receipt["response_received_at"],
                previous_decision=previous,
            )
            candidate = build_challenger_forward_decision(
                klines=klines,
                scheduled_for=next_slot_text,
                recorded_at=recorded_at,
                previous_decision=previous,
            )
            bundle = build_challenger_source_bundle(
                runtime_probe=gate.probe,
                kline_receipt=receipt,
                klines=klines,
                candidate_decision=candidate,
                previous_decision=previous,
            )
            bundle_path = publish_challenger_source_bundle(
                bundle=bundle,
                output_root=Path(output_root),
            )
            stored = state.append(
                klines=klines,
                scheduled_for=next_slot_text,
                recorded_at=recorded_at,
            )
            if stored != candidate:
                raise ChallengerForwardRunnerError(
                    "CHALLENGER_RUNNER_STATE_COMMIT_MISMATCH"
                )
    except ChallengerForwardRunnerError:
        raise
    except ChallengerForwardError as error:
        raise ChallengerForwardRunnerError(error.reason_code) from error
    return {
        "status": "RECORDED",
        "current_slot": current_slot_text,
        "next_required_slot": utc_datetime(next_slot + _FOUR_HOURS),
        "decision_count": candidate["sequence"],
        "decision_id": candidate["decision_id"],
        "decision_hash": candidate["decision_hash"],
        "source_bundle_path": str(bundle_path),
        "source_bundle_hash": bundle["bundle_hash"],
        "server_time_request_count": gate.probe_request_count,
        "kline_request_count": 1,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "forward_evidence_eligibility": (
            "UNANCHORED_LOCAL_PREQUENTIAL_ONLY"
        ),
    }
