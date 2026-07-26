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
from crypto_quant.release_artifacts import (
    deployment_line_hash,
    experiment_manifest_hash,
    experiment_recipe_binding_hash,
    supporting_observation_bundle_hash,
    supporting_observation_hash,
)
from crypto_quant.statistical_decision import (
    build_statistical_decision_snapshot,
    statistical_decision_snapshot_hash,
    statistical_trial_registry_hash,
)
from crypto_quant.statistics import statistical_series_hash
from tests.factories import (
    make_statistical_decision_snapshot,
    statistical_decision_inputs,
)

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
                    binding["value"] = self.bundle.evaluator_build.build_hash
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
            "evaluator_build_hash": builtin["evaluator_build_hash"],
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
        experiment_hash = "0" * 64
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
        experiment = {
            "$schema": "./experiment-manifest-v1.1.schema.json",
            "schema_version": "1.1.0",
            "experiment_id": "experiment-1",
            "experiment_manifest_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "hypothesis_id": "hypothesis-1",
            "parent_experiment_ids": [],
            "release_route": recipe["release_route"],
            "ai_endpoint": recipe["ai_endpoint"],
            "endpoint_policy_version": bundle.policy["policy_version"],
            "baseline_recipe_release_id": recipe[
                "baseline_recipe_release_id"
            ],
            "baseline_recipe_release_hash": recipe[
                "baseline_recipe_release_hash"
            ],
            "route_and_endpoint_frozen_at": "2024-12-31T23:59:58Z",
            "created_by": "HUMAN",
            "created_at": "2024-12-31T23:59:57Z",
            "status": "COMPLETED",
            "failure_reason": None,
            "code_and_environment": {
                "git_commit": "a" * 40,
                "dirty_worktree": False,
                "dirty_patch_hash": None,
                "environment_lock_hash": digest("experiment-environment"),
                "library_hardware_hash": digest("library-hardware"),
                "random_seeds": {
                    "numpy": 7,
                    "model": 11,
                    "bootstrap": 13,
                },
                "training_entrypoint": "crypto_quant.train",
                "parameters_hash": digest("training-parameters"),
            },
            "data": {
                "raw_snapshots": [
                    {
                        "snapshot_id": "market-snapshot-1",
                        "snapshot_hash": digest("market-snapshot"),
                    }
                ],
                "data_source_policy_hash": recipe[
                    "data_source_policy_hash"
                ],
                "available_time_rule_hash": digest("available-time-rule"),
                "instrument_metadata_hashes": [
                    digest("instrument-metadata")
                ],
                "windows": [
                    {
                        "role": "FIT",
                        "start": "2023-01-01T00:00:00Z",
                        "end": "2024-01-01T00:00:00Z",
                    },
                    {
                        "role": "CALIBRATION",
                        "start": "2024-01-01T00:00:00Z",
                        "end": "2024-07-01T00:00:00Z",
                    },
                    {
                        "role": "VALIDATION",
                        "start": "2024-07-01T00:00:00Z",
                        "end": "2025-01-01T00:00:00Z",
                    },
                ],
                "purge_hours": 24,
                "embargo_hours": 24,
                "missing_anomaly_rule_hash": digest(
                    "missing-anomaly-rule"
                ),
                "data_quality_report_hash": digest("data-quality-report"),
            },
            "frozen_design_hashes": {
                name: recipe[name]
                for name in (
                    "strategy_proposal_hash",
                    "feature_schema_hash",
                    "label_definition_hash",
                    "model_family_hash",
                    "hyperparameter_search_space_hash",
                    "calibration_method_hash",
                    "decision_thresholds_hash",
                    "position_policy_hash",
                    "risk_policy_hash",
                    "execution_fill_model_hash",
                    "data_source_policy_hash",
                    "cost_definition_hash",
                    "accounting_policy_hash",
                    "interface_compatibility_hash",
                    "data_quality_policy_hash",
                    "split_policy_hash",
                    "statistical_design_policy_hash",
                    "cost_allocation_policy_hash",
                    "forward_control_policy_hash",
                    "release_gate_policy_hash",
                    "policy_bundle_hash",
                )
            },
            "economics": {
                "approved_production_capital_usdt": "500",
                "reporting_asset": "USDT",
                "evaluation_window_start": "2025-01-01T00:00:00Z",
                "evaluation_window_end": "2025-12-31T23:59:59Z",
                "minimum_economic_effect": "0.001",
                "target_power": "0.80",
                "maximum_ci_width": "0.01",
                "trial_family_id": "trial-family-1",
                "multiplicity_method": "HOLM",
                "family_wise_alpha": "0.05",
                "benchmark_hash": digest("benchmark"),
            },
            "search_budget": {
                "predeclared_trial_budget": 5,
                "actual_total_trials": 4,
                "hyperparameter_search_space_hash": recipe[
                    "hyperparameter_search_space_hash"
                ],
                "feature_set_count": 1,
                "threshold_variant_count": 1,
                "aborted_trials": 1,
                "failed_trials": 1,
                "invalid_trials": 0,
                "trial_registry_hash": digest("trial-registry"),
            },
            "outputs": {
                "model_and_calibrator_hashes": [
                    digest("experiment-model-output")
                ],
                "oos_prediction_artifact_hash": digest("oos-predictions"),
                "fold_trades_equity_hash": digest("fold-trades-equity"),
                "metrics_charts_audit_hash": digest(
                    "metrics-charts-audit"
                ),
                "feature_stability_hash": digest("feature-stability"),
                "failure_log_hash": digest("failure-log"),
                "conclusion": "CANDIDATE",
                "signed_by": "research-authority",
            },
            "recipe_binding": {
                "recipe_release_id": recipe["recipe_release_id"],
                "recipe_release_hash": "0" * 64,
                "recipe_binding_hash": "0" * 64,
            },
            "manifest_attestation": {
                "algorithm": "ED25519",
                "key_id": "research-authority",
                "signed_at": "2025-01-01T00:00:02Z",
                "signature_base64": "D" * 86 + "==",
            },
        }
        experiment_hash = experiment_manifest_hash(experiment)
        experiment["experiment_manifest_hash"] = experiment_hash
        recipe["experiment_manifest_hash"] = experiment_hash
        recipe["recipe_release_hash"] = artifact_self_hash(
            recipe,
            "recipe_release_hash",
            "freeze_attestation",
        )
        experiment["recipe_binding"]["recipe_release_hash"] = recipe[
            "recipe_release_hash"
        ]
        experiment["recipe_binding"]["recipe_binding_hash"] = (
            experiment_recipe_binding_hash(experiment)
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

        deployment_line = {
            "$schema": "./deployment-line-v1.1.schema.json",
            "schema_version": "1.1.0",
            "deployment_line_id": "line-1",
            "deployment_line_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "release_kind": recipe["release_kind"],
            "recipe_release_id": recipe["recipe_release_id"],
            "recipe_release_hash": recipe["recipe_release_hash"],
            "experiment_manifest_hash": experiment_hash,
            "release_route": recipe["release_route"],
            "ai_endpoint": recipe["ai_endpoint"],
            "baseline_recipe_release_id": recipe[
                "baseline_recipe_release_id"
            ],
            "baseline_recipe_release_hash": recipe[
                "baseline_recipe_release_hash"
            ],
            "direction": "LONG",
            "venue": "BINANCE_SPOT",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-12-31T23:59:58Z",
            "revision": 1,
            "lifecycle_status": "ACTIVE",
            "current_stage": "PAPER",
            "stage_history": [
                {
                    "stage": "RECIPE_CANDIDATE",
                    "entered_at": "2025-01-01T00:00:00Z",
                    "exited_at": "2025-01-02T00:00:00Z",
                    "result": "PASS",
                    "evidence_hash": digest("candidate-evidence"),
                },
                {
                    "stage": "SHADOW",
                    "entered_at": "2025-01-02T00:00:00Z",
                    "exited_at": "2025-01-10T00:00:00Z",
                    "result": "PASS",
                    "evidence_hash": digest("shadow-evidence"),
                },
                {
                    "stage": "PAPER",
                    "entered_at": "2025-01-10T00:00:00Z",
                    "exited_at": None,
                    "result": "IN_PROGRESS",
                    "evidence_hash": None,
                },
            ],
            "active_model_bundle_id": (
                model["model_bundle_id"] if ai else None
            ),
            "active_model_bundle_hash": (
                model["model_bundle_hash"] if ai else None
            ),
            "active_no_ai_base_version": None if ai else "no-ai-base-v1",
            "last_known_good_reference_hash": None,
            "minor_bundle_refresh_count": 0,
            "evidence_inheritance": {
                "minor_bundle_may_preserve_stage_calendar": True,
                "bundle_segments_required": True,
                "major_change_inherits_evidence": False,
                "stage_runtime_pass_reuse_allowed": False,
            },
            "line_attestation": {
                "algorithm": "ED25519",
                "key_id": "deployment-authority",
                "signed_at": "2025-12-31T23:59:59Z",
                "signature_base64": "E" * 86 + "==",
            },
        }
        deployment_line["deployment_line_hash"] = deployment_line_hash(
            deployment_line
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
                            experiment["experiment_id"]
                            if name == "experiment_manifest"
                            else (
                                model["model_bundle_id"]
                                if name == "model_bundle"
                                else f"{name}-1"
                            )
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
            ],
            experiment["manifest_attestation"]["signature_base64"]: (
                experiment["recipe_binding"]["recipe_binding_hash"]
            ),
            deployment_line["line_attestation"]["signature_base64"]: (
                deployment_line["deployment_line_hash"]
            ),
        }
        artifact_documents = {
            "recipe_release": recipe,
            "experiment_manifest": experiment,
            "deployment_line": deployment_line,
        }
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
                "experiment_manifest_schema_id": (
                    "experiment-manifest-v1.1.schema.json"
                ),
                "experiment_manifest_id": experiment["experiment_id"],
                "experiment_manifest_hash": experiment_hash,
                "deployment_line_schema_id": (
                    "deployment-line-v1.1.schema.json"
                ),
                "deployment_line_id": "line-1",
                "deployment_line_hash": deployment_line[
                    "deployment_line_hash"
                ],
                "supporting_observation_bundle_schema_id": None,
                "supporting_observation_bundle_id": None,
                "supporting_observation_bundle_hash": None,
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

    def statistical_reference_fixture(self):
        snapshot = make_statistical_decision_snapshot()
        current = next(
            item
            for item in snapshot["trial_registry"]
            if item["candidate_id"] == snapshot["current_candidate_id"]
        )
        scope = snapshot["scope"]
        required_hashes = [
            snapshot["snapshot_hash"],
            snapshot["trial_registry_hash"],
            *[
                item["source_series_hash"]
                for item in snapshot["trial_registry"]
                if item["candidate_status"] == "EVALUATED"
            ],
        ]
        evidence = {
            "release_route": scope["release_route"],
            "evaluation_ledger": scope["evaluation_ledger"],
            "direction": scope["direction"],
            "venue": scope["venue"],
            "recipe_release_id": current["recipe_release_id"],
            "recipe_release_hash": current["recipe_release_hash"],
            "deployment_line_id": scope["deployment_line_id"],
            "deployment_line_hash": scope["deployment_line_hash"],
            "evaluation_window_start": scope["evaluation_window_start"],
            "evaluation_window_end": scope["evaluation_window_end"],
            "approved_production_capital_usdt": scope[
                "approved_production_capital_usdt"
            ],
            "ai_endpoint": None,
            "experiment_manifest_id": snapshot["experiment_manifest_id"],
            "experiment_manifest_hash": snapshot["experiment_manifest_hash"],
            "policy_binding_hashes": {
                "statistical_design_policy_id": snapshot[
                    "statistical_design_policy_hash"
                ],
            },
            "frozen_release_inputs": {
                "statistical_decision_snapshot": {
                    "artifact_id": snapshot["snapshot_id"],
                    "artifact_hash": snapshot["snapshot_hash"],
                }
            },
            "sample_status": {
                "raw_event_count": 6,
                "effective_event_count": 2,
                "sufficient": True,
            },
            "artifact_hashes": required_hashes,
        }
        experiment = {
            "experiment_id": snapshot["experiment_manifest_id"],
            "experiment_manifest_hash": snapshot["experiment_manifest_hash"],
            "economics": {
                "trial_family_id": snapshot["trial_family_id"],
                "minimum_economic_effect": snapshot["design"][
                    "minimum_economic_effect"
                ],
                "multiplicity_method": "HOLM",
                "family_wise_alpha": "0.05",
            },
            "search_budget": {
                "actual_total_trials": len(snapshot["trial_registry"]),
                "trial_registry_hash": snapshot["trial_registry_hash"],
            },
        }
        trust = EvidenceTrustContext(
            policy_bundle_hash="",
            binding_ids={},
            binding_hashes={},
            artifact_hashes={
                "statistical_decision_snapshot": snapshot["snapshot_hash"],
            },
            capital_values={},
            artifact_documents={
                "statistical_decision_snapshot": snapshot,
                "experiment_manifest": experiment,
            },
        )
        return snapshot, evidence, trust

    def complete_statistical_gate_fixture(self):
        bundle, envelopes, _, trust = self.fixture()
        evidence = deepcopy(envelopes[0])
        recipe = deepcopy(trust.artifact_documents["recipe_release"])
        experiment = deepcopy(
            trust.artifact_documents["experiment_manifest"]
        )
        deployment = deepcopy(
            trust.artifact_documents["deployment_line"]
        )
        inputs = statistical_decision_inputs()
        current = next(
            item
            for item in inputs["trial_registry"]
            if item["candidate_id"] == "candidate-current"
        )
        current["recipe_release_id"] = recipe["recipe_release_id"]
        current["source_series_snapshot"]["scope"][
            "recipe_release_id"
        ] = recipe["recipe_release_id"]
        inputs["expected_trial_registry_hash"] = (
            statistical_trial_registry_hash(inputs["trial_registry"])
        )

        experiment["economics"].update(
            {
                "approved_production_capital_usdt": "500",
                "evaluation_window_start": inputs["scope"][
                    "evaluation_window_start"
                ],
                "evaluation_window_end": inputs["scope"][
                    "evaluation_window_end"
                ],
                "minimum_economic_effect": inputs["design"][
                    "minimum_economic_effect"
                ],
                "maximum_ci_width": "25",
                "trial_family_id": inputs["trial_family_id"],
            }
        )
        experiment["search_budget"].update(
            {
                "actual_total_trials": len(inputs["trial_registry"]),
                "aborted_trials": 1,
                "failed_trials": 0,
                "invalid_trials": 0,
                "trial_registry_hash": inputs[
                    "expected_trial_registry_hash"
                ],
            }
        )
        experiment_hash = experiment_manifest_hash(experiment)
        experiment["experiment_manifest_hash"] = experiment_hash

        recipe["experiment_manifest_hash"] = experiment_hash
        recipe["recipe_release_hash"] = artifact_self_hash(
            recipe,
            "recipe_release_hash",
            "freeze_attestation",
        )
        experiment["recipe_binding"]["recipe_release_hash"] = recipe[
            "recipe_release_hash"
        ]
        experiment["recipe_binding"]["recipe_binding_hash"] = (
            experiment_recipe_binding_hash(experiment)
        )

        deployment["experiment_manifest_hash"] = experiment_hash
        deployment["recipe_release_hash"] = recipe["recipe_release_hash"]
        deployment["current_stage"] = "RECIPE_CANDIDATE"
        deployment["stage_history"] = [
            {
                "stage": "RECIPE_CANDIDATE",
                "entered_at": "2025-01-01T00:00:00Z",
                "exited_at": None,
                "result": "IN_PROGRESS",
                "evidence_hash": None,
            }
        ]
        deployment["deployment_line_hash"] = deployment_line_hash(deployment)

        current["recipe_release_hash"] = recipe["recipe_release_hash"]
        current["source_series_snapshot"]["scope"][
            "recipe_release_hash"
        ] = recipe["recipe_release_hash"]
        for item in inputs["trial_registry"]:
            source = item["source_series_snapshot"]
            if source is None:
                continue
            source["experiment_manifest_id"] = experiment["experiment_id"]
            source["experiment_manifest_hash"] = experiment_hash
            source["statistical_design_policy_id"] = (
                "approved:statistical_design_policy_id"
            )
            source["statistical_design_policy_hash"] = evidence[
                "policy_binding_hashes"
            ]["statistical_design_policy_id"]
            source["scope"]["deployment_line_id"] = deployment[
                "deployment_line_id"
            ]
            source["scope"]["deployment_line_hash"] = deployment[
                "deployment_line_hash"
            ]
            source["approved_production_capital_usdt"] = "500"
            source["series_hash"] = statistical_series_hash(source)
            item["source_series_hash"] = source["series_hash"]

        inputs["scope"].update(
            {
                "deployment_line_id": deployment["deployment_line_id"],
                "deployment_line_hash": deployment["deployment_line_hash"],
                "approved_production_capital_usdt": "500",
            }
        )
        snapshot = build_statistical_decision_snapshot(
            snapshot_id="statistical-decision-complete-evidence",
            release_gate_policy_id=bundle.policy["policy_id"],
            release_gate_policy_version=bundle.policy["policy_version"],
            metric_catalog_id=bundle.catalog["catalog_id"],
            metric_catalog_version=bundle.catalog["catalog_version"],
            statistical_design_policy_id=(
                "approved:statistical_design_policy_id"
            ),
            statistical_design_policy_hash=evidence[
                "policy_binding_hashes"
            ]["statistical_design_policy_id"],
            experiment_manifest_id=experiment["experiment_id"],
            experiment_manifest_hash=experiment_hash,
            generated_at=inputs["scope"]["evaluation_window_end"],
            **inputs,
        )

        gate = next(
            item
            for item in bundle.policy["gates"]["SAMPLE"]
            if item["gate_id"] == "HOLM_ADJUSTED_PRIMARY_PASS"
        )
        definition = bundle.metrics.resolve(gate["metric_id"])
        evidence.update(
            {
                "evidence_id": "evidence-holm-adjusted-primary-pass",
                "gate_group_id": "SAMPLE",
                "gate_id": gate["gate_id"],
                "metric_id": gate["metric_id"],
                "estimator_id": definition["estimator_id"],
                "metric_unit": definition["unit"],
                "evaluation_ledger": inputs["scope"]["evaluation_ledger"],
                "recipe_release_id": recipe["recipe_release_id"],
                "recipe_release_hash": recipe["recipe_release_hash"],
                "experiment_manifest_id": experiment["experiment_id"],
                "experiment_manifest_hash": experiment_hash,
                "deployment_line_id": deployment["deployment_line_id"],
                "deployment_line_hash": deployment["deployment_line_hash"],
                "stage": "OFFLINE_OOS",
                "evaluation_window_start": inputs["scope"][
                    "evaluation_window_start"
                ],
                "evaluation_window_end": inputs["scope"][
                    "evaluation_window_end"
                ],
                "approved_production_capital_usdt": "500",
                "metric_value": True,
                "comparator": "EQ",
                "threshold_snapshot": True,
                "result": "PASS",
                "sample_status": {
                    "raw_event_count": 6,
                    "effective_event_count": 2,
                    "sufficient": True,
                },
                "artifact_hashes": [
                    evidence["frozen_release_inputs"][
                        "approved_capital_and_break_even_plan"
                    ]["artifact_hash"],
                    snapshot["snapshot_hash"],
                    snapshot["trial_registry_hash"],
                    *[
                        item["source_series_hash"]
                        for item in snapshot["trial_registry"]
                        if item["candidate_status"] == "EVALUATED"
                    ],
                ],
            }
        )
        for name, document, artifact_id, artifact_hash in (
            (
                "recipe_release",
                recipe,
                recipe["recipe_release_id"],
                recipe["recipe_release_hash"],
            ),
            (
                "experiment_manifest",
                experiment,
                experiment["experiment_id"],
                experiment_hash,
            ),
        ):
            proof = evidence["frozen_release_inputs"][name]
            proof["artifact_id"] = artifact_id
            proof["artifact_hash"] = artifact_hash
        decision_freeze_hash = digest("freeze:statistical-decision")
        decision_signature_hash = digest(
            "signature:statistical-decision"
        )
        evidence["frozen_release_inputs"][
            "statistical_decision_snapshot"
        ] = {
            "schema_id": "statistical-decision-snapshot-v1.schema.json",
            "artifact_id": snapshot["snapshot_id"],
            "artifact_hash": snapshot["snapshot_hash"],
            "frozen_at": "2025-12-31T23:59:58Z",
            "freeze_evidence_hash": decision_freeze_hash,
            "signer_id": "release-authority",
            "signature_hash": decision_signature_hash,
        }
        evidence["evidence_hash"] = gate_evidence_hash(evidence)

        artifact_hashes = {
            **trust.artifact_hashes,
            "recipe_release": recipe["recipe_release_hash"],
            "experiment_manifest": experiment_hash,
            "statistical_decision_snapshot": snapshot["snapshot_hash"],
        }
        freeze_evidence = dict(trust.verified_freeze_evidence)
        for name in ("recipe_release", "experiment_manifest"):
            proof = evidence["frozen_release_inputs"][name]
            freeze_evidence[proof["freeze_evidence_hash"]] = proof[
                "artifact_hash"
            ]
        freeze_evidence[decision_freeze_hash] = snapshot["snapshot_hash"]
        signatures = dict(trust.verified_signatures)
        signatures[decision_signature_hash] = decision_freeze_hash
        attestations = dict(trust.verified_artifact_attestations)
        attestations[
            recipe["freeze_attestation"]["attestation_hash"]
        ] = recipe["recipe_release_hash"]
        attestations[
            experiment["manifest_attestation"]["signature_base64"]
        ] = experiment["recipe_binding"]["recipe_binding_hash"]
        attestations[
            deployment["line_attestation"]["signature_base64"]
        ] = deployment["deployment_line_hash"]
        trust = replace(
            trust,
            artifact_hashes=artifact_hashes,
            verified_signatures=signatures,
            verified_freeze_evidence=freeze_evidence,
            verified_artifact_attestations=attestations,
            artifact_documents={
                **trust.artifact_documents,
                "recipe_release": recipe,
                "experiment_manifest": experiment,
                "deployment_line": deployment,
                "statistical_decision_snapshot": snapshot,
            },
        )
        scope = bundle.evidence_scope_snapshot(evidence)
        return bundle, evidence, scope, trust, snapshot

    def test_complete_statistical_decision_gate_evidence_validates(self):
        bundle, evidence, scope, trust, _ = (
            self.complete_statistical_gate_fixture()
        )

        result = bundle.validate_gate_evidence(
            "SAMPLE",
            evidence,
            expected_scope=scope,
            trust=trust,
        )

        self.assertTrue(result.valid, result.reason_codes)
        self.assertEqual(result.computed_gate_result, "PASS")

        missing_freeze = deepcopy(evidence)
        del missing_freeze["frozen_release_inputs"][
            "statistical_decision_snapshot"
        ]
        self.assertTrue(bundle.evidence_schema_errors(missing_freeze))

    def test_supporting_observation_requires_complete_statistical_family_sources(
        self,
    ):
        bundle, evidence, scope, trust, snapshot = (
            self.complete_statistical_gate_fixture()
        )
        definition = bundle.metrics.resolve(evidence["metric_id"])
        inputs = {"statistical_decision_snapshot": snapshot}
        execution = bundle.estimators.execute(
            definition["estimator_id"],
            inputs,
        )
        observation = {
            "observation_id": "supporting-statistical-decision",
            "observation_hash": "0" * 64,
            "metric_id": evidence["metric_id"],
            "metric_unit": definition["unit"],
            "estimator_id": definition["estimator_id"],
            "implementation_id": execution.implementation_id,
            "implementation_version": execution.implementation_version,
            "estimator_inputs": inputs,
            "status": execution.status,
            "value": execution.value,
            "reason_codes": list(execution.reason_codes),
            "estimator_execution_hash": execution.execution_hash,
            "source_artifact_hashes": [
                snapshot["snapshot_hash"],
                snapshot["trial_registry_hash"],
                *[
                    item["source_series_hash"]
                    for item in snapshot["trial_registry"]
                    if item["candidate_status"] == "EVALUATED"
                ],
            ],
        }
        observation["observation_hash"] = supporting_observation_hash(
            observation
        )
        signature = "F" * 86 + "=="
        supporting = {
            "$schema": "./supporting-observation-bundle-v1.schema.json",
            "schema_version": "1.0.0",
            "bundle_id": "supporting-statistical-decision-bundle",
            "bundle_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "scope_hash": business_hash(scope),
            "policy_bundle_hash": evidence["policy_bundle_hash"],
            "evaluator_build_hash": bundle.evaluator_build.build_hash,
            "computed_at": "2026-01-01T00:00:01Z",
            "observations": [observation],
            "bundle_attestation": {
                "algorithm": "ED25519",
                "key_id": "observation-authority",
                "signed_at": "2026-01-01T00:00:02Z",
                "signature_base64": signature,
            },
        }
        supporting["bundle_hash"] = supporting_observation_bundle_hash(
            supporting
        )
        evidence["supporting_observation_bundle_schema_id"] = (
            "supporting-observation-bundle-v1.schema.json"
        )
        evidence["supporting_observation_bundle_id"] = supporting[
            "bundle_id"
        ]
        evidence["supporting_observation_bundle_hash"] = supporting[
            "bundle_hash"
        ]
        evidence["evidence_hash"] = gate_evidence_hash(evidence)
        trust = replace(
            trust,
            verified_artifact_attestations={
                **trust.verified_artifact_attestations,
                signature: supporting["bundle_hash"],
            },
        )

        valid = bundle.validate_gate_evidence(
            "SAMPLE",
            evidence,
            expected_scope=scope,
            trust=trust,
            supporting_observation_bundle=supporting,
        )
        self.assertTrue(valid.valid, valid.reason_codes)

        tampered = deepcopy(supporting)
        tampered_observation = tampered["observations"][0]
        tampered_observation["source_artifact_hashes"].remove(
            next(
                item["source_series_hash"]
                for item in snapshot["trial_registry"]
                if item["candidate_id"] == "candidate-current"
            )
        )
        tampered_observation["observation_hash"] = (
            supporting_observation_hash(tampered_observation)
        )
        tampered["bundle_hash"] = supporting_observation_bundle_hash(
            tampered
        )
        tampered_evidence = deepcopy(evidence)
        tampered_evidence["supporting_observation_bundle_hash"] = tampered[
            "bundle_hash"
        ]
        tampered_evidence["evidence_hash"] = gate_evidence_hash(
            tampered_evidence
        )
        tampered_trust = replace(
            trust,
            verified_artifact_attestations={
                **trust.verified_artifact_attestations,
                signature: tampered["bundle_hash"],
            },
        )
        rejected = bundle.validate_gate_evidence(
            "SAMPLE",
            tampered_evidence,
            expected_scope=scope,
            trust=tampered_trust,
            supporting_observation_bundle=tampered,
        )

        self.assertIn(
            "SUPPORTING_STATISTICAL_DECISION_SOURCE_MISSING:"
            "primary_endpoint_holm_adjusted_pass",
            rejected.reason_codes,
        )

    def test_statistical_decision_estimator_route_uses_trusted_snapshot(self):
        snapshot, evidence, _ = self.statistical_reference_fixture()
        evidence["claimed_achieved_power"] = "1"

        inputs = self.bundle._estimator_inputs(
            "ACHIEVED_POWER_AT_MERE_V1",
            "achieved_power_at_minimum_economic_effect",
            evidence,
            scope_verified=True,
            trust_verified=True,
            statistical_decision_snapshot=snapshot,
        )
        execution = self.bundle.estimators.execute(
            "ACHIEVED_POWER_AT_MERE_V1",
            inputs,
        )

        self.assertEqual(
            inputs,
            {"statistical_decision_snapshot": snapshot},
        )
        self.assertEqual(execution.status, "COMPUTED")
        self.assertEqual(execution.value, "0.031")

    def test_statistical_decision_reference_binds_all_sources_and_sample(self):
        snapshot, evidence, trust = self.statistical_reference_fixture()

        self.assertEqual(
            self.bundle._statistical_decision_reference_reasons(
                evidence,
                trust,
            ),
            (),
        )

        cases = []
        missing_document = replace(
            trust,
            artifact_documents={
                "experiment_manifest": trust.artifact_documents[
                    "experiment_manifest"
                ]
            },
        )
        cases.append(
            (
                evidence,
                missing_document,
                "STATISTICAL_DECISION_DOCUMENT_MISSING",
            )
        )
        wrong_freeze = deepcopy(evidence)
        wrong_freeze["frozen_release_inputs"][
            "statistical_decision_snapshot"
        ]["artifact_id"] = "other-snapshot"
        cases.append(
            (
                wrong_freeze,
                trust,
                "STATISTICAL_DECISION_FREEZE_ID_MISMATCH",
            )
        )
        wrong_scope = deepcopy(evidence)
        wrong_scope["evaluation_window_end"] = "2025-01-06T00:00:00Z"
        cases.append(
            (
                wrong_scope,
                trust,
                "STATISTICAL_DECISION_SCOPE_MISMATCH:"
                "evaluation_window_end",
            )
        )
        wrong_recipe = deepcopy(evidence)
        wrong_recipe["recipe_release_hash"] = "f" * 64
        cases.append(
            (
                wrong_recipe,
                trust,
                "STATISTICAL_DECISION_RECIPE_MISMATCH",
            )
        )
        wrong_manifest = deepcopy(
            trust.artifact_documents["experiment_manifest"]
        )
        wrong_manifest["search_budget"]["actual_total_trials"] = 2
        cases.append(
            (
                evidence,
                replace(
                    trust,
                    artifact_documents={
                        **trust.artifact_documents,
                        "experiment_manifest": wrong_manifest,
                    },
                ),
                "STATISTICAL_DECISION_TRIAL_COUNT_MISMATCH",
            )
        )
        missing_source = deepcopy(evidence)
        missing_source["artifact_hashes"].remove(
            next(
                item["source_series_hash"]
                for item in snapshot["trial_registry"]
                if item["candidate_id"] == "candidate-current"
            )
        )
        cases.append(
            (
                missing_source,
                trust,
                "STATISTICAL_DECISION_SOURCE_HASH_MISSING:"
                "candidate-current",
            )
        )
        wrong_sample = deepcopy(evidence)
        wrong_sample["sample_status"]["effective_event_count"] = 3
        cases.append(
            (
                wrong_sample,
                trust,
                "STATISTICAL_DECISION_SAMPLE_ESS_MISMATCH",
            )
        )
        wrong_policy = deepcopy(snapshot)
        wrong_policy["release_gate_policy_version"] = "9.9.9"
        wrong_policy["snapshot_hash"] = statistical_decision_snapshot_hash(
            wrong_policy
        )
        cases.append(
            (
                evidence,
                replace(
                    trust,
                    artifact_hashes={
                        "statistical_decision_snapshot": wrong_policy[
                            "snapshot_hash"
                        ]
                    },
                    artifact_documents={
                        **trust.artifact_documents,
                        "statistical_decision_snapshot": wrong_policy,
                    },
                ),
                "STATISTICAL_DECISION_POLICY_IDENTITY_MISMATCH",
            )
        )

        for candidate_evidence, candidate_trust, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(
                    expected,
                    self.bundle._statistical_decision_reference_reasons(
                        candidate_evidence,
                        candidate_trust,
                    ),
                )

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

    def test_metric_value_must_match_independent_estimator_execution(self):
        bundle, envelopes, scope, trust = self.fixture()
        evidence = deepcopy(envelopes[1])
        evidence["metric_value"] = "999"
        evidence["evidence_hash"] = gate_evidence_hash(evidence)

        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            evidence,
            expected_scope=scope,
            trust=trust,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.computed_gate_result, "PASS")
        self.assertIn("EVIDENCE_METRIC_VALUE_MISMATCH", result.reason_codes)
        self.assertTrue(result.estimator_execution_hash)

    def supporting_bundle(self, bundle, evidence, scope, trust):
        definition = bundle.metrics.resolve(evidence["metric_id"])
        execution = bundle.estimators.execute(
            definition["estimator_id"],
            {
                "actual_deployable_capital_usdt": (
                    evidence["actual_deployable_capital_usdt"]
                ),
                "snapshot_verified": True,
            },
        )
        observation = {
            "observation_id": "supporting-observation-1",
            "observation_hash": "0" * 64,
            "metric_id": evidence["metric_id"],
            "metric_unit": definition["unit"],
            "estimator_id": definition["estimator_id"],
            "implementation_id": execution.implementation_id,
            "implementation_version": execution.implementation_version,
            "estimator_inputs": {
                "actual_deployable_capital_usdt": (
                    evidence["actual_deployable_capital_usdt"]
                ),
                "snapshot_verified": True,
            },
            "status": execution.status,
            "value": execution.value,
            "reason_codes": list(execution.reason_codes),
            "estimator_execution_hash": execution.execution_hash,
            "source_artifact_hashes": [
                trust.artifact_hashes[
                    "approved_capital_and_break_even_plan"
                ]
            ],
        }
        observation["observation_hash"] = supporting_observation_hash(
            observation
        )
        supporting = {
            "$schema": "./supporting-observation-bundle-v1.schema.json",
            "schema_version": "1.0.0",
            "bundle_id": "supporting-bundle-1",
            "bundle_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "scope_hash": business_hash(scope),
            "policy_bundle_hash": evidence["policy_bundle_hash"],
            "evaluator_build_hash": bundle.evaluator_build.build_hash,
            "computed_at": "2026-01-01T00:00:01Z",
            "observations": [observation],
            "bundle_attestation": {
                "algorithm": "ED25519",
                "key_id": "evaluator-authority",
                "signed_at": "2026-01-01T00:00:02Z",
                "signature_base64": "F" * 86 + "==",
            },
        }
        supporting["bundle_hash"] = supporting_observation_bundle_hash(
            supporting
        )
        return supporting

    def test_supporting_observation_requires_frozen_reexecution_bundle(self):
        bundle, envelopes, scope, trust = self.fixture()
        evidence = deepcopy(envelopes[1])
        supporting = self.supporting_bundle(
            bundle,
            evidence,
            scope,
            trust,
        )
        evidence.update(
            {
                "supporting_observation_bundle_schema_id": (
                    "supporting-observation-bundle-v1.schema.json"
                ),
                "supporting_observation_bundle_id": supporting["bundle_id"],
                "supporting_observation_bundle_hash": supporting[
                    "bundle_hash"
                ],
            }
        )
        evidence["evidence_hash"] = gate_evidence_hash(evidence)
        trusted = replace(
            trust,
            verified_artifact_attestations={
                **trust.verified_artifact_attestations,
                supporting["bundle_attestation"]["signature_base64"]: (
                    supporting["bundle_hash"]
                ),
            },
        )

        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            evidence,
            expected_scope=scope,
            trust=trusted,
            supporting_observation_bundle=supporting,
        )

        self.assertTrue(result.valid, result.reason_codes)
        self.assertTrue(result.supporting_observation_validation_hash)

        tampered = deepcopy(supporting)
        tampered["observations"][0]["value"] = "999"
        tampered["observations"][0]["observation_hash"] = (
            supporting_observation_hash(tampered["observations"][0])
        )
        tampered["bundle_hash"] = supporting_observation_bundle_hash(tampered)
        evidence["supporting_observation_bundle_hash"] = tampered[
            "bundle_hash"
        ]
        evidence["evidence_hash"] = gate_evidence_hash(evidence)
        tamper_trusted = replace(
            trust,
            verified_artifact_attestations={
                **trust.verified_artifact_attestations,
                tampered["bundle_attestation"]["signature_base64"]: (
                    tampered["bundle_hash"]
                ),
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            evidence,
            expected_scope=scope,
            trust=tamper_trusted,
            supporting_observation_bundle=tampered,
        )
        self.assertFalse(result.valid)
        self.assertTrue(
            any(
                reason.startswith(
                    "SUPPORTING_ESTIMATOR_RESULT_MISMATCH:"
                )
                for reason in result.reason_codes
            )
        )

    def test_raw_supporting_observation_mapping_is_never_trusted(self):
        bundle, envelopes, scope, trust = self.fixture()
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[1],
            expected_scope=scope,
            trust=trust,
            supporting_observations={
                "approved_production_capital_usdt": "1"
            },
        )
        self.assertFalse(result.valid)
        self.assertIn(
            "RAW_SUPPORTING_OBSERVATIONS_FORBIDDEN",
            result.reason_codes,
        )

    def test_experiment_binding_and_deployment_sequence_fail_closed(self):
        bundle, envelopes, scope, trust = self.fixture()
        source = envelopes[1]

        experiment = deepcopy(
            trust.artifact_documents["experiment_manifest"]
        )
        experiment["recipe_binding"]["recipe_release_hash"] = digest(
            "other-recipe"
        )
        changed_experiment = replace(
            trust,
            artifact_documents={
                **trust.artifact_documents,
                "experiment_manifest": experiment,
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            source,
            expected_scope=scope,
            trust=changed_experiment,
        )
        self.assertIn(
            "EXPERIMENT_RECIPE_BINDING_HASH_MISMATCH",
            result.reason_codes,
        )
        self.assertIn(
            "EXPERIMENT_RECIPE_REFERENCE_MISMATCH:recipe_release_hash",
            result.reason_codes,
        )

        line = deepcopy(trust.artifact_documents["deployment_line"])
        del line["stage_history"][1]
        line["deployment_line_hash"] = deployment_line_hash(line)
        changed_evidence = deepcopy(source)
        changed_evidence["deployment_line_hash"] = line[
            "deployment_line_hash"
        ]
        changed_evidence["evidence_hash"] = gate_evidence_hash(
            changed_evidence
        )
        line_signature = line["line_attestation"]["signature_base64"]
        changed_line = replace(
            trust,
            verified_artifact_attestations={
                **trust.verified_artifact_attestations,
                line_signature: line["deployment_line_hash"],
            },
            artifact_documents={
                **trust.artifact_documents,
                "deployment_line": line,
            },
        )
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            changed_evidence,
            expected_scope=scope,
            trust=changed_line,
        )
        self.assertIn(
            "DEPLOYMENT_LINE_STAGE_SEQUENCE_INVALID",
            result.reason_codes,
        )

    def test_catalog_algorithm_without_implementation_cannot_validate(self):
        bundle, envelopes, _, trust = self.fixture()
        catalog = deepcopy(bundle.catalog)
        metric_id = envelopes[1]["metric_id"]
        catalog["exact_overrides"][metric_id]["estimator_id"] = (
            "DEFLATED_SHARPE_CONFIDENCE_V1"
        )
        unavailable_bundle = PolicyBundle(
            root=bundle.root,
            policy=deepcopy(bundle.policy),
            catalog=catalog,
            evidence_schema=deepcopy(bundle.evidence_schema),
            estimators=bundle.estimators,
            evaluator_build=bundle.evaluator_build,
        )
        evidence = deepcopy(envelopes[1])
        evidence["estimator_id"] = "DEFLATED_SHARPE_CONFIDENCE_V1"
        evidence["evidence_hash"] = gate_evidence_hash(evidence)
        expected_scope = unavailable_bundle.evidence_scope_snapshot(evidence)

        result = unavailable_bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            evidence,
            expected_scope=expected_scope,
            trust=trust,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.computed_gate_result, "FAIL")
        self.assertIn(
            "ESTIMATOR_EXECUTION:ESTIMATOR_NOT_EXECUTABLE",
            result.reason_codes,
        )

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

        wrong_line_scope = deepcopy(scope)
        wrong_line_scope["deployment_line_hash"] = digest("old-line")
        result = bundle.validate_gate_evidence(
            "CAPITAL_READINESS",
            envelopes[0],
            expected_scope=wrong_line_scope,
            trust=trust,
        )
        self.assertIn(
            "SCOPE_VALUE_MISMATCH:deployment_line_hash",
            result.reason_codes,
        )

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
