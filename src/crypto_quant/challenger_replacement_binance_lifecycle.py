"""Fixture-only Binance lifecycle evidence without operational authority."""

import copy
from dataclasses import dataclass
import json
from typing import Mapping, Optional, Tuple

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_simulation import (
    ChallengerReplacementSimulationError,
    _simulate_challenger_replacement_v072_transition,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_V072_BUILD_VERSION = ("v0.72.0-fixture", "0.72.0", "1.66.0")
_HASH_KEYS = (
    "peeled_commit",
    "build_input_tree_hash",
    "manifest_hash",
    "manifest_file_sha256",
)
_BUILD_KEYS = {
    "release_tag",
    "peeled_commit",
    "package_version",
    "manifest_version",
    "build_input_tree_hash",
    "manifest_hash",
    "manifest_file_sha256",
}
_PAYLOAD_KEYS = {
    "NO_INTENT_RECONCILED": {"action", "reason_code"},
    "INTENT_PREPARED": {
        "product",
        "side",
        "reduce_only",
        "order_type",
        "quantity",
        "approved_notional",
        "instrument_metadata_hash",
    },
    "ATTEMPT_SUBMITTED_FIXTURE": {"client_order_id"},
    "ORDER_ACKNOWLEDGED_FIXTURE": {"client_order_id"},
    "FILL_OBSERVED_FIXTURE": {
        "fill_id",
        "quantity",
        "price",
        "notional",
        "fee_asset",
        "fee",
        "cumulative_filled_quantity",
    },
    "ORDER_UNKNOWN_FIXTURE": {
        "reason_code",
        "last_known_cumulative_filled_quantity",
    },
    "ORDER_RECONCILED_FIXTURE": {
        "terminal_state",
        "cumulative_filled_quantity",
        "average_fill_price_or_null",
        "cumulative_fee",
    },
    "STOP_INTENT_PREPARED": {
        "stop_intent_id",
        "side",
        "reduce_only",
        "quantity",
        "trigger_price",
        "order_type",
    },
    "STOP_ACKNOWLEDGED_FIXTURE": {
        "stop_intent_id",
        "stop_client_order_id",
    },
    "STOP_CANCEL_REQUESTED_FIXTURE": {"stop_intent_id"},
    "STOP_CANCEL_ACKNOWLEDGED_FIXTURE": {"stop_intent_id"},
    "STOP_TRIGGERED_FIXTURE": {
        "stop_intent_id",
        "bar_open",
        "bar_high",
        "bar_low",
        "gap_reference",
    },
    "LIFECYCLE_RECONCILED_FIXTURE": {
        "engine_projection_hash",
        "venue_projection_hash",
        "ledger_projection_hash",
    },
    "LIFECYCLE_FAILED_CLOSED": {
        "reason_code",
        "position_certainty",
        "unresolved_intent_ids",
    },
}
_NULL_ID_EVENTS = {
    "NO_INTENT_RECONCILED",
    "LIFECYCLE_RECONCILED_FIXTURE",
    "LIFECYCLE_FAILED_CLOSED",
}


class ChallengerReplacementLifecycleError(ValueError):
    """The fixture lifecycle could not establish its frozen identity."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class LifecycleEvent:
    ordinal: int
    event_type: str
    event_hash: str
    parent_event_hash_or_null: Optional[str]
    intent_id_or_null: Optional[str]
    attempt_id_or_null: Optional[str]
    payload_bytes: bytes


@dataclass(frozen=True)
class ChallengerReplacementLifecycleResult:
    source_bytes: bytes
    previous_snapshot_bytes: bytes
    plan_identity_bytes: bytes
    contract_identity_bytes: bytes
    build_identity_bytes: bytes
    decision_bytes: bytes
    accounting_bytes: bytes
    next_snapshot_bytes: bytes
    lifecycle_events: Tuple[LifecycleEvent, ...]
    status: str
    operationally_complete: bool
    reason_code_or_null: Optional[str]


def _invalid(reason="CHALLENGER_REPLACEMENT_LIFECYCLE_IDENTITY_INVALID"):
    raise ChallengerReplacementLifecycleError(reason)


def _canonical_bytes(value) -> bytes:
    return canonical_json(value).encode("utf-8")


def _valid_v072_build(value) -> bool:
    if not isinstance(value, Mapping) or set(value) != _BUILD_KEYS:
        return False
    if (
        value.get("release_tag"),
        value.get("package_version"),
        value.get("manifest_version"),
    ) != _V072_BUILD_VERSION:
        return False
    for key in _HASH_KEYS:
        item = value.get(key)
        expected = 40 if key == "peeled_commit" else 64
        if (
            not isinstance(item, str)
            or len(item) != expected
            or any(character not in "0123456789abcdef" for character in item)
        ):
            return False
    return True


def _append_event(
    events,
    *,
    event_type,
    payload,
    intent_id_or_null=None,
    attempt_id_or_null=None,
):
    if event_type not in _PAYLOAD_KEYS or set(payload) != _PAYLOAD_KEYS[event_type]:
        _invalid("CHALLENGER_REPLACEMENT_LIFECYCLE_EVENT_INVALID")
    if event_type in _NULL_ID_EVENTS:
        if intent_id_or_null is not None or attempt_id_or_null is not None:
            _invalid("CHALLENGER_REPLACEMENT_LIFECYCLE_EVENT_INVALID")
    ordinal = len(events) + 1
    parent = None if not events else events[-1].event_hash
    body = {
        "ordinal": ordinal,
        "event_type": event_type,
        "parent_event_hash_or_null": parent,
        "intent_id_or_null": intent_id_or_null,
        "attempt_id_or_null": attempt_id_or_null,
        "payload": payload,
    }
    event = LifecycleEvent(
        ordinal=ordinal,
        event_type=event_type,
        event_hash=business_hash(body),
        parent_event_hash_or_null=parent,
        intent_id_or_null=intent_id_or_null,
        attempt_id_or_null=attempt_id_or_null,
        payload_bytes=_canonical_bytes(payload),
    )
    events.append(event)


def _intent_identity(*, source, plan, contract, decision, accounting):
    action = decision["action"]
    product = "spot" if "SPOT" in action else "perpetual"
    side = "BUY" if action == "OPEN_SPOT_LONG" else "SELL"
    metadata = source["instruments"][product]
    identity = {
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
        "simulation_contract_id": contract["contract_id"],
        "simulation_contract_hash": contract["contract_hash"],
        "opportunity_id": source["opportunity"]["opportunity_id"],
        "decision_hash": decision["decision_hash"],
        "position_before": decision["position_before"],
        "action": action,
        "product_or_null": product,
        "side_or_null": side,
        "reduce_only": False,
        "approved_quantity": accounting["quantity"],
        "approved_notional": accounting["notional"],
        "instrument_metadata_hash_or_null": metadata["metadata_hash"],
    }
    intent_id = stable_id("replacement_intent", identity)
    attempt_id = stable_id(
        "replacement_attempt", {"intent_id": intent_id, "attempt_ordinal": 1}
    )
    client_id = stable_id(
        "replacement_client", {"intent_id": intent_id, "product": product}
    )
    return product, side, metadata, intent_id, attempt_id, client_id


def _event_documents(events):
    return [
        {
            "ordinal": event.ordinal,
            "event_type": event.event_type,
            "event_hash": event.event_hash,
            "parent_event_hash_or_null": event.parent_event_hash_or_null,
            "intent_id_or_null": event.intent_id_or_null,
            "attempt_id_or_null": event.attempt_id_or_null,
            "payload": json.loads(event.payload_bytes),
        }
        for event in events
    ]


def _append_reconciled(events, *, accounting, next_snapshot):
    _append_event(
        events,
        event_type="LIFECYCLE_RECONCILED_FIXTURE",
        payload={
            "engine_projection_hash": business_hash(
                {"events": _event_documents(events)}
            ),
            "venue_projection_hash": business_hash(
                {"fill": accounting, "position": next_snapshot["position_state"]}
            ),
            "ledger_projection_hash": business_hash(
                {"accounting": accounting, "next_snapshot": next_snapshot}
            ),
        },
    )


def _append_open(events, *, source, plan, contract, transition):
    decision = transition["decision"]
    accounting = transition["accounting"]
    product, side, metadata, intent_id, attempt_id, client_id = _intent_identity(
        source=source,
        plan=plan,
        contract=contract,
        decision=decision,
        accounting=accounting,
    )
    common = {"intent_id_or_null": intent_id}
    _append_event(
        events,
        event_type="INTENT_PREPARED",
        payload={
            "product": product,
            "side": side,
            "reduce_only": False,
            "order_type": "MARKET",
            "quantity": accounting["quantity"],
            "approved_notional": accounting["notional"],
            "instrument_metadata_hash": metadata["metadata_hash"],
        },
        **common,
    )
    for event_type in (
        "ATTEMPT_SUBMITTED_FIXTURE",
        "ORDER_ACKNOWLEDGED_FIXTURE",
    ):
        _append_event(
            events,
            event_type=event_type,
            payload={"client_order_id": client_id},
            intent_id_or_null=intent_id,
            attempt_id_or_null=attempt_id,
        )
    fill_id = stable_id(
        "replacement_fill",
        {"attempt_id": attempt_id, "cumulative_quantity": accounting["quantity"]},
    )
    _append_event(
        events,
        event_type="FILL_OBSERVED_FIXTURE",
        payload={
            "fill_id": fill_id,
            "quantity": accounting["quantity"],
            "price": accounting["fill_price"],
            "notional": accounting["notional"],
            "fee_asset": "USDT",
            "fee": accounting["fee"],
            "cumulative_filled_quantity": accounting["quantity"],
        },
        intent_id_or_null=intent_id,
        attempt_id_or_null=attempt_id,
    )
    _append_event(
        events,
        event_type="ORDER_RECONCILED_FIXTURE",
        payload={
            "terminal_state": "FILLED",
            "cumulative_filled_quantity": accounting["quantity"],
            "average_fill_price_or_null": accounting["fill_price"],
            "cumulative_fee": accounting["fee"],
        },
        intent_id_or_null=intent_id,
        attempt_id_or_null=attempt_id,
    )
    terms = transition["protective_stop_terms_or_null"]
    stop_intent_id = stable_id(
        "replacement_stop",
        {
            "protected_intent_id": intent_id,
            "quantity": terms["quantity"],
            "trigger_price": terms["trigger_price"],
            "stop_ordinal": 1,
        },
    )
    stop_attempt_id = stable_id(
        "replacement_attempt",
        {"intent_id": stop_intent_id, "attempt_ordinal": 1},
    )
    stop_client_id = stable_id(
        "replacement_client",
        {"intent_id": stop_intent_id, "product": product},
    )
    _append_event(
        events,
        event_type="STOP_INTENT_PREPARED",
        payload={
            "stop_intent_id": stop_intent_id,
            "side": terms["side"],
            "reduce_only": terms["reduce_only"],
            "quantity": terms["quantity"],
            "trigger_price": terms["trigger_price"],
            "order_type": "STOP_MARKET",
        },
        intent_id_or_null=stop_intent_id,
    )
    _append_event(
        events,
        event_type="STOP_ACKNOWLEDGED_FIXTURE",
        payload={
            "stop_intent_id": stop_intent_id,
            "stop_client_order_id": stop_client_id,
        },
        intent_id_or_null=stop_intent_id,
        attempt_id_or_null=stop_attempt_id,
    )
    snapshot = copy.deepcopy(transition["next_snapshot"])
    snapshot["protective_stop_or_null"] = {
        "stop_intent_id": stop_intent_id,
        "stop_attempt_id": stop_attempt_id,
        "stop_client_order_id": stop_client_id,
        **terms,
        "status": "CONFIRMED_FIXTURE",
    }
    snapshot["snapshot_hash"] = artifact_self_hash(snapshot, "snapshot_hash")
    return snapshot


def _close_identity(*, source, previous, plan, contract, decision, accounting):
    product = "spot" if previous["position_state"] == "SPOT_LONG" else "perpetual"
    side = "SELL" if product == "spot" else "BUY"
    reduce_only = product == "perpetual"
    identity = {
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
        "simulation_contract_id": contract["contract_id"],
        "simulation_contract_hash": contract["contract_hash"],
        "opportunity_id": source["opportunity"]["opportunity_id"],
        "decision_hash": decision["decision_hash"],
        "position_before": decision["position_before"],
        "action": decision["action"],
        "product_or_null": product,
        "side_or_null": side,
        "reduce_only": reduce_only,
        "approved_quantity": accounting["quantity"],
        "approved_notional": accounting["notional"],
        "instrument_metadata_hash_or_null": previous["instrument_metadata_hash_or_null"],
    }
    intent_id = stable_id("replacement_intent", identity)
    attempt_id = stable_id(
        "replacement_attempt", {"intent_id": intent_id, "attempt_ordinal": 1}
    )
    client_id = stable_id(
        "replacement_client", {"intent_id": intent_id, "product": product}
    )
    return product, side, reduce_only, intent_id, attempt_id, client_id


def _append_fill_and_reconcile(events, *, accounting, intent_id, attempt_id):
    fill_id = stable_id(
        "replacement_fill",
        {"attempt_id": attempt_id, "cumulative_quantity": accounting["quantity"]},
    )
    _append_event(
        events,
        event_type="FILL_OBSERVED_FIXTURE",
        payload={
            "fill_id": fill_id,
            "quantity": accounting["quantity"],
            "price": accounting["fill_price"],
            "notional": accounting["notional"],
            "fee_asset": "USDT",
            "fee": accounting["fee"],
            "cumulative_filled_quantity": accounting["quantity"],
        },
        intent_id_or_null=intent_id,
        attempt_id_or_null=attempt_id,
    )
    _append_event(
        events,
        event_type="ORDER_RECONCILED_FIXTURE",
        payload={
            "terminal_state": "FILLED",
            "cumulative_filled_quantity": accounting["quantity"],
            "average_fill_price_or_null": accounting["fill_price"],
            "cumulative_fee": accounting["fee"],
        },
        intent_id_or_null=intent_id,
        attempt_id_or_null=attempt_id,
    )


def _append_close(events, *, source, previous, plan, contract, transition):
    decision, accounting = transition["decision"], transition["accounting"]
    triggered = transition["triggered_stop_or_null"]
    if triggered is not None:
        intent_id = triggered["stop_intent_id"]
        attempt_id = triggered["stop_attempt_id"]
        _append_event(
            events,
            event_type="STOP_TRIGGERED_FIXTURE",
            payload={
                "stop_intent_id": intent_id,
                "bar_open": triggered["bar_open"],
                "bar_high": triggered["bar_high"],
                "bar_low": triggered["bar_low"],
                "gap_reference": triggered["gap_reference"],
            },
            intent_id_or_null=intent_id,
            attempt_id_or_null=attempt_id,
        )
        _append_fill_and_reconcile(
            events,
            accounting=accounting,
            intent_id=intent_id,
            attempt_id=attempt_id,
        )
        return transition["next_snapshot"]

    old_stop = previous["protective_stop_or_null"]
    for event_type in (
        "STOP_CANCEL_REQUESTED_FIXTURE",
        "STOP_CANCEL_ACKNOWLEDGED_FIXTURE",
    ):
        _append_event(
            events,
            event_type=event_type,
            payload={"stop_intent_id": old_stop["stop_intent_id"]},
            intent_id_or_null=old_stop["stop_intent_id"],
            attempt_id_or_null=old_stop["stop_attempt_id"],
        )
    product, side, reduce_only, intent_id, attempt_id, client_id = _close_identity(
        source=source,
        previous=previous,
        plan=plan,
        contract=contract,
        decision=decision,
        accounting=accounting,
    )
    _append_event(
        events,
        event_type="INTENT_PREPARED",
        payload={
            "product": product,
            "side": side,
            "reduce_only": reduce_only,
            "order_type": "MARKET",
            "quantity": accounting["quantity"],
            "approved_notional": accounting["notional"],
            "instrument_metadata_hash": previous["instrument_metadata_hash_or_null"],
        },
        intent_id_or_null=intent_id,
    )
    for event_type in (
        "ATTEMPT_SUBMITTED_FIXTURE",
        "ORDER_ACKNOWLEDGED_FIXTURE",
    ):
        _append_event(
            events,
            event_type=event_type,
            payload={"client_order_id": client_id},
            intent_id_or_null=intent_id,
            attempt_id_or_null=attempt_id,
        )
    _append_fill_and_reconcile(
        events,
        accounting=accounting,
        intent_id=intent_id,
        attempt_id=attempt_id,
    )
    return transition["next_snapshot"]


def simulate_challenger_replacement_binance_lifecycle(
    *, source, previous_projection, plan, contract, build_identity
) -> ChallengerReplacementLifecycleResult:
    """Produce no-intent fixture lifecycle evidence for one v0.72 input."""

    if (
        not _valid_v072_build(build_identity)
        or not isinstance(source, Mapping)
        or source.get("build_identity") != dict(build_identity)
    ):
        _invalid()
    try:
        transition = _simulate_challenger_replacement_v072_transition(
            source=source,
            previous_projection=previous_projection,
            plan=plan,
            contract=contract,
            build_identity=build_identity,
        )
        decision = transition["decision"]
        if decision["action"] not in {
            "HOLD_FLAT",
            "HOLD_SPOT_LONG",
            "HOLD_PERP_SHORT",
            "OPEN_SPOT_LONG",
            "OPEN_PERP_SHORT",
            "CLOSE_SPOT_LONG",
            "CLOSE_PERP_SHORT",
            "RISK_FLATTEN",
            "STOP_CLOSE_SPOT_LONG",
            "STOP_CLOSE_PERP_SHORT",
        }:
            _invalid("CHALLENGER_REPLACEMENT_LIFECYCLE_ACTION_UNSUPPORTED")
        events = []
        next_snapshot = transition["next_snapshot"]
        if decision["action"] in {"OPEN_SPOT_LONG", "OPEN_PERP_SHORT"}:
            next_snapshot = _append_open(
                events,
                source=source,
                plan=plan,
                contract=contract,
                transition=transition,
            )
        elif decision["action"] in {
            "CLOSE_SPOT_LONG",
            "CLOSE_PERP_SHORT",
            "RISK_FLATTEN",
            "STOP_CLOSE_SPOT_LONG",
            "STOP_CLOSE_PERP_SHORT",
        }:
            next_snapshot = _append_close(
                events,
                source=source,
                previous=previous_projection,
                plan=plan,
                contract=contract,
                transition=transition,
            )
        else:
            _append_event(
                events,
                event_type="NO_INTENT_RECONCILED",
                payload={
                    "action": decision["action"],
                    "reason_code": decision["reason_code"],
                },
            )
        _append_reconciled(
            events,
            accounting=transition["accounting"],
            next_snapshot=next_snapshot,
        )
        plan_identity = {
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
        }
        contract_identity = {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
        }
        return ChallengerReplacementLifecycleResult(
            source_bytes=_canonical_bytes(source),
            previous_snapshot_bytes=_canonical_bytes(previous_projection),
            plan_identity_bytes=_canonical_bytes(plan_identity),
            contract_identity_bytes=_canonical_bytes(contract_identity),
            build_identity_bytes=_canonical_bytes(build_identity),
            decision_bytes=_canonical_bytes(decision),
            accounting_bytes=_canonical_bytes(transition["accounting"]),
            next_snapshot_bytes=_canonical_bytes(next_snapshot),
            lifecycle_events=tuple(events),
            status="RECONCILED_FIXTURE",
            operationally_complete=True,
            reason_code_or_null=None,
        )
    except ChallengerReplacementLifecycleError:
        raise
    except (ChallengerReplacementSimulationError, CanonicalizationError, KeyError,
            TypeError, ValueError) as error:
        raise ChallengerReplacementLifecycleError(
            "CHALLENGER_REPLACEMENT_LIFECYCLE_IDENTITY_INVALID"
        ) from error
