import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class ChallengerReplacementV3ActivationStartTests(unittest.TestCase):
    def install(self):
        large = 2**60 + 123
        contract = {
            "deployment": {"deployment_id": "dep", "deployment_hash": "a" * 64},
            "event_root": {"path": "/fixed/events",
                           "device": str(large + 1), "inode": str(large + 2),
                           "owner_uid": 501},
            "paths": {"start_receipt_root": "/fixed/start"},
        }
        receipt = {"receipt_id": "challenger_replacement_v3_activation_install_" + "b" * 64,
                   "receipt_hash": "c" * 64}
        return {"contract": contract}, receipt, b"install"

    def observation(self):
        return SimpleNamespace(
            deployment={"deployment_id": "dep", "deployment_hash": "a" * 64},
            start_receipt_or_null=None, event_projection={"events": ()},
            evidence_health="HEALTHY",
        )

    def test_not_ready_returns_waiting_without_publication(self):
        from crypto_quant import challenger_replacement_v3_activation_start as module
        from crypto_quant.challenger_replacement_v3_start import ChallengerReplacementV3StartError

        with patch.object(module, "_load_fixed_successful_install_receipt", return_value=self.install()), \
             patch.object(module, "observe_challenger_replacement_v3", return_value=self.observation()), \
             patch.object(module, "build_challenger_replacement_v3_start_receipt",
                          side_effect=ChallengerReplacementV3StartError("CHALLENGER_REPLACEMENT_V3_START_NOT_READY")), \
             patch.object(module, "_publish_contract_exact") as publish:
            result = module.publish_fixed_v3_start_receipt()
        self.assertEqual(result["status"], "WAITING_FOR_FIRST_NATURAL_OBSERVED")
        publish.assert_not_called()

    def test_ready_receipt_publishes_fixed_name_and_install_binding(self):
        from crypto_quant import challenger_replacement_v3_activation_start as module

        receipt = {"receipt_id": "start", "install_receipt_binding": {
            "receipt_id": self.install()[1]["receipt_id"],
            "receipt_hash": "c" * 64,
            "file_sha256": hashlib.sha256(b"install").hexdigest(),
        }}
        with patch.object(module, "_load_fixed_successful_install_receipt", return_value=self.install()), \
             patch.object(module, "observe_challenger_replacement_v3", return_value=self.observation()), \
             patch.object(module, "build_challenger_replacement_v3_start_receipt", return_value=receipt) as build, \
             patch.object(module, "load_challenger_replacement_v3_start_receipt_bytes", return_value=receipt), \
             patch.object(module, "_publish_contract_exact", return_value=("PUBLISHED", object())) as publish:
            result = module.publish_fixed_v3_start_receipt()
        self.assertEqual(result["status"], "START_RECEIPT_PUBLISHED")
        self.assertEqual(publish.call_args.args[1],
                         "challenger-replacement-v3-start-receipt-v1.json")
        self.assertEqual(build.call_args.kwargs["install_receipt_binding"],
                         receipt["install_receipt_binding"])
        identity = build.call_args.kwargs["event_root_identity"]
        self.assertEqual(identity.device, 2**60 + 124)
        self.assertEqual(identity.inode, 2**60 + 125)


if __name__ == "__main__":
    unittest.main()
