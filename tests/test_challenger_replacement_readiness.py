import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import inspect

from crypto_quant.challenger_replacement_opportunity_projection import (
    opportunity_id_for,
)
from crypto_quant.challenger_replacement_readiness import (
    ChallengerReplacementReadinessError,
    EconomicTailObservation,
    OpportunityReadinessFact,
    ReplacementReadinessFacts,
    _ReplacementReadinessBoundary,
    evaluate_challenger_replacement_operational_readiness,
    observe_challenger_replacement_economic_tail,
)
import crypto_quant.challenger_replacement_readiness as readiness_module


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
    terminal_observed = _START + timedelta(
        hours=4 * (total - 1), minutes=11
    )
    return _ReplacementReadinessBoundary(
        qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
        start_opportunity_id_or_null=opportunity_id_for(_utc(_START)),
        start_scheduled_for_or_null=_utc(_START),
        start_observed_at_or_null=_utc(_START + timedelta(minutes=5)),
        observed_at=_utc(terminal_observed),
    )


def _seven_day_boundary():
    return _ReplacementReadinessBoundary(
        qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
        start_opportunity_id_or_null=opportunity_id_for(_utc(_START)),
        start_scheduled_for_or_null=_utc(_START),
        start_observed_at_or_null=_utc(_START + timedelta(minutes=5)),
        observed_at=_utc(_START + timedelta(days=7, minutes=5)),
    )


def _elapsed_boundary(days):
    return _ReplacementReadinessBoundary(
        qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
        start_opportunity_id_or_null=opportunity_id_for(_utc(_START)),
        start_scheduled_for_or_null=_utc(_START),
        start_observed_at_or_null=_utc(_START + timedelta(minutes=5)),
        observed_at=_utc(_START + timedelta(days=days, minutes=5)),
    )


def _not_started_boundary():
    return _ReplacementReadinessBoundary(
        qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
        start_opportunity_id_or_null=None,
        start_scheduled_for_or_null=None,
        start_observed_at_or_null=None,
        observed_at=_utc(_START),
    )


def _facts_with_cycles(products):
    facts = _coverage_facts(observed=42, total=42)
    items = list(facts.opportunities)
    cursor = 0
    for product in products:
        position = "SPOT_LONG" if product == "spot" else "PERP_SHORT"
        items[cursor] = replace(
            items[cursor],
            position_before="FLAT",
            position_after=position,
            product_or_null=product,
            protective_stop_status="CONFIRMED_FIXTURE",
        )
        items[cursor + 1] = replace(
            items[cursor + 1],
            position_before=position,
            position_after="FLAT",
            product_or_null=product,
            protective_stop_status="NOT_REQUIRED_FLAT",
        )
        cursor += 2
    return replace(facts, opportunities=tuple(items))


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

    def test_unresolved_reasons_must_be_an_ordered_tuple(self):
        facts = _coverage_facts(observed=19, total=20)
        first = replace(
            facts.opportunities[0],
            unresolved_reason_codes=["LEDGER_POSITION_MISMATCH"],
        )
        self.assert_facts_invalid(
            replace(facts, opportunities=(first, *facts.opportunities[1:]))
        )

    def test_observed_product_value_is_strict(self):
        facts = _coverage_facts(observed=19, total=20)
        first = replace(facts.opportunities[0], product_or_null="SPOT")
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

    def test_start_must_bind_exact_first_verified_observed_opportunity(self):
        facts = _coverage_facts(observed=2, total=2)
        boundary = _boundary_for_due_count(2)
        cases = (
            replace(
                facts,
                opportunities=(
                    replace(
                        facts.opportunities[0],
                        outcome="MISSED",
                        observed_at_or_null=None,
                        missed_reason_or_null="CAPTURE_WINDOW_EXPIRED",
                        detected_at_or_null=_utc(_START + timedelta(minutes=11)),
                        result_evidence_sha256_or_null=None,
                        lifecycle_status_or_null=None,
                    ),
                    facts.opportunities[1],
                ),
                observed_opportunity_count=1,
                missed_opportunity_count=1,
            ),
            replace(
                facts,
                opportunities=(
                    replace(
                        facts.opportunities[0],
                        observed_at_or_null=_utc(_START + timedelta(minutes=6)),
                    ),
                    facts.opportunities[1],
                ),
            ),
        )
        for candidate in cases:
            with self.subTest(candidate=candidate.opportunities[0].outcome):
                self.assert_facts_invalid(candidate, boundary)

    def test_fact_terminal_times_must_stay_inside_observation_boundary(self):
        facts = _coverage_facts(observed=2, total=2)
        boundary = _boundary_for_due_count(2)
        for terminal in (
            _utc(_START - timedelta(milliseconds=1)),
            _utc(_START + timedelta(hours=4, minutes=10, milliseconds=1)),
        ):
            first = replace(
                facts.opportunities[0],
                terminal_recorded_at=terminal,
                observed_at_or_null=terminal,
            )
            with self.subTest(terminal=terminal):
                self.assert_facts_invalid(
                    replace(facts, opportunities=(first, facts.opportunities[1])),
                    boundary,
                )


class ChallengerReplacementOperationalPolicyTests(unittest.TestCase):
    def test_absent_start_is_not_started(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _coverage_facts(observed=0, total=0),
            _not_started_boundary(),
        )

        self.assertEqual(result.policy_status, "NOT_STARTED")
        self.assertEqual(result.due_opportunity_count, 0)

    def test_below_ninety_five_percent_extends_after_seven_days(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _coverage_facts(observed=39, total=42),
            _seven_day_boundary(),
        )

        self.assertFalse(result.meets_minimum_observed_coverage)
        self.assertEqual(result.policy_status, "PENDING_AUTOMATIC_EXTENSION")
        self.assertIn("MINIMUM_OBSERVED_COVERAGE_NOT_MET", result.reason_codes)

    def test_missing_due_terminal_extends_after_seven_days(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _coverage_facts(observed=41, total=41),
            _seven_day_boundary(),
        )

        self.assertFalse(result.terminal_coverage_complete)
        self.assertEqual(result.policy_status, "PENDING_AUTOMATIC_EXTENSION")
        self.assertIn("TERMINAL_COVERAGE_INCOMPLETE", result.reason_codes)

    def test_hold_inside_position_does_not_create_an_extra_cycle(self):
        facts = _coverage_facts(observed=42, total=42)
        items = list(facts.opportunities)
        items[0] = replace(
            items[0], position_after="SPOT_LONG", product_or_null="spot"
        )
        items[1] = replace(
            items[1],
            position_before="SPOT_LONG",
            position_after="SPOT_LONG",
            product_or_null="spot",
        )
        items[2] = replace(
            items[2], position_before="SPOT_LONG", product_or_null="spot"
        )

        result = evaluate_challenger_replacement_operational_readiness(
            replace(facts, opportunities=tuple(items)),
            _seven_day_boundary(),
        )

        self.assertEqual(result.strategy_cycle_count, 1)
        self.assertEqual(result.spot_roundtrip_count, 1)

    def test_direct_cross_product_reversal_is_confirmed_failure(self):
        facts = _coverage_facts(observed=42, total=42)
        items = list(facts.opportunities)
        items[0] = replace(
            items[0], position_after="SPOT_LONG", product_or_null="spot"
        )
        items[1] = replace(
            items[1],
            position_before="SPOT_LONG",
            position_after="PERP_SHORT",
            product_or_null="perpetual",
        )

        result = evaluate_challenger_replacement_operational_readiness(
            replace(facts, opportunities=tuple(items)),
            _seven_day_boundary(),
        )

        self.assertEqual(
            result.policy_status, "OPERATIONAL_QUALIFICATION_DID_NOT_PASS"
        )
        self.assertIn(
            "CROSS_PRODUCT_REVERSAL_WITHOUT_FLAT", result.reason_codes
        )

    def test_duplicate_entry_transition_is_confirmed_failure(self):
        facts = _coverage_facts(observed=42, total=42)
        items = list(facts.opportunities)
        items[0] = replace(
            items[0], position_after="SPOT_LONG", product_or_null="spot"
        )
        items[1] = replace(
            items[1], position_after="SPOT_LONG", product_or_null="spot"
        )

        result = evaluate_challenger_replacement_operational_readiness(
            replace(facts, opportunities=tuple(items)),
            _seven_day_boundary(),
        )

        self.assertEqual(
            result.policy_status, "OPERATIONAL_QUALIFICATION_DID_NOT_PASS"
        )
        self.assertIn(
            "DUPLICATE_POSITION_ENTRY_TRANSITION", result.reason_codes
        )

    def test_failed_lifecycle_cannot_complete_cycle(self):
        facts = _facts_with_cycles(("spot", "perpetual", "spot"))
        items = list(facts.opportunities)
        items[1] = replace(items[1], lifecycle_status_or_null="FAILED_CLOSED")

        result = evaluate_challenger_replacement_operational_readiness(
            replace(facts, opportunities=tuple(items)),
            _seven_day_boundary(),
        )

        self.assertEqual(result.strategy_cycle_count, 2)
        self.assertEqual(
            result.policy_status, "OPERATIONAL_QUALIFICATION_DID_NOT_PASS"
        )
        self.assertIn("LIFECYCLE_NOT_RECONCILED", result.reason_codes)

    def test_confirmed_evidence_identity_failure_is_did_not_pass(self):
        facts = replace(
            _facts_with_cycles(("spot", "perpetual", "spot")),
            evidence_failure_kind_or_null=(
                "CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE"
            ),
        )

        result = evaluate_challenger_replacement_operational_readiness(
            facts, _seven_day_boundary()
        )

        self.assertEqual(
            result.policy_status, "OPERATIONAL_QUALIFICATION_DID_NOT_PASS"
        )
        self.assertIn(
            "CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE",
            result.reason_codes,
        )

    def test_three_cycles_with_both_products_pass_policy_only(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _facts_with_cycles(("spot", "perpetual", "spot")),
            _seven_day_boundary(),
        )

        self.assertEqual(result.strategy_cycle_count, 3)
        self.assertEqual(result.spot_roundtrip_count, 2)
        self.assertEqual(result.perpetual_roundtrip_count, 1)
        self.assertEqual(
            result.policy_status, "OPERATIONAL_QUALIFICATION_PASS"
        )
        self.assertEqual(
            result.authority_status, "FIXTURE_POLICY_RESULT_NOT_OPERATIONAL"
        )

    def test_two_cycles_remain_pending_after_seven_days(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _facts_with_cycles(("spot", "perpetual")),
            _seven_day_boundary(),
        )

        self.assertEqual(
            result.policy_status, "PENDING_AUTOMATIC_EXTENSION"
        )
        self.assertIn("MINIMUM_STRATEGY_CYCLES_NOT_MET", result.reason_codes)

    def test_single_product_cycles_remain_pending(self):
        result = evaluate_challenger_replacement_operational_readiness(
            _facts_with_cycles(("spot", "spot", "spot")),
            _seven_day_boundary(),
        )

        self.assertEqual(
            result.policy_status, "PENDING_AUTOMATIC_EXTENSION"
        )
        self.assertIn("PERPETUAL_ROUNDTRIP_NOT_OBSERVED", result.reason_codes)

    def test_confirmed_safety_failure_is_did_not_pass(self):
        facts = replace(
            _facts_with_cycles(("spot", "perpetual", "spot")),
            incident_count=1,
        )
        result = evaluate_challenger_replacement_operational_readiness(
            facts, _seven_day_boundary()
        )

        self.assertEqual(
            result.policy_status, "OPERATIONAL_QUALIFICATION_DID_NOT_PASS"
        )
        self.assertIn("S0_OR_S1_INCIDENT", result.reason_codes)

    def test_top_level_confirmed_safety_states_can_never_pass(self):
        cases = (
            ({"unknown_order_count": 1}, "UNKNOWN_ORDER_PRESENT"),
            ({"open_order_count": 1}, "OPEN_ORDER_PRESENT_AT_BOUNDARY"),
            ({"reconciliation_status": "FAILED_CLOSED"}, "LEDGER_POSITION_MISMATCH"),
            (
                {
                    "current_position": "SPOT_LONG",
                    "protective_stop_status": "MISSING_OR_UNCONFIRMED",
                },
                "PROTECTIVE_STOP_MISSING_OR_UNCONFIRMED",
            ),
            ({"current_position": "SPOT_LONG"}, "NON_FLAT_TERMINAL_POSITION"),
            ({"risk_state": "HALT"}, "STAGE_FAILED_RISK_LOCK"),
            ({"daily_loss_boundary_state": "BREACHED"}, "SAFETY_BOUNDARY_BREACHED"),
            ({"drawdown_boundary_state": "BREACHED"}, "SAFETY_BOUNDARY_BREACHED"),
        )
        for overrides, reason in cases:
            with self.subTest(overrides=overrides):
                result = evaluate_challenger_replacement_operational_readiness(
                    replace(_facts_with_cycles(("spot", "perpetual", "spot")), **overrides),
                    _seven_day_boundary(),
                )
                self.assertEqual(
                    result.policy_status,
                    "OPERATIONAL_QUALIFICATION_DID_NOT_PASS",
                )
                self.assertIn(reason, result.reason_codes)

    def test_unavailable_evidence_is_inconclusive(self):
        facts = replace(
            _facts_with_cycles(("spot", "perpetual", "spot")),
            evidence_failure_kind_or_null=(
                "EVIDENCE_SOURCE_UNAVAILABLE_OR_QUALIFICATION_UNKNOWN"
            ),
        )
        result = evaluate_challenger_replacement_operational_readiness(
            facts, _seven_day_boundary()
        )

        self.assertEqual(
            result.policy_status, "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
        )

    def test_confirmed_violation_wins_over_unavailable_evidence(self):
        facts = _facts_with_cycles(("spot", "perpetual", "spot"))
        first = replace(
            facts.opportunities[0],
            unresolved_reason_codes=("LEDGER_POSITION_MISMATCH",),
        )
        facts = replace(
            facts,
            opportunities=(first, *facts.opportunities[1:]),
            evidence_failure_kind_or_null=(
                "EVIDENCE_SOURCE_UNAVAILABLE_OR_QUALIFICATION_UNKNOWN"
            ),
        )
        result = evaluate_challenger_replacement_operational_readiness(
            facts, _seven_day_boundary()
        )

        self.assertEqual(
            result.policy_status, "OPERATIONAL_QUALIFICATION_DID_NOT_PASS"
        )
        self.assertIn("LEDGER_POSITION_MISMATCH", result.reason_codes)

    def test_exposed_missed_gap_is_permanent_failure(self):
        facts = _facts_with_cycles(("spot", "perpetual", "spot"))
        first = replace(
            facts.opportunities[0],
            economic_gap_locked=True,
            unresolved_reason_codes=("ECONOMIC_GAP_LOCKED",),
        )
        result = evaluate_challenger_replacement_operational_readiness(
            replace(facts, opportunities=(first, *facts.opportunities[1:])),
            _seven_day_boundary(),
        )

        self.assertEqual(
            result.policy_status, "OPERATIONAL_QUALIFICATION_DID_NOT_PASS"
        )
        self.assertIn("ECONOMIC_GAP_LOCKED", result.reason_codes)


class ChallengerReplacementEconomicTailTests(unittest.TestCase):
    def test_no_start_reports_not_started_without_economic_fields(self):
        value = observe_challenger_replacement_economic_tail(
            _coverage_facts(observed=0, total=0),
            _not_started_boundary(),
        )

        self.assertIsInstance(value, EconomicTailObservation)
        self.assertEqual(value.status, "NOT_STARTED")
        self.assertIsNone(value.next_boundary_or_null)

    def test_day_89_withholds_economics_and_exposes_next_boundary(self):
        value = observe_challenger_replacement_economic_tail(
            _coverage_facts(observed=534, total=534),
            _elapsed_boundary(89),
        )

        self.assertEqual(value.status, "WITHHELD_PRE_TAIL")
        self.assertEqual(value.elapsed_complete_days, 89)
        self.assertEqual(
            value.next_boundary_or_null,
            "2026-04-01T00:05:00.000Z",
        )

    def test_day_90_reports_unpreregistered_final_evaluator(self):
        value = observe_challenger_replacement_economic_tail(
            _coverage_facts(observed=540, total=540),
            _elapsed_boundary(90),
        )

        self.assertEqual(
            value.status,
            "TAIL_REACHED_FINAL_EVALUATOR_NOT_PREREGISTERED",
        )
        self.assertIsNone(value.next_boundary_or_null)

    def test_confirmed_safety_failure_precedes_tail_status(self):
        facts = replace(
            _coverage_facts(observed=534, total=534), incident_count=1
        )

        value = observe_challenger_replacement_economic_tail(
            facts, _elapsed_boundary(89)
        )

        self.assertEqual(value.status, "FAILED_CLOSED")
        self.assertTrue(value.unresolved_safety_failure)

    def test_unsanitized_object_is_rejected_without_economic_access(self):
        class Unsanitized:
            accesses = 0

            def __getattr__(self, name):
                if name in {"pnl", "fee", "funding", "return", "drawdown"}:
                    self.accesses += 1
                    raise AssertionError("economic semantic access")
                raise AttributeError(name)

        value = Unsanitized()
        with self.assertRaises(ChallengerReplacementReadinessError):
            observe_challenger_replacement_economic_tail(
                value, _elapsed_boundary(89)
            )
        self.assertEqual(value.accesses, 0)

    def test_tail_result_and_public_api_have_no_economic_result_surface(self):
        value = observe_challenger_replacement_economic_tail(
            _coverage_facts(observed=534, total=534),
            _elapsed_boundary(89),
        )
        forbidden = ("pnl", "fee", "funding", "return", "drawdown", "win_rate")
        fields_and_repr = " ".join(
            (*EconomicTailObservation.__slots__, repr(value))
        ).lower()
        self.assertFalse(any(token in fields_and_repr for token in forbidden))

        for name, member in inspect.getmembers(readiness_module):
            if (
                name.startswith("_")
                or not callable(member)
                or getattr(member, "__module__", None)
                != readiness_module.__name__
            ):
                continue
            lowered = name.lower()
            self.assertNotRegex(lowered, r"economic.*result|profit.*gate|publish.*economic")
            parameters = inspect.signature(member).parameters
            self.assertTrue(set(parameters).isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
