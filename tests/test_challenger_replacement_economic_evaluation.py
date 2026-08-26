import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
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
    observe_challenger_replacement_economic_progress,
)
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


def synthetic_result(seconds, *, equity=None, position="FLAT", fee="0",
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


if __name__ == "__main__":
    unittest.main()
