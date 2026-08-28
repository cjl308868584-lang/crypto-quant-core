import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import crypto_quant
from crypto_quant.canonical import business_hash
from crypto_quant.challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from crypto_quant.challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from crypto_quant.challenger_replacement_fault_matrix import (
    load_challenger_replacement_fault_matrix_bytes,
)
from crypto_quant.challenger_replacement_plan_v3 import (
    build_challenger_replacement_plan_v3,
)
from crypto_quant.challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.challenger_replacement_v3_deployment import (
    _CORE_PATHS, _PREDECESSOR,
    load_challenger_replacement_v3_deployment_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "artifacts/challenger-replacement/challenger-replacement-v3-deployment-v0.76.0.json"
FAULT_RECEIPT = ROOT / "artifacts/challenger-replacement/challenger-replacement-fault-matrix-v0.76.0.json"
STATUS = ROOT / "docs/implementation-status-v0.76.0.md"

V076_MODULES = (
    "challenger_replacement_public_http.py",
    "challenger_replacement_public_market_capture.py",
    "challenger_replacement_public_simulation.py",
    "challenger_replacement_public_simulation_contract.py",
    "challenger_replacement_v3_runtime.py",
    "challenger_replacement_v3_deployment.py",
    "challenger_replacement_v3_start.py",
    "challenger_replacement_fault_matrix.py",
    "challenger_replacement_operational_qualification.py",
    "challenger_replacement_economic_evaluation.py",
    "challenger_replacement_economic_evaluation_cli.py",
    "challenger_replacement_v3_observer.py",
    "operations_projection_v3.py",
)


class V076ReleaseMetadataTests(unittest.TestCase):
    def test_runtime_fixture_is_present_in_wheel_and_sdist(self):
        member = (
            "crypto_quant/fixtures/challenger-replacement-v076/"
            "binance-lifecycle-long-input.json"
        )
        with tempfile.TemporaryDirectory(prefix="cq-v076-package-") as directory:
            candidate = Path(directory) / "candidate"
            shutil.copytree(ROOT / "src", candidate / "src")
            for name in ("README.md", "pyproject.toml", "setup.py"):
                shutil.copy2(ROOT / name, candidate / name)
            dist = candidate / "dist"
            result = subprocess.run(
                [
                    sys.executable, "setup.py", "--quiet", "sdist",
                    "bdist_wheel", "--dist-dir", str(dist),
                ],
                cwd=candidate, capture_output=True, text=True,
                timeout=60, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            wheel = next(dist.glob("*.whl"))
            source = next(dist.glob("*.tar.gz"))
            with zipfile.ZipFile(wheel) as archive:
                self.assertIn(member, archive.namelist())
            with tarfile.open(source) as archive:
                self.assertTrue(any(
                    name.endswith("/src/" + member)
                    for name in archive.getnames()
                ))

    def test_formal_deployment_and_fault_receipt_replay_exact_runtime_bytes(self):
        deployment_bytes = DEPLOYMENT.read_bytes()
        deployment_header = json.loads(deployment_bytes)
        core = deployment_header["executable_core_identity"]
        self.assertEqual(set(core), _CORE_PATHS)
        for path, digest in core.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        plan = build_challenger_replacement_plan_v3()
        economic = build_challenger_replacement_economic_plan()
        accelerated = build_challenger_replacement_accelerated_canary_plan()
        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        public = build_challenger_replacement_public_simulation_contract(
            plan=plan, economic_plan=economic, predecessor_contract=predecessor,
        )
        deployment = load_challenger_replacement_v3_deployment_bytes(
            deployment_bytes, predecessor_release=_PREDECESSOR, plan=plan,
            economic_plan=economic, accelerated_plan=accelerated,
            predecessor_contract=predecessor, public_contract=public,
            build_identity=deployment_header["candidate_build"],
            strategy_inventory=core,
        )
        self.assertEqual(deployment["candidate_build"], {
            "reviewed_code_checkpoint":
                "1cfddb9a6455416903f4e967ca5d4eb036f01409",
            "package_version": "0.76.0",
            "predecessor_manifest_identity": _PREDECESSOR,
            "executable_core_hash": business_hash(core),
        })
        self.assertEqual(
            hashlib.sha256(deployment_bytes).hexdigest(),
            "28eec0ee5f424952ee96e0c711abc68d7d1cab592859515ba8f79958971d288b",
        )
        fault_bytes = FAULT_RECEIPT.read_bytes()
        fault_header = json.loads(fault_bytes)
        runtime_core = dict(core)
        runtime_core[str(DEPLOYMENT.relative_to(ROOT))] = hashlib.sha256(
            deployment_bytes
        ).hexdigest()
        self.assertEqual(fault_header["runtime_core_identity"], runtime_core)
        self.assertEqual(fault_header["executable_core_hash"], business_hash(core))
        self.assertEqual(
            hashlib.sha256(fault_bytes).hexdigest(),
            "98c900ca8cba6afb8c79c06be2487baa52ea6d2a113dbcffc5d9bb961bf96226",
        )
        self.assertEqual(
            load_challenger_replacement_fault_matrix_bytes(
                fault_bytes, build_identity=deployment["candidate_build"],
                runtime_core_identity=runtime_core,
            ),
            fault_header,
        )

    def test_versions_status_and_formal_files_are_exact(self):
        self.assertEqual(crypto_quant.__version__, "0.76.0")
        self.assertRegex(
            (ROOT / "pyproject.toml").read_text(),
            r'(?m)^version = "0\.76\.0"$',
        )
        self.assertRegex((ROOT / "setup.py").read_text(), r'version="0\.76\.0"')
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(
            (manifest["package_version"], manifest["manifest_version"]),
            ("0.76.0", "1.70.0"),
        )
        self.assertTrue(DEPLOYMENT.is_file())
        self.assertTrue(FAULT_RECEIPT.is_file())
        status = STATUS.read_text()
        for claim in (
            "PUBLIC_SIMULATION_AND_RESEARCH_CODE_RELEASED_NOT_ACTIVATED",
            "CODE_COMPLETE_NOT_ACTIVATED_NOT_YET_REACHED",
            "production_activation=false",
            "runtime_install_authorized=false",
            "replacement_start_authorized=false",
            "credentials_allowed=false",
            "account_requests_allowed=false",
            "real_orders_allowed=false",
            "fund_movement_allowed=false",
            "production_state_writes=0",
            "economic_outcome_reads=0",
            "no 72-hour timer started",
            "no 90-day timer started",
            "no profitability or AI-advantage conclusion",
        ):
            self.assertIn(claim, status)

    def test_manifest_inventory_contains_every_v076_release_input(self):
        from crypto_quant.build import EvaluatorBuild, _V076_RELEASE_PATHS

        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        self.assertEqual(set(_V076_RELEASE_PATHS) - expected, set())
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(set(manifest["file_hashes"]), expected)

    def test_v076_python_size_and_capability_boundaries(self):
        source = ROOT / "src/crypto_quant"
        total = sum(len((source / name).read_text().splitlines()) for name in V076_MODULES)
        self.assertLessEqual(total, 5_000)
        forbidden_imports = {"requests", "aiohttp", "websockets", "ccxt", "binance"}
        forbidden_text = {
            "X-MBX-APIKEY", "api_key", "secret_key", "withdraw",
            "/api/v3/order", "/fapi/v1/order", "launchctl bootstrap",
        }
        for name in V076_MODULES:
            path = source / name
            tree = ast.parse(path.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertEqual(imported & forbidden_imports, set(), name)
            text = path.read_text()
            checked = forbidden_text - (
                {"api_key"} if name == "challenger_replacement_public_http.py"
                else set()
            )
            self.assertEqual({token for token in checked if token in text}, set(), name)


if __name__ == "__main__":
    unittest.main()
