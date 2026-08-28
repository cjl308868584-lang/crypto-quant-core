"""Strict tail-blind operations projection for the v3 public runtime."""

import copy
import json
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json
from .challenger_replacement_opportunity_projection import validate_build_identity
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_v3_observer import ChallengerReplacementV3Observation


_AUTHORITY_KEYS = (
    "production_activation", "runtime_install_authorized", "replacement_start_authorized",
    "credentials_allowed", "account_requests_allowed", "broker_requests_allowed",
    "real_orders_allowed", "fund_movement_allowed", "new_risk_authorized",
)


class OperationsProjectionV3Error(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="OPERATIONS_PROJECTION_V3_INVALID"):
    raise OperationsProjectionV3Error(reason)


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", "operations-projection-v3.schema.json"
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _counts(observation):
    event = observation.event_projection
    economic = observation.economic_progress
    try:
        names = ("due", "terminal", "observed", "missed")
        values = {name: economic[name + "_opportunity_count"] for name in names}
        if (
            any(type(value) is not int or value < 0 for value in values.values())
            or values["terminal"] > values["due"]
            or values["observed"] + values["missed"] != values["terminal"]
            or any(event[name + "_opportunity_count"] != values[name]
                   for name in names[1:])
        ):
            _invalid()
        return values
    except (KeyError, TypeError):
        _invalid()


def _document(observation, build_identity):
    try:
        validate_build_identity(build_identity)
        if not isinstance(observation, ChallengerReplacementV3Observation):
            _invalid()
        deployment = observation.deployment
        if deployment.get("build_identity") not in (None, build_identity):
            _invalid("OPERATIONS_PROJECTION_V3_BUILD_MISMATCH")
        authority = deployment.get("authority", {})
        if any(authority.values()):
            _invalid("OPERATIONS_PROJECTION_V3_AUTHORITY_INVALID")
        operational = observation.operational_qualification
        if operational["status"] not in {
            "NOT_STARTED", "ACTIVE", "INTERRUPTED_RECOVERABLE",
            "BLOCK_FAILED", "QUALIFIED",
        } or observation.economic_progress["status"] != "TAIL_BLIND":
            _invalid()
        counts = _counts(observation)
        snapshot = observation.event_projection.get("latest_next_snapshot_or_null")
        simulation = {
            "current_product": "FLAT", "reconciliation_status": "NOT_AVAILABLE",
            "risk_state": "NOT_AVAILABLE", "economic_gap_locked": False,
            "protective_stop_status": "NOT_REQUIRED_FLAT",
        }
        if snapshot is not None:
            simulation = {
                "current_product": snapshot["position_state"],
                "reconciliation_status": snapshot.get(
                    "reconciliation_status", "MATCHED"
                ),
                "risk_state": snapshot["risk_state"],
                "economic_gap_locked": snapshot["economic_gap_locked"],
                "protective_stop_status": (
                    "NOT_REQUIRED_FLAT" if snapshot["position_state"] == "FLAT"
                    else snapshot["protective_stop_or_null"]["status"]
                ),
            }
        health = observation.evidence_health
        status = "FAILED_CLOSED" if health == "FAILED_CLOSED" or operational["status"] == "BLOCK_FAILED" else (
            "DEGRADED" if health != "HEALTHY" or counts["missed"] or
            operational["status"] == "INTERRUPTED_RECOVERABLE" else "HEALTHY")
        value = {
            "$schema": "./operations-projection-v3.schema.json",
            "schema_version": "3.0.0", "status": status,
            "service_and_evidence_health": health,
            "operational_qualification": {
                "status": operational["status"],
                "eligible_continuous_seconds": operational.get("eligible_continuous_seconds", 0),
                "segment_id_or_null": operational.get("final_segment_id_or_null"),
                "reason_codes": copy.deepcopy(operational.get("reason_codes", [])),
            },
            "opportunities": counts,
            "next_required_opportunity": observation.economic_progress.get(
                "next_required_opportunity"
            ),
            "fault_matrix": {
                "status": "VERIFIED",
                "receipt_id_or_null": operational.get("bindings", {}).get("fault_receipt_id"),
                "receipt_hash_or_null": operational.get("bindings", {}).get("fault_receipt_hash"),
            },
            "economic_progress": {key: copy.deepcopy(observation.economic_progress[key])
                                  for key in ("status", "elapsed_complete_days", "evidence_health")},
            "simulation_state": simulation,
            "provenance": {
                "deployment_id_or_null": deployment.get("deployment_id"),
                "deployment_hash_or_null": deployment.get("deployment_hash"),
                "build_identity": copy.deepcopy(dict(build_identity)),
                "start_receipt_id_or_null": (
                    None if observation.start_receipt_or_null is None
                    else observation.start_receipt_or_null.get("receipt_id")
                ),
            },
            "authority": {key: False for key in _AUTHORITY_KEYS},
            "projection_hash": "0" * 64,
        }
        value["projection_hash"] = business_hash({
            "purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V3",
            **{key: item for key, item in value.items() if key != "projection_hash"},
        })
        return value
    except OperationsProjectionV3Error:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise OperationsProjectionV3Error(
            "OPERATIONS_PROJECTION_V3_INVALID"
        ) from error


def build_operations_projection_v3(observation, *, build_identity):
    return copy.deepcopy(_document(observation, build_identity))


def load_operations_projection_v3_bytes(
    data, *, observation=None, build_identity=None
):
    if not isinstance(data, bytes) or not 0 < len(data) <= 1_048_576:
        _invalid("OPERATIONS_PROJECTION_V3_BYTES_INVALID")
    try:
        value = _strict_json_bytes(data)
        if data != canonical_json(value).encode("utf-8"):
            _invalid()
        if observation is None and build_identity is None:
            if (
                tuple(_validator().iter_errors(value))
                or any(value.get("authority", {}).values())
            ):
                _invalid()
            validate_build_identity(value["provenance"]["build_identity"])
            claimed = value["projection_hash"]
            if claimed != business_hash({
                "purpose": "TAIL_BLIND_OPERATIONS_PROJECTION_V3",
                **{key: item for key, item in value.items()
                   if key != "projection_hash"},
            }):
                _invalid()
        elif observation is None or build_identity is None:
            _invalid()
        elif value != _document(observation, build_identity):
            _invalid()
        return copy.deepcopy(value)
    except OperationsProjectionV3Error:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise OperationsProjectionV3Error(
            "OPERATIONS_PROJECTION_V3_BYTES_INVALID"
        ) from error
