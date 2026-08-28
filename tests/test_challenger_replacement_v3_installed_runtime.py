import unittest
from contextlib import contextmanager
from unittest.mock import patch


class ChallengerReplacementV3InstalledRuntimeTests(unittest.TestCase):
    def test_missing_install_receipt_fails_before_runtime(self):
        from crypto_quant import challenger_replacement_v3_installed_runtime as adapter

        with patch.object(adapter, "_open_fixed_sources", side_effect=adapter.ReplacementV3InstalledRuntimeError(
            "CHALLENGER_REPLACEMENT_V3_INSTALL_RECEIPT_REQUIRED"
        )), patch.object(adapter, "run_challenger_replacement_v3_opportunity") as run:
            with self.assertRaisesRegex(ValueError, "INSTALL_RECEIPT_REQUIRED"):
                adapter.run_installed_v3_opportunity()
        run.assert_not_called()

    def test_adapter_delegates_exact_sources_and_closes_context(self):
        from crypto_quant import challenger_replacement_v3_installed_runtime as adapter

        sources = {key: object() for key in adapter._SOURCE_KEYS}
        closed = []

        @contextmanager
        def opened():
            try:
                yield sources
            finally:
                closed.append(True)

        expected = {"status": "OBSERVED"}
        with patch.object(adapter, "_open_fixed_sources", opened), patch.object(
            adapter, "run_challenger_replacement_v3_opportunity", return_value=expected
        ) as run:
            self.assertEqual(adapter.run_installed_v3_opportunity(), expected)
        run.assert_called_once_with(**sources)
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
