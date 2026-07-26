import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from crypto_quant.contracts import EventEnvelope
from crypto_quant.economics import economic_snapshot_hash
from crypto_quant.errors import LedgerIntegrityError
from crypto_quant.estimators import EstimatorRegistry
from crypto_quant.evidence import EvidenceTrustContext
from crypto_quant.ledger import EventLedger
from crypto_quant.release import PolicyBundle, load_json_strict


ROOT = Path(__file__).resolve().parents[1]
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
START = "2026-01-01T00:00:00.000Z"
END = "2026-01-01T23:59:59.000Z"
ECONOMIC_SCOPE = {
    "evaluation_ledger": "AI_LEDGER",
    "release_route": "AI_ENHANCED",
    "direction": "LONG",
    "venue": "BINANCE_SPOT",
    "recipe_release_id": "recipe-1",
    "recipe_release_hash": HASH_A,
    "deployment_line_id": "line-1",
    "deployment_line_hash": HASH_B,
}

ECONOMIC_ESTIMATORS = {
    "FILL_BASED_GROSS_MINUS_FEES_PLUS_SIGNED_FUNDING_V1": "19",
    "CASH_FLOW_ADJUSTED_LIQUIDATION_EQUITY_MINUS_ALLOCATED_COSTS_V1": "14",
    "CASH_FLOW_ADJUSTED_DAILY_LOSS_V1": "0.019",
    "CASH_FLOW_ADJUSTED_MAX_DRAWDOWN_V1": (
        "0.01073170731707317073170731707"
    ),
    "WORST_CASE_GROSS_EXPOSURE_OVER_MARKED_EQUITY_V1": (
        "0.3488372093023255813953488372"
    ),
}


def event_envelope(payload, event_id, event_time):
    timestamp = datetime.fromisoformat(
        event_time.replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    return EventEnvelope.create(
        schema_version="1.1.0",
        event_id=event_id,
        trace_id="economic-trace-1",
        correlation_id="economic-correlation-1",
        causation_id=None,
        run_id="economic-run-1",
        event_time=timestamp,
        available_at=timestamp,
        ingested_at=timestamp,
        recorded_at=timestamp,
        source="REPLAY",
        payload=payload,
    )


def equity_payload(snapshot_id, as_of, marked, liquidation, *, exposure):
    return {
        "equity_snapshot_id": snapshot_id,
        "account_id": "account-1",
        **ECONOMIC_SCOPE,
        "marked_equity_usdt": Decimal(marked),
        "liquidation_equity_usdt": Decimal(liquidation),
        "spot_notional_usdt": Decimal(exposure[0]),
        "perp_notional_usdt": Decimal(exposure[1]),
        "active_order_risk_increasing_notional_usdt": Decimal(exposure[2]),
        "active_order_unknown_notional_usdt": Decimal(exposure[3]),
        "expected_exit_fee_accrued_usdt": Decimal("0"),
        "conservative_close_verified": True,
        "is_utc_day_start": as_of == START,
        "position_cost_bases": [],
        "as_of": as_of,
        "source_snapshot_hash": HASH_A,
    }


class EconomicEstimatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        cls.registry = EstimatorRegistry.load(ROOT / "config", catalog)
        golden = json.loads(
            (ROOT / "config" / "estimator-golden-vectors-v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.snapshot = golden["fixtures"]["economic-snapshot-valid"]

    def execute(self, estimator_id, snapshot=None):
        return self.registry.execute(
            estimator_id,
            {
                "economic_ledger_snapshot": (
                    self.snapshot if snapshot is None else snapshot
                )
            },
        )

    def test_all_economic_estimators_match_exact_decimal_results(self):
        for estimator_id, expected in ECONOMIC_ESTIMATORS.items():
            with self.subTest(estimator_id=estimator_id):
                result = self.execute(estimator_id)
                self.assertEqual(result.status, "COMPUTED")
                self.assertEqual(result.value, expected)

    def test_snapshot_hash_schema_and_semantics_fail_closed(self):
        tampered = deepcopy(self.snapshot)
        tampered["ending_liquidation_equity_usdt"] = "9999"
        result = self.execute(
            "CASH_FLOW_ADJUSTED_LIQUIDATION_EQUITY_MINUS_ALLOCATED_COSTS_V1",
            tampered,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertIn(
            "ECONOMIC_SNAPSHOT_SELF_HASH_MISMATCH",
            result.reason_codes,
        )

        binary_float = deepcopy(self.snapshot)
        binary_float["starting_liquidation_equity_usdt"] = 1000.0
        result = self.execute(
            "CASH_FLOW_ADJUSTED_LIQUIDATION_EQUITY_MINUS_ALLOCATED_COSTS_V1",
            binary_float,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(
            result.reason_codes,
            ("ECONOMIC_SNAPSHOT_SCHEMA_INVALID",),
        )

        wrong_cost_scope = deepcopy(self.snapshot)
        wrong_cost_scope["scope"]["release_route"] = "BASELINE_ONLY"
        wrong_cost_scope["snapshot_hash"] = economic_snapshot_hash(
            wrong_cost_scope
        )
        result = self.execute(
            "CASH_FLOW_ADJUSTED_LIQUIDATION_EQUITY_MINUS_ALLOCATED_COSTS_V1",
            wrong_cost_scope,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertIn(
            "ECONOMIC_SNAPSHOT_COST_SCOPE_MISMATCH",
            result.reason_codes,
        )

    def test_fill_prices_already_include_slippage_and_are_not_double_charged(self):
        changed_shortfall = deepcopy(self.snapshot)
        for fill in changed_shortfall["fills"]:
            fill["implementation_shortfall_usdt"] = "999"
        changed_shortfall["snapshot_hash"] = economic_snapshot_hash(
            changed_shortfall
        )
        result = self.execute(
            "FILL_BASED_GROSS_MINUS_FEES_PLUS_SIGNED_FUNDING_V1",
            changed_shortfall,
        )
        self.assertEqual(result.status, "COMPUTED")
        self.assertEqual(result.value, "19")

        crossing = deepcopy(self.snapshot)
        crossing["fills"][1]["quantity"] = "3"
        crossing["snapshot_hash"] = economic_snapshot_hash(crossing)
        result = self.execute(
            "FILL_BASED_GROSS_MINUS_FEES_PLUS_SIGNED_FUNDING_V1",
            crossing,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(
            result.reason_codes,
            ("ECONOMIC_FILL_CROSSES_ZERO",),
        )

    def test_economic_execution_is_deterministic_100_times(self):
        hashes = {
            self.execute(estimator_id).execution_hash
            for estimator_id in ECONOMIC_ESTIMATORS
            for _ in range(100)
        }
        self.assertEqual(len(hashes), len(ECONOMIC_ESTIMATORS))

    def test_release_evidence_cannot_reuse_another_scope_snapshot(self):
        scope = self.snapshot["scope"]
        evidence = {
            **scope,
            "policy_binding_hashes": {
                "accounting_policy_id": self.snapshot[
                    "accounting_policy_hash"
                ],
                "cost_allocation_policy_id": self.snapshot[
                    "cost_allocation_policy_hash"
                ],
            },
            "frozen_release_inputs": {
                "economic_ledger_snapshot": {
                    "artifact_id": self.snapshot["snapshot_id"],
                    "artifact_hash": self.snapshot["snapshot_hash"],
                }
            },
            "artifact_hashes": [
                self.snapshot["snapshot_hash"],
                self.snapshot["source_ledger_hash"],
                self.snapshot["source_projection_hash"],
            ],
        }
        trust = EvidenceTrustContext(
            policy_bundle_hash=HASH_A,
            binding_ids={},
            binding_hashes={},
            artifact_hashes={
                "economic_ledger_snapshot": self.snapshot["snapshot_hash"]
            },
            capital_values={},
            artifact_documents={
                "economic_ledger_snapshot": self.snapshot
            },
        )
        self.assertEqual(
            PolicyBundle._economic_snapshot_reference_reasons(
                evidence,
                trust,
            ),
            (),
        )

        wrong_scope = dict(evidence)
        wrong_scope["deployment_line_hash"] = HASH_A
        wrong_scope["artifact_hashes"] = [
            self.snapshot["snapshot_hash"],
        ]
        reasons = PolicyBundle._economic_snapshot_reference_reasons(
            wrong_scope,
            trust,
        )
        self.assertIn(
            "ECONOMIC_SNAPSHOT_SCOPE_MISMATCH:deployment_line_hash",
            reasons,
        )
        self.assertIn(
            "ECONOMIC_SNAPSHOT_SOURCE_HASH_MISSING:source_ledger_hash",
            reasons,
        )


class EconomicLedgerReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "economic-ledger.sqlite"
        catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        self.registry = EstimatorRegistry.load(ROOT / "config", catalog)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def append(ledger, event_type, event_id, event_time, payload):
        ledger.append(
            event_type,
            event_envelope(payload, event_id, event_time),
            payload,
        )

    def populate(self, ledger):
        self.append(
            ledger,
            "EquitySnapshotRecorded",
            "equity-event-1",
            START,
            equity_payload(
                "equity-1",
                START,
                "1000",
                "1000",
                exposure=("0", "0", "0", "0"),
            ),
        )
        cash = {
            "flow_id": "flow-1",
            "account_id": "account-1",
            "flow_type": "DEPOSIT",
            "signed_amount_usdt": Decimal("50"),
        }
        self.append(
            ledger,
            "ExternalCashFlowRecorded",
            "flow-event-1",
            "2026-01-01T09:00:00.000Z",
            cash,
        )
        for number, side, price, event_time in (
            (1, "BUY", "100", "2026-01-01T10:00:00.000Z"),
            (2, "SELL", "110", "2026-01-01T11:00:00.000Z"),
        ):
            fill = {
                "fill_id": f"fill-{number}",
                "account_id": "account-1",
                "market_scope": "BINANCE:SPOT",
                "exchange_trade_id": f"trade-{number}",
                "local_order_id": f"order-{number}",
                "venue_order_id": f"venue-order-{number}",
                "instrument_id": "BINANCE:SPOT:ETHUSDT",
                "side": side,
                "quantity": Decimal("2"),
                "price": Decimal(price),
                "contract_multiplier": Decimal("1"),
                "decision_reference_price": Decimal(price),
                "liquidity_role": "TAKER",
                "fee_amount": Decimal("1"),
                "fee_asset": "USDT",
                "fee_value_usdt": Decimal("1"),
                "fee_fx_rate_id_or_null": None,
                "implementation_shortfall_usdt": Decimal("0.5"),
                "exchange_event_time": event_time,
                "raw_payload_hash": HASH_A,
                **ECONOMIC_SCOPE,
            }
            self.append(
                ledger,
                "FillRecorded",
                f"fill-event-{number}",
                event_time,
                fill,
            )
        funding = {
            "funding_id": "funding-1",
            "account_id": "account-1",
            "instrument_id": "BINANCE:SPOT:ETHUSDT",
            "signed_amount_usdt": Decimal("1"),
            "position_quantity": Decimal("2"),
            "funding_rate": Decimal("0.005"),
            "mark_price": Decimal("100"),
            "settled_at": "2026-01-01T12:00:00.000Z",
            "raw_payload_hash": HASH_B,
            **ECONOMIC_SCOPE,
        }
        self.append(
            ledger,
            "FundingCashFlowRecorded",
            "funding-event-1",
            funding["settled_at"],
            funding,
        )
        self.append(
            ledger,
            "EquitySnapshotRecorded",
            "equity-event-2",
            "2026-01-01T12:00:00.000Z",
            equity_payload(
                "equity-2",
                "2026-01-01T12:00:00.000Z",
                "1075",
                "1075",
                exposure=("200", "100", "50", "25"),
            ),
        )
        for number, category, amount, allocation_scope, event_time in (
            (
                1,
                "INFRASTRUCTURE",
                "3",
                "SHARED",
                "2026-01-01T18:00:00.000Z",
            ),
            (
                2,
                "AI_INFERENCE",
                "2",
                "AI_ENHANCED",
                "2026-01-01T20:00:00.000Z",
            ),
        ):
            cost = {
                "cost_id": f"cost-{number}",
                "account_id": "account-1",
                "evaluation_ledger": "AI_LEDGER",
                "release_route": "AI_ENHANCED",
                "category": category,
                "amount_usdt": Decimal(amount),
                "allocation_scope": allocation_scope,
                "allocation_policy_hash": HASH_D,
                "occurred_at": event_time,
                **ECONOMIC_SCOPE,
            }
            self.append(
                ledger,
                "AllocatedCostRecorded",
                f"cost-event-{number}",
                event_time,
                cost,
            )
        self.append(
            ledger,
            "EquitySnapshotRecorded",
            "equity-event-3",
            END,
            equity_payload(
                "equity-3",
                END,
                "1069",
                "1069",
                exposure=("0", "0", "0", "0"),
            ),
        )

    @staticmethod
    def snapshot(ledger):
        return ledger.economic_ledger_snapshot(
            snapshot_id="economic-ledger-test-1",
            account_id="account-1",
            evaluation_ledger="AI_LEDGER",
            release_route="AI_ENHANCED",
            direction="LONG",
            venue="BINANCE_SPOT",
            recipe_release_id="recipe-1",
            recipe_release_hash=HASH_A,
            deployment_line_id="line-1",
            deployment_line_hash=HASH_B,
            evaluation_window_start=START,
            evaluation_window_end=END,
            accounting_policy_id="accounting-v1",
            accounting_policy_hash=HASH_C,
            cost_allocation_policy_id="cost-allocation-v1",
            cost_allocation_policy_hash=HASH_D,
            generated_at="2026-01-02T00:00:00.000Z",
        )

    def test_verified_snapshot_replays_to_identical_profit_and_risk(self):
        with EventLedger(self.path) as ledger:
            self.populate(ledger)
            unrelated_fill = json.loads(
                ledger.connection.execute(
                    """
                    SELECT payload_json FROM fills_projection
                    WHERE fill_id = 'fill-1'
                    """
                ).fetchone()[0]
            )
            unrelated_fill.update(
                {
                    "fill_id": "fill-other-line",
                    "exchange_trade_id": "trade-other-line",
                    "local_order_id": "order-other-line",
                    "venue_order_id": "venue-order-other-line",
                    "fee_value_usdt": "100",
                    "exchange_event_time": END,
                    "deployment_line_id": "line-2",
                    "deployment_line_hash": HASH_C,
                }
            )
            self.append(
                ledger,
                "FillRecorded",
                "fill-event-other-line",
                END,
                unrelated_fill,
            )
            unrelated_cost = json.loads(
                ledger.connection.execute(
                    """
                    SELECT payload_json FROM allocated_costs_projection
                    WHERE cost_id = 'cost-1'
                    """
                ).fetchone()[0]
            )
            unrelated_cost.update(
                {
                    "cost_id": "cost-other-line",
                    "amount_usdt": "100",
                    "occurred_at": END,
                    "deployment_line_id": "line-2",
                    "deployment_line_hash": HASH_C,
                }
            )
            self.append(
                ledger,
                "AllocatedCostRecorded",
                "cost-event-other-line",
                END,
                unrelated_cost,
            )
            before = self.snapshot(ledger)
            for estimator_id, expected in ECONOMIC_ESTIMATORS.items():
                result = self.registry.execute(
                    estimator_id,
                    {"economic_ledger_snapshot": before},
                )
                self.assertEqual(result.status, "COMPUTED")
                self.assertEqual(result.value, expected)

            ledger.rebuild_projections()
            after = self.snapshot(ledger)
            self.assertEqual(after, before)
            self.assertEqual(after["snapshot_hash"], before["snapshot_hash"])

            ledger.connection.execute(
                """
                UPDATE allocated_costs_projection
                SET projection_hash = ?
                WHERE cost_id = 'cost-1'
                """,
                (HASH_A,),
            )
            ledger.connection.commit()
            with self.assertRaises(LedgerIntegrityError):
                self.snapshot(ledger)
            ledger.rebuild_projections()
            self.assertEqual(self.snapshot(ledger), before)


if __name__ == "__main__":
    unittest.main()
