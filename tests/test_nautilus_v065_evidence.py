import copy
import unittest
from pathlib import Path

from crypto_quant.nautilus_v065_contract import (
    _self_hash,
    build_nautilus_v065_current_reference,
    build_nautilus_v065_request,
)
from crypto_quant.nautilus_v065_evidence import (
    NautilusV065EvidenceError,
    build_nautilus_v065_supply_failure_comparison,
    compare_nautilus_v065,
)
from crypto_quant.nautilus_v065_plan import build_nautilus_v065_plan
from crypto_quant.nautilus_v065_supply_chain import supply_chain_receipt_hash
import test_nautilus_v065_supply_chain as supply_chain_fixtures


ROOT = Path(__file__).resolve().parents[1]


def _rehash_result(value):
    result = copy.deepcopy(value)
    for scenario in result["scenario_results"]:
        for event in scenario["events"]:
            event["event_hash"] = "0" * 64
            event["event_hash"] = _self_hash(event, "event_hash")
    result["result_id"] = "nautilus_v065_result_" + "0" * 64
    result["result_hash"] = "0" * 64
    digest = _self_hash(result, "result_id", "result_hash")
    result["result_id"] = "nautilus_v065_result_" + digest
    result["result_hash"] = digest
    return result


class NautilusV065EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_nautilus_v065_plan(
            repository_root=ROOT,
            candidate_commit=__import__("subprocess").check_output(
                ["/usr/bin/git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        )

    def evidence(self):
        receipt = supply_chain_fixtures.NautilusV065SupplyChainTests().receipt()
        receipt["plan_id"] = self.plan["plan_id"]
        receipt["plan_hash"] = self.plan["plan_hash"]
        receipt["receipt_id"] = "nautilus_v065_supply_chain_" + "0" * 64
        receipt["receipt_hash"] = "0" * 64
        digest = supply_chain_receipt_hash(receipt)
        receipt["receipt_id"] = "nautilus_v065_supply_chain_" + digest
        receipt["receipt_hash"] = digest
        request = build_nautilus_v065_request(
            plan_id=self.plan["plan_id"],
            plan_hash=self.plan["plan_hash"],
            supply_chain_receipt_id=receipt["receipt_id"],
            supply_chain_receipt_hash=receipt["receipt_hash"],
        )
        current = build_nautilus_v065_current_reference(request=request)
        candidate = copy.deepcopy(current)
        candidate["engine"] = "NAUTILUS_TRADER_1.230.0"
        candidate = _rehash_result(candidate)
        return receipt, request, current, candidate, copy.deepcopy(candidate)

    def compare(self, **changes):
        receipt, request, current, first, replay = self.evidence()
        values = dict(
            plan=self.plan,
            receipt=receipt,
            request=request,
            current_reference=current,
            first_result=first,
            replay_result=replay,
        )
        values.update(changes)
        return compare_nautilus_v065(**values)

    def test_exact_and_pure_decimal_representation_are_the_only_adoptable_results(self):
        exact = self.compare()
        self.assertEqual(exact["difference_classes"], ["EXACT_MATCH"])
        self.assertEqual(exact["conclusion"], "ADOPT_FOR_PREREGISTERED_SHADOW")
        self.assertTrue(all(exact["gates"].values()))

        receipt, request, current, first, replay = self.evidence()
        first["scenario_results"][0]["filled_quantity"] = "0.0500"
        replay["scenario_results"][0]["filled_quantity"] = "0.0500"
        first, replay = _rehash_result(first), _rehash_result(replay)
        represented = compare_nautilus_v065(
            plan=self.plan, receipt=receipt, request=request,
            current_reference=current, first_result=first, replay_result=replay,
        )
        self.assertEqual(
            represented["difference_classes"],
            ["EXPECTED_ENGINE_REPRESENTATION_DIFFERENCE"],
        )
        self.assertEqual(represented["conclusion"], "ADOPT_FOR_PREREGISTERED_SHADOW")

    def test_each_preregistered_economic_difference_has_one_directional_class(self):
        cases = (
            ("average_price", "2000.101", "ROUNDING_POLICY_DIFFERENCE"),
            ("filled_quantity", "0.04", "FILL_MODEL_DIFFERENCE"),
            ("fee_usdt", "0.2", "FEE_MODEL_DIFFERENCE"),
            ("ending_cash_usdt", "899", "POSITION_ACCOUNTING_DIFFERENCE"),
            ("net_pnl_usdt", "-1", "PNL_ACCOUNTING_DIFFERENCE"),
        )
        for field, value, expected in cases:
            with self.subTest(field=field):
                receipt, request, current, first, replay = self.evidence()
                first["scenario_results"][0][field] = value
                replay["scenario_results"][0][field] = value
                first, replay = _rehash_result(first), _rehash_result(replay)
                comparison = compare_nautilus_v065(
                    plan=self.plan, receipt=receipt, request=request,
                    current_reference=current, first_result=first, replay_result=replay,
                )
                self.assertIn(expected, comparison["difference_classes"])
                self.assertEqual(comparison["conclusion"], "REJECT_KEEP_CURRENT_CORE")

    def test_observed_nautilus_partial_fill_is_rejected_without_changing_reference(self):
        receipt, request, current, first, replay = self.evidence()
        partial = first["scenario_results"][1]
        partial.update(
            average_price="2000.106",
            fee_usdt="0.1000053",
            ending_cash_usdt="899.8946947",
            unrealized_pnl_usdt="0.0022",
            net_pnl_usdt="-0.0978053",
        )
        partial["events"][2].update(price="2000.11", fee_usdt="0.0600033")
        replay = copy.deepcopy(first)
        first, replay = _rehash_result(first), _rehash_result(replay)
        comparison = compare_nautilus_v065(
            plan=self.plan, receipt=receipt, request=request,
            current_reference=current, first_result=first, replay_result=replay,
        )
        self.assertEqual(
            comparison["difference_classes"],
            [
                "FILL_MODEL_DIFFERENCE",
                "FEE_MODEL_DIFFERENCE",
                "POSITION_ACCOUNTING_DIFFERENCE",
                "PNL_ACCOUNTING_DIFFERENCE",
            ],
        )
        self.assertEqual(comparison["conclusion"], "REJECT_KEEP_CURRENT_CORE")
        self.assertEqual(
            current["scenario_results"][1]["average_price"], "2000.16"
        )

    def test_instrument_restart_and_safety_boundaries_are_not_adoptable(self):
        receipt, request, current, first, replay = self.evidence()
        first["scenario_results"][2]["status"] = "FILLED"
        first["scenario_results"][2]["events"][0]["status"] = "FILLED"
        replay = copy.deepcopy(first)
        first, replay = _rehash_result(first), _rehash_result(replay)
        unsupported = compare_nautilus_v065(
            plan=self.plan, receipt=receipt, request=request,
            current_reference=current, first_result=first, replay_result=replay,
        )
        self.assertIn("UNSUPPORTED_INSTRUMENT_RULE", unsupported["difference_classes"])

        receipt, request, current, first, replay = self.evidence()
        replay["scenario_results"][0]["average_price"] = "2000.11"
        replay = _rehash_result(replay)
        restarted = compare_nautilus_v065(
            plan=self.plan, receipt=receipt, request=request,
            current_reference=current, first_result=first, replay_result=replay,
        )
        self.assertEqual(restarted["difference_classes"], ["RESTART_SEMANTICS_DIFFERENCE"])

        receipt, request, current, first, replay = self.evidence()
        first["safety_counters"]["network_requests"] = 1
        replay["safety_counters"]["network_requests"] = 1
        first, replay = _rehash_result(first), _rehash_result(replay)
        unsafe = compare_nautilus_v065(
            plan=self.plan, receipt=receipt, request=request,
            current_reference=current, first_result=first, replay_result=replay,
        )
        self.assertEqual(unsafe["difference_classes"], ["SAFETY_BOUNDARY_VIOLATION"])
        self.assertEqual(unsafe["conclusion"], "REJECT_KEEP_CURRENT_CORE")

    def test_supply_failure_is_inconclusive_without_runner_evidence(self):
        comparison = build_nautilus_v065_supply_failure_comparison(
            plan=self.plan,
            reason_code="NAUTILUS_V065_SLSA_VERIFICATION_FAILED",
            runner_invocation_count=0,
        )
        self.assertEqual(comparison["difference_classes"], ["SUPPLY_CHAIN_OR_LICENSE_FAILURE"])
        self.assertEqual(comparison["conclusion"], "INCONCLUSIVE_KEEP_CURRENT_CORE")
        self.assertEqual(comparison["runner_invocation_count"], 0)

    def test_tamper_unclassified_or_incomplete_evidence_fails_closed(self):
        receipt, request, current, first, replay = self.evidence()
        for mutate in (
            lambda: first.__setitem__("result_hash", "0" * 64),
            lambda: current["scenario_results"][0].__setitem__("average_price", "999"),
            lambda: request["scenarios"][0]["order_intent"].__setitem__("quantity", "0.06"),
        ):
            with self.subTest():
                local_receipt, local_request, local_current, local_first, local_replay = self.evidence()
                receipt, request, current, first, replay = local_receipt, local_request, local_current, local_first, local_replay
                mutate()
                with self.assertRaises(NautilusV065EvidenceError):
                    compare_nautilus_v065(
                        plan=self.plan, receipt=receipt, request=request,
                        current_reference=current, first_result=first, replay_result=replay,
                    )


if __name__ == "__main__":
    unittest.main()
