import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.instruments import InstrumentMetadata, MarketType
from crypto_quant.system_paper_broker import FillScenario
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.system_paper_public_input import (
    build_system_paper_market_bundle,
)
from crypto_quant.system_paper_runtime import (
    SystemPaperRuntimeError,
    SystemPaperSlotInputs,
    build_initial_system_paper_runtime_snapshot,
    load_system_paper_slot_result_bytes,
    load_system_paper_slot_result,
    run_system_paper_slot,
    system_paper_slot_hash,
)
from tests.system_paper_fixtures import (
    DEFAULT_SCHEDULED_FOR as SOURCE_SCHEDULED_FOR,
    valid_public_capture,
)


NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)
SCHEDULED_FOR = "2026-08-02T00:00:00.000Z"


def make_metadata(
    *,
    market_type: MarketType = MarketType.SPOT,
    effective_from: datetime = NOW,
    effective_to_or_null: Optional[datetime] = None,
) -> InstrumentMetadata:
    return InstrumentMetadata(
        schema_version="instrument-metadata-v1",
        instrument_id=f"BINANCE:{market_type.value}:ETHUSDT",
        exchange="BINANCE",
        market_type=market_type,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        settlement_asset="USDT",
        effective_from=effective_from,
        effective_to_or_null=effective_to_or_null,
        price_tick=Decimal("0.01"),
        quantity_step=Decimal("0.0001"),
        min_quantity=Decimal("0.0001"),
        max_quantity=Decimal("1000"),
        min_notional=Decimal("5"),
        contract_multiplier=Decimal("1"),
        supported_order_types=("LIMIT", "MARKET"),
        supported_time_in_force=("GTC", "IOC"),
        supports_reduce_only=market_type is MarketType.USDT_PERP,
        supports_stop_market=True,
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.0015"),
        metadata_source="frozen-runtime-test-fixture",
    )


def make_bundle(
    *,
    long_signal: bool = True,
    bid: str = "99.99",
    ask: str = "100.01",
    scheduled_for: str = SCHEDULED_FOR,
    captured_at: Optional[str] = None,
    metadata: Optional[InstrumentMetadata] = None,
):
    capture, _transport = valid_public_capture(
        scheduled_for=scheduled_for,
        latest="110" if long_signal else "90",
        prior="100",
        bid=bid,
        ask=ask,
        recorded_at_or_none=captured_at,
    )
    bundle = build_system_paper_market_bundle(
        plan=build_system_paper_plan(),
        scheduled_for=scheduled_for,
        capture=capture,
    )
    if metadata is not None:
        bundle["instrument_metadata"] = json.loads(
            canonical_json(metadata.business_payload())
        )
        bundle["instrument_metadata_schema_version"] = metadata.schema_version
    bundle["bundle_hash"] = artifact_self_hash(bundle, "bundle_hash")
    return bundle


def rehash_snapshot(snapshot):
    value = dict(snapshot)
    value["snapshot_hash"] = artifact_self_hash(value, "snapshot_hash")
    return value


def rehash_parent_snapshot(snapshot):
    value = dict(snapshot)
    parent_id = "system_paper_slot_" + "a" * 64
    value["processed_slot_ids"] = [parent_id]
    value["last_slot_id_or_null"] = parent_id
    value["last_slot_hash_or_null"] = "b" * 64
    return rehash_snapshot(value)


def rehash_slot(result):
    value = copy.deepcopy(result)
    value["slot_hash"] = "0" * 64
    value["runtime_snapshot"]["snapshot_hash"] = "0" * 64
    value["runtime_snapshot"]["last_slot_hash_or_null"] = "0" * 64
    value["slot_hash"] = system_paper_slot_hash(value)
    value["runtime_snapshot"]["last_slot_hash_or_null"] = value["slot_hash"]
    value["runtime_snapshot"]["snapshot_hash"] = artifact_self_hash(
        value["runtime_snapshot"],
        "snapshot_hash",
    )
    return value


class SystemPaperRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_system_paper_plan()
        self.previous = build_initial_system_paper_runtime_snapshot(self.plan)

    def inputs(self, **overrides) -> SystemPaperSlotInputs:
        values = {
            "plan": self.plan,
            "scheduled_for": SCHEDULED_FOR,
            "public_market_bundle": make_bundle(),
            "previous_runtime_snapshot": self.previous,
            "fill_scenario": FillScenario.partial_then_full("0.40"),
        }
        values.update(overrides)
        return SystemPaperSlotInputs(**values)

    def test_slot_records_signal_risk_order_fill_ledger_and_reconciliation(self) -> None:
        result = run_system_paper_slot(self.inputs())

        self.assertEqual(result["status"], "SYSTEM_PAPER_SLOT_COMPLETED")
        self.assertEqual(result["signal"]["decision_source"], "NO_AI_BASE")
        self.assertEqual(result["risk"]["state"], "NORMAL")
        self.assertEqual(result["order"]["state"], "FILLED")
        self.assertGreater(Decimal(result["order"]["filled_quantity"]), Decimal("0"))
        self.assertEqual(result["ledger"]["debits_usdt"], result["ledger"]["credits_usdt"])
        self.assertEqual(result["safety_counts"]["credential_reads"], 0)
        self.assertEqual(result["safety_counts"]["account_requests"], 0)
        self.assertEqual(result["safety_counts"]["real_broker_calls"], 0)
        self.assertEqual(result["safety_counts"]["real_order_writes"], 0)
        self.assertEqual(
            result["reconciliation"]["unexplained_position_difference"],
            "0",
        )
        self.assertEqual(result["reconciliation"]["ledger_imbalance_usdt"], "0")
        self.assertTrue(result["replay"]["decision_hash_match"])
        self.assertEqual(result["slot_hash"], system_paper_slot_hash(result))
        self.assertEqual(
            result["runtime_snapshot"]["last_slot_hash_or_null"],
            result["slot_hash"],
        )
        self.assertIsNone(result["runtime_snapshot"]["active_order_or_null"])
        self.assertEqual(result["reconciliation"]["status"], "RECONCILED")

    def test_runtime_accepts_only_the_source_replayed_market_bundle(self) -> None:
        """Catches retaining the old hash-only observed_at bundle contract."""

        capture, _transport = valid_public_capture()
        bundle = build_system_paper_market_bundle(
            plan=self.plan,
            scheduled_for=SOURCE_SCHEDULED_FOR,
            capture=capture,
        )

        try:
            result = run_system_paper_slot(
                self.inputs(
                    scheduled_for=SOURCE_SCHEDULED_FOR,
                    public_market_bundle=bundle,
                )
            )
        except SystemPaperRuntimeError as error:
            self.fail("runtime rejected the replayed source bundle: " + str(error))

        self.assertEqual(result["status"], "SYSTEM_PAPER_SLOT_COMPLETED")
        self.assertEqual(
            result["replay_inputs"]["public_market_bundle"]["captured_at"],
            "2026-08-02T12:05:01.000Z",
        )

    def test_next_slot_refuses_new_decision_while_unknown_order_is_active(self) -> None:
        first = run_system_paper_slot(
            self.inputs(fill_scenario=FillScenario.disconnect_after_submit())
        )

        with self.assertRaisesRegex(
            SystemPaperRuntimeError,
            "SYSTEM_PAPER_ACTIVE_ORDER_RECONCILIATION_REQUIRED",
        ):
            run_system_paper_slot(
                self.inputs(
                    scheduled_for="2026-08-02T04:00:00.000Z",
                    public_market_bundle=make_bundle(
                        scheduled_for="2026-08-02T04:00:00.000Z"
                    ),
                    previous_runtime_snapshot=first["runtime_snapshot"],
                )
            )

    def test_disconnect_reconciliation_can_finish_within_the_same_slot(self) -> None:
        result = run_system_paper_slot(
            self.inputs(fill_scenario=FillScenario.disconnect_then_full())
        )

        self.assertEqual(result["order"]["state"], "FILLED")
        self.assertIsNone(result["runtime_snapshot"]["active_order_or_null"])
        self.assertEqual(result["reconciliation"]["status"], "RECONCILED")

    def test_no_trade_signal_keeps_cash_and_position_unchanged(self) -> None:
        result = run_system_paper_slot(
            self.inputs(public_market_bundle=make_bundle(long_signal=False))
        )

        self.assertIsNone(result["order"])
        self.assertEqual(result["signal"]["recommended_action"], "HOLD_CURRENT")
        self.assertEqual(result["runtime_snapshot"]["cash_usdt"], "1000")
        self.assertEqual(result["runtime_snapshot"]["position_quantity"], "0")

    def test_unknown_order_locks_risk_and_preserves_balanced_ledger(self) -> None:
        result = run_system_paper_slot(
            self.inputs(fill_scenario=FillScenario.disconnect_after_submit())
        )

        self.assertEqual(result["order"]["state"], "UNKNOWN")
        self.assertEqual(result["risk"]["state"], "LOCKED")
        self.assertEqual(result["runtime_snapshot"]["risk_state"], "LOCKED")
        self.assertEqual(result["ledger"]["debits_usdt"], "0")
        self.assertEqual(result["ledger"]["credits_usdt"], "0")

    def test_rejected_order_is_recorded_without_economic_mutation(self) -> None:
        result = run_system_paper_slot(
            self.inputs(fill_scenario=FillScenario.rejected())
        )

        self.assertEqual(result["order"]["state"], "REJECTED")
        self.assertIn("SIMULATED_ORDER_REJECTED", result["risk"]["reason_codes"])
        self.assertEqual(result["runtime_snapshot"]["cash_usdt"], "1000")
        self.assertEqual(result["runtime_snapshot"]["position_quantity"], "0")

    def test_losing_mark_to_market_is_preserved_even_without_a_new_trade(self) -> None:
        previous = rehash_parent_snapshot(
            {
                **self.previous,
                "cash_usdt": "890",
                "position_quantity": "1",
                "position_cost_usdt": "110",
                "average_entry_price_or_null": "110",
                "marked_equity_usdt": "1000",
                "peak_equity_usdt": "1000",
            }
        )

        result = run_system_paper_slot(
            self.inputs(
                previous_runtime_snapshot=previous,
                public_market_bundle=make_bundle(long_signal=False),
            )
        )

        self.assertIsNone(result["order"])
        self.assertEqual(result["ledger"]["unrealized_pnl_usdt"], "-10.01")
        self.assertEqual(result["runtime_snapshot"]["marked_equity_usdt"], "989.99")

    def test_closed_losing_trade_relieves_cost_and_records_realized_pnl(self) -> None:
        previous = rehash_parent_snapshot(
            {
                **self.previous,
                "cash_usdt": "890",
                "position_quantity": "1",
                "position_cost_usdt": "110",
                "average_entry_price_or_null": "110",
                "marked_equity_usdt": "1000",
                "peak_equity_usdt": "1000",
                "risk_state": "LOCKED",
            }
        )

        result = run_system_paper_slot(
            self.inputs(
                previous_runtime_snapshot=previous,
                fill_scenario=FillScenario.immediate_full(),
            )
        )

        self.assertEqual(result["order"]["state"], "FILLED")
        self.assertEqual(result["runtime_snapshot"]["position_quantity"], "0")
        self.assertEqual(result["runtime_snapshot"]["position_cost_usdt"], "0")
        self.assertIsNone(result["runtime_snapshot"]["average_entry_price_or_null"])
        self.assertLess(Decimal(result["ledger"]["realized_pnl_usdt"]), Decimal("0"))
        self.assertEqual(
            result["runtime_snapshot"]["cumulative_realized_pnl_usdt"],
            result["ledger"]["realized_pnl_usdt"],
        )
        self.assertGreater(
            Decimal(result["runtime_snapshot"]["cumulative_fees_usdt"]),
            Decimal("0"),
        )
        self.assertEqual(result["ledger"]["debits_usdt"], result["ledger"]["credits_usdt"])

    def test_duplicate_slot_is_rejected_from_the_parent_snapshot(self) -> None:
        first = run_system_paper_slot(self.inputs())

        with self.assertRaisesRegex(
            SystemPaperRuntimeError,
            "SYSTEM_PAPER_SLOT_DUPLICATE",
        ):
            run_system_paper_slot(
                self.inputs(previous_runtime_snapshot=first["runtime_snapshot"])
            )

    def test_hard_drawdown_boundary_blocks_new_exposure(self) -> None:
        previous = rehash_parent_snapshot(
            {
                **self.previous,
                "cash_usdt": "800",
                "marked_equity_usdt": "800",
                "peak_equity_usdt": "1000",
            }
        )

        result = run_system_paper_slot(
            self.inputs(previous_runtime_snapshot=previous)
        )

        self.assertIsNone(result["order"])
        self.assertEqual(result["risk"]["drawdown_state"], "HARD_BOUNDARY")
        self.assertEqual(result["risk"]["state"], "LOCKED")
        self.assertIn("DRAWDOWN_HARD_BOUNDARY", result["risk"]["reason_codes"])

    def test_halt_drawdown_issues_only_a_protective_sell(self) -> None:
        previous = rehash_parent_snapshot(
            {
                **self.previous,
                "cash_usdt": "0",
                "position_quantity": "10",
                "position_cost_usdt": "1000",
                "average_entry_price_or_null": "100",
                "marked_equity_usdt": "1000",
                "peak_equity_usdt": "1000",
            }
        )

        result = run_system_paper_slot(
            self.inputs(
                previous_runtime_snapshot=previous,
                public_market_bundle=make_bundle(bid="83.99", ask="84.01"),
            )
        )

        self.assertEqual(result["risk"]["drawdown_state"], "HALT")
        self.assertEqual(result["risk"]["state"], "LOCKED")
        self.assertEqual(result["order"]["side"], "SELL")
        self.assertLess(
            Decimal(result["runtime_snapshot"]["position_quantity"]),
            Decimal("10"),
        )
        self.assertGreater(
            Decimal(result["runtime_snapshot"]["cash_usdt"]),
            Decimal("0"),
        )

    def test_parent_risk_lock_allows_reduction_but_never_new_exposure(self) -> None:
        previous = rehash_parent_snapshot(
            {
                **self.previous,
                "cash_usdt": "900",
                "position_quantity": "1",
                "position_cost_usdt": "100",
                "average_entry_price_or_null": "100",
                "marked_equity_usdt": "1000",
                "peak_equity_usdt": "1000",
                "risk_state": "LOCKED",
            }
        )

        result = run_system_paper_slot(
            self.inputs(previous_runtime_snapshot=previous)
        )

        self.assertEqual(result["order"]["side"], "SELL")
        self.assertIn("PARENT_RISK_LOCKED", result["risk"]["reason_codes"])
        self.assertLess(
            Decimal(result["runtime_snapshot"]["position_quantity"]),
            Decimal("1"),
        )


    def test_result_schema_mirror_and_strict_loader_round_trip(self) -> None:
        result = run_system_paper_slot(self.inputs())
        root = Path(__file__).resolve().parents[1]
        config_schema = root / "config" / "system-paper-slot-result-v1.schema.json"
        package_schema = (
            root
            / "src"
            / "crypto_quant"
            / "schemas"
            / "system-paper-slot-result-v1.schema.json"
        )

        self.assertEqual(config_schema.read_bytes(), package_schema.read_bytes())
        schema = json.loads(config_schema.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(result)), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "slot.json"
            path.write_bytes(canonical_json(result).encode("utf-8") + b"\n")
            self.assertEqual(load_system_paper_slot_result(path), result)

    def test_loader_rejects_duplicate_keys_and_binary_floats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory).resolve() / "duplicate.json"
            duplicate.write_bytes(b'{"slot_hash":"a","slot_hash":"b"}')
            with self.assertRaisesRegex(
                SystemPaperRuntimeError,
                "SYSTEM_PAPER_SLOT_JSON_DUPLICATE_KEY",
            ):
                load_system_paper_slot_result(duplicate)

            binary_float = Path(directory).resolve() / "float.json"
            binary_float.write_bytes(b'{"value":1.5}')
            with self.assertRaisesRegex(
                SystemPaperRuntimeError,
                "SYSTEM_PAPER_SLOT_JSON_FLOAT_FORBIDDEN",
            ):
                load_system_paper_slot_result(binary_float)

    def test_loader_replays_full_slot_and_rejects_semantic_forgery(self) -> None:
        forged = copy.deepcopy(run_system_paper_slot(self.inputs()))
        forged["order"]["side"] = "SELL"
        forged["order"]["result_hash"] = business_hash(
            {
                "local_order_id": forged["order"]["local_order_id"],
                "instrument_id": forged["order"]["instrument_id"],
                "side": forged["order"]["side"],
                "fill_policy_version": forged["order"]["fill_policy_version"],
                "state": forged["order"]["state"],
                "requested_quantity": forged["order"]["requested_quantity"],
                "cumulative_filled_quantity": forged["order"]["filled_quantity"],
                "average_fill_price": forged["order"]["average_fill_price_or_null"],
                "fee_usdt": forged["order"]["fee_usdt"],
                "event_ids": forged["order"]["event_ids"],
                "risk_lock_required": forged["order"]["risk_lock_required"],
            }
        )
        forged = rehash_slot(forged)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "forged.json"
            path.write_bytes(canonical_json(forged).encode("utf-8") + b"\n")
            with self.assertRaisesRegex(
                SystemPaperRuntimeError,
                "SYSTEM_PAPER_FULL_REPLAY_MISMATCH",
            ):
                load_system_paper_slot_result(path)

    def test_nonfirst_loader_requires_the_exact_parent_artifact_chain(self) -> None:
        first = run_system_paper_slot(
            self.inputs(public_market_bundle=make_bundle(long_signal=False))
        )
        second = run_system_paper_slot(
            self.inputs(
                scheduled_for="2026-08-02T04:00:00.000Z",
                public_market_bundle=make_bundle(
                    long_signal=False,
                    scheduled_for="2026-08-02T04:00:00.000Z",
                ),
                previous_runtime_snapshot=first["runtime_snapshot"],
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            parent_path = Path(directory).resolve() / "parent.json"
            child_path = Path(directory).resolve() / "child.json"
            parent_path.write_bytes(canonical_json(first).encode("utf-8") + b"\n")
            child_path.write_bytes(canonical_json(second).encode("utf-8") + b"\n")
            with self.assertRaisesRegex(
                SystemPaperRuntimeError,
                "SYSTEM_PAPER_PARENT_ARTIFACT_REQUIRED",
            ):
                load_system_paper_slot_result(child_path)
            self.assertEqual(
                load_system_paper_slot_result(
                    child_path,
                    parent_result_paths=(parent_path,),
                ),
                second,
            )

    def test_full_slot_replay_is_byte_deterministic(self) -> None:
        first = run_system_paper_slot(self.inputs())
        second = run_system_paper_slot(self.inputs())

        self.assertEqual(canonical_json(first), canonical_json(second))

    def test_market_bundle_unknown_fields_fail_closed(self) -> None:
        bundle = make_bundle()
        bundle["credential"] = "must-never-be-accepted"
        bundle["bundle_hash"] = artifact_self_hash(bundle, "bundle_hash")

        with self.assertRaisesRegex(
            SystemPaperRuntimeError,
            "SYSTEM_PAPER_MARKET_BUNDLE_INVALID",
        ):
            run_system_paper_slot(self.inputs(public_market_bundle=bundle))

    def test_market_bundle_rejects_instrument_not_replayed_from_sources(self) -> None:
        bundle = make_bundle(metadata=make_metadata(market_type=MarketType.USDT_PERP))

        with self.assertRaisesRegex(
            SystemPaperRuntimeError,
            "SYSTEM_PAPER_MARKET_BUNDLE_INVALID",
        ):
            run_system_paper_slot(self.inputs(public_market_bundle=bundle))

    def test_market_metadata_cannot_be_detached_from_source_receipts(self) -> None:
        bundle = make_bundle(
            metadata=make_metadata(
                effective_from=NOW - timedelta(days=2),
                effective_to_or_null=NOW - timedelta(days=1),
            )
        )

        with self.assertRaisesRegex(
            SystemPaperRuntimeError,
            "SYSTEM_PAPER_MARKET_BUNDLE_INVALID",
        ):
            run_system_paper_slot(self.inputs(public_market_bundle=bundle))

    def test_slot_carries_exact_instrument_and_provider_binding(self) -> None:
        result = run_system_paper_slot(self.inputs())

        self.assertEqual(result["instrument"]["provider"], "BINANCE_MARKET_DATA_ONLY")
        self.assertEqual(result["instrument"]["instrument_id"], "BINANCE:SPOT:ETHUSDT")
        self.assertEqual(result["instrument"]["market_type"], "SPOT")
        self.assertEqual(result["instrument"]["symbol"], "ETHUSDT")
        self.assertEqual(result["instrument"]["contract_multiplier"], "1")
        self.assertEqual(
            result["instrument"]["metadata_hash"],
            "6a75a74f4ffd8dc2c028716321ecd933a0b90c4d9d5b4d35c6105b5e3aa91084",
        )

    def test_position_snapshot_requires_a_positive_average_entry(self) -> None:
        previous = rehash_parent_snapshot(
            {
                **self.previous,
                "cash_usdt": "900",
                "position_quantity": "1",
                "marked_equity_usdt": "1000",
                "peak_equity_usdt": "1000",
            }
        )

        with self.assertRaisesRegex(
            SystemPaperRuntimeError,
            "SYSTEM_PAPER_RUNTIME_SNAPSHOT_INVALID",
        ):
            run_system_paper_slot(
                self.inputs(previous_runtime_snapshot=previous)
            )

    def test_first_slot_requires_the_exact_frozen_genesis_snapshot(self) -> None:
        forged = rehash_snapshot(
            {
                **self.previous,
                "cash_usdt": "900",
                "marked_equity_usdt": "900",
            }
        )

        with self.assertRaisesRegex(
            SystemPaperRuntimeError,
            "SYSTEM_PAPER_RUNTIME_GENESIS_MISMATCH",
        ):
            run_system_paper_slot(
                self.inputs(previous_runtime_snapshot=forged)
            )

    def test_nonempty_snapshot_requires_last_id_and_hash_tail_binding(self) -> None:
        forged = rehash_snapshot(
            {
                **self.previous,
                "processed_slot_ids": ["system_paper_slot_" + "a" * 64],
                "last_slot_id_or_null": "system_paper_slot_" + "b" * 64,
                "last_slot_hash_or_null": "c" * 64,
            }
        )

        with self.assertRaisesRegex(
            SystemPaperRuntimeError,
            "SYSTEM_PAPER_RUNTIME_PARENT_BINDING_INVALID",
        ):
            run_system_paper_slot(
                self.inputs(previous_runtime_snapshot=forged)
            )


class SystemPaperRuntimeLoaderTests(unittest.TestCase):
    """Regression tests for bytes/path trust-chain equivalence."""

    def setUp(self) -> None:
        self.plan = build_system_paper_plan()
        self.first_inputs = SystemPaperSlotInputs(
            plan=self.plan,
            scheduled_for=SCHEDULED_FOR,
            public_market_bundle=make_bundle(long_signal=False),
            previous_runtime_snapshot=build_initial_system_paper_runtime_snapshot(
                self.plan
            ),
            fill_scenario=FillScenario.immediate_full(),
        )

    def second_inputs(self, snapshot):
        return SystemPaperSlotInputs(
            plan=self.plan,
            scheduled_for="2026-08-02T04:00:00.000Z",
            public_market_bundle=make_bundle(
                long_signal=False,
                scheduled_for="2026-08-02T04:00:00.000Z",
            ),
            previous_runtime_snapshot=snapshot,
            fill_scenario=FillScenario.immediate_full(),
        )

    def test_bytes_loader_matches_path_loader_and_replays_full_parent_chain(self):
        # Catches a loader that verifies only a path or only the outer result.
        first = run_system_paper_slot(self.first_inputs)
        second = run_system_paper_slot(self.second_inputs(first["runtime_snapshot"]))
        first_body = canonical_json(first).encode("utf-8")
        second_body = canonical_json(second).encode("utf-8")

        loaded = load_system_paper_slot_result_bytes(
            second_body,
            parent_result_bodies=(first_body,),
        )

        self.assertEqual(loaded, second)
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve() / "parent.json"
            child = Path(directory).resolve() / "child.json"
            parent.write_bytes(first_body)
            child.write_bytes(second_body)
            self.assertEqual(
                load_system_paper_slot_result(child, parent_result_paths=(parent,)),
                loaded,
            )

    def test_bytes_loader_rejects_ambiguous_or_noncanonical_json_bytes(self):
        # Catches accepting byte representations that change the signed payload.
        for body, reason in (
            (b'{"slot_hash":"a","slot_hash":"b"}', "DUPLICATE_KEY"),
            (b'{"value":1.5}', "FLOAT_FORBIDDEN"),
            (b"{}\n\n", "CANONICAL_BYTES_REQUIRED"),
        ):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(SystemPaperRuntimeError, reason):
                    load_system_paper_slot_result_bytes(body)

        first = run_system_paper_slot(self.first_inputs)
        self.assertEqual(
            load_system_paper_slot_result_bytes(
                canonical_json(first).encode("utf-8") + b"\n"
            ),
            first,
        )

    def test_bytes_loader_rejects_missing_extra_reordered_and_tampered_parents(self):
        # Catches bypassing ordered full-chain replay or accepting rehashed parents.
        first = run_system_paper_slot(self.first_inputs)
        second = run_system_paper_slot(self.second_inputs(first["runtime_snapshot"]))
        third = run_system_paper_slot(
            SystemPaperSlotInputs(
                plan=self.plan,
                scheduled_for="2026-08-02T08:00:00.000Z",
                public_market_bundle=make_bundle(
                    long_signal=False,
                    scheduled_for="2026-08-02T08:00:00.000Z",
                ),
                previous_runtime_snapshot=second["runtime_snapshot"],
                fill_scenario=FillScenario.immediate_full(),
            )
        )
        first_body = canonical_json(first).encode("utf-8")
        second_body = canonical_json(second).encode("utf-8")
        third_body = canonical_json(third).encode("utf-8")
        tampered = copy.deepcopy(second)
        tampered["risk"]["reason_codes"] = ["FORGED"]
        tampered = rehash_slot(tampered)
        tampered_body = canonical_json(tampered).encode("utf-8")

        for parents in (
            (),
            (second_body,),
            (first_body, third_body),
            (second_body, first_body),
            (first_body, tampered_body),
        ):
            with self.subTest(parent_count=len(parents)):
                with self.assertRaises(SystemPaperRuntimeError):
                    load_system_paper_slot_result_bytes(
                        third_body,
                        parent_result_bodies=parents,
                    )


if __name__ == "__main__":
    unittest.main()
