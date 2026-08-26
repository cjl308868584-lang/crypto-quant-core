import inspect
import os
import socket
import stat
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from crypto_quant import challenger_replacement_v3_observer as observer_module
from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_v3_observer import (
    ChallengerReplacementV3Observation,
    observe_challenger_replacement_v3,
)


class ChallengerReplacementV3ObserverTests(unittest.TestCase):
    def test_not_installed_is_explicit_and_observer_accepts_no_paths(self):
        self.assertEqual(
            tuple(inspect.signature(observe_challenger_replacement_v3).parameters),
            (),
        )
        with patch(
            "crypto_quant.challenger_replacement_v3_observer._runtime_entry",
            return_value=None,
        ):
            observed = observe_challenger_replacement_v3()
        self.assertIsInstance(observed, ChallengerReplacementV3Observation)
        self.assertEqual(observed.evidence_health, "NOT_INSTALLED")
        self.assertEqual(observed.operational_qualification["status"], "NOT_STARTED")
        self.assertEqual(observed.economic_progress["status"], "TAIL_BLIND")
        self.assertEqual(observed.event_projection["events"], ())

    def test_installed_private_boundary_must_return_exact_typed_observation(self):
        sentinel = ChallengerReplacementV3Observation(
            deployment={"status": "V3_DEPLOYMENT_CANDIDATE_NOT_INSTALLABLE_NOT_ACTIVATED",
                        "authority": {"production_activation": False}},
            start_receipt_or_null=None,
            event_projection={"events": (), "opportunities": {},
                              "terminal_opportunity_count": 0,
                              "observed_opportunity_count": 0,
                              "missed_opportunity_count": 0,
                              "latest_next_snapshot_or_null": None},
            operational_qualification={"status": "ACTIVE"},
            economic_progress={"status": "TAIL_BLIND"},
            evidence_health="HEALTHY",
        )
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "runtime")
            os.mkdir(root, 0o700)
            with patch(
                "crypto_quant.challenger_replacement_v3_observer._RUNTIME_ROOT",
                root,
            ), patch(
                "crypto_quant.challenger_replacement_v3_observer._load_installed_observation",
                return_value=sentinel,
            ):
                self.assertIs(observe_challenger_replacement_v3(), sentinel)
            with patch(
                "crypto_quant.challenger_replacement_v3_observer._RUNTIME_ROOT",
                root,
            ), patch(
                "crypto_quant.challenger_replacement_v3_observer._load_installed_observation",
                return_value={},
            ):
                failed = observe_challenger_replacement_v3()
        self.assertEqual(failed.evidence_health, "FAILED_CLOSED")

    def test_installed_loader_composes_only_strict_fixed_sources(self):
        deployment = {
            "candidate_build": {"release_tag": "v0.76.0"},
            "authority": {"production_activation": False},
        }
        receipt = {"receipt_id": "receipt"}
        raw_projection = {"events": (), "opportunities": {}}
        public_projection = {
            "events": (), "opportunities": {},
            "terminal_opportunity_count": 0,
            "observed_opportunity_count": 0,
            "missed_opportunity_count": 0,
            "latest_next_snapshot_or_null": None,
        }
        state = SimpleNamespace(
            _replay=lambda: raw_projection, replay=lambda: public_projection,
        )
        identity = object()
        operational = {"status": "ACTIVE"}
        progress = {"status": "TAIL_BLIND"}
        fault_bytes = canonical_json({
            "runtime_core_identity": {
                "src/crypto_quant/challenger_replacement_events.py": "b" * 64,
            },
        }).encode("utf-8")
        with patch.object(
            observer_module, "_load_deployment", return_value=deployment,
            create=True,
        ), patch.object(
            observer_module, "_open_state", return_value=nullcontext((identity, state)),
            create=True,
        ), patch.object(
            observer_module, "_read_fixed", side_effect=(b"start", fault_bytes),
            create=True,
        ), patch.object(
            observer_module, "load_challenger_replacement_v3_start_receipt_bytes",
            return_value=receipt, create=True,
        ) as start_loader, patch.object(
            observer_module, "_load_fault_receipt",
            return_value={"status": "FAULT_MATRIX_PASSED"}, create=True,
        ) as fault_loader, patch.object(
            observer_module, "_build_operational_facts",
            return_value=object(), create=True,
        ), patch.object(
            observer_module, "_evaluate_operational",
            return_value=operational, create=True,
        ), patch.object(
            observer_module, "build_economic_progress_facts_from_state",
            return_value=object(), create=True,
        ), patch.object(
            observer_module, "observe_challenger_replacement_economic_progress",
            return_value=progress, create=True,
        ), patch.object(
            observer_module, "_observed_at", return_value="2026-08-26T00:00:00.000Z",
            create=True,
        ):
            value = observer_module._load_installed_observation(object())
        self.assertEqual(value.deployment, deployment)
        self.assertIs(value.start_receipt_or_null, receipt)
        self.assertIs(value.event_projection, public_projection)
        self.assertIs(value.operational_qualification, operational)
        self.assertIs(value.economic_progress, progress)
        start_loader.assert_called_once()
        fault_loader.assert_called_once()

    def test_observation_failure_does_not_append_or_repair(self):
        with patch(
            "crypto_quant.challenger_replacement_v3_observer._runtime_entry",
            side_effect=OSError("untrusted"),
        ), patch(
            "crypto_quant.challenger_replacement_events.publish_challenger_replacement_event"
        ) as publish:
            result = observe_challenger_replacement_v3()
        self.assertEqual(result.evidence_health, "FAILED_CLOSED")
        publish.assert_not_called()

    def test_unexpected_private_loader_failure_is_bounded_and_closes_root(self):
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "runtime")
            os.mkdir(root, 0o700)
            with patch(
                "crypto_quant.challenger_replacement_v3_observer._RUNTIME_ROOT",
                root,
            ), patch(
                "crypto_quant.challenger_replacement_v3_observer._load_installed_observation",
                side_effect=RuntimeError("private path"),
            ):
                result = observe_challenger_replacement_v3()
        self.assertEqual(result.evidence_health, "FAILED_CLOSED")

    def test_trusted_root_is_retained_for_loader_and_closed_after_observation(self):
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "runtime")
            os.mkdir(root, 0o700)
            received = []

            def load(capability):
                received.append((capability.fd, os.fstat(capability.fd).st_ino))
                return ChallengerReplacementV3Observation(
                    deployment={"authority": {}}, start_receipt_or_null=None,
                    event_projection={},
                    operational_qualification={"status": "ACTIVE"},
                    economic_progress={"status": "TAIL_BLIND"},
                    evidence_health="HEALTHY",
                )

            with patch(
                "crypto_quant.challenger_replacement_v3_observer._RUNTIME_ROOT",
                root,
            ), patch(
                "crypto_quant.challenger_replacement_v3_observer._load_installed_observation",
                side_effect=load,
            ):
                result = observe_challenger_replacement_v3()
            self.assertEqual(result.evidence_health, "HEALTHY")
            self.assertEqual(received[0][1], os.lstat(root).st_ino)
            with self.assertRaises(OSError):
                os.fstat(received[0][0])

    def test_special_symlink_hardlink_and_wrong_mode_roots_fail_without_mutation(self):
        with tempfile.TemporaryDirectory() as parent:
            sentinel = os.path.join(parent, "sentinel")
            with open(sentinel, "wb") as handle:
                handle.write(b"unchanged")
            candidates = []
            symlink = os.path.join(parent, "symlink")
            os.symlink(sentinel, symlink)
            candidates.append(symlink)
            hardlink = os.path.join(parent, "hardlink")
            os.link(sentinel, hardlink)
            candidates.append(hardlink)
            fifo = os.path.join(parent, "fifo")
            os.mkfifo(fifo, 0o600)
            candidates.append(fifo)
            wrong_mode = os.path.join(parent, "wrong-mode")
            os.mkdir(wrong_mode, 0o755)
            candidates.append(wrong_mode)
            sock_path = os.path.join(parent, "socket")
            listener = socket.socket(socket.AF_UNIX)
            listener.bind(sock_path)
            candidates.append(sock_path)
            with open(sentinel, "rb") as handle:
                before = (handle.read(), os.lstat(sentinel))
            try:
                for candidate in candidates:
                    with self.subTest(candidate=candidate), patch(
                        "crypto_quant.challenger_replacement_v3_observer._RUNTIME_ROOT",
                        candidate,
                    ):
                        self.assertEqual(
                            observe_challenger_replacement_v3().evidence_health,
                            "FAILED_CLOSED",
                        )
            finally:
                listener.close()
            with open(sentinel, "rb") as handle:
                after = (handle.read(), os.lstat(sentinel))
            self.assertEqual(before[0], after[0])
            self.assertEqual(
                (before[1].st_ino, before[1].st_mode, before[1].st_nlink),
                (after[1].st_ino, after[1].st_mode, after[1].st_nlink),
            )


if __name__ == "__main__":
    unittest.main()
