"""Fixture-only Binance lifecycle evidence without operational authority."""
import copy, json
from dataclasses import dataclass, replace
from typing import Mapping, Optional, Tuple
from .canonical import business_hash, canonical_decimal, canonical_json, stable_id
from decimal import Decimal, ROUND_CEILING
from .challenger_replacement_simulation import ChallengerReplacementSimulationError, _risk, _simulate_challenger_replacement_v072_transition
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
    "INTENT_PREPARED": {"product", "side", "reduce_only", "order_type", "quantity", "approved_notional", "instrument_metadata_hash"},
    "ATTEMPT_SUBMITTED_FIXTURE": {"client_order_id"},
    "ORDER_ACKNOWLEDGED_FIXTURE": {"client_order_id"},
    "FILL_OBSERVED_FIXTURE": {"fill_id", "quantity", "price", "notional", "fee_asset", "fee", "cumulative_filled_quantity"},
    "ORDER_UNKNOWN_FIXTURE": {"reason_code", "last_known_cumulative_filled_quantity"},
    "ORDER_RECONCILED_FIXTURE": {"terminal_state", "cumulative_filled_quantity", "average_fill_price_or_null", "cumulative_fee"},
    "STOP_INTENT_PREPARED": {"stop_intent_id", "side", "reduce_only", "quantity", "trigger_price", "order_type"},
    "STOP_ACKNOWLEDGED_FIXTURE": {"stop_intent_id", "stop_client_order_id"},
    "STOP_CANCEL_REQUESTED_FIXTURE": {"stop_intent_id"},
    "STOP_CANCEL_ACKNOWLEDGED_FIXTURE": {"stop_intent_id"},
    "STOP_TRIGGERED_FIXTURE": {"stop_intent_id", "bar_open", "bar_high", "bar_low", "gap_reference"},
    "LIFECYCLE_RECONCILED_FIXTURE": {"engine_projection_hash", "venue_projection_hash", "ledger_projection_hash"},
    "LIFECYCLE_FAILED_CLOSED": {"reason_code", "position_certainty", "unresolved_intent_ids"},
}
_NULL_ID_EVENTS = {
    "NO_INTENT_RECONCILED", "LIFECYCLE_RECONCILED_FIXTURE",
    "LIFECYCLE_FAILED_CLOSED",
}
class ChallengerReplacementLifecycleError(ValueError):
    """The fixture lifecycle could not establish its frozen identity."""
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code
@dataclass(frozen=True)
class LifecycleEvent:
    ordinal: int; event_type: str; event_hash: str
    parent_event_hash_or_null: Optional[str]
    intent_id_or_null: Optional[str]; attempt_id_or_null: Optional[str]
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
@dataclass(frozen=True)
class _Projection:
    product_or_null: Optional[str]; signed_quantity: str
    average_price_or_null: Optional[str]; cumulative_fee: str
    funding: str; terminal_state: str
@dataclass(frozen=True)
class LifecycleObservation(_Projection):
    fill_before_ack: bool = False; unknown_reason_or_null: Optional[str] = None
    conflicting_duplicate: bool = False; overfill: bool = False
    stop_confirmed: bool = True
    partial_first_quantity_or_null: Optional[str] = None
    missing_cancel_ack: bool = False; missing_new_stop_ack: bool = False
    second_fill_before_stop_ack: bool = False; old_stop_late_fill: bool = False
    wrong_product_or_side: bool = False; flatten_succeeded: bool = True
@dataclass(frozen=True)
class EngineProjection(_Projection): pass
@dataclass(frozen=True)
class VenueProjection(_Projection): pass
@dataclass(frozen=True)
class LedgerProjection(_Projection): pass
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
def _order_identity(
    *, source, plan, contract, decision, accounting, product, side,
    reduce_only, metadata_hash
):
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
        "instrument_metadata_hash_or_null": metadata_hash,
    }
    intent_id = stable_id("replacement_intent", identity)
    attempt_id = stable_id(
        "replacement_attempt", {"intent_id": intent_id, "attempt_ordinal": 1}
    )
    client_id = stable_id(
        "replacement_client", {"intent_id": intent_id, "product": product}
    )
    return intent_id, attempt_id, client_id
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
def _append_reconciled(events, *, engine, venue, ledger):
    _append_event(
        events,
        event_type="LIFECYCLE_RECONCILED_FIXTURE",
        payload={
            "engine_projection_hash": business_hash(engine),
            "venue_projection_hash": business_hash(venue),
            "ledger_projection_hash": business_hash(ledger),
        },
    )
def _normal_lifecycle_observations(transition, previous_position):
    accounting, snapshot = transition["accounting"], transition["next_snapshot"]
    product = {
        "SPOT_LONG": "spot",
        "PERP_SHORT": "perpetual",
    }.get(snapshot["position_state"])
    return (LifecycleObservation(
        product, snapshot["signed_quantity"], accounting["fill_price"],
        accounting["fee"], accounting["funding_cashflow"], "FILLED",
    ),)
def _rechain_fill_before_ack(events):
    values = list(events)
    fill = next(i for i, event in enumerate(values) if event.event_type == "FILL_OBSERVED_FIXTURE")
    ack = next(i for i, event in enumerate(values) if event.event_type == "ORDER_ACKNOWLEDGED_FIXTURE")
    values.insert(ack, values.pop(fill))
    rebuilt = []
    for event in values: _append_event(rebuilt, event_type=event.event_type, payload=json.loads(event.payload_bytes), intent_id_or_null=event.intent_id_or_null, attempt_id_or_null=event.attempt_id_or_null)
    events[:] = rebuilt
def _rechain_partial(events, item, *, taker_fee, transition, source):
    partial = item.partial_first_quantity_or_null
    prefix = events[:3]
    fill = next(event for event in events if event.event_type == "FILL_OBSERVED_FIXTURE")
    order = next(event for event in events if event.event_type == "ORDER_RECONCILED_FIXTURE")
    stop_prepare = next(event for event in events if event.event_type == "STOP_INTENT_PREPARED")
    stop_ack = next(event for event in events if event.event_type == "STOP_ACKNOWLEDGED_FIXTURE")
    full = json.loads(fill.payload_bytes); full_q = Decimal(full["quantity"]); part_q = Decimal(partial)
    if part_q <= 0 or part_q >= full_q: return "UNRECORDED_OR_CONFLICTING_FILL"
    ratio = part_q / full_q
    part = dict(full); part.update(
        quantity=canonical_decimal(part_q), cumulative_filled_quantity=canonical_decimal(part_q),
        notional=canonical_decimal(Decimal(full["notional"]) * ratio),
        fee=canonical_decimal((Decimal(full["notional"]) * ratio * taker_fee).quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)),
    )
    part["fill_id"] = stable_id("replacement_fill", {"attempt_id": fill.attempt_id_or_null, "cumulative_quantity": part["quantity"]})
    remain = dict(full); remain.update(
        quantity=canonical_decimal(full_q - part_q),
        notional=canonical_decimal(Decimal(full["notional"]) - Decimal(part["notional"])),
        fee=canonical_decimal(((Decimal(full["notional"]) - Decimal(part["notional"])) * taker_fee).quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)),
    )
    final_stop = json.loads(stop_prepare.payload_bytes)
    old_id = stable_id("replacement_stop", {"protected_intent_id": fill.intent_id_or_null, "quantity": partial, "trigger_price": final_stop["trigger_price"], "stop_ordinal": 1})
    old_attempt = stable_id("replacement_attempt", {"intent_id": old_id, "attempt_ordinal": 1})
    old_client = stable_id("replacement_client", {"intent_id": old_id, "product": "spot" if final_stop["side"] == "SELL" else "perpetual"})
    old_stop = {**final_stop, "stop_intent_id": old_id, "quantity": partial}
    rebuilt = []
    for event in prefix: _append_event(rebuilt, event_type=event.event_type, payload=json.loads(event.payload_bytes), intent_id_or_null=event.intent_id_or_null, attempt_id_or_null=event.attempt_id_or_null)
    _append_event(rebuilt, event_type="FILL_OBSERVED_FIXTURE", payload=part, intent_id_or_null=fill.intent_id_or_null, attempt_id_or_null=fill.attempt_id_or_null)
    _append_event(rebuilt, event_type="STOP_INTENT_PREPARED", payload=old_stop, intent_id_or_null=old_id)
    if item.second_fill_before_stop_ack: _append_event(rebuilt, event_type="FILL_OBSERVED_FIXTURE", payload=remain, intent_id_or_null=fill.intent_id_or_null, attempt_id_or_null=fill.attempt_id_or_null)
    _append_event(rebuilt, event_type="STOP_ACKNOWLEDGED_FIXTURE", payload={"stop_intent_id": old_id, "stop_client_order_id": old_client}, intent_id_or_null=old_id, attempt_id_or_null=old_attempt)
    if not item.second_fill_before_stop_ack: _append_event(rebuilt, event_type="FILL_OBSERVED_FIXTURE", payload=remain, intent_id_or_null=fill.intent_id_or_null, attempt_id_or_null=fill.attempt_id_or_null)
    _append_event(rebuilt, event_type="STOP_CANCEL_REQUESTED_FIXTURE", payload={"stop_intent_id": old_id}, intent_id_or_null=old_id, attempt_id_or_null=old_attempt)
    if not item.missing_cancel_ack: _append_event(rebuilt, event_type="STOP_CANCEL_ACKNOWLEDGED_FIXTURE", payload={"stop_intent_id": old_id}, intent_id_or_null=old_id, attempt_id_or_null=old_attempt)
    if item.old_stop_late_fill and not item.missing_cancel_ack: _append_event(rebuilt, event_type="FILL_OBSERVED_FIXTURE", payload=part, intent_id_or_null=old_id, attempt_id_or_null=old_attempt)
    elif not item.missing_cancel_ack:
        _append_event(rebuilt, event_type=stop_prepare.event_type, payload=json.loads(stop_prepare.payload_bytes), intent_id_or_null=stop_prepare.intent_id_or_null, attempt_id_or_null=stop_prepare.attempt_id_or_null)
        if not item.missing_new_stop_ack: _append_event(rebuilt, event_type=stop_ack.event_type, payload=json.loads(stop_ack.payload_bytes), intent_id_or_null=stop_ack.intent_id_or_null, attempt_id_or_null=stop_ack.attempt_id_or_null)
    total_fee = Decimal(part["fee"]) + Decimal(remain["fee"])
    if not any((item.missing_cancel_ack, item.missing_new_stop_ack, item.second_fill_before_stop_ack, item.old_stop_late_fill)):
        order_payload = json.loads(order.payload_bytes); order_payload["cumulative_fee"] = canonical_decimal(total_fee)
        _append_event(rebuilt, event_type=order.event_type, payload=order_payload, intent_id_or_null=order.intent_id_or_null, attempt_id_or_null=order.attempt_id_or_null)
    delta = total_fee - Decimal(transition["accounting"]["fee"])
    transition["accounting"]["fee"] = canonical_decimal(total_fee)
    snapshot = transition["next_snapshot"]
    for name, sign in (("cumulative_fees", 1), ("cash", -1)):
        snapshot[name] = canonical_decimal(Decimal(snapshot[name]) + sign * delta)
    _risk(snapshot, source)
    snapshot["snapshot_hash"] = artifact_self_hash(snapshot, "snapshot_hash")
    events[:] = rebuilt
    return None


def _rechain_ambiguous(events, reason):
    prefix = events[:3]
    intent = next(event for event in prefix if event.event_type == "INTENT_PREPARED")
    attempt = next(event for event in prefix if event.attempt_id_or_null is not None)
    rebuilt = []
    for event in prefix: _append_event(rebuilt, event_type=event.event_type, payload=json.loads(event.payload_bytes), intent_id_or_null=event.intent_id_or_null, attempt_id_or_null=event.attempt_id_or_null)
    _append_event(
        rebuilt, event_type="ORDER_UNKNOWN_FIXTURE",
        payload={"reason_code": reason, "last_known_cumulative_filled_quantity": "0"},
        intent_id_or_null=intent.intent_id_or_null, attempt_id_or_null=attempt.attempt_id_or_null,
    )
    events[:] = rebuilt


def _rechain_conflicting_fill(events, *, overfill, quantity_step, taker_fee):
    prefix = events[:3]; original = next(event for event in events if event.event_type == "FILL_OBSERVED_FIXTURE")
    first = json.loads(original.payload_bytes); second = dict(first)
    if overfill:
        quantity = Decimal(first["cumulative_filled_quantity"]) + quantity_step
        notional = Decimal(first["price"]) * quantity_step
        second.update(quantity=canonical_decimal(quantity_step), cumulative_filled_quantity=canonical_decimal(quantity), notional=canonical_decimal(notional), fee=canonical_decimal((notional * taker_fee).quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)))
        second["fill_id"] = stable_id("replacement_fill", {"attempt_id": original.attempt_id_or_null, "cumulative_quantity": second["cumulative_filled_quantity"]})
    else:
        second["fee"] = canonical_decimal(Decimal(first["fee"]) + Decimal("0.00000001"))
    rebuilt = []
    for event in prefix: _append_event(rebuilt, event_type=event.event_type, payload=json.loads(event.payload_bytes), intent_id_or_null=event.intent_id_or_null, attempt_id_or_null=event.attempt_id_or_null)
    for payload in (first, second):
        _append_event(rebuilt, event_type="FILL_OBSERVED_FIXTURE", payload=payload, intent_id_or_null=original.intent_id_or_null, attempt_id_or_null=original.attempt_id_or_null)
    events[:] = rebuilt
def _projection_values(events, funding="0"):
    intent = next(
        (json.loads(event.payload_bytes) for event in events
         if event.event_type == "INTENT_PREPARED"),
        None,
    )
    fill = next(
        (json.loads(event.payload_bytes) for event in reversed(events)
         if event.event_type == "FILL_OBSERVED_FIXTURE"),
        None,
    )
    terminal = next(
        (json.loads(event.payload_bytes) for event in reversed(events)
         if event.event_type == "ORDER_RECONCILED_FIXTURE"), None,
    )
    if fill is None:
        return None, "0", None, "0", "0", "NO_INTENT"
    opens_position = intent is not None and not intent["reduce_only"] and (
        (intent["product"] == "spot" and intent["side"] == "BUY")
        or (intent["product"] == "perpetual" and intent["side"] == "SELL")
    )
    product = intent["product"] if opens_position else None
    signed = "0" if product is None else (
        "-" + fill["cumulative_filled_quantity"]
        if product == "perpetual" else fill["cumulative_filled_quantity"]
    )
    return product, signed, fill["price"], (terminal or {"cumulative_fee": fill["fee"]})["cumulative_fee"], funding, "FILLED"
def _reduce_engine(events, funding="0"):
    return EngineProjection(*_projection_values(events, funding))
def _reduce_venue(observations, previous_position):
    item = observations[-1]
    return VenueProjection(
        item.product_or_null, item.signed_quantity, item.average_price_or_null,
        item.cumulative_fee, item.funding, item.terminal_state,
    )
def _reduce_ledger(previous_snapshot, accounting_transition):
    accounting, snapshot = (
        accounting_transition["accounting"], accounting_transition["next_snapshot"]
    )
    product = {"SPOT_LONG": "spot", "PERP_SHORT": "perpetual"}.get(
        snapshot["position_state"]
    )
    return LedgerProjection(
        product, snapshot["signed_quantity"], accounting["fill_price"],
        accounting["fee"], accounting["funding_cashflow"], "FILLED",
    )
def _reconcile(events, transition, previous, source):
    if transition["accounting"]["fill_price"] is None:
        snapshot, accounting = transition["next_snapshot"], transition["accounting"]
        values = (
            {"SPOT_LONG": "spot", "PERP_SHORT": "perpetual"}.get(snapshot["position_state"]),
            snapshot["signed_quantity"], None, "0",
            accounting["funding_cashflow"], "NO_INTENT",
        )
        return EngineProjection(*values), VenueProjection(*values), LedgerProjection(*values), None
    observations = _normal_lifecycle_observations(
        transition, previous["position_state"]
    )
    item = observations[0]
    product = "spot" if transition["decision"]["action"].endswith("SPOT_LONG") else "perpetual"
    partial_fault = _rechain_partial(
        events, item,
        taker_fee=Decimal(source["instruments"][product]["metadata"]["taker_fee"]),
        transition=transition, source=source,
    ) if item.partial_first_quantity_or_null is not None else None
    if item.partial_first_quantity_or_null is not None:
        observations = (replace(item, cumulative_fee=transition["accounting"]["fee"]),)
    fault = partial_fault or (
        "UNRESOLVED_UNKNOWN" if item.unknown_reason_or_null in {"TIMEOUT", "DISCONNECT"}
        else "DUPLICATE_ECONOMIC_ORDER" if item.conflicting_duplicate
        else "UNRECORDED_OR_CONFLICTING_FILL" if item.overfill
        else "DISASTER_STOP_MISSING_OR_UNCONFIRMED" if not item.stop_confirmed
        else "DISASTER_STOP_MISSING_OR_UNCONFIRMED" if item.missing_cancel_ack or item.missing_new_stop_ack or item.second_fill_before_stop_ack or not item.flatten_succeeded
        else "UNRECORDED_OR_CONFLICTING_FILL" if item.old_stop_late_fill or item.wrong_product_or_side
        else None
    )
    if item.unknown_reason_or_null in {"TIMEOUT", "DISCONNECT"}:
        _rechain_ambiguous(events, item.unknown_reason_or_null)
    elif item.conflicting_duplicate:
        _rechain_conflicting_fill(events, overfill=False, quantity_step=Decimal("0"), taker_fee=Decimal("0"))
    elif item.overfill:
        _rechain_conflicting_fill(
            events, overfill=True,
            quantity_step=Decimal(source["instruments"][product]["metadata"]["quantity_step"]),
            taker_fee=Decimal(source["instruments"][product]["metadata"]["taker_fee"]),
        )
    elif not item.stop_confirmed:
        events[:] = [event for event in events if event.event_type != "STOP_ACKNOWLEDGED_FIXTURE"]
        rebuilt = []
        for event in events: _append_event(rebuilt, event_type=event.event_type, payload=json.loads(event.payload_bytes), intent_id_or_null=event.intent_id_or_null, attempt_id_or_null=event.attempt_id_or_null)
        events[:] = rebuilt
    if fault is None and item.fill_before_ack:
        _rechain_fill_before_ack(events)
    engine = _reduce_engine(tuple(events), transition["accounting"]["funding_cashflow"])
    venue = _reduce_venue(observations, previous["position_state"])
    ledger = _reduce_ledger(previous, transition)
    values = lambda item: tuple(getattr(item, name) for name in EngineProjection.__dataclass_fields__)
    if fault is None and (
        values(engine) != values(venue) or values(venue) != values(ledger)
    ):
        fault = "LEDGER_POSITION_MISMATCH"
    return engine, venue, ledger, fault
def _append_open(events, *, source, plan, contract, transition):
    decision = transition["decision"]
    accounting = transition["accounting"]
    product = "spot" if decision["action"] == "OPEN_SPOT_LONG" else "perpetual"
    side = "BUY" if product == "spot" else "SELL"
    metadata = source["instruments"][product]
    intent_id, attempt_id, client_id = _order_identity(
        source=source,
        plan=plan,
        contract=contract,
        decision=decision,
        accounting=accounting,
        product=product,
        side=side,
        reduce_only=False,
        metadata_hash=metadata["metadata_hash"],
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
    _append_fill_and_reconcile(events, accounting=accounting, intent_id=intent_id, attempt_id=attempt_id)
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
    product = "spot" if previous["position_state"] == "SPOT_LONG" else "perpetual"
    side, reduce_only = ("SELL", False) if product == "spot" else ("BUY", True)
    intent_id, attempt_id, client_id = _order_identity(
        source=source,
        plan=plan,
        contract=contract,
        decision=decision,
        accounting=accounting,
        product=product,
        side=side,
        reduce_only=reduce_only,
        metadata_hash=previous["instrument_metadata_hash_or_null"],
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
        if decision["action"] not in {"HOLD_FLAT", "HOLD_SPOT_LONG", "HOLD_PERP_SHORT", "OPEN_SPOT_LONG", "OPEN_PERP_SHORT", "CLOSE_SPOT_LONG", "CLOSE_PERP_SHORT", "RISK_FLATTEN", "STOP_CLOSE_SPOT_LONG", "STOP_CLOSE_PERP_SHORT"}:
            _invalid("CHALLENGER_REPLACEMENT_LIFECYCLE_ACTION_UNSUPPORTED")
        events = []
        next_snapshot = transition["next_snapshot"]
        if decision["action"] in {"OPEN_SPOT_LONG", "OPEN_PERP_SHORT"}:
            next_snapshot = _append_open(events, source=source, plan=plan, contract=contract, transition=transition)
        elif decision["action"] in {"CLOSE_SPOT_LONG", "CLOSE_PERP_SHORT", "RISK_FLATTEN", "STOP_CLOSE_SPOT_LONG", "STOP_CLOSE_PERP_SHORT"}:
            next_snapshot = _append_close(events, source=source, previous=previous_projection, plan=plan, contract=contract, transition=transition)
        else:
            _append_event(events, event_type="NO_INTENT_RECONCILED", payload={"action": decision["action"], "reason_code": decision["reason_code"]})
        engine, venue, ledger, failure_reason = _reconcile(
            events, {**transition, "next_snapshot": next_snapshot}, previous_projection,
            source,
        )
        status, reason = "RECONCILED_FIXTURE", None
        if failure_reason is None:
            _append_reconciled(events, engine=engine, venue=venue, ledger=ledger)
        else:
            status, reason = "FAILED_CLOSED", failure_reason
            next_snapshot = copy.deepcopy(next_snapshot)
            next_snapshot["risk_state"] = "STAGE_FAILED_LOCKED"
            unresolved = reason in {
                "UNRESOLVED_UNKNOWN", "DUPLICATE_ECONOMIC_ORDER",
                "UNRECORDED_OR_CONFLICTING_FILL",
            }
            if unresolved:
                intent = next((event.intent_id_or_null for event in events if event.intent_id_or_null is not None), stable_id("replacement_unresolved", {"opportunity_id": source["opportunity"]["opportunity_id"], "reason_code": reason}))
                if reason in {"UNRESOLVED_UNKNOWN", "DUPLICATE_ECONOMIC_ORDER"} or any(
                    event.event_type == "ORDER_UNKNOWN_FIXTURE" for event in events
                ) or len([event for event in events if event.event_type == "FILL_OBSERVED_FIXTURE"]) > 1:
                    next_snapshot = copy.deepcopy(previous_projection)
                    next_snapshot["parent_snapshot_hash_or_null"] = previous_projection["snapshot_hash"]
                    next_snapshot["opportunity_id_or_null"] = source["opportunity"]["opportunity_id"]
                    next_snapshot["risk_state"] = "STAGE_FAILED_LOCKED"
                next_snapshot["position_certainty"] = "UNRESOLVED"
                next_snapshot["unresolved_intent_ids"] = [intent]
            if next_snapshot["position_state"] != "FLAT":
                next_snapshot["protective_stop_or_null"] = None
            next_snapshot["snapshot_hash"] = artifact_self_hash(next_snapshot, "snapshot_hash")
            _append_event(
                events,
                event_type="LIFECYCLE_FAILED_CLOSED",
                payload={
                    "reason_code": reason,
                    "position_certainty": next_snapshot["position_certainty"],
                    "unresolved_intent_ids": next_snapshot["unresolved_intent_ids"],
                },
            )
        plan_identity = {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]}
        contract_identity = {"contract_id": contract["contract_id"], "contract_hash": contract["contract_hash"]}
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
            status=status,
            operationally_complete=status == "RECONCILED_FIXTURE",
            reason_code_or_null=reason,
        )
    except ChallengerReplacementLifecycleError:
        raise
    except (ChallengerReplacementSimulationError, CanonicalizationError, KeyError,
            TypeError, ValueError) as error:
        raise ChallengerReplacementLifecycleError(
            "CHALLENGER_REPLACEMENT_LIFECYCLE_IDENTITY_INVALID"
        ) from error
