import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import (
    Decimal,
    ROUND_HALF_EVEN,
    getcontext,
    localcontext,
)
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_decimal
from crypto_quant.economics import economic_snapshot_hash
from crypto_quant.estimators import EstimatorRegistry
from crypto_quant.evidence import EvidenceTrustContext
from crypto_quant.release import MetricResolver, PolicyBundle, load_json_strict
from crypto_quant.release_artifacts import (
    supporting_observation_bundle_hash,
    supporting_observation_hash,
    validate_supporting_observation_bundle,
)
from crypto_quant.statistics import statistical_series_hash
from crypto_quant.trade_replay import (
    analyze_trade_replay_source,
    build_trade_replay_snapshot,
    leave_top_5_positive_trades_out_mbb_lcb95,
    trade_replay_snapshot_hash,
    trade_replay_snapshot_reasons,
)

from tests.factories import complete_trade_replay_inputs


ROOT = Path(__file__).resolve().parents[1]


def timestamp(hour):
    value = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        hours=hour
    )
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fill(
    fill_id,
    *,
    instrument,
    side,
    quantity,
    price,
    sequence,
    hour,
    multiplier="1",
):
    return {
        "fill_id": fill_id,
        "exchange_trade_id": f"exchange-{fill_id}",
        "local_order_id": f"order-{fill_id}",
        "venue_order_id": f"venue-{fill_id}",
        "source_event_sequence": sequence,
        "instrument_id": instrument,
        "side": side,
        "quantity": quantity,
        "price": price,
        "contract_multiplier": multiplier,
        "fee_value_usdt": "0",
        "implementation_shortfall_usdt": "0",
        "exchange_event_time": timestamp(hour),
    }


class CompleteTradeSourceReplayTests(unittest.TestCase):
    def inputs(self, pnl="10"):
        source, snapshots, valuations = complete_trade_replay_inputs(
            trade_pnls=(pnl,)
        )
        return deepcopy(source), deepcopy(snapshots), deepcopy(valuations)

    @staticmethod
    def rehash(
        source,
        snapshots,
        valuations,
        *,
        recompute_values=True,
    ):
        old_to_new = {}
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            for snapshot, observation in zip(
                snapshots,
                source["observations"],
            ):
                old_hash = observation["source_economic_snapshot_hash"]
                snapshot["snapshot_hash"] = economic_snapshot_hash(snapshot)
                new_hash = snapshot["snapshot_hash"]
                old_to_new[old_hash] = new_hash
                observation["source_economic_snapshot_hash"] = new_hash
                if recompute_values:
                    start = Decimal(
                        snapshot["starting_liquidation_equity_usdt"]
                    )
                    end = Decimal(
                        snapshot["ending_liquidation_equity_usdt"]
                    )
                    observation["value"] = canonical_decimal(
                        (end / start).ln()
                    )
        source["source_economic_snapshot_hashes"] = [
            snapshot["snapshot_hash"] for snapshot in snapshots
        ]
        for checkpoint in valuations:
            checkpoint["source_economic_snapshot_hash"] = old_to_new.get(
                checkpoint["source_economic_snapshot_hash"],
                checkpoint["source_economic_snapshot_hash"],
            )
        source["series_hash"] = statistical_series_hash(source)

    def analyze(self, source, snapshots, valuations):
        return analyze_trade_replay_source(
            source_series_snapshot=source,
            economic_snapshots=snapshots,
            valuation_checkpoints=valuations,
        )

    def test_split_fills_form_one_zero_to_zero_trade(self):
        source, snapshots, valuations = self.inputs("30")
        snapshot = snapshots[0]
        snapshot["fills"] = [
            fill(
                "split-open-1",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="BUY",
                quantity="1",
                price="100",
                sequence=2,
                hour=6,
            ),
            fill(
                "split-open-2",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="BUY",
                quantity="2",
                price="100",
                sequence=3,
                hour=7,
            ),
            fill(
                "split-close-1",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="SELL",
                quantity="1",
                price="110",
                sequence=4,
                hour=8,
            ),
            fill(
                "split-close-2",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="SELL",
                quantity="2",
                price="110",
                sequence=5,
                hour=9,
            ),
        ]
        snapshot["equity_points"][-1]["source_event_sequence"] = 6
        self.rehash(source, snapshots, valuations)

        analysis = self.analyze(source, snapshots, valuations)

        self.assertEqual(len(analysis.completed_trades), 1)
        trade = analysis.completed_trades[0]
        self.assertEqual(
            trade.fill_ids,
            (
                "split-open-1",
                "split-open-2",
                "split-close-1",
                "split-close-2",
            ),
        )
        self.assertEqual(trade.contribution_usdt, Decimal("30"))
        self.assertTrue(trade.eligible)

    def test_overlapping_instruments_form_independent_cycles(self):
        source, snapshots, valuations = self.inputs("30")
        snapshot = snapshots[0]
        snapshot["fills"] = [
            fill(
                "btc-open",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="BUY",
                quantity="1",
                price="100",
                sequence=2,
                hour=6,
            ),
            fill(
                "eth-open",
                instrument="BINANCE:SPOT:ETHUSDT",
                side="BUY",
                quantity="1",
                price="200",
                sequence=3,
                hour=7,
            ),
            fill(
                "btc-close",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="SELL",
                quantity="1",
                price="110",
                sequence=4,
                hour=8,
            ),
            fill(
                "eth-close",
                instrument="BINANCE:SPOT:ETHUSDT",
                side="SELL",
                quantity="1",
                price="220",
                sequence=5,
                hour=9,
            ),
        ]
        snapshot["equity_points"][-1]["source_event_sequence"] = 6
        self.rehash(source, snapshots, valuations)

        analysis = self.analyze(source, snapshots, valuations)

        self.assertEqual(
            [
                (trade.instrument_id, trade.contribution_usdt)
                for trade in analysis.completed_trades
            ],
            [
                ("BINANCE:SPOT:BTCUSDT", Decimal("10")),
                ("BINANCE:SPOT:ETHUSDT", Decimal("20")),
            ],
        )

    def test_opening_and_unclosed_positions_are_not_eligible(self):
        source, snapshots, valuations = self.inputs("10")
        snapshot = snapshots[0]
        opening = {
            "instrument_id": "BINANCE:SPOT:BTCUSDT",
            "signed_quantity": "1",
            "moving_average_entry_price": "100",
            "contract_multiplier": "1",
        }
        snapshot["opening_positions"] = [opening]
        snapshot["equity_points"][0]["position_cost_bases"] = [opening]
        snapshot["fills"] = [
            fill(
                "opening-close",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="SELL",
                quantity="1",
                price="110",
                sequence=2,
                hour=6,
            ),
            fill(
                "unclosed-open",
                instrument="BINANCE:SPOT:BTCUSDT",
                side="BUY",
                quantity="1",
                price="105",
                sequence=3,
                hour=12,
            ),
        ]
        ending = {
            "instrument_id": "BINANCE:SPOT:BTCUSDT",
            "signed_quantity": "1",
            "moving_average_entry_price": "105",
            "contract_multiplier": "1",
        }
        snapshot["equity_points"][-1]["position_cost_bases"] = [ending]
        valuations[0]["instruments"] = [
            {
                "instrument_id": "BINANCE:SPOT:BTCUSDT",
                "long_executable_exit_price_usdt": "100",
                "short_executable_exit_price_usdt": None,
                "contract_multiplier": "1",
                "expected_exit_fee_usdt": "0",
                "valuation_source_hash": "8" * 64,
            }
        ]
        valuations[-1]["instruments"] = [
            {
                "instrument_id": "BINANCE:SPOT:BTCUSDT",
                "long_executable_exit_price_usdt": "105",
                "short_executable_exit_price_usdt": None,
                "contract_multiplier": "1",
                "expected_exit_fee_usdt": "0",
                "valuation_source_hash": "9" * 64,
            }
        ]
        self.rehash(source, snapshots, valuations)

        analysis = self.analyze(source, snapshots, valuations)

        self.assertEqual(len(analysis.completed_trades), 1)
        self.assertFalse(analysis.completed_trades[0].eligible)
        self.assertEqual(
            analysis.completed_trades[0].fill_ids,
            ("opening-close",),
        )

    def test_fill_crossing_zero_fails_closed(self):
        source, snapshots, valuations = self.inputs()
        snapshots[0]["fills"][1]["quantity"] = "2"
        self.rehash(source, snapshots, valuations)

        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_FILL_CROSSES_ZERO",
        ):
            self.analyze(source, snapshots, valuations)

    def test_multiplier_change_fails_closed(self):
        source, snapshots, valuations = self.inputs()
        snapshots[0]["fills"][1]["contract_multiplier"] = "2"
        self.rehash(source, snapshots, valuations)

        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_MULTIPLIER_CHANGED",
        ):
            self.analyze(source, snapshots, valuations)

    def test_original_equity_must_replay_at_every_checkpoint(self):
        source, snapshots, valuations = self.inputs()
        snapshot = snapshots[0]
        snapshot["ending_liquidation_equity_usdt"] = "1010.01"
        snapshot["equity_points"][-1]["liquidation_equity_usdt"] = "1010.01"
        snapshot["equity_points"][-1]["marked_equity_usdt"] = "1010.01"
        self.rehash(
            source,
            snapshots,
            valuations,
        )

        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_ORIGINAL_EQUITY_MISMATCH",
        ):
            self.analyze(source, snapshots, valuations)

    def test_funding_position_must_match_replayed_position(self):
        source, snapshots, valuations = self.inputs("11")
        snapshot = snapshots[0]
        snapshot["funding_cashflows"] = [
            {
                "funding_id": "funding-invalid-position",
                "source_event_sequence": 3,
                "instrument_id": "BINANCE:SPOT:BTCUSDT",
                "signed_amount_usdt": "1",
                "position_quantity": "2",
                "funding_rate": "0.01",
                "mark_price": "100",
                "settled_at": timestamp(12),
            }
        ]
        snapshot["fills"][1]["source_event_sequence"] = 4
        snapshot["equity_points"][-1]["source_event_sequence"] = 5
        self.rehash(source, snapshots, valuations)

        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_FUNDING_POSITION_MISMATCH",
        ):
            self.analyze(source, snapshots, valuations)

    def test_trade_id_is_stable_and_uploader_cannot_supply_it(self):
        source, snapshots, valuations = self.inputs()

        first = self.analyze(source, snapshots, valuations)
        second = self.analyze(source, snapshots, valuations)

        expected = (
            "trd:"
            "ab29083599dcffce5ff2f7966f5d6a53"
            "d49d2970ba054a37ea0a81f69467a53c"
        )
        self.assertEqual(first.completed_trades[0].trade_id, expected)
        self.assertEqual(second.completed_trades[0].trade_id, expected)

        forged_source = deepcopy(source)
        forged_snapshots = deepcopy(snapshots)
        forged_valuations = deepcopy(valuations)
        forged_snapshots[0]["fills"][0]["trade_id"] = "uploader-choice"
        self.rehash(
            forged_source,
            forged_snapshots,
            forged_valuations,
        )
        with self.assertRaisesRegex(
            ValueError,
            "TRADE_REPLAY_UPLOADER_TRADE_ID_FORBIDDEN",
        ):
            self.analyze(
                forged_source,
                forged_snapshots,
                forged_valuations,
            )


class CompleteTradeCounterfactualTests(unittest.TestCase):
    @staticmethod
    def build(
        *,
        trade_pnls=("10", "9", "8", "7", "6", "5"),
        block_length=2,
        minimum_block_count=2,
    ):
        source, snapshots, valuations = complete_trade_replay_inputs(
            trade_pnls=trade_pnls,
            block_length=block_length,
            minimum_block_count=minimum_block_count,
        )
        return build_trade_replay_snapshot(
            replay_id="trade-replay-test",
            source_series_snapshot=source,
            economic_snapshots=snapshots,
            valuation_checkpoints=valuations,
            generated_at=source["generated_at"],
        )

    def test_selects_exactly_five_largest_positive_complete_trades(self):
        artifact = self.build()
        contributions = {
            item["trade_id"]: Decimal(item["economic_contribution_usdt"])
            for item in artifact["completed_trades"]
        }

        self.assertEqual(len(artifact["selected_trade_ids"]), 5)
        self.assertEqual(
            [contributions[item] for item in artifact["selected_trade_ids"]],
            [
                Decimal("10"),
                Decimal("9"),
                Decimal("8"),
                Decimal("7"),
                Decimal("6"),
            ],
        )
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            self.assertEqual(
                sum(
                    (
                        Decimal(item["value"])
                        for item in artifact["counterfactual_series"][
                            "observations"
                        ]
                    ),
                    Decimal("0"),
                ),
                (Decimal("1005") / Decimal("1000")).ln(),
            )

    def test_equal_contribution_uses_trade_id_ascending(self):
        artifact = self.build(trade_pnls=("10",) * 6)
        all_ids = sorted(
            item["trade_id"] for item in artifact["completed_trades"]
        )
        self.assertEqual(
            artifact["selected_trade_ids"],
            all_ids[:5],
        )

    def test_fewer_than_five_removes_all_positive_trades(self):
        artifact = self.build(trade_pnls=("3", "0", "-1", "2"))
        contributions = {
            item["trade_id"]: Decimal(item["economic_contribution_usdt"])
            for item in artifact["completed_trades"]
        }
        self.assertEqual(
            [contributions[item] for item in artifact["selected_trade_ids"]],
            [Decimal("3"), Decimal("2")],
        )

    def test_no_positive_trade_removes_none_but_still_replays(self):
        artifact = self.build(trade_pnls=("0", "-1", "0", "-2"))
        self.assertEqual(artifact["selected_trade_ids"], [])
        self.assertNotEqual(
            artifact["counterfactual_series"]["series_hash"],
            artifact["source_series_hash"],
        )
        self.assertEqual(
            [
                item["value"]
                for item in artifact["counterfactual_series"][
                    "observations"
                ]
            ],
            [
                item["value"]
                for item in artifact["source_series_snapshot"][
                    "observations"
                ]
            ],
        )

    def test_counterfactual_series_tampering_fails_closed(self):
        artifact = self.build()
        tampered = deepcopy(artifact)
        tampered["counterfactual_series"]["observations"][0]["value"] = "1"
        tampered["counterfactual_series"]["series_hash"] = (
            statistical_series_hash(tampered["counterfactual_series"])
        )
        tampered["replay_hash"] = trade_replay_snapshot_hash(tampered)
        self.assertIn(
            "TRADE_REPLAY_COUNTERFACTUAL_MISMATCH",
            trade_replay_snapshot_reasons(tampered),
        )

    def test_selected_trade_removes_all_fills_and_owned_funding(self):
        source, snapshots, valuations = complete_trade_replay_inputs(
            trade_pnls=("12",)
        )
        snapshot = snapshots[0]
        snapshot["fills"][1]["price"] = "110"
        snapshot["fills"][1]["source_event_sequence"] = 4
        snapshot["funding_cashflows"] = [
            {
                "funding_id": "funding-owned",
                "source_event_sequence": 3,
                "instrument_id": "BINANCE:SPOT:BTCUSDT",
                "signed_amount_usdt": "2",
                "position_quantity": "1",
                "funding_rate": "0.02",
                "mark_price": "100",
                "settled_at": timestamp(12),
            }
        ]
        snapshot["equity_points"][-1]["source_event_sequence"] = 5
        CompleteTradeSourceReplayTests.rehash(
            source,
            snapshots,
            valuations,
        )

        artifact = build_trade_replay_snapshot(
            replay_id="funding-removal",
            source_series_snapshot=source,
            economic_snapshots=snapshots,
            valuation_checkpoints=valuations,
            generated_at=source["generated_at"],
        )

        self.assertEqual(
            artifact["completed_trades"][0]["funding_ids"],
            ["funding-owned"],
        )
        self.assertEqual(
            artifact["completed_trades"][0][
                "economic_contribution_usdt"
            ],
            "12",
        )
        self.assertEqual(
            artifact["counterfactual_series"]["observations"][0][
                "value"
            ],
            "0",
        )

    def test_external_flows_and_allocated_costs_are_preserved(self):
        source, snapshots, valuations = complete_trade_replay_inputs(
            trade_pnls=("60",)
        )
        snapshot = snapshots[0]
        snapshot["fills"][1]["price"] = "110"
        snapshot["fills"][1]["source_event_sequence"] = 4
        snapshot["external_cash_flows"] = [
            {
                "flow_id": "deposit-kept",
                "source_event_sequence": 3,
                "flow_type": "DEPOSIT",
                "signed_amount_usdt": "50",
                "occurred_at": timestamp(10),
            }
        ]
        snapshot["allocated_costs"] = [
            {
                "cost_id": "shared-cost-kept",
                "source_event_sequence": 5,
                "category": "INFRASTRUCTURE",
                "amount_usdt": "2",
                "allocation_scope": "SHARED",
                "occurred_at": timestamp(20),
            }
        ]
        snapshot["equity_points"][-1]["source_event_sequence"] = 6
        CompleteTradeSourceReplayTests.rehash(
            source,
            snapshots,
            valuations,
            recompute_values=False,
        )
        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            source["observations"][0]["value"] = canonical_decimal(
                (Decimal("1008") / Decimal("1000")).ln()
            )
            source["series_hash"] = statistical_series_hash(source)

        artifact = build_trade_replay_snapshot(
            replay_id="cost-flow-preservation",
            source_series_snapshot=source,
            economic_snapshots=snapshots,
            valuation_checkpoints=valuations,
            generated_at=source["generated_at"],
        )

        with localcontext() as context:
            context.prec = 50
            context.rounding = ROUND_HALF_EVEN
            expected = canonical_decimal(
                (Decimal("998") / Decimal("1000")).ln()
            )
        self.assertEqual(
            artifact["counterfactual_series"]["observations"][0][
                "value"
            ],
            expected,
        )
        source_value = Decimal(
            source["observations"][0]["value"]
        )
        self.assertNotEqual(
            Decimal(expected),
            source_value - Decimal("10"),
        )

    def test_artifact_schema_and_decimal_context_are_deterministic(self):
        schema = json.loads(
            (
                ROOT / "config" / "trade-replay-snapshot-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        original_precision = getcontext().prec
        hashes = set()
        try:
            for precision in (9, 18, 28, 60):
                getcontext().prec = precision
                artifact = self.build()
                self.assertEqual(
                    list(
                        Draft202012Validator(schema).iter_errors(
                            artifact
                        )
                    ),
                    [],
                )
                hashes.add(artifact["replay_hash"])
        finally:
            getcontext().prec = original_precision
        self.assertEqual(len(hashes), 1)

    def test_semantic_revalidation_ignores_global_decimal_context(self):
        artifact = self.build()
        original_precision = getcontext().prec
        try:
            for precision in (9, 18, 28, 60):
                getcontext().prec = precision
                self.assertEqual(
                    trade_replay_snapshot_reasons(artifact),
                    (),
                )
                status, value, reasons = (
                    leave_top_5_positive_trades_out_mbb_lcb95(
                        {"trade_replay_snapshot": artifact}
                    )
                )
                self.assertEqual((status, value, reasons), (
                    "COMPUTED",
                    "0",
                    (),
                ))
        finally:
            getcontext().prec = original_precision


class CompleteTradeReplayEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.artifact = CompleteTradeCounterfactualTests.build()
        self.source_series = self.artifact["source_series_snapshot"]
        self.policy_bundle = PolicyBundle.__new__(PolicyBundle)
        self.policy_bundle.root = ROOT / "config"

    def expected_scope(self):
        bindings = self.artifact["policy_bindings"]
        return {
            **self.artifact["scope"],
            "policy_binding_hashes": {
                "accounting_policy_id": bindings[
                    "accounting_policy_hash"
                ],
                "cost_allocation_policy_id": bindings[
                    "cost_allocation_policy_hash"
                ],
                "split_policy_id": bindings["split_policy_hash"],
                "statistical_design_policy_id": bindings[
                    "statistical_design_policy_hash"
                ],
            },
            "experiment_manifest_id": bindings[
                "experiment_manifest_id"
            ],
            "experiment_manifest_hash": bindings[
                "experiment_manifest_hash"
            ],
            "approved_production_capital_usdt": self.artifact[
                "approved_production_capital_usdt"
            ],
        }

    def required_source_hashes(self):
        counterfactual = self.artifact["counterfactual_series"]
        return [
            self.artifact["replay_hash"],
            self.artifact["source_series_hash"],
            *self.artifact["source_economic_snapshot_hashes"],
            counterfactual["series_hash"],
            *[
                observation["counterfactual_replay_period_hash"]
                for observation in counterfactual["observations"]
            ],
        ]

    def test_release_estimator_inputs_use_trade_replay_snapshot(self):
        inputs = self.policy_bundle._estimator_inputs(
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
            "baseline_leave_top_5_positive_trades_out_net_log_growth_lcb95",
            {},
            scope_verified=True,
            trust_verified=True,
            trade_replay_snapshot=self.artifact,
        )
        self.assertEqual(inputs, {"trade_replay_snapshot": self.artifact})

    def test_release_reference_requires_complete_trade_replay_sources(self):
        expected = self.expected_scope()
        evidence = {
            **self.artifact["scope"],
            "policy_binding_hashes": expected["policy_binding_hashes"],
            "experiment_manifest_id": expected["experiment_manifest_id"],
            "experiment_manifest_hash": expected[
                "experiment_manifest_hash"
            ],
            "approved_production_capital_usdt": expected[
                "approved_production_capital_usdt"
            ],
            "artifact_hashes": self.required_source_hashes(),
            "frozen_release_inputs": {
                "trade_replay_snapshot": {
                    "artifact_id": self.artifact["replay_id"],
                    "artifact_hash": self.artifact["replay_hash"],
                },
                "statistical_series_snapshot": {
                    "artifact_id": self.source_series["series_id"],
                    "artifact_hash": self.source_series["series_hash"],
                },
            },
        }
        trust = EvidenceTrustContext(
            policy_bundle_hash="policy",
            binding_ids={},
            binding_hashes={},
            artifact_hashes={
                "trade_replay_snapshot": self.artifact["replay_hash"],
                "statistical_series_snapshot": self.source_series[
                    "series_hash"
                ],
            },
            capital_values={},
            artifact_documents={
                "trade_replay_snapshot": self.artifact,
                "statistical_series_snapshot": self.source_series,
            },
        )

        reasons = self.policy_bundle._trade_replay_reference_reasons(
            evidence,
            trust,
        )
        self.assertEqual(reasons, ())

        incomplete = deepcopy(evidence)
        incomplete["artifact_hashes"] = incomplete["artifact_hashes"][:-1]
        reasons = self.policy_bundle._trade_replay_reference_reasons(
            incomplete,
            trust,
        )
        self.assertIn("TRADE_REPLAY_SOURCE_HASH_MISSING", reasons)

    def test_supporting_observation_requires_complete_trade_replay_sources(
        self,
    ):
        catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        registry = EstimatorRegistry.load(ROOT / "config", catalog)
        resolver = MetricResolver(catalog)
        metric_id = (
            "baseline_leave_top_5_positive_trades_out_net_log_growth_lcb95"
        )
        definition = resolver.resolve(metric_id)
        estimator_inputs = {"trade_replay_snapshot": self.artifact}
        execution = registry.execute(
            definition["estimator_id"],
            estimator_inputs,
        )
        source_hashes = self.required_source_hashes()
        observation = {
            "observation_id": "trade-replay-observation-1",
            "observation_hash": "0" * 64,
            "metric_id": metric_id,
            "metric_unit": definition["unit"],
            "estimator_id": definition["estimator_id"],
            "implementation_id": execution.implementation_id,
            "implementation_version": execution.implementation_version,
            "estimator_inputs": estimator_inputs,
            "status": execution.status,
            "value": execution.value,
            "reason_codes": list(execution.reason_codes),
            "estimator_execution_hash": execution.execution_hash,
            "source_artifact_hashes": source_hashes[:-1],
        }
        observation["observation_hash"] = supporting_observation_hash(
            observation
        )
        expected_scope = self.expected_scope()
        signature = "T" * 86 + "=="
        bundle = {
            "$schema": "./supporting-observation-bundle-v1.schema.json",
            "schema_version": "1.0.0",
            "bundle_id": "trade-replay-supporting-bundle-1",
            "bundle_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "scope_hash": business_hash(expected_scope),
            "policy_bundle_hash": "a" * 64,
            "evaluator_build_hash": "b" * 64,
            "computed_at": "2026-01-02T00:00:01Z",
            "observations": [observation],
            "bundle_attestation": {
                "algorithm": "ED25519",
                "key_id": "trade-replay-authority",
                "signed_at": "2026-01-02T00:00:02Z",
                "signature_base64": signature,
            },
        }
        bundle["bundle_hash"] = supporting_observation_bundle_hash(bundle)
        validation = validate_supporting_observation_bundle(
            bundle,
            schema=load_json_strict(
                ROOT
                / "config"
                / "supporting-observation-bundle-v1.schema.json"
            ),
            expected_scope=expected_scope,
            policy_bundle_hash="a" * 64,
            evaluator_build_hash="b" * 64,
            resolve_metric=resolver.resolve,
            estimators=registry,
            allowed_source_hashes=set(source_hashes),
            verified_attestations={signature: bundle["bundle_hash"]},
            first_result_revealed_at="2026-01-01T00:00:00Z",
        )

        self.assertFalse(validation.valid)
        self.assertIn(
            f"SUPPORTING_TRADE_REPLAY_SOURCE_INCOMPLETE:{metric_id}",
            validation.reason_codes,
        )

        complete = deepcopy(bundle)
        complete["observations"][0][
            "source_artifact_hashes"
        ] = source_hashes
        complete["observations"][0]["observation_hash"] = (
            supporting_observation_hash(complete["observations"][0])
        )
        complete["bundle_hash"] = supporting_observation_bundle_hash(
            complete
        )
        validation = validate_supporting_observation_bundle(
            complete,
            schema=load_json_strict(
                ROOT
                / "config"
                / "supporting-observation-bundle-v1.schema.json"
            ),
            expected_scope=expected_scope,
            policy_bundle_hash="a" * 64,
            evaluator_build_hash="b" * 64,
            resolve_metric=resolver.resolve,
            estimators=registry,
            allowed_source_hashes=set(source_hashes),
            verified_attestations={signature: complete["bundle_hash"]},
            first_result_revealed_at="2026-01-01T00:00:00Z",
        )
        self.assertTrue(validation.valid, validation.reason_codes)

    def test_release_schema_freezes_replay_and_source_series(self):
        schema = load_json_strict(
            ROOT / "config" / "release-evidence-v1.1.schema.json"
        )
        errors = list(
            Draft202012Validator(schema).iter_errors(
                {
                    "metric_id": (
                        "baseline_leave_top_5_positive_trades_out_"
                        "net_log_growth_lcb95"
                    ),
                    "frozen_release_inputs": {},
                }
            )
        )
        replay_errors = [
            error
            for error in errors
            if list(error.absolute_path) == ["frozen_release_inputs"]
            and error.validator == "required"
        ]
        messages = " ".join(error.message for error in replay_errors)
        self.assertIn("trade_replay_snapshot", messages)
        self.assertIn("statistical_series_snapshot", messages)

    def test_insufficient_blocks_is_inconclusive(self):
        artifact = CompleteTradeCounterfactualTests.build(
            trade_pnls=("10",),
            block_length=2,
            minimum_block_count=2,
        )
        status, value, reasons = (
            leave_top_5_positive_trades_out_mbb_lcb95(
                {"trade_replay_snapshot": artifact}
            )
        )
        self.assertEqual(status, "INCONCLUSIVE")
        self.assertIsNone(value)
        self.assertEqual(
            reasons,
            ("STATISTICAL_SERIES_INSUFFICIENT_BLOCKS",),
        )


if __name__ == "__main__":
    unittest.main()
