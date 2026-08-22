"""Strict live-input boundary for the replacement Challenger."""

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_replacement_plan_v2 import challenger_replacement_plan_v2_reasons
from .evidence import artifact_self_hash
from .runtime_health import server_time_probe_reasons, server_time_probe_trust_hash


_CAPABILITY_TOKEN = object()
_MAX_CAPTURE_BYTES = 2 * 1024 * 1024
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


class ChallengerReplacementLiveInputError(ValueError):
    """The replacement live-input boundary failed closed."""

    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


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

    del previous_source_bundle
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
