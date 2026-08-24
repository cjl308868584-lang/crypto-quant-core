import decimal
import unittest
from datetime import datetime, timedelta, timezone

from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityError,
    derive_due_opportunities,
    opportunity_coverage,
    opportunity_health,
    opportunity_id_for,
)


class OpportunityScheduleTests(unittest.TestCase):
    def test_opportunity_id_accepts_only_canonical_four_hour_grid(self):
        for hour in ("00", "04", "08", "12", "16", "20"):
            scheduled = "2026-08-24T%s:00:00.000Z" % hour
            self.assertEqual(
                opportunity_id_for(scheduled), "ETHUSDT@" + scheduled
            )
        for invalid in (
            "2026-08-24T01:00:00.000Z",
            "2026-08-24T04:00:00Z",
            "2026-08-24T04:00:00.000+00:00",
            "not-time",
            "",
            None,
            True,
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ChallengerReplacementOpportunityError):
                    opportunity_id_for(invalid)

    def test_due_opportunities_have_deterministic_windows_and_statuses(self):
        due = derive_due_opportunities(
            start_scheduled_for="2026-08-24T00:00:00.000Z",
            detected_at="2026-08-24T12:11:00.000Z",
            terminal_scheduled_for=("2026-08-24T00:00:00.000Z",),
        )
        self.assertEqual(
            tuple(item["scheduled_for"] for item in due),
            (
                "2026-08-24T04:00:00.000Z",
                "2026-08-24T08:00:00.000Z",
                "2026-08-24T12:00:00.000Z",
            ),
        )
        self.assertEqual({item["status"] for item in due}, {"EXPIRED"})
        self.assertEqual(
            due[-1],
            {
                "opportunity_id": "ETHUSDT@2026-08-24T12:00:00.000Z",
                "scheduled_for": "2026-08-24T12:00:00.000Z",
                "capture_open": "2026-08-24T12:02:00.000Z",
                "capture_close": "2026-08-24T12:10:00.000Z",
                "status": "EXPIRED",
            },
        )

    def test_capture_window_is_closed_and_preopen_is_not_eligible(self):
        cases = (
            ("2026-08-24T00:01:59.999Z", "NOT_OPEN"),
            ("2026-08-24T00:02:00.000Z", "ELIGIBLE_WINDOW"),
            ("2026-08-24T00:10:00.000Z", "ELIGIBLE_WINDOW"),
            ("2026-08-24T00:10:00.001Z", "EXPIRED"),
        )
        for detected_at, status in cases:
            with self.subTest(detected_at=detected_at):
                due = derive_due_opportunities(
                    start_scheduled_for="2026-08-24T00:00:00.000Z",
                    detected_at=detected_at,
                    terminal_scheduled_for=(),
                )
                self.assertEqual(due[0]["status"], status)

    def test_schedule_handles_year_rollover(self):
        due = derive_due_opportunities(
            start_scheduled_for="2026-12-31T20:00:00.000Z",
            detected_at="2027-01-01T04:11:00.000Z",
            terminal_scheduled_for=("2026-12-31T20:00:00.000Z",),
        )
        self.assertEqual(
            tuple(item["scheduled_for"] for item in due),
            (
                "2027-01-01T00:00:00.000Z",
                "2027-01-01T04:00:00.000Z",
            ),
        )

    def test_schedule_rejects_invalid_boundaries_and_terminal_history(self):
        cases = (
            {
                "start_scheduled_for": "2026-08-24T01:00:00.000Z",
                "detected_at": "2026-08-24T04:00:00.000Z",
                "terminal_scheduled_for": (),
            },
            {
                "start_scheduled_for": "2026-08-24T04:00:00.000Z",
                "detected_at": "2026-08-24T00:00:00.000Z",
                "terminal_scheduled_for": (),
            },
            {
                "start_scheduled_for": "2026-08-24T00:00:00.000Z",
                "detected_at": "2026-08-24T08:00:00.000Z",
                "terminal_scheduled_for": (
                    "2026-08-24T04:00:00.000Z",
                    "2026-08-24T00:00:00.000Z",
                ),
            },
            {
                "start_scheduled_for": "2026-08-24T00:00:00.000Z",
                "detected_at": "2026-08-24T08:00:00.000Z",
                "terminal_scheduled_for": (
                    "2026-08-24T00:00:00.000Z",
                    "2026-08-24T00:00:00.000Z",
                ),
            },
            {
                "start_scheduled_for": "2026-08-24T00:00:00.000Z",
                "detected_at": "2026-08-24T08:00:00.000Z",
                "terminal_scheduled_for": (
                    "2026-08-24T00:00:00.000Z",
                    "2026-08-24T08:00:00.000Z",
                ),
            },
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ChallengerReplacementOpportunityError):
                    derive_due_opportunities(**arguments)


class OpportunityHealthTests(unittest.TestCase):
    def test_no_start_boundary_is_not_started(self):
        health = opportunity_health(
            projection={
                "terminal_scheduled_for": (),
                "observed_opportunity_count": 0,
            },
            start_scheduled_for=None,
            detected_at="2026-08-24T00:00:00.000Z",
        )
        self.assertEqual(
            health,
            {
                "due_opportunity_count": 0,
                "coverage_numerator": 0,
                "coverage_denominator": 0,
                "meets_minimum_observed_coverage": None,
                "eligibility_status": "NOT_STARTED_NO_START_BOUNDARY",
            },
        )

    def test_health_uses_exact_integer_threshold(self):
        cases = (
            (1, 1, True, "BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED"),
            (19, 20, True, "BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED"),
            (18, 20, False, "PRE_TAIL_ELIGIBILITY_ONLY"),
        )
        original = decimal.getcontext().copy()
        try:
            for precision in (2, 7, 28):
                decimal.getcontext().prec = precision
                for observed, due, meets, status in cases:
                    with self.subTest(
                        precision=precision, observed=observed, due=due
                    ):
                        start = datetime(
                            2026, 8, 1, tzinfo=timezone.utc
                        )
                        terminal = tuple(
                            (start + timedelta(hours=4 * index)).isoformat(
                                timespec="milliseconds"
                            ).replace("+00:00", "Z")
                            for index in range(due)
                        )
                        projection = {
                            "terminal_scheduled_for": terminal,
                            "observed_opportunity_count": observed,
                        }
                        health = opportunity_health(
                            projection=projection,
                            start_scheduled_for="2026-08-01T00:00:00.000Z",
                            detected_at=terminal[-1],
                        )
                        self.assertEqual(
                            (
                                health["coverage_numerator"],
                                health["coverage_denominator"],
                                health["meets_minimum_observed_coverage"],
                                health["eligibility_status"],
                            ),
                            (observed, due, meets, status),
                        )
        finally:
            decimal.setcontext(original)

    def test_large_coverage_is_exact_and_context_independent(self):
        observed = 9_500_000_000_000_001
        due = 10_000_000_000_000_001
        original = decimal.getcontext().copy()
        try:
            for precision in (2, 7, 28):
                decimal.getcontext().prec = precision
                self.assertEqual(
                    opportunity_coverage(observed, due),
                    {
                        "coverage_numerator": observed,
                        "coverage_denominator": due,
                        "meets_minimum_observed_coverage": True,
                    },
                )
        finally:
            decimal.setcontext(original)


if __name__ == "__main__":
    unittest.main()
