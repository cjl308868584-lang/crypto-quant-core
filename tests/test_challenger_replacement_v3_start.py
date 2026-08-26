import unittest
from copy import deepcopy
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_events import (
    ChallengerReplacementEventRootIdentity,
    open_challenger_replacement_event_root,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from crypto_quant.challenger_replacement_public_market_capture import (
    load_challenger_replacement_public_market_capture_bytes,
)
from crypto_quant.challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from crypto_quant.challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from crypto_quant.challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.challenger_replacement_v3_deployment import (
    build_challenger_replacement_v3_deployment,
)
from crypto_quant.challenger_replacement_v3_runtime import (
    run_challenger_replacement_v3_opportunity,
)
from crypto_quant.challenger_replacement_v3_start import (
    ChallengerReplacementV3StartError,
    build_challenger_replacement_v3_start_receipt,
    load_challenger_replacement_v3_start_receipt_bytes,
)
from tests.test_challenger_replacement_events import EventWorkspace
from tests.test_challenger_replacement_public_market_capture import (
    COMMITTED_CAPTURE,
    V076_BUILD,
)
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan
from tests.test_challenger_replacement_v3_deployment import (
    CANDIDATE_BUILD, INVENTORY, PREDECESSOR_RELEASE,
)


class ChallengerReplacementV3StartTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_v3_plan()
        self.economic = build_challenger_replacement_economic_plan()
        self.accelerated = build_challenger_replacement_accelerated_canary_plan()
        self.predecessor = build_challenger_replacement_simulation_contract(
            plan=self.plan
        )
        self.public = build_challenger_replacement_public_simulation_contract(
            plan=self.plan, economic_plan=self.economic,
            predecessor_contract=self.predecessor,
        )
        self.workspace = EventWorkspace()
        self.addCleanup(self.workspace.close)

    def build(self):
        return build_challenger_replacement_v3_deployment(
            predecessor_release=PREDECESSOR_RELEASE, plan=self.plan,
            economic_plan=self.economic, accelerated_plan=self.accelerated,
            predecessor_contract=self.predecessor,
            public_contract=self.public, build_identity=CANDIDATE_BUILD,
            strategy_inventory=INVENTORY,
        )

    def test_first_observed_event_binds_operational_and_economic_clocks(self):
        deployment = self.build()
        capture = load_challenger_replacement_public_market_capture_bytes(
            COMMITTED_CAPTURE.read_bytes(), plan=self.plan,
            build_identity=V076_BUILD, previous_source_bundle=None,
        )
        identity = self.workspace.identity()
        with open_challenger_replacement_event_root(identity) as root:
            state = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            )
            with patch(
                "crypto_quant.challenger_replacement_v3_runtime._acquire",
                return_value=capture,
            ):
                run_challenger_replacement_v3_opportunity(
                    state=state, event_root=root, plan=self.plan,
                    economic_plan=self.economic,
                    predecessor_contract=self.predecessor,
                    public_contract=self.public, build_identity=V076_BUILD,
                )
            projection = state._replay()

        bound_identity = ChallengerReplacementEventRootIdentity(
            absolute_path=deployment["paths"]["event_root"],
            device=identity.device, inode=identity.inode, uid=identity.uid,
            mode_octal=identity.mode_octal,
        )

        receipt = build_challenger_replacement_v3_start_receipt(
            deployment=deployment,
            event_projection=projection,
            event_root_identity=bound_identity,
        )
        observed = projection["events"][2]
        body = canonical_json(receipt).encode("utf-8")

        self.assertEqual(
            receipt["operational_start"]["observed_at"],
            "2026-08-26T04:05:00.000Z",
        )
        self.assertEqual(
            receipt["economic_start"]["scheduled_for"],
            "2026-08-26T04:00:00.000Z",
        )
        self.assertEqual(receipt["shared_event_hash"], observed.event_hash)
        self.assertNotIn("required_slot_count", receipt)
        self.assertNotIn("required_slot_count", receipt["economic_start"])
        self.assertEqual(
            load_challenger_replacement_v3_start_receipt_bytes(
                body, deployment=deployment,
                event_projection=projection,
                event_root_identity=bound_identity,
            ),
            receipt,
        )

        changed = deepcopy(receipt)
        changed["$schema"] = "./challenger-replacement-start-receipt-v1.schema.json"
        with self.assertRaises(ChallengerReplacementV3StartError):
            load_challenger_replacement_v3_start_receipt_bytes(
                canonical_json(changed).encode("utf-8"), deployment=deployment,
                event_projection=projection, event_root_identity=bound_identity,
            )

        with self.assertRaises(ChallengerReplacementV3StartError):
            build_challenger_replacement_v3_start_receipt(
                deployment=deployment, event_projection=projection,
                event_root_identity=identity,
            )

    def test_no_observed_event_cannot_create_a_start_receipt(self):
        identity = self.workspace.identity()
        with open_challenger_replacement_event_root(identity) as root:
            projection = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            )._replay()
        deployment = self.build()
        bound_identity = ChallengerReplacementEventRootIdentity(
            absolute_path=deployment["paths"]["event_root"],
            device=identity.device, inode=identity.inode, uid=identity.uid,
            mode_octal=identity.mode_octal,
        )
        with self.assertRaisesRegex(
            ChallengerReplacementV3StartError,
            "CHALLENGER_REPLACEMENT_V3_START_NOT_READY",
        ):
            build_challenger_replacement_v3_start_receipt(
                deployment=deployment, event_projection=projection,
                event_root_identity=bound_identity,
            )


if __name__ == "__main__":
    unittest.main()
