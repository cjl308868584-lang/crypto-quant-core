import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from crypto_quant.challenger_replacement_fault_matrix import (
    run_challenger_replacement_fault_matrix,
)
from crypto_quant.challenger_replacement_operational_qualification import (
    ChallengerReplacementOperationalQualificationError,
    OperationalQualificationFacts,
    evaluate_challenger_replacement_operational_qualification,
    load_challenger_replacement_operational_qualification_bytes,
)
from crypto_quant import challenger_replacement_operational_qualification as qualification_module
from tests.test_challenger_replacement_fault_matrix import BUILD, CORE


UTC = timezone.utc
START = datetime(2026, 9, 1, tzinfo=UTC)


def iso(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def terminal(at_seconds, *, segment="segment-1", outcome="OBSERVED",
             qualification="PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER",
             clock="HEALTHY_ALIGNED", stop="SIMULATED_PROTECTIVE_STOP_ACTIVE"):
    at = START + timedelta(seconds=at_seconds)
    return {
        "opportunity_id": "ETHUSDT@" + iso(at),
        "scheduled_for": iso(at),
        "observed_at": iso(at),
        "segment_id": segment,
        "outcome": outcome,
        "evidence_qualification": qualification,
        "clock_status": clock,
        "simulated_stop_status": stop,
        "terminal_coverage_complete": True,
    }


def observed_series(end_seconds, *, start_seconds=0, segment="segment-1"):
    return tuple(
        terminal(value, segment=segment)
        for value in range(start_seconds, end_seconds + 1, 14_400)
    )


def facts(*opportunities, observed_seconds=None, hard=(), position="FLAT",
          reconciliation="MATCHED", started=True):
    receipt = {}
    if started:
        receipt = {
            "receipt_id": "challenger_replacement_v3_start_receipt_" + "1" * 64,
            "receipt_hash": "2" * 64,
            "status": "V3_FIRST_NATURAL_OBSERVED_BOUND_NOT_ACTIVATED",
            "deployment": {"candidate_build": deepcopy(BUILD),
                           "executable_core_hash": business_hash(CORE)},
            "operational_start": {"observed_at": iso(START)},
            "economic_start": {"scheduled_for": iso(START)},
        }
    if observed_seconds is None:
        observed_seconds = max(
            (int((datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00")) - START).total_seconds())
             for item in opportunities),
            default=0,
        )
    value = OperationalQualificationFacts(
        start_receipt=receipt,
        terminal_opportunities=tuple(opportunities),
        observed_at=iso(START + timedelta(seconds=observed_seconds)),
        position_state=position,
        reconciliation_status=reconciliation,
        hard_stop_reason_codes=tuple(hard),
    )
    return value


REAL_EVENT_FACTS = qualification_module._event_facts


class ChallengerReplacementOperationalQualificationTests(unittest.TestCase):
    def setUp(self):
        absent_runtime = patch(
            "crypto_quant.challenger_replacement_v3_observer._runtime_entry",
            return_value=None,
        )
        absent_runtime.start()
        self.addCleanup(absent_runtime.stop)
        self.plan = build_challenger_replacement_accelerated_canary_plan()
        self.fault = run_challenger_replacement_fault_matrix(
            build_identity=BUILD, runtime_core_identity=CORE,
        )
        gate = unittest.mock.patch.object(
            qualification_module, "_event_facts", side_effect=lambda value: value
        )
        gate.start()
        self.addCleanup(gate.stop)

    def evaluate(self, value):
        return evaluate_challenger_replacement_operational_qualification(
            value, accelerated_plan=self.plan, fault_receipt=self.fault
        )

    def test_caller_constructed_facts_cannot_qualify(self):
        raw = OperationalQualificationFacts(
            start_receipt=facts(terminal(0)).start_receipt,
            terminal_opportunities=observed_series(259200),
            observed_at=iso(START + timedelta(seconds=259200)),
            position_state="FLAT",
            reconciliation_status="MATCHED",
            hard_stop_reason_codes=(),
        )
        with unittest.mock.patch.object(
            qualification_module, "_event_facts", wraps=REAL_EVENT_FACTS
        ), self.assertRaisesRegex(
            ChallengerReplacementOperationalQualificationError,
            "CHALLENGER_REPLACEMENT_OPERATIONAL_FACT_SOURCE_INVALID",
        ):
            self.evaluate(raw)

    def test_importable_authority_token_cannot_qualify_caller_facts(self):
        raw = OperationalQualificationFacts(
            start_receipt=facts(terminal(0)).start_receipt,
            terminal_opportunities=observed_series(259200),
            observed_at=iso(START + timedelta(seconds=259200)),
            position_state="FLAT", reconciliation_status="MATCHED",
            hard_stop_reason_codes=(),
        )
        object.__setattr__(raw, "_authority", object())
        self.assertFalse(hasattr(qualification_module, "_STRICT_EVENT_FACTS"))
        with unittest.mock.patch.object(
            qualification_module, "_event_facts", wraps=REAL_EVENT_FACTS
        ), self.assertRaisesRegex(
            ChallengerReplacementOperationalQualificationError,
            "CHALLENGER_REPLACEMENT_OPERATIONAL_FACT_SOURCE_INVALID",
        ):
            self.evaluate(raw)

    def test_fault_receipt_must_match_start_receipt_candidate_build(self):
        value = facts(terminal(0))
        value.start_receipt["deployment"]["candidate_build"]["peeled_commit"] = "6" * 40
        with self.assertRaisesRegex(
            ChallengerReplacementOperationalQualificationError,
            "CHALLENGER_REPLACEMENT_FAULT_MATRIX_NOT_PASSED",
        ):
            self.evaluate(value)

    def test_fault_receipt_must_match_start_receipt_executable_core(self):
        value = facts(terminal(0))
        value.start_receipt["deployment"]["executable_core_hash"] = "d" * 64
        with self.assertRaisesRegex(
            ChallengerReplacementOperationalQualificationError,
            "CHALLENGER_REPLACEMENT_FAULT_MATRIX_NOT_PASSED",
        ):
            self.evaluate(value)

    def test_not_started_active_exact_boundary_and_loader(self):
        self.assertEqual(self.evaluate(facts(started=False))["status"], "NOT_STARTED")
        active = self.evaluate(facts(
            *observed_series(244800), observed_seconds=259199
        ))
        self.assertEqual(active["status"], "ACTIVE")
        self.assertEqual(active["eligible_continuous_seconds"], 259199)
        qualified_facts = facts(
            *observed_series(259200), observed_seconds=259200
        )
        qualified = self.evaluate(qualified_facts)
        self.assertEqual(qualified["status"], "QUALIFIED")
        self.assertEqual(qualified["eligible_continuous_seconds"], 259200)
        body = canonical_json(qualified).encode("utf-8")
        self.assertEqual(
            load_challenger_replacement_operational_qualification_bytes(
                body,
                facts=qualified_facts,
                accelerated_plan=self.plan,
                fault_receipt=self.fault,
            ),
            qualified,
        )
        changed = deepcopy(qualified)
        changed["status"] = "ACTIVE"
        with self.assertRaises(ChallengerReplacementOperationalQualificationError):
            load_challenger_replacement_operational_qualification_bytes(
                canonical_json(changed).encode("utf-8"),
                facts=qualified_facts,
                accelerated_plan=self.plan,
                fault_receipt=self.fault,
            )

    def test_real_two_minute_observed_delay_keeps_scheduled_cadence_and_72h_clock(self):
        delay = 120
        receipt = {
            "receipt_id": "challenger_replacement_v3_start_receipt_" + "1" * 64,
            "receipt_hash": "2" * 64,
            "status": "V3_FIRST_NATURAL_OBSERVED_BOUND_NOT_ACTIVATED",
            "deployment": {"candidate_build": deepcopy(BUILD),
                           "executable_core_hash": business_hash(CORE)},
            "operational_start": {"observed_at": iso(START + timedelta(seconds=delay))},
            "economic_start": {"scheduled_for": iso(START)},
        }
        opportunities = tuple(
            dict(
                terminal(seconds),
                observed_at=iso(START + timedelta(seconds=seconds + delay)),
            )
            for seconds in range(0, 259_200 + 1, 14_400)
        )
        value = OperationalQualificationFacts(
            start_receipt=receipt, terminal_opportunities=opportunities,
            observed_at=iso(START + timedelta(seconds=259_200 + delay)),
            position_state="FLAT", reconciliation_status="MATCHED",
            hard_stop_reason_codes=(),
        )
        result = self.evaluate(value)
        self.assertEqual(result["status"], "QUALIFIED")
        self.assertEqual(result["eligible_continuous_seconds"], 259_200)

    def test_disconnected_segments_never_sum_and_flat_miss_is_recoverable(self):
        result = self.evaluate(facts(
            *observed_series(187200, segment="old"),
            terminal(201600, segment="break", outcome="MISSED",
                     stop="NOT_REQUIRED_FLAT"),
            *observed_series(259200, start_seconds=216000, segment="new"),
            observed_seconds=259200,
        ))
        self.assertEqual(result["status"], "INTERRUPTED_RECOVERABLE")
        self.assertEqual(result["eligible_continuous_seconds"], 43200)
        self.assertIn("FLAT_MISSED_OPPORTUNITY", result["reason_codes"])

    def test_hard_stop_and_unsafe_boundaries_take_precedence(self):
        cases = (
            facts(*observed_series(259200), observed_seconds=259200,
                  hard=("UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",)),
            facts(*observed_series(259200), observed_seconds=259200,
                  position="EXPOSED", reconciliation="MISMATCHED"),
            facts(*observed_series(244800), terminal(259200, stop="MISSING"),
                  observed_seconds=259200, position="EXPOSED"),
            facts(*observed_series(244800), terminal(259200, clock="UNTRUSTED"),
                  observed_seconds=259200),
            facts(*observed_series(244800), terminal(259200, qualification="TEST_FIXTURE_ONLY"),
                  observed_seconds=259200),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(self.evaluate(value)["status"], "BLOCK_FAILED")

    def test_incomplete_coverage_or_failed_fault_receipt_cannot_qualify(self):
        incomplete = terminal(259200)
        incomplete["terminal_coverage_complete"] = False
        self.assertEqual(
            self.evaluate(facts(*observed_series(244800), incomplete, observed_seconds=259200))["status"],
            "INTERRUPTED_RECOVERABLE",
        )
        failed = deepcopy(self.fault)
        failed["cases"][0]["passed"] = False
        failed["status"] = "FAULT_MATRIX_FAILED"
        with self.assertRaises(ChallengerReplacementOperationalQualificationError):
            evaluate_challenger_replacement_operational_qualification(
                facts(*observed_series(259200), observed_seconds=259200),
                accelerated_plan=self.plan,
                fault_receipt=failed,
            )

    def test_inputs_are_strict_and_plan_policy_cannot_be_caller_overridden(self):
        with self.assertRaises(ChallengerReplacementOperationalQualificationError):
            self.evaluate(facts(terminal(0), observed_seconds=-1))
        changed_plan = deepcopy(self.plan)
        changed_plan["simulation_qualification"]["minimum_continuous_seconds"] = 1
        with self.assertRaises(ChallengerReplacementOperationalQualificationError):
            evaluate_challenger_replacement_operational_qualification(
                facts(terminal(0)), accelerated_plan=changed_plan,
                fault_receipt=self.fault,
            )

    def test_missing_due_four_hour_opportunity_cannot_qualify(self):
        missing = list(observed_series(259200))
        del missing[7]
        result = self.evaluate(facts(*missing, observed_seconds=259200))
        self.assertEqual(result["status"], "INTERRUPTED_RECOVERABLE")
        self.assertIn("TERMINAL_COVERAGE_INCOMPLETE", result["reason_codes"])

    def test_safe_segment_change_resets_continuity_without_summing(self):
        old = observed_series(129600, segment="old")
        new = observed_series(259200, start_seconds=144000, segment="new")
        result = self.evaluate(facts(*old, *new, observed_seconds=259200))
        self.assertEqual(result["status"], "INTERRUPTED_RECOVERABLE")
        self.assertEqual(result["eligible_continuous_seconds"], 115200)
        self.assertIn("SAFE_DISCONNECTION", result["reason_codes"])

    def test_result_identity_covers_complete_terminal_fact_history(self):
        original = facts(*observed_series(259200), observed_seconds=259200)
        changed_items = list(original.terminal_opportunities)
        changed_items[8] = dict(changed_items[8], opportunity_id="different")
        changed = OperationalQualificationFacts(
            start_receipt=original.start_receipt,
            terminal_opportunities=tuple(changed_items),
            observed_at=original.observed_at,
            position_state=original.position_state,
            reconciliation_status=original.reconciliation_status,
            hard_stop_reason_codes=original.hard_stop_reason_codes,
        )
        first = self.evaluate(original)
        second = self.evaluate(changed)
        self.assertNotEqual(first["bindings"]["facts_hash"], second["bindings"]["facts_hash"])
        self.assertNotEqual(first["result_id"], second["result_id"])


if __name__ == "__main__":
    unittest.main()
