"""Pure dual-clock start receipt derived from the first v3 observed event."""

import base64
import copy
import json
from functools import lru_cache
from importlib import resources
from typing import Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_events import (
    ChallengerReplacementEventRootIdentity,
    load_challenger_replacement_event_bytes,
)
from .challenger_replacement_plan import ChallengerReplacementPlanError, _strict_json_bytes
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-v3-start-receipt-v1.schema.json"


class ChallengerReplacementV3StartError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_V3_START_INVALID"):
    raise ChallengerReplacementV3StartError(reason)


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _SCHEMA
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validated_deployment(deployment):
    if (
        not isinstance(deployment, Mapping)
        or deployment.get("deployment_hash")
        != artifact_self_hash(deployment, "deployment_hash")
        or deployment.get("status")
        != "V3_DEPLOYMENT_CANDIDATE_NOT_INSTALLABLE_NOT_ACTIVATED"
        or any(deployment.get("authority", {}).values())
    ):
        _invalid()


def _first_observed(projection, identity):
    if (
        not isinstance(projection, Mapping)
        or not isinstance(identity, ChallengerReplacementEventRootIdentity)
        or not isinstance(projection.get("events"), tuple)
    ):
        _invalid()
    observed = None
    for event in projection["events"]:
        loaded = load_challenger_replacement_event_bytes(event.final_bytes)
        header = json.loads(loaded.final_bytes.decode("utf-8"))
        if (
            header["event_root_device"] != identity.device
            or header["event_root_inode"] != identity.inode
        ):
            _invalid()
        if header["event_type"] != "OPPORTUNITY_OBSERVED":
            continue
        if observed is not None:
            break
        payload = _strict_json_bytes(base64.b64decode(
            header["payload_bytes_base64"], validate=True
        ))
        slot = projection["opportunities"].get(header["slot_id"])
        if (
            not isinstance(slot, Mapping)
            or slot.get("outcome") != "OBSERVED"
            or slot.get("result_evidence", {}).get("evidence_qualification")
            != "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER"
            or payload.get("observed_at") != header["recorded_at"]
            or payload.get("scheduled_for") != slot.get("scheduled_for")
        ):
            _invalid()
        observed = (loaded, header, payload)
    if observed is None:
        _invalid("CHALLENGER_REPLACEMENT_V3_START_NOT_READY")
    return observed


def _document(*, deployment, event_projection, event_root_identity):
    _validated_deployment(deployment)
    if (
        not isinstance(event_root_identity, ChallengerReplacementEventRootIdentity)
        or event_root_identity.absolute_path != deployment["paths"]["event_root"]
        or event_root_identity.mode_octal != "0700"
    ):
        _invalid()
    event, header, payload = _first_observed(
        event_projection, event_root_identity
    )
    document = {
        "$schema": "./" + _SCHEMA, "schema_version": "1.0.0",
        "receipt_id": "", "receipt_hash": "0" * 64,
        "deployment": {
            "deployment_id": deployment["deployment_id"],
            "deployment_hash": deployment["deployment_hash"],
            "executable_core_hash": deployment["executable_core_hash"],
        },
        "plans": copy.deepcopy(deployment["plans"]),
        "shared_opportunity_id": header["slot_id"],
        "shared_event_hash": event.event_hash,
        "operational_start": {"observed_at": payload["observed_at"]},
        "economic_start": {"scheduled_for": payload["scheduled_for"]},
        "event_root_identity": {
            "absolute_path": event_root_identity.absolute_path,
            "device": event_root_identity.device,
            "inode": event_root_identity.inode,
            "uid": event_root_identity.uid,
            "mode_octal": event_root_identity.mode_octal,
        },
        "authority": {
            "production_activation": False,
            "credentials_used": False,
            "account_requests": 0,
            "orders_submitted_to_venue": 0,
            "fund_movement": 0,
        },
        "status": "V3_FIRST_NATURAL_OBSERVED_BOUND_NOT_ACTIVATED",
    }
    identity = {key: value for key, value in document.items() if key not in {
        "$schema", "schema_version", "receipt_id", "receipt_hash"
    }}
    document["receipt_id"] = stable_id(
        "challenger_replacement_v3_start_receipt", identity
    )
    document["receipt_hash"] = artifact_self_hash(document, "receipt_hash")
    if tuple(_validator().iter_errors(document)):
        _invalid()
    return document


def build_challenger_replacement_v3_start_receipt(
    *, deployment, event_projection, event_root_identity
):
    return copy.deepcopy(_document(
        deployment=deployment,
        event_projection=event_projection,
        event_root_identity=event_root_identity,
    ))


def load_challenger_replacement_v3_start_receipt_bytes(
    data, *, deployment, event_projection, event_root_identity
):
    if not isinstance(data, bytes) or not 0 < len(data) <= 262_144:
        _invalid("CHALLENGER_REPLACEMENT_V3_START_BYTES_INVALID")
    try:
        value = _strict_json_bytes(data)
        expected = _document(
            deployment=deployment, event_projection=event_projection,
            event_root_identity=event_root_identity,
        )
        if data != canonical_json(value).encode("utf-8") or value != expected:
            _invalid()
        return copy.deepcopy(value)
    except ChallengerReplacementV3StartError:
        raise
    except (ChallengerReplacementPlanError, KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementV3StartError(
            "CHALLENGER_REPLACEMENT_V3_START_BYTES_INVALID"
        ) from error
