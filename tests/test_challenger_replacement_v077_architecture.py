from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1] / "src" / "crypto_quant"
REPOSITORY = ROOT.parents[1]
V076_BUILD_INPUT_TREE = "4d8e9acf8e68c037c8ad274d970bfe67c71d4766"
PROTOCOL_TRANSPORT = (
    "challenger_replacement_binance_private_protocol.py",
    "challenger_replacement_binance_private_transport.py",
)
CREDENTIAL = ("challenger_replacement_binance_credential.py",)
PREFLIGHT = ("challenger_replacement_binance_preflight.py",)
PRIVATE_PROJECTION = (
    "challenger_replacement_binance_private_contract.py",
)
ORDER_RUNTIME = (
    "challenger_replacement_binance_private_lifecycle.py",
    "challenger_replacement_binance_reconciliation.py",
    "challenger_replacement_binance_private_runtime.py",
)
CONTROLLERS = (
    "challenger_replacement_canary_controller.py",
    "challenger_replacement_private_fault_matrix.py",
)
OPPORTUNITY_PROJECTION = (
    "src/crypto_quant/challenger_replacement_opportunity_projection.py",
)
EVENT_STORAGE = (
    "src/crypto_quant/challenger_replacement_events.py",
)
DELIVERY = (
    "src/crypto_quant/operations_projection_v3.py",
    "src/crypto_quant/operations_alerts.py",
    "src/crypto_quant/dashboard/app.js",
)
RELEASE_METADATA = (
    "src/crypto_quant/__init__.py",
    "src/crypto_quant/build.py",
)
V078_ACTIVATION_CODE = {
    "src/crypto_quant/challenger_replacement_install.py",
    "src/crypto_quant/challenger_replacement_install_preflight.py",
    "src/crypto_quant/challenger_replacement_install_trust.py",
    "src/crypto_quant/challenger_replacement_v3_activation_install.py",
    "src/crypto_quant/challenger_replacement_v3_activation_install_cli.py",
    "src/crypto_quant/challenger_replacement_v3_activation_preflight.py",
    "src/crypto_quant/challenger_replacement_v3_activation_preflight_cli.py",
    "src/crypto_quant/challenger_replacement_v3_activation_start.py",
    "src/crypto_quant/challenger_replacement_v3_activation_start_cli.py",
    "src/crypto_quant/challenger_replacement_v3_activation_trust.py",
    "src/crypto_quant/challenger_replacement_v3_activation_trust_cli.py",
    "src/crypto_quant/challenger_replacement_v3_installed_runtime.py",
    "src/crypto_quant/challenger_replacement_v3_observer.py",
    "src/crypto_quant/challenger_replacement_v3_runtime.py",
    "src/crypto_quant/challenger_replacement_v3_start.py",
}


def physical_lines(*names):
    return sum(len((ROOT / name).read_text(encoding="utf-8").splitlines())
               for name in names)


def added_lines(*paths):
    result = subprocess.run(
        ["git", "diff", "--numstat", V076_BUILD_INPUT_TREE, "--", *paths],
        cwd=REPOSITORY, check=True, capture_output=True, text=True,
    )
    allowed, seen, total = set(paths), set(), 0
    for line in result.stdout.splitlines():
        added, _deleted, path = line.split("\t")
        if added == "-" or path not in allowed or path in seen:
            raise AssertionError("V077_ARCHITECTURE_DIFF_INVALID")
        seen.add(path)
        total += int(added)
    return total


class BinancePrivateArchitectureBudgetTests(unittest.TestCase):
    def test_frozen_component_budgets_are_respected(self):
        groups = {
            "protocol_transport": (PROTOCOL_TRANSPORT, 600),
            "credential": (CREDENTIAL, 220),
            "preflight": (PREFLIGHT, 380),
            "private_projection": (PRIVATE_PROJECTION, 700),
            "order_runtime": (ORDER_RUNTIME, 2100),
            "controllers": (
                tuple(name for name in CONTROLLERS if (ROOT / name).is_file()),
                2200,
            ),
        }
        mandatory = (
            PROTOCOL_TRANSPORT + CREDENTIAL + PREFLIGHT
            + PRIVATE_PROJECTION + ORDER_RUNTIME
        )
        self.assertTrue(all((ROOT / name).is_file() for name in mandatory))
        self.assertTrue(all((REPOSITORY / name).is_file()
                            for name in OPPORTUNITY_PROJECTION + DELIVERY))
        counted = tuple(
            name for names, _cap in groups.values() for name in names
        )
        self.assertEqual(len(counted), len(set(counted)))
        expected_private = {
            *PROTOCOL_TRANSPORT,
            "challenger_replacement_binance_private_contract.py",
            "challenger_replacement_binance_private_lifecycle.py",
            "challenger_replacement_binance_private_runtime.py",
        }
        discovered_private = {
            path.name for path in ROOT.glob(
                "challenger_replacement_binance_private_*.py"
            )
        }
        self.assertEqual(discovered_private, expected_private)
        expected_modified_code = {
            *RELEASE_METADATA,
            *("src/crypto_quant/" + name for name in counted),
            *EVENT_STORAGE,
            *OPPORTUNITY_PROJECTION,
            *DELIVERY,
        }
        modified = subprocess.run(
            ["git", "diff", "--name-only", V076_BUILD_INPUT_TREE, "--",
             "src/crypto_quant"],
            cwd=REPOSITORY, check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        modified_code = {
            path for path in modified
            if path.endswith(".py") or path.endswith(".js")
        }
        self.assertEqual(modified_code - V078_ACTIVATION_CODE,
                         expected_modified_code)
        for label, (names, cap) in groups.items():
            with self.subTest(component=label):
                lines = physical_lines(*names)
                if label == "private_projection":
                    lines += added_lines(*OPPORTUNITY_PROJECTION, *EVENT_STORAGE)
                self.assertLessEqual(lines, cap)
        delivery_lines = added_lines(*DELIVERY)
        self.assertLessEqual(delivery_lines, 150)
        self.assertLessEqual(
            physical_lines(*counted)
            + added_lines(*OPPORTUNITY_PROJECTION)
            + added_lines(*EVENT_STORAGE)
            + delivery_lines,
            6200,
        )


if __name__ == "__main__":
    unittest.main()
