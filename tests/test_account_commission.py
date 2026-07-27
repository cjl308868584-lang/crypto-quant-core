import hashlib
import hmac
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from jsonschema import Draft202012Validator

from crypto_quant.account_commission import (
    AccountCommissionError,
    AccountCommissionHttpResponse,
    AccountCommissionPlan,
    BinanceAccountCommissionTransport,
    _create_test_signer,
    account_commission_reasons,
    account_commission_trust_hash,
    build_account_commission_snapshot,
    capture_account_commission,
    load_account_signer_from_environment,
    sign_account_commission_request,
)
from crypto_quant.account_commission_cli import main
from tests.test_runtime_health import FakeTimeTransport, fake_time_responses


UTC = timezone.utc
API_KEY = "A" * 32
API_SECRET = "B" * 32


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def safe_permission_body(**overrides):
    body = {
        "ipRestrict": True,
        "createTime": 1785150000000,
        "enableWithdrawals": False,
        "enableInternalTransfer": False,
        "permitsUniversalTransfer": False,
        "enableVanillaOptions": False,
        "enableReading": True,
        "enableFutures": False,
        "enableMargin": False,
        "enableSpotAndMarginTrading": False,
        "enablePortfolioMarginTrading": False,
        "tradingAuthorityExpirationTime": 0,
    }
    body.update(overrides)
    return body


def spot_body():
    return {
        "symbol": "ETHUSDT",
        "standardCommission": {
            "maker": "0.0001",
            "taker": "0.0002",
            "buyer": "0.00003",
            "seller": "0.00004",
        },
        "specialCommission": {
            "maker": "0.00001",
            "taker": "0.00002",
            "buyer": "0.000003",
            "seller": "0.000004",
        },
        "taxCommission": {
            "maker": "0.000001",
            "taker": "0.000002",
            "buyer": "0.0000003",
            "seller": "0.0000004",
        },
        "discount": {
            "enabledForAccount": True,
            "enabledForSymbol": True,
            "discountAsset": "BNB",
            "discount": "0.25",
        },
    }


def futures_body():
    return {
        "symbol": "ETHUSDT",
        "makerCommissionRate": "0.0002",
        "takerCommissionRate": "0.0005",
    }


class FakeAccountTransport:
    def __init__(self, bodies=None):
        self.bodies = list(
            bodies
            or [safe_permission_body(), spot_body(), futures_body()]
        )
        self.calls = 0
        self.requests = []
        self.api_key_headers = []

    def get(self, request, api_key_header):
        index = self.calls
        self.calls += 1
        self.requests.append(request)
        self.api_key_headers.append(api_key_header)
        if index >= len(self.bodies):
            raise AssertionError("unexpected account request")
        started = datetime(
            2026, 7, 27, 12, 5, 13, 300000, tzinfo=UTC
        ) + timedelta(milliseconds=index * 100)
        body = json.dumps(
            self.bodies[index], separators=(",", ":")
        ).encode()
        return AccountCommissionHttpResponse(
            status=200,
            final_url=request.url,
            headers={
                "Date": "Mon, 27 Jul 2026 12:05:13 GMT",
                "X-MBX-USED-WEIGHT-1M": str(index + 1),
            },
            body=body,
            request_started_at=iso(started),
            response_received_at=iso(
                started + timedelta(milliseconds=50)
            ),
        )


class BombAccountTransport:
    def __init__(self):
        self.calls = 0

    def get(self, *_args):
        self.calls += 1
        raise AssertionError("account transport must not be called")


class AccountCommissionPlanTests(unittest.TestCase):
    def test_plan_freezes_three_exact_signed_read_requests(self):
        plan = AccountCommissionPlan.create()
        self.assertEqual(plan.recv_window_ms, 5000)
        self.assertEqual(
            [
                (item.family, item.host, item.path, item.symbol_or_null)
                for item in plan.requests
            ],
            [
                (
                    "API_KEY_RESTRICTIONS",
                    "api.binance.com",
                    "/sapi/v1/account/apiRestrictions",
                    None,
                ),
                (
                    "SPOT_ACCOUNT_COMMISSION",
                    "api.binance.com",
                    "/api/v3/account/commission",
                    "ETHUSDT",
                ),
                (
                    "USD_M_ACCOUNT_COMMISSION",
                    "fapi.binance.com",
                    "/fapi/v1/commissionRate",
                    "ETHUSDT",
                ),
            ],
        )
        with self.assertRaises(TypeError):
            AccountCommissionPlan()
        with self.assertRaises(AccountCommissionError):
            AccountCommissionPlan.create(symbol="BTCUSDT")
        self.assertFalse(hasattr(BinanceAccountCommissionTransport, "post"))

    def test_hmac_signing_is_exact_and_repr_is_redacted(self):
        signer = _create_test_signer(API_KEY, API_SECRET)
        request = AccountCommissionPlan.create().requests[1]
        signed = sign_account_commission_request(
            request, 1785153913220, signer
        )
        unsigned = (
            "symbol=ETHUSDT&recvWindow=5000&timestamp=1785153913220"
        )
        expected = hmac.new(
            API_SECRET.encode(),
            unsigned.encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(signed.unsigned_query, unsigned)
        self.assertEqual(signed.signature, expected)
        self.assertNotIn(API_KEY, repr(signer))
        self.assertNotIn(API_SECRET, repr(signer))
        self.assertNotIn(expected, repr(signed))
        signer.close()
        self.assertEqual(set(signer._secret), {0})
        self.assertEqual(set(signer._api_key), {0})
        with self.assertRaises(AccountCommissionError):
            signer.sign(b"x")

    def test_production_transport_disables_proxy_and_never_retries(self):
        class FailingOpener:
            def __init__(self):
                self.calls = 0

            def open(self, *_args, **_kwargs):
                self.calls += 1
                raise URLError("offline")

        clock = lambda: "2026-07-27T12:05:13.300Z"
        sentinel = object()
        with patch(
            "crypto_quant.account_commission.build_opener",
            return_value=sentinel,
        ) as build:
            production = BinanceAccountCommissionTransport(clock=clock)
        self.assertIs(production._opener, sentinel)
        self.assertEqual(build.call_args.args[0].proxies, {})

        opener = FailingOpener()
        transport = BinanceAccountCommissionTransport(
            clock=clock, opener=opener
        )
        signer = _create_test_signer()
        request = sign_account_commission_request(
            AccountCommissionPlan.create().requests[0],
            1785153913300,
            signer,
        )
        with self.assertRaisesRegex(
            AccountCommissionError,
            "ACCOUNT_COMMISSION_TRANSPORT_FAILURE",
        ):
            transport.get(request, signer.api_key_header())
        self.assertEqual(opener.calls, 1)
        self.assertEqual(transport.calls, 1)
        signer.close()


class AccountCredentialFileTests(unittest.TestCase):
    def test_owner_only_files_outside_workspace_and_output_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output = root / "output"
            secrets = root / "secrets"
            workspace.mkdir()
            output.mkdir()
            secrets.mkdir()
            key = secrets / "key"
            secret = secrets / "secret"
            key.write_text(API_KEY + "\n", encoding="ascii")
            secret.write_text(API_SECRET + "\n", encoding="ascii")
            key.chmod(0o600)
            secret.chmod(0o600)
            environment = {
                "CRYPTO_QUANT_BINANCE_READONLY_API_KEY_FILE": str(key),
                "CRYPTO_QUANT_BINANCE_READONLY_API_SECRET_FILE": str(
                    secret
                ),
            }
            with patch.dict(os.environ, environment, clear=False):
                signer = load_account_signer_from_environment(
                    output_root=output,
                    workspace_root=workspace,
                )
            self.assertEqual(
                signer.fingerprint,
                hashlib.sha256(API_KEY.encode()).hexdigest(),
            )
            signer.close()

    def test_bad_mode_symlink_inside_boundary_and_secret_value_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output = root / "output"
            secrets = root / "secrets"
            workspace.mkdir()
            output.mkdir()
            secrets.mkdir()
            valid_key = secrets / "key"
            valid_secret = secrets / "secret"
            valid_key.write_text(API_KEY, encoding="ascii")
            valid_secret.write_text(API_SECRET, encoding="ascii")
            valid_key.chmod(0o600)
            valid_secret.chmod(0o600)

            cases = []
            bad_mode = secrets / "bad-mode"
            bad_mode.write_text(API_KEY, encoding="ascii")
            bad_mode.chmod(0o644)
            cases.append((bad_mode, valid_secret))
            link = secrets / "link"
            link.symlink_to(valid_key)
            cases.append((link, valid_secret))
            inside = workspace / "key"
            inside.write_text(API_KEY, encoding="ascii")
            inside.chmod(0o600)
            cases.append((inside, valid_secret))
            cases.append((Path(API_KEY), valid_secret))

            for key, secret in cases:
                environment = {
                    "CRYPTO_QUANT_BINANCE_READONLY_API_KEY_FILE": str(
                        key
                    ),
                    "CRYPTO_QUANT_BINANCE_READONLY_API_SECRET_FILE": str(
                        secret
                    ),
                }
                with self.subTest(key=key), patch.dict(
                    os.environ, environment, clear=False
                ):
                    with self.assertRaises(AccountCommissionError):
                        load_account_signer_from_environment(
                            output_root=output,
                            workspace_root=workspace,
                        )


class AccountCommissionSnapshotTests(unittest.TestCase):
    def _capture(self, bodies=None):
        signer = _create_test_signer(API_KEY, API_SECRET)
        transport = FakeAccountTransport(bodies)
        capture = capture_account_commission(
            signer=signer,
            server_time_transport=FakeTimeTransport(
                fake_time_responses()
            ),
            account_transport=transport,
        )
        snapshot = build_account_commission_snapshot(capture)
        signer.close()
        return snapshot, transport

    def test_snapshot_replays_account_rates_and_conservative_costs(self):
        snapshot, transport = self._capture()
        self.assertEqual(transport.calls, 3)
        self.assertEqual(snapshot["network_request_count"], 6)
        self.assertEqual(
            snapshot["permission_summary"]["status"],
            "READ_ONLY_IP_RESTRICTED",
        )
        spot = snapshot["commission_context"]["spot"]
        self.assertEqual(
            spot["authoritative_no_discount_rates"]["taker_buy"],
            "0.0002553",
        )
        self.assertEqual(
            spot["authoritative_no_discount_rates"]["taker_sell"],
            "0.0002664",
        )
        self.assertIsNotNone(spot["bnb_discount_scenario_or_null"])
        self.assertEqual(
            spot["bnb_discount_scenario_or_null"]["taker_buy"],
            "0.0000828",
        )
        self.assertEqual(
            spot["bnb_discount_scenario_or_null"]["taker_sell"],
            "0.0000864",
        )
        costs = snapshot["cost_scenarios"]
        self.assertEqual(
            costs["spot_two_taker_sides_rate"], "0.0005217"
        )
        self.assertEqual(
            costs["spot_two_taker_sides_per_1000_usdt"], "0.5217"
        )
        self.assertEqual(
            costs["futures_taker_per_1000_usdt"], "0.5"
        )
        self.assertEqual(
            costs["futures_two_taker_sides_per_1000_usdt"], "1"
        )
        self.assertTrue(
            costs["v0_18_assumption_covers_futures_taker"]
        )
        trust = account_commission_trust_hash(snapshot)
        self.assertEqual(account_commission_reasons(snapshot, trust), ())

    def test_permission_gate_blocks_before_any_commission_request(self):
        dangerous_fields = (
            "enableWithdrawals",
            "enableInternalTransfer",
            "permitsUniversalTransfer",
            "enableVanillaOptions",
            "enableFutures",
            "enableMargin",
            "enableSpotAndMarginTrading",
            "enablePortfolioMarginTrading",
            "futureTradePermission",
        )
        for field in dangerous_fields:
            signer = _create_test_signer()
            transport = FakeAccountTransport(
                [safe_permission_body(**{field: True})]
            )
            with self.subTest(field=field), self.assertRaisesRegex(
                AccountCommissionError,
                "ACCOUNT_CREDENTIAL_SCOPE_BLOCKED",
            ):
                capture_account_commission(
                    signer=signer,
                    server_time_transport=FakeTimeTransport(
                        fake_time_responses()
                    ),
                    account_transport=transport,
                )
            self.assertEqual(transport.calls, 1)
            signer.close()

    def test_unknown_false_permission_is_preserved_and_safe(self):
        snapshot, _ = self._capture(
            [
                safe_permission_body(futurePermission=False),
                spot_body(),
                futures_body(),
            ]
        )
        self.assertFalse(
            snapshot["permission_summary"]["flags"][
                "futurePermission"
            ]
        )

    def test_blocked_clock_makes_zero_account_requests(self):
        signer = _create_test_signer()
        bomb = BombAccountTransport()
        with self.assertRaisesRegex(
            AccountCommissionError,
            "ACCOUNT_COMMISSION_CLOCK_BLOCKED",
        ):
            capture_account_commission(
                signer=signer,
                server_time_transport=FakeTimeTransport(
                    fake_time_responses(
                        offset_ms=8000, rtts=(50, 60, 55)
                    )
                ),
                account_transport=bomb,
            )
        self.assertEqual(bomb.calls, 0)
        signer.close()

    def test_tampering_and_secret_persistence_are_rejected(self):
        snapshot, _ = self._capture()
        serialized = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn(API_KEY, serialized)
        self.assertNotIn(API_SECRET, serialized)
        trust = account_commission_trust_hash(snapshot)
        for kind in ("receipt", "cost", "fingerprint", "claim"):
            candidate = deepcopy(snapshot)
            if kind == "receipt":
                candidate["receipts"][1]["response_body_utf8"] += " "
            elif kind == "cost":
                candidate["cost_scenarios"][
                    "futures_taker_per_1000_usdt"
                ] = "0"
            elif kind == "fingerprint":
                candidate["api_key_fingerprint"] = "f" * 64
            else:
                candidate["production_eligibility"] = "APPROVED"
            with self.subTest(kind=kind):
                self.assertTrue(
                    account_commission_reasons(candidate, trust)
                )

    def test_bad_symbol_binary_float_rate_and_response_shape_fail(self):
        base = [safe_permission_body(), spot_body(), futures_body()]
        cases = []
        bad_symbol = deepcopy(base)
        bad_symbol[1]["symbol"] = "BTCUSDT"
        cases.append(bad_symbol)
        bad_rate = deepcopy(base)
        bad_rate[2]["takerCommissionRate"] = "NaN"
        cases.append(bad_rate)
        extra = deepcopy(base)
        extra[2]["vipTier"] = 0
        cases.append(extra)
        for bodies in cases:
            signer = _create_test_signer()
            with self.subTest(), self.assertRaises(
                AccountCommissionError
            ):
                capture_account_commission(
                    signer=signer,
                    server_time_transport=FakeTimeTransport(
                        fake_time_responses()
                    ),
                    account_transport=FakeAccountTransport(bodies),
                )
            signer.close()

    def test_schema_is_packaged_mirrored_and_rejects_extra_claims(self):
        root = Path(__file__).resolve().parents[1]
        governance = (
            root / "config" / "account-commission-snapshot-v1.schema.json"
        )
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "account-commission-snapshot-v1.schema.json"
        )
        self.assertEqual(governance.read_bytes(), packaged.read_bytes())
        schema = json.loads(governance.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        snapshot, _ = self._capture()
        self.assertEqual(
            tuple(Draft202012Validator(schema).iter_errors(snapshot)),
            (),
        )
        snapshot["live_ready"] = True
        self.assertTrue(
            tuple(Draft202012Validator(schema).iter_errors(snapshot))
        )


class AccountCommissionCliTests(unittest.TestCase):
    def test_cli_publishes_immutable_mode_600_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            signer = _create_test_signer()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    ["--output-root", directory],
                    signer=signer,
                    server_time_transport=FakeTimeTransport(
                        fake_time_responses()
                    ),
                    account_transport=FakeAccountTransport(),
                )
            self.assertEqual(result, 0)
            summary = json.loads(stdout.getvalue())
            artifact = Path(summary["artifact_path"])
            self.assertTrue(artifact.is_file())
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertEqual(summary["network_request_count"], 6)
            signer.close()

    def test_cli_exposes_no_secret_source_or_order_overrides(self):
        forbidden = (
            "--api-key",
            "--secret",
            "--credential",
            "--url",
            "--host",
            "--proxy",
            "--header",
            "--symbol",
            "--recv-window",
            "--timestamp",
            "--account",
            "--order",
        )
        for argument in forbidden:
            with self.subTest(argument=argument), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(main([argument, "x"]), 2)

    def test_cli_without_credential_files_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "CRYPTO_QUANT_BINANCE_READONLY_API_KEY_FILE": "",
                "CRYPTO_QUANT_BINANCE_READONLY_API_SECRET_FILE": "",
            },
            clear=False,
        ):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = main(["--output-root", directory])
            self.assertEqual(result, 1)
            self.assertIn(
                "ACCOUNT_CREDENTIAL_FILE_REQUIRED", stderr.getvalue()
            )


if __name__ == "__main__":
    unittest.main()
