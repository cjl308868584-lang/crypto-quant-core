"""Deterministic operations alert boundary tests."""

import json
import unittest

from crypto_quant.canonical import canonical_json
from crypto_quant.operations_alerts import (
    OperationsAlertsError,
    build_operations_status_body,
    derive_operations_alerts,
)
from crypto_quant.operations_projection import (
    ChallengerOperationsSource,
    OperationsProjectionSources,
    ReleaseOperationsSource,
    SourceProvenance,
    SystemPaperOperationsSource,
    build_operations_projection,
)


NOW = "2026-08-05T00:25:00.000Z"
OBSERVED = "2026-08-05T00:10:00.000Z"
COMMIT = "7cb3dc47984581e2c5873d7ece8417b137168303"


def _provenance(kind, observed_at=OBSERVED):
    return SourceProvenance(kind, "a" * 64, observed_at)


def _projection_body(*, challenger=None, paper=None):
    challenger_values = {
        "phase": "REPLACEMENT_NOT_STARTED",
        "service_health": "NOT_LOADED",
        "evidence_health": "NOT_AVAILABLE",
        "verified_slot_count": 0,
        "completed_episode_count": 0,
        "active_episode_present": False,
        "next_required_slot": None,
        "gate_status": "NOT_AVAILABLE",
        "incident_count": 0,
        "provenance": _provenance("CHALLENGER_OPERATIONS"),
    }
    challenger_values.update(challenger or {})
    paper_values = {
        "phase": "COLLECTING",
        "service_health": "HEALTHY",
        "evidence_health": "VERIFIED",
        "elapsed_days": 1,
        "verified_slot_count": 6,
        "next_required_slot": "2026-08-05T04:00:00.000Z",
        "submitted_order_count": 4,
        "filled_order_count": 2,
        "partially_filled_order_count": 1,
        "cancelled_order_count": 0,
        "rejected_order_count": 1,
        "timeout_unknown_order_count": 0,
        "reconciliation_status": "RECONCILED",
        "risk_state": "NORMAL",
        "gate_status": "NOT_EVALUATED",
        "incident_count": 0,
        "provenance": _provenance("SYSTEM_PAPER_OPERATIONS"),
    }
    paper_values.update(paper or {})
    projection = build_operations_projection(
        NOW,
        OperationsProjectionSources(
            release_loader=lambda: ReleaseOperationsSource(
                package_version="0.60.0",
                main_commit=COMMIT,
                release_tag="v0.60.0",
                tag_commit=COMMIT,
                identity_status="VERIFIED",
                provenance=_provenance(
                    "RELEASE_IDENTITY", "2026-08-04T23:00:00.000Z"
                ),
            ),
            challenger_loader=lambda: ChallengerOperationsSource(
                **challenger_values
            ),
            system_paper_loader=lambda: SystemPaperOperationsSource(
                **paper_values
            ),
        ),
    )
    return canonical_json(projection).encode("utf-8")


class OperationsAlertsStrictBoundaryTests(unittest.TestCase):
    def assert_invalid(self, body):
        with self.assertRaises(OperationsAlertsError) as caught:
            derive_operations_alerts(body)
        self.assertEqual(
            caught.exception.reason_code,
            "OPERATIONS_ALERTS_PROJECTION_INVALID",
        )
        self.assertEqual(str(caught.exception), caught.exception.reason_code)

    def test_healthy_collecting_paper_has_no_alerts_and_allows_observed_risk(self):
        alerts = derive_operations_alerts(_projection_body())

        self.assertEqual(alerts["schema_version"], "1.0.0")
        self.assertEqual(alerts["status"], "HEALTHY")
        self.assertTrue(alerts["new_risk_allowed"])
        self.assertEqual(
            alerts["counts"],
            {"INFO": 0, "WARNING": 0, "CRITICAL": 0},
        )
        self.assertEqual(alerts["alerts"], [])

    def test_rejects_non_bytes_noncanonical_duplicate_float_hash_and_unknown(self):
        valid = _projection_body()
        wrong_hash = json.loads(valid)
        wrong_hash["projection_hash"] = "0" * 64
        unknown = json.loads(valid)
        unknown["private_path"] = "/Users/example/private"
        cases = (
            json.loads(valid),
            valid + b"\n",
            b'{"x":1,"x":2}',
            b'{"x":1.25}',
            canonical_json(wrong_hash).encode("utf-8"),
            canonical_json(unknown).encode("utf-8"),
        )
        for body in cases:
            with self.subTest(body_type=type(body).__name__):
                self.assert_invalid(body)


class OperationsAlertClassificationTests(unittest.TestCase):
    @staticmethod
    def record(alert_id, severity, stream, reason_code, risk_effect):
        return {
            "alert_id": alert_id,
            "severity": severity,
            "stream": stream,
            "reason_code": reason_code,
            "risk_effect": risk_effect,
        }

    def test_challenger_warning_conditions_are_stable_and_do_not_couple_paper(self):
        warning = self.record(
            "OPS-CHALLENGER-SERVICE-DEGRADED",
            "WARNING",
            "CHALLENGER",
            "CHALLENGER_SERVICE_DEGRADED",
            "NO_CHANGE",
        )
        stale = self.record(
            "OPS-CHALLENGER-EVIDENCE-STALE",
            "WARNING",
            "CHALLENGER",
            "CHALLENGER_EVIDENCE_STALE",
            "NO_CHANGE",
        )
        incident = self.record(
            "OPS-CHALLENGER-INCIDENT",
            "WARNING",
            "CHALLENGER",
            "CHALLENGER_INCIDENT_DETECTED",
            "NO_CHANGE",
        )
        cases = (
            ({"service_health": "DEGRADED"}, [warning]),
            ({"evidence_health": "STALE"}, [stale]),
            (
                {
                    "evidence_health": "STALE",
                    "provenance": _provenance(
                        "CHALLENGER_OPERATIONS",
                        "2026-08-04T23:00:00.000Z",
                    ),
                },
                [stale],
            ),
            ({"evidence_health": "INCIDENT_DETECTED"}, [incident]),
            ({"incident_count": 2}, [incident]),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                result = derive_operations_alerts(
                    _projection_body(challenger=overrides)
                )
                self.assertEqual(result["alerts"], expected)
                self.assertEqual(
                    result["counts"],
                    {"INFO": 0, "WARNING": 1, "CRITICAL": 0},
                )
                self.assertTrue(result["new_risk_allowed"])

    def test_failed_closed_conditions_emit_system_then_specific_alert(self):
        system = self.record(
            "OPS-SYSTEM-FAILED-CLOSED",
            "CRITICAL",
            "SYSTEM",
            "OPERATIONS_PROJECTION_FAILED_CLOSED",
            "BLOCK_NEW_RISK",
        )
        cases = (
            (
                {"challenger": {"service_health": "FAILED_CLOSED"}},
                self.record(
                    "OPS-CHALLENGER-SERVICE-FAILED-CLOSED",
                    "CRITICAL",
                    "CHALLENGER",
                    "CHALLENGER_SERVICE_FAILED_CLOSED",
                    "BLOCK_NEW_RISK",
                ),
            ),
            (
                {"challenger": {"evidence_health": "FAILED_CLOSED"}},
                self.record(
                    "OPS-CHALLENGER-EVIDENCE-FAILED-CLOSED",
                    "CRITICAL",
                    "CHALLENGER",
                    "CHALLENGER_EVIDENCE_FAILED_CLOSED",
                    "BLOCK_NEW_RISK",
                ),
            ),
            (
                {"paper": {"service_health": "FAILED_CLOSED"}},
                self.record(
                    "OPS-PAPER-SERVICE-FAILED-CLOSED",
                    "CRITICAL",
                    "SYSTEM_PAPER",
                    "SYSTEM_PAPER_SERVICE_FAILED_CLOSED",
                    "BLOCK_NEW_RISK",
                ),
            ),
            (
                {"paper": {"evidence_health": "FAILED_CLOSED"}},
                self.record(
                    "OPS-PAPER-EVIDENCE-FAILED-CLOSED",
                    "CRITICAL",
                    "SYSTEM_PAPER",
                    "SYSTEM_PAPER_EVIDENCE_FAILED_CLOSED",
                    "BLOCK_NEW_RISK",
                ),
            ),
            (
                {"paper": {"reconciliation_status": "FAILED_CLOSED"}},
                self.record(
                    "OPS-PAPER-RECONCILIATION-FAILED-CLOSED",
                    "CRITICAL",
                    "SYSTEM_PAPER",
                    "SYSTEM_PAPER_RECONCILIATION_FAILED_CLOSED",
                    "BLOCK_NEW_RISK",
                ),
            ),
        )
        for overrides, specific in cases:
            with self.subTest(overrides=overrides):
                result = derive_operations_alerts(
                    _projection_body(**overrides)
                )
                self.assertEqual(result["alerts"], [system, specific])
                self.assertEqual(
                    result["counts"],
                    {"INFO": 0, "WARNING": 0, "CRITICAL": 2},
                )
                self.assertFalse(result["new_risk_allowed"])

    def test_paper_uncertainty_and_risk_conditions_block_observed_new_risk(self):
        cases = (
            (
                {
                    "submitted_order_count": 5,
                    "timeout_unknown_order_count": 1,
                },
                "OPS-PAPER-UNKNOWN-ORDER",
                "CRITICAL",
                "SYSTEM_PAPER_UNKNOWN_ORDER_PRESENT",
            ),
            (
                {"risk_state": "HALT"},
                "OPS-PAPER-RISK-HALT",
                "CRITICAL",
                "SYSTEM_PAPER_RISK_HALTED",
            ),
            (
                {"risk_state": "HARD_BOUNDARY"},
                "OPS-PAPER-RISK-HALT",
                "CRITICAL",
                "SYSTEM_PAPER_RISK_HALTED",
            ),
            (
                {"service_health": "DEGRADED"},
                "OPS-PAPER-SERVICE-DEGRADED",
                "WARNING",
                "SYSTEM_PAPER_SERVICE_DEGRADED",
            ),
            (
                {"evidence_health": "STALE"},
                "OPS-PAPER-EVIDENCE-STALE",
                "WARNING",
                "SYSTEM_PAPER_EVIDENCE_STALE",
            ),
            (
                {"evidence_health": "INCIDENT_DETECTED"},
                "OPS-PAPER-INCIDENT",
                "WARNING",
                "SYSTEM_PAPER_INCIDENT_DETECTED",
            ),
            (
                {"incident_count": 3},
                "OPS-PAPER-INCIDENT",
                "WARNING",
                "SYSTEM_PAPER_INCIDENT_DETECTED",
            ),
            (
                {"risk_state": "WARNING"},
                "OPS-PAPER-RISK-REDUCED",
                "WARNING",
                "SYSTEM_PAPER_RISK_REDUCED",
            ),
            (
                {"risk_state": "REDUCE"},
                "OPS-PAPER-RISK-REDUCED",
                "WARNING",
                "SYSTEM_PAPER_RISK_REDUCED",
            ),
        )
        for overrides, alert_id, severity, reason_code in cases:
            with self.subTest(overrides=overrides):
                result = derive_operations_alerts(
                    _projection_body(paper=overrides)
                )
                self.assertIn(
                    self.record(
                        alert_id,
                        severity,
                        "SYSTEM_PAPER",
                        reason_code,
                        "BLOCK_NEW_RISK",
                    ),
                    result["alerts"],
                )
                self.assertFalse(result["new_risk_allowed"])

    def test_not_started_and_final_phases_never_observe_new_risk_allowed(self):
        not_started = {
            "phase": "INSTALLED_NOT_STARTED",
            "service_health": "HEALTHY",
            "evidence_health": "VERIFIED",
            "elapsed_days": 0,
            "verified_slot_count": 0,
            "next_required_slot": None,
            "submitted_order_count": 0,
            "filled_order_count": 0,
            "partially_filled_order_count": 0,
            "cancelled_order_count": 0,
            "rejected_order_count": 0,
            "timeout_unknown_order_count": 0,
            "reconciliation_status": "RECONCILED",
            "risk_state": "NORMAL",
            "gate_status": "NOT_EVALUATED",
        }
        final = {
            "phase": "FINAL",
            "next_required_slot": None,
            "gate_status": "SYSTEM_PAPER_GATE_PASS",
        }
        self.assertFalse(
            derive_operations_alerts(
                _projection_body(paper=not_started)
            )["new_risk_allowed"]
        )
        self.assertFalse(
            derive_operations_alerts(
                _projection_body(paper=final)
            )["new_risk_allowed"]
        )

    def test_status_body_is_canonical_byte_stable_and_contains_exact_projection(self):
        body = _projection_body()

        first = build_operations_status_body(body)
        second = build_operations_status_body(body)
        value = json.loads(first)

        self.assertEqual(first, second)
        self.assertEqual(first, canonical_json(value).encode("utf-8"))
        self.assertEqual(value["schema_version"], "1.0.0")
        self.assertEqual(value["projection"], json.loads(body))
        self.assertEqual(
            value["alert_summary"], derive_operations_alerts(body)
        )


if __name__ == "__main__":
    unittest.main()
