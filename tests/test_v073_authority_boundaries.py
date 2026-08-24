"""Cross-component v0.73 authority, compatibility, and tail-blind gates."""

import ast
import hashlib
import inspect
import os
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from crypto_quant.challenger_replacement_readiness import (
    _ReplacementReadinessBoundary,
)
from crypto_quant.challenger_replacement_readiness_observer import (
    ChallengerReplacementReadinessReplaySource,
    observe_challenger_replacement_readiness,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from crypto_quant.system_paper_broker import SimulatedBroker
from crypto_quant.operations_alerts import (
    build_operations_status_body,
    derive_operations_alerts,
)
from crypto_quant.operations_projection_v2 import (
    _OperationsProjectionV2Boundary,
    build_operations_projection_v2,
)
from tests.test_challenger_replacement_readiness_observer import (
    PLAN_BYTES,
    ReadinessObserverWorkspace,
    _release_provenance,
)
from tests.test_operations_projection_v2 import sources as projection_sources


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "artifacts/challenger-replacement/challenger-replacement-plan-v0.69.0.json": "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
    "artifacts/challenger-replacement/challenger-replacement-plan-v3-supersession-v0.69.0.json": "1d4932712304a890c5ff0a393d9674c38e2459faa3954a957ac0439ea770a32d",
    "artifacts/challenger-replacement/challenger-replacement-v3-owner-attestation-v0.69.0.json": "b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7",
    "artifacts/challenger-replacement/challenger-replacement-v3-supersession-machine-evidence-v0.69.0.json": "170dcf26bffdf36149997ed9ceb7d8553735e53daef4e189f90974468662fae1",
    "artifacts/challenger-replacement/challenger-replacement-binance-simulation-contract-v0.71.0.json": "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f",
    "artifacts/challenger-replacement/challenger-replacement-binance-golden-fixture-manifest-v0.72.0.json": "c86993a5d56805eee3b703301f92d704cf0e7dacd06d4725a7ad9c3c16dd2b5f",
    "tests/fixtures/operations-projection-healthy.json": "bb1aec23580a2f18a723f33be86de3720a7b5a69342d5fbb82bc13a51707f0ba",
}


class V073CrossComponentTests(unittest.TestCase):
    def _observe(self, stream):
        workspace = ReadinessObserverWorkspace()
        self.addCleanup(workspace.close)
        workspace.run_stream(stream)
        start = "2026-08-24T00:00:00.000Z" if stream == "spot-cycle" else "2026-08-25T00:00:00.000Z"
        boundary = _ReplacementReadinessBoundary(
            qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
            start_opportunity_id_or_null="ETHUSDT@" + start,
            start_scheduled_for_or_null=start,
            start_observed_at_or_null=start.replace("00:00.000Z", "05:00.000Z"),
            observed_at="2026-08-26T00:25:00.000Z",
        )
        source = ChallengerReplacementReadinessReplaySource(workspace.state)
        return observe_challenger_replacement_readiness(
            plan_bytes=PLAN_BYTES,
            replay_source=source,
            boundary=boundary,
            release_provenance=_release_provenance(),
        )

    def test_both_fixture_streams_replay_to_tail_blind_read_only_status(self):
        for stream in ("spot-cycle", "perp-cycle"):
            with self.subTest(stream=stream):
                observation = self._observe(stream)
                source = projection_sources(observation)
                projected_at = observation.observed_at
                projection_boundary = _OperationsProjectionV2Boundary(
                    qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
                    observed_at=projected_at,
                )
                with patch.object(os, "write", side_effect=AssertionError("write")), patch(
                    "pathlib.Path.write_bytes", side_effect=AssertionError("write_bytes")
                ), patch(
                    "pathlib.Path.write_text", side_effect=AssertionError("write_text")
                ), patch.object(
                    subprocess, "run", side_effect=AssertionError("subprocess")
                ), patch(
                    "socket.socket", side_effect=AssertionError("network")
                ), patch.object(
                    ChallengerReplacementOpportunityState,
                    "append",
                    side_effect=AssertionError("event publish"),
                ), patch.object(
                    SimulatedBroker,
                    "submit",
                    side_effect=AssertionError("broker/order"),
                ), patch.object(
                    os, "system", side_effect=AssertionError("launchctl")
                ):
                    first = build_operations_projection_v2(
                        source, boundary=projection_boundary
                    )
                    second = build_operations_projection_v2(
                        source, boundary=projection_boundary
                    )
                    alerts = derive_operations_alerts(first)
                    status = build_operations_status_body(first)
                self.assertEqual(first, second)
                self.assertEqual(observation.authority_status, "FIXTURE_NOT_OPERATIONAL")
                self.assertFalse(alerts["new_risk_allowed"])
                alert_ids = [item["alert_id"] for item in alerts["alerts"]]
                self.assertIn("OPS-CHALLENGER-EVIDENCE-STALE", alert_ids)
                self.assertIn("OPS-PAPER-EVIDENCE-STALE", alert_ids)
                self.assertNotIn(b"pnl", status.lower())
                self.assertNotIn(b"profit", status.lower())

    def test_confirmed_failure_facts_flow_to_projection_and_critical_alerts(self):
        base = self._observe("spot-cycle")
        cases = (
            ({"unknown_order_count": 1}, "OPS-REPLACEMENT-UNKNOWN-ORDER"),
            (
                {"reconciliation_status": "FAILED_CLOSED"},
                "OPS-REPLACEMENT-RECONCILIATION-FAILED",
            ),
            (
                {
                    "current_position": "SPOT_LONG",
                    "protective_stop_status": "MISSING_OR_UNCONFIRMED",
                },
                "OPS-REPLACEMENT-STOP-FAILED",
            ),
        )
        for fact_overrides, expected_alert in cases:
            with self.subTest(expected_alert=expected_alert):
                observation = replace(
                    base,
                    facts=replace(base.facts, **fact_overrides),
                    operational=replace(
                        base.operational,
                        policy_status="OPERATIONAL_QUALIFICATION_DID_NOT_PASS",
                        reason_codes=("CONFIRMED_FIXTURE_SAFETY_FAILURE",),
                    ),
                    economic=replace(
                        base.economic,
                        status="FAILED_CLOSED",
                        unresolved_safety_failure=True,
                    ),
                )
                boundary = _OperationsProjectionV2Boundary(
                    qualification="COMMITTED_FIXTURE_BOUNDARY_NOT_OPERATIONAL",
                    observed_at=observation.observed_at,
                )
                body = build_operations_projection_v2(
                    projection_sources(observation), boundary=boundary
                )
                result = derive_operations_alerts(body)
                self.assertIn(
                    expected_alert,
                    [item["alert_id"] for item in result["alerts"]],
                )
                self.assertFalse(result["new_risk_allowed"])


class V073FrozenAndStaticAuthorityTests(unittest.TestCase):
    def test_released_governance_fixture_and_v1_bytes_are_frozen(self):
        for relative, expected in FROZEN.items():
            with self.subTest(relative=relative):
                self.assertEqual(
                    hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                    expected,
                )
        digest = hashlib.sha256()
        fixture_root = ROOT / "tests/fixtures/challenger_replacement_v072"
        files = sorted(fixture_root.glob("*/*.json"))
        self.assertEqual(len(files), 14)
        for path in files:
            digest.update(str(path.relative_to(fixture_root)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        self.assertEqual(
            digest.hexdigest(),
            "aa7edf9b470b7f6594fbec037d58d3485e4e0955805a7754c2003026fa8476a0",
        )

    def test_new_modules_import_no_operational_authority(self):
        forbidden_imports = {
            "socket", "subprocess", "sqlite3", "keyring", "requests",
            "urllib", "crypto_quant.system_paper_broker",
            "crypto_quant.challenger_forward_runner",
        }
        forbidden_parameters = {
            "api_key", "credential", "secret", "broker", "order_submitter",
            "production_root", "launchctl", "install", "start_service",
        }
        modules = (
            "challenger_replacement_readiness.py",
            "challenger_replacement_readiness_observer.py",
            "operations_projection_v2.py",
            "operations_alerts.py",
        )
        source_root = ROOT / "src/crypto_quant"
        for name in modules:
            tree = ast.parse((source_root / name).read_text(encoding="utf-8"))
            imports = set()
            parameters = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.lstrip("."))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        parameters.update(arg.arg for arg in node.args.args)
                        parameters.update(arg.arg for arg in node.args.kwonlyargs)
            with self.subTest(name=name):
                self.assertTrue(imports.isdisjoint(forbidden_imports), imports)
                self.assertTrue(parameters.isdisjoint(forbidden_parameters), parameters)


if __name__ == "__main__":
    unittest.main()
