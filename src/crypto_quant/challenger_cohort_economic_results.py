"""Deterministic economic results for every verified Challenger cohort Episode."""

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from decimal import (
    Context,
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_FLOOR,
    localcontext,
)
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .challenger_cohort_daily_archive import (
    ChallengerCohortDailyArchiveError,
    _discover_episode_receipts,
    _episode_filename,
    _load_day,
    _request,
    _required_minutes,
    _secure_directory,
    load_challenger_cohort_daily_archives,
)
from .challenger_episode_cohort_plan import challenger_episode_cohort_plan_hash
from .challenger_episode_economic_plan import (
    challenger_episode_economic_plan_hash,
    challenger_episode_economic_policy,
    next_strict_utc_minute,
)
from .challenger_cohort_episode_receipt import _read_exact_plan
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes
from .research_execution import ResearchExecutionError, _archive_rows


_RESULT_SCHEMA = "challenger-cohort-episode-economic-result-v1.schema.json"
_INDEX_SCHEMA = "challenger-cohort-economic-result-index-v1.schema.json"
_ZERO_HASH = "0" * 64
_DESIGN_COMMIT = "e687558"
_PLAN_ID = (
    "challenger_episode_cohort_plan_"
    "56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c"
)
_PLAN_HASH = "20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201"
_PLAN_FILE_SHA256 = "a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff"
_ECONOMIC_PLAN_ID = (
    "challenger_episode_economic_plan_"
    "e5c86696889d209373ce536ee0f54be72e59d7de96b6868cd5ab0358491985a4"
)
_ECONOMIC_PLAN_HASH = "fa43e1bb24ac0e9d70c82a3d09f03ca43a5f99c429f43e6c67d6e68029732831"
_ECONOMIC_PLAN_FILE_SHA256 = (
    "f22cb582a7df38e14220fca75359f6290af2fdb5896e5829ba5d7fd805cf54da"
)
_POLICY_HASH = "32c81160e936caf4253e0eabe46104fde5f6b747e0525fa2ea916c028dea82f9"
_EPISODE_DIRECTORY = "challenger-cohort-episode-receipts"
_RESULT_DIRECTORY = "challenger-cohort-economic-results"
_INDEX_DIRECTORY = "challenger-cohort-economic-result-index"
_MAX_PLAN_BYTES = 256 * 1024
_MAX_RECEIPT_BYTES = 64 * 1024 * 1024
_MAX_RESULT_BYTES = 2 * 1024 * 1024
_MAX_INDEX_BYTES = 8 * 1024 * 1024
_CONTEXT = Context(prec=50)
_ONE = Decimal("1")


class ChallengerCohortEconomicResultError(ValueError):
    """A cohort economic input, result, index, or publication failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=2)
def _validator(schema_name: str) -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", schema_name)
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
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_TIME_INVALID"
        )
    return converted, rendered


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_NUMBER_INVALID"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_NUMBER_INVALID"
        ) from error
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_NUMBER_INVALID"
        )
    return parsed


def _round_up(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _round_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _secure_json(
    path: Path,
    maximum_bytes: int,
    modes: Sequence[int],
) -> Tuple[Mapping[str, Any], bytes]:
    try:
        requested = Path(path).expanduser()
        status = requested.lstat()
        if (
            not requested.is_absolute()
            or stat.S_ISLNK(status.st_mode)
            or not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) not in modes
            or status.st_size <= 0
            or status.st_size > maximum_bytes
            or requested.resolve(strict=True) != requested.absolute()
        ):
            raise ValueError
        body = requested.read_bytes()
        value = _strict_json_bytes(body[:-1] if body.endswith(b"\n") else body)
        if not isinstance(value, Mapping):
            raise ValueError
        return value, body
    except Exception as error:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_INPUT_INVALID"
        ) from error


def read_exact_economic_plan(path: Path) -> Tuple[Mapping[str, Any], str]:
    plan, body = _secure_json(path, _MAX_PLAN_BYTES, (0o600, 0o644))
    file_sha256 = hashlib.sha256(body).hexdigest()
    policy = challenger_episode_economic_policy()
    try:
        if (
            file_sha256 != _ECONOMIC_PLAN_FILE_SHA256
            or plan["plan_id"] != _ECONOMIC_PLAN_ID
            or plan["plan_hash"] != _ECONOMIC_PLAN_HASH
            or plan["plan_hash"] != challenger_episode_economic_plan_hash(plan)
            or plan["economic_policy"] != policy
            or policy["policy_hash"] != _POLICY_HASH
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_PLAN_INVALID"
        ) from error
    return plan, file_sha256


def _plan_binding(
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
    economic_plan: Mapping[str, Any],
    economic_plan_file_sha256: str,
) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    policy = challenger_episode_economic_policy()
    measurement = cohort_plan.get("measurement_binding")
    expected_measurement = {
        "economic_plan_id": _ECONOMIC_PLAN_ID,
        "economic_plan_hash": _ECONOMIC_PLAN_HASH,
        "economic_plan_file_sha256": _ECONOMIC_PLAN_FILE_SHA256,
        "economic_policy_hash": _POLICY_HASH,
        "execution_minute_rule": policy["execution_minute_rule"],
        "entry_source_field": policy["entry_source_field"],
        "exit_source_field": policy["exit_source_field"],
        "slippage_rate_per_side": policy["slippage_rate_per_side"],
        "assumed_taker_fee_rate_per_side": policy[
            "assumed_taker_fee_rate_per_side"
        ],
        "reference_capital_usdt": policy["reference_capital_usdt"],
        "price_tick_usdt": policy["price_tick_usdt"],
        "quantity_step_eth": policy["quantity_step_eth"],
        "decimal_arithmetic_only": True,
    }
    if (
        cohort_plan_file_sha256 != _PLAN_FILE_SHA256
        or cohort_plan.get("plan_id") != _PLAN_ID
        or cohort_plan.get("plan_hash") != _PLAN_HASH
        or cohort_plan.get("plan_hash")
        != challenger_episode_cohort_plan_hash(cohort_plan)
        or economic_plan_file_sha256 != _ECONOMIC_PLAN_FILE_SHA256
        or economic_plan.get("plan_id") != _ECONOMIC_PLAN_ID
        or economic_plan.get("plan_hash") != _ECONOMIC_PLAN_HASH
        or economic_plan.get("economic_policy") != policy
        or measurement != expected_measurement
    ):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_PLAN_BINDING_INVALID"
        )
    return (
        {
            "plan_id": _PLAN_ID,
            "plan_hash": _PLAN_HASH,
            "plan_file_sha256": _PLAN_FILE_SHA256,
        },
        {
            "plan_id": _ECONOMIC_PLAN_ID,
            "plan_hash": _ECONOMIC_PLAN_HASH,
            "plan_file_sha256": _ECONOMIC_PLAN_FILE_SHA256,
            "economic_policy_hash": _POLICY_HASH,
        },
    )


def discover_episode_records(
    *,
    receipt_output_root: Path,
    cohort_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    receipt_loader=None,
) -> Tuple[Mapping[str, Any], ...]:
    receipts = _discover_episode_receipts(
        receipt_output_root=receipt_output_root,
        cohort_plan_path=cohort_plan_path,
        install_receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        receipt_loader=receipt_loader,
    )
    if not receipts:
        return ()
    directory = (
        Path(receipt_output_root).expanduser().resolve(strict=True)
        / _EPISODE_DIRECTORY
    )
    records = []
    for receipt in receipts:
        path = directory / _episode_filename(receipt)
        _value, body = _secure_json(path, _MAX_RECEIPT_BYTES, (0o600,))
        if _value != receipt:
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_RECEIPT_BYTES_INVALID"
            )
        records.append(
            {
                "receipt": receipt,
                "path": path,
                "file_sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    return tuple(records)


def load_archive_records(
    *,
    cohort_plan_path: Path,
    episode_receipt_output_root: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    archive_output_root: Path,
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
    receipt_loader=None,
) -> Mapping[str, Mapping[str, Any]]:
    archives = load_challenger_cohort_daily_archives(
        cohort_plan_path=cohort_plan_path,
        episode_receipt_output_root=episode_receipt_output_root,
        install_receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        archive_output_root=archive_output_root,
        receipt_loader=receipt_loader,
    )
    records = {}
    for period, (archive_bytes, checksum_bytes, retrieved_at) in archives.items():
        loaded = _load_day(
            output_root=archive_output_root,
            period=period,
            plan=cohort_plan,
            plan_file_sha256=cohort_plan_file_sha256,
        )
        if loaded is None:
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_ARCHIVE_SET_INCOMPLETE"
            )
        receipt, loaded_archive, loaded_checksum = loaded
        if (
            loaded_archive != archive_bytes
            or loaded_checksum != checksum_bytes
            or receipt["retrieved_at"] != retrieved_at
        ):
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_ARCHIVE_RELOAD_MISMATCH"
            )
        day_root = Path(archive_output_root).expanduser().resolve(strict=True) / (
            "challenger-cohort-daily-archives"
        ) / period
        receipt_path = day_root / "receipt.json"
        _receipt_value, receipt_bytes = _secure_json(
            receipt_path, 512 * 1024, (0o600,)
        )
        if _receipt_value != receipt:
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_ARCHIVE_RECEIPT_INVALID"
            )
        start = datetime.strptime(period, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        try:
            csv_bytes, rows, row_hashes, excluded = _archive_rows(
                request=_request(period),
                archive_bytes=archive_bytes,
                checksum_bytes=checksum_bytes,
                start=start,
                end=end,
            )
        except ResearchExecutionError as error:
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_ARCHIVE_INVALID"
            ) from error
        if len(rows) != 1440 or excluded or len(row_hashes) != 1440:
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_ARCHIVE_COVERAGE_INVALID"
            )
        records[period] = {
            "receipt": receipt,
            "receipt_file_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "archive_bytes": archive_bytes,
            "checksum_bytes": checksum_bytes,
            "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
            "rows": rows,
        }
    return records


def challenger_cohort_episode_economic_result_hash(result: Mapping[str, Any]) -> str:
    return artifact_self_hash(result, "result_hash")


def _result_identity(result: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "cohort_plan_hash": result["cohort_plan"]["plan_hash"],
        "episode_receipt_hash": result["episode_receipt"]["receipt_hash"],
        "entry_source_row_hash": result["execution_proxy"]["entry_source_row_hash"],
        "exit_source_row_hash": result["execution_proxy"]["exit_source_row_hash"],
        "economic_policy_hash": result["economic_plan"]["economic_policy_hash"],
        "evaluated_at": result["evaluated_at"],
    }


def _selected_row(record: Mapping[str, Any], minute: str) -> Mapping[str, Any]:
    parsed, rendered = _utc(minute)
    row = record["rows"].get(parsed)
    if not isinstance(row, Mapping) or row.get("open_time") != rendered:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_ROW_MISSING"
        )
    return row


def build_challenger_cohort_episode_economic_result(
    *,
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
    economic_plan: Mapping[str, Any],
    economic_plan_file_sha256: str,
    episode_record: Mapping[str, Any],
    archive_records: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    cohort_binding, economic_binding = _plan_binding(
        cohort_plan,
        cohort_plan_file_sha256,
        economic_plan,
        economic_plan_file_sha256,
    )
    receipt = episode_record["receipt"]
    episode = receipt["episode"]
    entry_minute = next_strict_utc_minute(episode["entry_recorded_at"])
    exit_minute = next_strict_utc_minute(episode["exit_recorded_at"])
    periods = tuple(sorted({entry_minute[:10], exit_minute[:10]}))
    if not set(periods).issubset(archive_records):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_ARCHIVE_SET_INCOMPLETE"
        )
    entry_row = _selected_row(archive_records[entry_minute[:10]], entry_minute)
    exit_row = _selected_row(archive_records[exit_minute[:10]], exit_minute)
    policy = economic_plan["economic_policy"]
    with localcontext(_CONTEXT):
        capital = _decimal(policy["reference_capital_usdt"], positive=True)
        tick = _decimal(policy["price_tick_usdt"], positive=True)
        step = _decimal(policy["quantity_step_eth"], positive=True)
        slippage = _decimal(policy["slippage_rate_per_side"])
        fee_rate = _decimal(policy["assumed_taker_fee_rate_per_side"])
        entry_source = _decimal(entry_row["high"], positive=True)
        exit_source = _decimal(exit_row["low"], positive=True)
        entry_fill = _round_up(entry_source * (_ONE + slippage), tick)
        exit_fill = _round_down(exit_source * (_ONE - slippage), tick)
        quantity = _round_down(capital / entry_fill, step)
        if exit_fill <= 0 or quantity <= 0:
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_CALCULATION_INVALID"
            )
        entry_notional = entry_fill * quantity
        exit_notional = exit_fill * quantity
        entry_fee = entry_notional * fee_rate
        exit_fee = exit_notional * fee_rate
        gross = (exit_fill - entry_fill) * quantity
        net = gross - entry_fee - exit_fee
        net_return = net / capital
    sources = []
    evaluated_at = max(
        archive_records[period]["receipt"]["retrieved_at"] for period in periods
    )
    for period in periods:
        record = archive_records[period]
        day_receipt = record["receipt"]
        selected = []
        if period == entry_minute[:10]:
            selected.append(entry_row)
        if period == exit_minute[:10] and exit_minute != entry_minute:
            selected.append(exit_row)
        sources.append(
            {
                "period": period,
                "receipt_id": day_receipt["receipt_id"],
                "receipt_hash": day_receipt["receipt_hash"],
                "receipt_file_sha256": record["receipt_file_sha256"],
                "retrieved_at": day_receipt["retrieved_at"],
                "archive_sha256": day_receipt["source"]["archive_sha256"],
                "checksum_file_sha256": day_receipt["source"][
                    "checksum_file_sha256"
                ],
                "csv_sha256": day_receipt["source"]["csv_sha256"],
                "csv_row_count": day_receipt["source"]["csv_row_count"],
                "source_rows_root_hash": day_receipt["source"][
                    "source_rows_root_hash"
                ],
                "selected_rows": selected,
            }
        )
    result = {
        "$schema": "./challenger-cohort-episode-economic-result-v1.schema.json",
        "schema_version": "1.0.0",
        "result_id": "challenger_cohort_episode_economic_result_" + _ZERO_HASH,
        "result_hash": _ZERO_HASH,
        "evaluated_at": evaluated_at,
        "design_commit": _DESIGN_COMMIT,
        "package_baseline": "0.46.0",
        "cohort_plan": cohort_binding,
        "economic_plan": economic_binding,
        "episode_receipt": {
            "receipt_id": receipt["receipt_id"],
            "receipt_hash": receipt["receipt_hash"],
            "receipt_file_sha256": episode_record["file_sha256"],
            "ordinal": episode["ordinal"],
            "episode_id": episode["episode_id"],
            "entry_scheduled_for": episode["entry_scheduled_for"],
            "validation_basis": "V0_45_LOADER_AND_ALL_INCLUSIVE_PREFIX",
        },
        "episode": {
            "entry_decision_id": episode["entry_decision_id"],
            "entry_decision_hash": episode["entry_decision_hash"],
            "entry_recorded_at": episode["entry_recorded_at"],
            "entry_execution_minute": entry_minute,
            "exit_decision_id": episode["exit_decision_id"],
            "exit_decision_hash": episode["exit_decision_hash"],
            "exit_action": episode["exit_action"],
            "exit_recorded_at": episode["exit_recorded_at"],
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
        "economics": {
            "reference_capital_usdt": canonical_decimal(capital),
            "entry_source_high": canonical_decimal(entry_source),
            "exit_source_low": canonical_decimal(exit_source),
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
        },
        "status": "DESCRIPTIVE_NO_EARLY_SUCCESS",
        "security_boundary": {
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "binary_float_allowed": False,
            "economic_override_allowed": False,
            "episode_selector_allowed": False,
        },
        "eligibility": {
            "execution": "INELIGIBLE_PROXY_NOT_REAL_FILL",
            "profitability": "INELIGIBLE_INTERIM_COHORT",
            "paper": "INELIGIBLE_FORWARD_RESEARCH_ONLY",
            "ai_comparison": "INELIGIBLE_NO_PAIRED_AI_EPISODE",
        },
        "warnings": [
            "ARCHIVE_FORWARD_OUTCOME_RESEARCH_ONLY",
            "DAILY_ARCHIVE_ROWS_ARE_EXECUTION_PROXIES_NOT_REAL_FILLS",
            "ASSUMED_TAKER_FEE_IS_NOT_ACCOUNT_ACTUAL_FEE",
            "ALL_COMPLETED_EPISODES_MUST_BE_RETAINED",
            "NO_EARLY_SUCCESS_OR_OPTIONAL_STOPPING",
            "NO_AI_ADVANTAGE_CLAIM",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    result["result_id"] = stable_id(
        "challenger_cohort_episode_economic_result", _result_identity(result)
    )
    result["result_hash"] = challenger_cohort_episode_economic_result_hash(result)
    if tuple(_validator(_RESULT_SCHEMA).iter_errors(result)):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_RESULT_SCHEMA_INVALID"
        )
    return result


def result_path(result_root: Path, result: Mapping[str, Any]) -> Path:
    stamp = (
        result["episode_receipt"]["entry_scheduled_for"]
        .replace("-", "")
        .replace(":", "")
        .replace(".000", "")
    )
    return (
        Path(result_root).expanduser().resolve()
        / _RESULT_DIRECTORY
        / f"{stamp}-{result['episode_receipt']['episode_id']}.json"
    )


def challenger_cohort_economic_result_reasons(
    result: Mapping[str, Any],
    *,
    build_arguments: Mapping[str, Any],
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator(_RESULT_SCHEMA).iter_errors(result)):
            reasons.append("CHALLENGER_COHORT_ECONOMIC_RESULT_SCHEMA_INVALID")
        if result.get(
            "result_hash"
        ) != challenger_cohort_episode_economic_result_hash(result):
            reasons.append("CHALLENGER_COHORT_ECONOMIC_RESULT_HASH_MISMATCH")
        if result.get("result_id") != stable_id(
            "challenger_cohort_episode_economic_result", _result_identity(result)
        ):
            reasons.append("CHALLENGER_COHORT_ECONOMIC_RESULT_ID_MISMATCH")
        rebuilt = build_challenger_cohort_episode_economic_result(**build_arguments)
        if business_hash(rebuilt) != business_hash(result):
            reasons.append("CHALLENGER_COHORT_ECONOMIC_RESULT_SEMANTIC_MISMATCH")
    except Exception:
        reasons.append("CHALLENGER_COHORT_ECONOMIC_RESULT_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def publish_result(
    *,
    result: Mapping[str, Any],
    output_path: Path,
    build_arguments: Mapping[str, Any],
) -> None:
    if challenger_cohort_economic_result_reasons(
        result, build_arguments=build_arguments
    ):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_RESULT_INVALID"
        )
    path = Path(output_path)
    try:
        _secure_directory(path.parent.parent, create=True)
        _secure_directory(path.parent, create=True)
        _publish_exact(path, canonical_json(result).encode("utf-8"))
    except (ChallengerCohortDailyArchiveError, ValueError) as error:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_RESULT_CONFLICT"
        ) from error


def load_result(
    *,
    output_path: Path,
    build_arguments: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], str]:
    result, body = _secure_json(output_path, _MAX_RESULT_BYTES, (0o600,))
    if challenger_cohort_economic_result_reasons(
        result, build_arguments=build_arguments
    ):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_RESULT_INVALID"
        )
    return result, hashlib.sha256(body).hexdigest()


def challenger_cohort_economic_result_index_hash(index: Mapping[str, Any]) -> str:
    return artifact_self_hash(index, "index_hash")


def _index_identity(index: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "cohort_plan_hash": index["cohort_plan"]["plan_hash"],
        "entry_count": index["entry_count"],
        "entries_root_hash": index["entries_root_hash"],
        "previous_index_hash": index["previous_index_hash"],
    }


def build_index_snapshot(
    *,
    cohort_binding: Mapping[str, Any],
    economic_binding: Mapping[str, Any],
    result_records: Sequence[Mapping[str, Any]],
    previous_index_hash: str,
) -> Dict[str, Any]:
    entries = []
    previous_entry = None
    for ordinal, record in enumerate(result_records, 1):
        result = record["result"]
        receipt = record["episode_record"]["receipt"]
        entry = {
            "ordinal": ordinal,
            "episode_id": receipt["episode"]["episode_id"],
            "entry_scheduled_for": receipt["episode"]["entry_scheduled_for"],
            "episode_receipt_id": receipt["receipt_id"],
            "episode_receipt_hash": receipt["receipt_hash"],
            "episode_receipt_file_sha256": record["episode_record"]["file_sha256"],
            "result_id": result["result_id"],
            "result_hash": result["result_hash"],
            "result_file_sha256": record["result_file_sha256"],
            "net_pnl_usdt": result["economics"]["net_pnl_usdt"],
            "net_return": result["economics"]["net_return"],
            "positive_label": result["economics"]["positive_label"],
        }
        if (
            entry["ordinal"] != receipt["episode"]["ordinal"]
            or (
                previous_entry is not None
                and entry["entry_scheduled_for"]
                <= previous_entry["entry_scheduled_for"]
            )
        ):
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_INDEX_ORDER_INVALID"
            )
        entries.append(entry)
        previous_entry = entry
    receipt_summary = [
        {
            "ordinal": entry["ordinal"],
            "episode_id": entry["episode_id"],
            "receipt_hash": entry["episode_receipt_hash"],
            "receipt_file_sha256": entry["episode_receipt_file_sha256"],
        }
        for entry in entries
    ]
    result_summary = [
        {
            "ordinal": entry["ordinal"],
            "episode_id": entry["episode_id"],
            "result_hash": entry["result_hash"],
            "result_file_sha256": entry["result_file_sha256"],
        }
        for entry in entries
    ]
    index = {
        "$schema": "./challenger-cohort-economic-result-index-v1.schema.json",
        "schema_version": "1.0.0",
        "index_id": "challenger_cohort_economic_result_index_" + _ZERO_HASH,
        "index_hash": _ZERO_HASH,
        "design_commit": _DESIGN_COMMIT,
        "package_baseline": "0.46.0",
        "cohort_plan": dict(cohort_binding),
        "economic_plan": dict(economic_binding),
        "entry_count": len(entries),
        "previous_index_hash": previous_index_hash,
        "episode_receipts_root_hash": business_hash(receipt_summary),
        "economic_results_root_hash": business_hash(result_summary),
        "entries_root_hash": business_hash(entries),
        "entries": entries,
        "status": "DESCRIPTIVE_NO_EARLY_SUCCESS",
        "eligibility": {
            "profitability": "INELIGIBLE_INTERIM_COHORT",
            "cumulative_evaluation": "INELIGIBLE_BEFORE_FIXED_TAIL_END",
        },
        "warnings": [
            "INDEX_IS_APPEND_ONLY_IMMUTABLE_CUMULATIVE_PREFIX",
            "ALL_COMPLETED_EPISODES_MUST_BE_RETAINED",
            "NO_EARLY_SUCCESS_OR_OPTIONAL_STOPPING",
            "NO_AI_ADVANTAGE_CLAIM",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    index["index_id"] = stable_id(
        "challenger_cohort_economic_result_index", _index_identity(index)
    )
    index["index_hash"] = challenger_cohort_economic_result_index_hash(index)
    if tuple(_validator(_INDEX_SCHEMA).iter_errors(index)):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_INDEX_SCHEMA_INVALID"
        )
    return index


def index_path(result_root: Path, index: Mapping[str, Any]) -> Path:
    return (
        Path(result_root).expanduser().resolve()
        / _INDEX_DIRECTORY
        / f"{index['entry_count']:04d}-{index['index_id']}.json"
    )


def load_existing_indexes(
    *,
    result_root: Path,
    cohort_binding: Mapping[str, Any],
    economic_binding: Mapping[str, Any],
    result_records: Sequence[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    root = Path(result_root).expanduser().resolve()
    directory = root / _INDEX_DIRECTORY
    if not directory.exists():
        return ()
    _secure_directory(root, create=False)
    _secure_directory(directory, create=False)
    paths = tuple(sorted(directory.iterdir(), key=lambda path: path.name))
    if len(paths) > len(result_records):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_INDEX_SET_INVALID"
        )
    indexes = []
    previous_hash = _ZERO_HASH
    for ordinal, path in enumerate(paths, 1):
        value, _body = _secure_json(path, _MAX_INDEX_BYTES, (0o600,))
        expected = build_index_snapshot(
            cohort_binding=cohort_binding,
            economic_binding=economic_binding,
            result_records=result_records[:ordinal],
            previous_index_hash=previous_hash,
        )
        if (
            path != index_path(root, expected)
            or value != expected
            or value["entry_count"] != ordinal
        ):
            raise ChallengerCohortEconomicResultError(
                "CHALLENGER_COHORT_ECONOMIC_INDEX_INVALID"
            )
        indexes.append(value)
        previous_hash = value["index_hash"]
    return tuple(indexes)


def publish_index(*, result_root: Path, index: Mapping[str, Any]) -> Path:
    path = index_path(result_root, index)
    try:
        _secure_directory(path.parent.parent, create=True)
        _secure_directory(path.parent, create=True)
        _publish_exact(path, canonical_json(index).encode("utf-8"))
    except (ChallengerCohortDailyArchiveError, ValueError) as error:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_INDEX_CONFLICT"
        ) from error
    value, _body = _secure_json(path, _MAX_INDEX_BYTES, (0o600,))
    if value != index:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_INDEX_RELOAD_MISMATCH"
        )
    return path


def validate_result_inventory(
    *,
    result_root: Path,
    expected_paths: Sequence[Path],
) -> None:
    root = Path(result_root).expanduser().resolve()
    directory = root / _RESULT_DIRECTORY
    if not directory.exists():
        return
    _secure_directory(root, create=False)
    _secure_directory(directory, create=False)
    actual = tuple(sorted(directory.iterdir(), key=lambda path: path.name))
    expected = tuple(sorted(expected_paths, key=lambda path: path.name))
    if actual != expected[: len(actual)]:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_RESULT_INVENTORY_INVALID"
        )


def publish_all_cohort_economic_results(
    *,
    cohort_plan_path: Path,
    economic_plan_path: Path,
    episode_receipt_output_root: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    archive_output_root: Path,
    result_output_root: Path,
    receipt_loader=None,
    after_result_hook=None,
) -> Mapping[str, Any]:
    cohort_plan, cohort_plan_file_sha256 = _read_exact_plan(cohort_plan_path)
    economic_plan, economic_plan_file_sha256 = read_exact_economic_plan(
        economic_plan_path
    )
    cohort_binding, economic_binding = _plan_binding(
        cohort_plan,
        cohort_plan_file_sha256,
        economic_plan,
        economic_plan_file_sha256,
    )
    episode_records = discover_episode_records(
        receipt_output_root=episode_receipt_output_root,
        cohort_plan_path=cohort_plan_path,
        install_receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        receipt_loader=receipt_loader,
    )
    if not episode_records:
        return {
            "status": "COHORT_ECONOMIC_RESULT_NO_COMPLETED_EPISODES",
            "episode_receipt_count": 0,
            "result_count": 0,
            "index_count": 0,
            "new_result_count": 0,
            "new_index_count": 0,
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
        }
    archive_records = load_archive_records(
        cohort_plan_path=cohort_plan_path,
        episode_receipt_output_root=episode_receipt_output_root,
        install_receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        archive_output_root=archive_output_root,
        cohort_plan=cohort_plan,
        cohort_plan_file_sha256=cohort_plan_file_sha256,
        receipt_loader=receipt_loader,
    )
    if set(archive_records) != set(
        _required_minutes(
            tuple(record["receipt"] for record in episode_records)
        )
    ):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_ARCHIVE_SET_INVALID"
        )
    builds = []
    expected_paths = []
    for episode_record in episode_records:
        arguments = {
            "cohort_plan": cohort_plan,
            "cohort_plan_file_sha256": cohort_plan_file_sha256,
            "economic_plan": economic_plan,
            "economic_plan_file_sha256": economic_plan_file_sha256,
            "episode_record": episode_record,
            "archive_records": archive_records,
        }
        result = build_challenger_cohort_episode_economic_result(**arguments)
        builds.append((arguments, result))
        expected_paths.append(result_path(result_output_root, result))
    validate_result_inventory(
        result_root=result_output_root, expected_paths=expected_paths
    )
    existing_result_count = 0
    result_records = []
    for (arguments, result), path, episode_record in zip(
        builds, expected_paths, episode_records
    ):
        if path.exists():
            loaded, file_sha256 = load_result(
                output_path=path, build_arguments=arguments
            )
            if loaded != result:
                raise ChallengerCohortEconomicResultError(
                    "CHALLENGER_COHORT_ECONOMIC_RESULT_CONFLICT"
                )
            existing_result_count += 1
        else:
            body = canonical_json(result).encode("utf-8")
            file_sha256 = hashlib.sha256(body).hexdigest()
        result_records.append(
            {
                "result": result,
                "result_file_sha256": file_sha256,
                "episode_record": episode_record,
                "build_arguments": arguments,
                "path": path,
            }
        )
    existing_indexes = load_existing_indexes(
        result_root=result_output_root,
        cohort_binding=cohort_binding,
        economic_binding=economic_binding,
        result_records=result_records,
    )
    if len(existing_indexes) > existing_result_count:
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_INDEX_WITHOUT_RESULT"
        )
    new_results = 0
    new_indexes = 0
    previous_hash = (
        existing_indexes[-1]["index_hash"] if existing_indexes else _ZERO_HASH
    )
    for ordinal, record in enumerate(result_records, 1):
        if ordinal > existing_result_count:
            publish_result(
                result=record["result"],
                output_path=record["path"],
                build_arguments=record["build_arguments"],
            )
            loaded, file_sha256 = load_result(
                output_path=record["path"],
                build_arguments=record["build_arguments"],
            )
            if loaded != record["result"]:
                raise ChallengerCohortEconomicResultError(
                    "CHALLENGER_COHORT_ECONOMIC_RESULT_RELOAD_MISMATCH"
                )
            record["result_file_sha256"] = file_sha256
            new_results += 1
            if after_result_hook is not None:
                after_result_hook(ordinal, record)
        if ordinal <= len(existing_indexes):
            previous_hash = existing_indexes[ordinal - 1]["index_hash"]
            continue
        index = build_index_snapshot(
            cohort_binding=cohort_binding,
            economic_binding=economic_binding,
            result_records=result_records[:ordinal],
            previous_index_hash=previous_hash,
        )
        publish_index(result_root=result_output_root, index=index)
        previous_hash = index["index_hash"]
        new_indexes += 1
    final_indexes = load_existing_indexes(
        result_root=result_output_root,
        cohort_binding=cohort_binding,
        economic_binding=economic_binding,
        result_records=result_records,
    )
    if len(final_indexes) != len(result_records):
        raise ChallengerCohortEconomicResultError(
            "CHALLENGER_COHORT_ECONOMIC_INDEX_SET_INCOMPLETE"
        )
    latest = final_indexes[-1]
    latest_path = index_path(result_output_root, latest)
    return {
        "status": "DESCRIPTIVE_NO_EARLY_SUCCESS",
        "episode_receipt_count": len(episode_records),
        "result_count": len(result_records),
        "index_count": len(final_indexes),
        "new_result_count": new_results,
        "new_index_count": new_indexes,
        "latest_index_id": latest["index_id"],
        "latest_index_hash": latest["index_hash"],
        "latest_index_path": str(latest_path),
        "market_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "state_write_count": 0,
        "runner_invocation_count": 0,
    }
