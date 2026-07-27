import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.market_data import HttpResponse
from crypto_quant.research_corpus import (
    HistoricalResearchCorpusState,
    ResearchCorpusError,
    build_default_research_corpus_plan,
    build_research_corpus_snapshot,
    load_research_corpus_snapshot,
    research_corpus_plan_hash,
    research_corpus_plan_reasons,
    research_corpus_snapshot_hash,
    research_corpus_snapshot_reasons,
    run_historical_research_corpus,
)


class TickClock:
    def __init__(self, start="2026-07-28T00:00:00.000Z"):
        self.current = datetime.fromisoformat(start.replace("Z", "+00:00"))

    def __call__(self):
        value = self.current.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        self.current += timedelta(seconds=1)
        return value


def monthly_spot_archive(period="2023-01", symbol="ETHUSDT"):
    start = datetime.strptime(period, "%Y-%m").replace(tzinfo=timezone.utc)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    rows = []
    cursor = start
    while cursor < end:
        opened = int(cursor.timestamp() * 1_000)
        rows.append(
            f"{opened},100,101,99,100.5,1,{opened + 14_399_999},"
            "100.5,1,0.5,50.25,0"
        )
        cursor += timedelta(hours=4)
    filename = f"{symbol}-4h-{period}.csv"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, ("\n".join(rows) + "\n").encode("ascii"))
    return output.getvalue()


class OneArchiveTransport:
    def __init__(self, period="2023-01", symbol="ETHUSDT"):
        self.archive = monthly_spot_archive(period, symbol)
        self.filename = f"{symbol}-4h-{period}.zip"
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if url.endswith(".CHECKSUM"):
            body = (
                f"{hashlib.sha256(self.archive).hexdigest()}"
                f"  {self.filename}\n"
            ).encode("ascii")
        else:
            body = self.archive
        return HttpResponse(
            status=200,
            final_url=url,
            headers={"Content-Length": str(len(body))},
            body=body,
        )


class FailingTransport:
    def __init__(self):
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        return HttpResponse(
            status=404,
            final_url=url,
            headers={"Content-Length": "0"},
            body=b"",
        )


class ResearchCorpusPlanTests(unittest.TestCase):
    def test_default_plan_freezes_42_months_8_folds_and_168_items(self):
        plan = build_default_research_corpus_plan()

        self.assertEqual(plan["months"][0], "2023-01")
        self.assertEqual(plan["months"][-1], "2026-06")
        self.assertEqual(len(plan["months"]), 42)
        self.assertEqual(len(plan["folds"]), 8)
        self.assertEqual(len(plan["items"]), 168)
        self.assertEqual(plan["summary"]["expected_physical_get_count"], 336)
        self.assertEqual(plan["plan_hash"], research_corpus_plan_hash(plan))
        self.assertEqual(research_corpus_plan_reasons(plan), ())
        self.assertEqual(
            plan["folds"][0]["training_window_start"],
            "2023-01-01T00:00:00.000Z",
        )
        self.assertEqual(
            plan["folds"][0]["oos_window_start"],
            "2024-07-01T00:00:00.000Z",
        )
        self.assertEqual(
            plan["folds"][-1]["oos_window_end_exclusive"],
            "2026-07-01T00:00:00.000Z",
        )
        self.assertEqual(
            plan["items"][0]["request"]["period_kind"],
            "MONTHLY",
        )

    def test_plan_rejects_rehashing_after_semantic_tamper(self):
        plan = build_default_research_corpus_plan()
        plan["items"][0]["month"] = "2023-02"
        plan["plan_hash"] = research_corpus_plan_hash(plan)

        self.assertIn(
            "CORPUS_PLAN_SEMANTIC_MISMATCH",
            research_corpus_plan_reasons(plan),
        )

    def test_plan_schema_mirror_is_exact(self):
        root = Path(__file__).parents[1]
        self.assertEqual(
            (
                root / "config/historical-research-corpus-plan-v1.schema.json"
            ).read_bytes(),
            (
                root
                / "src/crypto_quant/schemas/"
                "historical-research-corpus-plan-v1.schema.json"
            ).read_bytes(),
        )
        self.assertEqual(
            (
                root
                / "config/historical-research-corpus-snapshot-v1.schema.json"
            ).read_bytes(),
            (
                root
                / "src/crypto_quant/schemas/"
                "historical-research-corpus-snapshot-v1.schema.json"
            ).read_bytes(),
        )


class ResearchCorpusStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.plan = build_default_research_corpus_plan()
        self.state_path = self.root / "state/corpus.sqlite3"
        self.output_root = self.root / "output"

    def tearDown(self):
        self.temporary.cleanup()

    def test_empty_state_builds_fail_closed_coverage_snapshot(self):
        with HistoricalResearchCorpusState(
            self.state_path,
            plan=self.plan,
            output_root=self.output_root,
        ) as state:
            snapshot = build_research_corpus_snapshot(
                plan=self.plan,
                state=state,
                recorded_at="2026-07-28T00:00:00.000Z",
            )

        self.assertEqual(snapshot["summary"]["pending_item_count"], 168)
        self.assertEqual(snapshot["summary"]["succeeded_item_count"], 0)
        self.assertEqual(
            snapshot["research_training_readiness"],
            "NOT_READY_INCOMPLETE_OR_INVALID",
        )
        self.assertEqual(
            snapshot["formal_pit_eligibility"],
            "INELIGIBLE_ARCHIVE_REPLAY",
        )
        self.assertEqual(
            snapshot["snapshot_hash"],
            research_corpus_snapshot_hash(snapshot),
        )
        self.assertEqual(
            research_corpus_snapshot_reasons(snapshot, plan=self.plan),
            (),
        )
        self.assertEqual(os.stat(self.state_path).st_mode & 0o777, 0o600)

    def test_one_item_run_persists_exact_source_and_publishes_mode_600(self):
        transport = OneArchiveTransport()
        snapshot = run_historical_research_corpus(
            plan=self.plan,
            state_path=self.state_path,
            output_root=self.output_root,
            worker_id="worker-a",
            max_items=1,
            transport=transport,
            clock=TickClock(),
        )

        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(snapshot["summary"]["succeeded_item_count"], 1)
        self.assertEqual(snapshot["summary"]["physical_get_count"], 2)
        source_path = self.output_root / "source/ETH_SPOT_4H/2023-01.json"
        self.assertTrue(source_path.is_file())
        self.assertEqual(os.stat(source_path).st_mode & 0o777, 0o600)
        source = json.loads(source_path.read_text(encoding="utf-8"))
        self.assertEqual(source["request"], self.plan["items"][0]["request"])
        published = (
            self.output_root
            / "snapshots"
            / f"{snapshot['snapshot_id']}.json"
        )
        self.assertEqual(
            published.read_bytes(),
            canonical_json(snapshot).encode("utf-8"),
        )
        self.assertEqual(os.stat(published).st_mode & 0o777, 0o600)

    def test_recovery_does_not_refetch_successful_first_item(self):
        first = OneArchiveTransport()
        run_historical_research_corpus(
            plan=self.plan,
            state_path=self.state_path,
            output_root=self.output_root,
            worker_id="worker-a",
            max_items=1,
            transport=first,
            clock=TickClock(),
        )
        failing = FailingTransport()
        result = run_historical_research_corpus(
            plan=self.plan,
            state_path=self.state_path,
            output_root=self.output_root,
            worker_id="worker-b",
            max_items=1,
            transport=failing,
            clock=TickClock("2026-07-28T01:00:00.000Z"),
        )

        self.assertEqual(len(failing.calls), 1)
        self.assertIn("BTCUSDT", failing.calls[0])
        self.assertNotIn("ETHUSDT", failing.calls[0])
        self.assertEqual(result["summary"]["succeeded_item_count"], 1)
        self.assertEqual(result["summary"]["failed_item_count"], 1)
        self.assertEqual(result["summary"]["physical_get_count"], 3)

    def test_one_run_attempts_each_failed_item_at_most_once(self):
        failing = FailingTransport()
        result = run_historical_research_corpus(
            plan=self.plan,
            state_path=self.state_path,
            output_root=self.output_root,
            worker_id="worker-a",
            max_items=2,
            transport=failing,
            clock=TickClock(),
        )

        self.assertEqual(len(failing.calls), 2)
        self.assertIn("ETHUSDT", failing.calls[0])
        self.assertIn("BTCUSDT", failing.calls[1])
        self.assertEqual(result["summary"]["failed_item_count"], 2)
        self.assertEqual(
            result["items"][0]["attempt_count"],
            1,
        )
        self.assertEqual(
            result["items"][1]["attempt_count"],
            1,
        )

    def test_active_claim_is_not_stolen_and_expired_claim_is_recovered(self):
        with HistoricalResearchCorpusState(
            self.state_path,
            plan=self.plan,
            output_root=self.output_root,
        ) as state:
            first = state.claim_next(
                worker_id="worker-a",
                recorded_at="2026-07-28T00:00:00.000Z",
            )
            second = state.claim_next(
                worker_id="worker-b",
                recorded_at="2026-07-28T00:01:00.000Z",
            )
            recovered = state.claim_next(
                worker_id="worker-c",
                recorded_at="2026-07-28T00:15:00.000Z",
            )

        self.assertNotEqual(
            first["corpus_item_id"],
            second["corpus_item_id"],
        )
        self.assertEqual(
            recovered["corpus_item_id"],
            first["corpus_item_id"],
        )

    def test_state_rejects_output_binding_change(self):
        with HistoricalResearchCorpusState(
            self.state_path,
            plan=self.plan,
            output_root=self.output_root,
        ):
            pass

        with self.assertRaises(ResearchCorpusError) as raised:
            HistoricalResearchCorpusState(
                self.state_path,
                plan=self.plan,
                output_root=self.root / "other-output",
            )
        self.assertEqual(
            raised.exception.reason_code,
            "CORPUS_STATE_BINDING_MISMATCH",
        )

    def test_regressing_event_time_rolls_back_without_corrupting_state(self):
        with HistoricalResearchCorpusState(
            self.state_path,
            plan=self.plan,
            output_root=self.output_root,
        ) as state:
            state.claim_next(
                worker_id="worker-a",
                recorded_at="2026-07-28T00:01:00.000Z",
            )
            with self.assertRaises(ResearchCorpusError) as raised:
                state.claim_next(
                    worker_id="worker-b",
                    recorded_at="2026-07-28T00:00:00.000Z",
                )
            replay = state.replay()
        self.assertEqual(
            raised.exception.reason_code,
            "CORPUS_EVENT_TIME_REGRESSION",
        )
        self.assertEqual(replay["event_count"], 1)

    def test_source_and_event_tamper_fail_on_reopen(self):
        run_historical_research_corpus(
            plan=self.plan,
            state_path=self.state_path,
            output_root=self.output_root,
            worker_id="worker-a",
            max_items=1,
            transport=OneArchiveTransport(),
            clock=TickClock(),
        )
        connection = sqlite3.connect(str(self.state_path))
        try:
            connection.execute("DROP TRIGGER corpus_events_no_update")
            connection.execute(
                "UPDATE corpus_events SET source_bytes = ? "
                "WHERE event_type = 'SUCCEEDED'",
                (b"{}",),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(ResearchCorpusError) as raised:
            HistoricalResearchCorpusState(
                self.state_path,
                plan=self.plan,
                output_root=self.output_root,
            )
        self.assertEqual(
            raised.exception.reason_code,
            "CORPUS_SOURCE_BYTES_TAMPERED",
        )

    def test_limits_and_worker_ids_fail_before_state_or_network(self):
        transport = FailingTransport()
        for max_items in (0, 17, True):
            with self.subTest(max_items=max_items):
                with self.assertRaises(ResearchCorpusError):
                    run_historical_research_corpus(
                        plan=self.plan,
                        state_path=self.state_path,
                        output_root=self.output_root,
                        worker_id="worker-a",
                        max_items=max_items,
                        transport=transport,
                    )
        with self.assertRaises(ResearchCorpusError):
            run_historical_research_corpus(
                plan=self.plan,
                state_path=self.state_path,
                output_root=self.output_root,
                worker_id="../bad",
                max_items=1,
                transport=transport,
            )
        self.assertEqual(transport.calls, [])


class CompleteStateStub:
    def __init__(self, plan, anchored):
        self._states = {}
        for item in plan["items"]:
            attestation = hashlib.sha256(
                item["corpus_item_id"].encode("ascii")
            ).hexdigest()
            self._states[item["corpus_item_id"]] = {
                "status": "SUCCEEDED",
                "attempt": 1,
                "worker_id": "fixture",
                "recorded_at": "2026-07-28T00:00:00.000Z",
                "row": {
                    "source_bytes_sha256_or_null": hashlib.sha256(
                        (item["corpus_item_id"] + "-bytes").encode("ascii")
                    ).hexdigest(),
                    "source_snapshot_hash_or_null": hashlib.sha256(
                        (item["corpus_item_id"] + "-snapshot").encode("ascii")
                    ).hexdigest(),
                    "expected_attestation_hash_or_null": attestation,
                },
                "snapshot": {"quality_eligibility": "FORMAL_COMPLETE"},
            }
        self.anchored = anchored

    def replay(self):
        return {
            "states": self._states,
            "event_count": 336,
            "event_chain_end_hash": "a" * 64,
            "physical_get_count": 336,
        }


class ResearchCorpusReadinessTests(unittest.TestCase):
    def test_complete_fixture_state_is_research_ready_but_never_formal_oos(self):
        plan = build_default_research_corpus_plan()
        state = CompleteStateStub(plan, anchored=False)
        snapshot = build_research_corpus_snapshot(
            plan=plan,
            state=state,
            recorded_at="2026-07-28T00:00:00.000Z",
        )

        self.assertEqual(
            snapshot["research_training_readiness"],
            "READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD",
        )
        self.assertEqual(
            snapshot["attestation_eligibility"],
            "UNANCHORED_ARCHIVE_RESEARCH",
        )
        self.assertEqual(snapshot["release_oos_eligibility"], "INELIGIBLE")
        self.assertEqual(snapshot["profitability_eligibility"], "INELIGIBLE")
        self.assertEqual(
            research_corpus_snapshot_reasons(snapshot, plan=plan),
            (),
        )

    def test_snapshot_semantic_tamper_is_detected_after_rehash(self):
        plan = build_default_research_corpus_plan()
        with tempfile.TemporaryDirectory() as directory:
            with HistoricalResearchCorpusState(
                Path(directory) / "state.sqlite3",
                plan=plan,
                output_root=Path(directory) / "output",
            ) as state:
                snapshot = build_research_corpus_snapshot(
                    plan=plan,
                    state=state,
                    recorded_at="2026-07-28T00:00:00.000Z",
                )
        snapshot["summary"]["pending_item_count"] = 167
        snapshot["snapshot_hash"] = research_corpus_snapshot_hash(snapshot)

        self.assertIn(
            "CORPUS_SNAPSHOT_SUMMARY_MISMATCH",
            research_corpus_snapshot_reasons(snapshot, plan=plan),
        )

    def test_snapshot_loader_rejects_duplicate_or_noncanonical_json(self):
        plan = build_default_research_corpus_plan()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            with HistoricalResearchCorpusState(
                Path(directory) / "state.sqlite3",
                plan=plan,
                output_root=Path(directory) / "output",
            ) as state:
                snapshot = build_research_corpus_snapshot(
                    plan=plan,
                    state=state,
                    recorded_at="2026-07-28T00:00:00.000Z",
                )
            canonical = canonical_json(snapshot)
            path.write_text(canonical, encoding="utf-8")
            self.assertEqual(
                load_research_corpus_snapshot(path, plan=plan),
                snapshot,
            )
            path.write_text(
                canonical.replace(
                    '{"$schema":',
                    '{"schema_version":"1.0.0","$schema":',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ResearchCorpusError) as raised:
                load_research_corpus_snapshot(path, plan=plan)
            self.assertEqual(
                raised.exception.reason_code,
                "CORPUS_SOURCE_BYTES_INVALID",
            )


if __name__ == "__main__":
    unittest.main()
