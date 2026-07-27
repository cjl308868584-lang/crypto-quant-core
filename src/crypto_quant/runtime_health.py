"""Replayable server-time health, Paper heartbeats, and local alerts."""

import hashlib
import json
import sqlite3
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .market_data_cli import _publish_immutable
from .paper_scheduler import (
    PaperScheduleError,
    run_due_paper_cycle,
)


_POLICY_TOKEN = object()
_RUNTIME_GATE_TOKEN = object()
_GENESIS_HASH = "0" * 64
_SERVER_TIME_URL = "https://data-api.binance.vision/api/v3/time"
_SERVER_TIME_HOST = "data-api.binance.vision"
_SAMPLE_COUNT = 3
_MAX_RTT_MS = 3000
_MAX_INTERSECTION_WIDTH_MS = 1000
_ALIGNED_OFFSET_MS = 1000
_MAX_ABSOLUTE_OFFSET_MS = 5000
_HEARTBEAT_GAP_SECONDS = 15_300
_MAX_BODY_BYTES = 1024
_HTTP_TIMEOUT_SECONDS = 10
_RUNTIME_ATTESTATION_TYPE = "PAPER_RUNTIME_SNAPSHOT_ATTESTATION"
_PROBE_ATTESTATION_TYPE = "BINANCE_SERVER_TIME_PROBE_ATTESTATION"
_ALERT_CODES = frozenset(
    (
        "PAPER_CLOCK_PROBE_BLOCKED",
        "PAPER_HEARTBEAT_GAP",
        "PAPER_HEARTBEAT_CONTINUITY_UNKNOWN",
        "PAPER_SCHEDULER_FAILURE",
        "PAPER_SCHEDULER_BUSY",
    )
)
_WARNINGS = (
    "EXTERNAL_ALERT_DELIVERY_NOT_CONFIGURED",
    "OPERATING_SYSTEM_SCHEDULER_NOT_CONFIGURED",
    "ACCOUNT_FEE_SCHEDULE_UNOBSERVED",
    "PERPETUAL_CONTEXT_NOT_CAPTURED",
    "AI_MODEL_NOT_RUN",
)


class RuntimeHealthError(ValueError):
    """A clock probe, heartbeat state, or runtime Artifact failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise RuntimeHealthError("PAPER_RUNTIME_TIME_INVALID") from error
    else:
        raise RuntimeHealthError("PAPER_RUNTIME_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeHealthError("PAPER_RUNTIME_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    converted = converted.replace(
        microsecond=(converted.microsecond // 1000) * 1000
    )
    return converted, utc_datetime(converted)


def _epoch_ms(value: object) -> int:
    parsed, _ = _utc(value)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return int((parsed - epoch) // timedelta(milliseconds=1))


def _from_epoch_ms(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeHealthError("PAPER_RUNTIME_TIME_INVALID")
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        return utc_datetime(epoch + timedelta(milliseconds=value))
    except (OverflowError, ValueError) as error:
        raise RuntimeHealthError("PAPER_RUNTIME_TIME_INVALID") from error


def _utc_now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


@dataclass(frozen=True, init=False)
class RuntimeHealthPolicy:
    schema_version: str
    policy_id: str
    server_time_url: str
    sample_count: int
    max_rtt_ms: int
    max_intersection_width_ms: int
    aligned_offset_ms: int
    max_absolute_offset_ms: int
    heartbeat_gap_seconds: int

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _POLICY_TOKEN:
            raise TypeError("RuntimeHealthPolicy must be created with create")
        object.__setattr__(self, "schema_version", "1.0.0")
        object.__setattr__(
            self,
            "policy_id",
            "binance-public-time-paper-runtime-health-v1",
        )
        object.__setattr__(self, "server_time_url", _SERVER_TIME_URL)
        object.__setattr__(self, "sample_count", _SAMPLE_COUNT)
        object.__setattr__(self, "max_rtt_ms", _MAX_RTT_MS)
        object.__setattr__(
            self,
            "max_intersection_width_ms",
            _MAX_INTERSECTION_WIDTH_MS,
        )
        object.__setattr__(
            self, "aligned_offset_ms", _ALIGNED_OFFSET_MS
        )
        object.__setattr__(
            self, "max_absolute_offset_ms", _MAX_ABSOLUTE_OFFSET_MS
        )
        object.__setattr__(
            self, "heartbeat_gap_seconds", _HEARTBEAT_GAP_SECONDS
        )

    @classmethod
    def create(cls) -> "RuntimeHealthPolicy":
        return cls(_token=_POLICY_TOKEN)

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "server_time_url": self.server_time_url,
            "http_method": "GET",
            "security_type": "NONE_PUBLIC",
            "sample_count": self.sample_count,
            "automatic_retry_count": 0,
            "max_rtt_ms": self.max_rtt_ms,
            "server_timestamp_quantization_margin_ms": 1,
            "max_intersection_width_ms": self.max_intersection_width_ms,
            "aligned_offset_ms": self.aligned_offset_ms,
            "max_absolute_offset_ms": self.max_absolute_offset_ms,
            "correction_method": (
                "INTEGER_INTERSECTION_MIDPOINT_MONOTONIC_ANCHOR"
            ),
            "heartbeat_gap_seconds": self.heartbeat_gap_seconds,
            "alert_delivery": "LOCAL_ARTIFACT_ONLY",
        }

    @property
    def policy_hash(self) -> str:
        return business_hash(self.business_payload())


@dataclass(frozen=True)
class PublicServerTimeHttpResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes
    request_started_at: str
    response_received_at: str
    monotonic_rtt_ms: int


def _valid_server_time_url(value: object) -> bool:
    if value != _SERVER_TIME_URL:
        return False
    try:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and parsed.hostname == _SERVER_TIME_HOST
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and parsed.path == "/api/v3/time"
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


class _SameHostRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _valid_server_time_url(newurl):
            raise RuntimeHealthError("PAPER_CLOCK_REDIRECT_INVALID")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class BinanceServerTimeTransport:
    """Credential-free transport for one exact public server-time endpoint."""

    def __init__(
        self,
        *,
        wall_time_ns=None,
        monotonic_ns=None,
        opener=None,
    ):
        self._wall_time_ns = wall_time_ns or time.time_ns
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._opener = opener or build_opener(
            ProxyHandler({}), _SameHostRedirectHandler()
        )
        self.calls = 0

    def get(self) -> PublicServerTimeHttpResponse:
        self.calls += 1
        wall_start_ns = self._wall_time_ns()
        monotonic_start_ns = self._monotonic_ns()
        if (
            isinstance(wall_start_ns, bool)
            or not isinstance(wall_start_ns, int)
            or isinstance(monotonic_start_ns, bool)
            or not isinstance(monotonic_start_ns, int)
        ):
            raise RuntimeHealthError("PAPER_CLOCK_SOURCE_INVALID")
        try:
            request = Request(
                _SERVER_TIME_URL,
                method="GET",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "crypto-quant-runtime-health/0.20",
                },
            )
            with self._opener.open(
                request, timeout=_HTTP_TIMEOUT_SECONDS
            ) as response:
                body = response.read(_MAX_BODY_BYTES + 1)
                status = response.getcode()
                final_url = response.geturl()
                headers = dict(response.headers.items())
        except HTTPError as error:
            status = error.code
            final_url = error.geturl()
            headers = dict(error.headers.items()) if error.headers else {}
            body = b""
        except RuntimeHealthError:
            raise
        except (OSError, TimeoutError, URLError) as error:
            raise RuntimeHealthError("PAPER_CLOCK_TRANSPORT_FAILURE") from error
        monotonic_end_ns = self._monotonic_ns()
        wall_end_ns = self._wall_time_ns()
        if (
            isinstance(wall_end_ns, bool)
            or not isinstance(wall_end_ns, int)
            or isinstance(monotonic_end_ns, bool)
            or not isinstance(monotonic_end_ns, int)
            or monotonic_end_ns < monotonic_start_ns
        ):
            raise RuntimeHealthError("PAPER_CLOCK_SOURCE_INVALID")
        if len(body) > _MAX_BODY_BYTES:
            raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_TOO_LARGE")
        rtt_ms = (
            monotonic_end_ns - monotonic_start_ns + 999_999
        ) // 1_000_000
        return PublicServerTimeHttpResponse(
            status=status,
            final_url=final_url,
            headers=headers,
            body=body,
            request_started_at=_from_epoch_ms(
                wall_start_ns // 1_000_000
            ),
            response_received_at=_from_epoch_ms(
                wall_end_ns // 1_000_000
            ),
            monotonic_rtt_ms=rtt_ms,
        )


def _strict_json(body: bytes) -> Mapping[str, Any]:
    if not isinstance(body, bytes) or len(body) > _MAX_BODY_BYTES:
        raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID")

    def reject_float(_value):
        raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID")

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            body.decode("utf-8"),
            parse_float=reject_float,
            parse_constant=reject_float,
            object_pairs_hook=object_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID") from error
    if (
        not isinstance(parsed, Mapping)
        or set(parsed) != {"serverTime"}
        or isinstance(parsed["serverTime"], bool)
        or not isinstance(parsed["serverTime"], int)
        or parsed["serverTime"] < 0
        or parsed["serverTime"] > (1 << 53) - 1
    ):
        raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID")
    return parsed


def _selected_headers(headers: object) -> Dict[str, Optional[str]]:
    if not isinstance(headers, Mapping):
        raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID")
    lowered = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID")
        lowered[key.lower()] = value
    return {
        "http_date_or_null": lowered.get("date"),
        "retry_after_or_null": lowered.get("retry-after"),
    }


def _build_sample(
    response: PublicServerTimeHttpResponse,
    sequence: int,
    policy: RuntimeHealthPolicy,
) -> Dict[str, Any]:
    if (
        not isinstance(response, PublicServerTimeHttpResponse)
        or isinstance(response.status, bool)
        or response.status != 200
        or not _valid_server_time_url(response.final_url)
        or isinstance(response.monotonic_rtt_ms, bool)
        or not isinstance(response.monotonic_rtt_ms, int)
        or response.monotonic_rtt_ms < 0
    ):
        raise RuntimeHealthError("PAPER_CLOCK_RESPONSE_INVALID")
    started, started_text = _utc(response.request_started_at)
    received, received_text = _utc(response.response_received_at)
    if received < started:
        raise RuntimeHealthError("PAPER_CLOCK_WALL_REVERSED")
    parsed = _strict_json(response.body)
    server_ms = parsed["serverTime"]
    start_ms = _epoch_ms(started_text)
    receive_ms = _epoch_ms(received_text)
    sample = {
        "sequence": sequence,
        "request": {
            "method": "GET",
            "url": policy.server_time_url,
            "query": {},
            "security_type": "NONE_PUBLIC",
        },
        "status": response.status,
        "final_url": response.final_url,
        "selected_headers": _selected_headers(response.headers),
        "response_body_utf8": response.body.decode("utf-8"),
        "response_body_sha256": hashlib.sha256(response.body).hexdigest(),
        "request_started_at": started_text,
        "response_received_at": received_text,
        "wall_elapsed_ms": receive_ms - start_ms,
        "monotonic_rtt_ms": response.monotonic_rtt_ms,
        "server_time_ms": server_ms,
        "offset_lower_ms": server_ms - receive_ms - 1,
        "offset_upper_ms": server_ms - start_ms + 1,
    }
    sample["receipt_hash"] = business_hash(sample)
    return sample


def _classification(
    samples: Sequence[Mapping[str, Any]],
    policy: RuntimeHealthPolicy,
) -> Dict[str, Any]:
    reasons = []
    if len(samples) != policy.sample_count:
        reasons.append("PAPER_CLOCK_SAMPLE_COUNT_INVALID")
    if any(
        item.get("monotonic_rtt_ms", policy.max_rtt_ms + 1)
        > policy.max_rtt_ms
        for item in samples
    ):
        reasons.append("PAPER_CLOCK_RTT_EXCEEDS_LIMIT")
    if not samples:
        lower = None
        upper = None
        width = None
    else:
        lower = max(item["offset_lower_ms"] for item in samples)
        upper = min(item["offset_upper_ms"] for item in samples)
        width = upper - lower
        if lower > upper:
            reasons.append("PAPER_CLOCK_INTERVALS_DO_NOT_INTERSECT")
        elif width > policy.max_intersection_width_ms:
            reasons.append("PAPER_CLOCK_INTERSECTION_TOO_WIDE")
        if max(abs(lower), abs(upper)) > policy.max_absolute_offset_ms:
            reasons.append("PAPER_CLOCK_OFFSET_EXCEEDS_LIMIT")
    blocked = bool(reasons)
    if blocked:
        status = "BLOCKED"
        correction = None
    else:
        correction = (lower + upper) // 2
        conservative = max(abs(lower), abs(upper))
        status = (
            "HEALTHY_ALIGNED"
            if conservative <= policy.aligned_offset_ms
            else "HEALTHY_CORRECTED"
        )
    return {
        "health_status": status,
        "reason_codes": sorted(set(reasons)),
        "offset_intersection": {
            "lower_ms": lower,
            "upper_ms": upper,
            "width_ms": width,
        },
        "correction_ms": correction,
    }


def build_server_time_probe(
    *,
    transport=None,
    policy: Optional[RuntimeHealthPolicy] = None,
) -> Dict[str, Any]:
    selected_policy = policy or RuntimeHealthPolicy.create()
    if not isinstance(selected_policy, RuntimeHealthPolicy):
        raise RuntimeHealthError("PAPER_CLOCK_POLICY_INVALID")
    selected_transport = transport or BinanceServerTimeTransport()
    samples = []
    for sequence in range(1, selected_policy.sample_count + 1):
        if not hasattr(selected_transport, "get"):
            raise RuntimeHealthError("PAPER_CLOCK_TRANSPORT_INVALID")
        samples.append(
            _build_sample(
                selected_transport.get(), sequence, selected_policy
            )
        )
    classification = _classification(samples, selected_policy)
    last = samples[-1]
    correction = classification["correction_ms"]
    trusted_completed_at = (
        _from_epoch_ms(
            _epoch_ms(last["response_received_at"]) + correction
        )
        if correction is not None
        else None
    )
    identity = {
        "policy_hash": selected_policy.policy_hash,
        "receipt_hashes": [item["receipt_hash"] for item in samples],
    }
    probe = {
        "$schema": "./server-time-probe-v1.schema.json",
        "schema_version": "1.0.0",
        "probe_id": stable_id("server_time_probe", identity),
        "probe_hash": "",
        "policy": {
            **selected_policy.business_payload(),
            "policy_hash": selected_policy.policy_hash,
        },
        "sample_count": len(samples),
        "valid_sample_count": len(samples),
        "samples": samples,
        **classification,
        "local_completed_at": last["response_received_at"],
        "trusted_completed_at_or_null": trusted_completed_at,
        "time_basis": (
            "BINANCE_SERVER_TIME_ALIGNED"
            if classification["health_status"] == "HEALTHY_ALIGNED"
            else "BINANCE_SERVER_TIME_CORRECTED"
            if classification["health_status"] == "HEALTHY_CORRECTED"
            else "LOCAL_UNTRUSTED"
        ),
    }
    probe["probe_hash"] = artifact_self_hash(probe, "probe_hash")
    return probe


def _failed_probe(
    policy: RuntimeHealthPolicy,
    reason_code: str,
    local_completed_at: str,
) -> Dict[str, Any]:
    _, local_text = _utc(local_completed_at)
    identity = {
        "policy_hash": policy.policy_hash,
        "reason_code": reason_code,
        "local_completed_at": local_text,
    }
    probe = {
        "$schema": "./server-time-probe-v1.schema.json",
        "schema_version": "1.0.0",
        "probe_id": stable_id("server_time_probe", identity),
        "probe_hash": "",
        "policy": {**policy.business_payload(), "policy_hash": policy.policy_hash},
        "sample_count": 0,
        "valid_sample_count": 0,
        "samples": [],
        "health_status": "BLOCKED",
        "reason_codes": [reason_code],
        "offset_intersection": {
            "lower_ms": None,
            "upper_ms": None,
            "width_ms": None,
        },
        "correction_ms": None,
        "local_completed_at": local_text,
        "trusted_completed_at_or_null": None,
        "time_basis": "LOCAL_UNTRUSTED",
    }
    probe["probe_hash"] = artifact_self_hash(probe, "probe_hash")
    return probe


def server_time_probe_trust_hash(probe: Mapping[str, Any]) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _PROBE_ATTESTATION_TYPE,
                "probe_id": probe["probe_id"],
                "probe_hash": probe["probe_hash"],
                "policy_hash": probe["policy"]["policy_hash"],
                "receipt_hashes": [
                    item["receipt_hash"] for item in probe["samples"]
                ],
                "health_status": probe["health_status"],
            }
        )
    except (KeyError, TypeError):
        return ""


def server_time_probe_reasons(
    probe: Mapping[str, Any],
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(probe, Mapping):
        return ("PAPER_CLOCK_PROBE_INVALID",)
    reasons = []
    try:
        policy = RuntimeHealthPolicy.create()
        expected_policy = {
            **policy.business_payload(),
            "policy_hash": policy.policy_hash,
        }
        if probe.get("policy") != expected_policy:
            reasons.append("PAPER_CLOCK_POLICY_MISMATCH")
        if artifact_self_hash(probe, "probe_hash") != probe.get("probe_hash"):
            reasons.append("PAPER_CLOCK_PROBE_SELF_HASH_MISMATCH")
        if (
            server_time_probe_trust_hash(probe)
            != trusted_attestation_hash
        ):
            reasons.append("PAPER_CLOCK_PROBE_TRUST_HASH_MISMATCH")
        samples = probe.get("samples")
        if not isinstance(samples, list):
            raise RuntimeHealthError("PAPER_CLOCK_PROBE_INVALID")
        replayed = []
        for sequence, source in enumerate(samples, 1):
            if not isinstance(source, Mapping):
                raise RuntimeHealthError("PAPER_CLOCK_PROBE_INVALID")
            body = source.get("response_body_utf8")
            if not isinstance(body, str):
                raise RuntimeHealthError("PAPER_CLOCK_PROBE_INVALID")
            response = PublicServerTimeHttpResponse(
                status=source.get("status"),
                final_url=source.get("final_url"),
                headers={
                    "Date": source.get("selected_headers", {}).get(
                        "http_date_or_null"
                    )
                }
                if source.get("selected_headers", {}).get(
                    "http_date_or_null"
                )
                is not None
                else {},
                body=body.encode("utf-8"),
                request_started_at=source.get("request_started_at"),
                response_received_at=source.get("response_received_at"),
                monotonic_rtt_ms=source.get("monotonic_rtt_ms"),
            )
            expected = _build_sample(response, sequence, policy)
            # Retry-After is selected but absent on a successful official
            # response. Preserve and compare the complete stored receipt.
            expected["selected_headers"] = dict(
                source.get("selected_headers", {})
            )
            expected["receipt_hash"] = business_hash(
                {k: v for k, v in expected.items() if k != "receipt_hash"}
            )
            if expected != source:
                reasons.append("PAPER_CLOCK_SAMPLE_REPLAY_MISMATCH")
            replayed.append(expected)
        if samples:
            classification = _classification(replayed, policy)
            last = replayed[-1]
            correction = classification["correction_ms"]
            trusted = (
                _from_epoch_ms(
                    _epoch_ms(last["response_received_at"]) + correction
                )
                if correction is not None
                else None
            )
            expected_sample_count = len(samples)
        else:
            classification = {
                "health_status": "BLOCKED",
                "reason_codes": probe.get("reason_codes"),
                "offset_intersection": {
                    "lower_ms": None,
                    "upper_ms": None,
                    "width_ms": None,
                },
                "correction_ms": None,
            }
            trusted = None
            expected_sample_count = 0
            if (
                not isinstance(probe.get("reason_codes"), list)
                or not probe["reason_codes"]
            ):
                reasons.append("PAPER_CLOCK_FAILURE_REASON_MISSING")
        for name in (
            "health_status",
            "reason_codes",
            "offset_intersection",
            "correction_ms",
        ):
            if probe.get(name) != classification[name]:
                reasons.append("PAPER_CLOCK_CLASSIFICATION_MISMATCH")
        if probe.get("sample_count") != expected_sample_count:
            reasons.append("PAPER_CLOCK_SAMPLE_COUNT_MISMATCH")
        if probe.get("valid_sample_count") != expected_sample_count:
            reasons.append("PAPER_CLOCK_VALID_SAMPLE_COUNT_MISMATCH")
        if probe.get("trusted_completed_at_or_null") != trusted:
            reasons.append("PAPER_CLOCK_TRUSTED_TIME_MISMATCH")
        expected_basis = (
            "BINANCE_SERVER_TIME_ALIGNED"
            if classification["health_status"] == "HEALTHY_ALIGNED"
            else "BINANCE_SERVER_TIME_CORRECTED"
            if classification["health_status"] == "HEALTHY_CORRECTED"
            else "LOCAL_UNTRUSTED"
        )
        if probe.get("time_basis") != expected_basis:
            reasons.append("PAPER_CLOCK_TIME_BASIS_MISMATCH")
        identity = (
            {
                "policy_hash": policy.policy_hash,
                "receipt_hashes": [
                    item["receipt_hash"] for item in replayed
                ],
            }
            if replayed
            else {
                "policy_hash": policy.policy_hash,
                "reason_code": probe["reason_codes"][0],
                "local_completed_at": probe["local_completed_at"],
            }
        )
        if probe.get("probe_id") != stable_id(
            "server_time_probe", identity
        ):
            reasons.append("PAPER_CLOCK_PROBE_ID_MISMATCH")
    except (KeyError, TypeError, ValueError, RuntimeHealthError):
        reasons.append("PAPER_CLOCK_PROBE_REPLAY_INVALID")
    return tuple(sorted(set(reasons)))


class TrustedRuntimeClock:
    """UTC clock advanced only by monotonic elapsed time after a trusted probe."""

    def __init__(
        self,
        *,
        anchor_utc_ms: int,
        anchor_monotonic_ns: Optional[int] = None,
        monotonic_ns=None,
    ):
        if isinstance(anchor_utc_ms, bool) or not isinstance(anchor_utc_ms, int):
            raise RuntimeHealthError("PAPER_TRUSTED_CLOCK_INVALID")
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._anchor_monotonic_ns = (
            self._monotonic_ns()
            if anchor_monotonic_ns is None
            else anchor_monotonic_ns
        )
        if (
            isinstance(self._anchor_monotonic_ns, bool)
            or not isinstance(self._anchor_monotonic_ns, int)
        ):
            raise RuntimeHealthError("PAPER_TRUSTED_CLOCK_INVALID")
        self._anchor_utc_ms = anchor_utc_ms
        self._last_monotonic_ns = self._anchor_monotonic_ns

    def __call__(self) -> str:
        current = self._monotonic_ns()
        if (
            isinstance(current, bool)
            or not isinstance(current, int)
            or current < self._anchor_monotonic_ns
            or current < self._last_monotonic_ns
        ):
            raise RuntimeHealthError("PAPER_TRUSTED_CLOCK_REVERSED")
        self._last_monotonic_ns = current
        elapsed_ms = (
            current - self._anchor_monotonic_ns
        ) // 1_000_000
        return _from_epoch_ms(self._anchor_utc_ms + elapsed_ms)


@dataclass(frozen=True, init=False)
class VerifiedRuntimeGate:
    """One replay-valid probe and the monotonic clock issued from it."""

    probe: Mapping[str, Any]
    clock: TrustedRuntimeClock
    probe_request_count: int

    def __init__(self, *args, **kwargs):
        if kwargs.pop("_token", None) is not _RUNTIME_GATE_TOKEN:
            raise TypeError(
                "VerifiedRuntimeGate is issued by open_verified_runtime_gate"
            )
        object.__setattr__(self, "probe", kwargs["probe"])
        object.__setattr__(self, "clock", kwargs["clock"])
        object.__setattr__(
            self, "probe_request_count", kwargs["probe_request_count"]
        )


def _trusted_clock_from_probe(probe: Mapping[str, Any]) -> TrustedRuntimeClock:
    if probe.get("health_status") not in (
        "HEALTHY_ALIGNED",
        "HEALTHY_CORRECTED",
    ):
        raise RuntimeHealthError("PAPER_CLOCK_PROBE_BLOCKED")
    return TrustedRuntimeClock(
        anchor_utc_ms=_epoch_ms(probe["trusted_completed_at_or_null"])
    )


def open_verified_runtime_gate(
    *,
    server_time_transport=None,
    monotonic_ns=None,
) -> VerifiedRuntimeGate:
    """Issue one shared clock gate after a complete healthy probe."""

    probe = build_server_time_probe(
        transport=server_time_transport,
        policy=RuntimeHealthPolicy.create(),
    )
    trust_hash = server_time_probe_trust_hash(probe)
    if server_time_probe_reasons(probe, trust_hash):
        raise RuntimeHealthError("PAPER_CLOCK_PROBE_INVALID")
    if probe["health_status"] not in (
        "HEALTHY_ALIGNED",
        "HEALTHY_CORRECTED",
    ):
        raise RuntimeHealthError("PAPER_CLOCK_PROBE_BLOCKED")
    return VerifiedRuntimeGate(
        probe=probe,
        clock=TrustedRuntimeClock(
            anchor_utc_ms=_epoch_ms(
                probe["trusted_completed_at_or_null"]
            ),
            monotonic_ns=monotonic_ns,
        ),
        probe_request_count=3,
        _token=_RUNTIME_GATE_TOKEN,
    )


def _validate_state_path(path: Path) -> None:
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        parent_entry = parent.lstat()
        if stat.S_ISLNK(parent_entry.st_mode) or not stat.S_ISDIR(
            parent_entry.st_mode
        ):
            raise RuntimeHealthError("PAPER_RUNTIME_STATE_PATH_INVALID")
        if path.exists() or path.is_symlink():
            entry = path.lstat()
            if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
                raise RuntimeHealthError("PAPER_RUNTIME_STATE_PATH_INVALID")
    except OSError as error:
        raise RuntimeHealthError("PAPER_RUNTIME_STATE_PATH_INVALID") from error


def _event_body(
    *,
    sequence: int,
    event_id: str,
    event_time: str,
    payload: Mapping[str, Any],
    payload_hash: str,
    previous_event_hash: str,
) -> Dict[str, Any]:
    return {
        "sequence": sequence,
        "event_id": event_id,
        "event_type": "HEARTBEAT_RECORDED",
        "event_time": event_time,
        "payload": dict(payload),
        "payload_hash": payload_hash,
        "previous_event_hash": previous_event_hash,
    }


def _verify_events(
    events: Sequence[Mapping[str, Any]],
    policy: RuntimeHealthPolicy,
) -> None:
    previous_hash = _GENESIS_HASH
    previous_time = None
    previous_active = []
    previous_trusted = None
    for expected_sequence, source in enumerate(events, 1):
        try:
            sequence = source["sequence"]
            event_time, event_text = _utc(source["event_time"])
            payload = source["payload"]
        except (KeyError, RuntimeHealthError) as error:
            raise RuntimeHealthError("PAPER_RUNTIME_EVENT_INVALID") from error
        if (
            sequence != expected_sequence
            or source.get("event_type") != "HEARTBEAT_RECORDED"
            or not isinstance(payload, Mapping)
            or source.get("previous_event_hash") != previous_hash
            or (previous_time is not None and event_time < previous_time)
        ):
            raise RuntimeHealthError("PAPER_RUNTIME_EVENT_INVALID")
        payload_hash = business_hash(payload)
        if source.get("payload_hash") != payload_hash:
            raise RuntimeHealthError(
                "PAPER_RUNTIME_EVENT_PAYLOAD_HASH_MISMATCH"
            )
        identity = {
            "sequence": sequence,
            "event_type": "HEARTBEAT_RECORDED",
            "event_time": event_text,
            "payload_hash": payload_hash,
            "previous_event_hash": previous_hash,
        }
        event_id = stable_id("runtime_event", identity)
        if source.get("event_id") != event_id:
            raise RuntimeHealthError("PAPER_RUNTIME_EVENT_ID_MISMATCH")
        body = _event_body(
            sequence=sequence,
            event_id=event_id,
            event_time=event_text,
            payload=payload,
            payload_hash=payload_hash,
            previous_event_hash=previous_hash,
        )
        if source.get("event_hash") != business_hash(body):
            raise RuntimeHealthError("PAPER_RUNTIME_EVENT_HASH_MISMATCH")
        probe = payload.get("probe")
        if server_time_probe_reasons(
            probe, server_time_probe_trust_hash(probe)
        ):
            raise RuntimeHealthError("PAPER_RUNTIME_PROBE_INVALID")
        network = payload.get("network")
        if (
            not isinstance(network, Mapping)
            or network.get("server_time_request_count") not in (0, 1, 2, 3)
            or isinstance(network.get("paper_market_request_count"), bool)
            or network.get("paper_market_request_count") not in (0, 4)
            or network.get("total_network_request_count")
            != network.get("server_time_request_count")
            + network.get("paper_market_request_count")
        ):
            raise RuntimeHealthError("PAPER_RUNTIME_NETWORK_COUNT_INVALID")
        alerts = payload.get("alerts")
        if (
            not isinstance(alerts, Mapping)
            or alerts.get("delivery") != "LOCAL_ARTIFACT_ONLY"
        ):
            raise RuntimeHealthError("PAPER_RUNTIME_ALERT_INVALID")
        active = alerts.get("active")
        raised = alerts.get("raised")
        cleared = alerts.get("cleared")
        if any(
            not isinstance(items, list)
            or items != sorted(set(items))
            or not set(items).issubset(_ALERT_CODES)
            for items in (active, raised, cleared)
        ):
            raise RuntimeHealthError("PAPER_RUNTIME_ALERT_INVALID")
        if raised != sorted(set(active) - set(previous_active)):
            raise RuntimeHealthError("PAPER_RUNTIME_ALERT_TRANSITION_INVALID")
        if cleared != sorted(set(previous_active) - set(active)):
            raise RuntimeHealthError("PAPER_RUNTIME_ALERT_TRANSITION_INVALID")
        trusted = payload.get("trusted_heartbeat_at_or_null")
        gap = payload.get("heartbeat_gap_seconds_or_null")
        expected_gap = None
        if previous_trusted is not None and trusted is not None:
            delta = _utc(trusted)[0] - _utc(previous_trusted)[0]
            expected_gap = int(delta.total_seconds())
            if expected_gap < 0:
                raise RuntimeHealthError(
                    "PAPER_RUNTIME_TRUSTED_TIME_REVERSED"
                )
        if gap != expected_gap:
            raise RuntimeHealthError("PAPER_RUNTIME_HEARTBEAT_GAP_INVALID")
        expected_gap_alert = (
            expected_gap is not None
            and expected_gap > policy.heartbeat_gap_seconds
        )
        if (
            ("PAPER_HEARTBEAT_GAP" in active) != expected_gap_alert
        ):
            raise RuntimeHealthError("PAPER_RUNTIME_GAP_ALERT_INVALID")
        expected_unknown = (
            expected_sequence > 1
            and (previous_trusted is None or trusted is None)
        )
        if (
            "PAPER_HEARTBEAT_CONTINUITY_UNKNOWN" in active
        ) != expected_unknown:
            raise RuntimeHealthError(
                "PAPER_RUNTIME_CONTINUITY_ALERT_INVALID"
            )
        previous_active = active
        previous_trusted = trusted
        previous_time = event_time
        previous_hash = source["event_hash"]


class RuntimeHealthState:
    """Append-only WAL heartbeat state; no update/delete path is exposed."""

    def __init__(self, path: Path, policy: RuntimeHealthPolicy):
        if not isinstance(policy, RuntimeHealthPolicy):
            raise RuntimeHealthError("PAPER_RUNTIME_POLICY_INVALID")
        self.path = Path(path)
        self.policy = policy
        _validate_state_path(self.path)
        self.connection = sqlite3.connect(str(self.path), timeout=0)
        self.connection.row_factory = sqlite3.Row
        mode = self.connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise RuntimeHealthError("PAPER_RUNTIME_WAL_REQUIRED")
        self.connection.execute("PRAGMA synchronous = FULL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runtime_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                event_time TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                previous_event_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS runtime_events_no_update
            BEFORE UPDATE ON runtime_events
            BEGIN SELECT RAISE(ABORT, 'runtime events are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS runtime_events_no_delete
            BEFORE DELETE ON runtime_events
            BEGIN SELECT RAISE(ABORT, 'runtime events are immutable'); END;
            """
        )
        self.verify_integrity()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "RuntimeHealthState":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def events(self) -> Tuple[Dict[str, Any], ...]:
        result = []
        for row in self.connection.execute(
            "SELECT * FROM runtime_events ORDER BY sequence"
        ).fetchall():
            result.append(
                {
                    "sequence": row["sequence"],
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "event_time": row["event_time"],
                    "payload": json.loads(row["payload_json"]),
                    "payload_hash": row["payload_hash"],
                    "previous_event_hash": row["previous_event_hash"],
                    "event_hash": row["event_hash"],
                }
            )
        return tuple(result)

    def verify_integrity(self) -> str:
        events = self.events()
        _verify_events(events, self.policy)
        return events[-1]["event_hash"] if events else _GENESIS_HASH

    def prepare_heartbeat(
        self, raw_payload: Mapping[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(raw_payload, Mapping):
            raise RuntimeHealthError("PAPER_RUNTIME_PAYLOAD_INVALID")
        payload = json.loads(canonical_json(dict(raw_payload)))
        probe = payload.get("probe")
        if server_time_probe_reasons(
            probe, server_time_probe_trust_hash(probe)
        ):
            raise RuntimeHealthError("PAPER_RUNTIME_PROBE_INVALID")
        events = self.events()
        previous = events[-1]["payload"] if events else None
        trusted = probe.get("trusted_completed_at_or_null")
        gap = None
        derived = set(payload.get("alerts", {}).get("active", []))
        if previous is not None:
            prior_trusted = previous.get("trusted_heartbeat_at_or_null")
            if trusted is not None and prior_trusted is not None:
                delta = _utc(trusted)[0] - _utc(prior_trusted)[0]
                gap = int(delta.total_seconds())
                if gap < 0:
                    raise RuntimeHealthError(
                        "PAPER_RUNTIME_TRUSTED_TIME_REVERSED"
                    )
                if gap > self.policy.heartbeat_gap_seconds:
                    derived.add("PAPER_HEARTBEAT_GAP")
            else:
                derived.add("PAPER_HEARTBEAT_CONTINUITY_UNKNOWN")
        if not derived.issubset(_ALERT_CODES):
            raise RuntimeHealthError("PAPER_RUNTIME_ALERT_INVALID")
        prior_active = (
            set(previous["alerts"]["active"]) if previous is not None else set()
        )
        active = sorted(derived)
        payload["heartbeat_gap_seconds_or_null"] = gap
        payload["trusted_heartbeat_at_or_null"] = trusted
        payload["alerts"] = {
            "active": active,
            "raised": sorted(set(active) - prior_active),
            "cleared": sorted(prior_active - set(active)),
            "delivery": "LOCAL_ARTIFACT_ONLY",
        }
        return payload

    def append_heartbeat(
        self, payload: Mapping[str, Any]
    ) -> Dict[str, Any]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.verify_integrity()
            normalized = (
                json.loads(canonical_json(dict(payload)))
                if "heartbeat_gap_seconds_or_null" in payload
                else self.prepare_heartbeat(payload)
            )
            last = self.connection.execute(
                "SELECT sequence, event_time, event_hash "
                "FROM runtime_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            sequence = 1 if last is None else int(last["sequence"]) + 1
            previous_hash = (
                _GENESIS_HASH if last is None else last["event_hash"]
            )
            observed = (
                normalized["probe"]["trusted_completed_at_or_null"]
                or normalized["probe"]["local_completed_at"]
            )
            event_dt, event_time = _utc(observed)
            if last is not None:
                last_dt, _ = _utc(last["event_time"])
                if event_dt < last_dt:
                    event_time = utc_datetime(
                        last_dt + timedelta(milliseconds=1)
                    )
            payload_hash = business_hash(normalized)
            identity = {
                "sequence": sequence,
                "event_type": "HEARTBEAT_RECORDED",
                "event_time": event_time,
                "payload_hash": payload_hash,
                "previous_event_hash": previous_hash,
            }
            event_id = stable_id("runtime_event", identity)
            body = _event_body(
                sequence=sequence,
                event_id=event_id,
                event_time=event_time,
                payload=normalized,
                payload_hash=payload_hash,
                previous_event_hash=previous_hash,
            )
            event_hash = business_hash(body)
            self.connection.execute(
                """
                INSERT INTO runtime_events (
                    event_id, event_type, event_time, payload_json,
                    payload_hash, previous_event_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    "HEARTBEAT_RECORDED",
                    event_time,
                    canonical_json(normalized),
                    payload_hash,
                    previous_hash,
                    event_hash,
                ),
            )
            event = {**body, "event_hash": event_hash}
            _verify_events(self.events(), self.policy)
            self.connection.commit()
            return event
        except Exception:
            self.connection.rollback()
            raise


def _runtime_summary(events: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    status_counts = {
        "HEALTHY_ALIGNED": 0,
        "HEALTHY_CORRECTED": 0,
        "BLOCKED": 0,
    }
    scheduler_counts: Dict[str, int] = {}
    trusted_times = []
    gaps = []
    for event in events:
        payload = event["payload"]
        status_counts[payload["probe"]["health_status"]] += 1
        outcome = payload["scheduler"]["outcome"]
        scheduler_counts[outcome] = scheduler_counts.get(outcome, 0) + 1
        trusted = payload["trusted_heartbeat_at_or_null"]
        if trusted is not None:
            trusted_times.append(trusted)
        gap = payload["heartbeat_gap_seconds_or_null"]
        if gap is not None:
            gaps.append(gap)
    latest = events[-1]["payload"] if events else None
    return {
        "heartbeat_count": len(events),
        "health_status_counts": status_counts,
        "scheduler_outcome_counts": {
            name: scheduler_counts[name] for name in sorted(scheduler_counts)
        },
        "first_trusted_heartbeat_at_or_null": (
            trusted_times[0] if trusted_times else None
        ),
        "last_trusted_heartbeat_at_or_null": (
            trusted_times[-1] if trusted_times else None
        ),
        "max_trusted_heartbeat_gap_seconds_or_null": (
            max(gaps) if gaps else None
        ),
        "current_active_alerts": (
            latest["alerts"]["active"] if latest else []
        ),
        "latest_scheduler": latest["scheduler"] if latest else None,
    }


@lru_cache(maxsize=1)
def _snapshot_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "paper-runtime-snapshot-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_runtime_snapshot(state: RuntimeHealthState) -> Dict[str, Any]:
    if not isinstance(state, RuntimeHealthState):
        raise RuntimeHealthError("PAPER_RUNTIME_STATE_INVALID")
    chain_end = state.verify_integrity()
    events = list(state.events())
    if not events:
        raise RuntimeHealthError("PAPER_RUNTIME_EMPTY")
    summary = _runtime_summary(events)
    identity = {
        "policy_hash": state.policy.policy_hash,
        "event_chain_end_hash": chain_end,
        "heartbeat_count": len(events),
    }
    snapshot = {
        "$schema": "./paper-runtime-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": stable_id("paper_runtime_snapshot", identity),
        "snapshot_hash": "",
        "recorded_at": events[-1]["event_time"],
        "policy": {
            **state.policy.business_payload(),
            "policy_hash": state.policy.policy_hash,
        },
        "events": events,
        "events_root_hash": business_hash(events),
        "event_chain_end_hash": chain_end,
        "summary": summary,
        "state_integrity": "VERIFIED_APPEND_ONLY_WAL",
        "runtime_health_eligibility": "OPERATIONAL_SMOKE_ONLY",
        "scheduler_eligibility": "SCHEDULER_OPERATIONAL_SMOKE_ONLY",
        "paper_eligibility": "LONGITUDINAL_COLLECTION_IN_PROGRESS",
        "profitability_eligibility": "INSUFFICIENT_DURATION_COST_AND_AI",
        "alert_delivery_eligibility": "LOCAL_ARTIFACT_ONLY",
        "warnings": list(_WARNINGS),
    }
    snapshot["snapshot_hash"] = artifact_self_hash(
        snapshot, "snapshot_hash"
    )
    if tuple(_snapshot_validator().iter_errors(snapshot)):
        raise RuntimeHealthError("PAPER_RUNTIME_SNAPSHOT_SCHEMA_INVALID")
    return snapshot


def runtime_snapshot_trust_hash(snapshot: Mapping[str, Any]) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _RUNTIME_ATTESTATION_TYPE,
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "policy_hash": snapshot["policy"]["policy_hash"],
                "events_root_hash": snapshot["events_root_hash"],
                "event_chain_end_hash": snapshot[
                    "event_chain_end_hash"
                ],
                "probe_trust_hashes": [
                    server_time_probe_trust_hash(event["payload"]["probe"])
                    for event in snapshot["events"]
                ],
            }
        )
    except (KeyError, TypeError):
        return ""


def runtime_snapshot_reasons(
    snapshot: Mapping[str, Any],
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(snapshot, Mapping):
        return ("PAPER_RUNTIME_SNAPSHOT_INVALID",)
    reasons = []
    try:
        if tuple(_snapshot_validator().iter_errors(snapshot)):
            reasons.append("PAPER_RUNTIME_SNAPSHOT_SCHEMA_INVALID")
        if artifact_self_hash(snapshot, "snapshot_hash") != snapshot.get(
            "snapshot_hash"
        ):
            reasons.append("PAPER_RUNTIME_SELF_HASH_MISMATCH")
        if (
            runtime_snapshot_trust_hash(snapshot)
            != trusted_attestation_hash
        ):
            reasons.append("PAPER_RUNTIME_TRUST_HASH_MISMATCH")
        policy = RuntimeHealthPolicy.create()
        expected_policy = {
            **policy.business_payload(),
            "policy_hash": policy.policy_hash,
        }
        if snapshot.get("policy") != expected_policy:
            reasons.append("PAPER_RUNTIME_POLICY_MISMATCH")
        events = snapshot["events"]
        _verify_events(events, policy)
        if business_hash(events) != snapshot.get("events_root_hash"):
            reasons.append("PAPER_RUNTIME_EVENTS_ROOT_MISMATCH")
        expected_end = events[-1]["event_hash"] if events else _GENESIS_HASH
        if expected_end != snapshot.get("event_chain_end_hash"):
            reasons.append("PAPER_RUNTIME_CHAIN_END_MISMATCH")
        if _runtime_summary(events) != snapshot.get("summary"):
            reasons.append("PAPER_RUNTIME_SUMMARY_MISMATCH")
        identity = {
            "policy_hash": policy.policy_hash,
            "event_chain_end_hash": expected_end,
            "heartbeat_count": len(events),
        }
        if snapshot.get("snapshot_id") != stable_id(
            "paper_runtime_snapshot", identity
        ):
            reasons.append("PAPER_RUNTIME_SNAPSHOT_ID_MISMATCH")
    except (
        KeyError,
        TypeError,
        ValueError,
        RuntimeHealthError,
    ):
        reasons.append("PAPER_RUNTIME_REPLAY_INVALID")
    for name, expected in (
        ("state_integrity", "VERIFIED_APPEND_ONLY_WAL"),
        ("runtime_health_eligibility", "OPERATIONAL_SMOKE_ONLY"),
        ("scheduler_eligibility", "SCHEDULER_OPERATIONAL_SMOKE_ONLY"),
        ("paper_eligibility", "LONGITUDINAL_COLLECTION_IN_PROGRESS"),
        (
            "profitability_eligibility",
            "INSUFFICIENT_DURATION_COST_AND_AI",
        ),
        ("alert_delivery_eligibility", "LOCAL_ARTIFACT_ONLY"),
    ):
        if snapshot.get(name) != expected:
            reasons.append("PAPER_RUNTIME_ELIGIBILITY_INVALID")
    if snapshot.get("warnings") != list(_WARNINGS):
        reasons.append("PAPER_RUNTIME_WARNINGS_INVALID")
    return tuple(sorted(set(reasons)))


def _scheduler_projection(
    outcome: str,
    result: Optional[Mapping[str, Any]] = None,
    reason_code: Optional[str] = None,
) -> Dict[str, Any]:
    source = result or {}
    return {
        "outcome": outcome,
        "reason_code_or_null": reason_code,
        "slot_id_or_null": source.get("slot_id"),
        "cycle_run_hash_or_null": source.get("cycle_run_hash"),
        "cycle_trust_hash_or_null": source.get("cycle_trust_hash"),
        "schedule_snapshot_hash_or_null": source.get(
            "schedule_snapshot_hash"
        ),
        "schedule_trust_hash_or_null": source.get("schedule_trust_hash"),
    }


def run_healthy_paper_cycle(
    *,
    runtime_state_path: Path,
    scheduler_state_path: Path,
    output_root: Path,
    worker_id: str,
    server_time_transport=None,
    paper_transport=None,
) -> Dict[str, Any]:
    policy = RuntimeHealthPolicy.create()
    selected_time_transport = (
        server_time_transport or BinanceServerTimeTransport()
    )
    calls_before = getattr(selected_time_transport, "calls", 0)
    if isinstance(calls_before, bool) or not isinstance(calls_before, int):
        calls_before = 0
    probe_error = None
    try:
        probe = build_server_time_probe(
            transport=selected_time_transport,
            policy=policy,
        )
    except RuntimeHealthError as error:
        probe_error = error.reason_code
        probe = _failed_probe(policy, error.reason_code, _utc_now())
    calls_after = getattr(selected_time_transport, "calls", None)
    time_count = (
        calls_after - calls_before
        if isinstance(calls_after, int)
        and not isinstance(calls_after, bool)
        and calls_after >= calls_before
        else None
    )
    if isinstance(time_count, bool) or not isinstance(time_count, int):
        time_count = 3 if probe_error is None else 0
    active_alerts = set()
    paper_count = 0
    schedule_result = None
    if probe["health_status"] == "BLOCKED":
        outcome = "CLOCK_BLOCKED"
        active_alerts.add("PAPER_CLOCK_PROBE_BLOCKED")
        scheduler = _scheduler_projection(
            "NOT_RUN_CLOCK_BLOCKED",
            reason_code=(
                probe_error
                or (
                    probe["reason_codes"][0]
                    if probe["reason_codes"]
                    else "PAPER_CLOCK_PROBE_BLOCKED"
                )
            ),
        )
    else:
        trusted_clock = _trusted_clock_from_probe(probe)
        try:
            schedule_result = run_due_paper_cycle(
                state_path=Path(scheduler_state_path),
                output_root=Path(output_root),
                worker_id=worker_id,
                transport=paper_transport,
                clock=trusted_clock,
            )
            outcome = schedule_result["outcome"]
            paper_count = schedule_result["network_request_count"]
            scheduler = _scheduler_projection(outcome, schedule_result)
            if outcome == "BUSY":
                active_alerts.add("PAPER_SCHEDULER_BUSY")
        except PaperScheduleError as error:
            outcome = "SCHEDULER_FAILED"
            active_alerts.add("PAPER_SCHEDULER_FAILURE")
            scheduler = _scheduler_projection(
                outcome, reason_code=error.reason_code
            )
    raw_payload = {
        "time_basis": probe["time_basis"],
        "probe": probe,
        "scheduler": scheduler,
        "network": {
            "server_time_request_count": time_count,
            "paper_market_request_count": paper_count,
            "total_network_request_count": time_count + paper_count,
        },
        "alerts": {
            "active": sorted(active_alerts),
            "raised": [],
            "cleared": [],
            "delivery": "LOCAL_ARTIFACT_ONLY",
        },
    }
    with RuntimeHealthState(Path(runtime_state_path), policy) as state:
        payload = state.prepare_heartbeat(raw_payload)
        event = state.append_heartbeat(payload)
        snapshot = build_runtime_snapshot(state)
    trust_hash = runtime_snapshot_trust_hash(snapshot)
    if runtime_snapshot_reasons(snapshot, trust_hash):
        raise RuntimeHealthError("PAPER_RUNTIME_SNAPSHOT_INVALID")
    artifact_name = (
        "paper-runtime-" + event["event_id"].lower() + ".json"
    )
    artifact_bytes = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    artifact_path = Path(output_root).resolve() / "runtime" / artifact_name
    created = _publish_immutable(
        Path(output_root),
        artifact_name,
        artifact_bytes,
        output_directory="runtime",
    )
    return {
        "outcome": outcome,
        "server_time_request_count": time_count,
        "paper_market_request_count": paper_count,
        "total_network_request_count": time_count + paper_count,
        "clock_health_status": probe["health_status"],
        "clock_correction_ms_or_null": probe["correction_ms"],
        "active_alerts": payload["alerts"]["active"],
        "runtime_snapshot_path": str(artifact_path),
        "runtime_snapshot_created": created,
        "runtime_snapshot_hash": snapshot["snapshot_hash"],
        "runtime_trust_hash": trust_hash,
        "runtime_snapshot": snapshot,
        "slot_id_or_null": scheduler["slot_id_or_null"],
        "cycle_run_hash_or_null": scheduler["cycle_run_hash_or_null"],
        "schedule_snapshot_hash_or_null": scheduler[
            "schedule_snapshot_hash_or_null"
        ],
    }
