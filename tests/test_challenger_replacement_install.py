import copy
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from tests.test_challenger_replacement_install_preflight import (
    OBSERVED,
    verified_inputs,
)
from tests.test_challenger_replacement_install_trust import ROOT, temporary_workspace


def install_inputs():
    from crypto_quant.challenger_replacement_install_preflight import (
        build_replacement_install_preflight_receipt,
    )

    inputs = verified_inputs()
    preflight = build_replacement_install_preflight_receipt(**inputs)
    contract_bytes = canonical_json(inputs["contract"]).encode()
    preflight_bytes = canonical_json(preflight).encode()
    return {
        "contract": inputs["contract"], "contract_bytes": contract_bytes,
        "preflight": preflight, "preflight_bytes": preflight_bytes,
        "plist_bytes": b"<?xml version='1.0'?><plist></plist>",
    }


def command(code=0, stdout=b"", stderr=b""):
    return code, stdout, stderr


def launchctl_print_bytes(contract):
    runtime = contract["runtime"]
    lines = [
        "{}/{} = {{".format("gui/501", contract["service"]["label"]),
        "\tpath = " + contract["paths"]["target_plist"],
        "\tstate = not running", "\tprogram = " + runtime["program_arguments"][0],
        "\targuments = {", *["\t\t" + item for item in runtime["program_arguments"]],
        "\t}", "\tworking directory = " + runtime["working_directory"],
        "\tenvironment = {", *[
            "\t\t{} => {}".format(key, value)
            for key, value in sorted({
                **runtime["environment"],
                "XPC_SERVICE_NAME": contract["service"]["label"],
            }.items())
        ], "\t}", "\truns = 0", "\tlast exit code = (never exited)", "}",
    ]
    return ("\n".join(lines) + "\n").encode()


class ReplacementInstallTests(unittest.TestCase):
    def test_success_uses_only_print_bootstrap_print_and_builds_receipt(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        target = inputs["contract"]["paths"]["target_plist"]
        print_argv = ("/bin/launchctl", "print", inputs["contract"]["service"]["identity"])
        bootstrap = ("/bin/launchctl", "bootstrap", "gui/501", target)
        post = b"label snapshot target schedule runs = 0"
        record = {
            "path": target, "device": 1, "inode": 2, "owner_uid": 501,
            "mode": 384, "link_count": 1,
            "size_bytes": len(inputs["plist_bytes"]),
            "sha256": hashlib.sha256(inputs["plist_bytes"]).hexdigest(),
        }
        with mock.patch.object(
            install, "_load_fixed_install_inputs", return_value=inputs
        ), mock.patch.object(
            install, "_now", return_value=OBSERVED + timedelta(minutes=5)
        ), mock.patch.object(
            install, "_target_absent", return_value=True
        ), mock.patch.object(
            install, "_publish_plist", return_value=("PUBLISHED", record)
        ), mock.patch.object(
            install, "_command",
            side_effect=[command(113), command(0), command(0, post)]
        ) as runner, mock.patch.object(
            install, "_post_print_valid", return_value=True
        ), mock.patch.object(
            install, "_publish_install_receipt", return_value="PUBLISHED"
        ) as publish:
            result = install.install_fixed_replacement_launch_agent()
        self.assertEqual([call.args[0] for call in runner.call_args_list],
                         [print_argv, bootstrap, print_argv])
        receipt = result["receipt"]
        self.assertEqual(receipt["status"], "INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT")
        self.assertEqual(receipt["authority"]["launchctl_read_count"], 2)
        self.assertEqual(receipt["authority"]["launchctl_mutation_count"], 1)
        self.assertEqual(receipt["authority"]["runtime_invocation_count"], 0)
        publish.assert_called_once()

    def test_expired_preflight_stops_before_print_plist_or_receipt_write(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        with mock.patch.object(
            install, "_load_fixed_install_inputs", return_value=inputs
        ), mock.patch.object(
            install, "_now", return_value=OBSERVED + timedelta(minutes=31)
        ), mock.patch.object(install, "_command") as command_call, \
             mock.patch.object(install, "_publish_plist") as plist, \
             mock.patch.object(install, "_publish_install_receipt") as receipt:
            with self.assertRaisesRegex(
                install.ReplacementInstallError,
                "CHALLENGER_REPLACEMENT_INSTALL_PREFLIGHT_EXPIRED",
            ):
                install.install_fixed_replacement_launch_agent()
        command_call.assert_not_called()
        plist.assert_not_called()
        receipt.assert_not_called()

    def test_bootstrap_failure_rolls_back_only_new_plist_and_writes_no_receipt(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        record = {"device": 1, "inode": 2}
        with mock.patch.object(
            install, "_load_fixed_install_inputs", return_value=inputs
        ), mock.patch.object(
            install, "_now", return_value=OBSERVED + timedelta(minutes=5)
        ), mock.patch.object(
            install, "_target_absent", return_value=True
        ), mock.patch.object(
            install, "_publish_plist", return_value=("PUBLISHED", record)
        ), mock.patch.object(
            install, "_command", side_effect=[command(113), command(9, b"", b"failed")]
        ), mock.patch.object(install, "_rollback_plist") as rollback, \
             mock.patch.object(install, "_publish_install_receipt") as receipt:
            with self.assertRaisesRegex(
                install.ReplacementInstallError,
                "CHALLENGER_REPLACEMENT_INSTALL_BOOTSTRAP_FAILED",
            ):
                install.install_fixed_replacement_launch_agent()
        rollback.assert_called_once_with(record)
        receipt.assert_not_called()

    def test_inputs_are_replayed_after_plist_publish_before_bootstrap(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        changed = copy.deepcopy(inputs)
        changed["plist_bytes"] = inputs["plist_bytes"] + b"changed"
        record = {"device": 1, "inode": 2}
        with mock.patch.object(
            install, "_load_fixed_install_inputs", side_effect=[inputs, changed]
        ), mock.patch.object(
            install, "_now", return_value=OBSERVED + timedelta(minutes=5)
        ), mock.patch.object(install, "_target_absent", return_value=True), \
             mock.patch.object(install, "_publish_plist", return_value=("PUBLISHED", record)), \
             mock.patch.object(install, "_command", return_value=command(113)) as runner, \
             mock.patch.object(install, "_rollback_plist") as rollback:
            with self.assertRaisesRegex(
                install.ReplacementInstallError,
                "CHALLENGER_REPLACEMENT_INSTALL_SOURCE_CHANGED",
            ):
                install.install_fixed_replacement_launch_agent()
        runner.assert_called_once()
        rollback.assert_called_once_with(record)

    def test_same_bytes_new_inode_plist_never_reaches_bootstrap_or_rollback(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        record = {"device": 1, "inode": 2}
        replacement = {"device": 1, "inode": 3}
        with mock.patch.object(
            install, "_load_fixed_install_inputs", return_value=inputs
        ), mock.patch.object(
            install, "_now", return_value=OBSERVED + timedelta(minutes=5)
        ), mock.patch.object(install, "_target_absent", return_value=True), \
             mock.patch.object(install, "_publish_plist",
                               side_effect=[("PUBLISHED", record),
                                            ("ALREADY_PUBLISHED", replacement)]), \
             mock.patch.object(install, "_command", return_value=command(113)) as runner, \
             mock.patch.object(install, "_rollback_plist") as rollback:
            with self.assertRaisesRegex(
                install.ReplacementInstallError,
                "CHALLENGER_REPLACEMENT_INSTALL_TARGET_IDENTITY_CHANGED",
            ):
                install.install_fixed_replacement_launch_agent()
        runner.assert_called_once()
        rollback.assert_not_called()

    def test_plist_publication_and_rollback_bind_exact_inode_under_0755_parent(self):
        import crypto_quant.challenger_replacement_install as install

        with temporary_workspace() as directory:
            parent = Path(directory) / "LaunchAgents"
            parent.mkdir(mode=0o755)
            target = parent / "fixed.plist"
            contract = install_inputs()["contract"]
            contract["paths"]["target_plist"] = str(target)
            body = b"fixed-plist"
            outcome, record = install._publish_plist(contract, body)
            self.assertEqual(outcome, "PUBLISHED")
            self.assertEqual(target.read_bytes(), body)
            old_inode = target.stat().st_ino
            target.unlink()
            target.write_bytes(body)
            target.chmod(0o600)
            self.assertNotEqual(target.stat().st_ino, old_inode)
            with self.assertRaisesRegex(
                install.ReplacementInstallError,
                "CHALLENGER_REPLACEMENT_INSTALL_ROLLBACK_IDENTITY_MISMATCH",
            ):
                install._rollback_plist(record)
            self.assertEqual(target.read_bytes(), body)

            sentinel = Path(directory) / "sentinel"
            sentinel.write_bytes(b"sentinel")
            target.unlink()
            target.symlink_to(sentinel)
            before = (sentinel.read_bytes(), sentinel.stat().st_mode,
                      sentinel.stat().st_ino, sentinel.stat().st_nlink,
                      sentinel.stat().st_ctime_ns)
            with self.assertRaises(Exception):
                install._publish_plist(contract, body)
            after = (sentinel.read_bytes(), sentinel.stat().st_mode,
                     sentinel.stat().st_ino, sentinel.stat().st_nlink,
                     sentinel.stat().st_ctime_ns)
            self.assertEqual(before, after)

    def test_bootstrap_transport_unknown_keeps_plist_and_publishes_unknown(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        record = {
            "path": inputs["contract"]["paths"]["target_plist"],
            "device": 1, "inode": 2, "owner_uid": 501, "mode": 384,
            "link_count": 1, "size_bytes": len(inputs["plist_bytes"]),
            "sha256": hashlib.sha256(inputs["plist_bytes"]).hexdigest(),
        }
        with mock.patch.object(
            install, "_load_fixed_install_inputs", return_value=inputs
        ), mock.patch.object(
            install, "_now", return_value=OBSERVED + timedelta(minutes=5)
        ), mock.patch.object(install, "_target_absent", return_value=True), \
             mock.patch.object(install, "_publish_plist", return_value=("PUBLISHED", record)), \
             mock.patch.object(install, "_command",
                               side_effect=[command(113), TimeoutError("unknown")]), \
             mock.patch.object(install, "_rollback_plist") as rollback, \
             mock.patch.object(install, "_publish_install_receipt", return_value="PUBLISHED"):
            result = install.install_fixed_replacement_launch_agent()
        rollback.assert_not_called()
        self.assertEqual(result["receipt"]["status"], "INSTALL_STATE_UNKNOWN_FAILED_CLOSED")
        self.assertIn("INSTALL_BOOTSTRAP_STATE_UNKNOWN", result["receipt"]["reason_codes"])
        self.assertEqual(result["receipt"]["authority"]["launchctl_read_count"], 1)

    def test_post_bootstrap_source_replacement_prevents_receipt_publication(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        changed = copy.deepcopy(inputs)
        changed["contract_bytes"] += b"changed"
        record = {
            "path": inputs["contract"]["paths"]["target_plist"],
            "device": 1, "inode": 2, "owner_uid": 501, "mode": 384,
            "link_count": 1, "size_bytes": len(inputs["plist_bytes"]),
            "sha256": hashlib.sha256(inputs["plist_bytes"]).hexdigest(),
        }
        with mock.patch.object(
            install, "_load_fixed_install_inputs",
            side_effect=[inputs, inputs, changed]
        ), mock.patch.object(
            install, "_now", return_value=OBSERVED + timedelta(minutes=5)
        ), mock.patch.object(install, "_target_absent", return_value=True), \
             mock.patch.object(install, "_publish_plist",
                               return_value=("PUBLISHED", record)), \
             mock.patch.object(install, "_command",
                               side_effect=[command(113), command(0),
                                            command(0, launchctl_print_bytes(inputs["contract"]))]), \
             mock.patch.object(install, "_publish_install_receipt") as publish:
            with self.assertRaisesRegex(
                install.ReplacementInstallError,
                "CHALLENGER_REPLACEMENT_INSTALL_SOURCE_CHANGED",
            ):
                install.install_fixed_replacement_launch_agent()
        publish.assert_not_called()

    def test_post_print_failure_publishes_unknown_without_bootout(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        record = {
            "path": inputs["contract"]["paths"]["target_plist"],
            "device": 1, "inode": 2, "owner_uid": 501, "mode": 384,
            "link_count": 1, "size_bytes": len(inputs["plist_bytes"]),
            "sha256": hashlib.sha256(inputs["plist_bytes"]).hexdigest(),
        }
        with mock.patch.object(
            install, "_load_fixed_install_inputs", return_value=inputs
        ), mock.patch.object(
            install, "_now", return_value=OBSERVED + timedelta(minutes=5)
        ), mock.patch.object(install, "_target_absent", return_value=True), \
             mock.patch.object(install, "_publish_plist", return_value=("PUBLISHED", record)), \
             mock.patch.object(install, "_command",
                               side_effect=[command(113), command(0), command(1, b"", b"bad")]), \
             mock.patch.object(install, "_publish_install_receipt", return_value="PUBLISHED"):
            result = install.install_fixed_replacement_launch_agent()
        self.assertEqual(result["receipt"]["status"], "INSTALL_STATE_UNKNOWN_FAILED_CLOSED")
        self.assertIn("INSTALL_POST_PRINT_INVALID", result["receipt"]["reason_codes"])

    def test_post_print_requires_frozen_contract_fields_and_zero_runs(self):
        import crypto_quant.challenger_replacement_install as install

        contract = install_inputs()["contract"]
        self.assertTrue(install._post_print_valid(
            contract, command(0, launchctl_print_bytes(contract))
        ))
        spoofed = launchctl_print_bytes(contract).replace(
            b"\tpath = ", b"\tpath = /wrong\n\tpath = ", 1
        )
        self.assertFalse(install._post_print_valid(
            contract, command(0, spoofed)
        ))

    def test_loader_rejects_extra_key_and_wrong_preflight_binding(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        receipt = install.build_replacement_install_receipt(
            contract=inputs["contract"], contract_bytes=inputs["contract_bytes"],
            preflight=inputs["preflight"], preflight_bytes=inputs["preflight_bytes"],
            status="INSTALL_STATE_UNKNOWN_FAILED_CLOSED", installed_at=OBSERVED,
            plist_record={
                "path": inputs["contract"]["paths"]["target_plist"],
                "device": 1, "inode": 2, "owner_uid": 501, "mode": 384,
                "link_count": 1, "size_bytes": 1, "sha256": "a" * 64,
            }, commands=[
                install._transcript((
                    "/bin/launchctl", "print",
                    inputs["contract"]["service"]["identity"],
                ), command(113)),
                install._transcript((
                    "/bin/launchctl", "bootstrap", "gui/501",
                    inputs["contract"]["paths"]["target_plist"],
                ), command(255)),
            ], reason_codes=["INSTALL_POST_PRINT_INVALID"],
        )
        altered = copy.deepcopy(receipt)
        altered["extra"] = True
        with self.assertRaisesRegex(
            install.ReplacementInstallError,
            "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_INVALID",
        ):
            install.load_replacement_install_receipt_bytes(
                canonical_json(altered).encode(), contract=inputs["contract"],
                contract_bytes=inputs["contract_bytes"],
                preflight=inputs["preflight"],
                preflight_bytes=inputs["preflight_bytes"],
            )

    def test_builder_rejects_forbidden_or_inconsistent_command_sequence(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        commands = [
            install._transcript(("/bin/launchctl", "print", "wrong"), command(113)),
            install._transcript((
                "/bin/launchctl", "bootstrap", "gui/501",
                inputs["contract"]["paths"]["target_plist"],
            ), command(255)),
        ]
        with self.assertRaisesRegex(
            install.ReplacementInstallError,
            "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_INVALID",
        ):
            install.build_replacement_install_receipt(
                contract=inputs["contract"], contract_bytes=inputs["contract_bytes"],
                preflight=inputs["preflight"], preflight_bytes=inputs["preflight_bytes"],
                status="INSTALL_STATE_UNKNOWN_FAILED_CLOSED", installed_at=OBSERVED,
                plist_record={
                    "path": inputs["contract"]["paths"]["target_plist"],
                    "device": 1, "inode": 2, "owner_uid": 501, "mode": 384,
                    "link_count": 1, "size_bytes": 1, "sha256": "a" * 64,
                }, commands=commands, reason_codes=["INSTALL_POST_PRINT_INVALID"],
            )

    def test_builder_rejects_time_outside_preflight_and_unknown_reason(self):
        import crypto_quant.challenger_replacement_install as install

        inputs = install_inputs()
        commands = [
            install._transcript((
                "/bin/launchctl", "print",
                inputs["contract"]["service"]["identity"],
            ), command(113)),
            install._transcript((
                "/bin/launchctl", "bootstrap", "gui/501",
                inputs["contract"]["paths"]["target_plist"],
            ), command(255)),
        ]
        with self.assertRaisesRegex(
            install.ReplacementInstallError,
            "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_INVALID",
        ):
            install.build_replacement_install_receipt(
                contract=inputs["contract"], contract_bytes=inputs["contract_bytes"],
                preflight=inputs["preflight"], preflight_bytes=inputs["preflight_bytes"],
                status="INSTALL_STATE_UNKNOWN_FAILED_CLOSED",
                installed_at=OBSERVED + timedelta(minutes=31),
                plist_record={
                    "path": inputs["contract"]["paths"]["target_plist"],
                    "device": 1, "inode": 2, "owner_uid": 501, "mode": 384,
                    "link_count": 1, "size_bytes": 1, "sha256": "a" * 64,
                }, commands=commands, reason_codes=["UNREGISTERED_REASON"],
            )

    def test_cli_rejects_arguments_before_any_install_action(self):
        import crypto_quant.challenger_replacement_install_cli as cli

        with mock.patch.object(cli, "install_fixed_replacement_launch_agent") as install:
            with self.assertRaises(SystemExit):
                cli.main(["--kickstart"])
            install.assert_not_called()

    def test_schema_mirror_is_strict_and_valid(self):
        name = "challenger-replacement-install-receipt-v1.schema.json"
        config = ROOT / "config" / name
        package = ROOT / "src/crypto_quant/schemas" / name
        self.assertEqual(config.read_bytes(), package.read_bytes())
        schema = json.loads(config.read_text())
        self.assertFalse(schema["additionalProperties"])
        Draft202012Validator.check_schema(schema)


if __name__ == "__main__":
    unittest.main()
