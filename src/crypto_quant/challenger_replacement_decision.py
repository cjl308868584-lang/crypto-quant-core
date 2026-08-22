"""Pure replacement Challenger decision semantics with no runtime authority."""

import json
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from decimal import Context, Decimal, InvalidOperation, localcontext
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal, stable_id, utc_datetime
from .challenger_replacement_plan_v2 import challenger_replacement_plan_v2_reasons
from .evidence import artifact_self_hash


_ZERO_HASH = "0" * 64
_FOUR_HOURS = timedelta(hours=4)
_CONTEXT = Context(prec=50)
_QUALIFICATION = "TEST_FIXTURE_ONLY_NOT_COHORT_EVIDENCE"
_COHORT_QUALIFICATION = "REPLACEMENT_CONFIRMATORY_COHORT_EVIDENCE"


class ChallengerReplacementDecisionError(ValueError):
    """The replacement decision failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _cohort_decision_validator():
    schema = json.loads(
        resources.files("crypto_quant")
        .joinpath("schemas", "challenger-replacement-decision-v2.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_challenger_replacement_cohort_decision(
    *, plan, source_bundle, recorded_at, previous_decision=None
):
    """Evaluate the frozen policy against one cohort-qualified v2 source."""

    if (
        not isinstance(source_bundle, Mapping)
        or source_bundle.get("$schema")
        != "./challenger-replacement-source-bundle-v2.schema.json"
        or source_bundle.get("evidence_qualification") != _COHORT_QUALIFICATION
        or source_bundle.get("bundle_hash")
        != artifact_self_hash(source_bundle, "bundle_hash")
        or source_bundle.get("live_capture_receipt", {}).get("rows")
        != source_bundle.get("klines")
        or source_bundle.get("network_request_count_observed_by_core_runtime") != 0
    ):
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_SOURCE_INVALID"
        )
    if previous_decision is None:
        fixture_previous = None
        previous_decision_hash = None
    elif (
        isinstance(previous_decision, Mapping)
        and previous_decision.get("$schema")
        == "./challenger-replacement-decision-v2.schema.json"
        and previous_decision.get("evidence_qualification")
        == _COHORT_QUALIFICATION
        and previous_decision.get("decision_hash")
        == artifact_self_hash(previous_decision, "decision_hash")
        and source_bundle.get("parents", {}).get(
            "previous_decision_hash_or_null"
        )
        == previous_decision.get("decision_hash")
    ):
        previous_decision_hash = previous_decision["decision_hash"]
        fixture_previous = deepcopy(dict(previous_decision))
        fixture_previous["$schema"] = (
            "./challenger-replacement-decision-v1.schema.json"
        )
        fixture_previous["schema_version"] = "1.0.0"
        fixture_previous["evidence_qualification"] = _QUALIFICATION
        fixture_previous["decision_hash"] = artifact_self_hash(
            fixture_previous, "decision_hash"
        )
    else:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_PREVIOUS_INVALID"
        )
    fixture_source = deepcopy(dict(source_bundle))
    fixture_source.pop("live_capture_receipt")
    fixture_source.pop("network_request_count_observed_by_core_runtime")
    fixture_source["$schema"] = "./challenger-replacement-source-bundle-v1.schema.json"
    fixture_source["schema_version"] = "1.0.0"
    fixture_source["evidence_qualification"] = _QUALIFICATION
    fixture_source["parents"]["previous_decision_hash_or_null"] = (
        None if fixture_previous is None else fixture_previous["decision_hash"]
    )
    fixture_source["bundle_hash"] = artifact_self_hash(
        fixture_source, "bundle_hash"
    )
    decision = build_challenger_replacement_decision(
        plan=plan,
        source_bundle=fixture_source,
        recorded_at=recorded_at,
        previous_decision=fixture_previous,
    )
    decision["$schema"] = "./challenger-replacement-decision-v2.schema.json"
    decision["schema_version"] = "2.0.0"
    decision["evidence_qualification"] = _COHORT_QUALIFICATION
    decision["parents"]["current_source_bundle_hash"] = source_bundle["bundle_hash"]
    decision["parents"]["previous_decision_hash_or_null"] = previous_decision_hash
    identity = {
        "plan_hash": plan["plan_hash"],
        "slot_id": source_bundle["slot"]["slot_id"],
        "sequence": source_bundle["slot"]["sequence"],
        "current_source_bundle_hash": source_bundle["bundle_hash"],
        "previous_decision_hash_or_null": previous_decision_hash,
    }
    decision["decision_id"] = stable_id(
        "challenger_replacement_decision", identity
    )
    decision["decision_hash"] = artifact_self_hash(decision, "decision_hash")
    return decision


def _utc(value: object) -> Tuple[datetime, str]:
    if not isinstance(value, str):
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_TIME_INVALID"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_TIME_INVALID"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_TIME_INVALID"
        )
    return converted, utc_datetime(converted)


def _flat_state() -> Dict[str, Any]:
    return {
        "position_state": "FLAT",
        "episode_id_or_null": None,
        "entry_scheduled_for_or_null": None,
        "minimum_hold_until_or_null": None,
        "vertical_exit_at_or_null": None,
    }


def _long_state(*, plan_hash: str, policy_hash: str, scheduled: datetime) -> Dict[str, Any]:
    scheduled_text = utc_datetime(scheduled)
    episode_id = stable_id(
        "challenger_replacement_episode",
        {
            "plan_hash": plan_hash,
            "policy_hash": policy_hash,
            "entry_scheduled_for": scheduled_text,
        },
    )
    return {
        "position_state": "LONG",
        "episode_id_or_null": episode_id,
        "entry_scheduled_for_or_null": scheduled_text,
        "minimum_hold_until_or_null": utc_datetime(
            scheduled + timedelta(hours=8)
        ),
        "vertical_exit_at_or_null": utc_datetime(
            scheduled + timedelta(hours=24)
        ),
    }


def _state_valid(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "position_state",
        "episode_id_or_null",
        "entry_scheduled_for_or_null",
        "minimum_hold_until_or_null",
        "vertical_exit_at_or_null",
    }:
        return False
    if value["position_state"] == "FLAT":
        return all(
            value[name] is None
            for name in (
                "episode_id_or_null",
                "entry_scheduled_for_or_null",
                "minimum_hold_until_or_null",
                "vertical_exit_at_or_null",
            )
        )
    if value["position_state"] != "LONG":
        return False
    try:
        entry = _utc(value["entry_scheduled_for_or_null"])[0]
        minimum = _utc(value["minimum_hold_until_or_null"])[0]
        vertical = _utc(value["vertical_exit_at_or_null"])[0]
    except ChallengerReplacementDecisionError:
        return False
    episode_id = value["episode_id_or_null"]
    return (
        isinstance(episode_id, str)
        and episode_id.startswith("challenger_replacement_episode_")
        and len(episode_id) == len("challenger_replacement_episode_") + 64
        and minimum == entry + timedelta(hours=8)
        and vertical == entry + timedelta(hours=24)
    )


def _previous_valid(
    previous: object, *, plan: Mapping[str, Any], source_bundle: Mapping[str, Any]
) -> bool:
    if not isinstance(previous, Mapping):
        return False
    try:
        previous_scheduled = _utc(previous["slot"]["scheduled_for"])[0]
        current_scheduled = _utc(source_bundle["slot"]["scheduled_for"])[0]
        return (
            previous.get("decision_hash")
            == artifact_self_hash(previous, "decision_hash")
            and previous.get("plan")
            == {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]}
            and previous.get("policy_hash")
            == plan["decision_policy"]["policy_hash"]
            and previous.get("hypothesis_registration_hash")
            == plan["scope"]["hypothesis_registration_hash"]
            and previous.get("build_identity") == source_bundle.get("build_identity")
            and _state_valid(previous.get("state_after"))
            and source_bundle.get("slot", {}).get("sequence")
            == previous.get("slot", {}).get("sequence") + 1
            and current_scheduled == previous_scheduled + _FOUR_HOURS
            and source_bundle.get("parents", {}).get(
                "previous_decision_hash_or_null"
            )
            == previous.get("decision_hash")
            and source_bundle.get("parents", {}).get(
                "previous_source_bundle_hash"
            )
            == previous.get("parents", {}).get("current_source_bundle_hash")
        )
    except (KeyError, TypeError, ValueError, ChallengerReplacementDecisionError):
        return False


def build_challenger_replacement_decision(
    *,
    plan: Mapping[str, Any],
    source_bundle: Mapping[str, Any],
    recorded_at: str,
    previous_decision: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate one fixture-backed source bundle without I/O authority."""

    if not isinstance(plan, Mapping):
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_PLAN_INVALID"
        )
    reasons = challenger_replacement_plan_v2_reasons(plan)
    if reasons:
        raise ChallengerReplacementDecisionError(reasons[0])
    if not isinstance(source_bundle, Mapping):
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_SOURCE_INVALID"
        )
    try:
        scheduled, scheduled_text = _utc(source_bundle["slot"]["scheduled_for"])
        recorded, recorded_text = _utc(recorded_at)
        captured = _utc(source_bundle["slot"]["captured_at"])[0]
        klines = source_bundle["klines"]
        closes = tuple(Decimal(row["close"]) for row in klines)
    except (KeyError, TypeError, InvalidOperation) as error:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_SOURCE_INVALID"
        ) from error
    if (
        len(closes) != 21
        or any(not value.is_finite() or value <= 0 for value in closes)
        or not captured <= recorded < scheduled + _FOUR_HOURS
        or source_bundle.get("bundle_hash")
        != artifact_self_hash(source_bundle, "bundle_hash")
        or source_bundle.get("plan")
        != {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]}
        or source_bundle.get("evidence_qualification") != _QUALIFICATION
    ):
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_SOURCE_INVALID"
        )
    with localcontext(_CONTEXT):
        prior_sma20 = sum(closes[:-1], Decimal("0")) / Decimal("20")
        distance = closes[-1] / prior_sma20 - Decimal("1")
        momentum = (closes[-1] / closes[-6]).ln()
    distance_pass = distance >= Decimal("0.005")
    momentum_pass = momentum > Decimal("0")
    policy_hash = plan["decision_policy"]["policy_hash"]
    if previous_decision is None:
        if (
            source_bundle.get("slot", {}).get("sequence") != 1
            or source_bundle.get("parents", {}).get(
                "previous_source_bundle_hash"
            )
            != _ZERO_HASH
            or source_bundle.get("parents", {}).get(
                "previous_decision_hash_or_null"
            )
            is not None
        ):
            raise ChallengerReplacementDecisionError(
                "CHALLENGER_REPLACEMENT_DECISION_PREVIOUS_INVALID"
            )
        state_before = _flat_state()
        previous_decision_hash = None
    else:
        if not _previous_valid(
            previous_decision, plan=plan, source_bundle=source_bundle
        ):
            raise ChallengerReplacementDecisionError(
                "CHALLENGER_REPLACEMENT_DECISION_PREVIOUS_INVALID"
            )
        state_before = dict(previous_decision["state_after"])
        previous_decision_hash = previous_decision["decision_hash"]
    if state_before["position_state"] == "FLAT":
        if distance_pass and momentum_pass:
            action = "ENTER_LONG"
            state_after = _long_state(
                plan_hash=plan["plan_hash"],
                policy_hash=policy_hash,
                scheduled=scheduled,
            )
        else:
            action = "REJECT_ENTRY"
            state_after = _flat_state()
    else:
        minimum = _utc(state_before["minimum_hold_until_or_null"])[0]
        vertical = _utc(state_before["vertical_exit_at_or_null"])[0]
        if scheduled < minimum:
            action = "HOLD_LONG_MINIMUM"
            state_after = state_before
        elif closes[-1] <= prior_sma20:
            action = "EXIT_LONG_SMA20"
            state_after = _flat_state()
        elif scheduled >= vertical:
            action = "EXIT_LONG_VERTICAL_24H"
            state_after = _flat_state()
        else:
            action = "HOLD_LONG"
            state_after = state_before
    parents = {
        "current_source_bundle_hash": source_bundle["bundle_hash"],
        "previous_source_bundle_hash": source_bundle["parents"][
            "previous_source_bundle_hash"
        ],
        "previous_decision_hash_or_null": previous_decision_hash,
    }
    identity = {
        "plan_hash": plan["plan_hash"],
        "slot_id": source_bundle["slot"]["slot_id"],
        "sequence": source_bundle["slot"]["sequence"],
        "current_source_bundle_hash": source_bundle["bundle_hash"],
        "previous_decision_hash_or_null": previous_decision_hash,
    }
    decision = {
        "$schema": "./challenger-replacement-decision-v1.schema.json",
        "schema_version": "1.0.0",
        "decision_id": stable_id("challenger_replacement_decision", identity),
        "decision_hash": _ZERO_HASH,
        "evidence_qualification": _QUALIFICATION,
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "build_identity": dict(source_bundle["build_identity"]),
        "slot": {
            "slot_id": source_bundle["slot"]["slot_id"],
            "sequence": source_bundle["slot"]["sequence"],
            "scheduled_for": scheduled_text,
            "recorded_at": recorded_text,
        },
        "parents": parents,
        "policy_hash": policy_hash,
        "hypothesis_registration_hash": plan["scope"][
            "hypothesis_registration_hash"
        ],
        "input_facts_root_hash": business_hash(klines),
        "features": {
            "latest_close": canonical_decimal(closes[-1]),
            "prior_sma20": canonical_decimal(prior_sma20),
            "eth_sma20_distance": canonical_decimal(distance),
            "eth_log_return_5": canonical_decimal(momentum),
        },
        "entry_conditions": {
            "sma20_distance_minimum": "0.005",
            "sma20_distance_pass": distance_pass,
            "eth_log_return_5_threshold": "0",
            "eth_log_return_5_pass": momentum_pass,
        },
        "state_before": state_before,
        "action": action,
        "state_after": state_after,
        "decision_eligibility": "REPLACEMENT_CHALLENGER_RESEARCH_ONLY",
        "broker_eligibility": "INELIGIBLE_NO_BROKER_ACCESS",
        "authority": dict(source_bundle["authority"]),
    }
    decision["decision_hash"] = artifact_self_hash(decision, "decision_hash")
    return decision


def challenger_replacement_decision_reasons(
    decision: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    source_bundle: Mapping[str, Any],
    previous_decision: Optional[Mapping[str, Any]],
) -> Tuple[str, ...]:
    """Replay a decision and return deterministic semantic mismatch reasons."""

    reasons = []
    try:
        if not isinstance(decision, Mapping):
            raise TypeError("decision must be a mapping")
        if decision.get("decision_hash") != artifact_self_hash(
            decision, "decision_hash"
        ):
            reasons.append("CHALLENGER_REPLACEMENT_DECISION_HASH_MISMATCH")
        rebuilt = build_challenger_replacement_decision(
            plan=plan,
            source_bundle=source_bundle,
            recorded_at=decision["slot"]["recorded_at"],
            previous_decision=previous_decision,
        )
        if business_hash(rebuilt) != business_hash(decision):
            reasons.append(
                "CHALLENGER_REPLACEMENT_DECISION_SEMANTIC_MISMATCH"
            )
    except ChallengerReplacementDecisionError as error:
        reasons.append(error.reason_code)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        reasons.append("CHALLENGER_REPLACEMENT_DECISION_INVALID")
    return tuple(sorted(set(reasons)))


def load_challenger_replacement_decision_bytes(
    data: bytes,
    *,
    plan: Mapping[str, Any],
    source_bundle: Mapping[str, Any],
    previous_decision: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Strict-load exact canonical decision bytes and replay their semantics."""

    from .challenger_replacement_evidence import _decision_validator, _strict_json_bytes

    if not isinstance(data, bytes) or not 0 < len(data) <= 2 * 1024 * 1024:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_SIZE_INVALID"
        )
    try:
        value = _strict_json_bytes(data)
    except ValueError as error:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_CANONICAL_BYTES_REQUIRED"
        ) from error
    if tuple(_decision_validator().iter_errors(value)):
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_DECISION_SCHEMA_INVALID"
        )
    reasons = challenger_replacement_decision_reasons(
        value,
        plan=plan,
        source_bundle=source_bundle,
        previous_decision=previous_decision,
    )
    if reasons:
        raise ChallengerReplacementDecisionError(reasons[0])
    return dict(value)


def load_challenger_replacement_cohort_decision_bytes(
    data, *, plan, source_bundle, previous_decision
):
    """Strict-load and replay one cohort-qualified decision."""

    from .challenger_replacement_evidence import _strict_json_bytes

    if not isinstance(data, bytes) or not 0 < len(data) <= 2 * 1024 * 1024:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_COHORT_DECISION_SIZE_INVALID"
        )
    try:
        value = _strict_json_bytes(data)
    except ValueError as error:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_COHORT_DECISION_CANONICAL_BYTES_REQUIRED"
        ) from error
    if tuple(_cohort_decision_validator().iter_errors(value)):
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_COHORT_DECISION_SCHEMA_INVALID"
        )
    try:
        rebuilt = build_challenger_replacement_cohort_decision(
            plan=plan,
            source_bundle=source_bundle,
            recorded_at=value["slot"]["recorded_at"],
            previous_decision=previous_decision,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_COHORT_DECISION_SEMANTIC_INVALID"
        ) from error
    if value != rebuilt:
        raise ChallengerReplacementDecisionError(
            "CHALLENGER_REPLACEMENT_COHORT_DECISION_SEMANTIC_INVALID"
        )
    return deepcopy(dict(value))
