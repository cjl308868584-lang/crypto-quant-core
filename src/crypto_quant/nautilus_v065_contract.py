"""Directional request/result boundary for the v0.65 Nautilus fixture spike."""

import copy
import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_plan import ChallengerReplacementPlanError, _strict_json_bytes
from .errors import CanonicalizationError
from .nautilus_v065_plan import NautilusV065PlanError, _read_plan_bytes


_REQUEST_SCHEMA = "nautilus-sandbox-request-v2.schema.json"
_RESULT_SCHEMA = "nautilus-sandbox-result-v2.schema.json"
_ZERO = "0" * 64
_SCENARIOS = (
    "IMMEDIATE_FULL",
    "PARTIAL_THEN_FULL",
    "BELOW_MINIMUM_REJECTED",
    "FRESH_PROCESS_REPLAY",
)


class NautilusV065ContractError(ValueError):
    """The frozen directional contract failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=2)
def _validator(name: str) -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", name)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _self_hash(value: Mapping[str, Any], *excluded: str) -> str:
    material = copy.deepcopy(dict(value))
    for field in excluded:
        if field in material:
            material[field] = _ZERO if not field.endswith("_id") else field.removesuffix("_id") + "_" + _ZERO
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def _event(value: Mapping[str, Any]) -> Dict[str, Any]:
    event = dict(value)
    event["event_hash"] = _ZERO
    event["event_hash"] = _self_hash(event, "event_hash")
    return event


def _closed_bars() -> list[Dict[str, Any]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = []
    closes = [
        "1800", "1810", "1825", "1815", "1830", "1845", "1860",
        "1850", "1875", "1890", "1880", "1905", "1920", "1935",
        "1925", "1950", "1965", "1980", "1970", "1990", "2000",
    ]
    for index, close in enumerate(closes, 1):
        close_value = int(close)
        opened = close_value - 5
        timestamp = start + timedelta(hours=4 * (index - 1))
        bars.append(
            _event(
                {
                    "sequence": index,
                    "bar_type": "ETHUSDT-4H-CLOSED",
                    "open_time": timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "close_time": (timestamp + timedelta(hours=4)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "open": str(opened),
                    "high": str(close_value + 12),
                    "low": str(opened - 10),
                    "close": close,
                    "volume": str(1000 + index * 10),
                }
            )
        )
    return bars


def _market_event(sequence: int, kind: str, occurred_at: str, **values: str) -> Dict[str, Any]:
    return _event({"sequence": sequence, "kind": kind, "occurred_at": occurred_at, **values})


def _scenarios(decision_id: str, target_id: str, risk_id: str) -> list[Dict[str, Any]]:
    immediate = [
        _market_event(1, "BBO", "2026-01-04T12:00:01.000Z", bid="2000", ask="2000.1", bid_size="10", ask_size="10"),
        _market_event(2, "TRADE", "2026-01-04T12:00:02.000Z", price="2000.1", quantity="0.05", aggressor_side="BUY"),
    ]
    partial = [
        _market_event(1, "BBO", "2026-01-04T12:00:01.000Z", bid="2000", ask="2000.1", bid_size="10", ask_size="0.02"),
        _market_event(2, "TRADE", "2026-01-04T12:00:02.000Z", price="2000.1", quantity="0.02", aggressor_side="BUY"),
        _market_event(3, "BBO", "2026-01-04T12:00:03.000Z", bid="2000.15", ask="2000.2", bid_size="10", ask_size="10"),
        _market_event(4, "TRADE", "2026-01-04T12:00:04.000Z", price="2000.2", quantity="0.03", aggressor_side="BUY"),
    ]
    below = [_market_event(1, "BBO", "2026-01-04T12:00:01.000Z", bid="2000", ask="2000.1", bid_size="10", ask_size="10")]
    specifications = (
        ("IMMEDIATE_FULL", "0.05", immediate),
        ("PARTIAL_THEN_FULL", "0.05", partial),
        ("BELOW_MINIMUM_REJECTED", "0.001", below),
        ("FRESH_PROCESS_REPLAY", "0.05", copy.deepcopy(immediate)),
    )
    result = []
    for name, quantity, events in specifications:
        scenario = {
            "scenario": name,
            "scenario_hash": _ZERO,
            "order_intent": {
                "decision_id": decision_id,
                "target_id": target_id,
                "risk_id": risk_id,
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": quantity,
            },
            "events": events,
        }
        scenario["scenario_hash"] = _self_hash(scenario, "scenario_hash")
        result.append(scenario)
    return result


def build_nautilus_v065_request(
    *,
    plan_id: str,
    plan_hash: str,
    supply_chain_receipt_id: str,
    supply_chain_receipt_hash: str,
) -> Dict[str, Any]:
    """Build the only allowed offline ETHUSDT 4H sandbox request."""

    if not (
        isinstance(plan_id, str) and plan_id.startswith("nautilus_v065_plan_")
        and isinstance(supply_chain_receipt_id, str) and supply_chain_receipt_id.startswith("nautilus_v065_supply_chain_")
        and all(isinstance(value, str) and len(value.rsplit("_", 1)[-1]) == 64 for value in (plan_id, supply_chain_receipt_id))
        and all(isinstance(value, str) and len(value) == 64 for value in (plan_hash, supply_chain_receipt_hash))
    ):
        raise NautilusV065ContractError("NAUTILUS_V065_BINDING_INVALID")
    decision = {
        "decision_id": "decision_" + _ZERO,
        "action": "SET_TARGET",
        "direction": "LONG",
        "instrument_id": "BINANCE:SPOT:ETHUSDT",
        "decided_at": "2026-01-04T12:00:00.000Z",
    }
    decision["decision_id"] = stable_id("decision", decision)
    target = {
        "target_id": "target_" + _ZERO,
        "decision_id": decision["decision_id"],
        "side": "BUY",
        "quantity": "0.05",
        "target_position_eth": "0.05",
    }
    target["target_id"] = stable_id("target", target)
    risk = {
        "risk_id": "risk_" + _ZERO,
        "target_id": target["target_id"],
        "authorized": True,
        "max_quantity": "0.05",
        "max_notional_usdt": "101",
        "short_allowed": False,
    }
    risk["risk_id"] = stable_id("risk", risk)
    request: Dict[str, Any] = {
        "$schema": "./nautilus-sandbox-request-v2.schema.json",
        "schema_version": "2.0.0",
        "request_id": "nautilus_v065_request_" + _ZERO,
        "request_hash": _ZERO,
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        "supply_chain_receipt_id": supply_chain_receipt_id,
        "supply_chain_receipt_hash": supply_chain_receipt_hash,
        "fixture_id": "ethusdt_4h_v2",
        "fixture_hash": _ZERO,
        "instrument": {
            "instrument_id": "BINANCE:SPOT:ETHUSDT",
            "symbol": "ETHUSDT",
            "base_asset": "ETH",
            "quote_asset": "USDT",
            "price_tick": "0.01",
            "quantity_step": "0.0001",
            "min_quantity": "0.0001",
            "min_notional": "5",
            "price_precision": 2,
            "quantity_precision": 4,
            "maker_fee": "0.001",
            "taker_fee": "0.001",
        },
        "starting_state": {"cash_usdt": "1000", "position_eth": "0"},
        "decision_authority": {"decision": decision, "target": target, "risk": risk},
        "closed_bars": _closed_bars(),
        "scenarios": _scenarios(decision["decision_id"], target["target_id"], risk["risk_id"]),
        "authority_counters": {
            "credential_reads": 0,
            "network_requests": 0,
            "broker_requests": 0,
            "orders_outside_fixture": 0,
            "production_state_writes": 0,
        },
    }
    request["fixture_hash"] = hashlib.sha256(canonical_json({key: request[key] for key in ("instrument", "starting_state", "decision_authority", "closed_bars", "scenarios")}).encode()).hexdigest()
    request["request_id"] = "nautilus_v065_request_" + _self_hash(request, "request_id", "request_hash")
    request["request_hash"] = _self_hash(request, "request_id", "request_hash")
    if tuple(_validator(_REQUEST_SCHEMA).iter_errors(request)):
        raise NautilusV065ContractError("NAUTILUS_V065_REQUEST_SCHEMA_INVALID")
    return copy.deepcopy(request)


def _result_event(sequence: int, kind: str, **values: str) -> Dict[str, Any]:
    return _event({"sequence": sequence, "kind": kind, **values})


def build_nautilus_v065_current_reference(*, request: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the frozen current-core comparison side without executing an engine."""

    verified_request = _verify_request(dict(request))
    values = {
        "IMMEDIATE_FULL": ("FILLED", "0.05", "2000.1", "0.100005", "899.894995", "0.05", "0", "-0.005", "-0.105005"),
        "PARTIAL_THEN_FULL": ("FILLED", "0.05", "2000.16", "0.100008", "899.891992", "0.05", "0", "-0.0005", "-0.100508"),
        "BELOW_MINIMUM_REJECTED": ("REJECTED_MIN_NOTIONAL", "0", "0", "0", "1000", "0", "0", "0", "0"),
        "FRESH_PROCESS_REPLAY": ("FILLED", "0.05", "2000.1", "0.100005", "899.894995", "0.05", "0", "-0.005", "-0.105005"),
    }
    scenario_results = []
    for scenario in verified_request["scenarios"]:
        status_value, filled, average, fee, cash, position, realized, unrealized, net = values[scenario["scenario"]]
        events = [_result_event(1, "ORDER_ACCEPTED" if filled != "0" else "ORDER_REJECTED", status=status_value)]
        if scenario["scenario"] == "PARTIAL_THEN_FULL":
            events.extend([_result_event(2, "FILL", price="2000.1", quantity="0.02", fee_usdt="0.040002"), _result_event(3, "FILL", price="2000.2", quantity="0.03", fee_usdt="0.060006")])
        elif filled != "0":
            events.append(_result_event(2, "FILL", price="2000.1", quantity="0.05", fee_usdt="0.100005"))
        scenario_results.append({
            "scenario": scenario["scenario"],
            "scenario_hash": scenario["scenario_hash"],
            "status": status_value,
            "requested_quantity": scenario["order_intent"]["quantity"],
            "filled_quantity": filled,
            "average_price": average,
            "fee_usdt": fee,
            "ending_cash_usdt": cash,
            "ending_position_eth": position,
            "realized_pnl_usdt": realized,
            "unrealized_pnl_usdt": unrealized,
            "net_pnl_usdt": net,
            "events": events,
        })
    result: Dict[str, Any] = {
        "$schema": "./nautilus-sandbox-result-v2.schema.json",
        "schema_version": "2.0.0",
        "result_id": "nautilus_v065_result_" + _ZERO,
        "result_hash": _ZERO,
        "request_id": verified_request["request_id"],
        "request_hash": verified_request["request_hash"],
        "engine": "CURRENT_CORE_REFERENCE_V1",
        "scenario_results": scenario_results,
        "fresh_process_replay_verified": True,
        "safety_counters": {
            "credential_reads": 0,
            "network_requests": 0,
            "live_adapter_imports": 0,
            "broker_requests": 0,
            "real_orders": 0,
            "production_state_writes": 0,
            "second_engine_creations": 0,
        },
    }
    digest = _self_hash(result, "result_id", "result_hash")
    result["result_id"] = "nautilus_v065_result_" + digest
    result["result_hash"] = digest
    if tuple(_validator(_RESULT_SCHEMA).iter_errors(result)):
        raise NautilusV065ContractError("NAUTILUS_V065_RESULT_SCHEMA_INVALID")
    return copy.deepcopy(result)


def _read_owner_exact(path: Path) -> bytes:
    requested = Path(path)
    try:
        value = requested.lstat()
        if not stat.S_ISREG(value.st_mode) or value.st_uid != os.geteuid() or value.st_nlink != 1 or stat.S_IMODE(value.st_mode) != 0o600:
            raise NautilusV065ContractError("NAUTILUS_V065_CONTRACT_PATH_INVALID")
        return _read_plan_bytes(requested)
    except NautilusV065ContractError:
        raise
    except (NautilusV065PlanError, OSError, ValueError) as error:
        raise NautilusV065ContractError("NAUTILUS_V065_CONTRACT_PATH_INVALID") from error


def _load(path: Path, schema: str) -> Dict[str, Any]:
    body = _read_owner_exact(path)
    try:
        payload = dict(_strict_json_bytes(body))
        if body != canonical_json(payload).encode("utf-8") + b"\n":
            raise NautilusV065ContractError("NAUTILUS_V065_CONTRACT_NOT_CANONICAL")
    except ChallengerReplacementPlanError as error:
        raise NautilusV065ContractError("NAUTILUS_V065_CONTRACT_JSON_INVALID") from error
    except (CanonicalizationError, RecursionError) as error:
        raise NautilusV065ContractError("NAUTILUS_V065_CONTRACT_JSON_INVALID") from error
    if tuple(_validator(schema).iter_errors(payload)):
        raise NautilusV065ContractError("NAUTILUS_V065_CONTRACT_SCHEMA_INVALID")
    return payload


def _verify_events(events: list[Mapping[str, Any]]) -> None:
    if [item["sequence"] for item in events] != list(range(1, len(events) + 1)):
        raise NautilusV065ContractError("NAUTILUS_V065_EVENT_SEQUENCE_INVALID")
    for event in events:
        if event["event_hash"] != _self_hash(event, "event_hash"):
            raise NautilusV065ContractError("NAUTILUS_V065_EVENT_HASH_INVALID")


def _verify_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    if tuple(_validator(_REQUEST_SCHEMA).iter_errors(payload)):
        raise NautilusV065ContractError("NAUTILUS_V065_REQUEST_SCHEMA_INVALID")
    _verify_events(payload["closed_bars"])
    for scenario in payload["scenarios"]:
        _verify_events(scenario["events"])
        if scenario["scenario_hash"] != _self_hash(scenario, "scenario_hash"):
            raise NautilusV065ContractError("NAUTILUS_V065_SCENARIO_HASH_INVALID")
    expected = build_nautilus_v065_request(
        plan_id=payload["plan_id"], plan_hash=payload["plan_hash"],
        supply_chain_receipt_id=payload["supply_chain_receipt_id"],
        supply_chain_receipt_hash=payload["supply_chain_receipt_hash"],
    )
    if payload != expected:
        raise NautilusV065ContractError("NAUTILUS_V065_REQUEST_SEMANTIC_MISMATCH")
    return copy.deepcopy(payload)


def load_nautilus_v065_request(path: Path) -> Dict[str, Any]:
    return _verify_request(_load(path, _REQUEST_SCHEMA))


def load_nautilus_v065_result(path: Path) -> Dict[str, Any]:
    return verify_nautilus_v065_result(_load(path, _RESULT_SCHEMA))


def verify_nautilus_v065_result(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Verify an already decoded result without performing file I/O."""

    payload = copy.deepcopy(dict(payload))
    if tuple(_validator(_RESULT_SCHEMA).iter_errors(payload)):
        raise NautilusV065ContractError("NAUTILUS_V065_RESULT_SCHEMA_INVALID")
    if [item["scenario"] for item in payload["scenario_results"]] != list(_SCENARIOS):
        raise NautilusV065ContractError("NAUTILUS_V065_RESULT_SCENARIOS_INVALID")
    for item in payload["scenario_results"]:
        _verify_events(item["events"])
    digest = _self_hash(payload, "result_id", "result_hash")
    if payload["result_hash"] != digest or payload["result_id"] != "nautilus_v065_result_" + digest:
        raise NautilusV065ContractError("NAUTILUS_V065_RESULT_HASH_INVALID")
    return copy.deepcopy(payload)
