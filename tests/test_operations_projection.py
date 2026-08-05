"""Tail-blind operations projection contract tests."""

import ast
import dataclasses
import json
import sqlite3
import socket
import subprocess
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import business_hash, canonical_json

from crypto_quant.operations_projection import (
    ChallengerOperationsSource,
    OperationsProjectionError,
    OperationsProjectionSources,
    ReleaseOperationsSource,
    SourceProvenance,
    SystemPaperOperationsSource,
    build_operations_projection,
    load_operations_projection_bytes,
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


class OperationsProjectionValidationTests(unittest.TestCase):
    def build(self, *, now=NOW, release=None, challenger=None, paper=None):
        return build_operations_projection(
            now,
            OperationsProjectionSources(
                release_loader=lambda: release or release_source(),
                challenger_loader=lambda: challenger or challenger_source(),
                system_paper_loader=lambda: paper or paper_source(),
            ),
        )

    def assert_reason(self, reason, operation):
        with self.assertRaises(OperationsProjectionError) as caught:
            operation()
        self.assertEqual(caught.exception.reason_code, reason)

    def test_rejects_release_identity_mismatches(self):
        invalid = (
            {"package_version": "0.59"},
            {"package_version": "0.59.0", "release_tag": "v0.59.1"},
            {"main_commit": "A" * 40},
            {"tag_commit": "b" * 40},
            {"identity_status": "UNVERIFIED"},
        )
        for override in invalid:
            with self.subTest(override=override):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_RELEASE_IDENTITY_MISMATCH",
                    lambda override=override: self.build(
                        release=release_source(**override)
                    ),
                )

    def test_rejects_invalid_provenance(self):
        invalid = (
            provenance("WRONG_KIND"),
            SourceProvenance(
                "RELEASE_IDENTITY", "A" * 64, "2026-08-04T23:00:00.000Z"
            ),
            SourceProvenance(
                "RELEASE_IDENTITY", "a" * 63, "2026-08-04T23:00:00.000Z"
            ),
        )
        for value in invalid:
            with self.subTest(value=value):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_SOURCE_INVALID",
                    lambda value=value: self.build(
                        release=release_source(provenance=value)
                    ),
                )

    def test_rejects_noncanonical_projection_and_observation_times(self):
        cases = (
            ("2026-08-05T00:25:00Z", None),
            ("2026-08-05T08:25:00.000+08:00", None),
            ("2026-08-05T00:25:00.000001Z", None),
            (NOW, "2026-08-05T00:10:00Z"),
            (NOW, "2026-08-05T08:10:00.000+08:00"),
        )
        for now, observed_at in cases:
            with self.subTest(now=now, observed_at=observed_at):
                challenger = (
                    challenger_source(
                        provenance=provenance(
                            "CHALLENGER_OPERATIONS", observed_at
                        )
                    )
                    if observed_at
                    else None
                )
                self.assert_reason(
                    "OPERATIONS_PROJECTION_TIME_INVALID",
                    lambda now=now, challenger=challenger: self.build(
                        now=now, challenger=challenger
                    ),
                )

    def test_freshness_boundaries_and_future_limit(self):
        def canonical(value):
            return (
                value.astimezone(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )

        now = datetime(2026, 8, 5, 0, 25, tzinfo=timezone.utc)
        at_20 = canonical(now - timedelta(minutes=20))
        after_20 = canonical(now - timedelta(minutes=20, milliseconds=1))
        at_future_5 = canonical(now + timedelta(minutes=5))
        after_future_5 = canonical(now + timedelta(minutes=5, milliseconds=1))

        fresh = self.build(
            challenger=challenger_source(
                provenance=provenance("CHALLENGER_OPERATIONS", at_20)
            )
        )
        stale = self.build(
            challenger=challenger_source(
                provenance=provenance("CHALLENGER_OPERATIONS", after_20)
            )
        )
        future = self.build(
            challenger=challenger_source(
                provenance=provenance("CHALLENGER_OPERATIONS", at_future_5)
            )
        )
        self.assertEqual(fresh["challenger"]["provenance"]["freshness"], "FRESH")
        self.assertEqual(stale["challenger"]["provenance"]["freshness"], "STALE")
        self.assertEqual(future["challenger"]["provenance"]["freshness"], "FRESH")
        self.assert_reason(
            "OPERATIONS_PROJECTION_FUTURE_SOURCE",
            lambda: self.build(
                challenger=challenger_source(
                    provenance=provenance(
                        "CHALLENGER_OPERATIONS", after_future_5
                    )
                )
            ),
        )

    def test_rejects_bool_and_negative_integer_counts(self):
        for value in (-1, True, "1"):
            with self.subTest(value=value):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_SOURCE_INVALID",
                    lambda value=value: self.build(
                        challenger=challenger_source(
                            verified_slot_count=value
                        )
                    ),
                )


class OperationsProjectionStateMachineTests(
    OperationsProjectionValidationTests
):
    def test_accepts_all_challenger_phases(self):
        cases = (
            challenger_source(),
            challenger_source(
                phase="REPLACEMENT_NOT_STARTED", incident_count=0
            ),
            challenger_source(
                phase="COLLECTING",
                service_health="HEALTHY",
                evidence_health="VERIFIED",
                verified_slot_count=1,
                active_episode_present=True,
                next_required_slot="2026-08-05T04:00:00.000Z",
                gate_status="WITHHELD_PRE_TAIL",
                incident_count=0,
            ),
            challenger_source(
                phase="FINAL",
                service_health="HEALTHY",
                evidence_health="VERIFIED",
                verified_slot_count=540,
                completed_episode_count=90,
                gate_status="RESEARCH_CONTINUATION_GATE_PASS",
                incident_count=0,
            ),
        )
        for source in cases:
            with self.subTest(phase=source.phase):
                self.assertEqual(
                    self.build(challenger=source)["challenger"]["phase"],
                    source.phase,
                )

    def test_rejects_challenger_gate_phase_contradictions(self):
        cases = (
            challenger_source(
                phase="COLLECTING", gate_status="NOT_AVAILABLE"
            ),
            challenger_source(
                phase="COLLECTING",
                gate_status="RESEARCH_CONTINUATION_GATE_PASS",
            ),
            challenger_source(
                phase="FINAL", gate_status="WITHHELD_PRE_TAIL"
            ),
        )
        for source in cases:
            with self.subTest(phase=source.phase, gate=source.gate_status):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_SOURCE_INVALID",
                    lambda source=source: self.build(challenger=source),
                )

    def test_accepts_all_system_paper_phases(self):
        cases = (
            paper_source(),
            paper_source(phase="INSTALLED_NOT_STARTED"),
            paper_source(
                phase="COLLECTING",
                service_health="HEALTHY",
                evidence_health="VERIFIED",
                elapsed_days=1,
                verified_slot_count=6,
                next_required_slot="2026-08-05T04:00:00.000Z",
                submitted_order_count=1,
                filled_order_count=1,
                reconciliation_status="RECONCILED",
                risk_state="NORMAL",
            ),
            paper_source(
                phase="FINAL",
                service_health="HEALTHY",
                evidence_health="VERIFIED",
                elapsed_days=90,
                verified_slot_count=540,
                submitted_order_count=30,
                filled_order_count=30,
                reconciliation_status="RECONCILED",
                risk_state="NORMAL",
                gate_status="SYSTEM_PAPER_GATE_PASS",
            ),
        )
        for source in cases:
            with self.subTest(phase=source.phase):
                self.assertEqual(
                    self.build(paper=source)["system_paper"]["phase"],
                    source.phase,
                )

    def test_not_installed_requires_zero_and_unavailable_state(self):
        cases = (
            paper_source(verified_slot_count=1),
            paper_source(submitted_order_count=1),
            paper_source(next_required_slot="2026-08-05T04:00:00.000Z"),
            paper_source(reconciliation_status="RECONCILED"),
            paper_source(risk_state="NORMAL"),
            paper_source(gate_status="SYSTEM_PAPER_GATE_PASS"),
        )
        for source in cases:
            with self.subTest(source=source):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_SOURCE_INVALID",
                    lambda source=source: self.build(paper=source),
                )

    def test_rejects_system_paper_gate_phase_contradictions(self):
        cases = (
            paper_source(
                phase="COLLECTING", gate_status="SYSTEM_PAPER_GATE_PASS"
            ),
            paper_source(phase="FINAL", gate_status="NOT_EVALUATED"),
        )
        for source in cases:
            with self.subTest(phase=source.phase, gate=source.gate_status):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_SOURCE_INVALID",
                    lambda source=source: self.build(paper=source),
                )


class OperationsProjectionAssemblyTests(
    OperationsProjectionValidationTests
):
    def healthy_challenger(self, **overrides):
        values = {
            "phase": "REPLACEMENT_NOT_STARTED",
            "incident_count": 0,
        }
        values.update(overrides)
        return challenger_source(**values)

    def collecting_paper(self, **overrides):
        values = {
            "phase": "COLLECTING",
            "service_health": "HEALTHY",
            "evidence_health": "VERIFIED",
            "elapsed_days": 1,
            "verified_slot_count": 6,
            "next_required_slot": "2026-08-05T04:00:00.000Z",
            "reconciliation_status": "RECONCILED",
            "risk_state": "NORMAL",
        }
        values.update(overrides)
        return paper_source(**values)

    def test_assembles_only_exact_allowlisted_fields(self):
        projection = self.build(challenger=self.healthy_challenger())

        self.assertEqual(
            set(projection),
            {
                "$schema",
                "schema_version",
                "projected_at",
                "status",
                "release",
                "challenger",
                "system_paper",
                "projection_hash",
            },
        )
        self.assertEqual(
            set(projection["release"]),
            {
                "package_version",
                "main_commit",
                "release_tag",
                "tag_commit",
                "identity_status",
                "provenance",
            },
        )
        self.assertEqual(
            set(projection["challenger"]),
            {
                "phase",
                "service_health",
                "evidence_health",
                "verified_slot_count",
                "completed_episode_count",
                "active_episode_present",
                "next_required_slot",
                "gate_status",
                "incident_count",
                "provenance",
            },
        )
        self.assertEqual(
            set(projection["system_paper"]),
            {
                "phase",
                "service_health",
                "evidence_health",
                "elapsed_days",
                "verified_slot_count",
                "next_required_slot",
                "submitted_order_count",
                "filled_order_count",
                "partially_filled_order_count",
                "cancelled_order_count",
                "rejected_order_count",
                "timeout_unknown_order_count",
                "reconciliation_status",
                "risk_state",
                "gate_status",
                "incident_count",
                "provenance",
            },
        )

    def test_derives_failed_closed_status(self):
        cases = (
            {"challenger": self.healthy_challenger(service_health="FAILED_CLOSED")},
            {"challenger": self.healthy_challenger(evidence_health="FAILED_CLOSED")},
            {"paper": self.collecting_paper(service_health="FAILED_CLOSED")},
            {"paper": self.collecting_paper(evidence_health="FAILED_CLOSED")},
            {"paper": self.collecting_paper(reconciliation_status="FAILED_CLOSED")},
        )
        for values in cases:
            with self.subTest(values=values):
                self.assertEqual(self.build(**values)["status"], "FAILED_CLOSED")

    def test_derives_degraded_status(self):
        stale = provenance(
            "CHALLENGER_OPERATIONS", "2026-08-04T23:00:00.000Z"
        )
        cases = (
            {"challenger": self.healthy_challenger(service_health="DEGRADED")},
            {"challenger": self.healthy_challenger(evidence_health="STALE")},
            {"challenger": self.healthy_challenger(evidence_health="INCIDENT_DETECTED")},
            {"challenger": self.healthy_challenger(incident_count=1)},
            {"challenger": self.healthy_challenger(provenance=stale)},
            {"paper": self.collecting_paper(risk_state="HALT")},
            {"paper": self.collecting_paper(risk_state="HARD_BOUNDARY")},
        )
        for values in cases:
            with self.subTest(values=values):
                self.assertEqual(self.build(**values)["status"], "DEGRADED")

    def test_legitimate_not_started_state_is_healthy(self):
        projection = self.build(challenger=self.healthy_challenger())
        self.assertEqual(projection["status"], "HEALTHY")

    def test_projection_hash_is_deterministic_and_purpose_bound(self):
        first = self.build(challenger=self.healthy_challenger())
        second = self.build(challenger=self.healthy_challenger())
        without_hash = dict(first)
        del without_hash["projection_hash"]

        self.assertEqual(first, second)
        self.assertEqual(
            first["projection_hash"],
            business_hash(
                {
                    "purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V1",
                    **without_hash,
                }
            ),
        )


class OperationsProjectionTailBlindTests(
    OperationsProjectionAssemblyTests
):
    FORBIDDEN = (
        "pnl",
        "profit",
        "return",
        "win_rate",
        "drawdown",
        "equity",
        "price",
        "fee",
        "confidence",
        "ranking",
        "interval",
        "power",
    )

    def assert_tail_blind(self, projection):
        body = canonical_json(projection).lower()
        for term in self.FORBIDDEN:
            with self.subTest(term=term):
                self.assertNotIn(term, body)

    def test_pre_tail_and_final_states_are_structurally_tail_blind(self):
        collecting = self.healthy_challenger(
            phase="COLLECTING",
            service_health="HEALTHY",
            evidence_health="VERIFIED",
            verified_slot_count=12,
            active_episode_present=True,
            next_required_slot="2026-08-05T04:00:00.000Z",
            gate_status="WITHHELD_PRE_TAIL",
        )
        final = self.healthy_challenger(
            phase="FINAL",
            service_health="HEALTHY",
            evidence_health="VERIFIED",
            verified_slot_count=540,
            completed_episode_count=90,
            gate_status="RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
        )
        self.assert_tail_blind(self.build(challenger=collecting))
        self.assert_tail_blind(self.build(challenger=final))

    def test_hostile_subclass_cannot_cross_the_boundary(self):
        class HostileRelease(ReleaseOperationsSource):
            __slots__ = ("pnl",)

        clean = release_source()
        hostile = HostileRelease(
            clean.package_version,
            clean.main_commit,
            clean.release_tag,
            clean.tag_commit,
            clean.identity_status,
            clean.provenance,
        )
        object.__setattr__(hostile, "pnl", {"credential": "/private/key"})

        with self.assertRaises(OperationsProjectionError) as caught:
            self.build(release=hostile)
        self.assertEqual(
            caught.exception.reason_code,
            "OPERATIONS_PROJECTION_SOURCE_INVALID",
        )
        self.assertNotIn("/private/key", str(caught.exception))


class OperationsProjectionLoaderTests(OperationsProjectionAssemblyTests):
    def projection(self):
        return self.build(challenger=self.healthy_challenger())

    def test_schema_mirrors_are_exact_and_closed_at_every_object(self):
        root = Path(__file__).resolve().parents[1]
        config = root / "config" / "operations-projection-v1.schema.json"
        packaged = (
            root
            / "src"
            / "crypto_quant"
            / "schemas"
            / "operations-projection-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), packaged.read_bytes())
        schema = json.loads(config.read_bytes())

        def assert_closed(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertIs(value.get("additionalProperties"), False)
                for child in value.values():
                    assert_closed(child)
            elif isinstance(value, list):
                for child in value:
                    assert_closed(child)

        assert_closed(schema)

    def test_loads_exact_canonical_projection_bytes(self):
        projection = self.projection()
        body = canonical_json(projection).encode("utf-8")

        loaded = load_operations_projection_bytes(body)

        self.assertEqual(loaded, projection)
        self.assertIsNot(loaded, projection)

    def test_rejects_invalid_json_domain_and_noncanonical_bytes(self):
        projection = self.projection()
        invalid = (
            b"\xff",
            b"",
            b"[]",
            b'{"duplicate":1,"duplicate":1}',
            b'{"binary_float":1.0}',
            b'{"non_finite":NaN}',
            json.dumps(projection).encode("utf-8"),
            canonical_json(projection).encode("utf-8") + b"\n",
        )
        for body in invalid:
            with self.subTest(body=body[:40]):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_BYTES_INVALID",
                    lambda body=body: load_operations_projection_bytes(body),
                )

    def test_rejects_oversized_bytes_before_decode(self):
        body = b"{" + (b" " * (2 * 1024 * 1024))
        self.assert_reason(
            "OPERATIONS_PROJECTION_BYTES_INVALID",
            lambda: load_operations_projection_bytes(body),
        )

    def test_rejects_unknown_fields_at_every_boundary(self):
        top = self.projection()
        top["unexpected"] = "value"
        nested = self.projection()
        nested["challenger"]["unexpected"] = "value"
        provenance_value = self.projection()
        provenance_value["system_paper"]["provenance"]["unexpected"] = "value"

        for value in (top, nested, provenance_value):
            with self.subTest(keys=sorted(value)):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_SCHEMA_INVALID",
                    lambda value=value: load_operations_projection_bytes(
                        canonical_json(value).encode("utf-8")
                    ),
                )

    def test_rejects_schema_enum_and_count_violations(self):
        bad_status = self.projection()
        bad_status["status"] = "MAYBE"
        bad_count = self.projection()
        bad_count["system_paper"]["verified_slot_count"] = -1
        bad_hash_shape = self.projection()
        bad_hash_shape["release"]["main_commit"] = "A" * 40

        for value in (bad_status, bad_count, bad_hash_shape):
            self.assert_reason(
                "OPERATIONS_PROJECTION_SCHEMA_INVALID",
                lambda value=value: load_operations_projection_bytes(
                    canonical_json(value).encode("utf-8")
                ),
            )

    def test_rejects_content_or_hash_tampering(self):
        content = self.projection()
        content["projected_at"] = "2026-08-05T00:26:00.000Z"
        changed_hash = self.projection()
        changed_hash["projection_hash"] = "b" * 64

        for value in (content, changed_hash):
            self.assert_reason(
                "OPERATIONS_PROJECTION_HASH_MISMATCH",
                lambda value=value: load_operations_projection_bytes(
                    canonical_json(value).encode("utf-8")
                ),
            )


class OperationsProjectionAdversarialTests(
    OperationsProjectionValidationTests
):
    def test_rejects_counts_beyond_exact_json_integer_range(self):
        source = challenger_source(
            phase="COLLECTING",
            service_health="HEALTHY",
            evidence_health="VERIFIED",
            verified_slot_count=1 << 53,
            active_episode_present=True,
            next_required_slot="2026-08-05T04:00:00.000Z",
            gate_status="WITHHELD_PRE_TAIL",
            incident_count=0,
        )
        self.assert_reason(
            "OPERATIONS_PROJECTION_SOURCE_INVALID",
            lambda: self.build(challenger=source),
        )

    def test_unhashable_enum_inputs_fail_with_bounded_reason(self):
        invalid_sources = (
            challenger_source(phase=[]),
            challenger_source(service_health={}),
            paper_source(risk_state=[]),
            paper_source(reconciliation_status={}),
        )
        for source in invalid_sources:
            with self.subTest(type=type(source).__name__):
                keyword = (
                    {"challenger": source}
                    if isinstance(source, ChallengerOperationsSource)
                    else {"paper": source}
                )
                self.assert_reason(
                    "OPERATIONS_PROJECTION_SOURCE_INVALID",
                    lambda keyword=keyword: self.build(**keyword),
                )

    def test_builder_performs_no_operational_io(self):
        source = challenger_source(
            phase="REPLACEMENT_NOT_STARTED", incident_count=0
        )
        with ExitStack() as stack:
            stack.enter_context(
                patch("builtins.open", side_effect=AssertionError("file I/O"))
            )
            stack.enter_context(
                patch.object(
                    subprocess,
                    "run",
                    side_effect=AssertionError("subprocess"),
                )
            )
            stack.enter_context(
                patch.object(
                    socket, "socket", side_effect=AssertionError("network")
                )
            )
            stack.enter_context(
                patch.object(
                    sqlite3,
                    "connect",
                    side_effect=AssertionError("state write"),
                )
            )
            projection = self.build(challenger=source)
        self.assertEqual(projection["status"], "HEALTHY")

    def test_module_imports_no_operational_capability(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "src" / "crypto_quant" / "operations_projection.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            imported.isdisjoint(
                {
                    "sqlite3",
                    "socket",
                    "subprocess",
                    "urllib",
                    "requests",
                    "httpx",
                }
            )
        )

    def test_identical_inputs_repeat_exactly(self):
        source = challenger_source(
            phase="REPLACEMENT_NOT_STARTED", incident_count=0
        )
        projections = [self.build(challenger=source) for _ in range(100)]
        self.assertTrue(all(value == projections[0] for value in projections))

if __name__ == "__main__":
    unittest.main()
