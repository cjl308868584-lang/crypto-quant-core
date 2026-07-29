"""Preregistered economic measurement plan for challenger episodes."""

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .challenger_first_slot_receipt import (
    challenger_first_slot_receipt_hash,
)
from .challenger_forward import challenger_decision_reasons
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-episode-economic-plan-v1.schema.json"
_ZERO_HASH = "0" * 64
_MINIMUM_HOLD = datetime(2026, 7, 29, 8, tzinfo=timezone.utc)
_SOURCE_RECEIPT_ID = (
    "challenger_first_slot_receipt_"
    "fcc86fe447ab8b2728a9bcd80371c26c9"
    "a30f59cec0b01306b278392b28d3c2b"
)
_SOURCE_RECEIPT_HASH = (
    "76acd1f21dbd0f4c71b45213a4d4d3983f7c3707ac77006b56da2675ecfa9521"
)
_SOURCE_FILE_SHA256 = (
    "b1b03bbe584386d3199cef3561fe22b4c92c3f359429ec43838d2b00a9566e43"
)
_EXPECTED_ENTRY_MINUTE = "2026-07-29T00:03:00.000Z"
_MAX_PLAN_BYTES = 256 * 1024


class ChallengerEpisodeEconomicPlanError(ValueError):
    """The preregistered economic plan failed closed."""

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
            raise ChallengerEpisodeEconomicPlanError(
                "CHALLENGER_EPISODE_ECONOMIC_TIME_INVALID"
            ) from error
    else:
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_TIME_INVALID"
        )
    return converted, rendered


def next_strict_utc_minute(value: object) -> str:
    """Return the first whole UTC minute strictly after a timestamp."""

    parsed, _ = _utc(value)
    return utc_datetime(
        parsed.replace(second=0, microsecond=0) + timedelta(minutes=1)
    )


def challenger_episode_economic_policy() -> Dict[str, Any]:
    """Return the frozen source, fill, cost, and calculation contract."""

    contract = {
        "policy_version": "CHALLENGER_EPISODE_ECONOMIC_PROXY_V1",
        "direction": "LONG",
        "provider": "BINANCE_PUBLIC_DATA",
        "market": "SPOT",
        "symbol": "ETHUSDT",
        "interval": "1m",
        "archive_period_kind": "DAILY",
        "execution_minute_rule": (
            "FIRST_WHOLE_UTC_MINUTE_STRICTLY_AFTER_DECISION_RECORDED_AT"
        ),
        "entry_source_field": "high",
        "exit_source_field": "low",
        "reference_capital_usdt": "1000",
        "price_tick_usdt": "0.01",
        "quantity_step_eth": "0.0001",
        "slippage_rate_per_side": "0.001",
        "assumed_taker_fee_rate_per_side": "0.0015",
        "fill_policy": "OFFICIAL_DAILY_1M_WORST_BAR_PLUS_10BPS_V1",
        "cost_policy": "ASSUMED_TAKER_15BPS_PER_SIDE_V1",
        "entry_fill_formula": (
            "ROUND_UP(entry_minute_high*(1+0.001),0.01)"
        ),
        "exit_fill_formula": (
            "ROUND_DOWN(exit_minute_low*(1-0.001),0.01)"
        ),
        "quantity_formula": "ROUND_DOWN(1000/entry_fill,0.0001)",
        "entry_fee_formula": "entry_fill*quantity*0.0015",
        "exit_fee_formula": "exit_fill*quantity*0.0015",
        "gross_pnl_formula": "(exit_fill-entry_fill)*quantity",
        "net_pnl_formula": "gross_pnl-entry_fee-exit_fee",
        "net_return_formula": "net_pnl/1000",
        "positive_label_rule": "1_IF_NET_RETURN_STRICTLY_GREATER_THAN_0",
        "decimal_arithmetic_only": True,
        "binary_float_allowed": False,
        "historical_fallback_allowed": False,
    }
    return {**contract, "policy_hash": business_hash(contract)}


def _source_receipt_valid(
    receipt: object, *, source_file_sha256: object
) -> bool:
    if not isinstance(receipt, Mapping):
        return False
    try:
        first = receipt["state"]["first_decision"]
        state_after = first["state_after"]
        return (
            source_file_sha256 == _SOURCE_FILE_SHA256
            and receipt["receipt_id"] == _SOURCE_RECEIPT_ID
            and receipt["receipt_hash"] == _SOURCE_RECEIPT_HASH
            and receipt["receipt_hash"]
            == challenger_first_slot_receipt_hash(receipt)
            and receipt["observation_status"]
            == "FIRST_SLOT_RECORDED_VERIFIED"
            and first["action"] == "ENTER_LONG"
            and first["sequence"] == 1
            and first["scheduled_for"]
            == "2026-07-29T00:00:00.000Z"
            and not challenger_decision_reasons(
                first, previous_decision=None
            )
            and state_after["position_state"] == "LONG"
            and state_after["episode_id_or_null"]
            == "challenger_episode_"
            "45c86b2c0c1610d890c2d956915803c4"
            "b375b2838a66215f3f87311c8342be91"
            and next_strict_utc_minute(first["recorded_at"])
            == _EXPECTED_ENTRY_MINUTE
        )
    except (
        ChallengerEpisodeEconomicPlanError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return False


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def challenger_episode_economic_plan_hash(
    plan: Mapping[str, Any],
) -> str:
    return artifact_self_hash(plan, "plan_hash")


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "source_receipt_hash": plan["source_first_slot_receipt"][
            "receipt_hash"
        ],
        "first_decision_hash": plan["first_episode"][
            "entry_decision_hash"
        ],
        "entry_execution_minute": plan["first_episode"][
            "entry_execution_minute"
        ],
        "economic_policy_hash": plan["economic_policy"]["policy_hash"],
        "registered_at": plan["registered_at"],
    }


def build_challenger_episode_economic_plan(
    *,
    first_slot_receipt: Mapping[str, Any],
    source_file_sha256: str,
    registered_at: object,
) -> Dict[str, Any]:
    """Build the pre-outcome plan without fetching or accepting prices."""

    registered, registered_text = _utc(registered_at)
    if not _source_receipt_valid(
        first_slot_receipt,
        source_file_sha256=source_file_sha256,
    ):
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_SOURCE_INVALID"
        )
    first = first_slot_receipt["state"]["first_decision"]
    if (
        registered
        < _utc(first_slot_receipt["observed_at"])[0]
        or registered >= _MINIMUM_HOLD
    ):
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_REGISTRATION_TIME_INVALID"
        )
    policy = challenger_episode_economic_policy()
    plan = {
        "$schema": "./challenger-episode-economic-plan-v1.schema.json",
        "schema_version": "1.0.0",
        "plan_id": "challenger_episode_economic_plan_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "registered_at": registered_text,
        "design_commit": "dd3ab06",
        "package_baseline": "0.36.0",
        "source_first_slot_receipt": {
            "receipt_id": first_slot_receipt["receipt_id"],
            "receipt_hash": first_slot_receipt["receipt_hash"],
            "file_sha256": source_file_sha256,
            "observed_at": first_slot_receipt["observed_at"],
        },
        "first_episode": {
            "episode_id": first["state_after"]["episode_id_or_null"],
            "entry_decision_id": first["decision_id"],
            "entry_decision_hash": first["decision_hash"],
            "entry_scheduled_for": first["scheduled_for"],
            "entry_recorded_at": first["recorded_at"],
            "entry_execution_minute": next_strict_utc_minute(
                first["recorded_at"]
            ),
            "minimum_hold_until": first["state_after"][
                "minimum_hold_until_or_null"
            ],
            "vertical_exit_at": first["state_after"][
                "vertical_exit_at_or_null"
            ],
            "exit_execution_minute_rule": policy[
                "execution_minute_rule"
            ],
        },
        "source_contract": {
            "request_constructor": (
                "ALLOWLISTED_HISTORICAL_ARCHIVE_REQUEST"
            ),
            "archive_base": (
                "https://data.binance.vision/data/spot/daily/"
                "klines/ETHUSDT/1m/"
            ),
            "archive_and_checksum_required": True,
            "complete_daily_row_count": 1440,
            "exact_selected_raw_row_required": True,
            "third_party_or_rest_fallback_allowed": False,
            "entry_exit_same_day_source_count": 1,
            "entry_exit_cross_day_source_count": 2,
        },
        "economic_policy": policy,
        "calculation_order": [
            "ENTRY_EXECUTION_MINUTE",
            "EXIT_EXECUTION_MINUTE",
            "ENTRY_FILL",
            "EXIT_FILL",
            "QUANTITY",
            "ENTRY_NOTIONAL",
            "EXIT_NOTIONAL",
            "ENTRY_FEE",
            "EXIT_FEE",
            "GROSS_PNL",
            "NET_PNL",
            "NET_RETURN",
            "POSITIVE_LABEL",
        ],
        "status": (
            "PREREGISTERED_WAITING_FIRST_EPISODE_COMPLETION_AND_DAILY_ARCHIVE"
        ),
        "authority": {
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "price_override_allowed": False,
            "time_override_allowed": False,
            "fee_override_allowed": False,
        },
        "eligibility": {
            "measurement_plan": "PREREGISTERED_BEFORE_OUTCOME",
            "execution": "INELIGIBLE_PROXY_NOT_REAL_FILL",
            "paper": "INELIGIBLE_NO_COMPLETED_EPISODE",
            "release_oos": "INELIGIBLE_FORWARD_COLLECTION_ONLY",
            "profitability": "INELIGIBLE",
        },
        "warnings": [
            "NO_OUTCOME_OR_EXIT_PRICE_WAS_OBSERVED",
            "NO_MARKET_REQUEST_WAS_MADE",
            "DAILY_ARCHIVE_ROWS_WILL_BE_EXECUTION_PROXIES_NOT_REAL_FILLS",
            "ARCHIVE_OUTCOME_SOURCE_IS_NOT_PIT_MARKET_INPUT",
            "SINGLE_EPISODE_CANNOT_ESTABLISH_EDGE",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    plan["plan_id"] = stable_id(
        "challenger_episode_economic_plan", _identity(plan)
    )
    plan["plan_hash"] = challenger_episode_economic_plan_hash(plan)
    if tuple(_validator().iter_errors(plan)):
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_PLAN_INVALID"
        )
    return plan


def challenger_episode_economic_plan_reasons(
    plan: Mapping[str, Any],
    *,
    first_slot_receipt: Mapping[str, Any],
    source_file_sha256: str,
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(plan)):
            reasons.append(
                "CHALLENGER_EPISODE_ECONOMIC_PLAN_SCHEMA_INVALID"
            )
        if plan.get(
            "plan_hash"
        ) != challenger_episode_economic_plan_hash(plan):
            reasons.append(
                "CHALLENGER_EPISODE_ECONOMIC_PLAN_HASH_MISMATCH"
            )
        rebuilt = build_challenger_episode_economic_plan(
            first_slot_receipt=first_slot_receipt,
            source_file_sha256=source_file_sha256,
            registered_at=plan["registered_at"],
        )
        if business_hash(rebuilt) != business_hash(plan):
            reasons.append(
                "CHALLENGER_EPISODE_ECONOMIC_PLAN_SEMANTIC_MISMATCH"
            )
    except (
        ChallengerEpisodeEconomicPlanError,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append(
            "CHALLENGER_EPISODE_ECONOMIC_PLAN_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def publish_challenger_episode_economic_plan(
    *,
    plan: Mapping[str, Any],
    first_slot_receipt: Mapping[str, Any],
    source_file_sha256: str,
    output_path: Path,
) -> None:
    if challenger_episode_economic_plan_reasons(
        plan,
        first_slot_receipt=first_slot_receipt,
        source_file_sha256=source_file_sha256,
    ):
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_PLAN_INVALID"
        )
    path = Path(output_path).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_OUTPUT_INVALID"
        )
    path = path.resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        _publish_exact(path, canonical_json(plan).encode("utf-8"))
    except ValueError as error:
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_PLAN_CONFLICT"
        ) from error


def load_challenger_episode_economic_plan(
    *,
    plan_path: Path,
    first_slot_receipt: Mapping[str, Any],
    source_file_sha256: str,
) -> Mapping[str, Any]:
    try:
        path = Path(plan_path).expanduser().resolve(strict=True)
        status = path.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size > _MAX_PLAN_BYTES
        ):
            raise ValueError
        plan = _strict_json_bytes(path.read_bytes())
    except Exception as error:
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_PLAN_READ_FAILED"
        ) from error
    if challenger_episode_economic_plan_reasons(
        plan,
        first_slot_receipt=first_slot_receipt,
        source_file_sha256=source_file_sha256,
    ):
        raise ChallengerEpisodeEconomicPlanError(
            "CHALLENGER_EPISODE_ECONOMIC_PLAN_INVALID"
        )
    return plan
