import hashlib
import json
import unittest
from copy import deepcopy
from importlib import resources
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.system_paper_plan import build_system_paper_plan
from tests.system_paper_fixtures import (
    DEFAULT_SCHEDULED_FOR,
    valid_public_capture,
    valid_public_transport,
)


EXPECTED_MARKET_BUNDLE_KEYS = {
    "bundle_hash",
    "provider",
    "scheduled_for",
    "captured_at",
    "instrument_metadata_schema_version",
    "instrument_metadata",
    "closed_4h_klines",
    "bbo",
    "source_receipts",
}


class SystemPaperPublicInputTests(unittest.TestCase):
    def bundle(self):
        from crypto_quant.system_paper_public_input import (
            build_system_paper_market_bundle,
        )

        capture, _transport = valid_public_capture()
        return build_system_paper_market_bundle(
            plan=build_system_paper_plan(),
            scheduled_for=DEFAULT_SCHEDULED_FOR,
            capture=capture,
        )

    def test_bundle_retains_replayable_sources_and_real_capture_time(self):
        """Catches replacing full sources with hashes or backdating metadata."""

        try:
            from crypto_quant.system_paper_public_input import (
                build_system_paper_market_bundle,
            )
        except ModuleNotFoundError:
            self.fail("system_paper_public_input is not implemented")

        capture, transport = valid_public_capture()
        bundle = build_system_paper_market_bundle(
            plan=build_system_paper_plan(),
            scheduled_for=DEFAULT_SCHEDULED_FOR,
            capture=capture,
        )

        self.assertEqual(set(bundle), EXPECTED_MARKET_BUNDLE_KEYS)
        self.assertEqual(bundle["scheduled_for"], "2026-08-02T12:00:00.000Z")
        self.assertEqual(bundle["captured_at"], "2026-08-02T12:05:01.000Z")
        self.assertEqual(len(bundle["source_receipts"]), 4)
        self.assertEqual(len(transport.requests), 4)
        self.assertEqual(
            bundle["closed_4h_klines"][-1]["close_time"],
            "2026-08-02T11:59:59.999Z",
        )
        self.assertEqual(
            bundle["instrument_metadata"]["effective_from"],
            "2026-08-02T12:05:00.200Z",
        )

    def test_loader_replays_exact_source_receipts_from_canonical_bytes(self):
        """Catches trusting a bundle self-hash without replaying raw sources."""

        try:
            from crypto_quant.system_paper_public_input import (
                load_system_paper_market_bundle_bytes,
            )
        except ImportError:
            self.fail("system paper market bundle loader is not implemented")

        bundle = self.bundle()
        body = canonical_json(bundle).encode("utf-8")

        self.assertEqual(load_system_paper_market_bundle_bytes(body), bundle)

    def test_loader_rejects_rehashed_source_and_normalized_fact_mutations(self):
        """Catches trusting a rehashed envelope instead of exact source replay."""

        from crypto_quant.system_paper_public_input import (
            SystemPaperPublicInputError,
            load_system_paper_market_bundle_bytes,
        )

        def rehash_receipt(receipt):
            receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")

        def rehash_bundle(bundle):
            bundle["bundle_hash"] = artifact_self_hash(bundle, "bundle_hash")
            return canonical_json(bundle).encode("utf-8")

        original = self.bundle()

        changed_raw = deepcopy(original)
        receipt = changed_raw["source_receipts"][0]
        rows = json.loads(receipt["response_body_utf8"])
        rows[-1][4] = "111"
        body = json.dumps(rows, separators=(",", ":"))
        receipt["response_body_utf8"] = body
        receipt["body_size_bytes"] = len(body.encode("utf-8"))
        receipt["body_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        rehash_receipt(receipt)

        changed_time = deepcopy(original)
        changed_time["source_receipts"][0]["recorded_at"] = (
            "2026-08-02T12:05:02.000Z"
        )
        rehash_receipt(changed_time["source_receipts"][0])

        changed_receipt_hash = deepcopy(original)
        changed_receipt_hash["source_receipts"][0]["receipt_hash"] = "f" * 64

        noncontiguous_kline = deepcopy(original)
        noncontiguous_kline["closed_4h_klines"][5]["open_time"] = (
            "2026-07-30T16:00:00.001Z"
        )

        changed_final_close = deepcopy(original)
        changed_final_close["closed_4h_klines"][-1]["close_time"] = (
            "2026-08-02T11:59:59.998Z"
        )

        detached_metadata = deepcopy(original)
        detached_metadata["instrument_metadata"]["effective_from"] = (
            "2026-08-02T12:05:02.000Z"
        )

        duplicate_family = deepcopy(original)
        duplicate_family["source_receipts"][1]["family"] = (
            duplicate_family["source_receipts"][0]["family"]
        )
        rehash_receipt(duplicate_family["source_receipts"][1])

        for name, mutated in (
            ("raw_response", changed_raw),
            ("receipt_time", changed_time),
            ("receipt_hash", changed_receipt_hash),
            ("noncontiguous_kline", noncontiguous_kline),
            ("final_close", changed_final_close),
            ("metadata", detached_metadata),
            ("duplicate_family", duplicate_family),
        ):
            with self.subTest(name=name), self.assertRaises(
                SystemPaperPublicInputError
            ):
                load_system_paper_market_bundle_bytes(rehash_bundle(mutated))

    def test_loader_rejects_float_unknown_and_legacy_shapes(self):
        """Catches accepting noncanonical numbers or the v0.57 hash-only shape."""

        from crypto_quant.system_paper_public_input import (
            SystemPaperPublicInputError,
            load_system_paper_market_bundle_bytes,
        )

        float_bundle = deepcopy(self.bundle())
        float_bundle["bbo"]["bid_price"] = 109.99
        float_body = json.dumps(
            float_bundle,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        unknown = deepcopy(self.bundle())
        unknown["credential"] = "must-never-be-accepted"
        unknown["bundle_hash"] = artifact_self_hash(unknown, "bundle_hash")

        legacy = deepcopy(self.bundle())
        legacy["observed_at"] = legacy.pop("scheduled_for")
        legacy["source_receipt_hashes"] = [
            item["receipt_hash"] for item in legacy.pop("source_receipts")
        ]
        legacy.pop("captured_at")
        legacy["bundle_hash"] = artifact_self_hash(legacy, "bundle_hash")

        for name, body in (
            ("float", float_body),
            ("unknown", canonical_json(unknown).encode("utf-8")),
            ("legacy", canonical_json(legacy).encode("utf-8")),
        ):
            with self.subTest(name=name), self.assertRaises(
                SystemPaperPublicInputError
            ):
                load_system_paper_market_bundle_bytes(body)

    def test_schema_is_packaged_byte_identically(self):
        root = Path(__file__).resolve().parents[1]
        governance = (
            root / "config" / "system-paper-market-bundle-v1.schema.json"
        ).read_bytes()
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "system-paper-market-bundle-v1.schema.json"
        ).read_bytes()

        self.assertEqual(governance, packaged)

    def test_builder_rejects_capture_outside_the_slot_window(self):
        """Catches binding an earlier public capture to a later logical slot."""

        from crypto_quant.system_paper_public_input import (
            SystemPaperPublicInputError,
            build_system_paper_market_bundle,
        )

        capture, _transport = valid_public_capture()
        with self.assertRaisesRegex(
            SystemPaperPublicInputError,
            "SYSTEM_PAPER_PUBLIC_CAPTURE_WINDOW_INVALID",
        ):
            build_system_paper_market_bundle(
                plan=build_system_paper_plan(),
                scheduled_for="2026-08-02T16:00:00.000Z",
                capture=capture,
            )

    def test_builder_rejects_warmup_not_closed_at_the_slot_boundary(self):
        """Catches accepting a stale but otherwise well-formed Kline window."""

        from crypto_quant.system_paper_public_input import (
            SystemPaperPublicInputError,
            build_system_paper_market_bundle,
        )

        capture, _transport = valid_public_capture(
            market_boundary_or_none="2026-08-02T08:00:00.000Z"
        )
        with self.assertRaisesRegex(
            SystemPaperPublicInputError,
            "SYSTEM_PAPER_PUBLIC_KLINE_BOUNDARY_INVALID",
        ):
            build_system_paper_market_bundle(
                plan=build_system_paper_plan(),
                scheduled_for=DEFAULT_SCHEDULED_FOR,
                capture=capture,
            )

    def test_provider_issues_the_scheduler_capture_with_four_public_gets(self):
        """Catches bypassing the scheduler's fixed capture/count contract."""

        try:
            from crypto_quant.system_paper_public_input import (
                capture_system_paper_input,
            )
        except ImportError:
            self.fail("system paper public input provider is not implemented")
        from crypto_quant.system_paper_scheduler import (
            SystemPaperInputRequest,
            SystemPaperSchedulePolicy,
        )

        plan = build_system_paper_plan()
        policy = SystemPaperSchedulePolicy.create(plan)
        slot = policy.slot_from_scheduled(DEFAULT_SCHEDULED_FOR)
        request = SystemPaperInputRequest.for_slot(policy, slot)
        transport, clock = valid_public_transport()

        capture = capture_system_paper_input(
            request,
            transport=transport,
            clock=clock,
        )

        self.assertEqual(capture.network_request_count, 4)
        self.assertEqual(capture.request_families, request.request_families)
        self.assertEqual(capture.captured_at, "2026-08-02T12:05:01.000Z")
        self.assertEqual(len(transport.requests), 4)
        self.assertEqual(
            capture.public_market_bundle["scheduled_for"],
            request.scheduled_for,
        )


if __name__ == "__main__":
    unittest.main()
