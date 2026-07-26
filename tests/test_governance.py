import copy
import tempfile
import unittest
from pathlib import Path

from crypto_quant.canonical import business_hash
from crypto_quant.errors import PolicyError
from crypto_quant.governance import GovernanceTemplateBundle
from crypto_quant.release import PolicyBundle, load_json_strict

ROOT = Path(__file__).resolve().parents[1]


class GovernanceTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = GovernanceTemplateBundle.load(ROOT / "config")

    def template(self, artifact_type):
        return next(
            artifact
            for artifact in self.bundle.templates.values()
            if artifact["artifact_type"] == artifact_type
        )

    def test_all_templates_validate_and_bundle_hash_is_frozen(self) -> None:
        result = self.bundle.result()
        self.assertEqual(result.template_count, 8)
        self.assertFalse(result.production_eligible)
        self.assertEqual(result.lifecycle_status, "TEMPLATE_UNAPPROVED")
        self.assertEqual(
            result.bundle_hash,
            "b3e45bae786b97889c66fdc08bfa6bda55663df7e13da6ef3d52adf8be1f9b14",
        )
        self.assertEqual(
            len({self.bundle.result().bundle_hash for _ in range(100)}),
            1,
        )
        self.assertEqual(len(set(result.artifact_types)), 8)

    def test_templates_cannot_be_mistaken_for_approved_bindings(self) -> None:
        for artifact in self.bundle.templates.values():
            self.assertIsNone(artifact["artifact_id_or_null"])
            self.assertFalse(artifact["production_eligible"])
            self.assertTrue(
                all(value is None for value in artifact["approval"].values())
            )
            self.assertEqual(len({business_hash(artifact) for _ in range(100)}), 1)

        readiness = PolicyBundle.load(ROOT / "config").readiness()
        self.assertEqual(readiness.result, "FAIL")
        for binding in (
            "data_quality_policy_id",
            "split_policy_id",
            "statistical_design_policy_id",
            "accounting_policy_id",
            "cost_allocation_policy_id",
            "forward_control_policy_id",
        ):
            self.assertIn(f"MISSING_BINDING:{binding}", readiness.reason_codes)

    def test_schema_rejects_approval_missing_sections_and_invalid_dates(self) -> None:
        approved = copy.deepcopy(self.template("ACCOUNTING_POLICY"))
        approved["production_eligible"] = True
        with self.assertRaises(PolicyError):
            self.bundle.validate_artifact(approved)

        incomplete = copy.deepcopy(self.template("FORWARD_CONTROL_POLICY"))
        del incomplete["specification"]["model_age_days"]
        with self.assertRaises(PolicyError):
            self.bundle.validate_artifact(incomplete)

        invalid_date = copy.deepcopy(self.template("INCIDENT_REPORT"))
        invalid_date["specification"]["detected_at_or_null"] = "not-a-date"
        with self.assertRaises(PolicyError):
            self.bundle.validate_artifact(invalid_date)

    def test_semantics_reject_incomplete_product_cost_and_harm_boundaries(self) -> None:
        data = copy.deepcopy(self.template("DATA_QUALITY_POLICY"))
        data["specification"]["product_data_matrix"][1]["product"] = "SPOT_LONG"
        with self.assertRaises(PolicyError):
            self.bundle.validate_artifact(data)

        costs = copy.deepcopy(self.template("COST_ALLOCATION_POLICY"))
        costs["specification"]["required_cost_event_types"].pop()
        with self.assertRaises(PolicyError):
            self.bundle.validate_artifact(costs)

        forward = copy.deepcopy(self.template("FORWARD_CONTROL_POLICY"))
        forward["specification"]["drawdown_actions"][0]["action"] = (
            "FLATTEN_AND_HALT"
        )
        with self.assertRaises(PolicyError):
            self.bundle.validate_artifact(forward)

    def test_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "duplicate.json"
            path.write_text('{"artifact_type":"A","artifact_type":"B"}')
            with self.assertRaises(PolicyError):
                load_json_strict(path)


if __name__ == "__main__":
    unittest.main()
