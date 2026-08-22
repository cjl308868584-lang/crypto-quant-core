import json
import hashlib
import os
import plistlib
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / "config/challenger-replacement-deployment-v1.schema.json"
PACKAGE_SCHEMA = ROOT / "src/crypto_quant/schemas/challenger-replacement-deployment-v1.schema.json"
ARTIFACT = ROOT / "artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json"
PLIST = ROOT / "artifacts/challenger-replacement/local.crypto-quant.challenger-replacement-v1.plist"


class DeploymentCandidateTests(unittest.TestCase):
    def test_schema_mirrors_and_candidate_has_fixed_identity(self):
        from crypto_quant.challenger_replacement_deployment import (
            build_challenger_replacement_deployment,
        )

        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        schema = json.loads(CONFIG_SCHEMA.read_text())
        Draft202012Validator.check_schema(schema)
        deployment = build_challenger_replacement_deployment()
        self.assertEqual(deployment["foundation"]["tag_object"],
                         "3b7ee80d0b6eb5e57934bd5b6cecf837e0a562d6")
        self.assertEqual(deployment["foundation"]["main_ci_run"], 32554406969)
        self.assertEqual(deployment["candidate_release"], {
            "release_tag": "v0.67.0",
            "package_version": "0.67.0",
            "manifest_version": "1.61.0",
        })
        self.assertNotIn("manifest_hash", deployment["candidate_release"])
        self.assertNotIn("peeled_commit", deployment["candidate_release"])
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(deployment)), [])

    def test_plist_has_exact_no_argument_schedule_and_safety_boundary(self):
        from crypto_quant.challenger_replacement_deployment import (
            build_challenger_replacement_deployment,
            render_challenger_replacement_plist,
        )

        deployment = build_challenger_replacement_deployment()
        plist_bytes = render_challenger_replacement_plist(deployment)
        plist = plistlib.loads(plist_bytes)
        self.assertEqual(plist["RunAtLoad"], False)
        self.assertEqual(plist["KeepAlive"], False)
        self.assertEqual(plist["ProcessType"], "Background")
        self.assertEqual(plist["Umask"], 0o077)
        self.assertEqual(plist["StartCalendarInterval"], [
            {"Hour": hour, "Minute": 2} for hour in (0, 4, 8, 12, 16, 20)
        ])
        self.assertEqual(plist["ProgramArguments"][1:], [
            "-m", "crypto_quant.challenger_replacement_live_runtime_cli"
        ])
        self.assertNotIn("/bin/sh", plist_bytes.decode())
        self.assertNotIn("--", plist_bytes.decode())
        self.assertEqual(render_challenger_replacement_plist(deployment), plist_bytes)

    def test_loader_replays_exact_candidate_and_manifest_bindings(self):
        from crypto_quant.canonical import canonical_json
        from crypto_quant.challenger_replacement_deployment import (
            build_challenger_replacement_deployment,
            challenger_replacement_deployment_bytes,
            load_challenger_replacement_deployment,
            render_challenger_replacement_plist,
        )

        deployment = build_challenger_replacement_deployment()
        body = challenger_replacement_deployment_bytes()
        plist_bytes = render_challenger_replacement_plist(deployment)
        required = deployment["source_file_allowlist"] + [
            "artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json",
            "artifacts/challenger-replacement/local.crypto-quant.challenger-replacement-v1.plist",
            "config/challenger-replacement-deployment-v1.schema.json",
            "src/crypto_quant/challenger_replacement_deployment.py",
        ]
        manifest = {
            "manifest_version": "1.61.0",
            "file_hashes": {name: "a" * 64 for name in required},
        }
        manifest["file_hashes"][required[-4]] = hashlib.sha256(body).hexdigest()
        manifest["file_hashes"][required[-3]] = hashlib.sha256(plist_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            deployment_path = Path(directory) / "deployment.json"
            manifest_path = Path(directory) / "manifest.json"
            deployment_path.write_bytes(body)
            manifest_path.write_bytes(canonical_json(manifest).encode())
            os.chmod(deployment_path, 0o600)
            os.chmod(manifest_path, 0o600)
            with self.assertRaisesRegex(
                ValueError, "CHALLENGER_REPLACEMENT_DEPLOYMENT_MANIFEST_INVALID"
            ):
                load_challenger_replacement_deployment(
                    deployment_path, manifest_path=manifest_path
                )

    def test_committed_candidates_equal_deterministic_builders(self):
        from crypto_quant.challenger_replacement_deployment import (
            build_challenger_replacement_deployment,
            challenger_replacement_deployment_bytes,
            render_challenger_replacement_plist,
        )

        deployment = build_challenger_replacement_deployment()
        self.assertEqual(ARTIFACT.read_bytes(), challenger_replacement_deployment_bytes())
        self.assertEqual(PLIST.read_bytes(), render_challenger_replacement_plist(deployment))

    def test_committed_candidate_loads_only_through_complete_build_manifest(self):
        from crypto_quant.challenger_replacement_deployment import (
            build_challenger_replacement_deployment,
            load_challenger_replacement_deployment,
        )

        self.assertEqual(
            load_challenger_replacement_deployment(
                ARTIFACT,
                manifest_path=ROOT / "config/evaluator-build-manifest-v1.json",
            ),
            build_challenger_replacement_deployment(),
        )


if __name__ == "__main__":
    unittest.main()
