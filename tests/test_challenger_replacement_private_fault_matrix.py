import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from jsonschema import Draft202012Validator
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from crypto_quant.evidence import artifact_self_hash
import crypto_quant.challenger_replacement_private_fault_matrix as fault_module
from crypto_quant.challenger_replacement_private_fault_matrix import (
    CASE_IDS, EXECUTABLE_INVENTORY_PATHS,
    PROBES,
    load_challenger_replacement_private_fault_matrix_bytes,
    run_challenger_replacement_private_fault_matrix,
)


ROOT = Path(__file__).resolve().parents[1]
V076 = ROOT / "artifacts/challenger-replacement/challenger-replacement-fault-matrix-v0.76.0.json"
EXPECTED_CASES = (
    "SIGNATURE_KNOWN_ANSWER", "SIGNATURE_PARAMETER_ORDER_MUTATION",
    "SIGNATURE_PERCENT_ENCODING_MUTATION", "CLOCK_AHEAD", "CLOCK_BEHIND",
    "SERVER_TIME_EXPIRED", "SERVER_TIME_PRODUCT_DISAGREEMENT", "DNS_FAILURE",
    "TLS_FAILURE", "REDIRECT_REJECTED", "PROXY_ENV_IGNORED", "HOST_REJECTED",
    "PATH_REJECTED", "DISCONNECT_BEFORE_SEND", "DISCONNECT_DURING_SEND",
    "DISCONNECT_AFTER_SEND", "ACK_LOSS_QUERY_RECOVERY", "VENUE_MINUS_1007_UNKNOWN",
    "VENUE_5XX_UNKNOWN", "MALFORMED_2XX_UNKNOWN", "RATE_LIMIT_418",
    "RATE_LIMIT_429", "DUPLICATE_CLIENT_ID", "QUERY_BEFORE_RETRY",
    "PROVEN_ABSENT_ONLY_BEFORE_FIRST_SEND", "PARTIAL_FILL", "CANCEL_FILL_RACE",
    "LATE_FILL", "OVERFILL", "CONFLICTING_FILL", "DUPLICATE_FEE",
    "FEE_CORRECTION_CONFLICT", "DUPLICATE_FUNDING", "FUNDING_CORRECTION_CONFLICT",
    "SAME_BYTES_DIFFERENT_IDENTITY", "PRIVATE_FRESH_PROCESS_UNKNOWN_REPLAY",
    "PRIVATE_FRESH_PROCESS_STOP_REPLAY", "SPOT_PERPETUAL_MUTUAL_EXCLUSION",
    "WRONG_POSITION_MODE", "WRONG_MULTI_ASSET_MODE", "WRONG_MARGIN_TYPE",
    "LEVERAGE_ABOVE_TWO", "PARTIAL_SHORT_REQUIRES_STOP_BEFORE_RETURN",
    "STOP_REJECTED", "STOP_LOST", "STOP_CANCEL_RACE", "STOP_REPLACEMENT_NO_GAP",
    "STOP_QUERY_MISMATCH", "BALANCE_DISAGREEMENT", "POSITION_DISAGREEMENT",
    "ORDER_DISAGREEMENT", "LEDGER_DISAGREEMENT", "DAILY_STOP",
    "DRAWDOWN_FLATTEN", "RESTART_PRESERVES_STOP",
    "UTC_ROLLOVER_ONLY_RESETS_DAILY_GATE", "CEREMONY_EXCLUDED_FROM_ECONOMICS",
    "READ_ONLY_UI_LOADER_FAILURE", "SECRET_ABSENT_FROM_LOGS_EXCEPTIONS_EVENTS_ARTIFACTS",
)


class ChallengerReplacementPrivateFaultMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.foundation = V076.read_bytes()
        cls.head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        cls.tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        with patch.object(fault_module, "_git_identity",
                          return_value=(cls.head, cls.tree)):
            cls.receipt = run_challenger_replacement_private_fault_matrix(
                v076_fault_receipt_bytes=cls.foundation,
            )
            cls.loaded_receipt = load_challenger_replacement_private_fault_matrix_bytes(
                cls.receipt, v076_fault_receipt_bytes=cls.foundation,
                expected_executable_checkpoint=cls.head,
                expected_executable_tree=cls.tree,
                expected_receipt_sha256=hashlib.sha256(cls.receipt).hexdigest(),
            )

    def run_and_load(self):
        return self.receipt, copy.deepcopy(self.loaded_receipt)

    def test_case_ids_are_exact_ordered_unique_atomic_probes(self):
        self.assertEqual(CASE_IDS, EXPECTED_CASES)
        self.assertEqual(tuple(PROBES), EXPECTED_CASES)
        self.assertEqual(len(set(PROBES.values())), len(EXPECTED_CASES))
        for case_id, probe in PROBES.items():
            with self.subTest(case_id=case_id):
                self.assertTrue(callable(probe))
                self.assertEqual(probe.__module__,
                                 "crypto_quant.challenger_replacement_private_fault_matrix")

    def test_campaign_seals_exact_primary_and_matching_independent_semantics(self):
        first, loaded = self.run_and_load()
        self.assertTrue(first.endswith(b"\n"))
        self.assertEqual(tuple(case["case_id"] for case in loaded["cases"]),
                         EXPECTED_CASES)
        self.assertTrue(all(case["status"] == "PASS" for case in loaded["cases"]))
        self.assertEqual(loaded["authority"], {
            "credential_reads": 0, "public_network_requests": 0,
            "private_network_requests": 0, "mutating_requests": 0,
            "economic_orders": 0, "fund_movement": 0,
            "production_state_writes": 0,
        })
        self.assertGreater(loaded["probe_activity"]["fixture_transport_requests"], 0)
        self.assertGreater(loaded["probe_activity"]["fixture_reconciliations"], 0)
        self.assertEqual(loaded["probe_activity"]["fresh_processes"], 3)
        replay = loaded["independent_replay"]
        self.assertTrue(replay["semantic_match"])
        self.assertEqual(replay["primary_case_semantic_hashes"],
                         replay["independent_case_semantic_hashes"])
        self.assertEqual(replay["primary_aggregate_semantic_hash"],
                         replay["independent_aggregate_semantic_hash"])
        self.assertEqual(replay["authority"], loaded["authority"])
        self.assertEqual(replay["probe_activity"], loaded["probe_activity"])
        self.assertEqual(loaded["status"], "PRIVATE_FAULT_MATRIX_PASSED_NOT_ACTIVATED")

    def test_semantic_projection_normalizes_only_closed_attachment_coordinates(self):
        publication = {
            "device": 10, "inode": 20, "uid": 501, "mode": 0o600,
            "nlink": 1, "size": 120, "sha256": "a" * 64,
        }
        case = {
            "case_id": "ACK_LOSS_QUERY_RECOVERY",
            "probe_id": "private_probe_ack_loss_query_recovery",
            "status": "PASS", "observed_code": "RETURNED",
            "fixture_bytes_utf8": canonical_json({
                "observed_boundary_inputs": [{
                    "boundary": "private_runtime_call",
                    "input": {"publication": publication, "quantity": "0.001"},
                }],
            }),
            "observed_result_bytes_utf8": canonical_json({
                "status": "TERMINAL_RECONCILED", "quantity": "0.001",
                "last_event_hash": "b" * 64,
            }),
            "observed_delta": {name: 0 for name in (
                "credential_reads", "public_network_requests",
                "private_network_requests", "mutating_requests",
                "economic_orders", "fund_movement", "production_state_writes")},
            "observed_activity": {
                "fixture_credential_reads": 0, "fixture_transport_requests": 1,
                "fixture_mutating_requests": 1, "fixture_order_intents": 1,
                "fixture_reconciliations": 1, "fresh_processes": 0,
            },
            "subprocess_or_null": None,
            "state_identity": {
                "applicability": "PUBLISHED_EVENT_AND_RESULT",
                "event_before_or_null": None,
                "event_after_or_null": "b" * 64,
                "artifact_before_or_null": None,
                "artifact_after_or_null": "c" * 64,
            },
        }
        changed_attachment = copy.deepcopy(case)
        changed_input = json.loads(changed_attachment["fixture_bytes_utf8"])
        changed_input["observed_boundary_inputs"][0]["input"]["publication"][
            "device"] = 11
        changed_input["observed_boundary_inputs"][0]["input"]["publication"][
            "inode"] = 21
        changed_attachment["fixture_bytes_utf8"] = canonical_json(changed_input)
        changed_result = json.loads(changed_attachment["observed_result_bytes_utf8"])
        changed_result["last_event_hash"] = "d" * 64
        changed_attachment["observed_result_bytes_utf8"] = canonical_json(changed_result)
        changed_attachment["state_identity"]["event_after_or_null"] = "d" * 64
        changed_attachment["state_identity"]["artifact_after_or_null"] = "e" * 64
        self.assertEqual(fault_module._semantic_case_projection(case),
                         fault_module._semantic_case_projection(changed_attachment))

        for path, value in (
                (("fixture", "publication", "sha256"), "f" * 64),
                (("fixture", "publication", "size"), 121),
                (("fixture", "publication", "mode"), 0o400),
                (("fixture", "quantity"), "0.002"),
                (("result", "quantity"), "0.002"),
                (("authority", "economic_orders"), 1)):
            altered = copy.deepcopy(case)
            if path[0] == "fixture":
                value_object = json.loads(altered["fixture_bytes_utf8"])
                target = value_object["observed_boundary_inputs"][0]["input"]
                if path[1] == "publication": target = target["publication"]
                target[path[-1]] = value
                altered["fixture_bytes_utf8"] = canonical_json(value_object)
            elif path[0] == "result":
                value_object = json.loads(altered["observed_result_bytes_utf8"])
                value_object[path[-1]] = value
                altered["observed_result_bytes_utf8"] = canonical_json(value_object)
            else:
                altered["observed_delta"][path[-1]] = value
            with self.subTest(path=path):
                self.assertNotEqual(fault_module._semantic_case_projection(case),
                                    fault_module._semantic_case_projection(altered))

        nested = copy.deepcopy(case)
        nested_result = json.loads(nested["observed_result_bytes_utf8"])
        nested_result["business_marker"] = {"last_event_hash": "f" * 64}
        nested["observed_result_bytes_utf8"] = canonical_json(nested_result)
        changed_nested = copy.deepcopy(nested)
        changed_nested_result = json.loads(
            changed_nested["observed_result_bytes_utf8"])
        changed_nested_result["business_marker"]["last_event_hash"] = "0" * 64
        changed_nested["observed_result_bytes_utf8"] = canonical_json(
            changed_nested_result)
        self.assertNotEqual(fault_module._semantic_case_projection(nested),
                            fault_module._semantic_case_projection(changed_nested))

    def test_cases_contain_observed_probe_and_boundary_evidence(self):
        _data, loaded = self.run_and_load()
        for case in loaded["cases"]:
            with self.subTest(case_id=case["case_id"]):
                self.assertEqual(case["probe_id"], "private_probe_" + case["case_id"].lower())
                fixture_bytes = case["fixture_bytes_utf8"].encode()
                result_bytes = case["observed_result_bytes_utf8"].encode()
                self.assertEqual(canonical_json(json.loads(fixture_bytes)),
                                 case["fixture_bytes_utf8"])
                self.assertEqual(canonical_json(json.loads(result_bytes)),
                                 case["observed_result_bytes_utf8"])
                self.assertEqual(hashlib.sha256(fixture_bytes).hexdigest(),
                                 case["fixture_sha256"])
                self.assertEqual(hashlib.sha256(result_bytes).hexdigest(),
                                 case["result_sha256"])
                self.assertIn(case["observed_code"], {"RETURNED", "REJECTED"})
                self.assertEqual(case["stdout_sha256"], hashlib.sha256(b"").hexdigest())
                self.assertEqual(case["stderr_sha256"], hashlib.sha256(b"").hexdigest())
                self.assertRegex(case["fixture_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(case["result_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(case["case_hash"], r"^[0-9a-f]{64}$")
                self.assertEqual(set(case["observed_delta"]), set(loaded["authority"]))
                self.assertEqual(set(case["observed_activity"]),
                                 set(loaded["probe_activity"]))
                self.assertTrue(all(isinstance(value, int) and value >= 0
                                    for value in case["observed_delta"].values()))
                fixture = json.loads(case["fixture_bytes_utf8"])
                self.assertGreater(len(fixture["observed_boundary_inputs"]), 0)
                identity = case["state_identity"]
                self.assertEqual(set(identity), {
                    "applicability", "event_before_or_null",
                    "event_after_or_null", "artifact_before_or_null",
                    "artifact_after_or_null",
                })
                if identity["applicability"] == "STATELESS_NOT_APPLICABLE":
                    self.assertTrue(all(identity[key] is None for key in identity
                                        if key != "applicability"))
                elif identity["applicability"] == "PUBLISHED_EVENT_ONLY":
                    self.assertRegex(identity["event_before_or_null"],
                                     r"^[0-9a-f]{64}$")
                    self.assertRegex(identity["event_after_or_null"],
                                     r"^[0-9a-f]{64}$")
                    self.assertNotEqual(identity["event_before_or_null"],
                                        identity["event_after_or_null"])
                    self.assertIsNone(identity["artifact_before_or_null"])
                    self.assertIsNone(identity["artifact_after_or_null"])
                else:
                    self.assertTrue(any(identity[key] is not None for key in identity
                                        if key != "applicability"))
        fresh = {case["case_id"]: case["subprocess_or_null"] for case in loaded["cases"]
                 if case["case_id"].startswith("PRIVATE_FRESH_PROCESS_")}
        self.assertEqual(set(fresh), {"PRIVATE_FRESH_PROCESS_UNKNOWN_REPLAY",
                                      "PRIVATE_FRESH_PROCESS_STOP_REPLAY"})
        for record in fresh.values():
            executable = Path(record["executable"])
            campaign_root = executable.parents[2]
            self.assertTrue(executable.is_absolute())
            self.assertEqual(record["argv"][0], record["executable"])
            self.assertTrue(campaign_root.name.startswith(
                "cq-v077-private-fault-campaign-"))
            self.assertFalse(campaign_root.exists())
            self.assertEqual(record["argv"][1:3], ["-I", "-m"])
            self.assertEqual(record["argv"][3],
                             "crypto_quant.challenger_replacement_private_fault_matrix")
            self.assertEqual(record["exit_status"], 0)
            self.assertRegex(record["stdout_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(record["stderr_sha256"], r"^[0-9a-f]{64}$")
        restart = next(case for case in loaded["cases"]
                       if case["case_id"] == "RESTART_PRESERVES_STOP")
        self.assertIsNotNone(restart["subprocess_or_null"])
        self.assertEqual(restart["subprocess_or_null"]["case_id"],
                         "RESTART_PRESERVES_STOP")
        secret = next(case for case in loaded["cases"] if case["case_id"] ==
                      "SECRET_ABSENT_FROM_LOGS_EXCEPTIONS_EVENTS_ARTIFACTS")
        secret_result = json.loads(secret["observed_result_bytes_utf8"])
        self.assertEqual(secret_result["occurrences"], {
            "artifacts": 0, "events": 0, "exceptions": 0, "logs": 0,
        })
        self.assertEqual(set(secret_result["surface_sha256"]),
                         {"artifacts", "events", "exceptions", "logs"})
        self.assertGreater(secret_result["surface_sizes"]["events"], 0)
        self.assertGreater(secret_result["surface_sizes"]["artifacts"], 0)
        self.assertGreater(secret_result["surface_sizes"]["exceptions"], 0)
        self.assertEqual(secret_result["surface_sizes"]["logs"], 0)
        self.assertTrue(secret_result["actual_transport_executed"])
        self.assertTrue(secret_result["actual_event_replayed"])
        by_id = {case["case_id"]: json.loads(case["observed_result_bytes_utf8"])
                 for case in loaded["cases"]}
        ack = by_id["ACK_LOSS_QUERY_RECOVERY"]
        self.assertEqual((ack["initial_status"], ack["recovered_status"],
                          ack["economic_send_count"], ack["recovery_send_count"]),
                         ("UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
                          "TERMINAL_RECONCILED", 1, 0))
        partial = by_id["PARTIAL_SHORT_REQUIRES_STOP_BEFORE_RETURN"]
        self.assertEqual((partial["status"], partial["protected_quantity"]),
                         ("PROTECTION_VERIFIED_RECONCILIATION_PENDING", "0.005"))
        replacement = by_id["STOP_REPLACEMENT_NO_GAP"]
        self.assertLess(replacement["candidate_verified_index"],
                        replacement["old_cancel_started_index"])
        self.assertEqual(replacement["replacement_stage"],
                         "BINANCE_STOP_REPLACEMENT_SUCCEEDED")

    def test_fixture_evidence_comes_from_actual_probe_boundaries(self):
        _data, loaded = self.run_and_load()
        fixtures = {
            case["case_id"]: json.loads(case["fixture_bytes_utf8"])
            for case in loaded["cases"]
        }
        ack_inputs = fixtures["ACK_LOSS_QUERY_RECOVERY"][
            "observed_boundary_inputs"]
        runtime_calls = [item for item in ack_inputs
                         if item["boundary"] == "private_runtime_call"]
        self.assertEqual(len(runtime_calls), 2)
        self.assertEqual(runtime_calls[0]["input"]["product"], "SPOT")
        self.assertEqual(
            [item["response_class"]
             for item in runtime_calls[0]["input"]["responses"]],
            ["RESPONSE_INVALID", "UNKNOWN"],
        )
        self.assertTrue(all(
            hashlib.sha256(item["body_utf8"].encode()).hexdigest()
            == item["body_sha256"]
            for call in runtime_calls
            for item in call["input"]["responses"]
        ))

        preflight_inputs = fixtures["LEVERAGE_ABOVE_TWO"][
            "observed_boundary_inputs"]
        preflight = next(item for item in preflight_inputs
                         if item["boundary"] == "account_preflight")
        symbol = json.loads(preflight["input"]["responses"][
            "FUTURES_SYMBOL_CONFIG"])
        self.assertEqual(symbol[0]["leverage"], 3)

        fresh = fixtures["PRIVATE_FRESH_PROCESS_UNKNOWN_REPLAY"][
            "runtime_state_transition_or_null"]
        self.assertTrue(fresh["process_boundary_replay"])
        self.assertGreater(fresh["event_count_after"],
                           fresh["event_count_before"])
        self.assertRegex(fresh["last_event_hash_before"], r"^[0-9a-f]{64}$")

    def test_inventory_and_foundation_are_exactly_bound(self):
        _data, loaded = self.run_and_load()
        self.assertEqual(loaded["executable_checkpoint"], self.head)
        self.assertEqual(loaded["executable_tree"], self.tree)
        self.assertEqual(loaded["foundation"]["artifact_sha256"],
                         hashlib.sha256(self.foundation).hexdigest())
        self.assertEqual(loaded["foundation"]["artifact_sha256"],
                         fault_module._V076_ARTIFACT_SHA256)
        self.assertGreater(len(loaded["executable_inventory"]), 10)
        self.assertEqual(tuple(item["path"] for item in loaded["executable_inventory"]),
                         EXECUTABLE_INVENTORY_PATHS)

    def test_probes_are_direct_module_owned_bindings_not_one_label_dispatcher(self):
        source = (ROOT / "src/crypto_quant/challenger_replacement_private_fault_matrix.py").read_text()
        self.assertNotIn("def _dispatch(", source)
        self.assertNotIn("tests.", source)
        self.assertNotIn("unittest.TestCase", source)
        self.assertEqual(frozenset(EXECUTABLE_INVENTORY_PATHS), {
            item["path"] for item in self.run_and_load()[1]["executable_inventory"]
        })

    def test_git_identity_rejects_any_inventory_blob_not_equal_to_head(self):
        real_run = fault_module.subprocess.run
        def changed(command, **kwargs):
            if command[:2] == ["git", "show"]:
                return type("Result", (), {"returncode": 0,
                                             "stdout": b"different"})()
            return real_run(command, **kwargs)
        with patch.object(fault_module.subprocess, "run", side_effect=changed), \
                self.assertRaisesRegex(ValueError, "EXECUTABLE_CHECKPOINT_DIRTY"):
            fault_module._git_identity()

    def test_isolated_python_uses_portable_temp_base_and_rejects_untrusted_root(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(fault_module.sys, "platform", "linux"), \
                patch.object(fault_module.tempfile, "gettempdir", return_value=directory):
            base = Path(directory)
            self.assertEqual(fault_module._temporary_base(), base)
            root = base / ("isolated-python-" + "a" * 16)
            root.mkdir(mode=0o755)
            before = root.lstat()
            with self.assertRaisesRegex(ValueError, "PRIVATE_FAULT_VENV_UNTRUSTED"):
                fault_module._isolated_python("a" * 64, base)
            after = root.lstat()
            self.assertEqual((before.st_dev, before.st_ino, before.st_mode),
                             (after.st_dev, after.st_ino, after.st_mode))

    def test_isolated_python_rejects_replaced_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            command = fault_module._isolated_python("b" * 64, Path(directory))
            executable = Path(command[0])
            executable.unlink()
            executable.symlink_to("/bin/sh")
            with self.assertRaisesRegex(ValueError, "PRIVATE_FAULT_VENV_UNTRUSTED"):
                fault_module._isolated_python("b" * 64, Path(directory))

    def test_isolated_python_rejects_symlinked_path_file_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            fault_module._isolated_python("c" * 64, Path(directory))
            root = Path(directory) / ("isolated-python-" + "c" * 16)
            path = next(root.glob("lib/python*/site-packages/crypto-quant-v077-private-fault.pth"))
            sentinel = Path(directory) / "sentinel"
            sentinel.write_bytes(path.read_bytes()); before_bytes, before = sentinel.read_bytes(), sentinel.stat()
            path.unlink(); path.symlink_to(sentinel)
            with self.assertRaisesRegex(ValueError, "PRIVATE_FAULT_VENV_UNTRUSTED"):
                fault_module._isolated_python("c" * 64, Path(directory))
            after = sentinel.stat()
            self.assertEqual((before_bytes, before.st_ino, before.st_mode),
                             (sentinel.read_bytes(), after.st_ino, after.st_mode))

    def test_isolated_python_has_closed_site_packages_and_rejects_extra_pth(self):
        with tempfile.TemporaryDirectory() as directory:
            fault_module._isolated_python("d" * 64, Path(directory))
            root = Path(directory) / ("isolated-python-" + "d" * 16)
            configuration = (root / "pyvenv.cfg").read_text()
            self.assertIn("include-system-site-packages = false", configuration)
            site = next(root.glob("lib/python*/site-packages"))
            self.assertEqual({item.name for item in site.iterdir()},
                             {"crypto-quant-v077-private-fault.pth"})
            sentinel = Path(directory) / "sentinel"
            sentinel.write_text("external-sentinel")
            extra = site / "evil.pth"
            extra.symlink_to(sentinel)
            before = (sentinel.read_bytes(), sentinel.lstat().st_ino,
                      sentinel.lstat().st_nlink, sentinel.lstat().st_ctime_ns)
            with self.assertRaisesRegex(ValueError,
                                        "PRIVATE_FAULT_VENV_UNTRUSTED"):
                fault_module._isolated_python("d" * 64, Path(directory))
            after = (sentinel.read_bytes(), sentinel.lstat().st_ino,
                     sentinel.lstat().st_nlink, sentinel.lstat().st_ctime_ns)
            self.assertEqual(before, after)

    def test_fresh_processes_return_their_own_guarded_runtime_evidence(self):
        _inventory, core_hash = fault_module._inventory()
        with tempfile.TemporaryDirectory(dir=fault_module._temporary_base()) as directory:
            ledger = fault_module._BoundaryLedger(Path(directory))
            fault_module._ACTIVE_LEDGER = ledger
            try:
                unknown = fault_module._fresh_record(
                    "PRIVATE_FRESH_PROCESS_UNKNOWN_REPLAY", core_hash)
                stop = fault_module._fresh_record(
                    "PRIVATE_FRESH_PROCESS_STOP_REPLAY", core_hash)
            finally:
                fault_module._ACTIVE_LEDGER = None
        for record in (unknown, stop):
            with self.subTest(case_id=record["case_id"]):
                self.assertEqual(record["authority"], {
                    "credential_reads": 0, "public_network_requests": 0,
                    "private_network_requests": 0, "mutating_requests": 0,
                    "economic_orders": 0, "fund_movement": 0,
                    "production_state_writes": 0,
                })
                self.assertGreater(
                    record["probe_activity"]["fixture_transport_requests"], 0)
                self.assertGreater(
                    record["probe_activity"]["fixture_order_intents"], 0)
                self.assertGreater(
                    record["probe_activity"]["fixture_reconciliations"], 0)
                self.assertRegex(record["result_sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(record["result_sha256"],
                                 record["artifact_identity_sha256"])
                self.assertTrue(record["process_boundary_replay"])
                self.assertGreater(record["event_count_after"],
                                   record["event_count_before"])
                self.assertNotEqual(record["event_semantic_sha256_before"],
                                    record["event_semantic_sha256_after"])
                self.assertEqual(record["argv"][4], "--fresh")
                self.assertGreaterEqual(len(record["argv"]), 11)
        self.assertEqual(unknown["runtime_status_before"],
                         "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN")
        self.assertEqual(unknown["runtime_status_after"], "TERMINAL_RECONCILED")
        self.assertEqual(unknown["economic_send_count"], 1)
        self.assertEqual(unknown["recovery_send_count"], 0)
        self.assertEqual(stop["runtime_status_after"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        self.assertEqual(stop["recovery_send_count"], 0)

    def test_fresh_case_observation_is_the_child_runtime_result(self):
        _inventory, core_hash = fault_module._inventory()
        with tempfile.TemporaryDirectory(
                dir=fault_module._temporary_base()) as directory:
            record = fault_module._case(
                "PRIVATE_FRESH_PROCESS_UNKNOWN_REPLAY", core_hash,
                fault_module._BoundaryLedger(Path(directory)))
        child = record["subprocess_or_null"]
        self.assertEqual(record["result_sha256"], child["result_sha256"])
        self.assertEqual(record["observed_result_bytes_utf8"],
                         child["result_bytes_utf8"])
        self.assertEqual(json.loads(record["observed_result_bytes_utf8"])[
            "recovered_status"], "TERMINAL_RECONCILED")

    def test_activity_counts_only_at_actual_production_boundaries(self):
        ledger = fault_module._BoundaryLedger()
        fault_module._ACTIVE_LEDGER = ledger
        try:
            fault_module._private_context()
            self.assertEqual(
                ledger.activity()["fixture_order_intents"], 0,
                "building fixture context is not an order-intent boundary")
            with patch.object(fault_module, "_reconciliation_values",
                              side_effect=RuntimeError("before-boundary")), \
                    self.assertRaisesRegex(RuntimeError, "before-boundary"):
                fault_module._reconciliation_probe("DUPLICATE_FEE")
            self.assertEqual(
                ledger.activity()["fixture_reconciliations"], 0,
                "fixture assembly failure must not count reconciliation")
        finally:
            fault_module._ACTIVE_LEDGER = None

    def test_release_authority_guard_fails_closed_for_every_counter(self):
        guard = fault_module._ReleaseAuthorityGuard()
        for boundary in (
            "credential_reads", "public_network_requests",
            "private_network_requests", "mutating_requests",
            "economic_orders", "fund_movement", "production_state_writes",
        ):
            with self.subTest(boundary=boundary), self.assertRaisesRegex(
                    RuntimeError, "PRIVATE_FAULT_RELEASE_AUTHORITY_BLOCKED"):
                guard.block(boundary)
        self.assertEqual(guard.snapshot(), {
            "credential_reads": 1, "public_network_requests": 1,
            "private_network_requests": 1, "mutating_requests": 1,
            "economic_orders": 1, "fund_movement": 1,
            "production_state_writes": 1,
        })

    def test_fixture_capability_is_required_at_all_seven_release_boundaries(self):
        guard = fault_module._ReleaseAuthorityGuard()
        for boundary in (
            "credential_reads", "public_network_requests",
            "private_network_requests", "mutating_requests",
            "economic_orders", "fund_movement", "production_state_writes",
        ):
            with self.subTest(boundary=boundary), self.assertRaisesRegex(
                    RuntimeError,
                    "PRIVATE_FAULT_RELEASE_AUTHORITY_BLOCKED:" + boundary):
                guard.authorize_fixture(boundary, object())
        self.assertEqual(guard.snapshot(), {name: 1 for name in (
            "credential_reads", "public_network_requests",
            "private_network_requests", "mutating_requests",
            "economic_orders", "fund_movement", "production_state_writes")})

        allowed = fault_module._ReleaseAuthorityGuard()
        for boundary in allowed.snapshot():
            allowed.authorize_fixture(boundary, fault_module._FIXTURE_AUTHORITY)
        self.assertEqual(allowed.snapshot(), {name: 0 for name in allowed.snapshot()})

        ledger = fault_module._BoundaryLedger()
        with self.assertRaisesRegex(
                RuntimeError,
                "PRIVATE_FAULT_RELEASE_AUTHORITY_BLOCKED:fund_movement"):
            ledger.authorize_request("CAPITAL_WITHDRAW", fault_module._FIXTURE_AUTHORITY)

    def test_restart_case_uses_a_real_process_boundary_and_preserves_stop(self):
        with tempfile.TemporaryDirectory(dir=fault_module._temporary_base()) as directory:
            ledger = fault_module._BoundaryLedger(Path(directory))
            fault_module._ACTIVE_LEDGER = ledger
            try:
                result = fault_module._misc_probe("RESTART_PRESERVES_STOP")
            finally:
                fault_module._ACTIVE_LEDGER = None
        self.assertTrue(result["process_boundary_replay"])
        self.assertEqual(result["runtime_status_after"],
                         "PROTECTION_VERIFIED_RECONCILIATION_PENDING")
        self.assertEqual(result["recovery_send_count"], 0)
        self.assertGreater(result["event_count_after"],
                           result["event_count_before"])
        self.assertEqual(ledger.activity()["fresh_processes"], 1)

    def test_disconnect_before_send_is_not_a_dns_connect_failure(self):
        ledger = fault_module._BoundaryLedger()
        fault_module._ACTIVE_LEDGER = ledger
        try:
            dns = fault_module._transport_probe("DNS_FAILURE")
            disconnected = fault_module._transport_probe(
                "DISCONNECT_BEFORE_SEND")
        finally:
            fault_module._ACTIVE_LEDGER = None
        self.assertEqual(dns, {
            "outcome": "REJECTED",
            "reason_code": "CONNECT_FAILED",
        })
        self.assertEqual(disconnected, {
            "class": "UNKNOWN", "request_attempts": 1, "bytes_sent": 0,
        })

    def test_server_time_product_disagreement_observes_both_products(self):
        ledger = fault_module._BoundaryLedger()
        fault_module._ACTIVE_LEDGER = ledger
        try:
            result = fault_module._protocol_probe(
                "SERVER_TIME_PRODUCT_DISAGREEMENT")
        finally:
            fault_module._ACTIVE_LEDGER = None
        self.assertEqual(result["checked_products"], ["SPOT", "PERPETUAL"])
        self.assertEqual(result["spot_server_time_ms"], 10000)
        self.assertEqual(result["perpetual"], {
            "outcome": "REJECTED", "reason_code": "SERVER_TIME_INVALID",
        })

    def test_secret_probe_scans_actual_transport_event_and_artifact_bytes(self):
        with tempfile.TemporaryDirectory(dir=fault_module._temporary_base()) as directory:
            ledger = fault_module._BoundaryLedger(Path(directory))
            fault_module._ACTIVE_LEDGER = ledger
            try:
                result = fault_module._misc_probe(
                    "SECRET_ABSENT_FROM_LOGS_EXCEPTIONS_EVENTS_ARTIFACTS")
            finally:
                fault_module._ACTIVE_LEDGER = None
        self.assertTrue(result["actual_transport_executed"])
        self.assertTrue(result["actual_event_replayed"])
        self.assertEqual(result["occurrences"], {
            "artifacts": 0, "events": 0, "exceptions": 0, "logs": 0,
        })
        self.assertGreater(result["surface_sizes"]["events"], 0)
        self.assertGreater(result["surface_sizes"]["artifacts"], 0)
        self.assertGreater(result["surface_sizes"]["exceptions"], 0)

    def test_foundation_is_the_one_frozen_v076_artifact(self):
        altered = bytearray(self.foundation); altered[-2] ^= 1
        with patch.object(fault_module, "_git_identity",
                          return_value=(self.head, self.tree)), \
                self.assertRaises(ValueError):
            run_challenger_replacement_private_fault_matrix(
                v076_fault_receipt_bytes=bytes(altered),
            )

    def test_loader_rejects_every_mutable_evidence_layer(self):
        data, _loaded = self.run_and_load()
        original = json.loads(data)
        mutations = []
        def changed(path, value):
            candidate = copy.deepcopy(original); target = candidate
            for part in path[:-1]: target = target[part]
            target[path[-1]] = value; mutations.append(candidate)
        changed(("cases", 0, "status"), "FAIL")
        changed(("cases", 0, "fixture_bytes_utf8"), "{}")
        changed(("cases", 1, "fixture_sha256"), "0" * 64)
        changed(("cases", 1, "observed_code"), "REJECTED")
        changed(("cases", 1, "observed_result_bytes_utf8"), "null")
        changed(("cases", 1, "stdout_sha256"), "0" * 64)
        changed(("cases", 2, "observed_delta", "private_network_requests"), 1)
        changed(("cases", 3, "case_hash"), "0" * 64)
        changed(("aggregate_case_hash",), "0" * 64)
        changed(("independent_replay", "independent_case_semantic_hashes", 0,
                 "semantic_hash"), "0" * 64)
        changed(("independent_replay", "semantic_match"), False)
        changed(("executable_inventory", 0, "sha256"), "0" * 64)
        changed(("executable_core_hash",), "0" * 64)
        changed(("foundation", "artifact_sha256"), "0" * 64)
        changed(("receipt_hash",), "0" * 64)
        fresh_index = next(index for index, case in enumerate(original["cases"])
                           if case["subprocess_or_null"] is not None)
        changed(("cases", fresh_index, "subprocess_or_null", "exit_status"), 1)
        for candidate in mutations:
            with self.subTest(), patch.object(
                    fault_module, "_git_identity",
                    return_value=(self.head, self.tree)), self.assertRaises(ValueError):
                load_challenger_replacement_private_fault_matrix_bytes(
                    (canonical_json(candidate) + "\n").encode(),
                    v076_fault_receipt_bytes=self.foundation,
                    expected_executable_checkpoint=self.head,
                    expected_executable_tree=self.tree,
                    expected_receipt_sha256=hashlib.sha256(self.receipt).hexdigest(),
                )

    def test_loader_rejects_invalid_self_hash_before_expensive_replay(self):
        document = json.loads(self.receipt)
        document["cases"][0]["fixture_bytes_utf8"] = "{}"
        with patch.object(
                fault_module,
                "run_challenger_replacement_private_fault_matrix",
                side_effect=AssertionError("EXPENSIVE_REPLAY_CALLED")), \
                self.assertRaisesRegex(
                    ValueError,
                    "CHALLENGER_REPLACEMENT_PRIVATE_FAULT_RECEIPT_INVALID"):
            load_challenger_replacement_private_fault_matrix_bytes(
                (canonical_json(document) + "\n").encode(),
                v076_fault_receipt_bytes=self.foundation,
                expected_executable_checkpoint=self.head,
                expected_executable_tree=self.tree,
                expected_receipt_sha256=hashlib.sha256(self.receipt).hexdigest(),
            )

    def test_loader_accepts_valid_receipt_without_campaign_reexecution(self):
        with patch.object(fault_module, "_git_identity",
                          return_value=(self.head, self.tree)), \
                patch.object(fault_module, "_execute_campaign",
                             side_effect=AssertionError("CAMPAIGN_REEXECUTED")):
            loaded = load_challenger_replacement_private_fault_matrix_bytes(
                self.receipt, v076_fault_receipt_bytes=self.foundation,
                expected_executable_checkpoint=self.head,
                expected_executable_tree=self.tree,
                expected_receipt_sha256=hashlib.sha256(self.receipt).hexdigest(),
            )
        self.assertTrue(loaded["independent_replay"]["semantic_match"])

    def test_loader_rejects_fully_rehashed_case_tamper(self):
        data, _loaded = self.run_and_load()
        document = json.loads(data)
        document["cases"][0]["fixture_sha256"] = "0" * 64
        case = document["cases"][0]
        case["case_hash"] = hashlib.sha256(canonical_json({
            key: value for key, value in case.items() if key != "case_hash"
        }).encode()).hexdigest()
        document["aggregate_case_hash"] = hashlib.sha256(canonical_json([
            {"case_id": item["case_id"], "case_hash": item["case_hash"]}
            for item in document["cases"]
        ]).encode()).hexdigest()
        identity = hashlib.sha256(canonical_json({
            key: value for key, value in document.items()
            if key not in {"receipt_id", "receipt_hash"}
        }).encode()).hexdigest()
        document["receipt_id"] = (
            "challenger_replacement_private_fault_matrix_" + identity
        )
        document["receipt_hash"] = artifact_self_hash(document, "receipt_hash")
        tampered = (canonical_json(document) + "\n").encode()
        with patch.object(fault_module, "_git_identity",
                          return_value=(self.head, self.tree)), \
                self.assertRaises(ValueError):
            load_challenger_replacement_private_fault_matrix_bytes(
                tampered, v076_fault_receipt_bytes=self.foundation,
                expected_executable_checkpoint=self.head,
                expected_executable_tree=self.tree,
                expected_receipt_sha256=hashlib.sha256(self.receipt).hexdigest(),
            )

    def test_external_receipt_digest_rejects_coordinated_fully_rehashed_tamper(self):
        document = json.loads(self.receipt)
        case = next(item for item in document["cases"]
                    if item["case_id"] == "ACK_LOSS_QUERY_RECOVERY")
        result = json.loads(case["observed_result_bytes_utf8"])
        result["economic_send_count"] = 0
        case["observed_result_bytes_utf8"] = canonical_json(result)
        case["result_sha256"] = hashlib.sha256(
            case["observed_result_bytes_utf8"].encode()).hexdigest()
        case["case_hash"] = hashlib.sha256(canonical_json({
            key: value for key, value in case.items() if key != "case_hash"
        }).encode()).hexdigest()
        document["aggregate_case_hash"] = hashlib.sha256(canonical_json([
            {"case_id": item["case_id"], "case_hash": item["case_hash"]}
            for item in document["cases"]
        ]).encode()).hexdigest()
        semantics = fault_module._semantic_hashes(document["cases"])
        replay = document["independent_replay"]
        replay["primary_case_semantic_hashes"] = copy.deepcopy(semantics)
        replay["independent_case_semantic_hashes"] = copy.deepcopy(semantics)
        aggregate = hashlib.sha256(canonical_json(semantics).encode()).hexdigest()
        replay["primary_aggregate_semantic_hash"] = aggregate
        replay["independent_aggregate_semantic_hash"] = aggregate
        identity = hashlib.sha256(canonical_json({
            key: value for key, value in document.items()
            if key not in {"receipt_id", "receipt_hash"}
        }).encode()).hexdigest()
        document["receipt_id"] = (
            "challenger_replacement_private_fault_matrix_" + identity)
        document["receipt_hash"] = artifact_self_hash(document, "receipt_hash")
        tampered = (canonical_json(document) + "\n").encode()
        with patch.object(fault_module, "_git_identity",
                          return_value=(self.head, self.tree)), \
                self.assertRaisesRegex(
                    ValueError,
                    "CHALLENGER_REPLACEMENT_PRIVATE_FAULT_RECEIPT_INVALID"):
            load_challenger_replacement_private_fault_matrix_bytes(
                tampered, v076_fault_receipt_bytes=self.foundation,
                expected_executable_checkpoint=self.head,
                expected_executable_tree=self.tree,
                expected_receipt_sha256=hashlib.sha256(self.receipt).hexdigest(),
            )

    def test_schema_closes_root_build_case_authority_and_subprocess_objects(self):
        schema = json.loads((ROOT / "src/crypto_quant/schemas/challenger-replacement-private-fault-receipt-v1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        for name in ("foundation", "buildIdentity", "predecessorManifest",
                     "inventoryItem", "case", "authority", "boundaryLedger", "probeActivity",
                     "semanticHash", "independentReplay", "subprocess"):
            self.assertFalse(schema["$defs"][name]["additionalProperties"])


class ChallengerReplacementPrivateFaultMatrixFailFastTests(unittest.TestCase):
    def test_oversized_receipt_is_rejected_before_external_digest_work(self):
        oversized = b"{" + b"x" * (4 * 1024 * 1024) + b"}\n"
        with patch.object(fault_module, "_digest",
                          side_effect=AssertionError("DIGEST_CALLED")) as digest, \
                self.assertRaisesRegex(
                    ValueError,
                    "CHALLENGER_REPLACEMENT_PRIVATE_FAULT_RECEIPT_INVALID"):
            fault_module.load_challenger_replacement_private_fault_matrix_bytes(
                oversized, v076_fault_receipt_bytes=b"x",
                expected_executable_checkpoint="1" * 40,
                expected_executable_tree="2" * 40,
                expected_receipt_sha256="3" * 64)
        digest.assert_not_called()

    def test_subprocess_semantics_normalize_only_campaign_executable_path(self):
        record = {
            "case_id": "PRIVATE_FRESH_PROCESS_UNKNOWN_REPLAY",
            "executable": "/private/tmp/campaign-a/bin/python",
            "exit_status": 0, "authority": {"economic_orders": 0},
            "probe_activity": {"fresh_processes": 1},
            "runtime_status_before": "UNKNOWN",
            "runtime_status_after": "TERMINAL_RECONCILED",
            "economic_send_count": 1, "recovery_send_count": 0,
            "process_boundary_replay": True, "event_count_before": 12,
            "event_count_after": 20,
            "event_semantic_sha256_before": "a" * 64,
            "event_semantic_sha256_after": "b" * 64,
        }
        changed_path = copy.deepcopy(record)
        changed_path["executable"] = "/private/tmp/campaign-b/bin/python"
        self.assertEqual(fault_module._semantic_subprocess(record),
                         fault_module._semantic_subprocess(changed_path))
        changed_business = copy.deepcopy(record)
        changed_business["economic_send_count"] = 2
        self.assertNotEqual(fault_module._semantic_subprocess(record),
                            fault_module._semantic_subprocess(changed_business))

    def test_secret_surface_semantics_normalize_only_identity_derived_hashes(self):
        _inventory, core_hash = fault_module._inventory()
        cases = []
        for _index in range(2):
            with tempfile.TemporaryDirectory(
                    dir=fault_module._temporary_base()) as directory:
                cases.append(fault_module._case(
                    "SECRET_ABSENT_FROM_LOGS_EXCEPTIONS_EVENTS_ARTIFACTS",
                    core_hash,
                    fault_module._BoundaryLedger(Path(directory))))
        first = fault_module._semantic_case_projection(cases[0])
        second = fault_module._semantic_case_projection(cases[1])
        self.assertEqual(first, second)
        altered = copy.deepcopy(cases[1])
        result = json.loads(altered["observed_result_bytes_utf8"])
        result["surface_sha256"]["exceptions"] = "f" * 64
        altered["observed_result_bytes_utf8"] = canonical_json(result)
        self.assertNotEqual(first,
            fault_module._semantic_case_projection(altered))

    def test_campaign_scratch_roots_are_distinct_and_owned_by_each_ledger(self):
        with tempfile.TemporaryDirectory() as first, \
                tempfile.TemporaryDirectory() as second:
            first_ledger = fault_module._BoundaryLedger(Path(first))
            second_ledger = fault_module._BoundaryLedger(Path(second))
            first_site = fault_module._site_root(
                "a" * 64, first_ledger.scratch_root)
            second_site = fault_module._site_root(
                "a" * 64, second_ledger.scratch_root)
            self.assertTrue(first_site.is_relative_to(Path(first)))
            self.assertTrue(second_site.is_relative_to(Path(second)))
            self.assertNotEqual(first_site, second_site)

    def test_runtime_case_records_exact_event_transition_without_fake_artifact(self):
        ledger = fault_module._BoundaryLedger()
        _inventory, core_hash = fault_module._inventory()
        case = fault_module._case("ACK_LOSS_QUERY_RECOVERY", core_hash, ledger)
        identity = case["state_identity"]
        self.assertEqual(identity["applicability"], "PUBLISHED_EVENT_ONLY")
        self.assertRegex(identity["event_before_or_null"], r"^[0-9a-f]{64}$")
        self.assertRegex(identity["event_after_or_null"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(identity["event_before_or_null"],
                            identity["event_after_or_null"])
        self.assertIsNone(identity["artifact_before_or_null"])
        self.assertIsNone(identity["artifact_after_or_null"])

    def test_server_time_product_probe_requires_public_fixture_authority(self):
        ledger = fault_module._BoundaryLedger()
        fault_module._ACTIVE_LEDGER = ledger
        try:
            with patch.object(
                    fault_module, "_authorize_fixture",
                    side_effect=RuntimeError("PUBLIC_GUARD")), \
                    self.assertRaisesRegex(RuntimeError, "PUBLIC_GUARD"):
                fault_module._protocol_probe(
                    "SERVER_TIME_PRODUCT_DISAGREEMENT")
        finally:
            fault_module._ACTIVE_LEDGER = None

    def test_secret_event_probe_requires_state_fixture_authority_before_open(self):
        ledger = fault_module._BoundaryLedger()
        fault_module._ACTIVE_LEDGER = ledger
        original = fault_module._authorize_fixture
        def guarded(boundary):
            if boundary == "production_state_writes":
                raise RuntimeError("STATE_GUARD")
            return original(boundary)
        try:
            with patch.object(fault_module, "_authorize_fixture",
                              side_effect=guarded), \
                    patch.object(
                        fault_module,
                        "open_challenger_replacement_event_root",
                        side_effect=AssertionError("EVENT_ROOT_OPENED")), \
                    self.assertRaisesRegex(RuntimeError, "STATE_GUARD"):
                fault_module._misc_probe(
                    "SECRET_ABSENT_FROM_LOGS_EXCEPTIONS_EVENTS_ARTIFACTS")
        finally:
            fault_module._ACTIVE_LEDGER = None

    def test_invalid_foundation_fails_before_campaign_execution(self):
        altered = bytearray(V076.read_bytes())
        altered[-2] ^= 1
        with patch.object(fault_module, "_inventory",
                          return_value=([], "1" * 64)), \
                patch.object(fault_module, "_git_identity",
                             return_value=("2" * 40, "3" * 40)), \
                patch.object(fault_module, "_execute_campaign",
                             side_effect=AssertionError("CAMPAIGN_EXECUTED")), \
                self.assertRaises(ValueError):
            run_challenger_replacement_private_fault_matrix(
                v076_fault_receipt_bytes=bytes(altered),
            )


if __name__ == "__main__":
    unittest.main()
