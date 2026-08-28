import json
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import canonical_json


ROOT = Path(__file__).resolve().parents[1]


class ChallengerReplacementV3ActivationTrustTests(unittest.TestCase):
    def test_fixed_candidate_binds_releases_and_excludes_private_execution(self):
        from crypto_quant.challenger_replacement_v3_activation_trust import (
            build_fixed_v3_activation_candidate,
        )

        candidate = build_fixed_v3_activation_candidate()
        self.assertEqual(candidate["release"]["tag"], "v0.78.0")
        self.assertEqual(candidate["predecessor_release"]["tag"], "v0.77.0")
        self.assertEqual(candidate["deployment"]["release_tag"], "v0.76.0")
        self.assertLessEqual(len(candidate["snapshot_inventory"]), 256)
        forbidden = (
            "binance_private", "private_protocol", "private_runtime",
            "canary_controller", "credential_envelope",
        )
        self.assertFalse(any(
            any(word in path.lower() for word in forbidden)
            for path in candidate["snapshot_inventory"]
        ))
        self.assertEqual(
            candidate["runtime_module"],
            "crypto_quant.challenger_replacement_v3_installed_runtime",
        )
        self.assertFalse(candidate["authority"]["production_activation"])
        self.assertFalse(candidate["authority"]["real_orders_allowed"])
        self.assertIn(
            "src/crypto_quant/challenger_replacement_v3_activation_trust_cli.py",
            candidate["snapshot_inventory"],
        )

    def test_candidate_loader_requires_exact_canonical_local_identity(self):
        from crypto_quant.challenger_replacement_v3_activation_trust import (
            ChallengerReplacementV3ActivationTrustError,
            build_fixed_v3_activation_candidate,
            load_fixed_v3_activation_candidate,
        )

        candidate = build_fixed_v3_activation_candidate()
        body = canonical_json(candidate).encode()
        self.assertEqual(load_fixed_v3_activation_candidate(body), candidate)
        with self.assertRaises(ChallengerReplacementV3ActivationTrustError):
            load_fixed_v3_activation_candidate(body + b"\n")

    def test_three_schema_mirrors_are_exact_and_closed(self):
        names = (
            "challenger-replacement-v3-install-contract-v1.schema.json",
            "challenger-replacement-v3-activation-preflight-v1.schema.json",
            "challenger-replacement-v3-activation-install-receipt-v1.schema.json",
        )
        for name in names:
            packaged = ROOT / "src/crypto_quant/schemas" / name
            configured = ROOT / "config" / name
            self.assertEqual(packaged.read_bytes(), configured.read_bytes())
            schema = json.loads(packaged.read_text())
            self.assertFalse(schema["additionalProperties"])

    def test_renderer_uses_existing_secure_snapshot_and_exact_publish_only(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        candidate = trust.build_fixed_v3_activation_candidate()
        snapshot = {
            "outcome": "PUBLISHED", "root": "/fixed/snapshot/tree",
            "tree_hash": "a" * 64, "file_count": len(candidate["snapshot_inventory"]),
            "total_size_bytes": 123, "root_device": 1, "root_inode": 2,
        }
        event = {
            "path": trust.activation_paths()["event_root"], "device": 3,
            "inode": 4, "owner_uid": 501, "mode": 448,
            "initial_event_count": 0, "initial_orphan_staging_count": 0,
        }
        python = {"path": "/usr/bin/python3", "sha256": "b" * 64}
        with patch.object(trust, "_released_identity", return_value={
            "tag": "v0.78.0", "peeled_commit": "c" * 40,
            "manifest_version": "1.72.0", "manifest_hash": "d" * 64,
            "manifest_file_sha256": "e" * 64,
        }), patch.object(
            trust, "_ensure_fixed_snapshot_directories",
            return_value=Path("/fixed/snapshot"),
        ), patch.object(
            trust, "_publish_snapshot_from_inventory", return_value=snapshot,
        ) as publish_snapshot, patch.object(
            trust, "_fixed_empty_event_root_identity", return_value=event,
        ), patch.object(
            trust, "_fixed_python_identity", return_value=python,
        ), patch.object(
            trust, "_publish_contract_exact",
            side_effect=(("PUBLISHED", object()), ("PUBLISHED", object())),
        ) as publish_exact:
            rendered = trust.render_fixed_v3_activation_candidate()
        publish_snapshot.assert_called_once()
        self.assertEqual(publish_exact.call_count, 2)
        self.assertEqual(rendered["contract"]["snapshot"]["tree_hash"], "a" * 64)
        self.assertEqual(rendered["contract"]["release"]["peeled_commit"], "c" * 40)
        self.assertEqual(rendered["contract_outcome"], "PUBLISHED")

    def test_install_contract_loader_replays_canonical_semantics(self):
        from crypto_quant import challenger_replacement_v3_activation_trust as trust

        candidate = trust.build_fixed_v3_activation_candidate()
        snapshot = {
            "root": "/fixed/snapshot/tree", "tree_hash": "a" * 64,
            "file_count": len(candidate["snapshot_inventory"]),
            "total_size_bytes": 123, "root_device": 1, "root_inode": 2,
        }
        event = {
            "path": trust.activation_paths()["event_root"], "device": 3,
            "inode": 4, "owner_uid": 501, "mode": 448,
            "initial_event_count": 0, "initial_orphan_staging_count": 0,
        }
        release = {
            "tag": "v0.78.0", "peeled_commit": "c" * 40,
            "tag_object": "f" * 40, "manifest_version": "1.72.0",
            "manifest_hash": "d" * 64, "manifest_file_sha256": "e" * 64,
        }
        contract = trust._contract(
            candidate, release, snapshot, event,
            {"path": "/usr/bin/python3", "sha256": "b" * 64},
        )
        body = canonical_json(contract).encode()
        self.assertEqual(trust.load_fixed_v3_install_contract_bytes(body), contract)
        altered = json.loads(body)
        altered["runtime"]["module"] = "not.allowed"
        altered["contract_hash"] = "0" * 64
        with self.assertRaises(trust.ChallengerReplacementV3ActivationTrustError):
            trust.load_fixed_v3_install_contract_bytes(canonical_json(altered).encode())


if __name__ == "__main__":
    unittest.main()
