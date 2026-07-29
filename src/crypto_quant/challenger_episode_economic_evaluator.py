"""Offline evaluator for the preregistered first Challenger episode."""

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, localcontext
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal, canonical_json, stable_id, utc_datetime
from .challenger_episode_economic_plan import (
    challenger_episode_economic_plan_hash,
    challenger_episode_economic_policy,
    next_strict_utc_minute,
)
from .challenger_first_episode_receipt import (
    _identity as _completion_receipt_identity,
    _validator as _completion_receipt_validator,
    challenger_first_episode_receipt_hash,
)
from .challenger_forward import challenger_decision_reasons
from .evidence import artifact_self_hash
from .market_data import HistoricalArchiveRequest
from .research_corpus import _publish_exact, _strict_json_bytes
from .research_execution import ResearchExecutionError, _archive_rows, _request_payload


_SCHEMA = "challenger-episode-economic-result-v1.schema.json"
_ZERO_HASH = "0" * 64
_HASH = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT = Context(prec=50)
_ONE = Decimal("1")
_EXPECTED_PLAN_ID = (
    "challenger_episode_economic_plan_"
    "e5c86696889d209373ce536ee0f54be72e59d7de96b6868cd5ab0358491985a4"
)
_EXPECTED_PLAN_HASH = (
    "fa43e1bb24ac0e9d70c82a3d09f03ca43a5f99c429f43e6c67d6e68029732831"
)
_EXPECTED_PLAN_FILE_SHA256 = (
    "f22cb582a7df38e14220fca75359f6290af2fdb5896e5829ba5d7fd805cf54da"
)
_MAX_RESULT_BYTES = 2 * 1024 * 1024


class ChallengerEpisodeEconomicEvaluatorError(ValueError):
    """An evaluator input, calculation, or exact publication failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerEpisodeEconomicEvaluatorError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_TIME_INVALID"
            ) from error
    else:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_TIME_INVALID"
        )
    return converted, rendered


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_NUMBER_INVALID"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_NUMBER_INVALID"
        ) from error
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_NUMBER_INVALID"
        )
    return parsed


def _round_up(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _round_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _plan_valid(plan: object, plan_file_sha256: object) -> bool:
    if not isinstance(plan, Mapping):
        return False
    try:
        return (
            plan_file_sha256 == _EXPECTED_PLAN_FILE_SHA256
            and plan["plan_id"] == _EXPECTED_PLAN_ID
            and plan["plan_hash"] == _EXPECTED_PLAN_HASH
            and plan["plan_hash"] == challenger_episode_economic_plan_hash(plan)
            and plan["economic_policy"] == challenger_episode_economic_policy()
            and plan["status"]
            == "PREREGISTERED_WAITING_FIRST_EPISODE_COMPLETION_AND_DAILY_ARCHIVE"
            and plan["first_episode"]["entry_execution_minute"]
            == "2026-07-29T00:03:00.000Z"
        )
    except (KeyError, TypeError, ValueError):
        return False


def _completion_receipt_valid(
    receipt: object,
    *,
    receipt_file_sha256: object,
    plan: Mapping[str, Any],
) -> bool:
    if (
        not isinstance(receipt, Mapping)
        or not isinstance(receipt_file_sha256, str)
        or not _HASH.fullmatch(receipt_file_sha256)
    ):
        return False
    try:
        if tuple(_completion_receipt_validator().iter_errors(receipt)):
            return False
        if (
            receipt["receipt_hash"]
            != challenger_first_episode_receipt_hash(receipt)
            or receipt["receipt_id"]
            != stable_id(
                "challenger_first_episode_receipt",
                _completion_receipt_identity(receipt),
            )
            or receipt["observation_status"]
            != "FIRST_EPISODE_COMPLETED_VERIFIED"
            or receipt["security_boundary"]["network_request_count"] != 0
            or receipt["security_boundary"]["broker_request_count"] != 0
            or receipt["security_boundary"]["order_submission_count"] != 0
            or receipt["security_boundary"]["state_write_count"] != 0
        ):
            return False
        decisions = receipt["state"]["decisions"]
        if (
            not 3 <= len(decisions) <= 7
            or receipt["state"]["episode_decision_count"] != len(decisions)
            or receipt["state"]["decisions_root_hash"] != business_hash(decisions)
            or receipt["state"]["decision_chain_end_hash"]
            != decisions[-1]["decision_hash"]
        ):
            return False
        previous = None
        for decision in decisions:
            if challenger_decision_reasons(
                decision, previous_decision=previous
            ):
                return False
            previous = decision
        entry = decisions[0]
        exit_decision = decisions[-1]
        planned = plan["first_episode"]
        if (
            entry["decision_id"] != planned["entry_decision_id"]
            or entry["decision_hash"] != planned["entry_decision_hash"]
            or entry["recorded_at"] != planned["entry_recorded_at"]
            or entry["state_after"]["episode_id_or_null"]
            != planned["episode_id"]
            or next_strict_utc_minute(entry["recorded_at"])
            != planned["entry_execution_minute"]
            or exit_decision["action"]
            not in ("EXIT_LONG_SMA20", "EXIT_LONG_VERTICAL_24H")
            or exit_decision["state_after"]["position_state"] != "FLAT"
            or receipt["episode"]["episode_id"] != planned["episode_id"]
            or receipt["episode"]["exit_action"] != exit_decision["action"]
            or receipt["episode"]["exit_scheduled_for"]
            != exit_decision["scheduled_for"]
            or _utc(receipt["observed_at"])[0]
            < _utc(exit_decision["recorded_at"])[0]
        ):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def required_challenger_episode_archive_periods(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
) -> Tuple[str, ...]:
    """Return the only official DAILY periods allowed by the frozen times."""

    if not _plan_valid(plan, plan_file_sha256):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_PLAN_INVALID"
        )
    if not _completion_receipt_valid(
        completion_receipt,
        receipt_file_sha256=completion_receipt_file_sha256,
        plan=plan,
    ):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_RECEIPT_INVALID"
        )
    exit_minute = next_strict_utc_minute(
        completion_receipt["state"]["decisions"][-1]["recorded_at"]
    )
    periods = {
        plan["first_episode"]["entry_execution_minute"][:10],
        exit_minute[:10],
    }
    return tuple(sorted(periods))


def _daily_request(period: str) -> HistoricalArchiveRequest:
    try:
        parsed = datetime.strptime(period, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError) as error:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_PERIOD_INVALID"
        ) from error
    if not datetime(2026, 7, 29, tzinfo=timezone.utc) <= parsed <= datetime(
        2026, 7, 30, tzinfo=timezone.utc
    ):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_PERIOD_INVALID"
        )
    return HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="DAILY",
        period=period,
    )


def _verified_daily_source(
    *,
    period: str,
    archive_bytes: bytes,
    checksum_bytes: bytes,
    retrieved_at: str,
    required_open_times: Sequence[str],
) -> Dict[str, Any]:
    request = _daily_request(period)
    day_start = datetime.strptime(period, "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    day_end = day_start + timedelta(days=1)
    retrieved, retrieved_text = _utc(retrieved_at)
    if retrieved < day_end:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_ARCHIVE_EARLY"
        )
    try:
        csv_bytes, rows, row_hashes, excluded = _archive_rows(
            request=request,
            archive_bytes=archive_bytes,
            checksum_bytes=checksum_bytes,
            start=day_start,
            end=day_end,
        )
    except ResearchExecutionError as error:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_ARCHIVE_INVALID"
        ) from error
    expected = [
        day_start + timedelta(minutes=index) for index in range(1440)
    ]
    if (
        len(rows) != 1440
        or excluded
        or list(rows) != expected
        or len(row_hashes) != 1440
    ):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_ARCHIVE_COVERAGE_INVALID"
        )
    selected = []
    for value in required_open_times:
        parsed, rendered = _utc(value)
        if parsed.strftime("%Y-%m-%d") != period or parsed not in rows:
            raise ChallengerEpisodeEconomicEvaluatorError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_ROW_MISSING"
            )
        row = rows[parsed]
        if row["open_time"] != rendered:
            raise ChallengerEpisodeEconomicEvaluatorError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_ROW_INVALID"
            )
        selected.append(row)
    return {
        "request": _request_payload(request),
        "retrieved_at": retrieved_text,
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "checksum_file_sha256": hashlib.sha256(checksum_bytes).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "csv_row_count": len(rows),
        "first_open_time": utc_datetime(day_start),
        "last_open_time": utc_datetime(day_end - timedelta(minutes=1)),
        "source_rows_root_hash": business_hash(row_hashes),
        "selected_rows": selected,
    }


def challenger_episode_economic_result_hash(
    result: Mapping[str, Any],
) -> str:
    return artifact_self_hash(result, "result_hash")


def _result_identity(result: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "plan_hash": result["plan_binding"]["plan_hash"],
        "completion_receipt_hash": result["completion_receipt"][
            "receipt_hash"
        ],
        "entry_source_row_hash": result["execution_proxy"][
            "entry_source_row_hash"
        ],
        "exit_source_row_hash": result["execution_proxy"][
            "exit_source_row_hash"
        ],
        "economic_policy_hash": result["economic_policy_hash"],
        "evaluated_at": result["evaluated_at"],
    }


def build_challenger_episode_economic_result(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
    daily_archives: Mapping[str, Tuple[bytes, bytes, str]],
    evaluated_at: object,
) -> Dict[str, Any]:
    """Build a deterministic result from loader-verified, offline inputs."""

    periods = required_challenger_episode_archive_periods(
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        completion_receipt=completion_receipt,
        completion_receipt_file_sha256=completion_receipt_file_sha256,
    )
    if not isinstance(daily_archives, Mapping) or set(
        daily_archives
    ) != set(periods):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_ARCHIVE_SET_INVALID"
        )
    evaluated, evaluated_text = _utc(evaluated_at)
    decisions = completion_receipt["state"]["decisions"]
    entry_decision = decisions[0]
    exit_decision = decisions[-1]
    entry_minute = plan["first_episode"]["entry_execution_minute"]
    exit_minute = next_strict_utc_minute(exit_decision["recorded_at"])
    required_by_period: Dict[str, list] = {period: [] for period in periods}
    required_by_period[entry_minute[:10]].append(entry_minute)
    required_by_period[exit_minute[:10]].append(exit_minute)
    sources = []
    rows = {}
    for period in periods:
        value = daily_archives[period]
        if (
            not isinstance(value, tuple)
            or len(value) != 3
            or not isinstance(value[0], bytes)
            or not isinstance(value[1], bytes)
        ):
            raise ChallengerEpisodeEconomicEvaluatorError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_ARCHIVE_BYTES_INVALID"
            )
        source = _verified_daily_source(
            period=period,
            archive_bytes=value[0],
            checksum_bytes=value[1],
            retrieved_at=value[2],
            required_open_times=tuple(required_by_period[period]),
        )
        if evaluated < _utc(source["retrieved_at"])[0]:
            raise ChallengerEpisodeEconomicEvaluatorError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_TIME_INVALID"
            )
        sources.append(source)
        for row in source["selected_rows"]:
            rows[row["open_time"]] = row
    if evaluated < _utc(completion_receipt["observed_at"])[0]:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_TIME_INVALID"
        )
    entry_row = rows[entry_minute]
    exit_row = rows[exit_minute]
    policy = plan["economic_policy"]
    with localcontext(_CONTEXT):
        capital = _decimal(
            policy["reference_capital_usdt"], positive=True
        )
        tick = _decimal(policy["price_tick_usdt"], positive=True)
        step = _decimal(policy["quantity_step_eth"], positive=True)
        slippage = _decimal(policy["slippage_rate_per_side"])
        fee_rate = _decimal(
            policy["assumed_taker_fee_rate_per_side"]
        )
        entry_source_price = _decimal(entry_row["high"], positive=True)
        exit_source_price = _decimal(exit_row["low"], positive=True)
        entry_fill = _round_up(
            entry_source_price * (_ONE + slippage), tick
        )
        exit_fill = _round_down(
            exit_source_price * (_ONE - slippage), tick
        )
        quantity = _round_down(capital / entry_fill, step)
        if exit_fill <= 0 or quantity <= 0:
            raise ChallengerEpisodeEconomicEvaluatorError(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_CALCULATION_INVALID"
            )
        entry_notional = entry_fill * quantity
        exit_notional = exit_fill * quantity
        entry_fee = entry_notional * fee_rate
        exit_fee = exit_notional * fee_rate
        gross = (exit_fill - entry_fill) * quantity
        net = gross - entry_fee - exit_fee
        net_return = net / capital
    economics = {
        "reference_capital_usdt": canonical_decimal(capital),
        "entry_source_high": canonical_decimal(entry_source_price),
        "exit_source_low": canonical_decimal(exit_source_price),
        "entry_fill_price": canonical_decimal(entry_fill),
        "exit_fill_price": canonical_decimal(exit_fill),
        "filled_quantity_eth": canonical_decimal(quantity),
        "entry_notional_usdt": canonical_decimal(entry_notional),
        "exit_notional_usdt": canonical_decimal(exit_notional),
        "entry_fee_usdt": canonical_decimal(entry_fee),
        "exit_fee_usdt": canonical_decimal(exit_fee),
        "gross_pnl_usdt": canonical_decimal(gross),
        "net_pnl_usdt": canonical_decimal(net),
        "net_return": canonical_decimal(net_return),
        "positive_label": 1 if net_return > 0 else 0,
    }
    result = {
        "$schema": "./challenger-episode-economic-result-v1.schema.json",
        "schema_version": "1.0.0",
        "result_id": "challenger_episode_economic_result_" + _ZERO_HASH,
        "result_hash": _ZERO_HASH,
        "evaluated_at": evaluated_text,
        "design_commit": "17c7348",
        "package_baseline": "0.37.0",
        "plan_binding": {
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "plan_file_sha256": plan_file_sha256,
            "registered_at": plan["registered_at"],
        },
        "completion_receipt": {
            "receipt_id": completion_receipt["receipt_id"],
            "receipt_hash": completion_receipt["receipt_hash"],
            "receipt_file_sha256": completion_receipt_file_sha256,
            "observed_at": completion_receipt["observed_at"],
            "episode_id": completion_receipt["episode"]["episode_id"],
            "validation_basis": "V0_36_LOADER_AND_OFFLINE_SEMANTIC_REPLAY",
        },
        "episode": {
            "entry_decision_id": entry_decision["decision_id"],
            "entry_decision_hash": entry_decision["decision_hash"],
            "entry_recorded_at": entry_decision["recorded_at"],
            "entry_execution_minute": entry_minute,
            "exit_decision_id": exit_decision["decision_id"],
            "exit_decision_hash": exit_decision["decision_hash"],
            "exit_action": exit_decision["action"],
            "exit_recorded_at": exit_decision["recorded_at"],
            "exit_execution_minute": exit_minute,
        },
        "source_archives": sources,
        "execution_proxy": {
            "entry_source_row_hash": entry_row["source_row_hash"],
            "exit_source_row_hash": exit_row["source_row_hash"],
            "entry_source_field": "high",
            "exit_source_field": "low",
            "real_fill_claimed": False,
        },
        "economic_policy_hash": policy["policy_hash"],
        "calculation_order": list(plan["calculation_order"]),
        "economics": economics,
        "status": "COMPLETED_ARCHIVE_FORWARD_ECONOMIC_PROXY",
        "security_boundary": {
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "binary_float_allowed": False,
            "price_override_allowed": False,
            "time_override_allowed": False,
            "fee_override_allowed": False,
        },
        "eligibility": {
            "execution": "INELIGIBLE_PROXY_NOT_REAL_FILL",
            "paper": "INELIGIBLE_SINGLE_EPISODE",
            "release_oos": "INELIGIBLE_FORWARD_COLLECTION_ONLY",
            "profitability": "INELIGIBLE_SINGLE_EPISODE",
            "ai_comparison": "INELIGIBLE_NO_PAIRED_AI_EPISODE",
        },
        "warnings": [
            "ARCHIVE_FORWARD_OUTCOME_RESEARCH_ONLY",
            "DAILY_ARCHIVE_ROWS_ARE_EXECUTION_PROXIES_NOT_REAL_FILLS",
            "ASSUMED_TAKER_FEE_IS_NOT_ACCOUNT_ACTUAL_FEE",
            "SINGLE_EPISODE_CANNOT_ESTABLISH_EDGE",
            "POSITIVE_RESULT_DOES_NOT_PROVE_PROFITABILITY",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    result["result_id"] = stable_id(
        "challenger_episode_economic_result", _result_identity(result)
    )
    result["result_hash"] = challenger_episode_economic_result_hash(result)
    if tuple(_validator().iter_errors(result)):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_SCHEMA_INVALID"
        )
    return result


def challenger_episode_economic_result_reasons(
    result: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
    daily_archives: Mapping[str, Tuple[bytes, bytes, str]],
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(result)):
            reasons.append(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_SCHEMA_INVALID"
            )
        if result.get(
            "result_hash"
        ) != challenger_episode_economic_result_hash(result):
            reasons.append(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_HASH_MISMATCH"
            )
        if result.get("result_id") != stable_id(
            "challenger_episode_economic_result", _result_identity(result)
        ):
            reasons.append(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_ID_MISMATCH"
            )
        rebuilt = build_challenger_episode_economic_result(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            completion_receipt=completion_receipt,
            completion_receipt_file_sha256=completion_receipt_file_sha256,
            daily_archives=daily_archives,
            evaluated_at=result["evaluated_at"],
        )
        if business_hash(rebuilt) != business_hash(result):
            reasons.append(
                "CHALLENGER_EPISODE_ECONOMIC_RESULT_SEMANTIC_MISMATCH"
            )
    except (
        ChallengerEpisodeEconomicEvaluatorError,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def publish_challenger_episode_economic_result(
    *,
    result: Mapping[str, Any],
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
    daily_archives: Mapping[str, Tuple[bytes, bytes, str]],
    output_path: Path,
) -> None:
    if challenger_episode_economic_result_reasons(
        result,
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        completion_receipt=completion_receipt,
        completion_receipt_file_sha256=completion_receipt_file_sha256,
        daily_archives=daily_archives,
    ):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_INVALID"
        )
    path = Path(output_path).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_OUTPUT_INVALID"
        )
    path = path.resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        _publish_exact(path, canonical_json(result).encode("utf-8"))
    except ValueError as error:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_CONFLICT"
        ) from error


def load_challenger_episode_economic_result(
    *,
    result_path: Path,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
    daily_archives: Mapping[str, Tuple[bytes, bytes, str]],
) -> Mapping[str, Any]:
    try:
        path = Path(result_path).expanduser().resolve(strict=True)
        status = path.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size > _MAX_RESULT_BYTES
        ):
            raise ValueError
        result = _strict_json_bytes(path.read_bytes())
    except Exception as error:
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_READ_FAILED"
        ) from error
    if challenger_episode_economic_result_reasons(
        result,
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        completion_receipt=completion_receipt,
        completion_receipt_file_sha256=completion_receipt_file_sha256,
        daily_archives=daily_archives,
    ):
        raise ChallengerEpisodeEconomicEvaluatorError(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_INVALID"
        )
    return result
