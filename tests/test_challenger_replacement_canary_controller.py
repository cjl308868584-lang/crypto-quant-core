import json
import hashlib
import base64
import os
from pathlib import Path
import unittest

from crypto_quant.challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from crypto_quant.challenger_replacement_canary_controller import (
    ChallengerReplacementCanaryControllerError,
    _project_challenger_replacement_canary,
    load_challenger_replacement_canary_approval_bytes,
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
from crypto_quant.challenger_replacement_binance_reconciliation import load_binance_reconciliation_capture
from crypto_quant.challenger_replacement_plan_v3 import build_challenger_replacement_plan_v3
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
        self.replacement_plan = build_challenger_replacement_plan_v3()

    def approval_bytes(self, kind="PROMOTION", **changes):
        document = {
            "$schema": "./challenger-replacement-canary-authority-approval-v1.schema.json",
            "schema_version": "1.0.0", "approval_id": "",
            "approval_kind": kind,
            "plan": {"plan_id": self.plan["plan_id"],
                     "plan_hash": self.plan["plan_hash"]},
            "build_identity": dict(V076_BUILD),
            "stage": "E1" if kind == "PROMOTION" else "E0",
            "block_id": "approved-block", "previous_block_id": "prior-block",
            "approved_at": "2026-09-01T00:00:00.000Z",
            "expires_at": "2026-09-03T00:00:00.000Z",
            "authority": {"network_requests": 0, "orders": 0,
                          "state_writes": 0, "production_activation": False},
        }
        document.update(changes)
        core = dict(document); core.pop("approval_id")
        prefix = "canary_promotion_" if kind == "PROMOTION" else "incident_unlock_"
        document["approval_id"] = prefix + hashlib.sha256(
            canonical_json(core).encode(),
        ).hexdigest()
        return (canonical_json(document) + "\n").encode()

    def test_approval_loader_binds_self_hash_plan_build_and_time(self):
        data = self.approval_bytes()
        loaded = load_challenger_replacement_canary_approval_bytes(
            data, plan=self.plan, build_identity=V076_BUILD,
            now="2026-09-02T00:00:00.000Z",
        )
        self.assertEqual(loaded["approval_kind"], "PROMOTION")
        wrong_id = json.loads(data)
        wrong_id["approval_id"] = "canary_promotion_" + "0" * 64
        for changed in (
            (canonical_json(wrong_id) + "\n").encode(),
            self.approval_bytes(build_identity={**V076_BUILD, "release_tag": "wrong"}),
            self.approval_bytes(expires_at="2026-09-02T00:00:00.000Z"),
        ):
            with self.subTest(), self.assertRaisesRegex(
                ChallengerReplacementCanaryControllerError,
                "CHALLENGER_REPLACEMENT_CANARY_APPROVAL_INVALID",
            ):
                load_challenger_replacement_canary_approval_bytes(
                    changed, plan=self.plan, build_identity=V076_BUILD,
                    now="2026-09-02T00:00:00.000Z",
                )

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

    @staticmethod
    def publication_record(publication):
        return {name: getattr(publication, name) for name in (
            "sequence", "event_hash", "device", "inode", "size",
        )}

    @staticmethod
    def activation_bytes(candidate):
        limits = {"E0": ("100", "50", "0.5"),
                  "E1": ("300", "300", "1"),
                  "E2": ("1000", "2000", "2")}
        capital, exposure, leverage = limits[candidate["stage"]]
        return (canonical_json({
            "$schema": "./challenger-replacement-binance-private-activation-v1.schema.json",
            "schema_version": "1.0.0", "activation_id": candidate["activation_id"],
            "build_identity": dict(V076_BUILD), "configuration_sha256": "6" * 64,
            "account_approval_sha256": "7" * 64, "block_id": candidate["block_id"],
            "stage": candidate["stage"], "capital_usdt": capital,
            "max_gross_exposure_usdt": exposure, "max_leverage": leverage,
            "expires_at": "2027-01-01T00:00:00.000Z", "production_activation": True,
        }) + "\n").encode()

    def project(self, events, now="2026-09-09T00:00:00.000Z", prefix=(),
                raw_stage_authority=False, replace_first_artifact=False,
                reconciliation_equity_override=None, outer_plan=None,
                replacement_plan=None, canary_plan=None):
        workspace = EventWorkspace()
        self.addCleanup(workspace.close)
        previous = "0" * 64
        with open_challenger_replacement_event_root(workspace.identity()) as root:
            sequence = 0
            def publish(payload):
                nonlocal sequence, previous
                sequence += 1
                event = build_challenger_replacement_event(
                    sequence=sequence, event_type=payload["event_type"],
                    slot_id=(payload["block_id"] if "block_id" in payload
                             else payload["slot_id"]),
                    worker_id="canary-controller-fixture",
                    recorded_at=(payload["occurred_at"] if "occurred_at" in payload
                                 else payload["recorded_at"]),
                    previous_event_hash=previous,
                    payload_bytes=canonical_json(payload.get("payload", payload)).encode(),
                    plan_hash=(outer_plan or self.replacement_plan)["plan_hash"],
                    build_identity_hash=business_hash(V076_BUILD),
                    event_root=root,
                )
                publication = publish_challenger_replacement_event(root, event)
                previous = event.event_hash
                return publication
            def reconcile(candidate, ordinal):
                capture = {"intent_id": "canary-capture-%064x" % ordinal,
                           "capture_version": "1.0.0"}
                for selector in ("event_input", "ledger_input", "venue_input"):
                    body = canonical_json({"selector": selector, "ordinal": ordinal}).encode()
                    capture[selector + "_bytes_base64"] = base64.b64encode(body).decode()
                    capture[selector + "_sha256"] = hashlib.sha256(body).hexdigest()
                captured = publish({
                    "event_type": "BINANCE_RECONCILIATION_INPUTS_CAPTURED",
                    "slot_id": candidate["block_id"], "recorded_at": candidate["occurred_at"],
                    "payload": capture,
                })
                publications = load_binance_reconciliation_capture(
                    event_root=root, capture_event_sequence=captured.sequence,
                    capture_event_hash=captured.event_hash,
                )["publications"]
                if candidate["event_type"] == "CEREMONY_STATE_RECONCILED":
                    state = candidate["state"]
                    expected_flat = state in {"CEREMONY_READY_FLAT", "FLAT_RECONCILED_AFTER_SPOT",
                        "FLAT_RECONCILED_AFTER_PERP", "CEREMONY_QUALIFIED"}
                    exposed = state in {"SPOT_LONG_RECONCILED", "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED"}
                    flat = expected_flat if expected_flat or exposed else True
                    product = "PERPETUAL" if "PERP" in state else "SPOT"
                    equity = "100"
                else:
                    flat, product = candidate["flat"], "SPOT"
                    equity = reconciliation_equity_override or candidate["equity"]
                signed = "0" if flat else "-0.001" if product == "PERPETUAL" else "0.001"
                facts = {"product": product, "signed_quantity": signed,
                    "average_entry_price_or_null": None if signed == "0" else "2000",
                    "realized_pnl": "0", "unrealized_pnl": "0", "cumulative_fee": "0",
                    "funding": "0", "wallet_balance": equity, "available_balance": equity,
                    "open_order_count": 0,
                    "protective_stop_client_id_or_null": ("cq77" + "9" * 32 if signed.startswith("-") else None),
                    "fill_ids": [ordinal]}
                document = {"$schema": "./challenger-replacement-binance-reconciliation-v1.schema.json",
                    "schema_version": "1.0.0", "reconciliation_id": "",
                    "status": "BINANCE_PRIVATE_RECONCILIATION_MATCHED",
                    "event_projection": facts, "venue_projection": facts, "ledger_projection": facts,
                    "capture_publications": json.loads(canonical_json(publications)),
                    "authority": {"network_requests": 0, "orders": 0, "state_writes": 0}}
                core = dict(document); core.pop("reconciliation_id")
                document["reconciliation_id"] = "binance_reconciliation_" + hashlib.sha256(
                    canonical_json(core).encode()).hexdigest()
                data = (canonical_json(document) + "\n").encode()
                artifact = {"event_type": "CANARY_AUTHORITY_ARTIFACT_PUBLISHED",
                    "block_id": candidate["block_id"], "occurred_at": candidate["occurred_at"],
                    "artifact_kind": "RECONCILIATION", "artifact_id": document["reconciliation_id"],
                    "artifact_bytes_base64": base64.b64encode(data).decode(),
                    "artifact_sha256": hashlib.sha256(data).hexdigest()}
                candidate["reconciliation_id"] = document["reconciliation_id"]
                candidate["reconciliation_publication"] = self.publication_record(publish(artifact))
            candidates = tuple(prefix) + tuple(events)
            activation_ids = set()
            first_artifact_path = None
            for original in candidates:
                candidate = dict(original)
                if (candidate["event_type"] in {"CEREMONY_STATE_RECONCILED", "CANARY_EQUITY_RECONCILED"}
                        and (candidate.get("reconciliation_id", "binance_reconciliation_" + "0" * 64)
                             .removeprefix("binance_reconciliation_").isalnum())
                        and len(candidate.get("reconciliation_id", "binance_reconciliation_" + "0" * 64)
                                .removeprefix("binance_reconciliation_")) == 64):
                    reconcile(candidate, sequence + 1)
                if (candidate["event_type"] == "CANARY_STAGE_BLOCK_STARTED"
                        and not raw_stage_authority):
                    if candidate["activation_id"] in activation_ids:
                        candidate["activation_id"] = "binance_private_activation_" + hashlib.sha256(
                            (candidate["block_id"] + candidate["occurred_at"]).encode(),
                        ).hexdigest()
                    activation_ids.add(candidate["activation_id"])
                    activation = self.activation_bytes(candidate)
                    artifact = {
                        "event_type": "CANARY_AUTHORITY_ARTIFACT_PUBLISHED",
                        "block_id": candidate["block_id"],
                        "occurred_at": candidate["occurred_at"],
                        "artifact_kind": "ACTIVATION",
                        "artifact_id": candidate["activation_id"],
                        "artifact_bytes_base64": base64.b64encode(activation).decode(),
                        "artifact_sha256": hashlib.sha256(activation).hexdigest(),
                    }
                    activation_publication = publish(artifact)
                    first_artifact_path = first_artifact_path or Path(
                        activation_publication.absolute_path,
                    )
                    candidate["activation_publication"] = self.publication_record(
                        activation_publication,
                    )
                    unlock = candidate["incident_unlock_id_or_null"]
                    kind = ("INCIDENT_UNLOCK" if isinstance(unlock, str)
                            and unlock.startswith("incident_unlock_")
                            and len(unlock.removeprefix("incident_unlock_")) == 64
                            else "PROMOTION" if candidate["stage"] != "E0" else None)
                    candidate["promotion_approval_id_or_null"] = None
                    candidate["approval_publication_or_null"] = None
                    if kind is not None:
                        approval = self.approval_bytes(
                            kind, stage=candidate["stage"], block_id=candidate["block_id"],
                            previous_block_id=candidate["previous_block_id_or_null"],
                            approved_at="2026-08-31T00:00:00.000Z",
                            expires_at="2027-01-01T00:00:00.000Z",
                        )
                        approval_id = json.loads(approval)["approval_id"]
                        if kind == "PROMOTION":
                            candidate["promotion_approval_id_or_null"] = approval_id
                        else:
                            candidate["incident_unlock_id_or_null"] = approval_id
                        approval_artifact = {
                            "event_type": "CANARY_AUTHORITY_ARTIFACT_PUBLISHED",
                            "block_id": candidate["block_id"],
                            "occurred_at": candidate["occurred_at"],
                            "artifact_kind": kind, "artifact_id": approval_id,
                            "artifact_bytes_base64": base64.b64encode(approval).decode(),
                            "artifact_sha256": hashlib.sha256(approval).hexdigest(),
                        }
                        candidate["approval_publication_or_null"] = self.publication_record(
                            publish(approval_artifact),
                        )
                publish(candidate)
            if replace_first_artifact:
                replacement = first_artifact_path.with_name("same-bytes-new-inode.tmp")
                replacement.write_bytes(first_artifact_path.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, first_artifact_path)
            data = project_challenger_replacement_canary(
                event_root=root, replacement_plan=(replacement_plan or self.replacement_plan),
                canary_plan=(canary_plan or self.plan), build_identity=V076_BUILD,
                now=now,
            )
        return data, load_challenger_replacement_canary_projection_bytes(
            data, plan=self.plan,
        )

    def reduce(self, events, now="2026-09-09T00:00:00.000Z"):
        data = _project_challenger_replacement_canary(
            events=tuple(events), plan=self.plan, now=now,
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

    def test_projection_rejects_non_canary_event_that_fails_chain_validation(self):
        prefix = ({
            "event_type": "INPUT_PREPARED", "slot_id": "ETHUSDT@fixture",
            "recorded_at": "2026-08-31T20:00:00.000Z",
            "payload": {"fixture": "non-canary-authority"},
        },)
        with self.assertRaisesRegex(
            ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
        ):
            self.project(self.ceremony_events(), prefix=prefix)

    def test_stage_start_without_exact_activation_publication_is_rejected(self):
        with self.assertRaisesRegex(
            ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
        ):
            self.project(self.ceremony_events() + (self.start(),),
                         raw_stage_authority=True)

    def test_stage_start_rejects_same_activation_bytes_at_different_inode(self):
        with self.assertRaisesRegex(
            ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
        ):
            self.project(self.ceremony_events() + (self.start(),),
                         replace_first_artifact=True)

    def test_equity_claim_must_equal_strict_reconciliation(self):
        with self.assertRaisesRegex(
            ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
        ):
            self.project(self.ceremony_events() + (
                self.start(), self.mark("2026-09-02T04:00:00.000Z", "99"),
            ), reconciliation_equity_override="100")

    def test_hard_stop_string_without_exact_private_event_is_rejected(self):
        with self.assertRaisesRegex(
            ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
        ):
            self.project(self.ceremony_events() + (
                self.start(),
                self.mark(
                    "2026-09-02T04:00:00.000Z", "99", flat=False,
                    hard_stop="VENUE_LOCAL_POSITION_MISMATCH",
                ),
            ))

    def test_manufactured_cycle_mapping_without_private_lifecycle_is_rejected(self):
        with self.assertRaisesRegex(
            ChallengerReplacementCanaryControllerError,
            "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
        ):
            self.project(self.ceremony_events() + (
                self.start(),
                self.cycle("SPOT", 1, "2026-09-03T00:00:00.000Z"),
            ))

    def test_replacement_and_canary_plans_cannot_be_substituted(self):
        cases = ({"outer_plan": self.plan}, {"replacement_plan": self.plan},
                 {"canary_plan": self.replacement_plan})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(
                ChallengerReplacementCanaryControllerError,
                "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
            ):
                self.project(self.ceremony_events(), **changes)

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
        _, failed = self.reduce(events, now="2026-09-02T12:00:00.000Z")
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
        _, loaded = self.reduce(events, now="2026-09-09T00:00:00.000Z")
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
            self.reduce(premature)

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
                    ("CHALLENGER_REPLACEMENT_CANARY_EVENT_INVALID" if field ==
                     "minimum_amount_satisfied_or_null" else
                     "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID"),
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
        _, loaded = self.reduce(events, now="2026-09-09T08:00:00.000Z")
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
        _, loaded = self.reduce(events, now="2026-09-24T08:00:00.000Z")
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
        _, failed = self.reduce(events, now="2026-09-02T12:00:00.000Z")
        self.assertEqual(failed["stage_block_or_null"]["status"],
                         "STAGE_FAILED_LOCKED")
        self.assertTrue(failed["stage_block_or_null"]["flat"])
        self.assertFalse(failed["stage_block_or_null"]["flatten_required"])

        restarted = events + (self.start(
            "E0", "2026-09-02T12:00:00.000Z", previous="e0-block-1",
            unlock="incident_unlock_" + "4" * 64,
        ) | {"block_id": "e0-block-2"},)
        _, loaded = self.reduce(restarted, now="2026-09-02T16:00:00.000Z")
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
                    self.reduce(invalid)

    def test_exact_activation_and_reconciliation_identities_are_required(self):
        for events, reason in (
            (self.ceremony_events() + (
                self.start() | {"activation_id": "approval"},
            ), "CHALLENGER_REPLACEMENT_CANARY_EVENT_INVALID"),
            (({**self.ceremony_events()[0],
              "reconciliation_id": "binance_reconciliation_short"},),
             "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID"),
        ):
            with self.subTest(events=events):
                with self.assertRaisesRegex(
                    ChallengerReplacementCanaryControllerError,
                    reason,
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
            "CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID",
        ):
            self.project(invalid)


if __name__ == "__main__":
    unittest.main()
