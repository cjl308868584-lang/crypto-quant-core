"""Fail-closed maintenance coordinator for Challenger cohort evidence."""

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .canonical import utc_datetime
from .challenger_cohort_daily_archive import (
    acquire_challenger_cohort_daily_archives,
)
from .challenger_cohort_economic_results import (
    publish_all_cohort_economic_results,
)
from .challenger_cohort_episode_receipt import (
    observe_challenger_cohort_episodes,
)
from .market_data import PublicArchiveTransport


class ChallengerCohortEvidenceMaintenanceError(ValueError):
    """A maintenance phase violated its frozen contract."""


_RECEIPT_STATUSES = frozenset(
    {
        "COHORT_NOT_STARTED_VERIFIED",
        "COHORT_EPISODE_IN_PROGRESS_VERIFIED",
        "COHORT_CONTINUITY_COLLECTING_VERIFIED",
        "COHORT_SLOT_WINDOW_COMPLETED_VERIFIED",
    }
)
_ARCHIVE_PENDING_STATUSES = frozenset(
    {
        "COHORT_DAILY_ARCHIVE_PENDING",
        "COHORT_DAILY_ARCHIVE_PARTIAL",
    }
)


def _mapping(value: object, error: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ChallengerCohortEvidenceMaintenanceError(error)
    return value


def _integer(
    source: Mapping[str, Any],
    name: str,
    *,
    error: str,
) -> int:
    value = source.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ChallengerCohortEvidenceMaintenanceError(error)
    return value


def _zero_security_counts(
    source: Mapping[str, Any],
    names: tuple[str, ...],
    *,
    error: str,
) -> None:
    for name in names:
        if _integer(source, name, error=error) != 0:
            raise ChallengerCohortEvidenceMaintenanceError(error)


def maintain_challenger_cohort_evidence(
    *,
    cohort_plan_path: Path,
    economic_plan_path: Path,
    episode_receipt_output_root: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    archive_output_root: Path,
    result_output_root: Path,
    observed_at: datetime,
    transport: PublicArchiveTransport,
    observer=None,
    archive_acquirer=None,
    result_publisher=None,
    launchctl_runner=None,
    receipt_loader=None,
) -> Mapping[str, Any]:
    """Run receipt, archive and result maintenance in one fixed order."""

    try:
        observed_text = utc_datetime(observed_at)
    except Exception as error:
        raise ChallengerCohortEvidenceMaintenanceError(
            "CHALLENGER_COHORT_EVIDENCE_TIME_INVALID"
        ) from error
    if not hasattr(transport, "get"):
        raise ChallengerCohortEvidenceMaintenanceError(
            "CHALLENGER_COHORT_EVIDENCE_TRANSPORT_INVALID"
        )

    receipt = _mapping(
        (observer or observe_challenger_cohort_episodes)(
            cohort_plan_path=cohort_plan_path,
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
            receipt_output_root=episode_receipt_output_root,
            clock=lambda: observed_text,
            _launchctl_runner=launchctl_runner,
        ),
        "CHALLENGER_COHORT_EVIDENCE_RECEIPT_SUMMARY_INVALID",
    )
    if (
        receipt.get("status") not in _RECEIPT_STATUSES
        or receipt.get("observed_at") != observed_text
    ):
        raise ChallengerCohortEvidenceMaintenanceError(
            "CHALLENGER_COHORT_EVIDENCE_RECEIPT_SUMMARY_INVALID"
        )
    receipt_error = "CHALLENGER_COHORT_EVIDENCE_RECEIPT_SUMMARY_INVALID"
    receipt_count = _integer(
        receipt, "completed_episode_count", error=receipt_error
    )
    receipt_created = _integer(
        receipt, "receipt_created_count", error=receipt_error
    )
    cohort_slots = _integer(
        receipt, "cohort_slot_count", error=receipt_error
    )
    if receipt_created > receipt_count:
        raise ChallengerCohortEvidenceMaintenanceError(receipt_error)
    _zero_security_counts(
        receipt,
        (
            "network_request_count",
            "broker_request_count",
            "order_submission_count",
            "state_write_count",
            "runner_invocation_count",
        ),
        error=receipt_error,
    )

    archive = _mapping(
        (archive_acquirer or acquire_challenger_cohort_daily_archives)(
            cohort_plan_path=cohort_plan_path,
            episode_receipt_output_root=episode_receipt_output_root,
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
            archive_output_root=archive_output_root,
            observed_at=observed_text,
            transport=transport,
            receipt_loader=receipt_loader,
        ),
        "CHALLENGER_COHORT_EVIDENCE_ARCHIVE_SUMMARY_INVALID",
    )
    archive_error = "CHALLENGER_COHORT_EVIDENCE_ARCHIVE_SUMMARY_INVALID"
    archive_status = archive.get("status")
    allowed_archive_statuses = _ARCHIVE_PENDING_STATUSES | {
        "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES",
        "COHORT_DAILY_ARCHIVE_COMPLETE",
    }
    if (
        archive_status not in allowed_archive_statuses
        or archive.get("observed_at") != observed_text
    ):
        raise ChallengerCohortEvidenceMaintenanceError(archive_error)
    archive_receipts = _integer(
        archive, "episode_receipt_count", error=archive_error
    )
    required_days = _integer(
        archive, "required_day_count", error=archive_error
    )
    verified_days = _integer(
        archive, "verified_day_count", error=archive_error
    )
    archive_requests = _integer(
        archive, "network_request_count", error=archive_error
    )
    if (
        archive_receipts != receipt_count
        or verified_days > required_days
        or (
            archive_status == "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES"
            and (receipt_count or required_days or verified_days)
        )
        or (
            archive_status == "COHORT_DAILY_ARCHIVE_COMPLETE"
            and (not required_days or verified_days != required_days)
        )
    ):
        raise ChallengerCohortEvidenceMaintenanceError(archive_error)
    _zero_security_counts(
        archive,
        (
            "broker_request_count",
            "order_submission_count",
            "strategy_state_write_count",
            "runner_invocation_count",
        ),
        error=archive_error,
    )

    receipt_stage = {
        "executed": True,
        "status": receipt["status"],
        "cohort_slot_count": cohort_slots,
        "completed_episode_count": receipt_count,
        "receipt_created_count": receipt_created,
    }
    archive_stage = {
        "executed": True,
        "status": archive_status,
        "required_day_count": required_days,
        "verified_day_count": verified_days,
        "network_request_count": archive_requests,
    }

    if archive_status == "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES":
        return {
            "status": "COHORT_EVIDENCE_NO_COMPLETED_EPISODES",
            "observed_at": observed_text,
            "receipt_stage": receipt_stage,
            "archive_stage": archive_stage,
            "result_stage": {
                "executed": False,
                "status": "NOT_EXECUTED_NO_COMPLETED_EPISODES",
            },
            "network_request_count": archive_requests,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "strategy_state_write_count": 0,
            "runner_invocation_count": 0,
        }
    if archive_status in _ARCHIVE_PENDING_STATUSES:
        return {
            "status": "COHORT_EVIDENCE_WAITING_ARCHIVES",
            "observed_at": observed_text,
            "receipt_stage": receipt_stage,
            "archive_stage": archive_stage,
            "result_stage": {
                "executed": False,
                "status": "NOT_EXECUTED_ARCHIVES_INCOMPLETE",
            },
            "network_request_count": archive_requests,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "strategy_state_write_count": 0,
            "runner_invocation_count": 0,
        }

    result = _mapping(
        (result_publisher or publish_all_cohort_economic_results)(
            cohort_plan_path=cohort_plan_path,
            economic_plan_path=economic_plan_path,
            episode_receipt_output_root=episode_receipt_output_root,
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
            archive_output_root=archive_output_root,
            result_output_root=result_output_root,
            receipt_loader=receipt_loader,
        ),
        "CHALLENGER_COHORT_EVIDENCE_RESULT_SUMMARY_INVALID",
    )
    result_error = "CHALLENGER_COHORT_EVIDENCE_RESULT_SUMMARY_INVALID"
    if result.get("status") != "DESCRIPTIVE_NO_EARLY_SUCCESS":
        raise ChallengerCohortEvidenceMaintenanceError(result_error)
    result_receipts = _integer(
        result, "episode_receipt_count", error=result_error
    )
    result_count = _integer(result, "result_count", error=result_error)
    index_count = _integer(result, "index_count", error=result_error)
    new_results = _integer(
        result, "new_result_count", error=result_error
    )
    new_indexes = _integer(
        result, "new_index_count", error=result_error
    )
    if (
        result_receipts != receipt_count
        or result_count != receipt_count
        or index_count != receipt_count
        or new_results > result_count
        or new_indexes > index_count
    ):
        raise ChallengerCohortEvidenceMaintenanceError(result_error)
    _zero_security_counts(
        result,
        (
            "market_request_count",
            "broker_request_count",
            "order_submission_count",
            "state_write_count",
            "runner_invocation_count",
        ),
        error=result_error,
    )
    return {
        "status": (
            "COHORT_EVIDENCE_MAINTAINED_DESCRIPTIVE_NO_EARLY_SUCCESS"
        ),
        "observed_at": observed_text,
        "receipt_stage": receipt_stage,
        "archive_stage": archive_stage,
        "result_stage": {
            "executed": True,
            "status": result["status"],
            "result_count": result_count,
            "index_count": index_count,
            "new_result_count": new_results,
            "new_index_count": new_indexes,
        },
        "network_request_count": archive_requests,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "strategy_state_write_count": 0,
        "runner_invocation_count": 0,
    }
