import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from decimal import getcontext, setcontext
from pathlib import Path
from unittest.mock import patch

from crypto_quant.challenger_replacement_economic_evaluation import (
    ChallengerReplacementEconomicEvaluationError,
    EconomicEvaluationFacts,
    EconomicOpportunityFact,
    EconomicProgressFacts,
    _build_economic_boundary_series,
    _strict_result,
    _strict_tail_mark,
    _bootstrap_statistics,
    _draw_start,
    evaluate_challenger_replacement_economic_result,
    load_challenger_replacement_economic_evaluation_bytes,
    observe_challenger_replacement_economic_progress,
)
from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from crypto_quant.challenger_replacement_public_market_capture import (
    load_challenger_replacement_public_market_capture_bytes,
)
from crypto_quant.challenger_replacement_public_simulation import (
    build_challenger_replacement_public_genesis_snapshot,
    build_challenger_replacement_public_simulation_input,
)
from crypto_quant.challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan
from tests.test_challenger_replacement_public_market_capture import (
    COMMITTED_CAPTURE,
    V076_BUILD,
)


UTC = timezone.utc
START = datetime(2026, 9, 1, tzinfo=UTC)
TAIL = START + timedelta(days=90)
GOLDEN = Path(__file__).parent / "fixtures/challenger_replacement_v076/public-simulation-golden.json"
KNOWN = Path(__file__).parent / "fixtures/challenger_replacement_v076/economic-evaluation-known-answers.json"


def iso(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def start_receipt():
    return {
        "receipt_id": "challenger_replacement_v3_start_receipt_" + "1" * 64,
        "receipt_hash": "2" * 64,
        "status": "V3_FIRST_NATURAL_OBSERVED_BOUND_NOT_ACTIVATED",
        "shared_opportunity_id": "ETHUSDT@" + iso(START),
        "shared_event_hash": "3" * 64,
        "economic_start": {"scheduled_for": iso(START)},
    }


def header(seconds, outcome="OBSERVED"):
    scheduled = START + timedelta(seconds=seconds)
    return {
        "opportunity_id": "ETHUSDT@" + iso(scheduled),
        "scheduled_for": iso(scheduled),
        "outcome": outcome,
        "evidence_health": "STRICT_REPLAY_VERIFIED",
    }


def synthetic_result(seconds, *, equity=None, peak=None, position="FLAT", fee="0",
                     funding="0", notional="0", gap=False):
    scheduled = START + timedelta(seconds=seconds)
    if equity is None:
        equity = 100 + seconds // 86400 + 1
    return {
        "opportunity": {
            "opportunity_id": "ETHUSDT@" + iso(scheduled),
            "scheduled_for": iso(scheduled),
        },
        "evidence_qualification": (
            "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER"
        ),
        "next_snapshot": {
            "marked_equity": str(equity),
            "peak_equity": str(max(100, equity) if peak is None else peak),
            "position_state": position,
            "economic_gap_locked": gap,
        },
        "accounting": {
            "fee": fee, "funding_cashflow": funding, "notional": notional,
        },
        "lifecycle": {"unresolved_unknown": False},
        "reconciliation": {"status": "MATCHED"},
    }


def opportunity(seconds, *, outcome="OBSERVED", result=None,
                missed_position=None, missed_reason=None):
    scheduled = START + timedelta(seconds=seconds)
    return EconomicOpportunityFact(
        opportunity_id="ETHUSDT@" + iso(scheduled),
        scheduled_for=iso(scheduled), outcome=outcome,
        result_or_null=(result if result is not None else (
            synthetic_result(seconds) if outcome == "OBSERVED" else None
        )),
        missed_position_state_or_null=missed_position,
        missed_reason_or_null=missed_reason,
    )


def population():
    return tuple(opportunity(seconds) for seconds in range(0, 7_776_000, 14_400))


class EconomicProgressTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_challenger_replacement_economic_plan()

    def test_pre_tail_projection_is_structurally_tail_blind(self):
        facts = EconomicProgressFacts(
            start_receipt=start_receipt(),
            terminal_headers=tuple(header(value) for value in range(0, 86_401, 14_400)),
            observed_at=iso(START + timedelta(days=1)),
        )
        progress = observe_challenger_replacement_economic_progress(
            facts, economic_plan=self.plan
        )
        self.assertEqual(progress["status"], "TAIL_BLIND")
        self.assertEqual(progress["due_opportunity_count"], 7)
        self.assertEqual(progress["terminal_opportunity_count"], 7)
        self.assertEqual(progress["observed_opportunity_count"], 7)
        self.assertEqual(progress["missed_opportunity_count"], 0)
        self.assertEqual(progress["elapsed_complete_days"], 1)
        forbidden = {
            "pnl", "profit", "return", "drawdown", "fee", "funding",
            "confidence", "bootstrap", "power", "rank", "pass",
        }
        keys = set()
        def visit(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    keys.add(key.lower())
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(progress)
        self.assertTrue(forbidden.isdisjoint(keys))

    def test_progress_rejects_gap_duplicate_and_economic_payload_header(self):
        good = [header(0), header(14_400)]
        for headers in (
            (good[1],),
            (good[0], good[0]),
            (dict(good[0], marked_equity="999"),),
        ):
            with self.subTest(headers=headers), self.assertRaises(
                ChallengerReplacementEconomicEvaluationError
            ):
                observe_challenger_replacement_economic_progress(
                    EconomicProgressFacts(
                        start_receipt=start_receipt(),
                        terminal_headers=tuple(headers),
                        observed_at=iso(START + timedelta(hours=4)),
                    ),
                    economic_plan=self.plan,
                )


class EconomicBoundarySeriesTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_challenger_replacement_economic_plan()

    def build(self, opportunities=None, *, observed_at=TAIL, tail=True):
        facts = EconomicEvaluationFacts(
            start_receipt=start_receipt(),
            opportunities=population() if opportunities is None else tuple(opportunities),
            observed_at=iso(observed_at),
            tail_mark_or_null=(
                {"source": {}, "previous_projection": {}, "marked_equity": "190"}
                if tail else None
            ),
        )
        with patch(
            "crypto_quant.challenger_replacement_economic_evaluation._strict_result",
            side_effect=lambda envelope, **_kwargs: envelope,
        ), patch(
            "crypto_quant.challenger_replacement_economic_evaluation._strict_tail_mark",
            return_value="190",
        ):
            return _build_economic_boundary_series(facts, economic_plan=self.plan)

    def test_tail_guard_runs_before_reading_result_or_tail_mark(self):
        class Explodes(dict):
            def __iter__(self):
                raise AssertionError("economic payload read before tail")
            def __getitem__(self, _key):
                raise AssertionError("economic payload read before tail")
        facts = EconomicEvaluationFacts(
            start_receipt=start_receipt(),
            opportunities=(replace(opportunity(0), result_or_null=Explodes()),),
            observed_at=iso(TAIL - timedelta(milliseconds=1)),
            tail_mark_or_null=Explodes(),
        )
        with self.assertRaisesRegex(
            ChallengerReplacementEconomicEvaluationError,
            "ECONOMIC_TAIL_NOT_REACHED",
        ):
            _build_economic_boundary_series(facts, economic_plan=self.plan)

    def test_post_tail_fact_is_rejected_instead_of_changing_result_identity(self):
        with self.assertRaisesRegex(
            ChallengerReplacementEconomicEvaluationError,
            "ECONOMIC_EVALUATION_FACTS_INVALID",
        ):
            self.build(population() + (opportunity(7_776_000),))

    def test_builds_91_boundaries_90_returns_six_blocks_and_drawdown(self):
        series = self.build()
        self.assertEqual(len(series["base"]["boundary_equities"]), 91)
        self.assertEqual(series["base"]["boundary_equities"][0], "100")
        self.assertEqual(series["base"]["boundary_equities"][-1], "190")
        self.assertEqual(series["base"]["daily_returns"], ["0.01"] * 90)
        self.assertEqual(series["base"]["fixed_15_day_blocks"], ["0.15"] * 6)
        self.assertEqual(series["base"]["maximum_drawdown_fraction"], "0")
        self.assertEqual(series["terminal_opportunity_count"], 540)
        self.assertEqual(series["observed_coverage"], "1")

    def test_flat_miss_charged_once_and_exposed_miss_not_imputed(self):
        values = list(population())
        index = 60
        values[index] = opportunity(
            index * 14_400, outcome="MISSED",
            missed_position="FLAT", missed_reason="MARKET_INPUT_UNAVAILABLE",
        )
        series = self.build(values)
        optimistic = series["optimistic_flat_miss"]["boundary_equities"]
        pessimistic = series["pessimistic_flat_miss"]["boundary_equities"]
        self.assertEqual(Decimal(optimistic[-1]) - Decimal(pessimistic[-1]), Decimal("1.25"))
        self.assertEqual(series["flat_miss_count"], 1)
        values[index] = replace(values[index], missed_position_state_or_null="SPOT_LONG")
        exposed = self.build(values)
        self.assertIn("EXPOSED_MISSED", exposed["confirmed_failure_boundaries"])
        self.assertIsNone(exposed["pessimistic_flat_miss"])

    def test_cycle_counts_and_stress_costs_use_each_record_once(self):
        values = list(population())
        values[0] = opportunity(0, result=synthetic_result(
            0, position="SPOT_LONG", fee="1", funding="-2", notional="10"
        ))
        values[1] = opportunity(14_400, result=synthetic_result(14_400, position="FLAT"))
        values[2] = opportunity(28_800, result=synthetic_result(28_800, position="PERP_SHORT"))
        values[3] = opportunity(43_200, result=synthetic_result(43_200, position="FLAT"))
        series = self.build(values)
        self.assertEqual(series["completed_cycle_count"], 2)
        self.assertEqual(series["spot_completed_cycle_count"], 1)
        self.assertEqual(series["perpetual_completed_cycle_count"], 1)
        self.assertEqual(series["stress_extra_cost_usdt"], "1.505")

    def test_continuous_drawdown_and_nonpositive_equity_include_intraday_states(self):
        values = list(population())
        values[0] = opportunity(0, result=synthetic_result(0, equity=50))
        values[1] = opportunity(14_400, result=synthetic_result(14_400, equity=101))
        series = self.build(values)
        self.assertEqual(series["base"]["maximum_drawdown_fraction"], "0.5")
        values[0] = opportunity(0, result=synthetic_result(0, equity=-1))
        failed = self.build(values)
        self.assertTrue(failed["nonpositive_equity"])

    def test_continuous_drawdown_uses_strict_snapshot_peak_equity(self):
        values = list(population())
        values[0] = opportunity(0, result=synthetic_result(0, equity=90, peak=120))
        series = self.build(values)
        self.assertEqual(series["base"]["maximum_drawdown_fraction"], "0.25")

    def test_real_golden_envelope_replays_through_public_strict_loader(self):
        plan = fixture_v3_plan()
        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        public = build_challenger_replacement_public_simulation_contract(
            plan=plan, economic_plan=self.plan, predecessor_contract=predecessor
        )
        capture = load_challenger_replacement_public_market_capture_bytes(
            COMMITTED_CAPTURE.read_bytes(), plan=plan,
            build_identity=V076_BUILD, previous_source_bundle=None,
        )
        source = build_challenger_replacement_public_simulation_input(
            capture, plan=plan, economic_plan=self.plan,
            predecessor_contract=predecessor, public_contract=public,
            build_identity=V076_BUILD,
        )
        previous = build_challenger_replacement_public_genesis_snapshot(
            plan=plan, public_contract=public
        )
        result = json.loads(GOLDEN.read_text(encoding="utf-8"))
        envelope = {
            "source": source, "previous_projection": previous,
            "result": result, "sequence": 1, "parent_event_hash": "0" * 64,
        }
        self.assertEqual(
            _strict_result(envelope, economic_plan=self.plan), result
        )
        tail = {
            "source": source,
            "previous_projection": previous,
            "marked_equity": "100",
        }
        self.assertEqual(
            _strict_tail_mark(
                tail, economic_plan=self.plan,
                expected_previous_hash=previous["snapshot_hash"],
                expected_scheduled_for=source["opportunity"]["scheduled_for"],
            ),
            "100",
        )
        changed = dict(tail, marked_equity="101")
        with self.assertRaises(ChallengerReplacementEconomicEvaluationError):
            _strict_tail_mark(
                changed, economic_plan=self.plan,
                expected_previous_hash=previous["snapshot_hash"],
                expected_scheduled_for=source["opportunity"]["scheduled_for"],
            )


DRAW_VECTORS = (
    (2026082574, 0, 0, 84, 32,
     "005ef479a250f41a49dd0717ea738f9979847e07b44ea39c9b322526388edbf8"),
    (2026082574, 0, 1, 84, 65,
     "8ca3b4c3bc8ed7cbb09736de1f197052158e81be999c70b230a8ca58cbbdef29"),
    (2026082574, 9999, 12, 84, 78,
     "3f4f7ea1df3036efdd288a800ef5b7eda452549f1c736e49d58519e632cc4636"),
    (2026082574, 0, 0, 1, 0,
     "98ac38b561532aaab998dfe0cb92ab74e9205fde4d37df1c78c90c4dcf82f5e8"),
)


def final_series(value="0.001"):
    daily = [value] * 90
    boundaries = ["100"]
    equity = Decimal("100")
    for item in daily:
        equity += Decimal(item) * Decimal("100")
        boundaries.append(str(equity))
    one = {
        "boundary_equities": boundaries,
        "daily_returns": daily,
        "fixed_15_day_blocks": [str(Decimal(value) * 15)] * 6,
        "maximum_drawdown_fraction": "0" if Decimal(value) >= 0 else "0.09",
    }
    return {
        "base": dict(one), "stress": dict(one),
        "optimistic_flat_miss": dict(one),
        "pessimistic_flat_miss": dict(one),
        "terminal_opportunity_count": 540,
        "observed_opportunity_count": 540,
        "missed_opportunity_count": 0, "observed_coverage": "1",
        "flat_miss_count": 0, "completed_cycle_count": 12,
        "spot_completed_cycle_count": 6,
        "perpetual_completed_cycle_count": 6,
        "stress_extra_cost_usdt": "0",
        "confirmed_failure_boundaries": [], "nonpositive_equity": False,
    }


class EconomicBootstrapAndResultTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_challenger_replacement_economic_plan()
        self.facts = EconomicEvaluationFacts(
            start_receipt=start_receipt(), opportunities=(),
            observed_at=iso(TAIL), tail_mark_or_null={},
        )

    def test_sha256_draw_vectors_and_rejection_sampling(self):
        import hashlib
        for seed, replicate, draw, count, expected, digest in DRAW_VECTORS:
            material = f"MBB_V1:{seed}:{replicate}:{draw}:{count}:0".encode("ascii")
            self.assertEqual(hashlib.sha256(material).hexdigest(), digest)
            self.assertEqual(_draw_start(
                seed=seed, replicate=replicate, draw=draw, start_count=count
            ), expected)

        class Digest:
            def __init__(self, value): self.value = value
            def digest(self): return self.value.to_bytes(32, "big")
        with patch(
            "crypto_quant.statistics.hashlib.sha256",
            side_effect=(Digest((1 << 256) - 1), Digest(5)),
        ) as mocked:
            self.assertEqual(_draw_start(
                seed=2026082574, replicate=0, draw=0, start_count=3
            ), 2)
        self.assertTrue(mocked.call_args_list[0].args[0].endswith(b":0"))
        self.assertTrue(mocked.call_args_list[1].args[0].endswith(b":1"))

    def test_constant_bootstrap_known_answers_keep_power_distinct(self):
        positive = _bootstrap_statistics(["0.001"] * 90, economic_plan=self.plan)
        self.assertEqual(positive, {
            "observed_mean": "0.001", "lcb95": "0.001",
            "centered_error_critical95": "0", "achieved_power_at_mere": "1",
        })
        negative = _bootstrap_statistics(["-0.001"] * 90, economic_plan=self.plan)
        self.assertEqual(negative["lcb95"], "-0.001")
        self.assertEqual(negative["achieved_power_at_mere"], "1")

    def test_bootstrap_ignores_process_decimal_context_and_rejects_binary_float(self):
        original = getcontext().copy()
        try:
            getcontext().prec = 7
            first = _bootstrap_statistics(["0.001"] * 90, economic_plan=self.plan)
            getcontext().prec = 31
            second = _bootstrap_statistics(["0.001"] * 90, economic_plan=self.plan)
        finally:
            setcontext(original)
        self.assertEqual(first, second)
        with self.assertRaises(ChallengerReplacementEconomicEvaluationError):
            _bootstrap_statistics([0.001] * 90, economic_plan=self.plan)

    def evaluate(self, series):
        with patch(
            "crypto_quant.challenger_replacement_economic_evaluation._build_economic_boundary_series",
            return_value=series,
        ):
            return evaluate_challenger_replacement_economic_result(
                self.facts, economic_plan=self.plan, build_identity=V076_BUILD
            )

    def test_pass_negative_and_bound_disagreement_map_to_exact_states(self):
        passed = self.evaluate(final_series())
        self.assertEqual(passed["status"], "RESEARCH_CONTINUATION_GATE_PASS")
        failed = self.evaluate(final_series("-0.001"))
        self.assertEqual(
            failed["status"], "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
        )
        disagreement = final_series()
        disagreement["pessimistic_flat_miss"] = final_series("-0.001")["base"]
        self.assertEqual(
            self.evaluate(disagreement)["status"],
            "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        )

    def test_sample_shortfall_and_confirmed_failure_precedence(self):
        short = final_series()
        short["observed_coverage"] = "0.949999"
        self.assertEqual(
            self.evaluate(short)["status"],
            "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        )
        confirmed = final_series()
        confirmed["confirmed_failure_boundaries"] = ["EXPOSED_MISSED"]
        self.assertEqual(
            self.evaluate(confirmed)["status"],
            "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
        )
        for field in (
            "completed_cycle_count", "spot_completed_cycle_count",
            "perpetual_completed_cycle_count",
        ):
            candidate = final_series()
            candidate[field] = 2
            with self.subTest(field=field):
                self.assertEqual(
                    self.evaluate(candidate)["status"],
                    "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                )
        blocks = final_series()
        blocks["base"]["fixed_15_day_blocks"] = ["0.015"] * 5
        self.assertEqual(
            self.evaluate(blocks)["status"],
            "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        )

    def test_achieved_power_shortfall_is_inconclusive(self):
        low_power = {
            "observed_mean": "0.001", "lcb95": "0.001",
            "centered_error_critical95": "0",
            "achieved_power_at_mere": "0.7999",
        }
        with patch(
            "crypto_quant.challenger_replacement_economic_evaluation._build_economic_boundary_series",
            return_value=final_series(),
        ), patch(
            "crypto_quant.challenger_replacement_economic_evaluation._bootstrap_statistics",
            return_value=low_power,
        ):
            result = evaluate_challenger_replacement_economic_result(
                self.facts, economic_plan=self.plan, build_identity=V076_BUILD
            )
        self.assertEqual(result["status"], "INCONCLUSIVE_INSUFFICIENT_EVIDENCE")

    def test_tail_evidence_shortfall_is_inconclusive_but_pre_tail_refuses(self):
        missing = EconomicEvaluationFacts(
            start_receipt=start_receipt(), opportunities=(),
            observed_at=iso(TAIL), tail_mark_or_null=None,
        )
        result = evaluate_challenger_replacement_economic_result(
            missing, economic_plan=self.plan, build_identity=V076_BUILD
        )
        self.assertEqual(result["status"], "INCONCLUSIVE_INSUFFICIENT_EVIDENCE")
        self.assertIn("ECONOMIC_TERMINAL_COVERAGE_INCOMPLETE", result["facts"]["reason_codes"])
        pre_tail = replace(missing, observed_at=iso(TAIL - timedelta(milliseconds=1)))
        with self.assertRaisesRegex(
            ChallengerReplacementEconomicEvaluationError,
            "ECONOMIC_TAIL_NOT_REACHED",
        ):
            evaluate_challenger_replacement_economic_result(
                pre_tail, economic_plan=self.plan, build_identity=V076_BUILD
            )

    def test_loader_rebuilds_all_fields_and_rejects_status_selection(self):
        series = final_series()
        result = self.evaluate(series)
        body = canonical_json(result).encode("utf-8")
        with patch(
            "crypto_quant.challenger_replacement_economic_evaluation._build_economic_boundary_series",
            return_value=series,
        ):
            self.assertEqual(
                load_challenger_replacement_economic_evaluation_bytes(
                    body, facts=self.facts, economic_plan=self.plan,
                    build_identity=V076_BUILD,
                ),
                result,
            )
            changed = dict(result, status="RESEARCH_CONTINUATION_GATE_DID_NOT_PASS")
            with self.assertRaises(ChallengerReplacementEconomicEvaluationError):
                load_challenger_replacement_economic_evaluation_bytes(
                    canonical_json(changed).encode("utf-8"), facts=self.facts,
                    economic_plan=self.plan, build_identity=V076_BUILD,
                )

    def test_committed_known_answers_match_exact_algorithms(self):
        known = json.loads(KNOWN.read_text(encoding="utf-8"))
        self.assertEqual(
            known["evidence_qualification"],
            "COMMITTED_DETERMINISTIC_TEST_VECTOR_NOT_RUNTIME_OR_ECONOMIC_EVIDENCE",
        )
        self.assertEqual(
            known["bootstrap"]["positive_constant"],
            _bootstrap_statistics(["0.001"] * 90, economic_plan=self.plan),
        )
        self.assertEqual(
            known["bootstrap"]["negative_constant"],
            _bootstrap_statistics(["-0.001"] * 90, economic_plan=self.plan),
        )
        self.assertEqual(
            tuple(
                (item["seed"], item["replicate"], item["draw"],
                 item["start_count"], item["result"], item["digest"])
                for item in known["draw_vectors"]
            ),
            DRAW_VECTORS,
        )

    def test_build_identity_mismatch_maps_to_domain_error(self):
        changed = dict(V076_BUILD, peeled_commit="g" * 40)
        with self.assertRaises(ChallengerReplacementEconomicEvaluationError):
            evaluate_challenger_replacement_economic_result(
                self.facts, economic_plan=self.plan, build_identity=changed
            )


if __name__ == "__main__":
    unittest.main()
