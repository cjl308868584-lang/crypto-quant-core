import copy
import hashlib
import io
import json
import shutil
import stat
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_cohort_episode_receipt import (
    ChallengerCohortEpisodeReceiptError,
    _partition,
    challenger_cohort_episode_receipt_hash,
    load_challenger_cohort_episode_receipt,
    observe_challenger_cohort_episodes,
)
from crypto_quant.challenger_cohort_episode_receipt_cli import (
    main as observer_main,
)
from crypto_quant.challenger_forward_runner import (
    run_challenger_forward_cycle,
)
from tests import test_challenger_first_slot_receipt as first_slot_tests
from tests.test_challenger_first_episode_receipt import (
    ChallengerFirstEpisodeReceiptTests,
)
from tests.test_challenger_forward_runner import (
    KlineTransport,
    gate_at,
    raw_window,
)


ROOT = Path(__file__).resolve().parents[1]
GENESIS = datetime(2026, 7, 29, tzinfo=timezone.utc)
COHORT_START = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
PLAN = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-cohort-plan-v0.43.0.json"
)
PLAN_SHA = (
    "a431fe2d316d8c9a647a4c45de280644"
    "e60554719603b5506670cef8a02ee7ff"
)
PILOT_AND_REJECTIONS = [102, 103, 99, 99, 99, 99, 99, 99, 99]
ONE_COHORT_EPISODE = PILOT_AND_REJECTIONS + [105, 106, 90]
TWO_COHORT_EPISODES = ONE_COHORT_EPISODE + [
    90,
    90,
    110,
    111,
    80,
]


class ChallengerCohortEpisodeReceiptTests(unittest.TestCase):
    @staticmethod
    def synthetic_decision(index, action, before, after):
        scheduled = COHORT_START + timedelta(hours=4 * index)
        return {
            "sequence": index + 10,
            "scheduled_for": scheduled.strftime(
                "%Y-%m-%dT%H:%M:%S.000Z"
            ),
            "recorded_at": (
                scheduled + timedelta(minutes=2)
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "action": action,
            "state_before": before,
            "state_after": after,
        }

    @staticmethod
    def flat():
        return {
            "position_state": "FLAT",
            "episode_id_or_null": None,
            "entry_decision_time_or_null": None,
            "minimum_hold_until_or_null": None,
            "vertical_exit_at_or_null": None,
        }

    def environment(self, root: Path):
        helper = first_slot_tests.ChallengerFirstSlotReceiptTests()
        environment = helper.environment(root)
        environment["receipt_output_root"] = root / "cohort-receipts"
        environment["cohort_plan_path"] = root / "cohort-plan.json"
        shutil.copy2(PLAN, environment["cohort_plan_path"])
        return environment

    def record(self, environment, closes):
        helper = ChallengerFirstEpisodeReceiptTests()
        return helper.record(environment, [100] * 20 + list(closes))

    def observe(self, environment, clock):
        return observe_challenger_cohort_episodes(
            cohort_plan_path=environment["cohort_plan_path"],
            install_receipt_path=environment[
                "install_receipt_path"
            ],
            contract_path=environment["contract_path"],
            plist_path=environment["plist_path"],
            receipt_output_root=environment["receipt_output_root"],
            clock=lambda: clock,
            _launchctl_runner=environment["service"],
        )

    def load(self, environment, receipt_path):
        return load_challenger_cohort_episode_receipt(
            receipt_path=receipt_path,
            cohort_plan_path=environment["cohort_plan_path"],
            install_receipt_path=environment[
                "install_receipt_path"
            ],
            contract_path=environment["contract_path"],
            plist_path=environment["plist_path"],
        )

    def test_plan_is_exact_and_prestart_is_read_only(self):
        self.assertEqual(hashlib.sha256(PLAN.read_bytes()).hexdigest(), PLAN_SHA)
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.record(environment, PILOT_AND_REJECTIONS)
            before = environment["paths"]["state"].read_bytes()
            result = self.observe(
                environment, COHORT_START - timedelta(minutes=1)
            )
            self.assertEqual(result["status"], "COHORT_NOT_STARTED_VERIFIED")
            self.assertEqual(result["cohort_slot_count"], 0)
            self.assertEqual(result["receipt_created_count"], 0)
            self.assertEqual(result["network_request_count"], 0)
            self.assertEqual(result["state_write_count"], 0)
            self.assertEqual(
                before, environment["paths"]["state"].read_bytes()
            )

    def test_rejected_slot_and_active_episode_publish_no_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rejected = self.environment(root / "rejected")
            self.record(rejected, PILOT_AND_REJECTIONS + [99])
            result = self.observe(
                rejected, COHORT_START + timedelta(minutes=2)
            )
            self.assertEqual(
                result["status"], "COHORT_CONTINUITY_COLLECTING_VERIFIED"
            )
            self.assertEqual(result["cohort_slot_count"], 1)
            self.assertEqual(result["completed_episode_count"], 0)
            self.assertEqual(result["receipts"], [])

            active = self.environment(root / "active")
            self.record(active, PILOT_AND_REJECTIONS + [105])
            result = self.observe(
                active, COHORT_START + timedelta(minutes=2)
            )
            self.assertEqual(
                result["status"], "COHORT_EPISODE_IN_PROGRESS_VERIFIED"
            )
            self.assertEqual(result["completed_episode_count"], 0)
            self.assertIsNotNone(result["active_episode_id_or_null"])
            self.assertEqual(result["receipt_created_count"], 0)

    def test_completed_episode_is_canonical_loadable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.record(environment, ONE_COHORT_EPISODE)
            clock = COHORT_START + timedelta(hours=8, minutes=2)
            first = self.observe(environment, clock)
            self.assertEqual(first["completed_episode_count"], 1)
            self.assertEqual(first["receipt_created_count"], 1)
            path = Path(first["receipts"][0]["receipt_path"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            receipt = self.load(environment, path)
            self.assertEqual(
                receipt["observation_status"],
                "COHORT_EPISODE_COMPLETED_VERIFIED",
            )
            self.assertEqual(receipt["episode"]["ordinal"], 1)
            self.assertEqual(receipt["episode"]["decision_count"], 3)
            self.assertEqual(
                receipt["state"]["cohort_prefix_slot_count"], 3
            )
            self.assertEqual(
                path.read_bytes(), canonical_json(receipt).encode("utf-8")
            )
            expected_id = receipt["receipt_id"]
            expected_hash = receipt["receipt_hash"]
            for _ in range(100):
                self.assertEqual(receipt["receipt_id"], expected_id)
                self.assertEqual(
                    challenger_cohort_episode_receipt_hash(receipt),
                    expected_hash,
                )
            second = self.observe(
                environment, clock + timedelta(minutes=1)
            )
            self.assertEqual(second["receipt_created_count"], 0)
            self.assertEqual(
                second["receipts"][0]["receipt_id"],
                first["receipts"][0]["receipt_id"],
            )
            self.assertEqual(
                second["receipts"][0]["receipt_hash"],
                first["receipts"][0]["receipt_hash"],
            )

    def test_output_root_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.environment(root / "environment")
            self.record(environment, ONE_COHORT_EPISODE)
            target = root / "target"
            target.mkdir(mode=0o700)
            link = root / "receipt-link"
            link.symlink_to(target, target_is_directory=True)
            environment["receipt_output_root"] = link
            with self.assertRaisesRegex(
                ChallengerCohortEpisodeReceiptError,
                "CHALLENGER_COHORT_EPISODE_OUTPUT_INVALID",
            ):
                self.observe(
                    environment,
                    COHORT_START + timedelta(hours=8, minutes=2),
                )

    def test_all_completed_episodes_are_published_without_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.record(environment, TWO_COHORT_EPISODES)
            result = self.observe(
                environment, COHORT_START + timedelta(hours=28, minutes=2)
            )
            self.assertEqual(result["completed_episode_count"], 2)
            self.assertEqual(result["receipt_created_count"], 2)
            self.assertEqual(
                [item["ordinal"] for item in result["receipts"]], [1, 2]
            )
            receipts = [
                self.load(environment, Path(item["receipt_path"]))
                for item in result["receipts"]
            ]
            self.assertEqual(
                receipts[0]["prior_completed_episodes"]["episode_ids"], []
            )
            self.assertEqual(
                receipts[1]["prior_completed_episodes"]["episode_ids"],
                [receipts[0]["episode"]["episode_id"]],
            )
            self.assertEqual(
                receipts[1]["state"]["cohort_prefix_slot_count"], 8
            )
            actions = [
                slot["action"]
                for slot in receipts[1]["state"]["cohort_prefix_slots"]
            ]
            self.assertEqual(
                actions,
                [
                    "ENTER_LONG",
                    "HOLD_LONG_MINIMUM",
                    "EXIT_LONG_SMA20",
                    "REJECT_ENTRY",
                    "REJECT_ENTRY",
                    "ENTER_LONG",
                    "HOLD_LONG_MINIMUM",
                    "EXIT_LONG_SMA20",
                ],
            )

    def test_later_state_bundle_and_log_append_preserve_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.record(environment, ONE_COHORT_EPISODE)
            observed = self.observe(
                environment,
                COHORT_START + timedelta(hours=8, minutes=2),
            )
            receipt_path = Path(observed["receipts"][0]["receipt_path"])
            stdout = environment["paths"]["stdout"]
            original_log = stdout.read_bytes()
            slot = GENESIS + timedelta(hours=4 * len(ONE_COHORT_EPISODE))
            now = slot + timedelta(minutes=1)
            gate, _source = gate_at(now)
            full_stream = [100] * 20 + ONE_COHORT_EPISODE + [90]
            appended = run_challenger_forward_cycle(
                state_path=environment["paths"]["state"],
                output_root=environment["paths"]["output"],
                runtime_gate=gate,
                kline_transport=KlineTransport(
                    raw_window(
                        slot,
                        full_stream[len(ONE_COHORT_EPISODE) :],
                    ),
                    now,
                ),
            )
            stdout.write_bytes(
                original_log
                + (
                    json.dumps(
                        appended,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            )
            stdout.chmod(0o600)
            receipt = self.load(environment, receipt_path)
            self.assertEqual(receipt["episode"]["ordinal"], 1)
            self.assertEqual(
                receipt["state"]["cohort_prefix_slot_count"], 3
            )

    def test_missing_first_cohort_slot_fails_at_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.record(environment, PILOT_AND_REJECTIONS)
            with self.assertRaisesRegex(
                ChallengerCohortEpisodeReceiptError,
                "CHALLENGER_COHORT_EPISODE_SLOT_MISSED",
            ):
                self.observe(
                    environment, COHORT_START + timedelta(hours=4)
                )

    def test_window_end_tracks_last_entry_to_natural_vertical_exit(self):
        flat = self.flat()
        decisions = [
            self.synthetic_decision(
                index, "REJECT_ENTRY", flat, flat
            )
            for index in range(539)
        ]
        entry_time = COHORT_START + timedelta(hours=4 * 539)
        long_state = {
            "position_state": "LONG",
            "episode_id_or_null": "challenger_episode_" + "a" * 64,
            "entry_decision_time_or_null": entry_time.strftime(
                "%Y-%m-%dT%H:%M:%S.000Z"
            ),
            "minimum_hold_until_or_null": (
                entry_time + timedelta(hours=8)
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "vertical_exit_at_or_null": (
                entry_time + timedelta(hours=24)
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        decisions.append(
            self.synthetic_decision(
                539, "ENTER_LONG", flat, long_state
            )
        )
        decisions.extend(
            [
                self.synthetic_decision(
                    540, "HOLD_LONG_MINIMUM", long_state, long_state
                ),
                self.synthetic_decision(
                    541, "HOLD_LONG", long_state, long_state
                ),
                self.synthetic_decision(
                    542, "HOLD_LONG", long_state, long_state
                ),
                self.synthetic_decision(
                    543, "HOLD_LONG", long_state, long_state
                ),
                self.synthetic_decision(
                    544, "HOLD_LONG", long_state, long_state
                ),
                self.synthetic_decision(
                    545, "EXIT_LONG_VERTICAL_24H", long_state, flat
                ),
            ]
        )
        cohort, completed, active, next_required = _partition(
            decisions,
            observed=COHORT_START
            + timedelta(hours=4 * 545, minutes=2),
        )
        self.assertEqual(len(cohort), 546)
        self.assertEqual(completed, ((539, 545),))
        self.assertIsNone(active)
        self.assertIsNone(next_required)

    def test_internal_cohort_gap_fails_closed(self):
        flat = self.flat()
        decisions = [
            self.synthetic_decision(0, "REJECT_ENTRY", flat, flat),
            self.synthetic_decision(2, "REJECT_ENTRY", flat, flat),
        ]
        with self.assertRaisesRegex(
            ChallengerCohortEpisodeReceiptError,
            "CHALLENGER_COHORT_EPISODE_SLOT_MISSED",
        ):
            _partition(
                decisions,
                observed=COHORT_START + timedelta(hours=8, minutes=2),
            )

    def test_duplicate_bundle_and_log_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_environment = self.environment(root / "bundle")
            results = self.record(
                bundle_environment, PILOT_AND_REJECTIONS + [105]
            )
            source = Path(results[-1]["source_bundle_path"])
            duplicate = source.parent / "duplicate.json"
            shutil.copy2(source, duplicate)
            duplicate.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortEpisodeReceiptError,
                "CHALLENGER_COHORT_EPISODE_SOURCE_INVALID",
            ):
                self.observe(
                    bundle_environment,
                    COHORT_START + timedelta(minutes=2),
                )

            log_environment = self.environment(root / "log")
            self.record(
                log_environment, PILOT_AND_REJECTIONS + [105]
            )
            stdout = log_environment["paths"]["stdout"]
            stdout.write_bytes(stdout.read_bytes() * 2)
            stdout.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortEpisodeReceiptError,
                "CHALLENGER_COHORT_EPISODE_SOURCE_INVALID",
            ):
                self.observe(
                    log_environment,
                    COHORT_START + timedelta(minutes=2),
                )

    def test_rehash_cannot_hide_boundary_or_omission_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.environment(root)
            self.record(environment, TWO_COHORT_EPISODES)
            result = self.observe(
                environment, COHORT_START + timedelta(hours=28, minutes=2)
            )
            source = Path(result["receipts"][1]["receipt_path"])
            original = json.loads(source.read_text())
            variants = []
            boundary = copy.deepcopy(original)
            boundary["security_boundary"]["order_submission_count"] = 1
            variants.append(boundary)
            omission = copy.deepcopy(original)
            omission["prior_completed_episodes"]["episode_ids"] = []
            omission["prior_completed_episodes"]["count"] = 0
            variants.append(omission)
            for index, changed in enumerate(variants):
                changed["receipt_hash"] = (
                    challenger_cohort_episode_receipt_hash(changed)
                )
                path = root / f"tampered-{index}.json"
                path.write_bytes(canonical_json(changed).encode("utf-8"))
                path.chmod(0o600)
                with self.assertRaisesRegex(
                    ChallengerCohortEpisodeReceiptError,
                    "CHALLENGER_COHORT_EPISODE_RECEIPT_INVALID",
                ):
                    self.load(environment, path)

    def test_schema_mirror_and_cli_authority_are_strict(self):
        config = (
            ROOT
            / "config"
            / "challenger-cohort-episode-receipt-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-cohort-episode-receipt-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_bytes()))
        source = (
            ROOT
            / "src"
            / "crypto_quant"
            / "challenger_cohort_episode_receipt_cli.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "--episode",
            "--sequence",
            "--date",
            "--time",
            "--state",
            "--bundle",
            "--stdout",
            "--stderr",
            "--service",
            "--command",
            "--url",
            "--price",
            "--pnl",
            "--credential",
            "--order",
            "--clock",
        ):
            self.assertNotIn(forbidden, source)
            with self.subTest(forbidden=forbidden), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(observer_main([forbidden, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
