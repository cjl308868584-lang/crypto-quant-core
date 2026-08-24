"""Fixture-only structural evidence for v3 opportunity state tests."""

import copy
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from typing import Any, Dict
from decimal import Decimal, InvalidOperation

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_decimal, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)


_SCHEMA = "challenger-replacement-opportunity-result-evidence-v1.schema.json"
_SCHEMA_V2 = "challenger-replacement-opportunity-result-evidence-v2.schema.json"
_MAX_BYTES = 65_536
_MAX_V2_BYTES = 1024 * 1024
_ZERO_HASH = "0" * 64
_AUTHORITY_V2 = {
    "network_requests": 0,
    "account_requests": 0,
    "broker_requests": 0,
    "orders_submitted_to_venue": 0,
    "credentials_used": False,
    "production_state_writes": 0,
    "production_activation": False,
    "runtime_install_authorized": False,
    "replacement_start_authorized": False,
    "real_orders_allowed": False,
}
_DECISION_KEYS = {
    "decision_id", "decision_hash", "opportunity_id", "source_hash", "plan",
    "policy_bindings", "previous_snapshot_hash", "position_before", "indicators",
    "daily_loss", "drawdown", "action", "reason_code", "risk_approval",
}
_SNAPSHOT_KEYS = {
    "snapshot_version", "snapshot_hash", "parent_snapshot_hash_or_null",
    "opportunity_id_or_null", "position_state", "position_certainty",
    "signed_quantity", "entry_price_or_null", "contract_multiplier", "entry_time",
    "instrument_metadata_hash_or_null", "protective_stop_or_null", "cash",
    "isolated_margin", "realized_pnl", "cumulative_fees", "cumulative_funding",
    "unrealized_pnl", "marked_equity", "peak_equity", "day_start_equity",
    "day_start_date_or_null", "gross_exposure", "risk_state",
    "active_order_or_null", "unresolved_intent_ids",
    "reverse_blocked_until_next_opportunity", "economic_gap_locked",
}
_ACCOUNTING_KEYS = {
    "fill_price", "quantity", "notional", "fee", "realized_pnl",
    "funding_cashflow",
}


class ChallengerReplacementOpportunityEvidenceError(ValueError):
    """Fixture opportunity evidence failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _validator_v2() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA_V2)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _invalid(reason="CHALLENGER_REPLACEMENT_OPPORTUNITY_EVIDENCE_INVALID"):
    raise ChallengerReplacementOpportunityEvidenceError(reason)


def _canonical_time(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.microsecond % 1000 == 0
        and utc_datetime(parsed.astimezone(timezone.utc)) == value
    )


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _document(
    *, opportunity_id, scheduled_for, observed_at,
    source_bundle_sha256, decision_sha256
) -> Dict[str, Any]:
    return {
        "$schema": "./" + _SCHEMA,
        "schema_version": "1.0.0",
        "mode": "FIXTURE_ONLY_NO_BROKER_NO_ORDER",
        "opportunity_id": opportunity_id,
        "scheduled_for": scheduled_for,
        "observed_at": observed_at,
        "source_bundle_sha256": source_bundle_sha256,
        "decision_sha256": decision_sha256,
        "authority": {
            "network_requests": 0,
            "broker_requests": 0,
            "orders": 0,
            "credentials_used": False,
            "production_state_writes": 0,
        },
    }


def _validate(document, expected):
    if tuple(_validator().iter_errors(document)):
        _invalid()
    if (
        document != expected
        or document["opportunity_id"] != "ETHUSDT@" + document["scheduled_for"]
        or not _canonical_time(document["scheduled_for"])
        or not _canonical_time(document["observed_at"])
    ):
        _invalid()
    scheduled = _time(document["scheduled_for"])
    observed = _time(document["observed_at"])
    if not scheduled + timedelta(seconds=120) <= observed <= scheduled + timedelta(
        seconds=600
    ):
        _invalid()


def build_challenger_replacement_fixture_result_evidence(
    *, opportunity_id, scheduled_for, observed_at,
    source_bundle_sha256, decision_sha256
):
    """Build zero-authority structural evidence for tests only."""

    document = _document(
        opportunity_id=opportunity_id,
        scheduled_for=scheduled_for,
        observed_at=observed_at,
        source_bundle_sha256=source_bundle_sha256,
        decision_sha256=decision_sha256,
    )
    _validate(document, document)
    return copy.deepcopy(document)


def load_challenger_replacement_fixture_result_evidence_bytes(
    data: bytes, *, opportunity_id, scheduled_for, observed_at,
    source_bundle_sha256, decision_sha256
):
    """Replay canonical fixture bytes against exact caller bindings."""

    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_BYTES:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVIDENCE_BYTES_INVALID")
    try:
        document = dict(_strict_json_bytes(data))
        canonical = canonical_json(document).encode("utf-8")
    except (ChallengerReplacementPlanError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityEvidenceError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVIDENCE_BYTES_INVALID"
        ) from error
    if data != canonical:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVIDENCE_BYTES_INVALID")
    expected = _document(
        opportunity_id=opportunity_id,
        scheduled_for=scheduled_for,
        observed_at=observed_at,
        source_bundle_sha256=source_bundle_sha256,
        decision_sha256=decision_sha256,
    )
    _validate(document, expected)
    return copy.deepcopy(document)


def _v2_invalid(reason="CHALLENGER_REPLACEMENT_SIMULATION_RESULT_EVIDENCE_INVALID"):
    raise ChallengerReplacementOpportunityEvidenceError(reason)


def _canonical_mapping_bytes(data: bytes) -> Dict[str, Any]:
    try:
        value = dict(_strict_json_bytes(data))
        if canonical_json(value).encode("utf-8") != data:
            _v2_invalid()
        return value
    except ChallengerReplacementOpportunityEvidenceError:
        raise
    except (ChallengerReplacementPlanError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityEvidenceError(
            "CHALLENGER_REPLACEMENT_SIMULATION_RESULT_EVIDENCE_INVALID"
        ) from error


def _decimal_is_canonical(value: object, *, nullable=False) -> bool:
    if nullable and value is None:
        return True
    if not isinstance(value, str):
        return False
    try:
        return canonical_decimal(Decimal(value)) == value
    except (InvalidOperation, ValueError):
        return False


def _event_document(event) -> Dict[str, Any]:
    payload = _canonical_mapping_bytes(event.payload_bytes)
    return {
        "ordinal": event.ordinal,
        "event_type": event.event_type,
        "event_hash": event.event_hash,
        "parent_event_hash_or_null": event.parent_event_hash_or_null,
        "intent_id_or_null": event.intent_id_or_null,
        "attempt_id_or_null": event.attempt_id_or_null,
        "payload": payload,
    }


def _result_identity(document):
    return {
        "plan": document["plan"],
        "simulation_contract": document["simulation_contract"],
        "opportunity": document["opportunity"],
        "source": document["source"],
        "decision_hash": document["decision"]["decision_hash"],
        "previous_snapshot_hash": document["previous_snapshot"]["snapshot_hash"],
    }


def _document_v2(lifecycle_result):
    from .challenger_replacement_binance_lifecycle import (
        ChallengerReplacementLifecycleResult,
    )

    if not isinstance(lifecycle_result, ChallengerReplacementLifecycleResult):
        _v2_invalid()
    source = _canonical_mapping_bytes(lifecycle_result.source_bytes)
    previous = _canonical_mapping_bytes(lifecycle_result.previous_snapshot_bytes)
    plan = _canonical_mapping_bytes(lifecycle_result.plan_identity_bytes)
    contract = _canonical_mapping_bytes(lifecycle_result.contract_identity_bytes)
    build = _canonical_mapping_bytes(lifecycle_result.build_identity_bytes)
    decision = _canonical_mapping_bytes(lifecycle_result.decision_bytes)
    accounting = _canonical_mapping_bytes(lifecycle_result.accounting_bytes)
    next_snapshot = _canonical_mapping_bytes(lifecycle_result.next_snapshot_bytes)
    document = {
        "$schema": "./" + _SCHEMA_V2,
        "schema_version": "2.0.0",
        "mode": "FIXTURE_SIMULATION_NO_NETWORK_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER",
        "result_id": "challenger_replacement_simulation_result_" + _ZERO_HASH,
        "result_hash": _ZERO_HASH,
        "evidence_qualification": "COMMITTED_FIXTURE_NOT_LIVE_MARKET_OR_ACCOUNT",
        "plan": plan,
        "simulation_contract": contract,
        "build_identity": build,
        "opportunity": copy.deepcopy(source["opportunity"]),
        "source": {"input_id": source["input_id"], "input_hash": source["input_hash"]},
        "decision": decision,
        "previous_snapshot": previous,
        "risk": {
            "approval": decision["risk_approval"],
            "reason_code": decision["reason_code"],
        },
        "lifecycle": {
            "status": lifecycle_result.status,
            "operationally_complete": lifecycle_result.operationally_complete,
            "reason_code_or_null": lifecycle_result.reason_code_or_null,
            "events": [_event_document(item) for item in lifecycle_result.lifecycle_events],
        },
        "accounting": accounting,
        "next_snapshot": next_snapshot,
        "authority": copy.deepcopy(_AUTHORITY_V2),
    }
    document["result_id"] = stable_id(
        "challenger_replacement_simulation_result", _result_identity(document)
    )
    document["result_hash"] = artifact_self_hash(document, "result_hash")
    return document


def _validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != _SNAPSHOT_KEYS:
        _v2_invalid()
    if snapshot.get("snapshot_hash") != artifact_self_hash(snapshot, "snapshot_hash"):
        _v2_invalid()
    try:
        from .challenger_replacement_simulation import _validate_snapshot as validate
        validate(snapshot)
    except (Exception,) as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        _v2_invalid()


def _validate_events(lifecycle, *, previous_snapshot, accounting, next_snapshot):
    from .challenger_replacement_binance_lifecycle import (
        EngineProjection,
        LifecycleEvent,
        _NULL_ID_EVENTS,
        _PAYLOAD_KEYS,
        _normal_lifecycle_observations,
        _reduce_engine,
        _reduce_ledger,
        _reduce_venue,
    )

    events = lifecycle.get("events")
    if not isinstance(events, list) or not events:
        _v2_invalid()
    parent = None
    for ordinal, event in enumerate(events, 1):
        if (
            not isinstance(event, dict)
            or set(event) != {
                "ordinal", "event_type", "event_hash", "parent_event_hash_or_null",
                "intent_id_or_null", "attempt_id_or_null", "payload",
            }
            or event["ordinal"] != ordinal
            or event["parent_event_hash_or_null"] != parent
            or event["event_type"] not in _PAYLOAD_KEYS
            or set(event["payload"]) != _PAYLOAD_KEYS[event["event_type"]]
            or (
                event["event_type"] in _NULL_ID_EVENTS
                and (
                    event["intent_id_or_null"] is not None
                    or event["attempt_id_or_null"] is not None
                )
            )
            or event["event_hash"] != artifact_self_hash(event, "event_hash")
        ):
            _v2_invalid()
        parent = event["event_hash"]
    expected_terminal = (
        "LIFECYCLE_RECONCILED_FIXTURE"
        if lifecycle["status"] == "RECONCILED_FIXTURE"
        else "LIFECYCLE_FAILED_CLOSED"
    )
    if events[-1]["event_type"] != expected_terminal:
        _v2_invalid()
    if expected_terminal == "LIFECYCLE_RECONCILED_FIXTURE":
        typed = tuple(LifecycleEvent(
            ordinal=event["ordinal"], event_type=event["event_type"],
            event_hash=event["event_hash"],
            parent_event_hash_or_null=event["parent_event_hash_or_null"],
            intent_id_or_null=event["intent_id_or_null"],
            attempt_id_or_null=event["attempt_id_or_null"],
            payload_bytes=canonical_json(event["payload"]).encode("utf-8"),
        ) for event in events[:-1])
        transition = {"accounting": accounting, "next_snapshot": next_snapshot}
        observations = _normal_lifecycle_observations(
            transition, previous_snapshot["position_state"]
        )
        if accounting["fill_price"] is None:
            product = {"SPOT_LONG": "spot", "PERP_SHORT": "perpetual"}.get(
                next_snapshot["position_state"]
            )
            values = (
                product, next_snapshot["signed_quantity"], None, "0",
                accounting["funding_cashflow"], "NO_INTENT",
            )
            projections = (EngineProjection(*values),) * 3
        else:
            projections = (
                _reduce_engine(typed, accounting["funding_cashflow"]),
                _reduce_venue(observations, previous_snapshot["position_state"]),
                _reduce_ledger(previous_snapshot, transition),
            )
        payload = events[-1]["payload"]
        if payload != {
            "engine_projection_hash": business_hash(projections[0]),
            "venue_projection_hash": business_hash(projections[1]),
            "ledger_projection_hash": business_hash(projections[2]),
        }:
            _v2_invalid()


def _validate_v2(document, *, plan, contract, build_identity):
    if tuple(_validator_v2().iter_errors(document)):
        _v2_invalid()
    expected_plan = {"plan_id": plan.get("plan_id"), "plan_hash": plan.get("plan_hash")}
    expected_contract = {
        "contract_id": contract.get("contract_id"),
        "contract_hash": contract.get("contract_hash"),
    }
    if (
        document["plan"] != expected_plan
        or document["simulation_contract"] != expected_contract
        or document["build_identity"] != build_identity
        or document["authority"] != _AUTHORITY_V2
        or set(document["decision"]) != _DECISION_KEYS
        or set(document["accounting"]) != _ACCOUNTING_KEYS
    ):
        _v2_invalid()
    _validate_snapshot(document["previous_snapshot"])
    _validate_snapshot(document["next_snapshot"])
    decision = document["decision"]
    expected_decision_id = stable_id(
        "challenger_replacement_simulation_decision",
        {key: value for key, value in decision.items()
         if key not in {"decision_id", "decision_hash"}},
    )
    if (
        decision["decision_id"] != expected_decision_id
        or decision["decision_hash"] != artifact_self_hash(decision, "decision_hash")
        or decision["plan"] != expected_plan
        or decision["source_hash"] != document["source"]["input_hash"]
        or decision["opportunity_id"] != document["opportunity"]["opportunity_id"]
        or decision["previous_snapshot_hash"]
        != document["previous_snapshot"]["snapshot_hash"]
        or document["risk"] != {
            "approval": decision["risk_approval"],
            "reason_code": decision["reason_code"],
        }
    ):
        _v2_invalid()
    if any(
        not _decimal_is_canonical(value, nullable=key == "fill_price")
        for key, value in document["accounting"].items()
    ):
        _v2_invalid()
    lifecycle = document["lifecycle"]
    if (
        lifecycle["operationally_complete"]
        != (lifecycle["status"] == "RECONCILED_FIXTURE")
        or (lifecycle["reason_code_or_null"] is None)
        != (lifecycle["status"] == "RECONCILED_FIXTURE")
    ):
        _v2_invalid()
    _validate_events(
        lifecycle,
        previous_snapshot=document["previous_snapshot"],
        accounting=document["accounting"],
        next_snapshot=document["next_snapshot"],
    )
    if (
        document["result_id"]
        != stable_id("challenger_replacement_simulation_result", _result_identity(document))
        or document["result_hash"] != artifact_self_hash(document, "result_hash")
    ):
        _v2_invalid()


def build_challenger_replacement_simulation_result_evidence(
    *, lifecycle_result: "ChallengerReplacementLifecycleResult"
) -> dict:
    """Build strict zero-authority v2 evidence from one typed lifecycle result."""

    document = _document_v2(lifecycle_result)
    _validate_v2(
        document,
        plan=json.loads(lifecycle_result.plan_identity_bytes),
        contract=json.loads(lifecycle_result.contract_identity_bytes),
        build_identity=json.loads(lifecycle_result.build_identity_bytes),
    )
    return copy.deepcopy(document)


def load_challenger_replacement_simulation_result_evidence_bytes(
    data: bytes, *, plan, contract, build_identity
) -> dict:
    """Replay bounded canonical v2 bytes against an exact trust context."""

    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_V2_BYTES:
        _v2_invalid("CHALLENGER_REPLACEMENT_SIMULATION_RESULT_EVIDENCE_BYTES_INVALID")
    try:
        document = dict(_strict_json_bytes(data))
        if canonical_json(document).encode("utf-8") != data:
            _v2_invalid("CHALLENGER_REPLACEMENT_SIMULATION_RESULT_EVIDENCE_BYTES_INVALID")
    except ChallengerReplacementOpportunityEvidenceError:
        raise
    except (ChallengerReplacementPlanError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityEvidenceError(
            "CHALLENGER_REPLACEMENT_SIMULATION_RESULT_EVIDENCE_BYTES_INVALID"
        ) from error
    _validate_v2(document, plan=plan, contract=contract, build_identity=build_identity)
    return copy.deepcopy(document)
