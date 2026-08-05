"""Deterministic alerts over a strict operations projection replay."""

from typing import Any, Dict, Mapping

from .canonical import canonical_json
from .operations_projection import load_operations_projection_bytes


class OperationsAlertsError(ValueError):
    """An operations alert projection failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _load_projection(projection_body: bytes) -> Mapping[str, Any]:
    try:
        return load_operations_projection_bytes(projection_body)
    except Exception as error:
        raise OperationsAlertsError(
            "OPERATIONS_ALERTS_PROJECTION_INVALID"
        ) from error


def _derive_verified_operations_alerts(
    projection: Mapping[str, Any],
) -> Dict[str, Any]:
    challenger = projection["challenger"]
    paper = projection["system_paper"]
    alerts = []

    def add(alert_id, severity, stream, reason_code, risk_effect):
        alerts.append(
            {
                "alert_id": alert_id,
                "severity": severity,
                "stream": stream,
                "reason_code": reason_code,
                "risk_effect": risk_effect,
            }
        )

    if projection["status"] == "FAILED_CLOSED":
        add(
            "OPS-SYSTEM-FAILED-CLOSED",
            "CRITICAL",
            "SYSTEM",
            "OPERATIONS_PROJECTION_FAILED_CLOSED",
            "BLOCK_NEW_RISK",
        )

    if challenger["service_health"] == "FAILED_CLOSED":
        add(
            "OPS-CHALLENGER-SERVICE-FAILED-CLOSED",
            "CRITICAL",
            "CHALLENGER",
            "CHALLENGER_SERVICE_FAILED_CLOSED",
            "BLOCK_NEW_RISK",
        )
    if challenger["evidence_health"] == "FAILED_CLOSED":
        add(
            "OPS-CHALLENGER-EVIDENCE-FAILED-CLOSED",
            "CRITICAL",
            "CHALLENGER",
            "CHALLENGER_EVIDENCE_FAILED_CLOSED",
            "BLOCK_NEW_RISK",
        )
    if challenger["service_health"] == "DEGRADED":
        add(
            "OPS-CHALLENGER-SERVICE-DEGRADED",
            "WARNING",
            "CHALLENGER",
            "CHALLENGER_SERVICE_DEGRADED",
            "NO_CHANGE",
        )
    if (
        challenger["evidence_health"] == "STALE"
        or challenger["provenance"]["freshness"] == "STALE"
    ):
        add(
            "OPS-CHALLENGER-EVIDENCE-STALE",
            "WARNING",
            "CHALLENGER",
            "CHALLENGER_EVIDENCE_STALE",
            "NO_CHANGE",
        )
    if (
        challenger["evidence_health"] == "INCIDENT_DETECTED"
        or challenger["incident_count"] > 0
    ):
        add(
            "OPS-CHALLENGER-INCIDENT",
            "WARNING",
            "CHALLENGER",
            "CHALLENGER_INCIDENT_DETECTED",
            "NO_CHANGE",
        )

    if paper["service_health"] == "FAILED_CLOSED":
        add(
            "OPS-PAPER-SERVICE-FAILED-CLOSED",
            "CRITICAL",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_SERVICE_FAILED_CLOSED",
            "BLOCK_NEW_RISK",
        )
    if paper["evidence_health"] == "FAILED_CLOSED":
        add(
            "OPS-PAPER-EVIDENCE-FAILED-CLOSED",
            "CRITICAL",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_EVIDENCE_FAILED_CLOSED",
            "BLOCK_NEW_RISK",
        )
    if paper["reconciliation_status"] == "FAILED_CLOSED":
        add(
            "OPS-PAPER-RECONCILIATION-FAILED-CLOSED",
            "CRITICAL",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_RECONCILIATION_FAILED_CLOSED",
            "BLOCK_NEW_RISK",
        )
    if paper["timeout_unknown_order_count"] > 0:
        add(
            "OPS-PAPER-UNKNOWN-ORDER",
            "CRITICAL",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_UNKNOWN_ORDER_PRESENT",
            "BLOCK_NEW_RISK",
        )
    if paper["risk_state"] in {"HALT", "HARD_BOUNDARY"}:
        add(
            "OPS-PAPER-RISK-HALT",
            "CRITICAL",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_RISK_HALTED",
            "BLOCK_NEW_RISK",
        )
    if paper["service_health"] == "DEGRADED":
        add(
            "OPS-PAPER-SERVICE-DEGRADED",
            "WARNING",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_SERVICE_DEGRADED",
            "BLOCK_NEW_RISK",
        )
    if (
        paper["evidence_health"] == "STALE"
        or paper["provenance"]["freshness"] == "STALE"
    ):
        add(
            "OPS-PAPER-EVIDENCE-STALE",
            "WARNING",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_EVIDENCE_STALE",
            "BLOCK_NEW_RISK",
        )
    if (
        paper["evidence_health"] == "INCIDENT_DETECTED"
        or paper["incident_count"] > 0
    ):
        add(
            "OPS-PAPER-INCIDENT",
            "WARNING",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_INCIDENT_DETECTED",
            "BLOCK_NEW_RISK",
        )
    if paper["risk_state"] in {"WARNING", "REDUCE"}:
        add(
            "OPS-PAPER-RISK-REDUCED",
            "WARNING",
            "SYSTEM_PAPER",
            "SYSTEM_PAPER_RISK_REDUCED",
            "BLOCK_NEW_RISK",
        )

    counts = {"INFO": 0, "WARNING": 0, "CRITICAL": 0}
    for alert in alerts:
        counts[alert["severity"]] += 1
    new_risk_allowed = (
        paper["phase"] == "COLLECTING"
        and paper["service_health"] == "HEALTHY"
        and paper["evidence_health"] == "VERIFIED"
        and paper["provenance"]["freshness"] == "FRESH"
        and paper["reconciliation_status"] == "RECONCILED"
        and paper["risk_state"] == "NORMAL"
        and paper["incident_count"] == 0
        and paper["timeout_unknown_order_count"] == 0
        and projection["status"] != "FAILED_CLOSED"
        and not any(
            alert["severity"] == "CRITICAL"
            and alert["stream"] in {"SYSTEM", "SYSTEM_PAPER"}
            for alert in alerts
        )
    )
    return {
        "schema_version": "1.0.0",
        "status": projection["status"],
        "new_risk_allowed": new_risk_allowed,
        "counts": counts,
        "alerts": alerts,
    }


def derive_operations_alerts(
    projection_body: bytes,
) -> Mapping[str, Any]:
    """Strictly replay projection bytes and derive allowlisted alerts."""

    projection = _load_projection(projection_body)
    return _derive_verified_operations_alerts(projection)


def build_operations_status_body(projection_body: bytes) -> bytes:
    """Build canonical dashboard status bytes from one strict replay."""

    projection = _load_projection(projection_body)
    value = {
        "schema_version": "1.0.0",
        "projection": projection,
        "alert_summary": _derive_verified_operations_alerts(projection),
    }
    return canonical_json(value).encode("utf-8")
