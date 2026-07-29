"""Recoverable official DAILY archives for the first Challenger episode."""

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .challenger_episode_economic_evaluator import (
    ChallengerEpisodeEconomicEvaluatorError,
    _verified_daily_source,
    required_challenger_episode_archive_periods,
)
from .evidence import artifact_self_hash
from .market_data import HistoricalArchiveRequest, PublicArchiveTransport
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-episode-archive-receipt-v1.schema.json"
_ZERO_HASH = "0" * 64
_ELIGIBILITY_DELAY = timedelta(minutes=5)
_MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
_MAX_CHECKSUM_BYTES = 4 * 1024
_MAX_RECEIPT_BYTES = 512 * 1024


class ChallengerEpisodeArchiveAcquisitionError(ValueError):
    """Archive acquisition, recovery, or trust validation failed closed."""

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
            raise ChallengerEpisodeArchiveAcquisitionError(
                "CHALLENGER_EPISODE_ARCHIVE_TIME_INVALID"
            ) from error
    else:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_TIME_INVALID"
        )
    return converted, rendered


def _request(period: str) -> HistoricalArchiveRequest:
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
        "archive_url": request.archive_url,
        "checksum_url": request.checksum_url,
        "archive_filename": request.archive_filename,
        "checksum_filename": request.archive_filename + ".CHECKSUM",
    }


def _required_times(
    plan: Mapping[str, Any],
    completion_receipt: Mapping[str, Any],
) -> Mapping[str, Tuple[str, ...]]:
    entry = plan["first_episode"]["entry_execution_minute"]
    exit_recorded = completion_receipt["state"]["decisions"][-1][
        "recorded_at"
    ]
    parsed, _ = _utc(exit_recorded)
    exit_minute = utc_datetime(
        parsed.replace(second=0, microsecond=0) + timedelta(minutes=1)
    )
    result: Dict[str, list] = {}
    for value in (entry, exit_minute):
        result.setdefault(value[:10], []).append(value)
    return {
        period: tuple(values) for period, values in sorted(result.items())
    }


def _required_periods(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
) -> Tuple[str, ...]:
    try:
        return required_challenger_episode_archive_periods(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            completion_receipt=completion_receipt,
            completion_receipt_file_sha256=completion_receipt_file_sha256,
        )
    except ChallengerEpisodeEconomicEvaluatorError as error:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_TRUST_INPUT_INVALID"
        ) from error


def _eligible_at(period: str) -> str:
    try:
        start = datetime.strptime(period, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError) as error:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_PERIOD_INVALID"
        ) from error
    return utc_datetime(start + timedelta(days=1) + _ELIGIBILITY_DELAY)


def challenger_episode_archive_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "plan_hash": receipt["plan_binding"]["plan_hash"],
        "completion_receipt_hash": receipt["completion_receipt"][
            "receipt_hash"
        ],
        "period": receipt["request"]["period"],
        "archive_sha256": receipt["source"]["archive_sha256"],
        "checksum_file_sha256": receipt["source"][
            "checksum_file_sha256"
        ],
        "retrieved_at": receipt["retrieved_at"],
    }


def _build_receipt(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
    source: Mapping[str, Any],
) -> Dict[str, Any]:
    request = source["request"]
    period = request["period"]
    receipt = {
        "$schema": "./challenger-episode-archive-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_episode_archive_receipt_" + _ZERO_HASH,
        "receipt_hash": _ZERO_HASH,
        "design_commit": "2e411a7",
        "package_baseline": "0.38.0",
        "plan_binding": {
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "plan_file_sha256": plan_file_sha256,
        },
        "completion_receipt": {
            "receipt_id": completion_receipt["receipt_id"],
            "receipt_hash": completion_receipt["receipt_hash"],
            "receipt_file_sha256": completion_receipt_file_sha256,
            "episode_id": completion_receipt["episode"]["episode_id"],
        },
        "request": {
            **request,
            "archive_url": _request(period).archive_url,
            "checksum_url": _request(period).checksum_url,
        },
        "eligible_at": _eligible_at(period),
        "retrieved_at": source["retrieved_at"],
        "required_open_times": [
            row["open_time"] for row in source["selected_rows"]
        ],
        "source": {
            "archive_sha256": source["archive_sha256"],
            "checksum_file_sha256": source["checksum_file_sha256"],
            "csv_sha256": source["csv_sha256"],
            "csv_row_count": source["csv_row_count"],
            "first_open_time": source["first_open_time"],
            "last_open_time": source["last_open_time"],
            "source_rows_root_hash": source["source_rows_root_hash"],
            "selected_rows": source["selected_rows"],
        },
        "status": "OFFICIAL_DAILY_ARCHIVE_VERIFIED",
        "security_boundary": {
            "archive_get_count": 1,
            "checksum_get_count": 1,
            "total_network_request_count": 2,
            "credential_used": False,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "strategy_state_write_count": 0,
            "runner_invocation_count": 0,
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
            "ARCHIVE_RETRIEVAL_IS_AFTER_SOURCE_DAY",
            "SELECTED_ROWS_ARE_EXECUTION_PROXIES_NOT_REAL_FILLS",
            "SINGLE_EPISODE_CANNOT_ESTABLISH_EDGE",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    receipt["receipt_id"] = stable_id(
        "challenger_episode_archive_receipt", _identity(receipt)
    )
    receipt["receipt_hash"] = challenger_episode_archive_receipt_hash(
        receipt
    )
    if tuple(_validator().iter_errors(receipt)):
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_RECEIPT_SCHEMA_INVALID"
        )
    return receipt


def _secure_read(path: Path, maximum_bytes: int) -> bytes:
    try:
        requested = Path(path).expanduser()
        status = requested.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size <= 0
            or status.st_size > maximum_bytes
        ):
            raise ValueError
        resolved = requested.resolve(strict=True)
        if resolved != requested.absolute():
            raise ValueError
        return resolved.read_bytes()
    except Exception as error:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_FILE_INVALID"
        ) from error


def _paths(output_root: Path, period: str) -> Mapping[str, Path]:
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_OUTPUT_INVALID"
        )
    root = requested.resolve()
    period_root = root / period
    request = _request(period)
    return {
        "root": root,
        "period_root": period_root,
        "archive": period_root / request.archive_filename,
        "checksum": period_root / (request.archive_filename + ".CHECKSUM"),
        "receipt": period_root / "receipt.json",
    }


def _secure_directory(path: Path, *, create: bool) -> None:
    requested = Path(path)
    try:
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
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_OUTPUT_INVALID"
        ) from error


def challenger_episode_archive_receipt_reasons(
    receipt: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
    archive_bytes: bytes,
    checksum_bytes: bytes,
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append(
                "CHALLENGER_EPISODE_ARCHIVE_RECEIPT_SCHEMA_INVALID"
            )
        if receipt.get(
            "receipt_hash"
        ) != challenger_episode_archive_receipt_hash(receipt):
            reasons.append(
                "CHALLENGER_EPISODE_ARCHIVE_RECEIPT_HASH_MISMATCH"
            )
        if receipt.get("receipt_id") != stable_id(
            "challenger_episode_archive_receipt", _identity(receipt)
        ):
            reasons.append(
                "CHALLENGER_EPISODE_ARCHIVE_RECEIPT_ID_MISMATCH"
            )
        required = _required_times(plan, completion_receipt)
        period = receipt["request"]["period"]
        source = _verified_daily_source(
            period=period,
            archive_bytes=archive_bytes,
            checksum_bytes=checksum_bytes,
            retrieved_at=receipt["retrieved_at"],
            required_open_times=required[period],
        )
        rebuilt = _build_receipt(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            completion_receipt=completion_receipt,
            completion_receipt_file_sha256=completion_receipt_file_sha256,
            source=source,
        )
        if business_hash(rebuilt) != business_hash(receipt):
            reasons.append(
                "CHALLENGER_EPISODE_ARCHIVE_RECEIPT_SEMANTIC_MISMATCH"
            )
    except (
        ChallengerEpisodeArchiveAcquisitionError,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append(
            "CHALLENGER_EPISODE_ARCHIVE_RECEIPT_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def _load_period(
    *,
    output_root: Path,
    period: str,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
) -> Optional[Tuple[Mapping[str, Any], bytes, bytes]]:
    paths = _paths(output_root, period)
    exists = {
        name: path.exists()
        for name, path in paths.items()
        if name in ("archive", "checksum", "receipt")
    }
    if not any(exists.values()):
        return None
    _secure_directory(paths["root"], create=False)
    _secure_directory(paths["period_root"], create=False)
    limits = {
        "archive": _MAX_ARCHIVE_BYTES,
        "checksum": _MAX_CHECKSUM_BYTES,
        "receipt": _MAX_RECEIPT_BYTES,
    }
    for name, present in exists.items():
        if present:
            _secure_read(paths[name], limits[name])
    if not all(exists.values()):
        return None
    archive_bytes = _secure_read(paths["archive"], _MAX_ARCHIVE_BYTES)
    checksum_bytes = _secure_read(
        paths["checksum"], _MAX_CHECKSUM_BYTES
    )
    try:
        receipt = _strict_json_bytes(
            _secure_read(paths["receipt"], _MAX_RECEIPT_BYTES)
        )
    except ValueError as error:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_RECEIPT_INVALID"
        ) from error
    reasons = challenger_episode_archive_receipt_reasons(
        receipt,
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        completion_receipt=completion_receipt,
        completion_receipt_file_sha256=completion_receipt_file_sha256,
        archive_bytes=archive_bytes,
        checksum_bytes=checksum_bytes,
    )
    if reasons:
        raise ChallengerEpisodeArchiveAcquisitionError(reasons[0])
    return receipt, archive_bytes, checksum_bytes


def _response_body(
    response: object,
    *,
    expected_url: str,
) -> Tuple[int, Optional[bytes]]:
    status = getattr(response, "status", None)
    final_url = getattr(response, "final_url", None)
    body = getattr(response, "body", None)
    if final_url != expected_url or status not in (200, 404):
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_HTTP_INVALID"
        )
    if status == 404:
        return status, None
    if not isinstance(body, bytes) or not body:
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_HTTP_INVALID"
        )
    return status, body


def acquire_challenger_episode_archives(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
    output_root: Path,
    observed_at: object,
    transport: PublicArchiveTransport,
) -> Mapping[str, Any]:
    """Acquire only missing eligible DAILY archives and recover exact results."""

    periods = _required_periods(
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        completion_receipt=completion_receipt,
        completion_receipt_file_sha256=completion_receipt_file_sha256,
    )
    required = _required_times(plan, completion_receipt)
    observed, observed_text = _utc(observed_at)
    if not hasattr(transport, "get"):
        raise ChallengerEpisodeArchiveAcquisitionError(
            "CHALLENGER_EPISODE_ARCHIVE_TRANSPORT_INVALID"
        )
    statuses = []
    total_requests = 0
    for period in periods:
        existing = _load_period(
            output_root=output_root,
            period=period,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            completion_receipt=completion_receipt,
            completion_receipt_file_sha256=completion_receipt_file_sha256,
        )
        if existing is not None:
            statuses.append(
                {
                    "period": period,
                    "status": "OFFICIAL_DAILY_ARCHIVE_VERIFIED",
                    "request_count": 0,
                    "receipt_id": existing[0]["receipt_id"],
                    "receipt_hash": existing[0]["receipt_hash"],
                }
            )
            continue
        eligible, eligible_text = _utc(_eligible_at(period))
        if observed < eligible:
            statuses.append(
                {
                    "period": period,
                    "status": "ARCHIVE_ACQUISITION_NOT_YET_ELIGIBLE",
                    "request_count": 0,
                    "eligible_at": eligible_text,
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
                    "status": "ARCHIVE_ACQUISITION_PENDING_ZIP_404",
                    "request_count": 1,
                    "eligible_at": eligible_text,
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
                    "status": "ARCHIVE_ACQUISITION_PENDING_CHECKSUM_404",
                    "request_count": 2,
                    "eligible_at": eligible_text,
                }
            )
            continue
        try:
            source = _verified_daily_source(
                period=period,
                archive_bytes=archive_bytes,
                checksum_bytes=checksum_bytes,
                retrieved_at=observed_text,
                required_open_times=required[period],
            )
        except ChallengerEpisodeEconomicEvaluatorError as error:
            raise ChallengerEpisodeArchiveAcquisitionError(
                "CHALLENGER_EPISODE_ARCHIVE_SOURCE_INVALID"
            ) from error
        receipt = _build_receipt(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            completion_receipt=completion_receipt,
            completion_receipt_file_sha256=completion_receipt_file_sha256,
            source=source,
        )
        paths = _paths(output_root, period)
        _secure_directory(paths["root"], create=True)
        _secure_directory(paths["period_root"], create=True)
        try:
            _publish_exact(paths["archive"], archive_bytes)
            _publish_exact(paths["checksum"], checksum_bytes)
            _publish_exact(
                paths["receipt"],
                canonical_json(receipt).encode("utf-8"),
            )
        except ValueError as error:
            raise ChallengerEpisodeArchiveAcquisitionError(
                "CHALLENGER_EPISODE_ARCHIVE_PUBLISH_CONFLICT"
            ) from error
        loaded = _load_period(
            output_root=output_root,
            period=period,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            completion_receipt=completion_receipt,
            completion_receipt_file_sha256=completion_receipt_file_sha256,
        )
        if loaded is None:
            raise ChallengerEpisodeArchiveAcquisitionError(
                "CHALLENGER_EPISODE_ARCHIVE_PUBLISH_INVALID"
            )
        statuses.append(
            {
                "period": period,
                "status": "OFFICIAL_DAILY_ARCHIVE_VERIFIED",
                "request_count": 2,
                "receipt_id": receipt["receipt_id"],
                "receipt_hash": receipt["receipt_hash"],
            }
        )
    verified_count = sum(
        item["status"] == "OFFICIAL_DAILY_ARCHIVE_VERIFIED"
        for item in statuses
    )
    if verified_count == len(periods):
        status = "ARCHIVE_ACQUISITION_COMPLETE"
    elif verified_count:
        status = "ARCHIVE_ACQUISITION_PARTIAL"
    else:
        status = "ARCHIVE_ACQUISITION_PENDING"
    return {
        "status": status,
        "observed_at": observed_text,
        "required_period_count": len(periods),
        "verified_period_count": verified_count,
        "network_request_count": total_requests,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "strategy_state_write_count": 0,
        "runner_invocation_count": 0,
        "periods": statuses,
    }


def load_challenger_episode_daily_archives(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    completion_receipt: Mapping[str, Any],
    completion_receipt_file_sha256: str,
    output_root: Path,
) -> Mapping[str, Tuple[bytes, bytes, str]]:
    """Load a complete verified owner-only mapping for the v0.38 evaluator."""

    periods = _required_periods(
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        completion_receipt=completion_receipt,
        completion_receipt_file_sha256=completion_receipt_file_sha256,
    )
    result = {}
    for period in periods:
        loaded = _load_period(
            output_root=output_root,
            period=period,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            completion_receipt=completion_receipt,
            completion_receipt_file_sha256=completion_receipt_file_sha256,
        )
        if loaded is None:
            raise ChallengerEpisodeArchiveAcquisitionError(
                "CHALLENGER_EPISODE_ARCHIVE_SET_INCOMPLETE"
            )
        receipt, archive_bytes, checksum_bytes = loaded
        result[period] = (
            archive_bytes,
            checksum_bytes,
            receipt["retrieved_at"],
        )
    return result
