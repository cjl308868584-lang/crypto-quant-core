import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from crypto_quant.canonical import business_hash
from crypto_quant.evidence import (
    EvidenceTrustContext,
    artifact_self_hash,
    gate_evidence_hash,
)
from crypto_quant.release import PolicyBundle

ROOT = Path(__file__).resolve().parents[1]


def digest(label):
    return business_hash({"fixture": label})


class GateEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = PolicyBundle.load(ROOT / "config")

    def activated_bundle(self):
        policy = deepcopy(self.bundle.policy)
        policy["status"] = "ACTIVE"
        policy["production_activation"]["enabled"] = True
        for binding in policy["required_policy_bindings"]:
            if binding["value"] is None:
                if binding["binding"] == "evaluator_build_hash":
                    binding["value"] = digest("evaluator-build")
                else:
                    binding["value"] = f"approved:{binding['binding']}"
        bundle = PolicyBundle(
            root=self.bundle.root,
            policy=policy,
            catalog=deepcopy(self.bundle.catalog),
            evidence_schema=deepcopy(self.bundle.evidence_schema),
        )
        bundle.validate_cross_references()
        return bundle

    def fixture(self, bundle=None, *, ai=False, fallback=False):
        bundle = bundle or self.bundle
        if fallback and not ai:
            raise ValueError("fallback fixture uses an AI source route")
        builtin = bundle.authoritative_builtin_binding_hashes()
        binding_hashes = {
            "metric_catalog_id": builtin["metric_catalog_id"],
            "evidence_schema_id": builtin["evidence_schema_id"],
            "recipe_release_schema_id": builtin["recipe_release_schema_id"],
            "risk_policy_id": builtin["risk_policy_id"],
            "data_quality_policy_id": digest("data-quality-policy"),
            "split_policy_id": digest("split-policy"),
            "statistical_design_policy_id": digest("statistical-design-policy"),
            "accounting_policy_id": digest("accounting-policy"),
            "cost_allocation_policy_id": digest("cost-allocation-policy"),
            "forward_control_policy_id": digest("forward-control-policy"),
            "compliance_attestation_id": digest("compliance-attestation"),
            "evaluator_build_hash": digest("evaluator-build"),
        }
        if ai:
            binding_hashes["model_bundle_schema_id"] = builtin[
                "model_bundle_schema_id"
            ]
        if fallback:
            binding_hashes["approved_fallback_registry_schema_id"] = builtin[
                "approved_fallback_registry_schema_id"
            ]
        release_policy_hash = business_hash(bundle.policy)
        configured_bindings = {
            item["binding"]: item["value"]
            for item in bundle.policy["required_policy_bindings"]
        }
        binding_ids = {
            name: configured_bindings.get(name) or f"approved:{name}"
            for name in binding_hashes
        }
        experiment_hash = digest("experiment-manifest")
        policy_bundle_hash = business_hash(
            {
                "policy_binding_hashes": binding_hashes,
                "release_gate_policy_hash": release_policy_hash,
            }
        )
        recipe = {
            "schema_version": "1.1.0",
            "recipe_release_id": "recipe-1",
            "recipe_release_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "release_kind": "INITIAL",
            "release_route": "AI_ENHANCED" if ai else "BASELINE_ONLY",
            "ai_endpoint": "GROWTH" if ai else None,
            "baseline_recipe_release_id": "baseline-recipe-1" if ai else None,
            "baseline_recipe_release_hash": (
                digest("baseline-recipe") if ai else None
            ),
            "model_family": "XGBOOST" if ai else "NO_AI_BASE",
            "directions": ["LONG"],
            "venues": ["BINANCE_SPOT"],
            "experiment_manifest_hash": experiment_hash,
            "strategy_proposal_hash": digest("strategy-proposal"),
            "feature_schema_hash": digest("feature-schema"),
            "label_definition_hash": digest("label-definition"),
            "model_family_hash": digest("model-family"),
            "hyperparameter_search_space_hash": digest("search-space"),
            "calibration_method_hash": digest("calibration"),
            "decision_thresholds_hash": digest("decision-thresholds"),
            "position_policy_hash": digest("position-policy"),
            "risk_policy_hash": binding_hashes["risk_policy_id"],
            "execution_fill_model_hash": digest("fill-model"),
            "data_source_policy_hash": digest("data-source-policy"),
            "cost_definition_hash": digest("cost-definition"),
            "accounting_policy_hash": binding_hashes["accounting_policy_id"],
            "interface_compatibility_hash": digest("interface"),
            "data_quality_policy_hash": binding_hashes["data_quality_policy_id"],
            "split_policy_hash": binding_hashes["split_policy_id"],
            "statistical_design_policy_hash": binding_hashes[
                "statistical_design_policy_id"
            ],
            "cost_allocation_policy_hash": binding_hashes[
                "cost_allocation_policy_id"
            ],
            "forward_control_policy_hash": binding_hashes[
                "forward_control_policy_id"
            ],
            "release_gate_policy_hash": release_policy_hash,
            "policy_bundle_hash": policy_bundle_hash,
            "created_at": "2025-01-01T00:00:00Z",
            "frozen_at": "2025-12-31T23:59:57Z",
            "first_outcome_available_at": "2026-01-01T00:00:00Z",
            "freeze_attestation": {
                "frozen_before_any_outcome": True,
                "attestation_hash": digest("recipe-attestation"),
                "signer_id": "release-authority",
                "signed_at": "2025-12-31T23:59:58Z",
            },
            "status": "FROZEN",
        }
        recipe["recipe_release_hash"] = artifact_self_hash(
            recipe,
            "recipe_release_hash",
            "freeze_attestation",
        )
        model = None
        if ai:
            model = {
                "schema_version": "1.1.0",
                "model_bundle_id": "model-1",
                "model_bundle_hash": "0" * 64,
                "hash_algorithm": "SHA-256",
                "canonicalization": "RFC8785_JCS",
                "recipe_release_id": recipe["recipe_release_id"],
                "recipe_release_hash": recipe["recipe_release_hash"],
                "deployment_line_id": "line-1",
                "release_route": "AI_ENHANCED",
                "ai_endpoint": "GROWTH",
                "direction": "LONG",
                "venue": "BINANCE_SPOT",
                "model_family": "XGBOOST",
                "training_mode": "FROM_SCRATCH",
                "training_data_start": "2023-01-01T00:00:00Z",
                "training_data_cutoff": "2025-01-01T00:00:00Z",
                "trained_at": "2025-01-02T00:00:00Z",
                "weights_hash": digest("model-weights"),
                "preprocessor_hash": digest("model-preprocessor"),
                "calibrator_hash": digest("model-calibrator"),
                "ood_detector_hash": digest("model-ood"),
                "quantile_models_hash": digest("model-quantiles"),
                "feature_schema_hash": recipe["feature_schema_hash"],
                "ordered_feature_names_hash": digest("ordered-features"),
                "training_data_snapshot_hash": digest("training-data"),
                "code_artifact_hash": digest("model-code"),
                "environment_hash": digest("model-environment"),
                "interface_compatibility_hash": recipe[
                    "interface_compatibility_hash"
                ],
                "output_quantization_hash": digest("output-quantization"),
                "evidence_hashes": {
                    "experiment_manifest_hash": experiment_hash,
                    "training_evidence_hash": digest("training-evidence"),
                    "oos_evidence_hash": digest("oos-evidence"),
                    "golden_snapshot_evidence_hash": digest("golden-evidence"),
                    "current_status_evidence_hash": digest("status-evidence"),
                },
                "status": "CANDIDATE",
                "created_at": "2025-01-02T00:00:00Z",
                "activated_at": None,
                "retired_at": None,
                "bundle_signature": {
                    "algorithm": "ED25519",
                    "key_id": "model-authority",
                    "signed_at": "2025-01-02T00:00:01Z",
                    "signature_base64": "A" * 86 + "==",
                },
            }
            model["model_bundle_hash"] = artifact_self_hash(
                model,
                "model_bundle_hash",
                "bundle_signature",
            )

        artifact_hashes = {
            "recipe_release": recipe["recipe_release_hash"],
            "recipe_release_schema": binding_hashes["recipe_release_schema_id"],
            "experiment_manifest": experiment_hash,
            "metric_catalog": binding_hashes["metric_catalog_id"],
            "evidence_schema": binding_hashes["evidence_schema_id"],
            "release_gate_policy": release_policy_hash,
            "risk_policy": binding_hashes["risk_policy_id"],
            "data_quality_policy": binding_hashes["data_quality_policy_id"],
            "split_policy": binding_hashes["split_policy_id"],
            "statistical_design_policy": binding_hashes[
                "statistical_design_policy_id"
            ],
            "accounting_policy": binding_hashes["accounting_policy_id"],
            "cost_allocation_policy": binding_hashes[
                "cost_allocation_policy_id"
            ],
            "approved_capital_and_break_even_plan": digest("capital-plan"),
            "forward_control_policy": binding_hashes["forward_control_policy_id"],
            "compliance_attestation": binding_hashes[
                "compliance_attestation_id"
            ],
            "evaluator_build": binding_hashes["evaluator_build_hash"],
        }
        if ai:
            artifact_hashes["model_bundle"] = model["model_bundle_hash"]
            artifact_hashes["model_bundle_schema"] = binding_hashes[
                "model_bundle_schema_id"
            ]
        if fallback:
            artifact_hashes["approved_fallback_registry_schema"] = binding_hashes[
                "approved_fallback_registry_schema_id"
            ]

        frozen_inputs = {}
        signatures = {}
        freeze_evidence = {}
        for name, artifact_hash in artifact_hashes.items():
            signature_hash = digest(f"signature:{name}")
            freeze_hash = digest(f"freeze:{name}")
            signatures[signature_hash] = freeze_hash
            freeze_evidence[freeze_hash] = artifact_hash
            binding = next(
                (
                    key
                    for key, proof_name in bundle._BINDING_TO_FROZEN_INPUT.items()
                    if proof_name == name and key in binding_ids
                ),
                None,
            )
            frozen_inputs[name] = {
                "schema_id": f"{name}-schema",
                "artifact_id": (
                    binding_ids[binding]
                    if binding is not None
                    else (
                        recipe["recipe_release_id"]
                        if name == "recipe_release"
                        else (
                            model["model_bundle_id"]
                            if name == "model_bundle"
                            else f"{name}-1"
                        )
                    )
                ),
                "artifact_hash": artifact_hash,
                "frozen_at": "2025-12-31T23:59:58Z",
                "freeze_evidence_hash": freeze_hash,
                "signer_id": "release-authority",
                "signature_hash": signature_hash,
            }

        reveal_hash = digest("result-reveal")
        artifact_attestations = {
            recipe["freeze_attestation"]["attestation_hash"]: recipe[
                "recipe_release_hash"
            ]
        }
        artifact_documents = {"recipe_release": recipe}
        if ai:
            artifact_attestations[
                model["bundle_signature"]["signature_base64"]
            ] = model["model_bundle_hash"]
            artifact_documents["model_bundle"] = model
        fallback_evidence_hash = digest("fallback-lkg-evidence")
        fallback_top_signature_hash = digest("fallback-top-signature")
        fallback_record = None
        fallback_registry = None
        if fallback:
            fallback_record = {
                "fallback_approval_id": "fallback-approval-1",
                "record_hash": "0" * 64,
                "source": {
                    "release_route": "AI_ENHANCED",
                    "ai_endpoint": "GROWTH",
                    "recipe_release_id": recipe["recipe_release_id"],
                    "recipe_release_hash": recipe["recipe_release_hash"],
                    "deployment_line_id": "line-1",
                    "model_bundle_id": model["model_bundle_id"],
                    "no_ai_base_version": None,
                },
                "fallback": {
                    "release_route": "BASELINE_ONLY",
                    "ai_endpoint": None,
                    "recipe_release_id": "fallback-recipe-1",
                    "recipe_release_hash": digest("fallback-recipe"),
                    "deployment_line_id": "fallback-line-1",
                    "model_bundle_id": None,
                    "no_ai_base_version": "no-ai-base-v1",
                },
                "fallback_qualification": "CHAMPION",
                "direction": "LONG",
                "venue": "BINANCE_SPOT",
                "maximum_approved_stage": "CANARY_25",
                "policy_hashes": {
                    "policy_bundle_hash": policy_bundle_hash,
                    "release_gate_policy_hash": release_policy_hash,
                    "data_quality_policy_hash": binding_hashes[
                        "data_quality_policy_id"
                    ],
                    "split_policy_hash": binding_hashes["split_policy_id"],
                    "statistical_design_policy_hash": binding_hashes[
                        "statistical_design_policy_id"
                    ],
                    "position_policy_hash": recipe["position_policy_hash"],
                    "risk_policy_hash": binding_hashes["risk_policy_id"],
                    "execution_fill_model_hash": recipe[
                        "execution_fill_model_hash"
                    ],
                    "accounting_policy_hash": binding_hashes[
                        "accounting_policy_id"
                    ],
                    "cost_allocation_policy_hash": binding_hashes[
                        "cost_allocation_policy_id"
                    ],
                    "forward_control_policy_hash": binding_hashes[
                        "forward_control_policy_id"
                    ],
                    "interface_compatibility_hash": recipe[
                        "interface_compatibility_hash"
                    ],
                },
                "status": "APPROVED",
                "approved_at": "2025-12-01T00:00:00Z",
                "expires_at": "2026-12-31T23:59:59Z",
                "last_known_good_evidence_hash": fallback_evidence_hash,
                "qualification_attestation": {
                    "fallback_independently_approved": True,
                    "fallback_completed_full_release_path": True,
                    "candidate_status_excluded": True,
                    "source_scope_exact_match_verified": True,
                    "fallback_scope_exact_match_verified": True,
                    "fallback_differs_from_source": True,
                    "stage_cap_verified": True,
                    "policy_hashes_verified": True,
                    "lkg_evidence_verified": True,
                    "attestation_hash": digest("fallback-qualification"),
                },
                "signature": {
                    "algorithm": "ED25519",
                    "key_id": "fallback-authority",
                    "signed_at": "2025-12-01T00:00:01Z",
                    "signature_base64": "B" * 86 + "==",
                },
            }
            fallback_record["record_hash"] = artifact_self_hash(
                fallback_record,
                "record_hash",
                "signature",
            )
            fallback_registry = {
                "schema_version": "1.1.0",
                "registry_id": "fallback-registry-1",
                "registry_version": "1.0.0",
                "registry_hash": "0" * 64,
                "hash_algorithm": "SHA-256",
                "canonicalization": "RFC8785_JCS",
                "policy_bundle_hash": policy_bundle_hash,
                "status": "ACTIVE",
                "generated_at": "2025-12-01T00:00:02Z",
                "records": [fallback_record],
                "registry_signature": {
                    "algorithm": "ED25519",
                    "key_id": "fallback-registry-authority",
                    "signed_at": "2025-12-01T00:00:03Z",
                    "signature_base64": "C" * 86 + "==",
                },
            }
            fallback_registry["registry_hash"] = artifact_self_hash(
                fallback_registry,
                "registry_hash",
                "registry_signature",
            )
            artifact_attestations[
                fallback_record["signature"]["signature_base64"]
            ] = fallback_record["record_hash"]
            artifact_attestations[
                fallback_registry["registry_signature"]["signature_base64"]
            ] = fallback_registry["registry_hash"]
            artifact_documents["approved_fallback_registry"] = fallback_registry
        trust = EvidenceTrustContext(
            policy_bundle_hash=policy_bundle_hash,
            binding_ids=binding_ids,
            binding_hashes=binding_hashes,
            artifact_hashes=artifact_hashes,
            capital_values={
                "approved_production_capital_usdt": "500",
                "actual_deployable_capital_usdt": "1000",
                "break_even_capital_lcb_root_usdt": "800",
            },
            verified_signatures=signatures,
            verified_freeze_evidence=freeze_evidence,
            verified_reveal_events={"reveal-1": reveal_hash},
            verified_fallback_signatures=(
                {fallback_top_signature_hash: fallback_evidence_hash}
                if fallback
                else {}
            ),
            verified_artifact_attestations=artifact_attestations,
            artifact_documents=artifact_documents,
        )

        gate_values = {
            "BREAK_EVEN_ROOT_IS_FINITE": (True, True),
            "ACTUAL_CAPITAL_AT_LEAST_APPROVED": ("1000", "500"),
            "ACTUAL_CAPITAL_AT_LEAST_BREAK_EVEN": ("1000", "800"),
        }
        gates = {
            gate["gate_id"]: gate
            for gate in bundle.flat_gate_groups()["CAPITAL_READINESS"]
        }
        envelopes = []
        for gate_id, (metric_value, threshold) in gate_values.items():
            gate = gates[gate_id]
            definition = bundle.metrics.resolve(gate["metric_id"])
            evidence = {
                "evidence_id": f"evidence-{gate_id.lower()}",
                "gate_group_id": "CAPITAL_READINESS",
                "gate_id": gate_id,
                "metric_id": gate["metric_id"],
                "metric_catalog_id": bundle.catalog["catalog_id"],
                "estimator_id": definition["estimator_id"],
                "release_gate_policy_id": bundle.policy["policy_id"],
                "release_gate_policy_version": bundle.policy["policy_version"],
                "release_route": "AI_ENHANCED" if ai else "BASELINE_ONLY",
                "release_kind": "INITIAL",
                "evaluation_ledger": "ROUTE_RUNTIME",
                "fallback_activation_requested": fallback,
                "ai_endpoint": "GROWTH" if ai else None,
                "recipe_release_schema_id": "recipe-release-v1.1.schema.json",
                "recipe_release_id": recipe["recipe_release_id"],
                "recipe_release_hash": recipe["recipe_release_hash"],
                "deployment_line_id": "line-1",
                "model_bundle_id": model["model_bundle_id"] if ai else None,
                "model_bundle_schema_id": (
                    "model-bundle-v1.1.schema.json" if ai else None
                ),
                "model_bundle_hash": model["model_bundle_hash"] if ai else None,
                "direction": "LONG",
                "venue": "BINANCE_SPOT",
                "stage": "PAPER",
                "evaluation_window_start": "2025-01-01T00:00:00Z",
                "evaluation_window_end": "2025-12-31T23:59:59Z",
                "first_result_revealed_at": "2026-01-01T00:00:00Z",
                "first_result_reveal_event_id": "reveal-1",
                "first_result_reveal_evidence_hash": reveal_hash,
                "approved_production_capital_usdt": "500",
                "actual_deployable_capital_usdt": "1000",
                "break_even_capital_lcb_root_usdt": "800",
                "policy_bundle_hash": policy_bundle_hash,
                "policy_binding_hashes": binding_hashes,
                "frozen_release_inputs": frozen_inputs,
                "metric_value": metric_value,
                "metric_unit": definition["unit"],
                "comparator": gate["comparator"],
                "threshold_snapshot": threshold,
                "result": "PASS",
                "sample_status": {
                    "raw_event_count": 100,
                    "effective_event_count": 80,
                    "sufficient": True,
                },
                "artifact_hashes": [
                    artifact_hashes["approved_capital_and_break_even_plan"]
                ],
                "computed_at": "2026-01-01T00:00:01Z",
                "evidence_hash": "0" * 64,
            }
            if fallback:
                evidence.update(
                    {
                        "approved_fallback_registry_record_id": fallback_record[
                            "fallback_approval_id"
                        ],
                        "approved_fallback_registry_schema_id": (
                            "approved-fallback-registry-v1.1.schema.json"
                        ),
                        "approved_fallback_registry_record_hash": fallback_record[
                            "record_hash"
                        ],
                        "approved_fallback_registry_evidence_hash": (
                            fallback_evidence_hash
                        ),
                        "approved_fallback_registry_status": "APPROVED",
                        "approved_fallback_registry_expires_at": fallback_record[
                            "expires_at"
                        ],
                        "approved_fallback_registry_signer_id": (
                            "fallback-authority"
                        ),
                        "approved_fallback_registry_signature_hash": (
                            fallback_top_signature_hash
                        ),
                    }
                )
            evidence["evidence_hash"] = gate_evidence_hash(evidence)
            envelopes.append(evidence)
        scope = bundle.evidence_scope_snapshot(envelopes[0])
        return bundle, envelopes, scope, trust

    def test_complete_capital_gate_envelopes_validate(self):
        bundle, envelopes, scope, trust = self.fixture()
        validations = [
            bundle.validate_gate_evidence(
                "CAPITAL_READINESS",
                evidence,
                expected_scope=scope,
                trust=trust,
            )
            for evidence in envelopes
        ]
        self.assertTrue(all(result.valid for result in validations))
        self.assertEqual(
            {result.computed_gate_result for result in validations},
            {"PASS"},
        )
        self.assertEqual(
            {result.computed_evidence_hash for result in validations},
            {evidence["evidence_hash"] for evidence in envelopes},
        )

    def test_ai_evidence_binds_model_schema_signature_and_release_scope(self):
        bundle, envelopes, scope, trust = self.fixture(ai=True)
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=trust,
        )
        self.assertTrue(result.valid, result.reason_codes)

        model = deepcopy(trust.artifact_documents["model_bundle"])
        model["recipe_release_hash"] = digest("wrong-recipe")
        model["model_bundle_hash"] = artifact_self_hash(
            model,
            "model_bundle_hash",
            "bundle_signature",
        )
        wrong_reference = replace(
            trust,
            artifact_documents={
                **trust.artifact_documents,
                "model_bundle": model,
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=wrong_reference,
        )
        self.assertIn(
            "MODEL_BUNDLE_REFERENCE_MISMATCH:recipe_release_hash",
            result.reason_codes,
        )

        unverified_signature = replace(
            trust,
            verified_artifact_attestations={
                key: value
                for key, value in trust.verified_artifact_attestations.items()
                if key
                != trust.artifact_documents["model_bundle"]["bundle_signature"][
                    "signature_base64"
                ]
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=unverified_signature,
        )
        self.assertIn("MODEL_BUNDLE_SIGNATURE_UNVERIFIED", result.reason_codes)

    def test_fallback_activation_requires_signed_unexpired_exact_record(self):
        bundle, envelopes, scope, trust = self.fixture(ai=True, fallback=True)
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=trust,
        )
        self.assertTrue(result.valid, result.reason_codes)

        registry = deepcopy(
            trust.artifact_documents["approved_fallback_registry"]
        )
        registry["records"][0]["source"]["deployment_line_id"] = "other-line"
        registry["records"][0]["record_hash"] = artifact_self_hash(
            registry["records"][0],
            "record_hash",
            "signature",
        )
        registry["registry_hash"] = artifact_self_hash(
            registry,
            "registry_hash",
            "registry_signature",
        )
        mismatched = replace(
            trust,
            artifact_documents={
                **trust.artifact_documents,
                "approved_fallback_registry": registry,
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=mismatched,
        )
        self.assertIn(
            "FALLBACK_SOURCE_SCOPE_MISMATCH:deployment_line_id",
            result.reason_codes,
        )

        expired_registry = deepcopy(
            trust.artifact_documents["approved_fallback_registry"]
        )
        expired_registry["records"][0]["expires_at"] = "2025-12-31T00:00:00Z"
        expired_registry["records"][0]["record_hash"] = artifact_self_hash(
            expired_registry["records"][0],
            "record_hash",
            "signature",
        )
        expired_registry["registry_hash"] = artifact_self_hash(
            expired_registry,
            "registry_hash",
            "registry_signature",
        )
        expired = replace(
            trust,
            artifact_documents={
                **trust.artifact_documents,
                "approved_fallback_registry": expired_registry,
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=expired,
        )
        self.assertIn("APPROVED_FALLBACK_RECORD_EXPIRED", result.reason_codes)

        unsigned = replace(trust, verified_fallback_signatures={})
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=unsigned,
        )
        self.assertIn("FALLBACK_SIGNATURE_UNVERIFIED", result.reason_codes)

    def test_claimed_result_threshold_unit_and_estimator_are_recomputed(self):
        bundle, envelopes, scope, trust = self.fixture()
        cases = (
            ("result", "FAIL", "EVIDENCE_CLAIMED_RESULT_MISMATCH"),
            ("threshold_snapshot", "499", "EVIDENCE_THRESHOLD_SNAPSHOT_MISMATCH"),
            ("metric_unit", "wrong-unit", "EVIDENCE_METRIC_UNIT_MISMATCH"),
            ("estimator_id", "UNKNOWN_V1", "EVIDENCE_ESTIMATOR_MISMATCH"),
            ("comparator", "LT", "EVIDENCE_COMPARATOR_MISMATCH"),
        )
        source = envelopes[1]
        for field, value, expected_reason in cases:
            evidence = deepcopy(source)
            evidence[field] = value
            evidence["evidence_hash"] = gate_evidence_hash(evidence)
            with self.subTest(field=field):
                result = bundle.validate_gate_evidence(
                    "CAPITAL_READINESS",
                    evidence,
                    expected_scope=scope,
                    trust=trust,
                )
                self.assertFalse(result.valid)
                self.assertIn(expected_reason, result.reason_codes)

    def test_hash_freeze_signature_reveal_and_capital_are_independent_proofs(self):
        bundle, envelopes, scope, trust = self.fixture()
        source = envelopes[0]

        corrupt_hash = deepcopy(source)
        corrupt_hash["evidence_hash"] = "f" * 64
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            corrupt_hash,
            expected_scope=scope,
            trust=trust,
        )
        self.assertIn("EVIDENCE_HASH_MISMATCH", result.reason_codes)

        late = deepcopy(source)
        late["frozen_release_inputs"]["risk_policy"]["frozen_at"] = (
            "2026-01-01T00:00:01Z"
        )
        late["evidence_hash"] = gate_evidence_hash(late)
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            late,
            expected_scope=scope,
            trust=trust,
        )
        self.assertIn(
            "FREEZE_AFTER_RESULT_REVEAL:risk_policy",
            result.reason_codes,
        )

        missing_signature = replace(
            trust,
            verified_signatures={},
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            source,
            expected_scope=scope,
            trust=missing_signature,
        )
        self.assertTrue(
            any(
                reason.startswith("FREEZE_SIGNATURE_UNVERIFIED:")
                for reason in result.reason_codes
            )
        )

        mixed_signature = replace(
            trust,
            verified_signatures={
                signature: digest("another-freeze-proof")
                for signature in trust.verified_signatures
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            source,
            expected_scope=scope,
            trust=mixed_signature,
        )
        self.assertTrue(
            any(
                reason.startswith("FREEZE_SIGNATURE_UNVERIFIED:")
                for reason in result.reason_codes
            )
        )

        missing_reveal = replace(
            trust,
            verified_reveal_events={},
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            source,
            expected_scope=scope,
            trust=missing_reveal,
        )
        self.assertIn(
            "FIRST_RESULT_REVEAL_EVIDENCE_UNVERIFIED",
            result.reason_codes,
        )

        wrong_capital = replace(
            trust,
            capital_values={
                **trust.capital_values,
                "actual_deployable_capital_usdt": "999",
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            source,
            expected_scope=scope,
            trust=wrong_capital,
        )
        self.assertIn(
            "FROZEN_CAPITAL_VALUE_MISMATCH:actual_deployable_capital_usdt",
            result.reason_codes,
        )

    def test_builtin_binding_and_recipe_cross_references_cannot_be_forged(self):
        bundle, envelopes, scope, trust = self.fixture()
        evidence = deepcopy(envelopes[0])
        forged = digest("forged-metric-catalog")
        evidence["policy_binding_hashes"]["metric_catalog_id"] = forged
        evidence["frozen_release_inputs"]["metric_catalog"]["artifact_hash"] = forged
        evidence["evidence_hash"] = gate_evidence_hash(evidence)
        forged_trust = replace(
            trust,
            binding_hashes={**trust.binding_hashes, "metric_catalog_id": forged},
            artifact_hashes={**trust.artifact_hashes, "metric_catalog": forged},
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            evidence,
            expected_scope=scope,
            trust=forged_trust,
        )
        self.assertIn(
            "BUILTIN_BINDING_HASH_MISMATCH:metric_catalog_id",
            result.reason_codes,
        )

        wrong_binding_id = replace(
            trust,
            binding_ids={
                **trust.binding_ids,
                "metric_catalog_id": "another-catalog-id",
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=wrong_binding_id,
        )
        self.assertIn(
            "POLICY_BINDING_ID_MISMATCH:metric_catalog_id",
            result.reason_codes,
        )
        self.assertIn(
            "BINDING_FREEZE_ID_MISMATCH:metric_catalog_id",
            result.reason_codes,
        )

        recipe = deepcopy(trust.artifact_documents["recipe_release"])
        recipe["directions"] = ["SHORT"]
        recipe["recipe_release_hash"] = artifact_self_hash(
            recipe,
            "recipe_release_hash",
            "freeze_attestation",
        )
        wrong_recipe = replace(
            trust,
            artifact_documents={"recipe_release": recipe},
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=scope,
            trust=wrong_recipe,
        )
        self.assertIn("RECIPE_RELEASE_DIRECTION_MISMATCH", result.reason_codes)
        self.assertIn(
            "RECIPE_RELEASE_REFERENCE_MISMATCH:recipe_release_hash",
            result.reason_codes,
        )

    def test_sample_status_and_exact_scope_fail_closed(self):
        bundle, envelopes, scope, trust = self.fixture()
        evidence = deepcopy(envelopes[0])
        evidence["sample_status"]["effective_event_count"] = 101
        evidence["sample_status"]["sufficient"] = False
        evidence["result"] = "INCONCLUSIVE"
        evidence["threshold_snapshot"] = None
        evidence["evidence_hash"] = gate_evidence_hash(evidence)
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            evidence,
            expected_scope=scope,
            trust=trust,
        )
        self.assertIn("EFFECTIVE_SAMPLE_EXCEEDS_RAW_SAMPLE", result.reason_codes)
        self.assertEqual(result.computed_gate_result, "INCONCLUSIVE")

        wrong_scope = deepcopy(scope)
        wrong_scope["stage"] = "CANARY_25"
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=wrong_scope,
            trust=trust,
        )
        self.assertIn("SCOPE_VALUE_MISMATCH:stage", result.reason_codes)

    def test_production_group_requires_complete_evidence_and_readiness(self):
        bundle, envelopes, scope, trust = self.fixture()
        blocked = bundle.evaluate_evidence_group(
            "CAPITAL_READINESS",
            envelopes,
            expected_scope=scope,
            trust=trust,
        )
        self.assertEqual(blocked.result, "FAIL")
        self.assertTrue(
            any(
                reason.startswith("RELEASE_NOT_READY:")
                for reason in blocked.reason_codes
            )
        )

        active = self.activated_bundle()
        active, envelopes, scope, trust = self.fixture(active)
        passed = active.evaluate_evidence_group(
            "CAPITAL_READINESS",
            envelopes,
            expected_scope=scope,
            trust=trust,
        )
        self.assertEqual(passed.result, "PASS")
        self.assertTrue(all(item.valid for item in passed.evidence_results))

        insufficient = deepcopy(envelopes)
        insufficient[0]["sample_status"]["sufficient"] = False
        insufficient[0]["threshold_snapshot"] = None
        insufficient[0]["result"] = "INCONCLUSIVE"
        insufficient[0]["evidence_hash"] = gate_evidence_hash(insufficient[0])
        inconclusive = active.evaluate_evidence_group(
            "CAPITAL_READINESS",
            insufficient,
            expected_scope=scope,
            trust=trust,
        )
        self.assertEqual(inconclusive.result, "INCONCLUSIVE")
        self.assertIn(
            "REQUIRED_GATE_INCONCLUSIVE:BREAK_EVEN_ROOT_IS_FINITE",
            inconclusive.reason_codes,
        )

        missing = active.evaluate_evidence_group(
            "CAPITAL_READINESS",
            envelopes[:-1],
            expected_scope=scope,
            trust=trust,
        )
        self.assertEqual(missing.result, "FAIL")
        self.assertIn(
            "MISSING_GATE_EVIDENCE:ACTUAL_CAPITAL_AT_LEAST_BREAK_EVEN",
            missing.reason_codes,
        )

    def test_validation_and_group_hashes_are_deterministic_100_times(self):
        active = self.activated_bundle()
        active, envelopes, scope, trust = self.fixture(active)
        results = [
            active.evaluate_evidence_group(
                "CAPITAL_READINESS",
                envelopes,
                expected_scope=scope,
                trust=trust,
            )
            for _ in range(100)
        ]
        self.assertEqual({result.result for result in results}, {"PASS"})
        self.assertEqual(len({result.result_hash for result in results}), 1)
        self.assertEqual(
            len(
                {
                    tuple(
                        validation.validation_hash
                        for validation in result.evidence_results
                    )
                    for result in results
                }
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
