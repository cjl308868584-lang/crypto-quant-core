import plistlib
import unittest
from copy import deepcopy

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from crypto_quant.challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from crypto_quant.challenger_replacement_v3_deployment import (
    ChallengerReplacementV3DeploymentError,
    build_challenger_replacement_v3_deployment,
    load_challenger_replacement_v3_deployment_bytes,
    render_challenger_replacement_v3_plist,
)
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan
from tests.test_challenger_replacement_public_market_capture import V076_BUILD


PREDECESSOR_RELEASE = {
    "release_tag": "v0.75.0",
    "peeled_commit": "a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5",
    "package_version": "0.75.0",
    "manifest_version": "1.69.0",
    "manifest_hash": "b15479590536c302e173a41a758c9113cd7452b0000d8b6c5cb5c2ad8b9404d9",
}
INVENTORY = {
    path: str(index) * 64
    for index, path in enumerate((
        "src/crypto_quant/challenger_replacement_events.py",
        "src/crypto_quant/challenger_replacement_opportunity_projection.py",
        "src/crypto_quant/challenger_replacement_public_market_capture.py",
        "src/crypto_quant/challenger_replacement_public_simulation.py",
        "src/crypto_quant/challenger_replacement_v3_runtime.py",
    ), 1)
}


class ChallengerReplacementV3DeploymentTests(unittest.TestCase):
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

    def build(self):
        return build_challenger_replacement_v3_deployment(
            predecessor_release=PREDECESSOR_RELEASE,
            plan=self.plan, economic_plan=self.economic,
            accelerated_plan=self.accelerated,
            predecessor_contract=self.predecessor,
            public_contract=self.public, build_identity=V076_BUILD,
            strategy_inventory=INVENTORY,
        )

    def test_candidate_is_deterministic_safe_and_strictly_replayable(self):
        deployment = self.build()
        body = canonical_json(deployment).encode("utf-8")

        self.assertEqual(
            load_challenger_replacement_v3_deployment_bytes(
                body, predecessor_release=PREDECESSOR_RELEASE,
                plan=self.plan, economic_plan=self.economic,
                accelerated_plan=self.accelerated,
                predecessor_contract=self.predecessor,
                public_contract=self.public, build_identity=V076_BUILD,
                strategy_inventory=INVENTORY,
            ),
            deployment,
        )
        self.assertEqual(deployment, self.build())
        self.assertEqual(deployment["executable_core_identity"], INVENTORY)
        self.assertEqual(deployment["authority"], {
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "real_orders_allowed": False,
            "fund_movement_allowed": False,
        })

    def test_plist_retains_six_natural_invocations_and_no_secret_surface(self):
        plist_bytes = render_challenger_replacement_v3_plist(self.build())
        plist = plistlib.loads(plist_bytes)

        self.assertFalse(plist["RunAtLoad"])
        self.assertFalse(plist["KeepAlive"])
        self.assertEqual(plist["StartCalendarInterval"], [
            {"Hour": hour, "Minute": 2} for hour in (0, 4, 8, 12, 16, 20)
        ])
        self.assertEqual(
            plist["Label"], "local.crypto-quant.challenger-replacement-v1"
        )
        self.assertEqual(plist["ProgramArguments"][1:], [
            "-m", "crypto_quant.challenger_replacement_v3_runtime",
        ])
        lowered = plist_bytes.lower()
        for forbidden in (b"api_key", b"secret", b"account", b"order"):
            self.assertNotIn(forbidden, lowered)

    def test_wrong_build_or_inventory_fails_before_candidate_construction(self):
        wrong_build = deepcopy(V076_BUILD)
        wrong_build["package_version"] = "0.75.0"
        wrong_inventory = dict(INVENTORY)
        wrong_inventory.pop(next(iter(wrong_inventory)))
        for build, inventory in (
            (wrong_build, INVENTORY), (V076_BUILD, wrong_inventory)
        ):
            with self.subTest(build=build["package_version"], count=len(inventory)), self.assertRaises(
                ChallengerReplacementV3DeploymentError
            ):
                build_challenger_replacement_v3_deployment(
                    predecessor_release=PREDECESSOR_RELEASE,
                    plan=self.plan, economic_plan=self.economic,
                    accelerated_plan=self.accelerated,
                    predecessor_contract=self.predecessor,
                    public_contract=self.public, build_identity=build,
                    strategy_inventory=inventory,
                )


if __name__ == "__main__":
    unittest.main()
