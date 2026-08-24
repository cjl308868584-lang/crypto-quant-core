import json
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.challenger_replacement_readiness import (
    EconomicTailObservation,
    OperationalReadinessResult,
    ReplacementReadinessFacts,
)
from crypto_quant.challenger_replacement_readiness_observer import (
    ReplacementReadinessObservation,
)
from crypto_quant.operations_projection import (
    ChallengerOperationsSource,
    ReleaseOperationsSource,
    SourceProvenance,
    SystemPaperOperationsSource,
)
from crypto_quant.operations_projection_v2 import (
    OperationsProjectionV2Error,
    OperationsProjectionV2Sources,
    _OperationsProjectionV2Boundary,
    build_operations_projection_v2,
    load_operations_projection_v2_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-25T00:25:00.000Z"
COMMIT = "44d294a8fbc55a0fb4f9fe0537bb868824815d80"


def provenance(kind):
    return SourceProvenance(
        source_kind=kind,
        source_sha256="a" * 64,
        observed_at="2026-08-25T00:10:00.000Z",
    )


def replacement_observation(**fact_overrides):
    facts_values = dict(
        qualification="STRICT_V072_FIXTURE_SANITIZED",
        plan_id="challenger_replacement_plan_v3_" + "1" * 64,
        plan_hash="2" * 64,
        event_evidence_identity_hash="3" * 64,
        release_provenance_hash="4" * 64,
        event_chain_end_hash_or_null=None,
        opportunities=(),
        terminal_opportunity_count=0,
        observed_opportunity_count=0,
        missed_opportunity_count=0,
        current_consecutive_missed=0,
        maximum_consecutive_missed=0,
        last_missed_reason_or_null=None,
        active_opportunity_present=False,
        current_position="FLAT",
        gross_exposure="0",
        open_order_count=0,
        unknown_order_count=0,
        reconciliation_status="RECONCILED",
        protective_stop_status="NOT_REQUIRED_FLAT",
        risk_state="NORMAL",
        daily_loss_boundary_state="NORMAL",
        drawdown_boundary_state="NORMAL",
        incident_count=0,
        evidence_failure_kind_or_null=None,
    )
    facts_values.update(fact_overrides)
    facts = ReplacementReadinessFacts(**facts_values)
    operational = OperationalReadinessResult(
        evidence_qualification="STRICT_V072_FIXTURE_SANITIZED",
        policy_status="NOT_STARTED",
        authority_status="FIXTURE_POLICY_RESULT_NOT_OPERATIONAL",
        elapsed_complete_days=0,
        due_opportunity_count=0,
        terminal_opportunity_count=0,
        observed_opportunity_count=0,
        missed_opportunity_count=0,
        observed_coverage_numerator=0,
        observed_coverage_denominator=0,
        meets_minimum_observed_coverage=False,
        terminal_coverage_complete=True,
        strategy_cycle_count=0,
        spot_roundtrip_count=0,
        perpetual_roundtrip_count=0,
        reason_codes=(),
    )
    economic = EconomicTailObservation(
        evidence_qualification="STRICT_V072_FIXTURE_SANITIZED",
        status="NOT_STARTED",
        elapsed_complete_days=0,
        minimum_calendar_days=90,
        due_opportunity_count=0,
        terminal_opportunity_count=0,
        observed_opportunity_count=0,
        missed_opportunity_count=0,
        meets_minimum_observed_coverage=False,
        terminal_coverage_complete=True,
        lifecycle_complete=True,
        unresolved_safety_failure=False,
        next_boundary_or_null=None,
    )
    return ReplacementReadinessObservation(
        authority_status="FIXTURE_NOT_OPERATIONAL",
        service_health="NOT_LOADED",
        evidence_health="VERIFIED",
        observed_at=NOW,
        event_evidence_identity_hash="3" * 64,
        release_provenance_hash="4" * 64,
        provenance_hash="5" * 64,
        facts=facts,
        operational=operational,
        economic=economic,
    )


def sources(replacement=None):
    return OperationsProjectionV2Sources(
        release=ReleaseOperationsSource(
            package_version="0.72.0",
            main_commit=COMMIT,
            release_tag="v0.72.0",
            tag_commit=COMMIT,
            identity_status="VERIFIED",
            provenance=provenance("RELEASE_IDENTITY"),
        ),
        legacy_challenger=ChallengerOperationsSource(
            phase="LEGACY_FAILED_REPLACEMENT_NOT_STARTED",
            service_health="NOT_LOADED",
            evidence_health="NOT_AVAILABLE",
            verified_slot_count=0,
            completed_episode_count=0,
            active_episode_present=False,
            next_required_slot=None,
            gate_status="NOT_AVAILABLE",
            incident_count=1,
            provenance=provenance("CHALLENGER_OPERATIONS"),
        ),
        replacement_v3=replacement or replacement_observation(),
        system_paper=SystemPaperOperationsSource(
            phase="NOT_INSTALLED",
            service_health="NOT_LOADED",
            evidence_health="NOT_AVAILABLE",
            elapsed_days=0,
            verified_slot_count=0,
            next_required_slot=None,
            submitted_order_count=0,
            filled_order_count=0,
            partially_filled_order_count=0,
            cancelled_order_count=0,
            rejected_order_count=0,
            timeout_unknown_order_count=0,
            reconciliation_status="NOT_AVAILABLE",
            risk_state="NOT_AVAILABLE",
            gate_status="NOT_EVALUATED",
            incident_count=0,
            provenance=provenance("SYSTEM_PAPER_OPERATIONS"),
        ),
    )


def boundary():
    return _OperationsProjectionV2Boundary(
        qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
        observed_at=NOW,
    )


def rehash(value):
    candidate = dict(value)
    candidate.pop("projection_hash", None)
    value["projection_hash"] = business_hash(
        {"purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V2", **candidate}
    )
    return canonical_json(value).encode("utf-8")


class OperationsProjectionV2ContractTests(unittest.TestCase):
    def assert_reason(self, reason, operation):
        with self.assertRaises(OperationsProjectionV2Error) as caught:
            operation()
        self.assertEqual(caught.exception.reason_code, reason)

    def test_schema_mirrors_are_exact_and_valid(self):
        config = ROOT / "config/operations-projection-v2.schema.json"
        package = ROOT / "src/crypto_quant/schemas/operations-projection-v2.schema.json"
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_text()))

    def test_builder_is_deterministic_canonical_and_strictly_replayable(self):
        first = build_operations_projection_v2(sources(), boundary=boundary())
        second = build_operations_projection_v2(sources(), boundary=boundary())

        self.assertIsInstance(first, bytes)
        self.assertEqual(first, second)
        self.assertEqual(first, canonical_json(json.loads(first)).encode("utf-8"))
        loaded = load_operations_projection_v2_bytes(first)
        self.assertEqual(
            set(loaded),
            {
                "$schema", "schema_version", "projected_at", "status",
                "release", "legacy_challenger", "replacement_v3",
                "system_paper", "projection_hash",
            },
        )
        self.assertEqual(loaded["schema_version"], "2.0.0")
        self.assertFalse(loaded["replacement_v3"]["new_risk_advisory"])
        self.assertNotIn("pnl", canonical_json(loaded).lower())

    def test_plain_mapping_sources_and_boundary_are_rejected(self):
        self.assert_reason(
            "OPERATIONS_PROJECTION_V2_SOURCES_INVALID",
            lambda: build_operations_projection_v2({}, boundary=boundary()),
        )
        self.assert_reason(
            "OPERATIONS_PROJECTION_V2_BOUNDARY_INVALID",
            lambda: build_operations_projection_v2(sources(), boundary={}),
        )

    def test_builder_rejects_internally_inconsistent_typed_observation(self):
        inconsistent = replacement_observation(terminal_opportunity_count=1)
        self.assert_reason(
            "OPERATIONS_PROJECTION_V2_SOURCES_INVALID",
            lambda: build_operations_projection_v2(
                sources(inconsistent), boundary=boundary()
            ),
        )

    def test_strict_byte_boundary_rejects_malformed_inputs(self):
        valid = build_operations_projection_v2(sources(), boundary=boundary())
        cases = (
            None,
            b"",
            b"x" * (1024 * 1024 + 1),
            b'{"a":1,"a":2}',
            b'{"a":1.5}',
            valid + b"\n",
        )
        for value in cases:
            with self.subTest(value_type=type(value).__name__):
                self.assert_reason(
                    "OPERATIONS_PROJECTION_V2_BYTES_INVALID",
                    lambda value=value: load_operations_projection_v2_bytes(value),
                )

    def test_semantic_count_and_safety_invariants_fail_closed(self):
        base = json.loads(build_operations_projection_v2(
            sources(), boundary=boundary()
        ))
        mutations = (
            ("terminal_gt_due", lambda d: d["replacement_v3"].update(
                due_opportunity_count=0, terminal_opportunity_count=1
            )),
            ("observed_missed_sum", lambda d: d["replacement_v3"].update(
                due_opportunity_count=2, terminal_opportunity_count=2,
                observed_opportunity_count=1, missed_opportunity_count=0,
                observed_coverage_numerator=1,
                observed_coverage_denominator=2,
                terminal_coverage_complete=True,
                meets_minimum_observed_coverage=False,
            )),
            ("wrong_coverage", lambda d: d["replacement_v3"].update(
                due_opportunity_count=20, terminal_opportunity_count=20,
                observed_opportunity_count=19, missed_opportunity_count=1,
                observed_coverage_numerator=19,
                observed_coverage_denominator=20,
                terminal_coverage_complete=True,
                meets_minimum_observed_coverage=False,
            )),
            ("nonflat_stop", lambda d: d["replacement_v3"].update(
                current_product="SPOT_LONG",
                protective_stop_status="NOT_REQUIRED_FLAT",
            )),
            ("unknown_risk", lambda d: d["replacement_v3"].update(
                unknown_order_count=1, new_risk_advisory=True
            )),
            ("economic_final", lambda d: d["replacement_v3"].update(
                economic_tail_status="RESEARCH_CONTINUATION_GATE_PASS"
            )),
            ("pass_without_cycles", lambda d: d["replacement_v3"].update(
                operational_gate_status="OPERATIONAL_QUALIFICATION_PASS"
            )),
            ("stale_marked_healthy", lambda d: d["replacement_v3"].update(
                service_health="HEALTHY",
                provenance={
                    **d["replacement_v3"]["provenance"],
                    "freshness": "STALE",
                },
            )),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                candidate = json.loads(canonical_json(base))
                mutate(candidate)
                self.assert_reason(
                    "OPERATIONS_PROJECTION_V2_SEMANTIC_INVALID",
                    lambda candidate=candidate: load_operations_projection_v2_bytes(
                        rehash(candidate)
                    ),
                )

    def test_bool_integer_extra_field_and_hash_mismatch_are_rejected(self):
        base = json.loads(build_operations_projection_v2(
            sources(), boundary=boundary()
        ))
        boolean_count = json.loads(canonical_json(base))
        boolean_count["replacement_v3"]["incident_count"] = False
        self.assert_reason(
            "OPERATIONS_PROJECTION_V2_SEMANTIC_INVALID",
            lambda: load_operations_projection_v2_bytes(rehash(boolean_count)),
        )
        extra = json.loads(canonical_json(base))
        extra["replacement_v3"]["secret"] = "no"
        self.assert_reason(
            "OPERATIONS_PROJECTION_V2_SCHEMA_INVALID",
            lambda: load_operations_projection_v2_bytes(rehash(extra)),
        )
        mismatch = json.loads(canonical_json(base))
        mismatch["projection_hash"] = "0" * 64
        self.assert_reason(
            "OPERATIONS_PROJECTION_V2_HASH_MISMATCH",
            lambda: load_operations_projection_v2_bytes(
                canonical_json(mismatch).encode("utf-8")
            ),
        )

    def test_unsafe_integer_schema_version_and_unknown_enum_are_rejected(self):
        base = json.loads(build_operations_projection_v2(
            sources(), boundary=boundary()
        ))
        unsafe = json.loads(canonical_json(base))
        unsafe["replacement_v3"]["incident_count"] = 1 << 53
        self.assert_reason(
            "OPERATIONS_PROJECTION_V2_BYTES_INVALID",
            lambda: load_operations_projection_v2_bytes(
                json.dumps(
                    unsafe, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                ).encode("utf-8")
            ),
        )
        for field, value in (
            ("$schema", "./wrong.schema.json"),
            ("schema_version", "3.0.0"),
        ):
            with self.subTest(field=field):
                candidate = json.loads(canonical_json(base))
                candidate[field] = value
                self.assert_reason(
                    "OPERATIONS_PROJECTION_V2_SCHEMA_INVALID",
                    lambda candidate=candidate: load_operations_projection_v2_bytes(
                        rehash(candidate)
                    ),
                )
        unknown = json.loads(canonical_json(base))
        unknown["replacement_v3"]["service_health"] = "MAGIC"
        self.assert_reason(
            "OPERATIONS_PROJECTION_V2_SCHEMA_INVALID",
            lambda: load_operations_projection_v2_bytes(rehash(unknown)),
        )


if __name__ == "__main__":
    unittest.main()
