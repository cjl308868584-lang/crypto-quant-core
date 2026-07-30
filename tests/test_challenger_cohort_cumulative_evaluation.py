import contextlib
import copy
import io
import json
import stat
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.challenger_cohort_cumulative_evaluation import (
    ChallengerCohortCumulativeEvaluationError,
    _path_result,
    _plan_binding,
    _read_exact_evaluation_plan,
    _read_exact_pilot,
    _sample_statistics,
    _stress_result,
    build_challenger_cohort_cumulative_evaluation,
    challenger_cohort_cumulative_evaluation_hash,
    evaluate_challenger_cohort,
    load_complete_economic_inventory,
    load_challenger_cohort_cumulative_evaluation,
    publish_challenger_cohort_cumulative_evaluation,
)
from crypto_quant.challenger_cohort_daily_archive import (
    acquire_challenger_cohort_daily_archives,
)
from crypto_quant.challenger_cohort_cumulative_evaluation_cli import (
    _parser,
    main as cli_main,
)
from crypto_quant.challenger_cohort_economic_results import (
    publish_all_cohort_economic_results,
    read_exact_economic_plan,
)
from crypto_quant.challenger_cohort_episode_receipt import _read_exact_plan
from tests.test_challenger_cohort_daily_archive import (
    FixtureTransport,
    fixture_loader,
    period_responses,
    write_receipts,
)
from tests.test_challenger_cohort_economic_results import complete_receipt
from tests.test_challenger_episode_economic_evaluator import daily_archive


ROOT = Path(__file__).resolve().parents[1]
COHORT_PLAN_PATH = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-cohort-plan-v0.43.0.json"
)
EVALUATION_PLAN_PATH = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-cohort-evaluation-plan-v0.44.0.json"
)
ECONOMIC_PLAN_PATH = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-economic-plan-v0.37.0.json"
)
PILOT_PATH = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-economic-result-v0.42.0.json"
)
ZERO = "0" * 64


class ChallengerCohortCumulativeEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cohort_plan, cls.cohort_sha = _read_exact_plan(
            COHORT_PLAN_PATH
        )
        cls.evaluation_plan, cls.evaluation_sha = (
            _read_exact_evaluation_plan(
                EVALUATION_PLAN_PATH,
                cohort_plan=cls.cohort_plan,
                cohort_plan_file_sha256=cls.cohort_sha,
            )
        )
        cls.economic_plan, cls.economic_sha = read_exact_economic_plan(
            ECONOMIC_PLAN_PATH
        )
        _cohort_binding, cls.economic_binding = _plan_binding(
            cls.cohort_plan,
            cls.cohort_sha,
            cls.economic_plan,
            cls.economic_sha,
        )
        cls.pilot, cls.pilot_sha = _read_exact_pilot(PILOT_PATH)

    def continuity(self, ids=(), *, observed_at="2026-10-29T12:00:00.000Z"):
        return {
            "observed_at": observed_at,
            "tail_end": "2026-10-29T12:00:00.000Z",
            "cohort_plan": {
                "plan_id": self.cohort_plan["plan_id"],
                "plan_hash": self.cohort_plan["plan_hash"],
                "plan_file_sha256": self.cohort_sha,
            },
            "state": {
                "path": "/trusted/state.sqlite",
                "file_sha256": "1" * 64,
                "total_decision_count": 540,
                "decision_chain_end_hash_or_null": "2" * 64,
            },
            "window_slot_count": 540,
            "cohort_slot_count": 540,
            "slots": [],
            "slots_root_hash": "3" * 64,
            "completed_episode_count": len(ids),
            "completed_episode_ids": list(ids),
            "completed_episode_ids_root_hash": business_hash(list(ids)),
            "active_episode_id_or_null": None,
            "next_required_slot_or_null": None,
            "source_bundle_count": 540,
            "source_bundles_root_hash": "4" * 64,
            "stdout_records_root_hash": "5" * 64,
            "stdout_prefix_sha256_or_null": "6" * 64,
            "stderr_prefix_sha256_or_null": "7" * 64,
            "launchctl_print_hash": "8" * 64,
            "launchd_runs_observed": 540,
            "security_boundary": {
                "launchctl_print_count": 1,
                "market_request_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
                "state_write_count": 0,
                "runner_invocation_count": 0,
            },
        }

    def record(self, ordinal, entry, net_return, *, source_exit="102"):
        episode_id = f"challenger_episode_{ordinal:064x}"
        receipt = {
            "receipt_id": f"receipt_{ordinal}",
            "receipt_hash": f"{ordinal:064x}",
            "episode": {
                "ordinal": ordinal,
                "episode_id": episode_id,
                "entry_scheduled_for": entry,
            },
        }
        result = {
            "result_id": f"result_{ordinal}",
            "result_hash": f"{ordinal + 1000:064x}",
            "evaluated_at": "2026-10-29T12:00:00.000Z",
            "economics": {
                "net_pnl_usdt": str(
                    (net_return * 1000).quantize(net_return)
                ),
                "net_return": str(net_return),
                "positive_label": 1 if net_return > 0 else 0,
                "entry_source_high": "100",
                "exit_source_low": source_exit,
            },
        }
        return {
            "episode_record": {
                "receipt": receipt,
                "file_sha256": f"{ordinal + 2000:064x}",
            },
            "result": result,
            "result_file_sha256": f"{ordinal + 3000:064x}",
        }

    def records(self, count=36, *, source_exit="102"):
        records = []
        blocks = self.evaluation_plan["time_blocks"]
        for index in range(count):
            block = blocks[index % 6]
            entry = block["start_inclusive"]
            variation = ((index * 7) % 11) - 5
            value = (
                Decimal("0.010")
                + Decimal(variation) * Decimal("0.00005")
            )
            records.append(
                self.record(
                    index + 1, entry, value, source_exit=source_exit
                )
            )
        return tuple(records)

    def inventory(self, records=()):
        latest = (
            {
                "index_id": "challenger_cohort_economic_result_index_"
                + "9" * 64,
                "index_hash": "a" * 64,
            }
            if records
            else None
        )
        return {
            "cohort_binding": {},
            "economic_binding": self.economic_binding,
            "episode_records": tuple(
                item["episode_record"] for item in records
            ),
            "result_records": tuple(records),
            "latest_index": latest,
            "latest_index_hash": latest["index_hash"] if latest else ZERO,
            "latest_index_file_sha256": "b" * 64 if latest else ZERO,
        }

    def economic_fixture(self, base):
        receipt_root = base / "receipts"
        archive_root = base / "archives"
        result_root = base / "results"
        receipt = complete_receipt(
            1,
            entry_scheduled="2026-07-30T12:00:00.000Z",
            entry_recorded="2026-07-30T12:02:06.752Z",
            exit_recorded="2026-07-30T20:02:06.752Z",
        )
        write_receipts(receipt_root, [receipt])
        archive, checksum = daily_archive(
            "2026-07-30",
            selected_prices={
                "2026-07-30T12:03:00.000Z": ("2000.01", "1999"),
                "2026-07-30T20:03:00.000Z": ("2101", "2100.01"),
            },
        )
        acquire_challenger_cohort_daily_archives(
            cohort_plan_path=COHORT_PLAN_PATH,
            episode_receipt_output_root=receipt_root,
            install_receipt_path=Path("/unused/install.json"),
            contract_path=Path("/unused/contract.json"),
            plist_path=Path("/unused/agent.plist"),
            archive_output_root=archive_root,
            observed_at="2026-07-31T00:05:00.000Z",
            transport=FixtureTransport(
                period_responses("2026-07-30", archive, checksum)
            ),
            receipt_loader=fixture_loader,
        )
        publish_all_cohort_economic_results(
            cohort_plan_path=COHORT_PLAN_PATH,
            economic_plan_path=ECONOMIC_PLAN_PATH,
            episode_receipt_output_root=receipt_root,
            install_receipt_path=Path("/unused/install.json"),
            contract_path=Path("/unused/contract.json"),
            plist_path=Path("/unused/agent.plist"),
            archive_output_root=archive_root,
            result_output_root=result_root,
            receipt_loader=fixture_loader,
        )
        return receipt_root, archive_root, result_root

    def build(self, records=()):
        ids = tuple(
            item["episode_record"]["receipt"]["episode"]["episode_id"]
            for item in records
        )
        return build_challenger_cohort_cumulative_evaluation(
            cohort_plan=self.cohort_plan,
            cohort_plan_file_sha256=self.cohort_sha,
            evaluation_plan=self.evaluation_plan,
            evaluation_plan_file_sha256=self.evaluation_sha,
            economic_binding=self.economic_binding,
            pilot=self.pilot,
            pilot_file_sha256=self.pilot_sha,
            continuity=self.continuity(ids),
            inventory=self.inventory(records),
        )

    def test_schema_mirrors_are_identical_and_valid(self):
        name = "challenger-cohort-cumulative-evaluation-v1.schema.json"
        config = ROOT / "config" / name
        package = ROOT / "src" / "crypto_quant" / "schemas" / name
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_text()))

    def test_exact_plans_and_negative_pilot_are_bound(self):
        self.assertEqual(
            self.evaluation_sha,
            "49e3b7642e163bb95c4ce01bc1c8d95a"
            "23b0cefce277d2f99f2e69029207a4d8",
        )
        self.assertEqual(
            self.pilot_sha,
            "8627677275c31de573f1a59f638ba167"
            "8772115dc6d932027a36e2f8b62d9fee",
        )
        self.assertLess(
            Decimal(self.pilot["economics"]["net_return"]),
            0,
        )

    def test_pre_tail_does_not_call_economic_loader_or_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            calls = []

            def continuity_loader(**_kwargs):
                return self.continuity(
                    (),
                    observed_at="2026-08-01T00:00:00.000Z",
                )

            def economic_loader(**_kwargs):
                calls.append(True)
                raise AssertionError("economic loader must not run")

            summary = evaluate_challenger_cohort(
                cohort_plan_path=COHORT_PLAN_PATH,
                evaluation_plan_path=EVALUATION_PLAN_PATH,
                economic_plan_path=Path("/must/not/be/read.json"),
                pilot_result_path=PILOT_PATH,
                install_receipt_path=Path("/unused/install.json"),
                contract_path=Path("/unused/contract.json"),
                plist_path=Path("/unused/agent.plist"),
                episode_receipt_output_root=Path("/unused/receipts"),
                archive_output_root=Path("/unused/archives"),
                result_output_root=Path("/unused/results"),
                evaluation_output_root=output,
                continuity_loader=continuity_loader,
                economic_loader=economic_loader,
            )
            self.assertEqual(
                summary["status"],
                "COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS",
            )
            self.assertEqual(calls, [])
            self.assertFalse(output.exists())
            self.assertNotIn("pnl", canonical_json(summary).lower())

    def test_complete_zero_episode_cohort_is_trusted_inconclusive(self):
        evaluation = self.build()
        self.assertEqual(
            evaluation["status"],
            "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        )
        self.assertEqual(
            evaluation["economic_inventory"]["latest_index_hash"], ZERO
        )
        self.assertEqual(
            evaluation["all_stream_descriptive"]["all_stream_count"], 1
        )
        self.assertEqual(
            evaluation["evaluation_hash"],
            challenger_cohort_cumulative_evaluation_hash(evaluation),
        )

    def test_positive_diverse_sample_passes_all_frozen_gates(self):
        evaluation = self.build(self.records())
        self.assertEqual(
            evaluation["status"], "RESEARCH_CONTINUATION_GATE_PASS"
        )
        self.assertTrue(
            evaluation["confirmatory_statistics"][
                "all_sample_gates_pass"
            ]
        )
        self.assertTrue(
            evaluation["leave_top_5"]["statistics"][
                "all_sample_gates_pass"
            ]
        )
        self.assertTrue(
            all(item["passed"] for item in evaluation["economic_gates"])
        )
        self.assertEqual(
            evaluation["eligibility"]["profitability"],
            "INELIGIBLE_RESEARCH_PROXY_NOT_SYSTEM_PAPER",
        )

    def test_stress_failure_does_not_pass(self):
        evaluation = self.build(self.records(source_exit="100"))
        self.assertEqual(
            evaluation["status"],
            "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
        )
        stress = next(
            item
            for item in evaluation["economic_gates"]
            if item["gate_id"] == "STRESS_1_5X_TOTAL_NET_PNL"
        )
        self.assertFalse(stress["passed"])

    def test_leave_top_five_sample_shortage_is_inconclusive(self):
        evaluation = self.build(self.records(count=34))
        self.assertTrue(
            evaluation["confirmatory_statistics"][
                "all_sample_gates_pass"
            ]
        )
        self.assertFalse(
            evaluation["leave_top_5"]["statistics"][
                "all_sample_gates_pass"
            ]
        )
        self.assertEqual(
            evaluation["status"],
            "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        )

    def test_empty_time_blocks_and_zero_variance_are_inconclusive(self):
        observations = [
            {
                "entry_scheduled_for": (
                    "2026-07-30T12:00:00.000Z"
                ),
                "net_return": "0.01",
            }
            for _ in range(30)
        ]
        summary = _sample_statistics(
            observations, evaluation_plan=self.evaluation_plan
        )
        self.assertFalse(summary["all_sample_gates_pass"])
        self.assertIsNone(summary["metrics"]["effective_event_count"])
        self.assertEqual(
            summary["metrics"]["nonempty_fixed_time_block_count"], 1
        )
        path = _path_result([{"net_pnl_usdt": "-1100"}])
        self.assertFalse(path["equity_never_nonpositive"])
        stress = _stress_result(
            [{"entry_source_high": "100", "exit_source_low": "99"}]
        )
        self.assertLess(Decimal(stress["total_net_pnl_usdt"]), 0)

    def test_publication_is_owner_only_exact_and_idempotent(self):
        evaluation = self.build()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            first = publish_challenger_cohort_cumulative_evaluation(
                evaluation=evaluation, output_root=root
            )
            before = first.stat()
            body = first.read_bytes()
            for _ in range(100):
                self.assertEqual(
                    publish_challenger_cohort_cumulative_evaluation(
                        evaluation=evaluation, output_root=root
                    ),
                    first,
                )
            after = first.stat()
            self.assertEqual(body, canonical_json(evaluation).encode())
            self.assertEqual(before.st_ino, after.st_ino)
            self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(first.parent.stat().st_mode), 0o700)
            self.assertEqual(
                load_challenger_cohort_cumulative_evaluation(
                    evaluation_path=first
                ),
                evaluation,
            )

    def test_rehash_cannot_hide_calculation_tamper(self):
        evaluation = self.build()
        changed = copy.deepcopy(evaluation)
        changed["path"]["ending_equity_usdt"] = "999999"
        changed["evaluation_hash"] = (
            challenger_cohort_cumulative_evaluation_hash(changed)
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ChallengerCohortCumulativeEvaluationError,
                "CHALLENGER_COHORT_CUMULATIVE_RESULT_INVALID",
            ):
                publish_challenger_cohort_cumulative_evaluation(
                    evaluation=changed,
                    output_root=Path(directory) / "output",
                )

    def test_v047_inventory_is_replayed_and_missing_result_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root, archive_root, result_root = (
                self.economic_fixture(base)
            )
            arguments = {
                "cohort_plan_path": COHORT_PLAN_PATH,
                "economic_plan_path": ECONOMIC_PLAN_PATH,
                "episode_receipt_output_root": receipt_root,
                "install_receipt_path": Path("/unused/install.json"),
                "contract_path": Path("/unused/contract.json"),
                "plist_path": Path("/unused/agent.plist"),
                "archive_output_root": archive_root,
                "result_output_root": result_root,
                "receipt_loader": fixture_loader,
            }
            inventory = load_complete_economic_inventory(**arguments)
            self.assertEqual(len(inventory["result_records"]), 1)
            self.assertEqual(inventory["latest_index"]["entry_count"], 1)
            result_path = next(
                (result_root / "challenger-cohort-economic-results").iterdir()
            )
            result_path.unlink()
            with self.assertRaisesRegex(
                ChallengerCohortCumulativeEvaluationError,
                "CHALLENGER_COHORT_CUMULATIVE_RESULT_MISSING",
            ):
                load_complete_economic_inventory(**arguments)

    def test_cli_has_only_frozen_authority_and_fails_structured(self):
        destinations = {
            action.dest for action in _parser()._actions
        }
        self.assertNotIn("episode_id", destinations)
        self.assertNotIn("clock", destinations)
        self.assertNotIn("pnl", destinations)
        self.assertNotIn("seed", destinations)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ("receipts", "archives", "results", "evaluation"):
                path = base / name
                path.mkdir(mode=0o700)
            captured = {}

            def evaluator(**kwargs):
                captured.update(kwargs)
                return {"status": "COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS"}

            arguments = [
                "--cohort-plan-path",
                str(COHORT_PLAN_PATH),
                "--evaluation-plan-path",
                str(EVALUATION_PLAN_PATH),
                "--economic-plan-path",
                str(ECONOMIC_PLAN_PATH),
                "--pilot-result-path",
                str(PILOT_PATH),
                "--install-receipt-path",
                str(base / "install.json"),
                "--contract-path",
                str(base / "contract.json"),
                "--plist-path",
                str(base / "agent.plist"),
                "--episode-receipt-output-root",
                str(base / "receipts"),
                "--archive-output-root",
                str(base / "archives"),
                "--result-output-root",
                str(base / "results"),
                "--evaluation-output-root",
                str(base / "evaluation"),
            ]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli_main(
                    arguments,
                    allowed_output_base=base,
                    evaluator=evaluator,
                )
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(stdout.getvalue())["status"],
                "COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS",
            )
            self.assertEqual(set(captured), {
                "cohort_plan_path",
                "evaluation_plan_path",
                "economic_plan_path",
                "pilot_result_path",
                "install_receipt_path",
                "contract_path",
                "plist_path",
                "episode_receipt_output_root",
                "archive_output_root",
                "result_output_root",
                "evaluation_output_root",
            })

    def test_mismatched_episode_set_fails_closed(self):
        records = self.records(count=1)
        with self.assertRaisesRegex(
            ChallengerCohortCumulativeEvaluationError,
            "CHALLENGER_COHORT_CUMULATIVE_EPISODE_SET_INVALID",
        ):
            build_challenger_cohort_cumulative_evaluation(
                cohort_plan=self.cohort_plan,
                cohort_plan_file_sha256=self.cohort_sha,
                evaluation_plan=self.evaluation_plan,
                evaluation_plan_file_sha256=self.evaluation_sha,
                economic_binding=self.economic_binding,
                pilot=self.pilot,
                pilot_file_sha256=self.pilot_sha,
                continuity=self.continuity(("wrong_episode",)),
                inventory=self.inventory(records),
            )
