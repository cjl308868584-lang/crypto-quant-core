"""GateEvidence hashing and external trust-proof verification."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Tuple

from .canonical import business_hash
from .errors import CanonicalizationError


@dataclass(frozen=True)
class EvidenceTrustContext:
    """Results supplied by trusted artifact and signature verifiers.

    The release evaluator compares these results byte-for-byte. It never treats
    the mere presence of a signature hash as proof that a signature was valid.
    """

    policy_bundle_hash: str
    binding_ids: Mapping[str, str]
    binding_hashes: Mapping[str, str]
    artifact_hashes: Mapping[str, str]
    capital_values: Mapping[str, Any]
    verified_signatures: Mapping[str, str] = field(default_factory=dict)
    verified_freeze_evidence: Mapping[str, str] = field(
        default_factory=dict
    )
    verified_reveal_events: Mapping[str, str] = field(
        default_factory=dict
    )
    verified_fallback_signatures: Mapping[str, str] = field(
        default_factory=dict
    )
    verified_artifact_attestations: Mapping[str, str] = field(
        default_factory=dict
    )
    artifact_documents: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class EvidenceValidation:
    evidence_id: str
    gate_id: str
    valid: bool
    computed_gate_result: str
    estimator_execution_hash: str
    computed_evidence_hash: str
    reason_codes: Tuple[str, ...]
    validation_hash: str


@dataclass(frozen=True)
class EvidenceGroupValidation:
    gate_group_id: str
    result: str
    evidence_results: Tuple[EvidenceValidation, ...]
    reason_codes: Tuple[str, ...]
    result_hash: str


def gate_evidence_hash(evidence: Mapping[str, Any]) -> str:
    """Hash a GateEvidence envelope excluding only its self-hash field."""

    body = dict(evidence)
    body.pop("evidence_hash", None)
    return business_hash(body)


def artifact_self_hash(
    artifact: Mapping[str, Any],
    hash_field: str,
    *signature_fields: str,
) -> str:
    """Hash an immutable artifact without its self-hash or signatures."""

    body = dict(artifact)
    body.pop(hash_field, None)
    for field_name in signature_fields:
        body.pop(field_name, None)
    return business_hash(body)


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone-aware")
    return parsed


def verify_trust_context(
    evidence: Mapping[str, Any],
    trust: EvidenceTrustContext,
) -> Tuple[str, ...]:
    """Verify frozen inputs against independent resolver/verifier outputs."""

    reasons = []
    try:
        computed_hash = gate_evidence_hash(evidence)
    except CanonicalizationError:
        computed_hash = ""
        reasons.append("EVIDENCE_NOT_CANONICAL")
    if evidence.get("evidence_hash") != computed_hash:
        reasons.append("EVIDENCE_HASH_MISMATCH")

    if evidence.get("policy_bundle_hash") != trust.policy_bundle_hash:
        reasons.append("POLICY_BUNDLE_HASH_MISMATCH")

    claimed_bindings = evidence.get("policy_binding_hashes")
    if not isinstance(claimed_bindings, Mapping):
        reasons.append("POLICY_BINDING_HASHES_MISSING")
        claimed_bindings = {}
    claimed_keys = set(claimed_bindings)
    trusted_keys = set(trust.binding_hashes)
    for name in sorted(trusted_keys - claimed_keys):
        reasons.append(f"POLICY_BINDING_HASH_MISSING:{name}")
    for name in sorted(claimed_keys - trusted_keys):
        reasons.append(f"POLICY_BINDING_HASH_UNEXPECTED:{name}")
    for name in sorted(claimed_keys & trusted_keys):
        if claimed_bindings[name] != trust.binding_hashes[name]:
            reasons.append(f"POLICY_BINDING_HASH_MISMATCH:{name}")

    frozen_inputs = evidence.get("frozen_release_inputs")
    if not isinstance(frozen_inputs, Mapping):
        reasons.append("FROZEN_RELEASE_INPUTS_MISSING")
        frozen_inputs = {}
    proof_keys = set(frozen_inputs)
    resolved_keys = set(trust.artifact_hashes)
    for name in sorted(proof_keys - resolved_keys):
        reasons.append(f"RESOLVED_ARTIFACT_HASH_MISSING:{name}")
    for name in sorted(resolved_keys - proof_keys):
        reasons.append(f"RESOLVED_ARTIFACT_HASH_UNEXPECTED:{name}")

    try:
        reveal_at = _timestamp(evidence.get("first_result_revealed_at"))
    except (TypeError, ValueError):
        reveal_at = None
        reasons.append("FIRST_RESULT_REVEAL_TIME_INVALID")

    for name in sorted(proof_keys):
        proof = frozen_inputs[name]
        if not isinstance(proof, Mapping):
            reasons.append(f"FREEZE_PROOF_INVALID:{name}")
            continue
        if (
            name in trust.artifact_hashes
            and proof.get("artifact_hash") != trust.artifact_hashes[name]
        ):
            reasons.append(f"FROZEN_ARTIFACT_HASH_MISMATCH:{name}")
        signature_hash = proof.get("signature_hash")
        freeze_evidence_hash = proof.get("freeze_evidence_hash")
        if trust.verified_signatures.get(signature_hash) != freeze_evidence_hash:
            reasons.append(f"FREEZE_SIGNATURE_UNVERIFIED:{name}")
        if (
            trust.verified_freeze_evidence.get(freeze_evidence_hash)
            != proof.get("artifact_hash")
        ):
            reasons.append(f"FREEZE_EVIDENCE_UNVERIFIED:{name}")
        try:
            frozen_at = _timestamp(proof.get("frozen_at"))
        except (TypeError, ValueError):
            reasons.append(f"FREEZE_TIME_INVALID:{name}")
            continue
        if reveal_at is not None:
            if frozen_at > reveal_at:
                reasons.append(f"FREEZE_AFTER_RESULT_REVEAL:{name}")
            elif frozen_at == reveal_at:
                reasons.append(f"FREEZE_REVEAL_ORDER_UNPROVEN:{name}")

    reveal_event_id = evidence.get("first_result_reveal_event_id")
    reveal_hash = evidence.get("first_result_reveal_evidence_hash")
    if trust.verified_reveal_events.get(reveal_event_id) != reveal_hash:
        reasons.append("FIRST_RESULT_REVEAL_EVIDENCE_UNVERIFIED")

    try:
        computed_at = _timestamp(evidence.get("computed_at"))
    except (TypeError, ValueError):
        computed_at = None
        reasons.append("EVIDENCE_COMPUTED_TIME_INVALID")
    if (
        reveal_at is not None
        and computed_at is not None
        and computed_at < reveal_at
    ):
        reasons.append("EVIDENCE_COMPUTED_BEFORE_RESULT_REVEAL")

    try:
        window_start = _timestamp(evidence.get("evaluation_window_start"))
        window_end = _timestamp(evidence.get("evaluation_window_end"))
        if window_end <= window_start:
            reasons.append("EVALUATION_WINDOW_NOT_INCREASING")
    except (TypeError, ValueError):
        reasons.append("EVALUATION_WINDOW_INVALID")

    capital_fields = (
        "approved_production_capital_usdt",
        "actual_deployable_capital_usdt",
        "break_even_capital_lcb_root_usdt",
    )
    expected_capital_keys = set(capital_fields)
    trusted_capital_keys = set(trust.capital_values)
    for name in sorted(expected_capital_keys - trusted_capital_keys):
        reasons.append(f"FROZEN_CAPITAL_VALUE_MISSING:{name}")
    for name in sorted(trusted_capital_keys - expected_capital_keys):
        reasons.append(f"FROZEN_CAPITAL_VALUE_UNEXPECTED:{name}")
    for name in sorted(expected_capital_keys & trusted_capital_keys):
        if evidence.get(name) != trust.capital_values[name]:
            reasons.append(f"FROZEN_CAPITAL_VALUE_MISMATCH:{name}")

    capital_plan = frozen_inputs.get("approved_capital_and_break_even_plan")
    artifact_hashes = evidence.get("artifact_hashes")
    if (
        isinstance(capital_plan, Mapping)
        and isinstance(artifact_hashes, list)
        and capital_plan.get("artifact_hash") not in artifact_hashes
    ):
        reasons.append("CAPITAL_PLAN_HASH_MISSING_FROM_ARTIFACTS")

    if evidence.get("fallback_activation_requested") is True:
        fallback_signature = evidence.get(
            "approved_fallback_registry_signature_hash"
        )
        fallback_evidence = evidence.get(
            "approved_fallback_registry_evidence_hash"
        )
        if (
            trust.verified_fallback_signatures.get(fallback_signature)
            != fallback_evidence
        ):
            reasons.append("FALLBACK_SIGNATURE_UNVERIFIED")

    return tuple(sorted(set(reasons)))
