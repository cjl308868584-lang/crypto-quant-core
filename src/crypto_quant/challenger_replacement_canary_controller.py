"""Pure operational-ceremony and E0/E1/E2 Canary projection."""
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from importlib import resources
import json
from types import MappingProxyType
from typing import Mapping
from jsonschema import Draft202012Validator
from .canonical import canonical_decimal, canonical_json, utc_datetime
from .challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)
from .challenger_replacement_events import (
    ChallengerReplacementEventRoot, replay_challenger_replacement_events,
)
from .challenger_replacement_install_trust import business_hash
_SCHEMA = "challenger-replacement-canary-projection-v1.schema.json"
_CEREMONY = (
    "CEREMONY_READY_FLAT", "SPOT_BUY_SUBMITTED",
    "SPOT_LONG_RECONCILED", "SPOT_SELL_SUBMITTED",
    "FLAT_RECONCILED_AFTER_SPOT", "PERP_SHORT_SUBMITTED",
    "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED",
    "PERP_CLOSE_REDUCE_ONLY_SUBMITTED", "FLAT_RECONCILED_AFTER_PERP",
    "CEREMONY_QUALIFIED",
)
_LABEL = "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE"
_HARD_STOPS = frozenset({
    "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
    "VENUE_LOCAL_POSITION_MISMATCH",
    "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
    "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
})
_AUTHORITY = {
    "network_requests": 0, "orders": 0, "state_writes": 0,
    "production_activation": False,
}
class ChallengerReplacementCanaryControllerError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code
def _fail(reason="CHALLENGER_REPLACEMENT_CANARY_EVENT_INVALID", error=None):
    failure = ChallengerReplacementCanaryControllerError(reason)
    if error is None:
        raise failure
    raise failure from error
def _time(value):
    try:
        if not isinstance(value, str):
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or utc_datetime(parsed) != value:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError as error:
        _fail(error=error)
def _decimal(value):
    try:
        number = Decimal(value)
        if (not isinstance(value, str) or not number.is_finite() or number < 0
                or canonical_decimal(number) != value):
            raise ValueError
        return number
    except (InvalidOperation, TypeError, ValueError) as error:
        _fail(error=error)
def _identity(value):
    return isinstance(value, str) and 1 <= len(value) <= 256
def _prefixed_hash(value, prefix):
    suffix = value[len(prefix):] if isinstance(value, str) else ""
    return (
        isinstance(value, str) and value.startswith(prefix)
        and len(suffix) == 64 and not set(suffix) - set("0123456789abcdef")
    )
def _event(value, previous_time):
    if not isinstance(value, Mapping):
        _fail()
    event_type = value.get("event_type")
    keys = {
        "CEREMONY_STATE_RECONCILED": {
            "event_type", "block_id", "label", "state", "occurred_at",
            "reconciliation_id", "minimum_amount_satisfied_or_null",
            "flat_or_null",
        },
        "CANARY_STAGE_BLOCK_STARTED": {
            "event_type", "stage", "block_id", "activation_id",
            "previous_block_id_or_null", "incident_unlock_id_or_null",
            "occurred_at", "starting_equity",
        },
        "CANARY_EQUITY_RECONCILED": {
            "event_type", "block_id", "occurred_at", "equity", "flat",
            "new_risk_attempted", "hard_stop_or_null",
        },
        "CANARY_STRATEGY_CYCLE_RECONCILED": {
            "event_type", "block_id", "occurred_at", "cycle_id", "product",
            "complete", "evidence_label",
        },
    }
    if event_type not in keys or frozenset(value) != keys[event_type]:
        _fail()
    occurred = _time(value["occurred_at"])
    if previous_time is not None and occurred <= previous_time:
        _fail()
    return dict(value), occurred
def _new_block(event, plan, previous):
    stage = event["stage"]
    if stage not in {"E0", "E1", "E2"}:
        _fail()
    policy = plan["canary_ladder"][stage]
    if (not _identity(event["block_id"])
            or not _prefixed_hash(
                event["activation_id"], "binance_private_activation_"
            )
            or _decimal(event["starting_equity"])
            != Decimal(policy["capital_limit_usdt"])):
        _fail()
    if previous is None:
        if (stage != "E0" or event["previous_block_id_or_null"] is not None
                or event["incident_unlock_id_or_null"] is not None):
            _fail()
    else:
        order = {"E0": "E1", "E1": "E2"}
        promoted = (
            previous["status"] == "STAGE_ELIGIBLE_AWAITING_APPROVAL"
            and order.get(previous["stage"]) == stage
            and event["incident_unlock_id_or_null"] is None
        )
        recovered = (
            previous["status"] == "STAGE_FAILED_LOCKED"
            and previous["flat"] is True and previous["stage"] == stage
            and _prefixed_hash(
                event["incident_unlock_id_or_null"], "incident_unlock_"
            )
        )
        if (not (promoted or recovered)
                or event["previous_block_id_or_null"] != previous["block_id"]
                or event["block_id"] == previous["block_id"]):
            _fail()
    equity = event["starting_equity"]
    return {
        "stage": stage, "block_id": event["block_id"],
        "activation_id": event["activation_id"],
        "previous_block_id_or_null": event["previous_block_id_or_null"],
        "incident_unlock_id_or_null": event["incident_unlock_id_or_null"],
        "started_at": event["occurred_at"], "status": "STAGE_ACTIVE",
        "starting_equity": equity, "current_equity": equity,
        "high_water_equity": equity, "day_start_date": event["occurred_at"][:10],
        "day_start_equity": equity, "daily_loss": "0", "drawdown": "0",
        "new_risk_blocked": False, "hard_stop_or_null": None,
        "failure_reason_or_null": None,
        "flat": True, "flatten_required": False,
        "strategy_cycle_count": 0, "spot_complete_cycles": 0,
        "perpetual_complete_cycles": 0, "cycle_ids": [],
    }
def _apply_equity(block, event, policy):
    if (event["block_id"] != block["block_id"]
            or not isinstance(event["flat"], bool)
            or not isinstance(event["new_risk_attempted"], bool)
            or (event["hard_stop_or_null"] is not None
                and event["hard_stop_or_null"] not in _HARD_STOPS)):
        _fail()
    equity = _decimal(event["equity"])
    if block["status"] == "STAGE_FAILED_LOCKED":
        if event["new_risk_attempted"] or event["hard_stop_or_null"] is not None:
            _fail()
        high = max(Decimal(block["high_water_equity"]), equity)
        block.update(
            current_equity=canonical_decimal(equity),
            high_water_equity=canonical_decimal(high),
            drawdown=canonical_decimal(max(Decimal(0), high - equity)),
            flat=event["flat"], flatten_required=not event["flat"],
        )
        return
    if event["occurred_at"][:10] != block["day_start_date"]:
        block.update(
            day_start_date=event["occurred_at"][:10],
            day_start_equity=event["equity"], daily_loss="0",
            new_risk_blocked=False, status="STAGE_ACTIVE",
        )
    high = max(Decimal(block["high_water_equity"]), equity)
    daily = max(Decimal(0), Decimal(block["day_start_equity"]) - equity)
    drawdown = max(Decimal(0), high - equity)
    daily_limit = (Decimal(policy["daily_loss_limit"])
                   if policy["daily_loss_limit_kind"] == "ABSOLUTE_USDT"
                   else Decimal(policy["capital_limit_usdt"])
                   * Decimal(policy["daily_loss_limit"]))
    drawdown_limit = (Decimal(policy["drawdown_limit"])
                      if policy["drawdown_limit_kind"] == "ABSOLUTE_USDT"
                      else high * Decimal(policy["drawdown_limit"]))
    hard_stop = event["hard_stop_or_null"]
    post_limit_attempt = (
        event["new_risk_attempted"]
        and (block["new_risk_blocked"] or daily >= daily_limit)
    )
    if hard_stop == "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT":
        if not post_limit_attempt:
            _fail()
    elif post_limit_attempt:
        if hard_stop != "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT":
            _fail()
    block.update(
        current_equity=canonical_decimal(equity),
        high_water_equity=canonical_decimal(high),
        daily_loss=canonical_decimal(daily), drawdown=canonical_decimal(drawdown),
        flat=event["flat"],
    )
    if hard_stop is not None or drawdown >= drawdown_limit:
        block.update(
            status="STAGE_FAILED_LOCKED", new_risk_blocked=True,
            hard_stop_or_null=hard_stop,
            failure_reason_or_null=(
                hard_stop or "STAGE_DRAWDOWN_LIMIT_REACHED"
            ),
            flatten_required=not event["flat"],
        )
    elif daily >= daily_limit:
        block.update(status="STAGE_DAILY_STOPPED", new_risk_blocked=True)
def _apply_cycle(block, event):
    if (event["block_id"] != block["block_id"]
            or block["status"] == "STAGE_FAILED_LOCKED"
            or event["product"] not in {"SPOT", "PERPETUAL"}
            or event["complete"] is not True
            or event["evidence_label"] != "NATURAL_STRATEGY_EVIDENCE"
            or not _identity(event["cycle_id"])
            or event["cycle_id"] in block["cycle_ids"]):
        _fail()
    block["cycle_ids"].append(event["cycle_id"])
    block["strategy_cycle_count"] += 1
    block["spot_complete_cycles" if event["product"] == "SPOT"
          else "perpetual_complete_cycles"] += 1
def _eligible(block, plan, now):
    policy = plan["canary_ladder"][block["stage"]]
    return all((
        block["status"] == "STAGE_ACTIVE",
        now >= _time(block["started_at"]) + timedelta(
            days=policy["minimum_calendar_days"]
        ),
        block["strategy_cycle_count"] >= policy["minimum_strategy_cycles"],
        block["spot_complete_cycles"] >= 1,
        block["perpetual_complete_cycles"] >= 1,
    ))
def _projection_id(document):
    core = dict(document)
    core.pop("projection_id", None)
    return "challenger_replacement_canary_projection_" + hashlib.sha256(
        canonical_json(core).encode()
    ).hexdigest()
def _project_challenger_replacement_canary(*, events, plan, now):
    """Pure reducer used only after canonical event replay."""
    if (not isinstance(events, tuple) or not isinstance(plan, Mapping)
            or dict(plan) != build_challenger_replacement_accelerated_canary_plan()):
        _fail()
    now_value = _time(now)
    ceremony = None
    block = None
    previous_time = None
    ceremony_index = 0
    for candidate in events:
        event, occurred = _event(candidate, previous_time)
        if occurred > now_value:
            _fail()
        previous_time = occurred
        if event["event_type"] == "CEREMONY_STATE_RECONCILED":
            state = event["state"]
            amount_required = state in {
                "SPOT_LONG_RECONCILED", "FLAT_RECONCILED_AFTER_SPOT",
                "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED",
                "FLAT_RECONCILED_AFTER_PERP",
            }
            expected_flat = (
                True if state in {
                    "CEREMONY_READY_FLAT", "FLAT_RECONCILED_AFTER_SPOT",
                    "FLAT_RECONCILED_AFTER_PERP", "CEREMONY_QUALIFIED",
                } else False if state in {
                    "SPOT_LONG_RECONCILED",
                    "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED",
                } else None
            )
            if (block is not None or ceremony_index >= len(_CEREMONY)
                    or state != _CEREMONY[ceremony_index]
                    or event["label"] != _LABEL
                    or not _identity(event["block_id"])
                    or not _prefixed_hash(
                        event["reconciliation_id"], "binance_reconciliation_"
                    ) or event["minimum_amount_satisfied_or_null"] != (
                        True if amount_required else None
                    ) or event["flat_or_null"] is not expected_flat
                    or (ceremony is not None
                          and event["block_id"] != ceremony["block_id"])):
                _fail()
            ceremony_index += 1
            ceremony = {
                "block_id": event["block_id"], "state": event["state"],
                "qualified": event["state"] == "CEREMONY_QUALIFIED",
                "strategy_cycle_count": 0, "economic_evidence_count": 0,
            }
        elif event["event_type"] == "CANARY_STAGE_BLOCK_STARTED":
            if ceremony is None or ceremony["qualified"] is not True:
                _fail()
            if block is not None and _eligible(block, plan, occurred):
                block["status"] = "STAGE_ELIGIBLE_AWAITING_APPROVAL"
            block = _new_block(event, plan, block)
        elif block is None:
            _fail()
        elif event["event_type"] == "CANARY_EQUITY_RECONCILED":
            _apply_equity(block, event, plan["canary_ladder"][block["stage"]])
        else:
            _apply_cycle(block, event)
    if block is not None and _eligible(block, plan, now_value):
        block["status"] = "STAGE_ELIGIBLE_AWAITING_APPROVAL"
    if block is not None:
        block.pop("cycle_ids")
    document = {
        "$schema": "./challenger-replacement-canary-projection-v1.schema.json",
        "schema_version": "1.0.0", "projection_id": "",
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "observed_through": now, "ceremony": ceremony,
        "stage_block_or_null": block, "authority": dict(_AUTHORITY),
    }
    document["projection_id"] = _projection_id(document)
    return (canonical_json(document) + "\n").encode()
def project_challenger_replacement_canary(*, event_root, plan, build_identity,
                                           now):
    """Project only from the retained canonical event-root capability."""
    try:
        if (not isinstance(event_root, ChallengerReplacementEventRoot)
                or not isinstance(build_identity, Mapping)):
            raise ValueError
        replay = replay_challenger_replacement_events(event_root)
        expected_build = business_hash(build_identity)
        events = []
        for event in replay.events:
            outer = json.loads(event.final_bytes.decode("utf-8"))
            payload = _strict_json_bytes(base64.b64decode(
                outer["payload_bytes_base64"], validate=True,
            ))
            if (outer["plan_hash"] != plan["plan_hash"]
                    or outer["build_identity_hash"] != expected_build
                    or payload.get("event_type") != outer["event_type"]
                    or payload.get("occurred_at") != outer["recorded_at"]
                    or payload.get("block_id") != outer["slot_id"]):
                raise ValueError
            events.append(payload)
        event_root.validate()
        return _project_challenger_replacement_canary(
            events=tuple(events), plan=plan, now=now,
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ChallengerReplacementCanaryControllerError): raise
        _fail("CHALLENGER_REPLACEMENT_CANARY_CANONICAL_AUTHORITY_INVALID", error)
def load_challenger_replacement_canary_projection_bytes(data, *, plan):
    """Strictly replay one canonical Canary projection."""
    try:
        if not isinstance(data, bytes) or not data.endswith(b"\n"):
            raise ValueError
        document = _strict_json_bytes(data[:-1])
        schema = json.loads(resources.files("crypto_quant").joinpath(
            "schemas", _SCHEMA,
        ).read_text(encoding="utf-8"))
        if (canonical_json(document).encode() != data[:-1]
                or tuple(Draft202012Validator(schema).iter_errors(document))
                or not isinstance(plan, Mapping)
                or dict(plan)
                != build_challenger_replacement_accelerated_canary_plan()
                or document["plan"] != {
                    "plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"],
                } or document["projection_id"] != _projection_id(document)):
            raise ValueError
        return _freeze(document)
    except (
        ChallengerReplacementPlanError, KeyError, TypeError,
        UnicodeDecodeError, ValueError,
    ) as error:
        _fail("CHALLENGER_REPLACEMENT_CANARY_PROJECTION_INVALID", error)
def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
