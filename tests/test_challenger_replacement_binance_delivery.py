import json
from pathlib import Path
import unittest

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.operations_alerts import derive_operations_alerts
from crypto_quant.operations_projection_v3 import (
    OperationsProjectionV3Error,
    build_operations_projection_v3,
    load_operations_projection_v3_bytes,
)
from tests.test_challenger_replacement_public_market_capture import V076_BUILD
from tests import test_challenger_replacement_canary_controller as canary_fixtures
from tests.test_operations_projection_v3 import observation


ROOT = Path(__file__).resolve().parents[1]


def canary_body(*, equity="100", hard_stop=None):
    states = (
        "CEREMONY_READY_FLAT", "SPOT_BUY_SUBMITTED",
        "SPOT_LONG_RECONCILED", "SPOT_SELL_SUBMITTED",
        "FLAT_RECONCILED_AFTER_SPOT", "PERP_SHORT_SUBMITTED",
        "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED",
        "PERP_CLOSE_REDUCE_ONLY_SUBMITTED", "FLAT_RECONCILED_AFTER_PERP",
        "CEREMONY_QUALIFIED",
    )
    amounts = {states[2], states[4], states[6], states[8]}
    flat = {states[0], states[4], states[8], states[9]}
    exposed = {states[2], states[6]}
    events = tuple({
        "event_type": "CEREMONY_STATE_RECONCILED",
        "block_id": "ceremony-block-1",
        "label": "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE",
        "state": state, "occurred_at": "2026-09-01T%02d:00:00.000Z" % index,
        "reconciliation_id": "binance_reconciliation_" + format(index, "064x"),
        "minimum_amount_satisfied_or_null": True if state in amounts else None,
        "flat_or_null": True if state in flat else False if state in exposed else None,
    } for index, state in enumerate(states)) + (
        {
            "event_type": "CANARY_STAGE_BLOCK_STARTED", "stage": "E0",
            "block_id": "e0-block-1",
            "activation_id": "binance_private_activation_" + "1" * 64,
            "previous_block_id_or_null": None,
            "incident_unlock_id_or_null": None,
            "occurred_at": "2026-09-02T00:00:00.000Z",
            "starting_equity": "100",
        }, {
            "event_type": "CANARY_EQUITY_RECONCILED",
            "block_id": "e0-block-1",
            "occurred_at": "2026-09-02T04:00:00.000Z",
            "equity": ("97.999" if hard_stop ==
                       "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT" else equity),
            "flat": hard_stop is None,
            "new_risk_attempted": hard_stop ==
                "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
            "hard_stop_or_null": hard_stop,
        },
    )
    fixture = canary_fixtures.ChallengerReplacementCanaryControllerTests()
    fixture.setUp()
    try:
        return fixture.project(
            events, now="2026-09-02T08:00:00.000Z",
        )[0]
    finally:
        fixture.doCleanups()


def operations_body(*, equity="100", hard_stop=None):
    value = build_operations_projection_v3(
        observation(missed=0), build_identity=V076_BUILD,
        canary_projection_bytes=canary_body(
            equity=equity, hard_stop=hard_stop,
        ),
    )
    return canonical_json(value).encode("utf-8")


class BinancePrivateDeliveryTests(unittest.TestCase):
    def test_strict_canary_projection_is_visible_without_authority(self):
        canary = canary_body(equity="97.999")
        observed = observation(missed=0)
        value = build_operations_projection_v3(
            observed, build_identity=V076_BUILD,
            canary_projection_bytes=canary,
        )
        body = canonical_json(value).encode("utf-8")
        self.assertEqual(load_operations_projection_v3_bytes(
            body, observation=observed, build_identity=V076_BUILD,
            canary_projection_bytes=canary,
        ), value)
        private = value["binance_private"]
        self.assertEqual(private["ceremony_status"], "CEREMONY_QUALIFIED")
        self.assertEqual(private["stage"], "E0")
        self.assertEqual(private["stage_status"], "STAGE_DAILY_STOPPED")
        self.assertEqual(private["daily_loss_usdt"], "2.001")
        self.assertEqual(private["high_water_loss_usdt"], "2.001")
        self.assertTrue(private["new_risk_blocked"])
        self.assertFalse(any(value["authority"].values()))

    def test_standalone_projection_rejects_invented_private_state(self):
        value = json.loads(operations_body())
        value["binance_private"]["hard_stop_or_null"] = "INVENTED"
        value["projection_hash"] = business_hash({
            "purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V3",
            **{key: item for key, item in value.items()
               if key != "projection_hash"},
        })
        with self.assertRaisesRegex(
            OperationsProjectionV3Error, "OPERATIONS_PROJECTION_V3_INVALID",
        ):
            load_operations_projection_v3_bytes(
                canonical_json(value).encode("utf-8")
            )

    def test_four_hard_stops_and_loss_boundaries_emit_fixed_alerts(self):
        cases = (
            ("UNRESOLVED_ECONOMIC_ORDER_UNKNOWN", "UNKNOWN-ORDER"),
            ("VENUE_LOCAL_POSITION_MISMATCH", "POSITION-MISMATCH"),
            ("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP", "STOP-MISSING"),
            ("RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT", "POST-LIMIT-RISK"),
        )
        for reason, suffix in cases:
            with self.subTest(reason=reason):
                alerts = derive_operations_alerts(operations_body(hard_stop=reason))
                self.assertIn(
                    "OPS-BINANCE-PRIVATE-" + suffix,
                    [item["alert_id"] for item in alerts["alerts"]],
                )
                self.assertFalse(alerts["new_risk_allowed"])

        daily = derive_operations_alerts(operations_body(equity="97.999"))
        self.assertIn("OPS-BINANCE-PRIVATE-DAILY-STOP",
                      [item["alert_id"] for item in daily["alerts"]])
        drawdown = derive_operations_alerts(operations_body(equity="95"))
        self.assertIn("OPS-BINANCE-PRIVATE-DRAWDOWN-FAIL",
                      [item["alert_id"] for item in drawdown["alerts"]])

    def test_disabled_examples_have_no_secret_account_or_live_path(self):
        config = ROOT / "config/challenger-replacement-binance-v1.example.json"
        plist = ROOT / "config/local.crypto-quant.challenger-replacement-binance-v1.plist.example"
        document = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual(document["production_activation"], False)
        self.assertEqual(document["credential_file"], "")
        self.assertEqual(document["account_approval_file"], "")
        self.assertEqual(document["activation_file"], "")
        combined = config.read_text() + plist.read_text()
        for forbidden in ("api_key", "secret_key", "/Users/", "account_id"):
            self.assertNotIn(forbidden, combined.lower())
        self.assertIn("<true/>", plist.read_text())
        self.assertIn("/usr/bin/false", plist.read_text())

    def test_dashboard_and_runbooks_remain_read_only_and_fail_closed(self):
        dashboard = (ROOT / "src/crypto_quant/dashboard/app.js").read_text()
        self.assertIn("Binance 私有边界", dashboard)
        for forbidden in ("fetch(\"http", "<button", "api_key", "secret_key"):
            self.assertNotIn(forbidden, dashboard.lower())
        for name in (
            "binance-private-preflight-v0.77.md",
            "binance-order-unknown-v0.77.md",
            "binance-safe-flatten-v0.77.md",
            "binance-secret-incident-v0.77.md",
        ):
            text = " ".join(
                (ROOT / "docs/runbooks" / name).read_text().lower().split()
            )
            self.assertIn("fail closed", text)
            self.assertIn("do not delete evidence", text)
            self.assertNotIn("resend an unknown order", text)


if __name__ == "__main__":
    unittest.main()
