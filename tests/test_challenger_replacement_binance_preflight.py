from copy import deepcopy
from dataclasses import replace
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_credential import (
    BinanceCredentialIdentity,
)
from crypto_quant.challenger_replacement_binance_private_contract import (
    BinanceAccountApproval, BinancePrivateActivation,
)
from tests.challenger_replacement_v077_private_fixtures import (
    loaded_private_activation,
)
from crypto_quant.challenger_replacement_binance_preflight import (
    BinanceAccountPreflightError,
    evaluate_binance_account_preflight,
    load_binance_account_preflight_bytes,
    open_binance_account_preflight_capability,
)


class BinanceAccountPreflightTests(unittest.TestCase):
    BUILD = {
        "release_tag": "v0.77.0", "peeled_commit": "1" * 40,
        "package_version": "0.77.0", "manifest_version": "v0.77.0",
        "build_input_tree_hash": "2" * 64, "manifest_hash": "3" * 64,
        "manifest_file_sha256": "4" * 64,
    }
    NOW = "2026-08-27T12:00:00.000Z"
    FINGERPRINT = "5" * 64

    def setUp(self):
        self.fixture = json.loads(resources.files("crypto_quant").joinpath(
            "fixtures", "challenger-replacement-v077",
            "account-preflight-flat.json",
        ).read_text(encoding="utf-8"))
        account_identity = hashlib.sha256(canonical_json({
            "api_key_create_time": self.fixture["API_RESTRICTIONS"]["createTime"],
            "spot_uid": self.fixture["SPOT_ACCOUNT"]["uid"],
            "venue": "BINANCE",
        }).encode()).hexdigest()
        self.approval = BinanceAccountApproval(
            account_identity_sha256=account_identity,
            key_fingerprint=self.FINGERPRINT,
            reviewed_egress_ip="203.0.113.10", reviewer_uid=501,
            reviewed_at="2026-08-27T10:00:00.000Z",
            expires_at="2026-08-28T00:00:00.000Z",
            spot_trading_approved=True, futures_trading_approved=True,
        )
        self.identity = BinanceCredentialIdentity(
            device=1, inode=2, owner_uid=501, mtime_ns=3, ctime_ns=4,
            file_sha256="7" * 64,
            key_fingerprint=self.FINGERPRINT,
        )

    def _responses(self, fixture=None):
        return {
            name: canonical_json(value).encode("utf-8")
            for name, value in (fixture or self.fixture).items()
        }

    def _evaluate(self, fixture=None, responses=None, approval=None,
                  identity=None, build=None, now=None):
        return evaluate_binance_account_preflight(
            responses=responses or self._responses(fixture),
            account_approval=approval or self.approval,
            credential_identity=identity or self.identity,
            build_identity=build or self.BUILD,
            now=now or self.NOW,
        )

    def _reason(self, fixture=None, **kwargs):
        with self.assertRaises(BinanceAccountPreflightError) as caught:
            self._evaluate(fixture, **kwargs)
        return caught.exception.reason_code

    def _retained_capability(self, data):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        parent = Path(directory.name) / "owner-only"
        parent.mkdir(mode=0o700)
        path = parent / "account-preflight.json"
        path.write_bytes(data)
        path.chmod(0o600)
        parent_stat, file_stat = parent.stat(), path.stat()
        reference = {
            "schema_version": "1.0.0", "absolute_path": str(path),
            "parent_device": parent_stat.st_dev,
            "parent_inode": parent_stat.st_ino,
            "file_device": file_stat.st_dev, "file_inode": file_stat.st_ino,
            "file_sha256": hashlib.sha256(data).hexdigest(),
        }
        capability = open_binance_account_preflight_capability(
            reference_bytes=(canonical_json(reference) + "\n").encode(),
            expected_uid=os.getuid(), build_identity=self.BUILD,
        )
        self.addCleanup(capability.close)
        return capability, path

    def test_flat_approved_fixture_builds_canonical_strict_replay(self):
        data = self._evaluate()
        self.assertTrue(data.endswith(b"\n"))
        document = json.loads(data)
        self.assertEqual(document["status"],
                         "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT")
        self.assertEqual(document["build_identity"], self.BUILD)
        self.assertEqual(document["account_approval"], {
            "account_identity_sha256": self.approval.account_identity_sha256,
            "key_fingerprint": self.FINGERPRINT,
            "reviewed_egress_ip_attestation": "203.0.113.10",
            "reviewer_uid": 501,
        })
        self.assertEqual(document["configuration"], {
            "position_mode": "ONE_WAY", "asset_mode": "SINGLE_ASSET",
            "symbol": "ETHUSDT", "margin_type": "ISOLATED",
            "leverage": 1, "auto_add_margin": False,
        })
        self.assertEqual(document["authority_counts"], {
            "network_requests": 0, "mutating_requests": 0,
            "orders": 0, "fund_movements": 0, "state_writes": 0,
        })
        loaded = load_binance_account_preflight_bytes(
            data, build_identity=self.BUILD
        )
        self.assertEqual(dict(loaded), document)
        with self.assertRaises(TypeError):
            loaded["permissions"]["withdraw"] = True
        self.assertEqual(self._evaluate(), data)

    def test_permission_scope_requires_trade_read_ip_and_no_fund_authority(self):
        mutations = {
            "withdraw": ("enableWithdrawals", True),
            "ip": ("ipRestrict", False),
            "reading": ("enableReading", False),
            "spot": ("enableSpotAndMarginTrading", False),
            "futures": ("enableFutures", False),
            "transfer": ("permitsUniversalTransfer", True),
            "margin": ("enableMargin", True),
        }
        for label, (key, value) in mutations.items():
            fixture = deepcopy(self.fixture)
            fixture["API_RESTRICTIONS"][key] = value
            with self.subTest(label=label):
                self.assertEqual(
                    self._reason(fixture),
                    "BINANCE_ACCOUNT_PREFLIGHT_PERMISSION_BLOCKED",
                )

    def test_locked_or_mismatched_approval_fails_closed(self):
        locked = deepcopy(self.fixture)
        locked["API_TRADING_STATUS"]["data"]["isLocked"] = True
        self.assertEqual(self._reason(locked),
                         "BINANCE_ACCOUNT_PREFLIGHT_ACCOUNT_LOCKED")
        wrong = BinanceCredentialIdentity(
            1, 2, 501, 3, 4, "7" * 64, "8" * 64
        )
        self.assertEqual(
            self._reason(identity=wrong),
            "BINANCE_ACCOUNT_PREFLIGHT_APPROVAL_INVALID",
        )
        self.assertEqual(
            self._reason(identity=replace(self.identity, mtime_ns=True)),
            "BINANCE_ACCOUNT_PREFLIGHT_APPROVAL_INVALID",
        )
        wrong_account = BinanceAccountApproval(
            **{**self.approval.__dict__, "account_identity_sha256": "9" * 64}
        )
        self.assertEqual(
            self._reason(approval=wrong_account),
            "BINANCE_ACCOUNT_PREFLIGHT_APPROVAL_INVALID",
        )
        expired = BinanceAccountApproval(
            **{**self.approval.__dict__, "expires_at": self.NOW}
        )
        self.assertEqual(
            self._reason(approval=expired),
            "BINANCE_ACCOUNT_PREFLIGHT_APPROVAL_INVALID",
        )

    def test_configuration_requires_one_way_single_asset_isolated_and_at_most_two(self):
        mutations = (
            ("FUTURES_POSITION_MODE", "dualSidePosition", True),
            ("FUTURES_MULTI_ASSET_MODE", "multiAssetsMargin", True),
        )
        for endpoint, key, value in mutations:
            fixture = deepcopy(self.fixture); fixture[endpoint][key] = value
            self.assertEqual(self._reason(fixture),
                             "BINANCE_ACCOUNT_PREFLIGHT_CONFIGURATION_BLOCKED")
        for key, value in (("marginType", "CROSSED"), ("leverage", 3),
                           ("isAutoAddMargin", True)):
            fixture = deepcopy(self.fixture)
            fixture["FUTURES_SYMBOL_CONFIG"][0][key] = value
            self.assertEqual(self._reason(fixture),
                             "BINANCE_ACCOUNT_PREFLIGHT_CONFIGURATION_BLOCKED")

    def test_any_exposure_or_open_order_is_not_flat(self):
        mutations = (
            ("SPOT_ACCOUNT", lambda value: value["balances"][0].update(free="0.1")),
            ("SPOT_OPEN_ORDERS", lambda value: value.append({"orderId": 1})),
            ("FUTURES_ACCOUNT", lambda value: value.update(totalInitialMargin="1")),
            ("FUTURES_POSITION", lambda value: value[0].update(positionAmt="-0.01")),
            ("FUTURES_OPEN_ORDERS", lambda value: value.append({"orderId": 2})),
            ("FUTURES_OPEN_ALGO_ORDERS", lambda value: value.append({"algoId": 3})),
        )
        for endpoint, mutate in mutations:
            fixture = deepcopy(self.fixture); mutate(fixture[endpoint])
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self._reason(fixture),
                                 "BINANCE_ACCOUNT_PREFLIGHT_NOT_FLAT")

    def test_missing_extra_duplicate_or_nonbytes_input_is_invalid(self):
        missing = self._responses(); missing.pop("SPOT_ACCOUNT")
        extra = self._responses(); extra["UNKNOWN"] = b"{}"
        duplicate = self._responses()
        duplicate["SPOT_ACCOUNT"] = b'{"canTrade":true,"canTrade":true}'
        nonbytes = self._responses(); nonbytes["SPOT_ACCOUNT"] = "{}"
        for responses in (missing, extra, duplicate, nonbytes):
            self.assertEqual(
                self._reason(responses=responses),
                "BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID",
            )

    def test_malformed_unconsumed_account_fields_cannot_hide_in_verified_artifact(self):
        mutations = (
            ("SPOT_ACCOUNT", lambda value: value.update(makerCommission="10")),
            ("SPOT_ACCOUNT", lambda value: value.update(canWithdraw="true")),
            ("SPOT_ACCOUNT", lambda value: value["balances"][1].update(locked="1")),
            ("FUTURES_ACCOUNT", lambda value: value.update(totalWalletBalance="NaN")),
            ("FUTURES_ACCOUNT", lambda value: value.update(assets=[])),
            ("FUTURES_POSITION", lambda value: value[0].update(adl="0")),
        )
        for endpoint, mutate in mutations:
            fixture = deepcopy(self.fixture); mutate(fixture[endpoint])
            with self.subTest(endpoint=endpoint):
                self.assertIn(self._reason(fixture), {
                    "BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID",
                    "BINANCE_ACCOUNT_PREFLIGHT_NOT_FLAT",
                })

    def test_schema_and_loader_reject_extra_or_wrong_build(self):
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas",
            "challenger-replacement-binance-account-preflight-v1.schema.json",
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        data = self._evaluate(); document = json.loads(data)
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(document)), [])
        document["extra"] = True
        tampered = (canonical_json(document) + "\n").encode()
        with self.assertRaises(BinanceAccountPreflightError):
            load_binance_account_preflight_bytes(tampered,
                                                 build_identity=self.BUILD)
        with self.assertRaises(BinanceAccountPreflightError):
            load_binance_account_preflight_bytes(
                data, build_identity={**self.BUILD, "release_tag": "wrong"}
            )

    def test_loader_rejects_rehashed_nested_semantic_tampering(self):
        originals = json.loads(self._evaluate())
        candidates = []
        value = deepcopy(originals); value["permissions"]["withdraw"] = True
        candidates.append(value)
        value = deepcopy(originals); value["configuration"]["leverage"] = 3
        candidates.append(value)
        value = deepcopy(originals); value["flatness"]["futures_positions"] = 1
        candidates.append(value)
        value = deepcopy(originals); value["authority_counts"]["orders"] = 1
        candidates.append(value)
        value = deepcopy(originals); value["response_sha256"].pop("SPOT_ACCOUNT")
        value["response_sha256"]["UNKNOWN"] = "0" * 64
        candidates.append(value)
        value = deepcopy(originals); value["account_approval"]["key_fingerprint"] = "G" * 64
        candidates.append(value)
        value = deepcopy(originals)
        value["account_approval"]["reviewed_egress_ip_attestation"] = "2001:db8::1"
        candidates.append(value)
        for document in candidates:
            core = dict(document); core.pop("preflight_id")
            document["preflight_id"] = "binance_account_preflight_" + hashlib.sha256(
                canonical_json(core).encode()
            ).hexdigest()
            with self.subTest(document=document):
                with self.assertRaises(BinanceAccountPreflightError):
                    load_binance_account_preflight_bytes(
                        (canonical_json(document) + "\n").encode(),
                        build_identity=self.BUILD,
                    )

    def test_capability_binds_activation_approval_credential_and_expiry(self):
        data = self._evaluate()
        document = json.loads(data)
        approval_bytes = (canonical_json({
            "$schema": "./challenger-replacement-binance-account-approval-v1.schema.json",
            "schema_version": "1.0.0",
            **self.approval.__dict__,
        }) + "\n").encode("utf-8")
        activation = loaded_private_activation(
            build_identity=self.BUILD, now=self.NOW,
            activation_id="binance_private_activation_" + "a" * 64,
            configuration_sha256=hashlib.sha256(canonical_json(
                document["configuration"]
            ).encode("utf-8")).hexdigest(),
            account_approval_sha256=hashlib.sha256(approval_bytes).hexdigest(),
            block_id="e0_block_" + "b" * 64,
        )
        capability, _path = self._retained_capability(data)
        loaded = capability.load(
            activation=activation, credential_identity=self.identity,
            now=self.NOW,
        )
        self.assertEqual(loaded["preflight_id"], document["preflight_id"])
        for altered in (
            replace(activation, account_approval_sha256="c" * 64),
            replace(activation, configuration_sha256="d" * 64),
            replace(activation, expires_at=self.NOW),
        ):
            with self.subTest(altered=altered), self.assertRaisesRegex(
                BinanceAccountPreflightError,
                "BINANCE_ACCOUNT_PREFLIGHT_AUTHORITY_INVALID",
            ):
                capability.load(
                    activation=altered, credential_identity=self.identity,
                    now=self.NOW,
                )
        with self.assertRaisesRegex(
            BinanceAccountPreflightError,
            "BINANCE_ACCOUNT_PREFLIGHT_AUTHORITY_INVALID",
        ):
            capability.load(
                activation=activation,
                credential_identity=replace(
                    self.identity, key_fingerprint="e" * 64
                ),
                now=self.NOW,
            )

    def test_retained_capability_rejects_same_bytes_at_a_new_inode(self):
        data = self._evaluate()
        capability, path = self._retained_capability(data)
        displaced = path.with_suffix(".displaced")
        path.rename(displaced)
        path.write_bytes(data)
        path.chmod(0o600)
        with self.assertRaisesRegex(
            BinanceAccountPreflightError,
            "BINANCE_ACCOUNT_PREFLIGHT_ATTACHMENT_CHANGED",
        ):
            capability.load(
                activation=loaded_private_activation(
                    build_identity=self.BUILD, now=self.NOW,
                    configuration_sha256=json.loads(data)[
                        "configuration_sha256"
                    ],
                    account_approval_sha256=json.loads(data)[
                        "account_approval_sha256"
                    ],
                ),
                credential_identity=self.identity, now=self.NOW,
            )
        self.assertEqual(displaced.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
