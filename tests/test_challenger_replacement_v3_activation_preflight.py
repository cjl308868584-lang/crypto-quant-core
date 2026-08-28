import hashlib
import inspect
import unittest
from datetime import datetime, timezone

from crypto_quant.canonical import canonical_json


NOW = datetime(2026, 8, 28, 8, 10, tzinfo=timezone.utc)


def verified_facts():
    return {
        "contract_binding": {
            "contract_id": "challenger_replacement_v3_install_contract_" + "a" * 64,
            "contract_hash": "b" * 64,
            "file_sha256": "c" * 64,
        },
        "machine": {
            "system": "Darwin", "machine": "arm64", "uid": 501,
            "home": "/Users/chenm4", "timezone": "Asia/Shanghai",
        },
        "release_replayed": True, "paths_verified": True,
        "power_safe": True,
        "disk": {"free_bytes": 20_000_000_000, "free_inodes": 200_000},
        "clock": {
            "endpoint": "https://data-api.binance.vision/api/v3/time",
            "request_count": 3, "trust_hash": "d" * 64,
        },
        "credential_count": 0,
        "commands_verified": True,
        "observed_at": NOW,
    }


class ChallengerReplacementV3ActivationPreflightTests(unittest.TestCase):
    def test_verified_receipt_is_30_minutes_and_has_zero_private_authority(self):
        from crypto_quant.challenger_replacement_v3_activation_preflight import (
            build_fixed_v3_activation_preflight,
            load_fixed_v3_activation_preflight_bytes,
        )

        receipt = build_fixed_v3_activation_preflight(**verified_facts())
        self.assertEqual(receipt["status"], "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE")
        self.assertEqual(receipt["expires_at"], "2026-08-28T08:40:00.000Z")
        self.assertEqual(receipt["authority"], {
            "market_request_count": 3, "launchctl_read_count": 2,
            "launchctl_mutation_count": 0, "runtime_invocation_count": 0,
            "state_write_count": 0, "credential_count": 0,
            "account_request_count": 0, "broker_request_count": 0,
            "order_count": 0, "fund_movement_count": 0,
        })
        body = canonical_json(receipt).encode()
        self.assertEqual(
            load_fixed_v3_activation_preflight_bytes(
                body, contract_binding=verified_facts()["contract_binding"]
            ), receipt,
        )

    def test_wrong_window_and_credentials_fail_closed(self):
        from crypto_quant.challenger_replacement_v3_activation_preflight import (
            build_fixed_v3_activation_preflight,
        )

        for change, reason in (
            ({"observed_at": datetime(2026, 8, 28, 8, 9, 59, tzinfo=timezone.utc)},
             "PREFLIGHT_INSTALL_WINDOW_UNSAFE"),
            ({"credential_count": 1, "clock": {
                "endpoint": "https://data-api.binance.vision/api/v3/time",
                "request_count": 0, "trust_hash": "0" * 64,
            }}, "PREFLIGHT_CREDENTIAL_BOUNDARY_PRESENT"),
        ):
            facts = verified_facts(); facts.update(change)
            receipt = build_fixed_v3_activation_preflight(**facts)
            self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
            self.assertIn(reason, receipt["reason_codes"])

    def test_module_has_no_system_paper_dependency(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as module

        source = inspect.getsource(module).lower()
        self.assertNotIn("system_paper", source)
        self.assertNotIn("challenger_cohort", source)


if __name__ == "__main__":
    unittest.main()
