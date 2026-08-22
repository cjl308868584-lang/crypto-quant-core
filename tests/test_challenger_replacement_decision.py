import unittest
from copy import deepcopy
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_decimal, canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.challenger_replacement_evidence import build_challenger_replacement_source_bundle
from crypto_quant.challenger_replacement_decision import (
    ChallengerReplacementDecisionError,
    build_challenger_replacement_decision,
    load_challenger_replacement_decision_bytes,
)
from tests.challenger_replacement_v2_fixtures import fixture_build_identity, fixture_capture, fixture_plan


def capture_with_closes(closes):
    capture = fixture_capture()
    rows = deepcopy(capture["klines"])
    for row, value in zip(rows, closes):
        close = Decimal(value)
        row.update(open=canonical_decimal(close), high=canonical_decimal(close + 1),
                   low=canonical_decimal(close - 1), close=canonical_decimal(close))
        body = dict(row); body.pop("source_row_hash")
        row["source_row_hash"] = business_hash(body)
    capture["klines"] = rows
    return capture


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_plan(); self.build = fixture_build_identity()

    def _decision(self, closes):
        source = build_challenger_replacement_source_bundle(
            plan=self.plan, capture=capture_with_closes(closes),
            observed_at="2026-08-22T04:05:00.000Z", build_identity=self.build,
            previous_source_bundle=None, previous_decision=None)
        decision = build_challenger_replacement_decision(
            plan=self.plan, source_bundle=source, recorded_at=source["slot"]["captured_at"],
            previous_decision=None)
        return source, decision

    def test_frozen_entry_threshold_and_momentum(self):
        _, below = self._decision(["100"] * 20 + ["100.4"])
        _, equal = self._decision(["100"] * 20 + ["100.5"])
        _, zero = self._decision(["99"] * 15 + ["100"] + ["99"] * 4 + ["100"])
        self.assertEqual((below["action"], below["features"]["eth_sma20_distance"]), ("REJECT_ENTRY", "0.004"))
        self.assertEqual((equal["action"], equal["features"]["eth_sma20_distance"]), ("ENTER_LONG", "0.005"))
        self.assertEqual((zero["action"], zero["features"]["eth_log_return_5"]), ("REJECT_ENTRY", "0"))

    def test_bytes_loader_replays_semantics_and_rejects_mutation(self):
        source, decision = self._decision(["100"] * 20 + ["101"])
        data = canonical_json(decision).encode("utf-8")
        self.assertEqual(load_challenger_replacement_decision_bytes(
            data, plan=self.plan, source_bundle=source, previous_decision=None), decision)
        mutated = deepcopy(decision); mutated["action"] = "REJECT_ENTRY"
        mutated["decision_hash"] = artifact_self_hash(mutated, "decision_hash")
        with self.assertRaises(ChallengerReplacementDecisionError):
            load_challenger_replacement_decision_bytes(
                canonical_json(mutated).encode("utf-8"), plan=self.plan, source_bundle=source,
                previous_decision=None)
        with self.assertRaises(ChallengerReplacementDecisionError):
            load_challenger_replacement_decision_bytes(
                b" " + data, plan=self.plan, source_bundle=source, previous_decision=None)

    def _advance(self, source, decision, latest):
        previous = datetime.fromisoformat(
            source["slot"]["scheduled_for"].replace("Z", "+00:00"))
        scheduled = previous + timedelta(hours=4)
        scheduled_text = scheduled.astimezone(timezone.utc).isoformat(
            timespec="milliseconds").replace("+00:00", "Z")
        captured_text = (scheduled + timedelta(minutes=5)).astimezone(
            timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        capture = fixture_capture(
            sequence=source["slot"]["sequence"] + 1,
            scheduled_for=scheduled_text, captured_at=captured_text, latest=latest)
        capture["klines"] = deepcopy(source["klines"][1:]) + [capture["klines"][-1]]
        next_source = build_challenger_replacement_source_bundle(
            plan=self.plan, capture=capture, observed_at=captured_text,
            build_identity=self.build, previous_source_bundle=source,
            previous_decision=decision)
        next_decision = build_challenger_replacement_decision(
            plan=self.plan, source_bundle=next_source, recorded_at=captured_text,
            previous_decision=decision)
        return next_source, next_decision

    def test_long_state_minimum_sma_and_vertical_exit_rules(self):
        source, decision = self._decision(["100"] * 20 + ["101"])
        self.assertEqual(decision["action"], "ENTER_LONG")
        source, decision = self._advance(source, decision, "102")
        self.assertEqual(decision["action"], "HOLD_LONG_MINIMUM")
        source, decision = self._advance(source, decision, "99")
        self.assertEqual(decision["action"], "EXIT_LONG_SMA20")

        source, decision = self._decision(["100"] * 20 + ["101"])
        for latest in ("102", "103", "104", "105", "106", "107"):
            source, decision = self._advance(source, decision, latest)
        self.assertEqual(decision["action"], "EXIT_LONG_VERTICAL_24H")

    def test_wrong_plan_source_and_previous_decision_fail_closed(self):
        source, decision = self._decision(["100"] * 20 + ["101"])
        wrong_plan = deepcopy(self.plan); wrong_plan["plan_hash"] = "f" * 64
        with self.assertRaises(ChallengerReplacementDecisionError):
            load_challenger_replacement_decision_bytes(
                canonical_json(decision).encode(), plan=wrong_plan,
                source_bundle=source, previous_decision=None)
        wrong_source = deepcopy(source); wrong_source["bundle_hash"] = "e" * 64
        with self.assertRaises(ChallengerReplacementDecisionError):
            load_challenger_replacement_decision_bytes(
                canonical_json(decision).encode(), plan=self.plan,
                source_bundle=wrong_source, previous_decision=None)


if __name__ == "__main__":
    unittest.main()
