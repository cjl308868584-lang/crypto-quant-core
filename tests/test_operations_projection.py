"""Tail-blind operations projection contract tests."""

import dataclasses
import unittest

from crypto_quant.operations_projection import (
    ChallengerOperationsSource,
    OperationsProjectionError,
    OperationsProjectionSources,
    ReleaseOperationsSource,
    SourceProvenance,
    SystemPaperOperationsSource,
    build_operations_projection,
)


NOW = "2026-08-05T00:25:00.000Z"
COMMIT = "3a4283bc06099f821ca72947535748d3e3760180"


def provenance(kind, observed_at="2026-08-05T00:10:00.000Z"):
    return SourceProvenance(
        source_kind=kind,
        source_sha256="a" * 64,
        observed_at=observed_at,
    )


def release_source(**overrides):
    values = {
        "package_version": "0.59.0",
        "main_commit": COMMIT,
        "release_tag": "v0.59.0",
        "tag_commit": COMMIT,
        "identity_status": "VERIFIED",
        "provenance": provenance(
            "RELEASE_IDENTITY", "2026-08-04T23:00:00.000Z"
        ),
    }
    values.update(overrides)
    return ReleaseOperationsSource(**values)


def challenger_source(**overrides):
    values = {
        "phase": "LEGACY_FAILED_REPLACEMENT_NOT_STARTED",
        "service_health": "NOT_LOADED",
        "evidence_health": "NOT_AVAILABLE",
        "verified_slot_count": 0,
        "completed_episode_count": 0,
        "active_episode_present": False,
        "next_required_slot": None,
        "gate_status": "NOT_AVAILABLE",
        "incident_count": 1,
        "provenance": provenance("CHALLENGER_OPERATIONS"),
    }
    values.update(overrides)
    return ChallengerOperationsSource(**values)


def paper_source(**overrides):
    values = {
        "phase": "NOT_INSTALLED",
        "service_health": "NOT_LOADED",
        "evidence_health": "NOT_AVAILABLE",
        "elapsed_days": 0,
        "verified_slot_count": 0,
        "next_required_slot": None,
        "submitted_order_count": 0,
        "filled_order_count": 0,
        "partially_filled_order_count": 0,
        "cancelled_order_count": 0,
        "rejected_order_count": 0,
        "timeout_unknown_order_count": 0,
        "reconciliation_status": "NOT_AVAILABLE",
        "risk_state": "NOT_AVAILABLE",
        "gate_status": "NOT_EVALUATED",
        "incident_count": 0,
        "provenance": provenance("SYSTEM_PAPER_OPERATIONS"),
    }
    values.update(overrides)
    return SystemPaperOperationsSource(**values)


class OperationsProjectionSourceBoundaryTests(unittest.TestCase):
    def sources(self, calls=None):
        calls = calls if calls is not None else []
        return OperationsProjectionSources(
            release_loader=lambda: calls.append("release") or release_source(),
            challenger_loader=(
                lambda: calls.append("challenger") or challenger_source()
            ),
            system_paper_loader=(
                lambda: calls.append("system_paper") or paper_source()
            ),
        )

    def assert_reason(self, reason, operation):
        with self.assertRaises(OperationsProjectionError) as caught:
            operation()
        self.assertEqual(caught.exception.reason_code, reason)
        self.assertEqual(str(caught.exception), reason)

    def test_calls_each_loader_once_in_fixed_order(self):
        calls = []

        projection = build_operations_projection(NOW, self.sources(calls))

        self.assertEqual(calls, ["release", "challenger", "system_paper"])
        self.assertEqual(projection["schema_version"], "1.0.0")

    def test_rejects_wrong_sources_container_without_calling_it(self):
        self.assert_reason(
            "OPERATIONS_PROJECTION_SOURCES_INVALID",
            lambda: build_operations_projection(NOW, object()),
        )

    def test_loader_failure_does_not_expose_exception_text(self):
        secret = "/Users/example/private/API_SECRET"

        def fail():
            raise RuntimeError(secret)

        sources = OperationsProjectionSources(
            release_loader=fail,
            challenger_loader=challenger_source,
            system_paper_loader=paper_source,
        )
        with self.assertRaises(OperationsProjectionError) as caught:
            build_operations_projection(NOW, sources)
        self.assertEqual(
            caught.exception.reason_code,
            "OPERATIONS_PROJECTION_SOURCE_LOAD_FAILED",
        )
        self.assertNotIn(secret, str(caught.exception))

    def test_rejects_wrong_loader_return_type(self):
        sources = OperationsProjectionSources(
            release_loader=lambda: {},
            challenger_loader=challenger_source,
            system_paper_loader=paper_source,
        )
        self.assert_reason(
            "OPERATIONS_PROJECTION_SOURCE_INVALID",
            lambda: build_operations_projection(NOW, sources),
        )

    def test_source_records_are_frozen_and_slotted(self):
        values = (
            provenance("RELEASE_IDENTITY"),
            release_source(),
            challenger_source(),
            paper_source(),
            self.sources(),
        )
        for value in values:
            with self.subTest(type=type(value).__name__):
                self.assertFalse(hasattr(value, "__dict__"))
                with self.assertRaises(
                    (dataclasses.FrozenInstanceError, AttributeError, TypeError)
                ):
                    value.hostile_extra = {"secret": "must-not-cross"}

    def test_projection_does_not_mutate_sources(self):
        release = release_source()
        challenger = challenger_source()
        paper = paper_source()
        before = (release, challenger, paper)
        sources = OperationsProjectionSources(
            release_loader=lambda: release,
            challenger_loader=lambda: challenger,
            system_paper_loader=lambda: paper,
        )

        build_operations_projection(NOW, sources)

        self.assertEqual((release, challenger, paper), before)


if __name__ == "__main__":
    unittest.main()
