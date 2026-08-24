"""Fixture-only Binance lifecycle evidence without operational authority."""

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from .canonical import business_hash, canonical_json
from .challenger_replacement_simulation import (
    ChallengerReplacementSimulationError,
    simulate_challenger_replacement_opportunity,
)
from .errors import CanonicalizationError


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
        transition = simulate_challenger_replacement_opportunity(
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
        }:
            _invalid("CHALLENGER_REPLACEMENT_LIFECYCLE_ACTION_UNSUPPORTED")
        events = []
        _append_event(
            events,
            event_type="NO_INTENT_RECONCILED",
            payload={
                "action": decision["action"],
                "reason_code": decision["reason_code"],
            },
        )
        _append_event(
            events,
            event_type="LIFECYCLE_RECONCILED_FIXTURE",
            payload={
                "engine_projection_hash": business_hash(
                    {"decision": decision, "status": "NO_INTENT"}
                ),
                "venue_projection_hash": business_hash(
                    {"position": previous_projection["position_state"]}
                ),
                "ledger_projection_hash": business_hash(
                    {
                        "accounting": transition["accounting"],
                        "next_snapshot": transition["next_snapshot"],
                    }
                ),
            },
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
            next_snapshot_bytes=_canonical_bytes(transition["next_snapshot"]),
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
