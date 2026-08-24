import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from crypto_quant.challenger_replacement_opportunity_projection import (
    opportunity_id_for,
)
from crypto_quant.challenger_replacement_readiness import (
    ChallengerReplacementReadinessError,
    OpportunityReadinessFact,
    ReplacementReadinessFacts,
    _ReplacementReadinessBoundary,
    evaluate_challenger_replacement_operational_readiness,
)


_HASH_A = "a" * 64
_HASH_B = "b" * 64
_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _utc(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _coverage_facts(*, observed, total):
    items = []
    for index in range(total):
        scheduled_for = _utc(_START + timedelta(hours=4 * index))
        is_observed = index < observed
        items.append(
            OpportunityReadinessFact(
                opportunity_id=opportunity_id_for(scheduled_for),
                scheduled_for=scheduled_for,
                outcome="OBSERVED" if is_observed else "MISSED",
                terminal_recorded_at=_utc(
                    _START + timedelta(hours=4 * index, minutes=5)
                ),
                observed_at_or_null=(
                    _utc(_START + timedelta(hours=4 * index, minutes=5))
                    if is_observed
                    else None
                ),
                missed_reason_or_null=(
                    None if is_observed else "CAPTURE_WINDOW_EXPIRED"
                ),
                detected_at_or_null=(
                    None
                    if is_observed
                    else _utc(_START + timedelta(hours=4 * index, minutes=11))
                ),
                result_evidence_sha256_or_null=(
                    _HASH_A if is_observed else None
                ),
                position_before="FLAT",
                position_after="FLAT",
                product_or_null=None,
                lifecycle_status_or_null=(
                    "RECONCILED_FIXTURE" if is_observed else None
                ),
                risk_state="NORMAL",
                protective_stop_status="NOT_REQUIRED_FLAT",
                economic_gap_locked=False,
                unresolved_reason_codes=(),
            )
        )
    return ReplacementReadinessFacts(
        qualification="STRICT_V072_FIXTURE_SANITIZED",
        plan_id="challenger_replacement_plan_v3_" + "1" * 64,
        plan_hash="2" * 64,
        event_evidence_identity_hash=_HASH_A,
        release_provenance_hash=_HASH_B,
        event_chain_end_hash_or_null="c" * 64,
        opportunities=tuple(items),
        terminal_opportunity_count=total,
        observed_opportunity_count=observed,
        missed_opportunity_count=total - observed,
        current_consecutive_missed=total - observed,
        maximum_consecutive_missed=total - observed,
        last_missed_reason_or_null=(
            None if observed == total else "CAPTURE_WINDOW_EXPIRED"
        ),
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


def _boundary_for_due_count(total):
    last_capture_close = _START + timedelta(
        hours=4 * (total - 1), minutes=10
    )
    return _ReplacementReadinessBoundary(
        qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
        start_opportunity_id_or_null=opportunity_id_for(_utc(_START)),
        start_scheduled_for_or_null=_utc(_START),
        start_observed_at_or_null=_utc(_START + timedelta(minutes=5)),
        observed_at=_utc(last_capture_close),
    )


class ChallengerReplacementReadinessCoverageTests(unittest.TestCase):
    def test_exact_nineteen_of_twenty_meets_frozen_coverage(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _coverage_facts(observed=19, total=20),
            _boundary_for_due_count(20),
        )

        self.assertEqual(result.observed_coverage_numerator, 19)
        self.assertEqual(result.observed_coverage_denominator, 20)
        self.assertTrue(result.meets_minimum_observed_coverage)
        self.assertTrue(result.terminal_coverage_complete)

    def test_before_day_seven_is_collecting_not_pass(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _coverage_facts(observed=19, total=20),
            _boundary_for_due_count(20),
        )

        self.assertEqual(
            result.policy_status, "COLLECTING_BEFORE_MINIMUM_DURATION"
        )

    def test_fixture_policy_result_never_claims_operational_authority(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _coverage_facts(observed=19, total=20),
            _boundary_for_due_count(20),
        )

        self.assertEqual(
            result.authority_status, "FIXTURE_POLICY_RESULT_NOT_OPERATIONAL"
        )

    def test_boolean_count_is_rejected(self):
        facts = _coverage_facts(observed=19, total=20)
        object.__setattr__(facts, "terminal_opportunity_count", True)

        with self.assertRaisesRegex(
            ChallengerReplacementReadinessError,
            "CHALLENGER_REPLACEMENT_READINESS_FACTS_INVALID",
        ):
            evaluate_challenger_replacement_operational_readiness(
                facts, _boundary_for_due_count(20)
            )


class ChallengerReplacementReadinessValidationTests(unittest.TestCase):
    def assert_facts_invalid(self, facts, boundary=None):
        with self.assertRaisesRegex(
            ChallengerReplacementReadinessError,
            "CHALLENGER_REPLACEMENT_READINESS_FACTS_INVALID",
        ):
            evaluate_challenger_replacement_operational_readiness(
                facts,
                boundary or _boundary_for_due_count(20),
            )

    def test_plain_mapping_is_not_a_typed_fact_set(self):
        self.assert_facts_invalid({})

    def test_wrong_fixture_qualification_is_rejected(self):
        facts = replace(
            _coverage_facts(observed=19, total=20),
            qualification="PRODUCTION",
        )
        self.assert_facts_invalid(facts)

    def test_noncanonical_timestamp_is_rejected(self):
        boundary = replace(
            _boundary_for_due_count(20),
            observed_at="2026-01-04T04:10:00Z",
        )
        self.assert_facts_invalid(
            _coverage_facts(observed=19, total=20), boundary
        )

    def test_negative_count_is_rejected(self):
        facts = replace(
            _coverage_facts(observed=19, total=20),
            incident_count=-1,
        )
        self.assert_facts_invalid(facts)

    def test_unsafe_integer_count_is_rejected(self):
        facts = replace(
            _coverage_facts(observed=19, total=20),
            incident_count=1 << 53,
        )
        self.assert_facts_invalid(facts)

    def test_malformed_identity_hash_is_rejected(self):
        facts = replace(
            _coverage_facts(observed=19, total=20),
            plan_hash="A" * 64,
        )
        self.assert_facts_invalid(facts)

    def test_every_identity_field_is_strict(self):
        invalid_fields = {
            "plan_id": "challenger_replacement_plan_v3_bad",
            "event_evidence_identity_hash": "0" * 63,
            "release_provenance_hash": "G" * 64,
            "event_chain_end_hash_or_null": "none",
        }
        for field, value in invalid_fields.items():
            with self.subTest(field=field):
                self.assert_facts_invalid(
                    replace(
                        _coverage_facts(observed=19, total=20),
                        **{field: value},
                    )
                )

    def test_count_inconsistency_is_rejected(self):
        facts = replace(
            _coverage_facts(observed=19, total=20),
            observed_opportunity_count=18,
        )
        self.assert_facts_invalid(facts)

    def test_out_of_order_opportunity_is_rejected(self):
        facts = _coverage_facts(observed=19, total=20)
        items = list(facts.opportunities)
        items[0], items[1] = items[1], items[0]
        self.assert_facts_invalid(replace(facts, opportunities=tuple(items)))

    def test_observed_fact_cannot_carry_missed_fields(self):
        facts = _coverage_facts(observed=19, total=20)
        first = replace(
            facts.opportunities[0],
            missed_reason_or_null="CAPTURE_WINDOW_EXPIRED",
        )
        self.assert_facts_invalid(
            replace(facts, opportunities=(first, *facts.opportunities[1:]))
        )

    def test_missed_fact_cannot_carry_result_evidence(self):
        facts = _coverage_facts(observed=19, total=20)
        last = replace(
            facts.opportunities[-1],
            result_evidence_sha256_or_null=_HASH_A,
        )
        self.assert_facts_invalid(
            replace(facts, opportunities=(*facts.opportunities[:-1], last))
        )

    def test_unknown_position_state_is_rejected(self):
        facts = replace(
            _coverage_facts(observed=19, total=20),
            current_position="UNKNOWN",
        )
        self.assert_facts_invalid(facts)

    def test_unknown_terminal_outcome_is_rejected(self):
        facts = _coverage_facts(observed=19, total=20)
        first = replace(facts.opportunities[0], outcome="SKIPPED")
        self.assert_facts_invalid(
            replace(facts, opportunities=(first, *facts.opportunities[1:]))
        )

    def test_unknown_fact_position_is_rejected(self):
        facts = _coverage_facts(observed=19, total=20)
        first = replace(facts.opportunities[0], position_after="UNKNOWN")
        self.assert_facts_invalid(
            replace(facts, opportunities=(first, *facts.opportunities[1:]))
        )

    def test_observed_result_hash_is_strict(self):
        facts = _coverage_facts(observed=19, total=20)
        first = replace(
            facts.opportunities[0],
            result_evidence_sha256_or_null="A" * 64,
        )
        self.assert_facts_invalid(
            replace(facts, opportunities=(first, *facts.opportunities[1:]))
        )

    def test_start_identity_must_match_start_schedule(self):
        boundary = replace(
            _boundary_for_due_count(20),
            start_opportunity_id_or_null="challenger_replacement_opportunity_"
            + "f" * 64,
        )
        self.assert_facts_invalid(
            _coverage_facts(observed=19, total=20), boundary
        )

    def test_start_observation_cannot_precede_start_schedule(self):
        boundary = replace(
            _boundary_for_due_count(20),
            start_observed_at_or_null="2025-12-31T23:59:59.000Z",
        )
        self.assert_facts_invalid(
            _coverage_facts(observed=19, total=20), boundary
        )

    def test_observation_cannot_precede_start_observation(self):
        boundary = replace(
            _boundary_for_due_count(20),
            observed_at="2026-01-01T00:00:00.000Z",
        )
        self.assert_facts_invalid(
            _coverage_facts(observed=19, total=20), boundary
        )


if __name__ == "__main__":
    unittest.main()
