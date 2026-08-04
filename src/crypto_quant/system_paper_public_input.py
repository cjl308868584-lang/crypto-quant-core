"""Replayable public-only input boundary for System Paper."""

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .offline_paper import (
    BinanceOfflinePaperTransport,
    OfflinePaperError,
    OfflinePaperPlan,
    VerifiedOfflinePaperCapture,
    capture_offline_paper,
    replay_offline_paper_capture,
    verified_offline_paper_market,
)
from .system_paper_plan import build_system_paper_plan, system_paper_plan_reasons


_SCHEMA = "system-paper-market-bundle-v1.schema.json"
_MAX_BUNDLE_BYTES = 10 * 1024 * 1024


class SystemPaperPublicInputError(ValueError):
    """The public System Paper capture failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SystemPaperPublicInputError("SYSTEM_PAPER_PUBLIC_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_TIME_INVALID"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperPublicInputError("SYSTEM_PAPER_PUBLIC_TIME_INVALID")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1000:
        raise SystemPaperPublicInputError("SYSTEM_PAPER_PUBLIC_TIME_INVALID")
    rendered = utc_datetime(parsed)
    if rendered != value:
        raise SystemPaperPublicInputError("SYSTEM_PAPER_PUBLIC_TIME_INVALID")
    return parsed, rendered


def _utc_now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _strict_json_bytes(body: bytes) -> Mapping[str, Any]:
    if not isinstance(body, bytes) or not body or len(body) > _MAX_BUNDLE_BYTES:
        raise SystemPaperPublicInputError("SYSTEM_PAPER_PUBLIC_BUNDLE_JSON_INVALID")

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise SystemPaperPublicInputError(
                    "SYSTEM_PAPER_PUBLIC_BUNDLE_JSON_DUPLICATE_KEY"
                )
            value[key] = item
        return value

    def reject_number(_value):
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_BUNDLE_FLOAT_FORBIDDEN"
        )

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except SystemPaperPublicInputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_BUNDLE_JSON_INVALID"
        ) from error
    if not isinstance(value, Mapping) or canonical_json(value).encode("utf-8") != body:
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_BUNDLE_JSON_NONCANONICAL"
        )
    return value


def build_system_paper_market_bundle(
    *,
    plan: Mapping[str, Any],
    scheduled_for: object,
    capture: VerifiedOfflinePaperCapture,
) -> Dict[str, Any]:
    """Build the sole source-complete market bundle for one logical slot."""

    if not isinstance(plan, Mapping) or system_paper_plan_reasons(plan):
        raise SystemPaperPublicInputError("SYSTEM_PAPER_PUBLIC_PLAN_INVALID")
    scheduled, scheduled_text = _utc(scheduled_for)
    if (
        scheduled.minute
        or scheduled.second
        or scheduled.microsecond
        or scheduled.hour % 4
    ):
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_SLOT_INVALID"
        )
    try:
        market = verified_offline_paper_market(capture)
        receipts = [dict(item) for item in market["source_receipts"]]
        captured_at = max(item["recorded_at"] for item in receipts)
        captured, _captured_text = _utc(captured_at)
        due = scheduled + timedelta(minutes=5)
        expires = due + timedelta(hours=4)
        if not due <= captured < expires:
            raise SystemPaperPublicInputError(
                "SYSTEM_PAPER_PUBLIC_CAPTURE_WINDOW_INVALID"
            )
        metadata = dict(market["instrument_metadata"])
        schema_version = metadata["schema_version"]
        klines = [
            {
                "open_time": item["open_time"],
                "close_time": item["close_time"],
                "close": item["close"],
                "source_row_hash": item["source_row_hash"],
            }
            for item in market["closed_4h_klines"]
        ]
        previous_close = None
        for item in klines:
            opened, _opened_text = _utc(item["open_time"])
            closed, _closed_text = _utc(item["close_time"])
            if closed - opened != timedelta(hours=4) - timedelta(milliseconds=1):
                raise SystemPaperPublicInputError(
                    "SYSTEM_PAPER_PUBLIC_KLINE_BOUNDARY_INVALID"
                )
            if previous_close is not None and opened != previous_close + timedelta(
                milliseconds=1
            ):
                raise SystemPaperPublicInputError(
                    "SYSTEM_PAPER_PUBLIC_KLINE_BOUNDARY_INVALID"
                )
            previous_close = closed
        if previous_close != scheduled - timedelta(milliseconds=1):
            raise SystemPaperPublicInputError(
                "SYSTEM_PAPER_PUBLIC_KLINE_BOUNDARY_INVALID"
            )
        bbo = {
            "bid_price": market["bbo"]["bid_price"],
            "ask_price": market["bbo"]["ask_price"],
        }
    except SystemPaperPublicInputError:
        raise
    except (KeyError, TypeError, ValueError, OfflinePaperError) as error:
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_CAPTURE_INVALID"
        ) from error
    bundle: Dict[str, Any] = {
        "bundle_hash": "0" * 64,
        "provider": plan["market_data_policy"]["provider"],
        "scheduled_for": scheduled_text,
        "captured_at": captured_at,
        "instrument_metadata_schema_version": schema_version,
        "instrument_metadata": metadata,
        "closed_4h_klines": klines,
        "bbo": bbo,
        "source_receipts": receipts,
    }
    bundle = json.loads(canonical_json(bundle))
    bundle["bundle_hash"] = artifact_self_hash(bundle, "bundle_hash")
    return bundle


def load_system_paper_market_bundle_bytes(body: bytes) -> Dict[str, Any]:
    """Load and independently replay one canonical market bundle."""

    value = dict(_strict_json_bytes(body))
    if tuple(_validator().iter_errors(value)):
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_BUNDLE_SCHEMA_INVALID"
        )
    if value.get("bundle_hash") != artifact_self_hash(value, "bundle_hash"):
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_BUNDLE_HASH_MISMATCH"
        )
    try:
        capture = replay_offline_paper_capture(value["source_receipts"])
        replayed = build_system_paper_market_bundle(
            plan=build_system_paper_plan(),
            scheduled_for=value["scheduled_for"],
            capture=capture,
        )
    except (KeyError, TypeError, ValueError, OfflinePaperError) as error:
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_BUNDLE_SOURCE_REPLAY_INVALID"
        ) from error
    if canonical_json(replayed) != canonical_json(value):
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_BUNDLE_REPLAY_MISMATCH"
        )
    return value


def capture_system_paper_input(
    request: object,
    *,
    transport=None,
    clock=None,
):
    """Capture exactly the four frozen public inputs for one scheduler slot."""

    from .system_paper_scheduler import (
        SystemPaperInputCapture,
        SystemPaperInputRequest,
        SystemPaperSchedulePolicy,
    )

    plan = build_system_paper_plan()
    policy = SystemPaperSchedulePolicy.create(plan)
    if not isinstance(request, SystemPaperInputRequest):
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_REQUEST_INVALID"
        )
    try:
        slot = policy.slot_from_scheduled(request.scheduled_for)
        expected = SystemPaperInputRequest.for_slot(policy, slot)
    except (TypeError, ValueError) as error:
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_REQUEST_INVALID"
        ) from error
    if request != expected:
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_REQUEST_INVALID"
        )
    sampled_clock = clock or _utc_now
    try:
        issued = capture_offline_paper(
            OfflinePaperPlan.create("ETHUSDT"),
            transport or BinanceOfflinePaperTransport(clock=sampled_clock),
            recorded_at=sampled_clock,
        )
        bundle = build_system_paper_market_bundle(
            plan=plan,
            scheduled_for=request.scheduled_for,
            capture=issued,
        )
    except SystemPaperPublicInputError:
        raise
    except (OfflinePaperError, TypeError, ValueError) as error:
        raise SystemPaperPublicInputError(
            "SYSTEM_PAPER_PUBLIC_CAPTURE_FAILED"
        ) from error
    capture_attempt_id = stable_id(
        "system_paper_capture",
        {
            "plan_hash": request.plan_hash,
            "slot_id": request.slot_id,
            "scheduled_for": request.scheduled_for,
            "bundle_hash": bundle["bundle_hash"],
        },
    )
    return SystemPaperInputCapture(
        public_market_bundle=bundle,
        capture_attempt_id=capture_attempt_id,
        captured_at=bundle["captured_at"],
        request_families=request.request_families,
        network_request_count=4,
    )
