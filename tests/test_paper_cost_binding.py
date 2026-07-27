import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.account_commission import (
    AccountCommissionHttpResponse,
    _create_test_signer,
    account_commission_trust_hash,
    build_account_commission_snapshot,
    capture_account_commission,
)
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.offline_paper import (
    build_offline_paper_run,
    offline_paper_run_trust_hash,
)
from crypto_quant.paper_cost_binding import (
    PaperCostBindingError,
    build_paper_account_cost_binding,
    paper_account_cost_binding_reasons,
    paper_account_cost_binding_trust_hash,
)
from crypto_quant.paper_cost_binding_cli import main
from tests.test_account_commission import (
    FakeAccountTransport,
    futures_body,
    safe_permission_body,
    spot_body,
)
from tests.test_offline_paper import valid_capture
from tests.test_runtime_health import (
    FakeTimeTransport,
    fake_time_responses,
)


ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class TimedAccountTransport:
    def __init__(self, base):
        self.base = base
        self.bodies = [
            safe_permission_body(),
            spot_body(),
            futures_body(),
        ]
        self.calls = 0

    def get(self, request, _api_key_header):
        index = self.calls
        self.calls += 1
        started = self.base + timedelta(
            seconds=2, milliseconds=200 + index * 100
        )
        body = json.dumps(
            self.bodies[index], separators=(",", ":")
        ).encode()
        return AccountCommissionHttpResponse(
            status=200,
            final_url=request.url,
            headers={
                "Date": "Mon, 27 Jul 2026 11:55:02 GMT",
                "X-MBX-USED-WEIGHT-1M": str(index + 1),
            },
            body=body,
            request_started_at=iso(started),
            response_received_at=iso(
                started + timedelta(milliseconds=50)
            ),
        )


def account_snapshot_at(base=None):
    signer = _create_test_signer()
    if base is None:
        time_transport = FakeTimeTransport(fake_time_responses())
        account_transport = FakeAccountTransport()
    else:
        time_transport = FakeTimeTransport(
            fake_time_responses(
                base=base,
                offset_ms=100,
                rtts=(50, 60, 55),
            )
        )
        account_transport = TimedAccountTransport(base)
    capture = capture_account_commission(
        signer=signer,
        server_time_transport=time_transport,
        account_transport=account_transport,
    )
    snapshot = build_account_commission_snapshot(capture)
    trust = account_commission_trust_hash(snapshot)
    signer.close()
    return snapshot, trust


def frozen_paper_run():
    path = (
        ROOT
        / "artifacts"
        / "paper"
        / "binance-offline-paper-smoke-v0.18.0.json"
    )
    run = json.loads(path.read_text(encoding="utf-8"))
    return run, offline_paper_run_trust_hash(run)


def filled_binding():
    run, paper_trust = frozen_paper_run()
    snapshot, account_trust = account_snapshot_at()
    binding = build_paper_account_cost_binding(
        offline_paper_run=run,
        offline_paper_trusted_attestation_hash=paper_trust,
        account_commission_snapshot=snapshot,
        account_commission_trusted_attestation_hash=account_trust,
        created_at="2026-07-27T14:00:00.000Z",
    )
    return binding, paper_trust, account_trust


class PaperCostBindingTests(unittest.TestCase):
    def test_filled_run_rebases_only_exact_entry_and_exit_fees(self):
        binding, paper_trust, account_trust = filled_binding()
        replay = binding["baseline_cost_replay"]
        self.assertEqual(replay["status"], "REPLAYED_FILLED")
        self.assertEqual(replay["entry_notional_usdt"], "89.728074")
        self.assertEqual(
            replay["conservative_exit_notional_usdt"], "89.547687"
        )
        self.assertEqual(
            replay["assumed_total_fee_usdt"], "0.2689136415"
        )
        self.assertEqual(
            replay["account_entry_fee_usdt"], "0.0229075772922"
        )
        self.assertEqual(
            replay["account_exit_fee_usdt"], "0.0238555038168"
        )
        self.assertEqual(
            replay["account_total_fee_usdt"], "0.046763081109"
        )
        self.assertEqual(
            replay["account_minus_assumed_fee_usdt"],
            "-0.222150560391",
        )
        self.assertEqual(
            replay["account_costed_ending_liquidation_equity_usdt"],
            "999.772849918891",
        )
        self.assertEqual(
            replay["account_costed_liquidation_net_change_usdt"],
            "-0.227150081109",
        )
        self.assertFalse(binding["fee_policy"]["bnb_discount_applied"])
        self.assertTrue(replay["only_fee_values_changed"])
        trust = paper_account_cost_binding_trust_hash(binding)
        self.assertEqual(
            paper_account_cost_binding_reasons(
                binding,
                trust,
                offline_paper_trusted_attestation_hash=paper_trust,
                account_commission_trusted_attestation_hash=account_trust,
            ),
            (),
        )

    def test_flat_run_keeps_zero_fee_and_unchanged_equity(self):
        capture, _ = valid_capture(latest="1900", prior="2000")
        run = build_offline_paper_run(
            capture,
            run_id="paper-cost-flat",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        paper_trust = offline_paper_run_trust_hash(run)
        account, account_trust = account_snapshot_at(
            datetime(2026, 7, 27, 11, 55, tzinfo=UTC)
        )
        binding = build_paper_account_cost_binding(
            offline_paper_run=run,
            offline_paper_trusted_attestation_hash=paper_trust,
            account_commission_snapshot=account,
            account_commission_trusted_attestation_hash=account_trust,
            created_at="2026-07-27T12:01:00.000Z",
        )
        replay = binding["baseline_cost_replay"]
        self.assertEqual(replay["status"], "REPLAYED_NO_TRADE")
        for name in (
            "assumed_total_fee_usdt",
            "account_total_fee_usdt",
            "account_minus_assumed_fee_usdt",
        ):
            self.assertEqual(replay[name], "0")
        self.assertEqual(
            replay["account_costed_ending_liquidation_equity_usdt"],
            replay["original_ending_liquidation_equity_usdt"],
        )

    def test_post_decision_and_expired_account_context_fail_closed(self):
        flat_capture, _ = valid_capture(latest="1900", prior="2000")
        flat = build_offline_paper_run(
            flat_capture,
            run_id="paper-cost-pit",
            recorded_at="2026-07-27T12:00:02.000Z",
        )
        paper_trust = offline_paper_run_trust_hash(flat)
        later, later_trust = account_snapshot_at()
        with self.assertRaisesRegex(
            PaperCostBindingError,
            "PAPER_COST_ACCOUNT_OBSERVED_AFTER_DECISION",
        ):
            build_paper_account_cost_binding(
                offline_paper_run=flat,
                offline_paper_trusted_attestation_hash=paper_trust,
                account_commission_snapshot=later,
                account_commission_trusted_attestation_hash=later_trust,
                created_at="2026-07-27T13:00:00.000Z",
            )

        old, old_trust = account_snapshot_at(
            datetime(2026, 7, 27, 7, 55, tzinfo=UTC)
        )
        with self.assertRaisesRegex(
            PaperCostBindingError,
            "PAPER_COST_ACCOUNT_EXPIRED_BEFORE_RUN_END",
        ):
            build_paper_account_cost_binding(
                offline_paper_run=flat,
                offline_paper_trusted_attestation_hash=paper_trust,
                account_commission_snapshot=old,
                account_commission_trusted_attestation_hash=old_trust,
                created_at="2026-07-27T13:00:00.000Z",
            )

    def test_source_external_trust_is_required_and_independent(self):
        run, paper_trust = frozen_paper_run()
        account, account_trust = account_snapshot_at()
        cases = (
            ("0" * 64, account_trust),
            (paper_trust, "0" * 64),
        )
        for supplied_paper, supplied_account in cases:
            with self.subTest(), self.assertRaises(
                PaperCostBindingError
            ):
                build_paper_account_cost_binding(
                    offline_paper_run=run,
                    offline_paper_trusted_attestation_hash=(
                        supplied_paper
                    ),
                    account_commission_snapshot=account,
                    account_commission_trusted_attestation_hash=(
                        supplied_account
                    ),
                    created_at="2026-07-27T14:00:00.000Z",
                )

    def test_semantic_tampering_fails_even_after_self_rehash(self):
        binding, paper_trust, account_trust = filled_binding()
        for field, value in (
            ("account_total_fee_usdt", "0"),
            (
                "account_costed_ending_liquidation_equity_usdt",
                "1001",
            ),
            ("only_fee_values_changed", False),
        ):
            candidate = deepcopy(binding)
            candidate["baseline_cost_replay"][field] = value
            candidate["binding_hash"] = artifact_self_hash(
                candidate, "binding_hash"
            )
            forged_trust = paper_account_cost_binding_trust_hash(
                candidate
            )
            with self.subTest(field=field):
                self.assertTrue(
                    paper_account_cost_binding_reasons(
                        candidate,
                        forged_trust,
                        offline_paper_trusted_attestation_hash=(
                            paper_trust
                        ),
                        account_commission_trusted_attestation_hash=(
                            account_trust
                        ),
                    )
                )

    def test_nested_source_mutation_and_eligibility_claim_fail(self):
        binding, paper_trust, account_trust = filled_binding()
        cases = []
        source = deepcopy(binding)
        source["offline_paper_run"]["run_end"] = (
            "2026-07-27T13:31:00.000Z"
        )
        cases.append(source)
        eligibility = deepcopy(binding)
        eligibility["production_eligibility"] = "APPROVED"
        cases.append(eligibility)
        for candidate in cases:
            with self.subTest():
                self.assertTrue(
                    paper_account_cost_binding_reasons(
                        candidate,
                        paper_account_cost_binding_trust_hash(candidate),
                        offline_paper_trusted_attestation_hash=(
                            paper_trust
                        ),
                        account_commission_trusted_attestation_hash=(
                            account_trust
                        ),
                    )
                )

    def test_schema_is_mirrored_and_rejects_extra_claims(self):
        governance = (
            ROOT / "config" / "paper-account-cost-binding-v1.schema.json"
        )
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "paper-account-cost-binding-v1.schema.json"
        )
        self.assertEqual(governance.read_bytes(), packaged.read_bytes())
        schema = json.loads(governance.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        binding, _, _ = filled_binding()
        self.assertEqual(
            tuple(Draft202012Validator(schema).iter_errors(binding)),
            (),
        )
        binding["profitable"] = True
        self.assertTrue(
            tuple(Draft202012Validator(schema).iter_errors(binding))
        )

    def test_created_at_must_follow_both_sources(self):
        run, paper_trust = frozen_paper_run()
        account, account_trust = account_snapshot_at()
        with self.assertRaisesRegex(
            PaperCostBindingError,
            "PAPER_COST_CREATED_BEFORE_SOURCES",
        ):
            build_paper_account_cost_binding(
                offline_paper_run=run,
                offline_paper_trusted_attestation_hash=paper_trust,
                account_commission_snapshot=account,
                account_commission_trusted_attestation_hash=account_trust,
                created_at="2026-07-27T12:00:00.000Z",
            )


class PaperCostBindingCliTests(unittest.TestCase):
    def test_cli_publishes_mode_600_binding_without_network(self):
        run, paper_trust = frozen_paper_run()
        account, account_trust = account_snapshot_at()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paper_path = root / "paper.json"
            account_path = root / "account.json"
            paper_trust_path = root / "paper.trust"
            account_trust_path = root / "account.trust"
            paper_path.write_text(json.dumps(run), encoding="utf-8")
            account_path.write_text(json.dumps(account), encoding="utf-8")
            paper_trust_path.write_text(
                paper_trust + "\n", encoding="ascii"
            )
            account_trust_path.write_text(
                account_trust + "\n", encoding="ascii"
            )
            output = root / "output"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "--paper-run",
                        str(paper_path),
                        "--paper-trust-hash-file",
                        str(paper_trust_path),
                        "--account-snapshot",
                        str(account_path),
                        "--account-trust-hash-file",
                        str(account_trust_path),
                        "--output-root",
                        str(output),
                    ],
                    clock=lambda: datetime(
                        2026, 7, 27, 14, tzinfo=UTC
                    ),
                )
            self.assertEqual(result, 0)
            summary = json.loads(stdout.getvalue())
            artifact = Path(summary["artifact_path"])
            self.assertTrue(artifact.is_file())
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                summary["production_eligibility"], "NOT_APPROVED"
            )

    def test_cli_exposes_no_network_credential_or_order_arguments(self):
        forbidden = (
            "--url",
            "--host",
            "--api-key",
            "--secret",
            "--credential",
            "--proxy",
            "--header",
            "--order",
            "--symbol",
            "--fee-rate",
            "--created-at",
        )
        for argument in forbidden:
            with self.subTest(argument=argument), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(main([argument, "x"]), 2)

    def test_cli_invalid_source_fails_closed_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.json"
            trust = root / "trust"
            invalid.write_text("{}", encoding="utf-8")
            trust.write_text("0" * 64, encoding="ascii")
            output = root / "output"
            with redirect_stderr(io.StringIO()):
                result = main(
                    [
                        "--paper-run",
                        str(invalid),
                        "--paper-trust-hash-file",
                        str(trust),
                        "--account-snapshot",
                        str(invalid),
                        "--account-trust-hash-file",
                        str(trust),
                        "--output-root",
                        str(output),
                    ]
                )
            self.assertEqual(result, 1)
            self.assertFalse(output.exists())

    def test_cli_rejects_duplicate_keys_floats_and_naive_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trust = root / "trust"
            trust.write_text("0" * 64, encoding="ascii")
            for body in ('{"x":1,"x":2}', '{"x":0.1}'):
                source = root / ("source-" + str(len(body)) + ".json")
                source.write_text(body, encoding="utf-8")
                with self.subTest(body=body), redirect_stderr(
                    io.StringIO()
                ):
                    self.assertEqual(
                        main(
                            [
                                "--paper-run",
                                str(source),
                                "--paper-trust-hash-file",
                                str(trust),
                                "--account-snapshot",
                                str(source),
                                "--account-trust-hash-file",
                                str(trust),
                                "--output-root",
                                str(root / "output"),
                            ]
                        ),
                        1,
                    )
            run, paper_trust = frozen_paper_run()
            account, account_trust = account_snapshot_at()
            paper = root / "paper.json"
            account_path = root / "account.json"
            paper_hash = root / "paper.hash"
            account_hash = root / "account.hash"
            paper.write_text(json.dumps(run), encoding="utf-8")
            account_path.write_text(
                json.dumps(account), encoding="utf-8"
            )
            paper_hash.write_text(paper_trust, encoding="ascii")
            account_hash.write_text(account_trust, encoding="ascii")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "--paper-run",
                            str(paper),
                            "--paper-trust-hash-file",
                            str(paper_hash),
                            "--account-snapshot",
                            str(account_path),
                            "--account-trust-hash-file",
                            str(account_hash),
                            "--output-root",
                            str(root / "naive"),
                        ],
                        clock=lambda: datetime(2026, 7, 27, 14),
                    ),
                    1,
                )


if __name__ == "__main__":
    unittest.main()
