import json
import unittest
from decimal import Decimal
from pathlib import Path

from crypto_quant.risk import DrawdownPolicy, DrawdownState

ROOT = Path(__file__).resolve().parents[1]


class DrawdownPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        policy = json.loads((ROOT / "config/release-gates-v1.1.json").read_text())
        cls.drawdown = DrawdownPolicy.from_release_policy(policy)

    def test_frozen_boundaries(self) -> None:
        cases = {
            "0.0999": DrawdownState.NORMAL,
            "0.10": DrawdownState.WARNING,
            "0.1199": DrawdownState.WARNING,
            "0.12": DrawdownState.REDUCE,
            "0.1499": DrawdownState.REDUCE,
            "0.15": DrawdownState.HALT,
            "0.1999": DrawdownState.HALT,
            "0.20": DrawdownState.HARD_BOUNDARY,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(self.drawdown.classify(value), expected)

    def test_warning_and_reduce_never_increase_or_reverse_risk(self) -> None:
        warning = self.drawdown.cap_signed_target(
            state=DrawdownState.WARNING,
            current_signed_exposure="100",
            requested_signed_exposure="150",
            original_approved_abs_exposure="200",
        )
        reduced = self.drawdown.cap_signed_target(
            state=DrawdownState.REDUCE,
            current_signed_exposure="-180",
            requested_signed_exposure="-170",
            original_approved_abs_exposure="200",
        )
        reversed_target = self.drawdown.cap_signed_target(
            state=DrawdownState.WARNING,
            current_signed_exposure="100",
            requested_signed_exposure="-50",
            original_approved_abs_exposure="200",
        )
        self.assertEqual(warning, Decimal("100"))
        self.assertEqual(reduced, Decimal("-100"))
        self.assertEqual(reversed_target, Decimal("0"))

    def test_halt_and_hard_boundary_flatten(self) -> None:
        for state in (DrawdownState.HALT, DrawdownState.HARD_BOUNDARY):
            with self.subTest(state=state):
                self.assertEqual(
                    self.drawdown.cap_signed_target(
                        state=state,
                        current_signed_exposure="100",
                        requested_signed_exposure="100",
                        original_approved_abs_exposure="200",
                    ),
                    Decimal("0"),
                )


if __name__ == "__main__":
    unittest.main()
