import unittest
import os
from pathlib import Path
from unittest.mock import patch

from crypto_quant.challenger_replacement_events import (
    open_challenger_replacement_event_root,
)
from crypto_quant.challenger_replacement_fixture_simulation import (
    run_challenger_replacement_fixture_simulation_opportunity,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityError,
    ChallengerReplacementOpportunityState,
    catch_up_missed_opportunities,
)
from crypto_quant.challenger_replacement_readiness import (
    _ReplacementReadinessBoundary,
)
from crypto_quant.challenger_replacement_readiness_observer import (
    ChallengerReplacementReadinessObserverError,
    ChallengerReplacementReadinessReplaySource,
    ReplacementReadinessObservation,
    ReplacementReadinessReleaseProvenance,
    observe_challenger_replacement_readiness,
)
from tests.challenger_replacement_v3_fixtures import (
    fixture_v072_build_identity,
    fixture_v072_golden_streams,
    fixture_v3_plan,
)
from tests.test_challenger_replacement_events import EventWorkspace


ROOT = Path(__file__).resolve().parents[1]
PLAN_BYTES = (
    ROOT
    / "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json"
).read_bytes()


def _release_provenance():
    return ReplacementReadinessReleaseProvenance(
        release_tag="v0.72.0",
        peeled_commit="44d294a8fbc55a0fb4f9fe0537bb868824815d80",
        package_version="0.72.0",
        manifest_version="1.66.0",
        build_input_tree_hash=(
            "9ee098305a9ce55ef6a135981f339348d20cb90e366c09af1bafcd0d52e25b87"
        ),
        manifest_hash=(
            "23083f76a979c77c88059271ff60cc514793f17a10d093eaab4c7a1ec2b86dc5"
        ),
    )


class ReadinessObserverWorkspace:
    def __init__(self):
        self.files = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.files.identity())
        self.state = ChallengerReplacementOpportunityState(
            event_root=self.root,
            plan=fixture_v3_plan(),
            build_identity=fixture_v072_build_identity(),
        )

    def close(self):
        self.root.close()
        self.files.close()

    def run_stream(self, name):
        for body in fixture_v072_golden_streams()[name]:
            run_challenger_replacement_fixture_simulation_opportunity(
                state=self.state,
                input_bytes=body,
                worker_id="fixture-worker",
            )


class ChallengerReplacementReadinessObserverTests(unittest.TestCase):
    def setUp(self):
        self.workspace = ReadinessObserverWorkspace()

    def tearDown(self):
        self.workspace.close()

    def boundary(self):
        return _ReplacementReadinessBoundary(
            qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
            start_opportunity_id_or_null="ETHUSDT@2026-08-24T00:00:00.000Z",
            start_scheduled_for_or_null="2026-08-24T00:00:00.000Z",
            start_observed_at_or_null="2026-08-24T00:05:00.000Z",
            observed_at="2026-08-24T08:10:00.000Z",
        )

    def observe(self, source):
        return observe_challenger_replacement_readiness(
            plan_bytes=PLAN_BYTES,
            replay_source=source,
            boundary=self.boundary(),
            release_provenance=_release_provenance(),
        )

    def test_observer_reduces_strict_v2_projection_once(self):
        self.workspace.run_stream("spot-cycle")
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )
        with patch.object(
            source, "replay", wraps=source.replay
        ) as replay:
            observed = self.observe(source)

        self.assertIsInstance(observed, ReplacementReadinessObservation)
        self.assertEqual(replay.call_count, 1)
        self.assertEqual(observed.authority_status, "FIXTURE_NOT_OPERATIONAL")
        self.assertEqual(
            tuple(
                (item.position_before, item.position_after, item.product_or_null)
                for item in observed.facts.opportunities
            ),
            (
                ("FLAT", "SPOT_LONG", "spot"),
                ("SPOT_LONG", "SPOT_LONG", "spot"),
                ("SPOT_LONG", "FLAT", "spot"),
            ),
        )
        self.assertEqual(
            tuple(
                (item.lifecycle_status_or_null, item.protective_stop_status)
                for item in observed.facts.opportunities
            ),
            (
                ("RECONCILED_FIXTURE", "CONFIRMED_FIXTURE"),
                ("RECONCILED_FIXTURE", "CONFIRMED_FIXTURE"),
                ("RECONCILED_FIXTURE", "NOT_REQUIRED_FLAT"),
            ),
        )
        self.assertEqual(observed.operational.strategy_cycle_count, 1)
        self.assertEqual(observed.economic.status, "WITHHELD_PRE_TAIL")

    def test_unexpected_memory_error_is_not_masked_as_plan_invalid(self):
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )
        with patch(
            "crypto_quant.challenger_replacement_readiness_observer._strict_json_bytes",
            side_effect=MemoryError("fixture allocation failure"),
        ):
            with self.assertRaisesRegex(MemoryError, "allocation failure"):
                self.observe(source)

    def test_observer_has_replay_only_facade_and_performs_zero_writes(self):
        self.workspace.run_stream("spot-cycle")
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )
        public = {
            name
            for name, value in vars(type(source)).items()
            if not name.startswith("_") and callable(value)
        }
        self.assertEqual(public, {"replay"})

        with patch.object(os, "write", side_effect=AssertionError("write")), patch.object(
            os, "chmod", side_effect=AssertionError("chmod")
        ), patch.object(
            os, "rename", side_effect=AssertionError("rename")
        ), patch.object(
            os, "replace", side_effect=AssertionError("replace")
        ), patch(
            "pathlib.Path.write_bytes", side_effect=AssertionError("write_bytes")
        ), patch(
            "pathlib.Path.write_text", side_effect=AssertionError("write_text")
        ), patch(
            "subprocess.run", side_effect=AssertionError("subprocess")
        ), patch(
            "socket.socket", side_effect=AssertionError("network")
        ):
            observed = self.observe(source)

        self.assertEqual(observed.evidence_health, "VERIFIED")

    def test_perpetual_fixture_stream_reduces_one_complete_roundtrip(self):
        self.workspace.run_stream("perp-cycle")
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )
        boundary = _ReplacementReadinessBoundary(
            qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
            start_opportunity_id_or_null="ETHUSDT@2026-08-25T00:00:00.000Z",
            start_scheduled_for_or_null="2026-08-25T00:00:00.000Z",
            start_observed_at_or_null="2026-08-25T00:05:00.000Z",
            observed_at="2026-08-25T12:10:00.000Z",
        )

        observed = observe_challenger_replacement_readiness(
            plan_bytes=PLAN_BYTES,
            replay_source=source,
            boundary=boundary,
            release_provenance=_release_provenance(),
        )

        self.assertEqual(observed.operational.perpetual_roundtrip_count, 1)
        self.assertEqual(observed.facts.current_position, "FLAT")
        self.assertEqual(
            tuple(item.product_or_null for item in observed.facts.opportunities),
            ("perpetual", "perpetual", "perpetual", "perpetual"),
        )

    def test_missed_while_exposed_is_preserved_as_permanent_gap(self):
        first = fixture_v072_golden_streams()["spot-cycle"][0]
        run_challenger_replacement_fixture_simulation_opportunity(
            state=self.workspace.state,
            input_bytes=first,
            worker_id="fixture-worker",
        )
        catch_up_missed_opportunities(
            state=self.workspace.state,
            start_scheduled_for="2026-08-24T00:00:00.000Z",
            detected_at="2026-08-24T04:11:00.000Z",
            worker_id="fixture-worker",
            reason_code="PROCESS_NOT_RUNNING",
        )
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )
        boundary = _ReplacementReadinessBoundary(
            qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
            start_opportunity_id_or_null="ETHUSDT@2026-08-24T00:00:00.000Z",
            start_scheduled_for_or_null="2026-08-24T00:00:00.000Z",
            start_observed_at_or_null="2026-08-24T00:05:00.000Z",
            observed_at="2026-08-24T04:11:00.000Z",
        )

        observed = observe_challenger_replacement_readiness(
            plan_bytes=PLAN_BYTES,
            replay_source=source,
            boundary=boundary,
            release_provenance=_release_provenance(),
        )

        missed = observed.facts.opportunities[-1]
        self.assertEqual(missed.outcome, "MISSED")
        self.assertTrue(missed.economic_gap_locked)
        self.assertIn("ECONOMIC_GAP_LOCKED", missed.unresolved_reason_codes)
        self.assertEqual(
            observed.operational.policy_status,
            "OPERATIONAL_QUALIFICATION_DID_NOT_PASS",
        )

    def test_confirmed_replay_violation_maps_to_did_not_pass(self):
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )
        hostile_text = "secret-path-and-input-bytes"
        with patch.object(
            source,
            "replay",
            side_effect=ChallengerReplacementOpportunityError(
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
            ),
        ):
            observed = self.observe(source)

        self.assertEqual(
            observed.operational.policy_status,
            "OPERATIONAL_QUALIFICATION_DID_NOT_PASS",
        )
        self.assertEqual(
            observed.facts.evidence_failure_kind_or_null,
            "CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE",
        )
        self.assertNotIn(hostile_text, repr(observed))

    def test_unavailable_replay_source_maps_to_inconclusive(self):
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )
        with patch.object(
            source,
            "replay",
            side_effect=ChallengerReplacementOpportunityError(
                "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED"
            ),
        ):
            observed = self.observe(source)

        self.assertEqual(
            observed.operational.policy_status,
            "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        )
        self.assertEqual(
            observed.facts.evidence_failure_kind_or_null,
            "EVIDENCE_SOURCE_UNAVAILABLE_OR_QUALIFICATION_UNKNOWN",
        )

    def test_orphan_staging_is_confirmed_evidence_failure(self):
        orphan = self.workspace.files.event_root / (
            ".stage-00000000000000000001-" + "a" * 64 + "-" + "b" * 32 + ".tmp"
        )
        orphan.write_bytes(b"partial")
        orphan.chmod(0o600)
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )

        observed = self.observe(source)

        self.assertEqual(
            observed.operational.policy_status,
            "OPERATIONAL_QUALIFICATION_DID_NOT_PASS",
        )
        self.assertEqual(
            observed.facts.evidence_failure_kind_or_null,
            "CONFIRMED_EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE",
        )

    def test_arbitrary_boundary_mapping_fails_with_fixed_reason(self):
        source = ChallengerReplacementReadinessReplaySource(
            self.workspace.state
        )
        with self.assertRaises(ChallengerReplacementReadinessObserverError) as caught:
            observe_challenger_replacement_readiness(
                plan_bytes=PLAN_BYTES,
                replay_source=source,
                boundary={"observed_at": "hostile"},
                release_provenance=_release_provenance(),
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_READINESS_OBSERVER_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
