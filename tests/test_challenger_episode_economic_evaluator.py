import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import (
    business_hash,
    canonical_json,
    stable_id,
    utc_datetime,
)
from crypto_quant.challenger_episode_economic_evaluator import (
    ChallengerEpisodeEconomicEvaluatorError,
    build_challenger_episode_economic_result,
    challenger_episode_economic_result_hash,
    challenger_episode_economic_result_reasons,
    load_challenger_episode_economic_result,
    publish_challenger_episode_economic_result,
    required_challenger_episode_archive_periods,
)
from crypto_quant.challenger_first_episode_receipt import (
    _identity as completion_identity,
    challenger_first_episode_receipt_hash,
)
from crypto_quant.challenger_forward import (
    build_challenger_forward_decision,
)
from crypto_quant.market_data import HistoricalArchiveRequest


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-economic-plan-v0.37.0.json"
)
FIRST_SLOT_PATH = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-first-slot-receipt-v0.35.0.json"
)
PLAN_FILE_SHA256 = (
    "f22cb582a7df38e14220fca75359f6290af2fdb5896e5829ba5d7fd805cf54da"
)
START = datetime(2026, 7, 29, tzinfo=timezone.utc)


def file_stat(seed):
    return {
        "device": 1,
        "inode": seed,
        "owner_uid": 501,
        "mode_octal": "0600",
        "link_count": 1,
        "size_bytes": 1,
        "sha256": hashlib.sha256(str(seed).encode()).hexdigest(),
    }


def next_row(previous, scheduled, recorded, close):
    prior_close = previous["close"]
    low = min(Decimal(prior_close), Decimal(close)) - Decimal("1")
    high = max(Decimal(prior_close), Decimal(close)) + Decimal("1")
    row = {
        **previous,
        "open_time": utc_datetime(scheduled - timedelta(hours=4)),
        "close_time": utc_datetime(scheduled - timedelta(milliseconds=1)),
        "available_at": utc_datetime(recorded - timedelta(milliseconds=1)),
        "open": prior_close,
        "high": format(high, "f"),
        "low": format(low, "f"),
        "close": close,
    }
    row["source_row_hash"] = business_hash(
        {key: value for key, value in row.items() if key != "source_row_hash"}
    )
    return row


def episode_decisions(*, vertical=False):
    first_slot = json.loads(FIRST_SLOT_PATH.read_text(encoding="utf-8"))
    decisions = [first_slot["state"]["first_decision"]]
    hours = (4, 8, 12, 16, 20, 24) if vertical else (4, 8)
    for index, hour in enumerate(hours):
        scheduled = START + timedelta(hours=hour)
        recorded = scheduled + timedelta(minutes=2, seconds=6, milliseconds=752)
        if vertical:
            close = str(1930 + index * 10)
        else:
            close = "1930" if hour == 4 else "1800"
        previous = decisions[-1]
        row = next_row(
            previous["input_klines"][-1],
            scheduled,
            recorded,
            close,
        )
        decisions.append(
            build_challenger_forward_decision(
                klines=previous["input_klines"][1:] + [row],
                scheduled_for=utc_datetime(scheduled),
                recorded_at=utc_datetime(recorded),
                previous_decision=previous,
            )
        )
    expected = (
        "EXIT_LONG_VERTICAL_24H" if vertical else "EXIT_LONG_SMA20"
    )
    assert decisions[-1]["action"] == expected
    return decisions


def completion_receipt(*, vertical=False):
    decisions = episode_decisions(vertical=vertical)
    first = decisions[0]
    last = decisions[-1]
    bundles = []
    matches = []
    for index, decision in enumerate(decisions, 1):
        bundles.append(
            {
                "sequence": index,
                "scheduled_for": decision["scheduled_for"],
                "path": f"/owner/bundle-{index}.json",
                "file_stat": file_stat(index),
                "bundle_id": (
                    "challenger_forward_source_bundle_"
                    + hashlib.sha256(f"bundle-{index}".encode()).hexdigest()
                ),
                "bundle_hash": hashlib.sha256(
                    f"bundle-hash-{index}".encode()
                ).hexdigest(),
                "decision_id": decision["decision_id"],
                "decision_hash": decision["decision_hash"],
            }
        )
        record = {"status": "RECORDED", "sequence": index}
        matches.append(
            {
                "sequence": index,
                "line_number": index,
                "record": record,
                "record_hash": hashlib.sha256(
                    canonical_json(record).encode()
                ).hexdigest(),
            }
        )
    observed = datetime.fromisoformat(
        last["recorded_at"].replace("Z", "+00:00")
    ) + timedelta(minutes=1)
    receipt = {
        "$schema": "./challenger-first-episode-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_first_episode_receipt_" + "0" * 64,
        "receipt_hash": "0" * 64,
        "observed_at": utc_datetime(observed),
        "forward_start": "2026-07-29T00:00:00.000Z",
        "minimum_hold_until": "2026-07-29T08:00:00.000Z",
        "vertical_exit_at": "2026-07-30T00:00:00.000Z",
        "install_receipt": {
            "receipt_id": "challenger_launchd_install_receipt_" + "1" * 64,
            "receipt_hash": "2" * 64,
            "target_path": "/owner/runner",
            "target_sha256": "3" * 64,
            "execution_snapshot": {"version": "fixture"},
        },
        "contract": {
            "contract_id": "challenger_launchd_contract_" + "4" * 64,
            "contract_hash": "5" * 64,
            "contract_trust_hash": "6" * 64,
            "launchd_plist_sha256": "7" * 64,
        },
        "launchctl_print": {"command_evidence_hash": "8" * 64},
        "launchd_runs_observed": len(decisions),
        "state": {
            "path": "/owner/state.sqlite3",
            "observed_file_stat": file_stat(100),
            "metadata": {
                "policy_hash": first["policy_hash"],
                "registration_hash": first["hypothesis_registration_hash"],
            },
            "total_decision_count_observed": len(decisions),
            "observed_decisions_root_hash": business_hash(decisions),
            "observed_state_chain_end_hash": last["decision_hash"],
            "episode_decision_count": len(decisions),
            "decisions": decisions,
            "decisions_root_hash": business_hash(decisions),
            "decision_chain_end_hash": last["decision_hash"],
        },
        "episode": {
            "episode_id": first["state_after"]["episode_id_or_null"],
            "entry_scheduled_for": first["scheduled_for"],
            "minimum_hold_until": "2026-07-29T08:00:00.000Z",
            "vertical_exit_at": "2026-07-30T00:00:00.000Z",
            "exit_scheduled_for": last["scheduled_for"],
            "exit_action": last["action"],
        },
        "source_bundles": bundles,
        "logs": {
            "stdout": {
                "path": "/owner/stdout.log",
                "observed_prefix_stat": file_stat(101),
                "matched_records": matches,
            },
            "stderr": {
                "path": "/owner/stderr.log",
                "observed_prefix_stat": file_stat(102),
                "empty": True,
            },
        },
        "observation_status": "FIRST_EPISODE_COMPLETED_VERIFIED",
        "security_boundary": {
            "launchctl_print_count": 1,
            "network_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
        },
        "eligibility": {
            "forward_evidence": "LOCAL_PREQUENTIAL_RESEARCH_ONLY",
            "external_time_anchor": "INELIGIBLE_LOCAL_ONLY",
            "paper": "INELIGIBLE_SINGLE_EPISODE",
            "release_oos": "INELIGIBLE_FORWARD_COLLECTION_ONLY",
            "profitability": "INELIGIBLE",
        },
        "warnings": [
            "BINANCE_TIME_RECEIPT_IS_NOT_INDEPENDENT_PUBLICATION",
            "NO_HISTORICAL_BACKFILL",
            "NO_EXECUTION_OR_COST_MODEL_BOUND",
            "SINGLE_EPISODE_CANNOT_ESTABLISH_EDGE",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    receipt["receipt_id"] = stable_id(
        "challenger_first_episode_receipt", completion_identity(receipt)
    )
    receipt["receipt_hash"] = challenger_first_episode_receipt_hash(receipt)
    body = canonical_json(receipt).encode()
    return receipt, hashlib.sha256(body).hexdigest()


def daily_archive(period, *, selected_prices=None, row_count=1440):
    request = HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="DAILY",
        period=period,
    )
    start = datetime.strptime(period, "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    selected_prices = selected_prices or {}
    rows = []
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for index in range(row_count):
        opened = start + timedelta(minutes=index)
        closed = opened + timedelta(minutes=1, microseconds=-1)
        high, low = selected_prices.get(
            utc_datetime(opened), ("2000", "1990")
        )
        opened_value = low
        closed_value = low
        open_raw = int((opened - epoch) / timedelta(microseconds=1))
        close_raw = int((closed - epoch) / timedelta(microseconds=1))
        rows.append(
            ",".join(
                (
                    str(open_raw),
                    opened_value,
                    high,
                    low,
                    closed_value,
                    "10",
                    str(close_raw),
                    "100",
                    "1",
                    "5",
                    "50",
                    "0",
                )
            )
        )
    csv_bytes = ("\n".join(rows) + "\n").encode("ascii")
    output = BytesIO()
    info = zipfile.ZipInfo(
        request.expected_csv_name, date_time=(2026, 7, 29, 0, 0, 0)
    )
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(info, csv_bytes)
    archive_bytes = output.getvalue()
    checksum = (
        f"{hashlib.sha256(archive_bytes).hexdigest()}"
        f"  {request.archive_filename}\n"
    ).encode()
    return archive_bytes, checksum


class ChallengerEpisodeEconomicEvaluatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.receipt, cls.receipt_sha = completion_receipt()
        cls.entry_minute = "2026-07-29T00:03:00.000Z"
        cls.exit_minute = "2026-07-29T08:03:00.000Z"
        archive, checksum = daily_archive(
            "2026-07-29",
            selected_prices={
                cls.entry_minute: ("2000.01", "1999"),
                cls.exit_minute: ("2101", "2100.01"),
            },
        )
        cls.archives = {
            "2026-07-29": (
                archive,
                checksum,
                "2026-07-30T00:05:00.000Z",
            )
        }

    def build(self, **overrides):
        arguments = {
            "plan": self.plan,
            "plan_file_sha256": PLAN_FILE_SHA256,
            "completion_receipt": self.receipt,
            "completion_receipt_file_sha256": self.receipt_sha,
            "daily_archives": self.archives,
            "evaluated_at": "2026-07-30T00:06:00.000Z",
        }
        arguments.update(overrides)
        return build_challenger_episode_economic_result(**arguments)

    def test_schema_mirrors_are_valid_and_identical(self):
        config = (
            ROOT
            / "config"
            / "challenger-episode-economic-result-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-episode-economic-result-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_text()))

    def test_same_day_result_is_deterministic_costed_and_ineligible(self):
        result = self.build()
        self.assertEqual(
            required_challenger_episode_archive_periods(
                plan=self.plan,
                plan_file_sha256=PLAN_FILE_SHA256,
                completion_receipt=self.receipt,
                completion_receipt_file_sha256=self.receipt_sha,
            ),
            ("2026-07-29",),
        )
        self.assertEqual(result["economics"]["entry_fill_price"], "2002.02")
        self.assertEqual(result["economics"]["exit_fill_price"], "2097.9")
        self.assertEqual(result["economics"]["filled_quantity_eth"], "0.4994")
        self.assertEqual(result["economics"]["positive_label"], 1)
        self.assertGreater(Decimal(result["economics"]["net_return"]), 0)
        self.assertEqual(
            result["status"], "COMPLETED_ARCHIVE_FORWARD_ECONOMIC_PROXY"
        )
        self.assertEqual(result["security_boundary"]["market_request_count"], 0)
        self.assertEqual(
            result["eligibility"]["profitability"],
            "INELIGIBLE_SINGLE_EPISODE",
        )
        self.assertEqual(
            result["result_hash"],
            challenger_episode_economic_result_hash(result),
        )
        self.assertFalse(
            challenger_episode_economic_result_reasons(
                result,
                plan=self.plan,
                plan_file_sha256=PLAN_FILE_SHA256,
                completion_receipt=self.receipt,
                completion_receipt_file_sha256=self.receipt_sha,
                daily_archives=self.archives,
            )
        )

    def test_negative_result_is_not_positive(self):
        archive, checksum = daily_archive(
            "2026-07-29",
            selected_prices={
                self.entry_minute: ("2000.01", "1999"),
                self.exit_minute: ("1901", "1900.01"),
            },
        )
        result = self.build(
            daily_archives={
                "2026-07-29": (
                    archive,
                    checksum,
                    "2026-07-30T00:05:00.000Z",
                )
            }
        )
        self.assertEqual(result["economics"]["positive_label"], 0)
        self.assertLess(Decimal(result["economics"]["net_pnl_usdt"]), 0)

    def test_vertical_exit_requires_exact_two_day_archive_set(self):
        receipt, receipt_sha = completion_receipt(vertical=True)
        periods = required_challenger_episode_archive_periods(
            plan=self.plan,
            plan_file_sha256=PLAN_FILE_SHA256,
            completion_receipt=receipt,
            completion_receipt_file_sha256=receipt_sha,
        )
        self.assertEqual(periods, ("2026-07-29", "2026-07-30"))
        entry_archive, entry_checksum = daily_archive(
            "2026-07-29",
            selected_prices={self.entry_minute: ("2000", "1990")},
        )
        exit_minute = "2026-07-30T00:03:00.000Z"
        exit_archive, exit_checksum = daily_archive(
            "2026-07-30",
            selected_prices={exit_minute: ("2200", "2190")},
        )
        result = self.build(
            completion_receipt=receipt,
            completion_receipt_file_sha256=receipt_sha,
            daily_archives={
                "2026-07-29": (
                    entry_archive,
                    entry_checksum,
                    "2026-07-30T00:05:00.000Z",
                ),
                "2026-07-30": (
                    exit_archive,
                    exit_checksum,
                    "2026-07-31T00:05:00.000Z",
                ),
            },
            evaluated_at="2026-07-31T00:06:00.000Z",
        )
        self.assertEqual(len(result["source_archives"]), 2)
        self.assertEqual(
            result["episode"]["exit_action"], "EXIT_LONG_VERTICAL_24H"
        )

    def test_plan_receipt_and_archive_set_fail_closed(self):
        cases = (
            {
                "plan_file_sha256": "0" * 64,
            },
            {
                "completion_receipt_file_sha256": "not-a-hash",
            },
            {
                "daily_archives": {},
            },
        )
        for override in cases:
            with self.subTest(override=override):
                with self.assertRaises(ChallengerEpisodeEconomicEvaluatorError):
                    self.build(**override)
        mutated = copy.deepcopy(self.receipt)
        mutated["state"]["decisions"][-1]["recorded_at"] = (
            "2026-07-29T08:03:06.752Z"
        )
        mutated["receipt_id"] = stable_id(
            "challenger_first_episode_receipt",
            completion_identity(mutated),
        )
        mutated["receipt_hash"] = challenger_first_episode_receipt_hash(mutated)
        with self.assertRaisesRegex(
            ChallengerEpisodeEconomicEvaluatorError,
            "RECEIPT_INVALID",
        ):
            self.build(completion_receipt=mutated)

    def test_checksum_coverage_and_time_fail_closed(self):
        archive, checksum, retrieved = self.archives["2026-07-29"]
        bad_inputs = (
            (archive, checksum[:-1] + b"x", retrieved),
            (
                *daily_archive("2026-07-29", row_count=1439),
                retrieved,
            ),
            (archive, checksum, "2026-07-29T23:59:59.000Z"),
        )
        for value in bad_inputs:
            with self.subTest(value=len(value[0])):
                with self.assertRaises(
                    ChallengerEpisodeEconomicEvaluatorError
                ):
                    self.build(daily_archives={"2026-07-29": value})
        with self.assertRaisesRegex(
            ChallengerEpisodeEconomicEvaluatorError,
            "TIME_INVALID",
        ):
            self.build(evaluated_at="2026-07-30T00:04:00.000Z")

    def test_coordinated_result_mutation_is_rejected_by_replay(self):
        result = self.build()
        mutated = copy.deepcopy(result)
        mutated["economics"]["net_pnl_usdt"] = "999"
        mutated["result_id"] = stable_id(
            "challenger_episode_economic_result",
            {
                "plan_hash": mutated["plan_binding"]["plan_hash"],
                "completion_receipt_hash": mutated["completion_receipt"][
                    "receipt_hash"
                ],
                "entry_source_row_hash": mutated["execution_proxy"][
                    "entry_source_row_hash"
                ],
                "exit_source_row_hash": mutated["execution_proxy"][
                    "exit_source_row_hash"
                ],
                "economic_policy_hash": mutated["economic_policy_hash"],
                "evaluated_at": mutated["evaluated_at"],
            },
        )
        mutated["result_hash"] = challenger_episode_economic_result_hash(
            mutated
        )
        reasons = challenger_episode_economic_result_reasons(
            mutated,
            plan=self.plan,
            plan_file_sha256=PLAN_FILE_SHA256,
            completion_receipt=self.receipt,
            completion_receipt_file_sha256=self.receipt_sha,
            daily_archives=self.archives,
        )
        self.assertIn(
            "CHALLENGER_EPISODE_ECONOMIC_RESULT_SEMANTIC_MISMATCH",
            reasons,
        )

    def test_exact_publisher_loader_and_conflict(self):
        result = self.build()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            arguments = {
                "result": result,
                "plan": self.plan,
                "plan_file_sha256": PLAN_FILE_SHA256,
                "completion_receipt": self.receipt,
                "completion_receipt_file_sha256": self.receipt_sha,
                "daily_archives": self.archives,
            }
            publish_challenger_episode_economic_result(
                **arguments, output_path=path
            )
            self.assertEqual(
                path.read_bytes(), canonical_json(result).encode()
            )
            loaded = load_challenger_episode_economic_result(
                result_path=path, **{k: v for k, v in arguments.items() if k != "result"}
            )
            self.assertEqual(loaded, result)
            path.write_bytes(b"{}")
            path.chmod(0o600)
            with self.assertRaises(
                ChallengerEpisodeEconomicEvaluatorError
            ):
                publish_challenger_episode_economic_result(
                    **arguments, output_path=path
                )


if __name__ == "__main__":
    unittest.main()
