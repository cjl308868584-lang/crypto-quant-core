"""Strict evidence contracts for the isolated replacement Challenger runtime."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal, stable_id, utc_datetime
from .canonical import canonical_json
from .challenger_replacement_plan_v2 import challenger_replacement_plan_v2_reasons
from .evidence import artifact_self_hash


_ZERO_HASH = "0" * 64
_FOUR_HOURS = timedelta(hours=4)
_ONE_MILLISECOND = timedelta(milliseconds=1)
_SOURCE_SCHEMA = "./challenger-replacement-source-bundle-v1.schema.json"
_QUALIFICATION = "TEST_FIXTURE_ONLY_NOT_COHORT_EVIDENCE"
_REQUEST_DESCRIPTOR = {
    "provider": "BINANCE_PUBLIC_DATA",
    "market": "SPOT",
    "data_family": "KLINES",
    "symbol": "ETHUSDT",
    "interval": "4h",
}
_BUILD_IDENTITY_KEYS = {
    "release_tag",
    "peeled_commit",
    "package_version",
    "manifest_version",
    "build_input_tree_hash",
    "manifest_hash",
    "manifest_file_sha256",
}


class ChallengerReplacementEvidenceError(ValueError):
    """Replacement evidence failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _source_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "challenger-replacement-source-bundle-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _decision_validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "challenger-replacement-decision-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str):
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_TIME_INVALID"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_TIME_INVALID"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_TIME_INVALID"
        )
    return converted, utc_datetime(converted)


def _hash(value: object, reason_code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ChallengerReplacementEvidenceError(reason_code)
    return value


def _build_identity(value: object) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BUILD_IDENTITY_KEYS:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_BUILD_IDENTITY_INVALID"
        )
    result = dict(value)
    for name in (
        "build_input_tree_hash",
        "manifest_hash",
        "manifest_file_sha256",
    ):
        _hash(result[name], "CHALLENGER_REPLACEMENT_INPUT_BUILD_IDENTITY_INVALID")
    if (
        not isinstance(result["peeled_commit"], str)
        or len(result["peeled_commit"]) != 40
        or any(character not in "0123456789abcdef" for character in result["peeled_commit"])
        or result["release_tag"] != "v0.66.0"
        or result["package_version"] != "0.66.0"
        or result["manifest_version"] != "1.60.0"
    ):
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_BUILD_IDENTITY_INVALID"
        )
    return result


def _normalized_klines(
    value: object, *, scheduled_for: datetime, captured_at: datetime
) -> Sequence[Dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 21:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_KLINES_INVALID"
        )
    result = []
    previous_open = None
    required = set(_REQUEST_DESCRIPTOR) | {
        "open_time",
        "close_time",
        "available_at",
        "open",
        "high",
        "low",
        "close",
        "source_row_hash",
    }
    for item in value:
        if not isinstance(item, Mapping) or set(item) != required:
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_INPUT_KLINES_INVALID"
            )
        if any(item[name] != expected for name, expected in _REQUEST_DESCRIPTOR.items()):
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_INPUT_KLINES_INVALID"
            )
        opened, opened_text = _utc(item["open_time"])
        closed, closed_text = _utc(item["close_time"])
        available, available_text = _utc(item["available_at"])
        try:
            opened_price = Decimal(item["open"])
            high = Decimal(item["high"])
            low = Decimal(item["low"])
            close = Decimal(item["close"])
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_INPUT_KLINES_INVALID"
            ) from error
        if (
            any(not number.is_finite() or number <= 0 for number in (opened_price, high, low, close))
            or high < max(opened_price, close)
            or low > min(opened_price, close)
            or closed != opened + _FOUR_HOURS - _ONE_MILLISECOND
            or available != opened + _FOUR_HOURS
            or available > captured_at
            or (previous_open is not None and opened != previous_open + _FOUR_HOURS)
        ):
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_INPUT_KLINES_INVALID"
            )
        normalized = {
            **_REQUEST_DESCRIPTOR,
            "open_time": opened_text,
            "close_time": closed_text,
            "available_at": available_text,
            "open": canonical_decimal(opened_price),
            "high": canonical_decimal(high),
            "low": canonical_decimal(low),
            "close": canonical_decimal(close),
        }
        if item["source_row_hash"] != business_hash(normalized):
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_INPUT_KLINES_INVALID"
            )
        normalized["source_row_hash"] = item["source_row_hash"]
        result.append(normalized)
        previous_open = opened
    if _utc(result[-1]["close_time"])[0] != scheduled_for - _ONE_MILLISECOND:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_SLOT_MISMATCH"
        )
    return result


def build_challenger_replacement_source_bundle(
    *,
    plan: Mapping[str, Any],
    build_identity: Mapping[str, Any],
    capture: Mapping[str, Any],
    observed_at: str,
    previous_source_bundle: Optional[Mapping[str, Any]],
    previous_decision: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build one deterministic, test-only replacement source bundle."""

    if not isinstance(plan, Mapping):
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_PLAN_INVALID"
        )
    plan_reasons = challenger_replacement_plan_v2_reasons(plan)
    if plan_reasons:
        raise ChallengerReplacementEvidenceError(plan_reasons[0])
    identity = _build_identity(build_identity)
    required_capture = {
        "slot_id",
        "sequence",
        "scheduled_for",
        "captured_at",
        "evidence_qualification",
        "request_descriptor",
        "klines",
        "network_request_count_observed_by_runtime",
    }
    if not isinstance(capture, Mapping) or set(capture) != required_capture:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_CAPTURE_INVALID"
        )
    scheduled, scheduled_text = _utc(capture["scheduled_for"])
    captured, captured_text = _utc(capture["captured_at"])
    observed, observed_text = _utc(observed_at)
    if (
        scheduled.minute
        or scheduled.second
        or scheduled.microsecond
        or scheduled.hour % 4
        or observed_text != captured_text
        or not scheduled <= captured < scheduled + _FOUR_HOURS
        or capture["evidence_qualification"] != _QUALIFICATION
        or capture["request_descriptor"] != _REQUEST_DESCRIPTOR
        or capture["network_request_count_observed_by_runtime"] != 0
        or isinstance(capture["sequence"], bool)
        or not isinstance(capture["sequence"], int)
        or capture["sequence"] < 1
    ):
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_CAPTURE_INVALID"
        )
    expected_slot_id = stable_id(
        "challenger_replacement_slot",
        {"plan_hash": plan["plan_hash"], "scheduled_for": scheduled_text},
    )
    if capture["slot_id"] != expected_slot_id:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_SLOT_ID_INVALID"
        )
    if previous_source_bundle is None and previous_decision is None:
        if capture["sequence"] != 1:
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_INPUT_PARENT_INVALID"
            )
        previous_source_hash = _ZERO_HASH
        previous_decision_hash = None
        previous_klines = None
    else:
        if not isinstance(previous_source_bundle, Mapping) or not isinstance(
            previous_decision, Mapping
        ):
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_INPUT_PARENT_INVALID"
            )
        previous_source_hash = _hash(
            previous_source_bundle.get("bundle_hash"),
            "CHALLENGER_REPLACEMENT_INPUT_PARENT_INVALID",
        )
        previous_decision_hash = _hash(
            previous_decision.get("decision_hash"),
            "CHALLENGER_REPLACEMENT_INPUT_PARENT_INVALID",
        )
        try:
            previous_scheduled = _utc(
                previous_source_bundle["slot"]["scheduled_for"]
            )[0]
            parent_valid = (
                previous_source_hash
                == artifact_self_hash(previous_source_bundle, "bundle_hash")
                and previous_decision_hash
                == artifact_self_hash(previous_decision, "decision_hash")
                and previous_source_bundle.get("plan")
                == {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]}
                and previous_source_bundle.get("build_identity") == identity
                and capture["sequence"]
                == previous_source_bundle["slot"]["sequence"] + 1
                and scheduled == previous_scheduled + _FOUR_HOURS
                and previous_decision.get("slot", {}).get("slot_id")
                == previous_source_bundle["slot"]["slot_id"]
                and previous_decision.get("parents", {}).get(
                    "current_source_bundle_hash"
                )
                == previous_source_hash
            )
            previous_klines = previous_source_bundle["klines"]
        except (KeyError, TypeError, ValueError):
            parent_valid = False
            previous_klines = None
        if not parent_valid:
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_INPUT_PARENT_INVALID"
            )
    klines = list(
        _normalized_klines(
            capture["klines"],
            scheduled_for=scheduled,
            captured_at=captured,
        )
    )
    if previous_klines is not None and klines[:-1] != list(previous_klines)[1:]:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_INPUT_REVISION"
        )
    build_identity_hash = artifact_self_hash(
        {**identity, "identity_hash": _ZERO_HASH}, "identity_hash"
    )
    bundle_identity = {
        "plan_hash": plan["plan_hash"],
        "build_identity_hash": build_identity_hash,
        "slot_id": expected_slot_id,
        "sequence": capture["sequence"],
        "scheduled_for": scheduled_text,
        "previous_source_bundle_hash": previous_source_hash,
        "previous_decision_hash_or_null": previous_decision_hash,
    }
    bundle = {
        "$schema": _SOURCE_SCHEMA,
        "schema_version": "1.0.0",
        "bundle_id": stable_id(
            "challenger_replacement_source_bundle", bundle_identity
        ),
        "bundle_hash": _ZERO_HASH,
        "evidence_qualification": _QUALIFICATION,
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "build_identity": identity,
        "slot": {
            "slot_id": expected_slot_id,
            "sequence": capture["sequence"],
            "scheduled_for": scheduled_text,
            "captured_at": captured_text,
        },
        "parents": {
            "previous_source_bundle_hash": previous_source_hash,
            "previous_decision_hash_or_null": previous_decision_hash,
        },
        "request_descriptor": dict(_REQUEST_DESCRIPTOR),
        "klines": klines,
        "authority": {
            "network_request_count_observed_by_runtime": 0,
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "broker_requests_allowed": False,
            "orders_allowed": False,
            "production_state_write_allowed": False,
        },
    }
    bundle["bundle_hash"] = artifact_self_hash(bundle, "bundle_hash")
    return bundle


def challenger_replacement_source_bundle_reasons(
    bundle: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    build_identity: Mapping[str, Any],
    previous_source_bundle: Optional[Mapping[str, Any]],
    previous_decision: Optional[Mapping[str, Any]],
) -> Tuple[str, ...]:
    """Return deterministic reasons for any source-bundle mismatch."""

    reasons = []
    try:
        if not isinstance(bundle, Mapping):
            raise TypeError("bundle must be a mapping")
        if tuple(_source_validator().iter_errors(bundle)):
            reasons.append("CHALLENGER_REPLACEMENT_INPUT_SCHEMA_INVALID")
        if bundle.get("bundle_hash") != artifact_self_hash(bundle, "bundle_hash"):
            reasons.append("CHALLENGER_REPLACEMENT_INPUT_HASH_MISMATCH")
        capture = {
            "slot_id": bundle["slot"]["slot_id"],
            "sequence": bundle["slot"]["sequence"],
            "scheduled_for": bundle["slot"]["scheduled_for"],
            "captured_at": bundle["slot"]["captured_at"],
            "evidence_qualification": bundle["evidence_qualification"],
            "request_descriptor": bundle["request_descriptor"],
            "klines": bundle["klines"],
            "network_request_count_observed_by_runtime": bundle["authority"][
                "network_request_count_observed_by_runtime"
            ],
        }
        rebuilt = build_challenger_replacement_source_bundle(
            plan=plan,
            build_identity=build_identity,
            capture=capture,
            observed_at=capture["captured_at"],
            previous_source_bundle=previous_source_bundle,
            previous_decision=previous_decision,
        )
        if business_hash(rebuilt) != business_hash(bundle):
            reasons.append("CHALLENGER_REPLACEMENT_INPUT_SEMANTIC_MISMATCH")
    except ChallengerReplacementEvidenceError as error:
        reasons.append(error.reason_code)
    except (KeyError, TypeError, ValueError):
        reasons.append("CHALLENGER_REPLACEMENT_INPUT_INVALID")
    return tuple(sorted(set(reasons)))


def _reject_duplicate_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ChallengerReplacementEvidenceError(
                "CHALLENGER_REPLACEMENT_ARTIFACT_JSON_INVALID"
            )
        result[key] = value
    return result


def _reject_float(_value: str) -> None:
    raise ChallengerReplacementEvidenceError(
        "CHALLENGER_REPLACEMENT_ARTIFACT_JSON_INVALID"
    )


def _strict_json_bytes(body: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except ChallengerReplacementEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_ARTIFACT_JSON_INVALID"
        ) from error
    if not isinstance(value, Mapping):
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_ARTIFACT_JSON_INVALID"
        )
    try:
        canonical = canonical_json(value).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_ARTIFACT_JSON_INVALID"
        ) from error
    if body != canonical:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_ARTIFACT_CANONICAL_BYTES_REQUIRED"
        )
    return value




def load_challenger_replacement_source_bundle_bytes(
    data: bytes,
    *,
    plan: Mapping[str, Any],
    build_identity: Mapping[str, Any],
    previous_source_bundle: Optional[Mapping[str, Any]],
    previous_decision: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Strict-load exact canonical source bytes and replay their semantics."""

    if not isinstance(data, bytes) or not 0 < len(data) <= 2 * 1024 * 1024:
        raise ChallengerReplacementEvidenceError(
            "CHALLENGER_REPLACEMENT_ARTIFACT_SIZE_INVALID"
        )
    value = _strict_json_bytes(data)
    reasons = challenger_replacement_source_bundle_reasons(
        value,
        plan=plan,
        build_identity=build_identity,
        previous_source_bundle=previous_source_bundle,
        previous_decision=previous_decision,
    )
    if reasons:
        raise ChallengerReplacementEvidenceError(reasons[0])
    return dict(value)

