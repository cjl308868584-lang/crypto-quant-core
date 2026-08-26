import inspect
import os
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

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
