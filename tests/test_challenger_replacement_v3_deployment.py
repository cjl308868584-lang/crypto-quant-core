import ast
import hashlib
import plistlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy

from crypto_quant.canonical import business_hash, canonical_json
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
from crypto_quant.challenger_replacement_public_market_capture import (
    _validate_build,
)
from crypto_quant.challenger_replacement_v3_deployment import (
    ChallengerReplacementV3DeploymentError,
    build_challenger_replacement_v3_deployment,
    load_challenger_replacement_v3_deployment_bytes,
    render_challenger_replacement_v3_plist,
    _CORE_PATHS,
)
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan
PREDECESSOR_RELEASE = {
    "repository": "cjl308868584-lang/crypto-quant-core",
    "visibility": "PUBLIC",
    "release_tag": "v0.75.0",
    "tag_object": "4bd4b2e21c760d6fad2a27903c67ee509ac116c9",
    "peeled_commit": "a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5",
    "package_version": "0.75.0",
    "manifest_version": "1.69.0",
    "manifest_hash": "b15479590536c302e173a41a758c9113cd7452b0000d8b6c5cb5c2ad8b9404d9",
    "manifest_file_sha256": "df1695827975cbeb9c094b8182839e132219a52a19dc4166677a742d48442220",
    "build_input_tree_hash": "07812c0a352dabab3742aa1c3417eaa8a8363e46a5059e49323f2b1c0d8a4a78",
    "main_ci_run": 32869868571,
}
INVENTORY = {
    path: hashlib.sha256(path.encode("utf-8")).hexdigest()
    for path in sorted(_CORE_PATHS)
}
CANDIDATE_BUILD = {
    "reviewed_code_checkpoint": "7" * 40,
    "package_version": "0.76.0",
    "predecessor_manifest_identity": PREDECESSOR_RELEASE,
    "executable_core_hash": business_hash(INVENTORY),
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
            public_contract=self.public, build_identity=CANDIDATE_BUILD,
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
                public_contract=self.public, build_identity=CANDIDATE_BUILD,
                strategy_inventory=INVENTORY,
            ),
            deployment,
        )
        self.assertEqual(deployment, self.build())
        self.assertEqual(deployment["executable_core_identity"], INVENTORY)
        self.assertEqual(deployment["candidate_build"], CANDIDATE_BUILD)
        self.assertNotIn("release_tag", deployment["candidate_build"])
        self.assertNotIn("manifest_hash", deployment["candidate_build"])
        self.assertEqual(deployment["authority"], {
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "real_orders_allowed": False,
            "fund_movement_allowed": False,
        })

    def test_formal_identity_replays_through_fixed_loader_and_capture_boundary(self):
        deployment = self.build()
        body = canonical_json(deployment).encode("utf-8")
        self.assertEqual(
            load_challenger_replacement_v3_deployment_bytes(
                body, predecessor_release=PREDECESSOR_RELEASE,
                plan=self.plan, economic_plan=self.economic,
                accelerated_plan=self.accelerated,
                predecessor_contract=self.predecessor,
                public_contract=self.public,
                build_identity=deployment["candidate_build"],
                strategy_inventory=INVENTORY,
            ),
            deployment,
        )
        _validate_build(deployment["candidate_build"])

    def test_inventory_covers_recursive_local_imports_and_v076_resources(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        pending = [path for path in _CORE_PATHS if path.endswith(".py")]
        closure = set()
        while pending:
            path = pending.pop()
            if path in closure:
                continue
            closure.add(path)
            tree = ast.parse((root / path).read_text(encoding="utf-8"))
            module = path[len("src/crypto_quant/"):-3].replace("/", ".")
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level:
                    base = module.split(".")[:-node.level]
                    name = ".".join(base + ([node.module] if node.module else []))
                    candidates = [name] + [
                        ".".join(filter(None, (name, alias.name)))
                        for alias in node.names
                    ]
                    for candidate in candidates:
                        imported = "src/crypto_quant/" + candidate.replace(".", "/") + ".py"
                        if (root / imported).is_file() and imported not in closure:
                            pending.append(imported)
        self.assertEqual(closure - _CORE_PATHS, set())
        for path in (
            "src/crypto_quant/schemas/challenger-replacement-public-market-capture-v2.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-public-simulation-contract-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-public-simulation-input-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-public-simulation-snapshot-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-public-simulation-result-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-v3-deployment-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-v3-start-receipt-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-fault-matrix-receipt-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-operational-qualification-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-economic-evaluation-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-plan-v3.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-economic-evaluation-plan-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-accelerated-canary-plan-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-simulation-contract-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-live-capture-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-binance-simulation-input-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-plan-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-plan-v2.schema.json",
            "artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json",
            "src/crypto_quant/schemas/operations-projection-v3.schema.json",
            "src/crypto_quant/fixtures/challenger-replacement-v076/binance-lifecycle-long-input.json",
        ):
            self.assertIn(path, _CORE_PATHS)

    def test_inventory_snapshot_can_build_v2_plan_in_a_fresh_process(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="cq-v076-core-") as directory:
            snapshot = __import__("pathlib").Path(directory)
            for relative in _CORE_PATHS:
                target = snapshot / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / relative, target)
            environment = dict(os.environ, PYTHONPATH=str(snapshot / "src"))
            result = subprocess.run([
                sys.executable, "-c",
                "from crypto_quant.challenger_replacement_plan_v2 import "
                "build_challenger_replacement_plan_v2 as build; build()",
            ], cwd=snapshot, env=environment, capture_output=True, text=True,
               timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

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
        wrong_build = deepcopy(CANDIDATE_BUILD)
        wrong_build["package_version"] = "0.75.0"
        wrong_inventory = dict(INVENTORY)
        wrong_inventory.pop(next(iter(wrong_inventory)))
        for build, inventory in (
            (wrong_build, INVENTORY), (CANDIDATE_BUILD, wrong_inventory)
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

    def test_non_mapping_inventory_uses_fixed_domain_error(self):
        for inventory in (None, []):
            with self.subTest(inventory=inventory), self.assertRaisesRegex(
                ChallengerReplacementV3DeploymentError,
                "^CHALLENGER_REPLACEMENT_V3_DEPLOYMENT_INVALID$",
            ):
                build_challenger_replacement_v3_deployment(
                    predecessor_release=PREDECESSOR_RELEASE,
                    plan=self.plan, economic_plan=self.economic,
                    accelerated_plan=self.accelerated,
                    predecessor_contract=self.predecessor,
                    public_contract=self.public,
                    build_identity=CANDIDATE_BUILD,
                    strategy_inventory=inventory,
                )


if __name__ == "__main__":
    unittest.main()
