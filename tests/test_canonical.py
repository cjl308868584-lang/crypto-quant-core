import unittest
from datetime import datetime, timezone
from decimal import Decimal

from crypto_quant.canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
)
from crypto_quant.decimal_math import (
    RiskRatio,
    round_down_to_step,
    round_price_down,
    round_price_up,
    round_signed_exposure_toward_zero,
)
from crypto_quant.errors import CanonicalizationError, ContractError


class CanonicalTests(unittest.TestCase):
    def test_canonical_json_and_hash_are_stable_100_times(self) -> None:
        payload = {
            "quantity": Decimal("1.2300"),
            "decision_time": datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            "nested": {"z": None, "a": True},
        }
        expected_json = (
            '{"decision_time":"2026-01-02T03:04:05.000Z",'
            '"nested":{"a":true,"z":null},"quantity":"1.23"}'
        )
        self.assertEqual(canonical_json(payload), expected_json)
        hashes = {business_hash(payload) for _ in range(100)}
        identifiers = {stable_id("target", payload) for _ in range(100)}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(len(identifiers), 1)

    def test_unsafe_numbers_fail_closed(self) -> None:
        for value in (0.1, Decimal("NaN"), Decimal("Infinity"), Decimal("-0")):
            with self.subTest(value=value):
                with self.assertRaises(CanonicalizationError):
                    canonical_decimal(value)
        with self.assertRaises(CanonicalizationError):
            canonical_json({"unsafe": 0.1})
        with self.assertRaises(CanonicalizationError):
            canonical_json({"too_large": 2**53})

    def test_tick_step_and_risk_ratio_use_decimal_units(self) -> None:
        self.assertEqual(round_down_to_step("1.239", "0.01"), Decimal("1.23"))
        self.assertEqual(
            round_signed_exposure_toward_zero("-1.239", "0.01"),
            Decimal("-1.23"),
        )
        self.assertEqual(round_price_down("1823.129", "0.01"), Decimal("1823.12"))
        self.assertEqual(round_price_up("1823.121", "0.01"), Decimal("1823.13"))
        self.assertEqual(
            RiskRatio("0.25").multiply(RiskRatio("0.25")).value,
            Decimal("0.0625"),
        )
        with self.assertRaises(ContractError):
            RiskRatio(25)


if __name__ == "__main__":
    unittest.main()
