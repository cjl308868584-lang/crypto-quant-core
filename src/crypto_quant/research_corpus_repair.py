"""Explicit official-daily repairs for degraded monthly research archives."""

import json
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .market_data import (
    HistoricalArchiveRequest,
    MarketDataError,
    historical_market_data_snapshot_attestation_hash,
    historical_market_data_snapshot_reasons,
)
from .research_corpus import (
    ResearchCorpusError,
    _publish_exact,
    _strict_json_bytes,
    research_corpus_plan_reasons,
    research_corpus_snapshot_reasons,
)


_SCHEMA = "historical-research-corpus-repair-v1.schema.json"
_ZERO_HASH = "0" * 64
_FOUR_HOURS = timedelta(hours=4)
_WARNINGS = (
    "DAILY_ARCHIVE_REPAIRS_DO_NOT_CREATE_POINT_IN_TIME_EVIDENCE",
    "REPAIRS_ARE_MARKET_CONTEXT_NOT_EXECUTION_FILLS",
    "NO_MODEL_TRAINED_OR_APPROVED",
    "NO_PROFITABILITY_CLAIM",
)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ResearchCorpusError("CORPUS_REPAIR_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ResearchCorpusError("CORPUS_REPAIR_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ResearchCorpusError("CORPUS_REPAIR_TIME_INVALID")
    rendered = utc_datetime(parsed)
    if rendered != value:
        raise ResearchCorpusError("CORPUS_REPAIR_TIME_INVALID")
    return parsed, rendered


def _month_bounds(month: str) -> Tuple[datetime, datetime]:
    try:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as error:
        raise ResearchCorpusError("CORPUS_REPAIR_MONTH_INVALID") from error
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def _expected_open_times(month: str) -> Tuple[str, ...]:
    start, end = _month_bounds(month)
    values = []
    cursor = start
    while cursor < end:
        values.append(utc_datetime(cursor))
        cursor += _FOUR_HOURS
    return tuple(values)


def _fact_open_times(snapshot: Mapping[str, Any]) -> Tuple[str, ...]:
    try:
        values = tuple(fact["open_time"] for fact in snapshot["facts"])
    except (KeyError, TypeError) as error:
        raise ResearchCorpusError("CORPUS_REPAIR_FACTS_INVALID") from error
    if (
        len(values) != len(set(values))
        or tuple(sorted(values)) != values
        or any(not isinstance(value, str) for value in values)
    ):
        raise ResearchCorpusError("CORPUS_REPAIR_FACTS_INVALID")
    return values


def _snapshot_integrity(
    snapshot: Mapping[str, Any],
    *,
    degraded_allowed: bool,
) -> str:
    try:
        attestation = historical_market_data_snapshot_attestation_hash(snapshot)
    except (MarketDataError, TypeError, ValueError) as error:
        raise ResearchCorpusError("CORPUS_REPAIR_SOURCE_INVALID") from error
    reasons = set(
        historical_market_data_snapshot_reasons(
            snapshot,
            trusted_snapshot_attestation_hashes={attestation},
        )
    )
    quality = snapshot.get("quality_eligibility")
    if quality == "FORMAL_COMPLETE" and not reasons:
        return attestation
    if degraded_allowed and quality == "RESEARCH_ONLY_DEGRADED":
        report = snapshot.get("quality_report")
        blocking = (
            set(report.get("blocking_findings", ()))
            if isinstance(report, Mapping)
            else set()
        )
        allowed_blocking = {
            "MARKET_DATA_PERIOD_COVERAGE",
            "MARKET_DATA_FUNDING_GAP",
        }
        allowed_reasons = blocking | {
            "MARKET_DATA_QUALITY_BLOCKING",
            "MARKET_DATA_RESEARCH_ONLY_DEGRADED",
        }
        if (
            blocking
            and not (blocking - allowed_blocking)
            and not (reasons - allowed_reasons)
        ):
            return attestation
    raise ResearchCorpusError("CORPUS_REPAIR_SOURCE_INVALID")


def _matching_scope(
    base_request: Mapping[str, Any],
    patch_request: Mapping[str, Any],
) -> bool:
    return (
        all(
            patch_request.get(field) == base_request.get(field)
            for field in (
                "schema_version",
                "provider",
                "market",
                "data_family",
                "symbol",
                "interval_or_null",
            )
        )
        and base_request.get("period_kind") == "MONTHLY"
        and patch_request.get("period_kind") == "DAILY"
    )


def repair_requests_for_degraded_sources(
    *,
    plan: Mapping[str, Any],
    corpus_snapshot: Mapping[str, Any],
    base_snapshots: Mapping[str, Mapping[str, Any]],
) -> Tuple[HistoricalArchiveRequest, ...]:
    """Derive the exact official daily requests needed to fill known gaps."""

    if research_corpus_plan_reasons(plan):
        raise ResearchCorpusError("CORPUS_REPAIR_PLAN_INVALID")
    if research_corpus_snapshot_reasons(corpus_snapshot, plan=plan):
        raise ResearchCorpusError("CORPUS_REPAIR_CORPUS_SNAPSHOT_INVALID")
    plan_items = {
        item["corpus_item_id"]: item for item in plan["items"]
    }
    degraded_items = [
        item
        for item in corpus_snapshot["items"]
        if item["quality_eligibility_or_null"] == "RESEARCH_ONLY_DEGRADED"
    ]
    if set(base_snapshots) != {
        item["corpus_item_id"] for item in degraded_items
    }:
        raise ResearchCorpusError("CORPUS_REPAIR_BASE_SET_INVALID")
    requests = []
    seen_days = set()
    for corpus_item in degraded_items:
        item_id = corpus_item["corpus_item_id"]
        plan_item = plan_items[item_id]
        base = base_snapshots[item_id]
        attestation = _snapshot_integrity(base, degraded_allowed=True)
        if (
            base.get("snapshot_hash")
            != corpus_item["snapshot_hash_or_null"]
            or attestation
            != corpus_item["expected_attestation_hash_or_null"]
            or business_hash(base.get("request"))
            != business_hash(plan_item["request"])
            or base.get("request", {}).get("data_family")
            not in ("KLINES", "MARK_PRICE_KLINES")
            or base.get("request", {}).get("interval_or_null") != "4h"
        ):
            raise ResearchCorpusError("CORPUS_REPAIR_BASE_SOURCE_MISMATCH")
        expected = set(_expected_open_times(plan_item["month"]))
        actual = set(_fact_open_times(base))
        missing = sorted(expected - actual)
        if not missing or actual - expected:
            raise ResearchCorpusError("CORPUS_REPAIR_MISSING_SET_INVALID")
        days = sorted({value[:10] for value in missing})
        for day in days:
            identity = (item_id, day)
            if identity in seen_days:
                raise ResearchCorpusError("CORPUS_REPAIR_REQUEST_DUPLICATE")
            seen_days.add(identity)
            request = HistoricalArchiveRequest.create(
                market=plan_item["request"]["market"],
                data_family=plan_item["request"]["data_family"],
                symbol=plan_item["request"]["symbol"],
                interval_or_null=plan_item["request"]["interval_or_null"],
                period_kind="DAILY",
                period=day,
            )
            requests.append(request)
    return tuple(requests)


def research_corpus_repair_bundle_hash(bundle: Mapping[str, Any]) -> str:
    return artifact_self_hash(bundle, "repair_bundle_hash")


def build_research_corpus_repair_bundle(
    *,
    plan: Mapping[str, Any],
    corpus_snapshot: Mapping[str, Any],
    base_snapshots: Mapping[str, Mapping[str, Any]],
    patch_snapshots: Sequence[Mapping[str, Any]],
    recorded_at: str,
) -> Dict[str, Any]:
    """Bind degraded monthly sources to exact official daily replacements."""

    _, recorded_text = _utc(recorded_at)
    requests = repair_requests_for_degraded_sources(
        plan=plan,
        corpus_snapshot=corpus_snapshot,
        base_snapshots=base_snapshots,
    )
    plan_items = {
        item["corpus_item_id"]: item for item in plan["items"]
    }
    degraded_items = [
        item
        for item in corpus_snapshot["items"]
        if item["quality_eligibility_or_null"] == "RESEARCH_ONLY_DEGRADED"
    ]
    request_keys = {
        (
            request.market,
            request.data_family,
            request.symbol,
            request.interval_or_null,
            request.period,
        )
        for request in requests
    }
    patches_by_key = {}
    for patch in patch_snapshots:
        attestation = _snapshot_integrity(patch, degraded_allowed=False)
        request = patch.get("request")
        if not isinstance(request, Mapping):
            raise ResearchCorpusError("CORPUS_REPAIR_PATCH_SCOPE_INVALID")
        key = (
            request.get("market"),
            request.get("data_family"),
            request.get("symbol"),
            request.get("interval_or_null"),
            request.get("period"),
        )
        if (
            key not in request_keys
            or key in patches_by_key
            or request.get("period_kind") != "DAILY"
        ):
            raise ResearchCorpusError("CORPUS_REPAIR_PATCH_SCOPE_INVALID")
        patches_by_key[key] = (patch, attestation)
    if set(patches_by_key) != request_keys:
        raise ResearchCorpusError("CORPUS_REPAIR_PATCH_SET_INCOMPLETE")

    repairs = []
    for corpus_item in degraded_items:
        item_id = corpus_item["corpus_item_id"]
        plan_item = plan_items[item_id]
        base = base_snapshots[item_id]
        base_request = base["request"]
        expected = set(_expected_open_times(plan_item["month"]))
        base_times = set(_fact_open_times(base))
        missing = sorted(expected - base_times)
        day_values = sorted({value[:10] for value in missing})
        patch_records = []
        repaired_times = set()
        for day in day_values:
            key = (
                base_request["market"],
                base_request["data_family"],
                base_request["symbol"],
                base_request["interval_or_null"],
                day,
            )
            patch, attestation = patches_by_key[key]
            if not _matching_scope(base_request, patch["request"]):
                raise ResearchCorpusError("CORPUS_REPAIR_PATCH_SCOPE_INVALID")
            patch_times = set(_fact_open_times(patch))
            required_for_day = {value for value in missing if value[:10] == day}
            if (
                patch_times != required_for_day
                or patch_times & base_times
                or repaired_times & patch_times
            ):
                raise ResearchCorpusError("CORPUS_REPAIR_PATCH_COVERAGE_INVALID")
            repaired_times.update(patch_times)
            patch_records.append(
                {
                    "period": day,
                    "snapshot_id": patch["snapshot_id"],
                    "snapshot_hash": patch["snapshot_hash"],
                    "expected_attestation_hash": attestation,
                    "archive_sha256": patch["source_receipt"][
                        "archive_sha256"
                    ],
                    "checksum_file_sha256": patch["source_receipt"][
                        "checksum_file_sha256"
                    ],
                    "source_rows_root_hash": patch["source_receipt"][
                        "source_rows_root_hash"
                    ],
                    "row_count": patch["quality_report"]["row_count"],
                    "open_times": sorted(patch_times),
                }
            )
        if repaired_times != set(missing) or base_times | repaired_times != expected:
            raise ResearchCorpusError("CORPUS_REPAIR_COMBINED_COVERAGE_INVALID")
        combined_records = [
            {
                "open_time": value,
                "source": "MONTHLY_BASE" if value in base_times else "DAILY_PATCH",
            }
            for value in sorted(expected)
        ]
        repair_identity = {
            "plan_hash": plan["plan_hash"],
            "corpus_item_id": item_id,
            "base_snapshot_hash": base["snapshot_hash"],
            "patch_snapshot_hashes": [
                record["snapshot_hash"] for record in patch_records
            ],
        }
        repairs.append(
            {
                "repair_id": stable_id("corpus_repair", repair_identity),
                "corpus_item_id": item_id,
                "stream_id": plan_item["stream_id"],
                "month": plan_item["month"],
                "base_snapshot_id": base["snapshot_id"],
                "base_snapshot_hash": base["snapshot_hash"],
                "base_expected_attestation_hash": (
                    historical_market_data_snapshot_attestation_hash(base)
                ),
                "missing_open_times": missing,
                "patches": patch_records,
                "repaired_open_times": sorted(repaired_times),
                "combined_interval_count": len(expected),
                "combined_coverage_root_hash": business_hash(combined_records),
                "repair_status": "EXPLICIT_OFFICIAL_DAILY_ARCHIVE_COMPLETE",
            }
        )
    repairs_root = business_hash(repairs)
    bundle = {
        "$schema": "./historical-research-corpus-repair-v1.schema.json",
        "schema_version": "1.0.0",
        "repair_bundle_id": stable_id(
            "corpus_repair_bundle",
            {
                "plan_hash": plan["plan_hash"],
                "event_chain_end_hash": corpus_snapshot[
                    "event_chain_end_hash"
                ],
                "repairs_root_hash": repairs_root,
                "recorded_at": recorded_text,
            },
        ),
        "repair_bundle_hash": _ZERO_HASH,
        "recorded_at": recorded_text,
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
        "corpus_snapshot_id": corpus_snapshot["snapshot_id"],
        "corpus_snapshot_hash": corpus_snapshot["snapshot_hash"],
        "event_chain_end_hash": corpus_snapshot["event_chain_end_hash"],
        "repairs": repairs,
        "summary": {
            "base_corpus_item_count": len(plan["items"]),
            "base_degraded_item_count": len(degraded_items),
            "repair_count": len(repairs),
            "patch_snapshot_count": sum(
                len(repair["patches"]) for repair in repairs
            ),
            "missing_interval_count": sum(
                len(repair["missing_open_times"]) for repair in repairs
            ),
            "repaired_interval_count": sum(
                len(repair["repaired_open_times"]) for repair in repairs
            ),
            "unresolved_interval_count": 0,
        },
        "research_training_readiness": (
            "READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD_WITH_EXPLICIT_DAILY_REPAIRS"
        ),
        "formal_pit_eligibility": "INELIGIBLE_ARCHIVE_REPLAY",
        "release_oos_eligibility": "INELIGIBLE",
        "profitability_eligibility": "INELIGIBLE",
        "warnings": list(_WARNINGS),
    }
    bundle["repair_bundle_hash"] = research_corpus_repair_bundle_hash(bundle)
    if tuple(_validator().iter_errors(bundle)):
        raise ResearchCorpusError("CORPUS_REPAIR_SCHEMA_INVALID")
    return bundle


def research_corpus_repair_bundle_reasons(
    bundle: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    corpus_snapshot: Mapping[str, Any],
    base_snapshots: Mapping[str, Mapping[str, Any]],
    patch_snapshots: Sequence[Mapping[str, Any]],
) -> Tuple[str, ...]:
    reasons = []
    if not isinstance(bundle, Mapping):
        return ("CORPUS_REPAIR_BUNDLE_INVALID",)
    try:
        if tuple(_validator().iter_errors(bundle)):
            reasons.append("CORPUS_REPAIR_SCHEMA_INVALID")
        if bundle.get("repair_bundle_hash") != research_corpus_repair_bundle_hash(
            bundle
        ):
            reasons.append("CORPUS_REPAIR_HASH_MISMATCH")
        expected = build_research_corpus_repair_bundle(
            plan=plan,
            corpus_snapshot=corpus_snapshot,
            base_snapshots=base_snapshots,
            patch_snapshots=patch_snapshots,
            recorded_at=bundle["recorded_at"],
        )
        if business_hash(bundle) != business_hash(expected):
            reasons.append("CORPUS_REPAIR_SEMANTIC_MISMATCH")
    except (KeyError, TypeError, ValueError, ResearchCorpusError):
        reasons.append("CORPUS_REPAIR_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def load_repair_source(path: Path) -> Mapping[str, Any]:
    try:
        return _strict_json_bytes(Path(path).expanduser().resolve().read_bytes())
    except OSError as error:
        raise ResearchCorpusError("CORPUS_REPAIR_SOURCE_READ_FAILED") from error


def publish_research_corpus_repair_artifacts(
    *,
    bundle: Mapping[str, Any],
    patch_snapshots: Sequence[Mapping[str, Any]],
    output_root: Path,
) -> None:
    if (
        not isinstance(bundle, Mapping)
        or tuple(_validator().iter_errors(bundle))
        or bundle.get("repair_bundle_hash")
        != research_corpus_repair_bundle_hash(bundle)
    ):
        raise ResearchCorpusError("CORPUS_REPAIR_BUNDLE_INVALID")
    expected_patches = {
        (
            patch["period"],
            patch["snapshot_id"],
            patch["snapshot_hash"],
            patch["expected_attestation_hash"],
        )
        for repair in bundle["repairs"]
        for patch in repair["patches"]
    }
    actual_patches = set()
    for patch in patch_snapshots:
        attestation = _snapshot_integrity(patch, degraded_allowed=False)
        request = patch.get("request")
        if not isinstance(request, Mapping):
            raise ResearchCorpusError("CORPUS_REPAIR_PATCH_SCOPE_INVALID")
        identity = (
            request.get("period"),
            patch.get("snapshot_id"),
            patch.get("snapshot_hash"),
            attestation,
        )
        if identity in actual_patches:
            raise ResearchCorpusError("CORPUS_REPAIR_PATCH_SCOPE_INVALID")
        actual_patches.add(identity)
    if actual_patches != expected_patches:
        raise ResearchCorpusError("CORPUS_REPAIR_PATCH_SET_INCOMPLETE")
    root = Path(output_root).expanduser().resolve()
    managed_directories = (
        root,
        root / "repairs",
        root / "repairs" / "source",
        root / "repairs" / "bundles",
    )
    for directory in managed_directories:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    for patch in patch_snapshots:
        request = patch["request"]
        source_directory = (
            root
            / "repairs"
            / "source"
            / f"{request['market']}_{request['data_family']}_{request['symbol']}"
        )
        source_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(source_directory, 0o700)
        path = (
            source_directory
            / f"{request['period']}.json"
        )
        _publish_exact(path, canonical_json(patch).encode("utf-8"))
    _publish_exact(
        root
        / "repairs"
        / "bundles"
        / f"{bundle['repair_bundle_id']}.json",
        canonical_json(bundle).encode("utf-8"),
    )
