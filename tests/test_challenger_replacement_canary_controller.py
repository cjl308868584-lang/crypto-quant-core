import json
import unittest

from crypto_quant.challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from crypto_quant.challenger_replacement_canary_controller import (
    ChallengerReplacementCanaryControllerError,
    load_challenger_replacement_canary_projection_bytes,
    project_challenger_replacement_canary,
)
from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_events import (
    build_challenger_replacement_event,
    open_challenger_replacement_event_root,
    publish_challenger_replacement_event,
)
from crypto_quant.challenger_replacement_install_trust import business_hash
from tests.test_challenger_replacement_events import EventWorkspace
from tests.test_challenger_replacement_public_market_capture import V076_BUILD


LABEL = "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE"
STATES = (
    "CEREMONY_READY_FLAT", "SPOT_BUY_SUBMITTED",
    "SPOT_LONG_RECONCILED", "SPOT_SELL_SUBMITTED",
    "FLAT_RECONCILED_AFTER_SPOT", "PERP_SHORT_SUBMITTED",
    "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED",
    "PERP_CLOSE_REDUCE_ONLY_SUBMITTED", "FLAT_RECONCILED_AFTER_PERP",
    "CEREMONY_QUALIFIED",
)


class ChallengerReplacementCanaryControllerTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_challenger_replacement_accelerated_canary_plan()

    @staticmethod
    def ceremony_events():
        return tuple({
            "event_type": "CEREMONY_STATE_RECONCILED",
            "block_id": "ceremony-block-1", "label": LABEL,
            "state": state,
            "occurred_at": "2026-09-01T%02d:00:00.000Z" % index,
            "reconciliation_id": "binance_reconciliation_" + format(index, "064x"),
            "minimum_amount_satisfied_or_null": (
                True if state in {
                    "SPOT_LONG_RECONCILED", "FLAT_RECONCILED_AFTER_SPOT",
                    "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED",
                    "FLAT_RECONCILED_AFTER_PERP",
                } else None
            ),
            "flat_or_null": (
                True if state in {
                    "CEREMONY_READY_FLAT", "FLAT_RECONCILED_AFTER_SPOT",
                    "FLAT_RECONCILED_AFTER_PERP", "CEREMONY_QUALIFIED",
                } else False if state in {
                    "SPOT_LONG_RECONCILED",
                    "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED",
                } else None
            ),
        } for index, state in enumerate(STATES))

    @staticmethod
    def start(stage="E0", at="2026-09-02T00:00:00.000Z",
              previous=None, unlock=None):
        return {
            "event_type": "CANARY_STAGE_BLOCK_STARTED",
            "stage": stage, "block_id": stage.lower() + "-block-1",
            "activation_id": "binance_private_activation_" + (
                {"E0": "1", "E1": "2", "E2": "3"}[stage] * 64
            ),
            "previous_block_id_or_null": previous,
            "incident_unlock_id_or_null": unlock,
            "occurred_at": at,
            "starting_equity": {"E0": "100", "E1": "300", "E2": "1000"}[stage],
        }

    @staticmethod
    def mark(at, equity, *, new_risk=False, hard_stop=None, flat=True):
        return {
            "event_type": "CANARY_EQUITY_RECONCILED",
            "block_id": "e0-block-1", "occurred_at": at,
            "equity": equity, "flat": flat,
            "new_risk_attempted": new_risk,
            "hard_stop_or_null": hard_stop,
        }

    @staticmethod
    def cycle(product, ordinal, at):
        return {
            "event_type": "CANARY_STRATEGY_CYCLE_RECONCILED",
            "block_id": "e0-block-1", "occurred_at": at,
            "cycle_id": "natural-cycle-%d" % ordinal,
            "product": product, "complete": True,
            "evidence_label": "NATURAL_STRATEGY_EVIDENCE",
        }

    @staticmethod
    def stage_event(event, *, stage, block_id):
        changed = dict(event)
        changed["block_id"] = block_id
        return changed

    def project(self, events, now="2026-09-09T00:00:00.000Z"):
        workspace = EventWorkspace()
        self.addCleanup(workspace.close)
        previous = "0" * 64
        with open_challenger_replacement_event_root(workspace.identity()) as root:
            for sequence, candidate in enumerate(events, 1):
                event = build_challenger_replacement_event(
                    sequence=sequence, event_type=candidate["event_type"],
                    slot_id=candidate["block_id"],
                    worker_id="canary-controller-fixture",
                    recorded_at=candidate["occurred_at"],
                    previous_event_hash=previous,
                    payload_bytes=canonical_json(candidate).encode(),
                    plan_hash=self.plan["plan_hash"],
                    build_identity_hash=business_hash(V076_BUILD),
                    event_root=root,
                )
                publish_challenger_replacement_event(root, event)
                previous = event.event_hash
            data = project_challenger_replacement_canary(
                event_root=root, plan=self.plan, build_identity=V076_BUILD,
                now=now,
            )
        return data, load_challenger_replacement_canary_projection_bytes(
            data, plan=self.plan,
        )

    def test_exact_ceremony_sequence_qualifies_but_counts_no_strategy_cycle(self):
        data, loaded = self.project(self.ceremony_events())
        self.assertEqual(loaded["ceremony"], {
            "block_id": "ceremony-block-1", "state": "CEREMONY_QUALIFIED",
            "qualified": True, "strategy_cycle_count": 0,
            "economic_evidence_count": 0,
        })
        self.assertIsNone(loaded["stage_block_or_null"])
        self.assertEqual(loaded["authority"], {
            "network_requests": 0, "orders": 0, "state_writes": 0,
            "production_activation": False,
        })
        self.assertEqual(
            json.loads(data)["projection_id"], loaded["projection_id"],
        )

    def test_public_projection_rejects_manufactured_event_list(self):
        with self.assertRaises(TypeError):
            project_challenger_replacement_canary(
                events=self.ceremony_events(), plan=self.plan,
                now="2026-09-09T00:00:00.000Z",
            )

    def test_daily_loss_stops_new_risk_until_utc_rollover(self):
        events = self.ceremony_events() + (
            self.start(),
            self.mark("2026-09-02T04:00:00.000Z", "97.999", flat=False),
        )
        _, stopped = self.project(events, now="2026-09-02T08:00:00.000Z")
        block = stopped["stage_block_or_null"]
        self.assertEqual(block["status"], "STAGE_DAILY_STOPPED")
        self.assertEqual(block["daily_loss"], "2.001")
        self.assertTrue(block["new_risk_blocked"])

        events += (self.mark(
            "2026-09-02T08:00:00.000Z", "97.999", new_risk=True,
            hard_stop="RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
        ),)
        _, failed = self.project(events, now="2026-09-02T12:00:00.000Z")
        self.assertEqual(failed["stage_block_or_null"]["status"],
                         "STAGE_FAILED_LOCKED")

        rollover = self.ceremony_events() + (
            self.start(),
            self.mark("2026-09-02T04:00:00.000Z", "97.999", flat=True),
            self.mark("2026-09-03T00:00:00.000Z", "97.999", flat=True),
        )
        _, resumed = self.project(rollover, now="2026-09-03T04:00:00.000Z")
        self.assertEqual(resumed["stage_block_or_null"]["status"],
                         "STAGE_ACTIVE")
        self.assertFalse(resumed["stage_block_or_null"]["new_risk_blocked"])

    def test_duration_cycles_products_create_eligibility_not_auto_promotion(self):
        events = list(self.ceremony_events()) + [self.start()]
        events.extend((
            self.cycle("SPOT", 1, "2026-09-03T00:00:00.000Z"),
            self.cycle("PERPETUAL", 2, "2026-09-05T00:00:00.000Z"),
            self.cycle("SPOT", 3, "2026-09-08T00:00:00.000Z"),
        ))
        _, loaded = self.project(events, now="2026-09-09T00:00:00.000Z")
        block = loaded["stage_block_or_null"]
        self.assertEqual(block["status"], "STAGE_ELIGIBLE_AWAITING_APPROVAL")
        self.assertEqual(block["strategy_cycle_count"], 3)
        self.assertEqual(block["spot_complete_cycles"], 2)
        self.assertEqual(block["perpetual_complete_cycles"], 1)
        self.assertEqual(block["stage"], "E0")

        premature = list(self.ceremony_events()) + [
            self.start(), self.start(
                "E1", "2026-09-03T00:00:00.000Z", previous="e0-block-1",
            ),
        ]
        with self.assertRaisesRegex(
            ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_EVENT_INVALID",
        ):
            self.project(premature)

    def test_ceremony_rejects_unmet_minimum_or_nonflat_qualification(self):
        for index, field, value in (
            (2, "minimum_amount_satisfied_or_null", False),
            (9, "flat_or_null", False),
        ):
            with self.subTest(field=field):
                events = list(self.ceremony_events())
                events[index] = {**events[index], field: value}
                with self.assertRaisesRegex(
                    ChallengerReplacementCanaryControllerError,
                    "CHALLENGER_REPLACEMENT_CANARY_EVENT_INVALID",
                ):
                    self.project(events)

    def test_drawdown_fails_block_without_inventing_a_hard_stop(self):
        events = self.ceremony_events() + (
            self.start(),
            self.mark("2026-09-02T04:00:00.000Z", "95", flat=True),
        )
        _, loaded = self.project(events, now="2026-09-02T08:00:00.000Z")
        block = loaded["stage_block_or_null"]
        self.assertEqual(block["status"], "STAGE_FAILED_LOCKED")
        self.assertEqual(block["failure_reason_or_null"],
                         "STAGE_DRAWDOWN_LIMIT_REACHED")
        self.assertIsNone(block["hard_stop_or_null"])

    def test_eligible_e0_allows_only_new_approved_e1_block(self):
        events = list(self.ceremony_events()) + [self.start()]
        events.extend((
            self.cycle("SPOT", 1, "2026-09-03T00:00:00.000Z"),
            self.cycle("PERPETUAL", 2, "2026-09-05T00:00:00.000Z"),
            self.cycle("SPOT", 3, "2026-09-09T00:00:00.000Z"),
            self.start("E1", "2026-09-09T04:00:00.000Z",
                       previous="e0-block-1"),
        ))
        _, loaded = self.project(events, now="2026-09-09T08:00:00.000Z")
        block = loaded["stage_block_or_null"]
        self.assertEqual(block["stage"], "E1")
        self.assertEqual(block["status"], "STAGE_ACTIVE")
        self.assertEqual(block["previous_block_id_or_null"], "e0-block-1")

    def test_e2_percentage_limits_use_stage_capital_and_high_water(self):
        events = self.ceremony_events() + (
            self.start("E0"),
            self.cycle("SPOT", 1, "2026-09-03T00:00:00.000Z"),
            self.cycle("PERPETUAL", 2, "2026-09-05T00:00:00.000Z"),
            self.cycle("SPOT", 3, "2026-09-09T00:00:00.000Z"),
            self.start("E1", "2026-09-09T04:00:00.000Z", "e0-block-1"),
        )
        e1_id = "e1-block-1"
        events += tuple(self.stage_event(
            self.cycle("SPOT" if index % 2 else "PERPETUAL", index,
                       "2026-09-%02dT00:00:00.000Z" % day),
            stage="E1", block_id=e1_id,
        ) for index, day in enumerate(range(10, 15), 4))
        events += (self.start(
            "E2", "2026-09-24T00:00:00.000Z", previous=e1_id,
        ), self.stage_event(
            self.mark("2026-09-24T04:00:00.000Z", "980", flat=True),
            stage="E2", block_id="e2-block-1",
        ))
        _, loaded = self.project(events, now="2026-09-24T08:00:00.000Z")
        self.assertEqual(loaded["stage_block_or_null"]["status"],
                         "STAGE_DAILY_STOPPED")

    def test_failed_block_can_only_restart_after_flat_and_exact_unlock(self):
        events = self.ceremony_events() + (
            self.start(),
            self.mark(
                "2026-09-02T04:00:00.000Z", "99", flat=False,
                hard_stop="VENUE_LOCAL_POSITION_MISMATCH",
            ),
            self.mark("2026-09-02T08:00:00.000Z", "98.9", flat=True),
        )
        _, failed = self.project(events, now="2026-09-02T12:00:00.000Z")
        self.assertEqual(failed["stage_block_or_null"]["status"],
                         "STAGE_FAILED_LOCKED")
        self.assertTrue(failed["stage_block_or_null"]["flat"])
        self.assertFalse(failed["stage_block_or_null"]["flatten_required"])

        restarted = events + (self.start(
            "E0", "2026-09-02T12:00:00.000Z", previous="e0-block-1",
            unlock="incident_unlock_" + "4" * 64,
        ) | {"block_id": "e0-block-2"},)
        _, loaded = self.project(restarted, now="2026-09-02T16:00:00.000Z")
        self.assertEqual(loaded["stage_block_or_null"]["block_id"],
                         "e0-block-2")
        self.assertEqual(loaded["stage_block_or_null"]["status"],
                         "STAGE_ACTIVE")

        for missing in (None, "incident_unlock_not-a-hash"):
            with self.subTest(unlock=missing):
                invalid = events + (self.start(
                    "E0", "2026-09-02T12:00:00.000Z",
                    previous="e0-block-1", unlock=missing,
                ) | {"block_id": "e0-block-2"},)
                with self.assertRaisesRegex(
                    ChallengerReplacementCanaryControllerError,
                    "CHALLENGER_REPLACEMENT_CANARY_EVENT_INVALID",
                ):
                    self.project(invalid)

    def test_exact_activation_and_reconciliation_identities_are_required(self):
        for events in (
            self.ceremony_events() + (
                self.start() | {"activation_id": "approval"},
            ),
            ({**self.ceremony_events()[0],
              "reconciliation_id": "binance_reconciliation_short"},),
        ):
            with self.subTest(events=events):
                with self.assertRaisesRegex(
                    ChallengerReplacementCanaryControllerError,
                    "CHALLENGER_REPLACEMENT_CANARY_EVENT_INVALID",
                ):
                    self.project(events)

    def test_loader_rejects_noncanonical_or_unbound_projection(self):
        data, _ = self.project(self.ceremony_events())
        altered_plan = dict(self.plan)
        altered_plan["status"] = "DIFFERENT"
        for candidate, plan in (
            (data[:-1], self.plan),
            (data.replace(b'"schema_version":"1.0.0"',
                          b'"schema_version": "1.0.0"'), self.plan),
            (data, altered_plan),
        ):
            with self.subTest(candidate=candidate[:24]):
                with self.assertRaisesRegex(
                    ChallengerReplacementCanaryControllerError,
                    "CHALLENGER_REPLACEMENT_CANARY_PROJECTION_INVALID",
                ):
                    load_challenger_replacement_canary_projection_bytes(
                        candidate, plan=plan,
                    )

    def test_post_limit_risk_hard_stop_requires_an_actual_post_limit_attempt(self):
        invalid = self.ceremony_events() + (
            self.start(),
            self.mark(
                "2026-09-02T04:00:00.000Z", "100", new_risk=False,
                hard_stop="RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
            ),
        )
        with self.assertRaisesRegex(
            ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_EVENT_INVALID",
        ):
            self.project(invalid)


if __name__ == "__main__":
    unittest.main()
