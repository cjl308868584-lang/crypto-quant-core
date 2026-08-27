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
DELIVERY = (
    "src/crypto_quant/operations_projection_v3.py",
    "src/crypto_quant/operations_alerts.py",
    "src/crypto_quant/dashboard/app.js",
)


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
            "private_projection": (PRIVATE_PROJECTION, 650),
            "order_runtime": (ORDER_RUNTIME, 2100),
            "controllers": (
                tuple(name for name in CONTROLLERS if (ROOT / name).is_file()),
                1250,
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
        for label, (names, cap) in groups.items():
            with self.subTest(component=label):
                lines = physical_lines(*names)
                if label == "private_projection":
                    lines += added_lines(*OPPORTUNITY_PROJECTION)
                self.assertLessEqual(lines, cap)
        delivery_lines = added_lines(*DELIVERY)
        self.assertLessEqual(delivery_lines, 150)
        self.assertLessEqual(
            physical_lines(*counted)
            + added_lines(*OPPORTUNITY_PROJECTION)
            + delivery_lines,
            5250,
        )


if __name__ == "__main__":
    unittest.main()
