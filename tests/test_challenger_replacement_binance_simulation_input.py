import copy
from dataclasses import replace
from decimal import Decimal
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.challenger_replacement_binance_simulation_input import (
    ChallengerReplacementSimulationInputError,
    load_challenger_replacement_binance_simulation_input_bytes,
)
from crypto_quant.evidence import artifact_self_hash
from tests.challenger_replacement_v3_fixtures import (
    DEFAULT_OBSERVED_AT,
    DEFAULT_SCHEDULED_FOR,
    fixture_opportunity_id,
    fixture_v071_build_identity,
    fixture_v071_contract,
    fixture_v071_input_bytes,
    fixture_v071_input_document,
    fixture_v071_spot_metadata,
    fixture_v072_build_identity,
    fixture_v072_input_bytes,
    fixture_v3_plan,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / (
    "config/challenger-replacement-binance-simulation-input-v1.schema.json"
)
PACKAGE_SCHEMA = ROOT / (
    "src/crypto_quant/schemas/"
    "challenger-replacement-binance-simulation-input-v1.schema.json"
)
INVALID = "CHALLENGER_REPLACEMENT_SIMULATION_INPUT_INVALID"
BYTES_INVALID = "CHALLENGER_REPLACEMENT_SIMULATION_INPUT_BYTES_INVALID"


class ChallengerReplacementBinanceSimulationInputTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_v3_plan()
        self.contract = fixture_v071_contract()
        self.build = fixture_v071_build_identity()
        self.opportunity_id = fixture_opportunity_id()

    def load(self, data=None, **bindings):
        return load_challenger_replacement_binance_simulation_input_bytes(
            fixture_v071_input_bytes() if data is None else data,
            plan=bindings.get("plan", self.plan),
            contract=bindings.get("contract", self.contract),
            build_identity=bindings.get("build_identity", self.build),
            opportunity_id=bindings.get("opportunity_id", self.opportunity_id),
        )

    @staticmethod
    def encoded(document):
        return canonical_json(document).encode("utf-8")

    @staticmethod
    def rehash(document, *, reidentify=False):
        value = copy.deepcopy(document)
        if reidentify:
            value["input_id"] = stable_id(
                "challenger_replacement_binance_simulation_input",
                {
                    "plan": value["plan"],
                    "simulation_contract": value["simulation_contract"],
                    "build_identity": value["build_identity"],
                    "opportunity": value["opportunity"],
                },
            )
        value["input_hash"] = artifact_self_hash(value, "input_hash")
        return value

    def assert_invalid(self, document, reason=INVALID, *, reidentify=False):
        value = self.rehash(document, reidentify=reidentify)
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationInputError,
            reason,
        ):
            self.load(self.encoded(value))

    def test_schema_mirror_and_exact_canonical_fixture_round_trip(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        expected = json.loads(fixture_v071_input_bytes())
        self.assertEqual(self.load(), expected)
        self.assertEqual(
            expected["input_hash"],
            artifact_self_hash(expected, "input_hash"),
        )
        self.assertEqual(
            expected["input_id"],
            "challenger_replacement_binance_simulation_input_"
            "be938e9efdc6b9393627d458c8d0a194aa5a77d953c15dccf1e3690cf390ffa6",
        )

    def test_fixture_has_exact_top_level_and_zero_authority(self):
        document = self.load()
        self.assertEqual(
            set(document),
            {
                "$schema",
                "schema_version",
                "input_id",
                "input_hash",
                "evidence_qualification",
                "plan",
                "simulation_contract",
                "build_identity",
                "opportunity",
                "bars",
                "instruments",
                "quotes",
                "funding",
                "authority",
            },
        )
        self.assertEqual(
            document["authority"],
            {
                "network_requests": 0,
                "account_requests": 0,
                "broker_requests": 0,
                "orders_submitted_to_venue": 0,
                "credentials_used": False,
                "production_state_writes": 0,
            },
        )
        self.assertEqual(
            document["evidence_qualification"],
            "COMMITTED_FIXTURE_NOT_LIVE_MARKET",
        )

    def test_fixture_binds_exact_plan_contract_build_and_opportunity(self):
        document = self.load()
        self.assertEqual(
            document["plan"],
            {"plan_id": self.plan["plan_id"], "plan_hash": self.plan["plan_hash"]},
        )
        self.assertEqual(
            document["simulation_contract"],
            {
                "contract_id": self.contract["contract_id"],
                "contract_hash": self.contract["contract_hash"],
            },
        )
        self.assertEqual(document["build_identity"], self.build)
        self.assertEqual(document["opportunity"]["opportunity_id"], self.opportunity_id)

        wrong_build = dict(self.build)
        wrong_build["manifest_hash"] = "a" * 64
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationInputError,
            INVALID,
        ):
            self.load(build_identity=wrong_build)
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationInputError,
            INVALID,
        ):
            self.load(opportunity_id="ETHUSDT@2026-01-02T04:00:00.000Z")

    def test_input_v1_dispatch_accepts_only_same_version_fixture_identity(self):
        v072_build = fixture_v072_build_identity()
        loaded = self.load(
            fixture_v072_input_bytes(),
            build_identity=v072_build,
        )
        self.assertEqual(loaded["build_identity"], v072_build)

        with self.assertRaisesRegex(
            ChallengerReplacementSimulationInputError,
            INVALID,
        ):
            self.load(
                fixture_v072_input_bytes(),
                build_identity=fixture_v071_build_identity(),
            )
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationInputError,
            INVALID,
        ):
            self.load(
                fixture_v071_input_bytes(),
                build_identity=v072_build,
            )

    def test_fixture_has_21_closed_contiguous_four_hour_bars(self):
        bars = self.load()["bars"]
        self.assertEqual(len(bars), 21)
        self.assertEqual(bars[-1]["close_boundary"], DEFAULT_SCHEDULED_FOR)
        for index, bar in enumerate(bars):
            opened = datetime.fromisoformat(bar["open_time"].replace("Z", "+00:00"))
            closed = datetime.fromisoformat(
                bar["close_boundary"].replace("Z", "+00:00")
            )
            self.assertEqual(closed - opened, timedelta(hours=4))
            if index:
                self.assertEqual(bars[index - 1]["close_boundary"], bar["open_time"])
            low, opened_price, close, high = map(
                Decimal, (bar["low"], bar["open"], bar["close"], bar["high"])
            )
            self.assertGreater(low, 0)
            self.assertLessEqual(low, opened_price)
            self.assertLessEqual(low, close)
            self.assertGreaterEqual(high, opened_price)
            self.assertGreaterEqual(high, close)

    def test_opportunity_window_is_exact_and_observation_is_inside(self):
        opportunity = self.load()["opportunity"]
        scheduled = datetime.fromisoformat(
            DEFAULT_SCHEDULED_FOR.replace("Z", "+00:00")
        )
        self.assertEqual(
            opportunity,
            {
                "opportunity_id": self.opportunity_id,
                "scheduled_for": DEFAULT_SCHEDULED_FOR,
                "capture_open": "2026-08-24T00:02:00.000Z",
                "capture_close": "2026-08-24T00:10:00.000Z",
                "observed_at": DEFAULT_OBSERVED_AT,
            },
        )
        observed = datetime.fromisoformat(
            opportunity["observed_at"].replace("Z", "+00:00")
        )
        self.assertGreaterEqual(observed, scheduled + timedelta(minutes=2))
        self.assertLessEqual(observed, scheduled + timedelta(minutes=10))

    def test_instrument_metadata_and_quotes_are_exactly_usable(self):
        document = self.load()
        instruments = document["instruments"]
        self.assertEqual(
            instruments["spot"]["metadata"]["instrument_id"],
            "BINANCE:SPOT:ETHUSDT",
        )
        self.assertEqual(
            instruments["perpetual"]["metadata"]["instrument_id"],
            "BINANCE:USDT_PERP:ETHUSDT",
        )
        for product in ("spot", "perpetual"):
            metadata = instruments[product]["metadata"]
            self.assertEqual(metadata["contract_multiplier"], "1")
            self.assertEqual(metadata["taker_fee"], "0.0015")
            self.assertRegex(instruments[product]["metadata_hash"], r"^[0-9a-f]{64}$")
        for quote in document["quotes"].values():
            self.assertLessEqual(Decimal(quote["bid"]), Decimal(quote["last"]))
            self.assertLessEqual(Decimal(quote["last"]), Decimal(quote["ask"]))
        self.assertGreater(
            Decimal(document["quotes"]["perpetual"]["mark"]),
            Decimal("0"),
        )

    def test_input_rejects_metadata_fee_conflict(self):
        metadata = fixture_v071_spot_metadata(taker_fee="0.001")
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationInputError,
            "SIMULATION_CONTRACT_METADATA_CONFLICT",
        ):
            self.load(fixture_v071_input_bytes(spot_metadata=metadata))

    def test_positive_non_unit_contract_multiplier_is_preserved(self):
        metadata = fixture_v071_spot_metadata(multiplier="2")
        loaded = self.load(fixture_v071_input_bytes(spot_metadata=metadata))
        self.assertEqual(
            loaded["instruments"]["spot"]["metadata"]["contract_multiplier"],
            "2",
        )

    def test_ineffective_metadata_is_a_semantic_input_failure(self):
        metadata = replace(
            fixture_v071_spot_metadata(),
            effective_from=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationInputError,
            INVALID,
        ):
            self.load(fixture_v071_input_bytes(spot_metadata=metadata))

    def test_funding_fields_are_paired_and_boundary_is_scheduled(self):
        self.assertEqual(
            self.load()["funding"],
            {"boundary_at_or_null": None, "rate_or_null": None},
        )
        funded = self.load(
            fixture_v071_input_bytes(
                funding_boundary_at_or_null=DEFAULT_SCHEDULED_FOR,
                funding_rate_or_null="0.0001",
            )
        )
        self.assertEqual(funded["funding"]["rate_or_null"], "0.0001")
        negative = self.load(
            fixture_v071_input_bytes(
                funding_boundary_at_or_null=DEFAULT_SCHEDULED_FOR,
                funding_rate_or_null="-0.0001",
            )
        )
        self.assertEqual(negative["funding"]["rate_or_null"], "-0.0001")

        for boundary, rate in (
            (DEFAULT_SCHEDULED_FOR, None),
            (None, "0.0001"),
            ("2026-01-01T04:00:00.000Z", "0.0001"),
        ):
            self.assert_invalid(
                fixture_v071_input_document(
                    funding_boundary_at_or_null=boundary,
                    funding_rate_or_null=rate,
                )
            )

    def test_semantic_tampering_fails_closed(self):
        base = fixture_v071_input_document()
        mutations = []

        def mutated(path, value):
            item = copy.deepcopy(base)
            target = item
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            mutations.append(item)

        mutated(("bars",), base["bars"][:-1])
        mutated(("bars", 1, "open_time"), base["bars"][0]["open_time"])
        mutated(("bars", -1, "close_boundary"), "2026-01-01T04:00:00.000Z")
        mutated(("bars", 0, "low"), "9999")
        mutated(("bars", 0, "close"), "0")
        mutated(("bars", 0, "open"), "1900.0")
        mutated(("quotes", "spot", "bid"), "2002")
        mutated(("quotes", "perpetual", "mark"), "0")
        mutated(("opportunity", "capture_open"), DEFAULT_SCHEDULED_FOR)
        mutated(("opportunity", "observed_at"), "2026-01-01T00:11:00.000Z")
        mutated(("instruments", "spot", "metadata_hash"), "a" * 64)
        mutated(("instruments", "spot", "metadata", "contract_multiplier"), "2")
        mutated(("authority", "network_requests"), 1)
        mutated(("evidence_qualification",), "LIVE")
        extra = copy.deepcopy(base)
        extra["pnl"] = "999"
        mutations.append(extra)
        for index, document in enumerate(mutations):
            with self.subTest(index=index):
                self.assert_invalid(document)

    def test_noncanonical_duplicate_float_and_unbounded_bytes_fail_closed(self):
        valid = fixture_v071_input_bytes()
        duplicate = b'{"x":1,"x":2}'
        float_value = valid.replace(b'"bid":"1999"', b'"bid":1999.0')
        for malformed in (
            b"",
            valid + b"\n",
            b" " + valid,
            duplicate,
            float_value,
            b"{" + (b" " * (2 * 1024 * 1024)) + b"}",
            b"[]",
            b"not-json",
        ):
            with self.subTest(size=len(malformed)):
                with self.assertRaisesRegex(
                    ChallengerReplacementSimulationInputError,
                    BYTES_INVALID,
                ):
                    self.load(malformed)

    def test_build_identity_must_be_strict_and_complete(self):
        for mutation in (
            {**self.build, "extra": "forbidden"},
            {**self.build, "peeled_commit": "A" * 40},
            {**self.build, "manifest_hash": "0" * 63},
            {**self.build, "release_tag": "evil"},
            {**self.build, "package_version": "999"},
            {**self.build, "manifest_version": "x"},
            {key: value for key, value in self.build.items() if key != "release_tag"},
        ):
            with self.subTest(mutation=mutation):
                document = fixture_v071_input_document()
                document["build_identity"] = copy.deepcopy(mutation)
                document = self.rehash(document, reidentify=True)
                with self.assertRaisesRegex(
                    ChallengerReplacementSimulationInputError,
                    INVALID,
                ):
                    self.load(
                        self.encoded(document),
                        build_identity=mutation,
                    )

    def test_off_grid_opportunity_fails_closed(self):
        scheduled = "2026-08-24T01:00:00.000Z"
        document = fixture_v071_input_document(
            scheduled_for=scheduled,
            observed_at="2026-08-24T01:05:00.000Z",
        )
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationInputError,
            INVALID,
        ):
            self.load(
                self.encoded(document),
                opportunity_id=fixture_opportunity_id(scheduled),
            )

    def test_production_input_module_has_no_io_or_nondeterministic_imports(self):
        module = ROOT / (
            "src/crypto_quant/"
            "challenger_replacement_binance_simulation_input.py"
        )
        source = module.read_text(encoding="utf-8")
        for forbidden in (
            "import requests",
            "import urllib",
            "import httpx",
            "import aiohttp",
            "import socket",
            "import keyring",
            "import subprocess",
            "import sqlite3",
            "import random",
            "Path(",
            "datetime.now",
            "time.time",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
