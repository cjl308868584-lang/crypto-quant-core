import json
import unittest
from copy import deepcopy
from pathlib import Path

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.challenger_replacement_v3_observer import (
    ChallengerReplacementV3Observation,
)
from crypto_quant.operations_projection_v3 import (
    OperationsProjectionV3Error,
    build_operations_projection_v3,
    load_operations_projection_v3_bytes,
)
from tests.test_challenger_replacement_public_market_capture import V076_BUILD


ROOT = Path(__file__).resolve().parents[1]


def observation(*, operational="ACTIVE", health="HEALTHY", missed=1):
    terminal = 7
    observed = terminal - missed
    snapshot = {
        "position_state": "FLAT", "reconciliation_status": "MATCHED",
        "risk_state": "RISK_CLEAR", "economic_gap_locked": False,
        "protective_stop_or_null": None,
    }
    return ChallengerReplacementV3Observation(
        deployment={
            "deployment_id": "challenger_replacement_v3_deployment_" + "1" * 64,
            "deployment_hash": "2" * 64,
            "build_identity": deepcopy(V076_BUILD),
            "status": "V3_DEPLOYMENT_CANDIDATE_NOT_INSTALLABLE_NOT_ACTIVATED",
            "authority": {"production_activation": False,
                          "runtime_install_authorized": False,
                          "replacement_start_authorized": False,
                          "credentials_allowed": False,
                          "account_requests_allowed": False,
                          "broker_requests_allowed": False,
                          "real_orders_allowed": False,
                          "fund_movement_allowed": False},
        },
        start_receipt_or_null={"receipt_id": "r", "receipt_hash": "3" * 64},
        event_projection={
            "events": (), "opportunities": {},
            "terminal_opportunity_count": terminal,
            "observed_opportunity_count": observed,
            "missed_opportunity_count": missed,
            "latest_next_snapshot_or_null": snapshot,
        },
        operational_qualification={
            "status": operational, "eligible_continuous_seconds": 86_400,
            "final_segment_id_or_null": "segment-1", "reason_codes": [],
            "bindings": {"fault_receipt_id": "f", "fault_receipt_hash": "4" * 64},
        },
        economic_progress={
            "status": "TAIL_BLIND", "due_opportunity_count": terminal,
            "terminal_opportunity_count": terminal,
            "observed_opportunity_count": observed,
            "missed_opportunity_count": missed,
            "elapsed_complete_days": 1,
            "next_required_opportunity": "ETHUSDT@2026-09-02T04:00:00.000Z",
            "evidence_health": "HEALTHY",
        },
        evidence_health=health,
    )


class OperationsProjectionV3Tests(unittest.TestCase):
    def test_schema_mirror_build_load_and_tail_blind_shape(self):
        package = ROOT / "src/crypto_quant/schemas/operations-projection-v3.schema.json"
        config = ROOT / "config/operations-projection-v3.schema.json"
        self.assertEqual(package.read_bytes(), config.read_bytes())
        value = build_operations_projection_v3(
            observation(), build_identity=V076_BUILD
        )
        body = canonical_json(value).encode("utf-8")
        self.assertEqual(
            load_operations_projection_v3_bytes(
                body, observation=observation(), build_identity=V076_BUILD
            ),
            value,
        )
        self.assertEqual((value["$schema"], value["schema_version"]),
                         ("./operations-projection-v3.schema.json", "3.0.0"))
        self.assertFalse(any(value["authority"].values()))
        forbidden = (
            "pnl", "profit", "return", "drawdown", "fee", "funding",
            "confidence", "bootstrap", "power", "rank", "pass",
        )
        def assert_tail_blind(item, *, key=""):
            if isinstance(item, dict):
                for child_key, child in item.items():
                    lowered_key = child_key.lower()
                    self.assertTrue(
                        all(token not in lowered_key for token in forbidden),
                        child_key,
                    )
                    assert_tail_blind(child, key=child_key)
            elif isinstance(item, list):
                for child in item:
                    assert_tail_blind(child, key=key)
            elif isinstance(item, str) and not (
                key.endswith("_hash")
                or key.endswith("_hash_or_null")
                or key == "projection_hash"
            ):
                lowered = item.lower()
                self.assertTrue(
                    all(token not in lowered for token in forbidden), item
                )

        assert_tail_blind(value)

    def test_all_operational_states_and_counts_are_projection_only(self):
        for state in (
            "NOT_STARTED", "ACTIVE", "INTERRUPTED_RECOVERABLE",
            "BLOCK_FAILED", "QUALIFIED",
        ):
            value = build_operations_projection_v3(
                observation(operational=state), build_identity=V076_BUILD
            )
            self.assertEqual(value["operational_qualification"]["status"], state)
            self.assertEqual(value["opportunities"], {
                "due": 7, "terminal": 7, "observed": 6, "missed": 1,
            })
            self.assertFalse(value["authority"]["new_risk_authorized"])

    def test_mutation_wrong_build_and_inconsistent_counts_fail_closed(self):
        current = observation()
        value = build_operations_projection_v3(current, build_identity=V076_BUILD)
        changed = deepcopy(value)
        changed["authority"]["new_risk_authorized"] = True
        with self.assertRaises(OperationsProjectionV3Error):
            load_operations_projection_v3_bytes(
                canonical_json(changed).encode("utf-8"),
                observation=current, build_identity=V076_BUILD,
            )
        other = dict(V076_BUILD, peeled_commit="6" * 40)
        with self.assertRaises(OperationsProjectionV3Error):
            build_operations_projection_v3(current, build_identity=other)
        broken = observation()
        broken.event_projection["missed_opportunity_count"] = 2
        with self.assertRaises(OperationsProjectionV3Error):
            build_operations_projection_v3(broken, build_identity=V076_BUILD)

    def test_standalone_loader_rejects_unknown_nested_fields_even_with_new_hash(self):
        value = build_operations_projection_v3(
            observation(), build_identity=V076_BUILD
        )
        value["economic_progress"]["private_result"] = "withheld"
        value["projection_hash"] = business_hash({
            "purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V3",
            **{key: item for key, item in value.items()
               if key != "projection_hash"},
        })
        with self.assertRaises(OperationsProjectionV3Error):
            load_operations_projection_v3_bytes(
                canonical_json(value).encode("utf-8")
            )


if __name__ == "__main__":
    unittest.main()
