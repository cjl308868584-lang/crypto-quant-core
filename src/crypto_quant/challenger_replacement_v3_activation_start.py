"""Bind the first natural v3 observation to the verified installation."""

import hashlib
from pathlib import Path

from .canonical import canonical_json
from .challenger_replacement_events import ChallengerReplacementEventRootIdentity
from .challenger_replacement_install_trust import _publish_contract_exact
from .challenger_replacement_v3_activation_install import (
    _load_fixed_successful_install_receipt,
)
from .challenger_replacement_v3_observer import observe_challenger_replacement_v3
from .challenger_replacement_v3_start import (
    ChallengerReplacementV3StartError,
    build_challenger_replacement_v3_start_receipt,
    load_challenger_replacement_v3_start_receipt_bytes,
)


_NAME = "challenger-replacement-v3-start-receipt-v1.json"


class ChallengerReplacementV3ActivationStartError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _binding(receipt, body):
    return {
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "file_sha256": hashlib.sha256(body).hexdigest(),
    }


def observe_fixed_v3_first_opportunity():
    inputs, install_receipt, install_bytes = _load_fixed_successful_install_receipt()
    contract = inputs["contract"]
    observation = observe_challenger_replacement_v3()
    deployment = observation.deployment
    if (
        observation.evidence_health not in {"HEALTHY", "DEGRADED"}
        or deployment.get("deployment_id") != contract["deployment"]["deployment_id"]
        or deployment.get("deployment_hash") != contract["deployment"]["deployment_hash"]
    ):
        raise ChallengerReplacementV3ActivationStartError(
            "CHALLENGER_REPLACEMENT_V3_OBSERVATION_FAILED_CLOSED"
        )
    binding = _binding(install_receipt, install_bytes)
    if observation.start_receipt_or_null is not None:
        if observation.start_receipt_or_null.get("install_receipt_binding") != binding:
            raise ChallengerReplacementV3ActivationStartError(
                "CHALLENGER_REPLACEMENT_V3_START_RECEIPT_INVALID"
            )
        return {
            "status": "START_RECEIPT_ALREADY_PUBLISHED",
            "receipt": observation.start_receipt_or_null,
            "observation": observation,
        }
    event = contract["event_root"]
    identity = ChallengerReplacementEventRootIdentity(
        event["path"], event["device"], event["inode"], event["owner_uid"], "0700"
    )
    try:
        receipt = build_challenger_replacement_v3_start_receipt(
            deployment=deployment, event_projection=observation.event_projection,
            event_root_identity=identity, install_receipt_binding=binding,
        )
    except ChallengerReplacementV3StartError as error:
        if error.reason_code == "CHALLENGER_REPLACEMENT_V3_START_NOT_READY":
            return {"status": "WAITING_FOR_FIRST_NATURAL_OBSERVED", "receipt": None}
        raise ChallengerReplacementV3ActivationStartError(
            "CHALLENGER_REPLACEMENT_V3_START_RECEIPT_INVALID"
        ) from error
    return {
        "status": "START_RECEIPT_READY", "receipt": receipt,
        "deployment": deployment, "projection": observation.event_projection,
        "event_root_identity": identity, "install_receipt_binding": binding,
        "start_receipt_root": contract["paths"]["start_receipt_root"],
    }


def publish_fixed_v3_start_receipt():
    prepared = observe_fixed_v3_first_opportunity()
    if prepared["status"] != "START_RECEIPT_READY":
        return prepared
    body = canonical_json(prepared["receipt"]).encode("utf-8")
    outcome, _ = _publish_contract_exact(
        Path(prepared["start_receipt_root"]), _NAME, body
    )
    replayed = load_challenger_replacement_v3_start_receipt_bytes(
        body, deployment=prepared["deployment"],
        event_projection=prepared["projection"],
        event_root_identity=prepared["event_root_identity"],
        install_receipt_binding=prepared["install_receipt_binding"],
    )
    return {"status": "START_RECEIPT_PUBLISHED", "receipt": replayed,
            "publication_outcome": outcome}
