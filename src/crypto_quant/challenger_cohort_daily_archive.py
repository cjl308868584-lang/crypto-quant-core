"""Shared official DAILY archives for all verified Challenger cohort Episodes."""

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .challenger_cohort_episode_receipt import (
    ChallengerCohortEpisodeReceiptError,
    _read_exact_plan,
    load_challenger_cohort_episode_receipt,
)
from .evidence import artifact_self_hash
from .market_data import HistoricalArchiveRequest, PublicArchiveTransport
from .research_corpus import _publish_exact, _strict_json_bytes
from .research_execution import ResearchExecutionError, _archive_rows


_SCHEMA = "challenger-cohort-daily-archive-receipt-v1.schema.json"
_ZERO_HASH = "0" * 64
_DESIGN_COMMIT = "b550f4d"
_PLAN_ID = (
    "challenger_episode_cohort_plan_"
    "56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c"
)
_PLAN_HASH = (
    "20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201"
)
_PLAN_FILE_SHA256 = (
    "a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff"
)
_FIRST_DAY = datetime(2026, 7, 30, tzinfo=timezone.utc)
_LAST_DAY = datetime(2026, 10, 29, tzinfo=timezone.utc)
_ELIGIBILITY_DELAY = timedelta(minutes=5)
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_CHECKSUM_BYTES = 4 * 1024
_MAX_RECEIPT_BYTES = 512 * 1024
_MAX_EPISODE_RECEIPT_BYTES = 64 * 1024 * 1024
_EPISODE_DIRECTORY = "challenger-cohort-episode-receipts"
_ARCHIVE_DIRECTORY = "challenger-cohort-daily-archives"


class ChallengerCohortDailyArchiveError(ValueError):
    """Shared archive discovery, acquisition, or validation failed closed."""

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
            raise ChallengerCohortDailyArchiveError(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_TIME_INVALID"
        )
    return converted, rendered


def _day_bounds(period: str) -> Tuple[datetime, datetime]:
    try:
        start = datetime.strptime(period, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError) as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_PERIOD_INVALID"
        ) from error
    if not _FIRST_DAY <= start <= _LAST_DAY:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_PERIOD_INVALID"
        )
    return start, start + timedelta(days=1)


def _next_strict_minute(value: object) -> str:
    parsed, _ = _utc(value)
    return utc_datetime(
        parsed.replace(second=0, microsecond=0) + timedelta(minutes=1)
    )


def _request(period: str) -> HistoricalArchiveRequest:
    _day_bounds(period)
    return HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="DAILY",
        period=period,
    )


def _request_payload(request: HistoricalArchiveRequest) -> Dict[str, Any]:
    return {
        "schema_version": request.schema_version,
        "provider": request.provider,
        "market": request.market,
        "data_family": request.data_family,
        "symbol": request.symbol,
        "interval_or_null": request.interval_or_null,
        "period_kind": request.period_kind,
        "period": request.period,
        "archive_filename": request.archive_filename,
        "checksum_filename": request.archive_filename + ".CHECKSUM",
        "archive_url": request.archive_url,
        "checksum_url": request.checksum_url,
    }


def _cohort_plan_binding(
    plan: Mapping[str, Any], plan_file_sha256: str
) -> Dict[str, str]:
    try:
        if (
            plan["plan_id"] != _PLAN_ID
            or plan["plan_hash"] != _PLAN_HASH
            or plan_file_sha256 != _PLAN_FILE_SHA256
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_PLAN_INVALID"
        ) from error
    return {
        "plan_id": _PLAN_ID,
        "plan_hash": _PLAN_HASH,
        "plan_file_sha256": _PLAN_FILE_SHA256,
    }


def _secure_directory(path: Path, *, create: bool) -> None:
    requested = Path(path)
    try:
        if not requested.is_absolute() or requested.is_symlink():
            raise ValueError
        if create:
            requested.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(requested, 0o700)
        status = requested.lstat()
        if (
            not stat.S_ISDIR(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or stat.S_IMODE(status.st_mode) != 0o700
            or requested.resolve(strict=True) != requested.absolute()
        ):
            raise ValueError
    except Exception as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_DIRECTORY_INVALID"
        ) from error


def _secure_read(path: Path, maximum_bytes: int) -> bytes:
    try:
        requested = Path(path)
        status = requested.lstat()
        if (
            not requested.is_absolute()
            or not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size <= 0
            or status.st_size > maximum_bytes
            or requested.resolve(strict=True) != requested.absolute()
        ):
            raise ValueError
        return requested.read_bytes()
    except Exception as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_FILE_INVALID"
        ) from error


def _episode_filename(receipt: Mapping[str, Any]) -> str:
    stamp = (
        receipt["episode"]["entry_scheduled_for"]
        .replace("-", "")
        .replace(":", "")
        .replace(".000", "")
    )
    return f"{stamp}-{receipt['episode']['episode_id']}.json"


def _discover_episode_receipts(
    *,
    receipt_output_root: Path,
    cohort_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    receipt_loader=None,
) -> Tuple[Mapping[str, Any], ...]:
    root = Path(receipt_output_root).expanduser()
    if not root.is_absolute() or root.is_symlink():
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_EPISODE_ROOT_INVALID"
        )
    if not root.exists():
        return ()
    try:
        resolved_root = root.resolve(strict=True)
        directory = resolved_root / _EPISODE_DIRECTORY
        if not directory.exists():
            return ()
        _secure_directory(resolved_root, create=False)
        _secure_directory(directory, create=False)
        entries = tuple(sorted(directory.iterdir(), key=lambda value: value.name))
    except ChallengerCohortDailyArchiveError:
        raise
    except Exception as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_EPISODE_ROOT_INVALID"
        ) from error
    if len(entries) > 540:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_EPISODE_SET_INVALID"
        )
    loader = receipt_loader or load_challenger_cohort_episode_receipt
    loaded = []
    for path in entries:
        try:
            status = path.lstat()
            if (
                path.suffix != ".json"
                or not stat.S_ISREG(status.st_mode)
                or stat.S_ISLNK(status.st_mode)
                or status.st_uid != os.getuid()
                or status.st_nlink != 1
                or stat.S_IMODE(status.st_mode) != 0o600
                or status.st_size <= 0
                or status.st_size > _MAX_EPISODE_RECEIPT_BYTES
            ):
                raise ValueError
            receipt = loader(
                receipt_path=path,
                cohort_plan_path=cohort_plan_path,
                install_receipt_path=install_receipt_path,
                contract_path=contract_path,
                plist_path=plist_path,
            )
            if path.name != _episode_filename(receipt):
                raise ValueError
            loaded.append(receipt)
        except Exception as error:
            raise ChallengerCohortDailyArchiveError(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_EPISODE_RECEIPT_INVALID"
            ) from error
    loaded.sort(key=lambda value: value["episode"]["ordinal"])
    prior_ids = []
    previous_entry = None
    for ordinal, receipt in enumerate(loaded, 1):
        try:
            episode = receipt["episode"]
            episode_id = episode["episode_id"]
            if (
                episode["ordinal"] != ordinal
                or episode_id in prior_ids
                or receipt["prior_completed_episodes"]["count"]
                != len(prior_ids)
                or receipt["prior_completed_episodes"]["episode_ids"]
                != prior_ids
                or (
                    previous_entry is not None
                    and episode["entry_scheduled_for"] <= previous_entry
                )
            ):
                raise ValueError
            prior_ids.append(episode_id)
            previous_entry = episode["entry_scheduled_for"]
        except Exception as error:
            raise ChallengerCohortDailyArchiveError(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_EPISODE_SET_INVALID"
            ) from error
    return tuple(loaded)


def _required_minutes(
    receipts: Sequence[Mapping[str, Any]],
) -> Mapping[str, Tuple[str, ...]]:
    result: Dict[str, set] = {}
    for receipt in receipts:
        try:
            episode = receipt["episode"]
            values = (
                _next_strict_minute(episode["entry_recorded_at"]),
                _next_strict_minute(episode["exit_recorded_at"]),
            )
            for value in values:
                _day_bounds(value[:10])
                result.setdefault(value[:10], set()).add(value)
        except Exception as error:
            raise ChallengerCohortDailyArchiveError(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_EXECUTION_MINUTE_INVALID"
            ) from error
    return {
        period: tuple(sorted(values))
        for period, values in sorted(result.items())
    }


def _verified_daily_source(
    *,
    period: str,
    archive_bytes: bytes,
    checksum_bytes: bytes,
    retrieved_at: object,
) -> Dict[str, Any]:
    request = _request(period)
    start, end = _day_bounds(period)
    retrieved, retrieved_text = _utc(retrieved_at)
    eligible = end + _ELIGIBILITY_DELAY
    if retrieved < eligible:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_SOURCE_EARLY"
        )
    try:
        csv_bytes, rows, row_hashes, excluded = _archive_rows(
            request=request,
            archive_bytes=archive_bytes,
            checksum_bytes=checksum_bytes,
            start=start,
            end=end,
        )
    except ResearchExecutionError as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_SOURCE_INVALID"
        ) from error
    expected = [
        start + timedelta(minutes=index) for index in range(1440)
    ]
    if (
        len(rows) != 1440
        or excluded
        or list(rows) != expected
        or len(row_hashes) != 1440
    ):
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_COVERAGE_INVALID"
        )
    return {
        "request": _request_payload(request),
        "retrieved_at": retrieved_text,
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "checksum_file_sha256": hashlib.sha256(checksum_bytes).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "csv_row_count": len(rows),
        "first_open_time": utc_datetime(start),
        "last_open_time": utc_datetime(end - timedelta(minutes=1)),
        "source_rows_root_hash": business_hash(row_hashes),
    }


def challenger_cohort_daily_archive_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "cohort_plan_hash": receipt["cohort_plan"]["plan_hash"],
        "period": receipt["request"]["period"],
        "archive_sha256": receipt["source"]["archive_sha256"],
        "checksum_file_sha256": receipt["source"][
            "checksum_file_sha256"
        ],
        "csv_sha256": receipt["source"]["csv_sha256"],
        "source_rows_root_hash": receipt["source"][
            "source_rows_root_hash"
        ],
        "retrieved_at": receipt["retrieved_at"],
    }


def _build_receipt(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    source: Mapping[str, Any],
) -> Dict[str, Any]:
    period = source["request"]["period"]
    _start, end = _day_bounds(period)
    receipt = {
        "$schema": "./challenger-cohort-daily-archive-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_cohort_daily_archive_receipt_" + _ZERO_HASH,
        "receipt_hash": _ZERO_HASH,
        "design_commit": _DESIGN_COMMIT,
        "package_baseline": "0.45.0",
        "cohort_plan": _cohort_plan_binding(plan, plan_file_sha256),
        "request": source["request"],
        "eligible_at": utc_datetime(end + _ELIGIBILITY_DELAY),
        "retrieved_at": source["retrieved_at"],
        "source": {
            "archive_sha256": source["archive_sha256"],
            "checksum_file_sha256": source["checksum_file_sha256"],
            "csv_sha256": source["csv_sha256"],
            "csv_row_count": source["csv_row_count"],
            "first_open_time": source["first_open_time"],
            "last_open_time": source["last_open_time"],
            "source_rows_root_hash": source["source_rows_root_hash"],
        },
        "status": "COHORT_DAILY_ARCHIVE_VERIFIED",
        "security_boundary": {
            "archive_get_count": 1,
            "checksum_get_count": 1,
            "total_network_request_count": 2,
            "credential_used": False,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "strategy_state_write_count": 0,
            "runner_invocation_count": 0,
            "caller_episode_selector_allowed": False,
            "caller_date_allowed": False,
            "caller_symbol_allowed": False,
            "caller_url_allowed": False,
            "rest_or_third_party_fallback_allowed": False,
        },
        "eligibility": {
            "source": "ARCHIVE_FORWARD_OUTCOME_RESEARCH_ONLY",
            "execution": "INELIGIBLE_PROXY_NOT_REAL_FILL",
            "profitability": "INELIGIBLE_SOURCE_ONLY",
        },
        "warnings": [
            "ARCHIVE_BYTES_ARE_OWNER_ONLY_AND_NOT_COMMITTED",
            "ARCHIVE_RETRIEVAL_IS_AFTER_SOURCE_DAY_PLUS_FIVE_MINUTES",
            "DAY_RECEIPT_IS_EPISODE_INDEPENDENT_AND_CONTENT_REUSABLE",
            "MINUTE_BARS_ARE_EXECUTION_PROXIES_NOT_REAL_FILLS",
            "COHORT_RESULTS_ARE_NOT_COMPUTED_BY_THIS_VERSION",
            "NO_AI_ADVANTAGE_CLAIM",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    receipt["receipt_id"] = stable_id(
        "challenger_cohort_daily_archive_receipt", _identity(receipt)
    )
    receipt["receipt_hash"] = (
        challenger_cohort_daily_archive_receipt_hash(receipt)
    )
    if tuple(_validator().iter_errors(receipt)):
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_RECEIPT_SCHEMA_INVALID"
        )
    return receipt


def challenger_cohort_daily_archive_receipt_reasons(
    receipt: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    archive_bytes: bytes,
    checksum_bytes: bytes,
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_RECEIPT_SCHEMA_INVALID"
            )
        if receipt.get(
            "receipt_hash"
        ) != challenger_cohort_daily_archive_receipt_hash(receipt):
            reasons.append(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_RECEIPT_HASH_MISMATCH"
            )
        if receipt.get("receipt_id") != stable_id(
            "challenger_cohort_daily_archive_receipt", _identity(receipt)
        ):
            reasons.append(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_RECEIPT_ID_MISMATCH"
            )
        source = _verified_daily_source(
            period=receipt["request"]["period"],
            archive_bytes=archive_bytes,
            checksum_bytes=checksum_bytes,
            retrieved_at=receipt["retrieved_at"],
        )
        rebuilt = _build_receipt(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            source=source,
        )
        if business_hash(rebuilt) != business_hash(receipt):
            reasons.append(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_RECEIPT_SEMANTIC_MISMATCH"
            )
    except Exception:
        reasons.append(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_RECEIPT_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def _paths(output_root: Path, period: str) -> Mapping[str, Path]:
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_OUTPUT_INVALID"
        )
    resolved = requested.resolve()
    request = _request(period)
    shared_root = resolved / _ARCHIVE_DIRECTORY
    day_root = shared_root / period
    return {
        "base_root": resolved,
        "shared_root": shared_root,
        "day_root": day_root,
        "archive": day_root / request.archive_filename,
        "checksum": day_root / (request.archive_filename + ".CHECKSUM"),
        "receipt": day_root / "receipt.json",
    }


def _validate_directory_entries(
    directory: Path, expected_names: Sequence[str]
) -> None:
    try:
        names = tuple(sorted(path.name for path in directory.iterdir()))
    except OSError as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_DIRECTORY_INVALID"
        ) from error
    if any(name not in expected_names for name in names):
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_DIRECTORY_INVALID"
        )


def _validate_archive_inventory(
    *,
    output_root: Path,
    required_periods: Sequence[str],
    plan: Mapping[str, Any],
    plan_file_sha256: str,
) -> None:
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_OUTPUT_INVALID"
        )
    resolved = requested.resolve()
    shared_root = resolved / _ARCHIVE_DIRECTORY
    if not shared_root.exists():
        return
    _secure_directory(resolved, create=False)
    _secure_directory(shared_root, create=False)
    allowed = set(required_periods)
    try:
        entries = tuple(shared_root.iterdir())
    except OSError as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_DIRECTORY_INVALID"
        ) from error
    for path in entries:
        if path.name not in allowed:
            raise ChallengerCohortDailyArchiveError(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_INVENTORY_INVALID"
            )
        _day_bounds(path.name)
        _secure_directory(path, create=False)
        _load_day(
            output_root=output_root,
            period=path.name,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
        )


def _load_day(
    *,
    output_root: Path,
    period: str,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
) -> Optional[Tuple[Mapping[str, Any], bytes, bytes]]:
    paths = _paths(output_root, period)
    if not paths["day_root"].exists():
        return None
    _secure_directory(paths["base_root"], create=False)
    _secure_directory(paths["shared_root"], create=False)
    _secure_directory(paths["day_root"], create=False)
    _validate_directory_entries(
        paths["day_root"],
        (
            paths["archive"].name,
            paths["checksum"].name,
            paths["receipt"].name,
        ),
    )
    limits = {
        "archive": _MAX_ARCHIVE_BYTES,
        "checksum": _MAX_CHECKSUM_BYTES,
        "receipt": _MAX_RECEIPT_BYTES,
    }
    exists = {
        name: paths[name].exists()
        for name in ("archive", "checksum", "receipt")
    }
    for name, present in exists.items():
        if present:
            _secure_read(paths[name], limits[name])
    if not all(exists.values()):
        return None
    archive_bytes = _secure_read(paths["archive"], _MAX_ARCHIVE_BYTES)
    checksum_bytes = _secure_read(paths["checksum"], _MAX_CHECKSUM_BYTES)
    try:
        receipt = _strict_json_bytes(
            _secure_read(paths["receipt"], _MAX_RECEIPT_BYTES)
        )
    except ValueError as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_RECEIPT_INVALID"
        ) from error
    reasons = challenger_cohort_daily_archive_receipt_reasons(
        receipt,
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        archive_bytes=archive_bytes,
        checksum_bytes=checksum_bytes,
    )
    if reasons:
        raise ChallengerCohortDailyArchiveError(reasons[0])
    return receipt, archive_bytes, checksum_bytes


def _response_body(
    response: object, *, expected_url: str
) -> Tuple[int, Optional[bytes]]:
    status = getattr(response, "status", None)
    final_url = getattr(response, "final_url", None)
    body = getattr(response, "body", None)
    if final_url != expected_url or status not in (200, 404):
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_HTTP_INVALID"
        )
    if status == 404:
        return status, None
    if not isinstance(body, bytes) or not body:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_HTTP_INVALID"
        )
    return status, body


def _publish_day(
    *,
    output_root: Path,
    period: str,
    archive_bytes: bytes,
    checksum_bytes: bytes,
    receipt: Mapping[str, Any],
) -> None:
    paths = _paths(output_root, period)
    _secure_directory(paths["base_root"], create=True)
    _secure_directory(paths["shared_root"], create=True)
    _secure_directory(paths["day_root"], create=True)
    _validate_directory_entries(
        paths["day_root"],
        (
            paths["archive"].name,
            paths["checksum"].name,
            paths["receipt"].name,
        ),
    )
    try:
        _publish_exact(paths["archive"], archive_bytes)
        _publish_exact(paths["checksum"], checksum_bytes)
        _publish_exact(
            paths["receipt"], canonical_json(receipt).encode("utf-8")
        )
    except ValueError as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_PUBLISH_CONFLICT"
        ) from error


def acquire_challenger_cohort_daily_archives(
    *,
    cohort_plan_path: Path,
    episode_receipt_output_root: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    archive_output_root: Path,
    observed_at: object,
    transport: PublicArchiveTransport,
    receipt_loader=None,
) -> Mapping[str, Any]:
    """Acquire all and only missing eligible days derived from verified receipts."""

    try:
        plan, plan_file_sha256 = _read_exact_plan(cohort_plan_path)
    except ChallengerCohortEpisodeReceiptError as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_PLAN_INVALID"
        ) from error
    _cohort_plan_binding(plan, plan_file_sha256)
    receipts = _discover_episode_receipts(
        receipt_output_root=episode_receipt_output_root,
        cohort_plan_path=cohort_plan_path,
        install_receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        receipt_loader=receipt_loader,
    )
    requirements = _required_minutes(receipts)
    _validate_archive_inventory(
        output_root=archive_output_root,
        required_periods=tuple(requirements),
        plan=plan,
        plan_file_sha256=plan_file_sha256,
    )
    observed, observed_text = _utc(observed_at)
    receipt_summary = [
        {
            "ordinal": receipt["episode"]["ordinal"],
            "episode_id": receipt["episode"]["episode_id"],
            "receipt_id": receipt["receipt_id"],
            "receipt_hash": receipt["receipt_hash"],
        }
        for receipt in receipts
    ]
    if not requirements:
        return {
            "status": "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES",
            "observed_at": observed_text,
            "episode_receipt_count": len(receipts),
            "episode_receipt_set_root_hash": business_hash(receipt_summary),
            "required_day_count": 0,
            "verified_day_count": 0,
            "network_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "strategy_state_write_count": 0,
            "runner_invocation_count": 0,
            "days": [],
        }
    if not hasattr(transport, "get"):
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_TRANSPORT_INVALID"
        )
    statuses = []
    total_requests = 0
    for period, minutes in requirements.items():
        existing = _load_day(
            output_root=archive_output_root,
            period=period,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
        )
        if existing is not None:
            statuses.append(
                {
                    "period": period,
                    "required_execution_minutes": list(minutes),
                    "status": "COHORT_DAILY_ARCHIVE_VERIFIED",
                    "request_count": 0,
                    "receipt_id": existing[0]["receipt_id"],
                    "receipt_hash": existing[0]["receipt_hash"],
                }
            )
            continue
        _start, end = _day_bounds(period)
        eligible = end + _ELIGIBILITY_DELAY
        eligible_at = utc_datetime(eligible)
        if observed < eligible:
            statuses.append(
                {
                    "period": period,
                    "required_execution_minutes": list(minutes),
                    "status": "COHORT_DAILY_ARCHIVE_NOT_YET_ELIGIBLE",
                    "request_count": 0,
                    "eligible_at": eligible_at,
                }
            )
            continue
        request = _request(period)
        archive_response = transport.get(request.archive_url)
        total_requests += 1
        archive_status, archive_bytes = _response_body(
            archive_response, expected_url=request.archive_url
        )
        if archive_status == 404:
            statuses.append(
                {
                    "period": period,
                    "required_execution_minutes": list(minutes),
                    "status": "COHORT_DAILY_ARCHIVE_PENDING_ZIP_404",
                    "request_count": 1,
                    "eligible_at": eligible_at,
                }
            )
            continue
        checksum_response = transport.get(request.checksum_url)
        total_requests += 1
        checksum_status, checksum_bytes = _response_body(
            checksum_response, expected_url=request.checksum_url
        )
        if checksum_status == 404:
            statuses.append(
                {
                    "period": period,
                    "required_execution_minutes": list(minutes),
                    "status": "COHORT_DAILY_ARCHIVE_PENDING_CHECKSUM_404",
                    "request_count": 2,
                    "eligible_at": eligible_at,
                }
            )
            continue
        source = _verified_daily_source(
            period=period,
            archive_bytes=archive_bytes,
            checksum_bytes=checksum_bytes,
            retrieved_at=observed_text,
        )
        receipt = _build_receipt(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            source=source,
        )
        _publish_day(
            output_root=archive_output_root,
            period=period,
            archive_bytes=archive_bytes,
            checksum_bytes=checksum_bytes,
            receipt=receipt,
        )
        loaded = _load_day(
            output_root=archive_output_root,
            period=period,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
        )
        if loaded is None:
            raise ChallengerCohortDailyArchiveError(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_PUBLISH_INVALID"
            )
        statuses.append(
            {
                "period": period,
                "required_execution_minutes": list(minutes),
                "status": "COHORT_DAILY_ARCHIVE_VERIFIED",
                "request_count": 2,
                "receipt_id": receipt["receipt_id"],
                "receipt_hash": receipt["receipt_hash"],
            }
        )
    verified_count = sum(
        item["status"] == "COHORT_DAILY_ARCHIVE_VERIFIED"
        for item in statuses
    )
    if verified_count == len(requirements):
        status = "COHORT_DAILY_ARCHIVE_COMPLETE"
    elif verified_count:
        status = "COHORT_DAILY_ARCHIVE_PARTIAL"
    else:
        status = "COHORT_DAILY_ARCHIVE_PENDING"
    return {
        "status": status,
        "observed_at": observed_text,
        "episode_receipt_count": len(receipts),
        "episode_receipt_set_root_hash": business_hash(receipt_summary),
        "required_day_count": len(requirements),
        "verified_day_count": verified_count,
        "network_request_count": total_requests,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "strategy_state_write_count": 0,
        "runner_invocation_count": 0,
        "days": statuses,
    }


def load_challenger_cohort_daily_archives(
    *,
    cohort_plan_path: Path,
    episode_receipt_output_root: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    archive_output_root: Path,
    receipt_loader=None,
) -> Mapping[str, Tuple[bytes, bytes, str]]:
    """Load the complete shared day set derived from all verified receipts."""

    try:
        plan, plan_file_sha256 = _read_exact_plan(cohort_plan_path)
    except ChallengerCohortEpisodeReceiptError as error:
        raise ChallengerCohortDailyArchiveError(
            "CHALLENGER_COHORT_DAILY_ARCHIVE_PLAN_INVALID"
        ) from error
    _cohort_plan_binding(plan, plan_file_sha256)
    receipts = _discover_episode_receipts(
        receipt_output_root=episode_receipt_output_root,
        cohort_plan_path=cohort_plan_path,
        install_receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        receipt_loader=receipt_loader,
    )
    requirements = _required_minutes(receipts)
    _validate_archive_inventory(
        output_root=archive_output_root,
        required_periods=tuple(requirements),
        plan=plan,
        plan_file_sha256=plan_file_sha256,
    )
    result = {}
    for period in requirements:
        loaded = _load_day(
            output_root=archive_output_root,
            period=period,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
        )
        if loaded is None:
            raise ChallengerCohortDailyArchiveError(
                "CHALLENGER_COHORT_DAILY_ARCHIVE_SET_INCOMPLETE"
            )
        receipt, archive_bytes, checksum_bytes = loaded
        result[period] = (
            archive_bytes,
            checksum_bytes,
            receipt["retrieved_at"],
        )
    return result
