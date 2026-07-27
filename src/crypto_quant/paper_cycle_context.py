"""Replayable account-cost and perpetual context for one Paper slot."""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .paper_cost_binding import paper_account_cost_binding_reasons
from .paper_scheduler import PaperSchedulePolicy
from .perpetual_context import perpetual_context_reasons


_ATTESTATION_TYPE = "PAPER_CYCLE_CONTEXT_BUNDLE_ATTESTATION"
_MAX_SOURCE_SKEW = timedelta(minutes=15)
_WARNINGS = (
    "PERPETUAL_CONTEXT_NOT_CONSUMED_BY_BASELINE_SIGNAL",
    "FUNDING_SCENARIOS_NOT_REALIZED_PNL",
    "ACCOUNT_COMMISSION_CURRENT_ONLY",
    "EXTERNAL_SOURCE_ATTESTATIONS_REQUIRED",
    "SHORT_EXECUTION_NOT_IMPLEMENTED",
    "AI_MODEL_NOT_RUN",
    "OPERATING_SYSTEM_SCHEDULER_NOT_CONFIGURED",
    "PAPER_DURATION_BELOW_90_DAYS",
    "PROFITABILITY_NOT_PROVEN",
)


class PaperCycleContextError(ValueError):
    """The context-complete Paper bundle failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise PaperCycleContextError(
                "PAPER_CONTEXT_TIME_INVALID"
            ) from error
    else:
        raise PaperCycleContextError("PAPER_CONTEXT_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperCycleContextError("PAPER_CONTEXT_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise PaperCycleContextError("PAPER_CONTEXT_TIME_INVALID")
    return converted, utc_datetime(converted)


def _hash(value: object, reason: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PaperCycleContextError(reason)
    return value


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "paper-cycle-context-bundle-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_sources(
    paper_cost_binding: Mapping[str, Any],
    paper_cost_binding_trusted_attestation_hash: str,
    offline_paper_trusted_attestation_hash: str,
    account_commission_trusted_attestation_hash: str,
    perpetual_context_snapshot: Mapping[str, Any],
    perpetual_context_trusted_attestation_hash: str,
) -> Dict[str, str]:
    hashes = {
        "paper_cost_binding_trusted_attestation_hash": _hash(
            paper_cost_binding_trusted_attestation_hash,
            "PAPER_CONTEXT_COST_BINDING_TRUST_INVALID",
        ),
        "offline_paper_trusted_attestation_hash": _hash(
            offline_paper_trusted_attestation_hash,
            "PAPER_CONTEXT_PAPER_TRUST_INVALID",
        ),
        "account_commission_trusted_attestation_hash": _hash(
            account_commission_trusted_attestation_hash,
            "PAPER_CONTEXT_ACCOUNT_TRUST_INVALID",
        ),
        "perpetual_context_trusted_attestation_hash": _hash(
            perpetual_context_trusted_attestation_hash,
            "PAPER_CONTEXT_PERPETUAL_TRUST_INVALID",
        ),
    }
    if paper_account_cost_binding_reasons(
        paper_cost_binding,
        hashes["paper_cost_binding_trusted_attestation_hash"],
        offline_paper_trusted_attestation_hash=hashes[
            "offline_paper_trusted_attestation_hash"
        ],
        account_commission_trusted_attestation_hash=hashes[
            "account_commission_trusted_attestation_hash"
        ],
    ):
        raise PaperCycleContextError(
            "PAPER_CONTEXT_COST_BINDING_INVALID"
        )
    if perpetual_context_reasons(
        perpetual_context_snapshot,
        hashes["perpetual_context_trusted_attestation_hash"],
    ):
        raise PaperCycleContextError(
            "PAPER_CONTEXT_PERPETUAL_SOURCE_INVALID"
        )
    return hashes


def _slot_and_pit(
    paper_cost_binding: Mapping[str, Any],
    perpetual_context_snapshot: Mapping[str, Any],
    created_at: object,
) -> Tuple[Dict[str, Any], str]:
    try:
        paper = paper_cost_binding["offline_paper_run"]
        decision, decision_text = _utc(paper["decision_time"])
        run_end, run_end_text = _utc(paper["run_end"])
        perpetual_source, perpetual_source_text = _utc(
            perpetual_context_snapshot["market_context"]["source_time"]
        )
        perpetual_recorded, perpetual_recorded_text = _utc(
            perpetual_context_snapshot["recorded_at"]
        )
    except (KeyError, TypeError) as error:
        raise PaperCycleContextError(
            "PAPER_CONTEXT_SOURCE_TIME_INVALID"
        ) from error
    policy = PaperSchedulePolicy.create()
    slot = policy.current_slot(decision_text)
    due = _utc(slot.due_at)[0]
    expires = _utc(slot.expires_at)[0]
    expected_run_id = "paper-slot-" + slot.slot_id.lower()
    if (
        paper.get("run_id") != expected_run_id
        or not due <= decision < expires
        or not due <= run_end < expires
    ):
        raise PaperCycleContextError(
            "PAPER_CONTEXT_SCHEDULED_RUN_MISMATCH"
        )
    if not due <= perpetual_source < expires:
        raise PaperCycleContextError(
            "PAPER_CONTEXT_PERPETUAL_OUTSIDE_SLOT"
        )
    if abs(perpetual_source - decision) > _MAX_SOURCE_SKEW:
        raise PaperCycleContextError(
            "PAPER_CONTEXT_SOURCE_SKEW_EXCEEDED"
        )
    if not perpetual_source <= perpetual_recorded < expires:
        raise PaperCycleContextError(
            "PAPER_CONTEXT_PERPETUAL_RECORDED_INVALID"
        )
    created, created_text = _utc(created_at)
    cost_created, _ = _utc(paper_cost_binding["created_at"])
    if (
        created < max(run_end, cost_created, perpetual_recorded)
        or created >= expires
    ):
        raise PaperCycleContextError(
            "PAPER_CONTEXT_CREATED_TIME_INVALID"
        )
    role = (
        "PRE_DECISION_AVAILABLE_NOT_CONSUMED"
        if perpetual_source <= decision
        else "POST_DECISION_OBSERVATIONAL_NOT_SIGNAL"
    )
    return {
        "status": "PASS",
        "schedule_policy_hash": policy.policy_hash,
        "slot": {
            "slot_id": slot.slot_id,
            "scheduled_for": slot.scheduled_for,
            "due_at": slot.due_at,
            "expires_at": slot.expires_at,
        },
        "paper_decision_time": decision_text,
        "paper_run_end": run_end_text,
        "perpetual_source_time": perpetual_source_text,
        "perpetual_recorded_at": perpetual_recorded_text,
        "absolute_source_skew_seconds": int(
            abs(perpetual_source - decision).total_seconds()
        ),
        "maximum_source_skew_seconds": 900,
        "perpetual_availability_role": role,
        "perpetual_used_in_signal": False,
        "historical_backfill_used": False,
    }, created_text


def build_paper_cycle_context_bundle(
    *,
    paper_cost_binding: Mapping[str, Any],
    paper_cost_binding_trusted_attestation_hash: str,
    offline_paper_trusted_attestation_hash: str,
    account_commission_trusted_attestation_hash: str,
    perpetual_context_snapshot: Mapping[str, Any],
    perpetual_context_trusted_attestation_hash: str,
    created_at: object,
) -> Dict[str, Any]:
    """Build one context-complete Paper scheduler sidecar bundle."""

    if not isinstance(paper_cost_binding, Mapping) or not isinstance(
        perpetual_context_snapshot, Mapping
    ):
        raise PaperCycleContextError("PAPER_CONTEXT_SOURCE_INVALID")
    source_hashes = _validate_sources(
        paper_cost_binding,
        paper_cost_binding_trusted_attestation_hash,
        offline_paper_trusted_attestation_hash,
        account_commission_trusted_attestation_hash,
        perpetual_context_snapshot,
        perpetual_context_trusted_attestation_hash,
    )
    pit, created_text = _slot_and_pit(
        paper_cost_binding, perpetual_context_snapshot, created_at
    )
    try:
        baseline = paper_cost_binding["baseline_cost_replay"]
        market = perpetual_context_snapshot["market_context"]
        scenarios = perpetual_context_snapshot[
            "short_funding_scenarios"
        ]
    except (KeyError, TypeError) as error:
        raise PaperCycleContextError(
            "PAPER_CONTEXT_DERIVED_SOURCE_INVALID"
        ) from error
    lineage = {
        **source_hashes,
        "paper_cost_binding_hash": paper_cost_binding["binding_hash"],
        "offline_paper_run_hash": paper_cost_binding[
            "offline_paper_run"
        ]["run_hash"],
        "account_commission_snapshot_hash": paper_cost_binding[
            "account_commission_snapshot"
        ]["snapshot_hash"],
        "perpetual_context_snapshot_hash": (
            perpetual_context_snapshot["snapshot_hash"]
        ),
        "copies_are_lineage_not_independent_proof": True,
    }
    identity = {
        "slot_id": pit["slot"]["slot_id"],
        "schedule_policy_hash": pit["schedule_policy_hash"],
        "lineage": lineage,
    }
    bundle = {
        "$schema": "./paper-cycle-context-bundle-v1.schema.json",
        "schema_version": "1.0.0",
        "bundle_id": stable_id("paper_cycle_context", identity),
        "bundle_hash": "",
        "created_at": created_text,
        "lineage": lineage,
        "paper_cost_binding": deepcopy(dict(paper_cost_binding)),
        "perpetual_context_snapshot": deepcopy(
            dict(perpetual_context_snapshot)
        ),
        "pit_context": pit,
        "cost_outcome": {
            "source_fill_status": baseline["source_fill_status"],
            "account_total_fee_usdt": baseline[
                "account_total_fee_usdt"
            ],
            "account_costed_ending_liquidation_equity_usdt": baseline[
                "account_costed_ending_liquidation_equity_usdt"
            ],
            "account_costed_liquidation_net_change_usdt": baseline[
                "account_costed_liquidation_net_change_usdt"
            ],
            "realized_pnl_claimed": False,
        },
        "perpetual_observation": {
            "symbol": market["symbol"],
            "market": market["market"],
            "source_time": market["source_time"],
            "mark_price": market["mark_price"],
            "index_price": market["index_price"],
            "basis_usdt": market["basis_usdt"],
            "basis_rate": market["basis_rate"],
            "current_open_interest": market["current_open_interest"],
            "open_interest_4h_value_change_rate_or_null": market[
                "open_interest_4h_value_change_rate_or_null"
            ],
            "next_funding_short_cashflow_per_1000_usdt": scenarios[
                "next_funding_short_cashflow_per_1000_usdt"
            ],
            "repeated_current_rate_24h_short_cashflow_per_1000_usdt": (
                scenarios[
                    "repeated_current_rate_24h_short_cashflow_per_1000_usdt"
                ]
            ),
            "two_x_recent_absolute_adverse_24h_short_cashflow_per_1000_usdt": (
                scenarios[
                    "two_x_recent_absolute_adverse_24h_short_cashflow_per_1000_usdt"
                ]
            ),
            "funding_realized": False,
            "forecast_claimed": False,
        },
        "security_boundary": {
            "network_requests_made_by_bundle": 0,
            "credentials_read_by_bundle": False,
            "account_balances_read": False,
            "orders_submitted": False,
            "paper_run_changed": False,
            "perpetual_used_in_signal": False,
        },
        "cycle_eligibility": "CONTEXT_COMPLETE_RESEARCH_ONLY",
        "paper_eligibility": "LONGITUDINAL_COLLECTION_IN_PROGRESS",
        "production_eligibility": "NOT_APPROVED",
        "profitability_eligibility": (
            "INSUFFICIENT_DURATION_EXECUTION_AND_AI"
        ),
        "warnings": list(_WARNINGS),
    }
    bundle["bundle_hash"] = artifact_self_hash(bundle, "bundle_hash")
    if tuple(_validator().iter_errors(bundle)):
        raise PaperCycleContextError(
            "PAPER_CONTEXT_BUNDLE_SCHEMA_INVALID"
        )
    return bundle


def paper_cycle_context_trust_hash(bundle: Mapping[str, Any]) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _ATTESTATION_TYPE,
                "bundle_id": bundle["bundle_id"],
                "bundle_hash": bundle["bundle_hash"],
                "slot_id": bundle["pit_context"]["slot"]["slot_id"],
                "schedule_policy_hash": bundle["pit_context"][
                    "schedule_policy_hash"
                ],
                "lineage": bundle["lineage"],
            }
        )
    except (KeyError, TypeError):
        return ""


def paper_cycle_context_reasons(
    bundle: Mapping[str, Any],
    trusted_bundle_attestation_hash: str,
    *,
    paper_cost_binding_trusted_attestation_hash: str,
    offline_paper_trusted_attestation_hash: str,
    account_commission_trusted_attestation_hash: str,
    perpetual_context_trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(bundle, Mapping):
        return ("PAPER_CONTEXT_BUNDLE_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(bundle)):
            reasons.append("PAPER_CONTEXT_BUNDLE_SCHEMA_INVALID")
        if artifact_self_hash(
            bundle, "bundle_hash"
        ) != bundle.get("bundle_hash"):
            reasons.append("PAPER_CONTEXT_BUNDLE_SELF_HASH_MISMATCH")
        if (
            paper_cycle_context_trust_hash(bundle)
            != trusted_bundle_attestation_hash
        ):
            reasons.append("PAPER_CONTEXT_BUNDLE_TRUST_HASH_MISMATCH")
        rebuilt = build_paper_cycle_context_bundle(
            paper_cost_binding=bundle["paper_cost_binding"],
            paper_cost_binding_trusted_attestation_hash=(
                paper_cost_binding_trusted_attestation_hash
            ),
            offline_paper_trusted_attestation_hash=(
                offline_paper_trusted_attestation_hash
            ),
            account_commission_trusted_attestation_hash=(
                account_commission_trusted_attestation_hash
            ),
            perpetual_context_snapshot=bundle[
                "perpetual_context_snapshot"
            ],
            perpetual_context_trusted_attestation_hash=(
                perpetual_context_trusted_attestation_hash
            ),
            created_at=bundle["created_at"],
        )
        if rebuilt != bundle:
            reasons.append("PAPER_CONTEXT_BUNDLE_REPLAY_MISMATCH")
    except (
        KeyError,
        TypeError,
        ValueError,
        PaperCycleContextError,
    ):
        reasons.append("PAPER_CONTEXT_BUNDLE_REPLAY_INVALID")
    return tuple(sorted(set(reasons)))
