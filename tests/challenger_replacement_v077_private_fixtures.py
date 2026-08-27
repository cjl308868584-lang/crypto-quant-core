import base64

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_private_contract import (
    load_binance_private_activation_bytes,
)


def loaded_private_activation(*, build_identity, now, **changes):
    document = {
        "$schema": "./challenger-replacement-binance-private-activation-v1.schema.json",
        "schema_version": "1.0.0",
        "activation_id": "binance_private_activation_" + "5" * 64,
        "build_identity": dict(build_identity),
        "configuration_sha256": "6" * 64,
        "account_approval_sha256": "7" * 64,
        "block_id": "e0-block-" + "8" * 64,
        "stage": "E0",
        "capital_usdt": "100",
        "max_gross_exposure_usdt": "50",
        "max_leverage": "0.5",
        "expires_at": "2026-08-28T00:00:00.000Z",
        "production_activation": True,
    }
    document.update(changes)
    return load_binance_private_activation_bytes(
        (canonical_json(document) + "\n").encode("utf-8"),
        build_identity=build_identity,
        now=now,
    )


def observe_fixture_opportunity(*, state, workspace, recorded_at):
    projection = state.replay()
    input_event = state.append(
        event_type="INPUT_PREPARED", opportunity_id=workspace.opportunity_id,
        worker_id="fixture-private-worker", recorded_at=recorded_at,
        payload=workspace.input_payload(),
        expected_last_event_hash=projection["last_event_hash"],
    )
    projection = state.replay()
    result_event = state.append(
        event_type="RESULT_PREPARED", opportunity_id=workspace.opportunity_id,
        worker_id="fixture-private-worker", recorded_at=recorded_at,
        payload={
            "opportunity_id": workspace.opportunity_id,
            "scheduled_for": workspace.opportunity_id.removeprefix("ETHUSDT@"),
            "input_event_hash": input_event.event_hash,
            "input_event_sequence": input_event.sequence,
            "source_bundle_sha256": workspace.source_hash,
            "decision_bytes_base64": base64.b64encode(
                workspace.decision_bytes
            ).decode("ascii"),
            "decision_sha256": workspace.decision_hash,
            "result_evidence_bytes_base64": base64.b64encode(
                workspace.evidence_bytes
            ).decode("ascii"),
            "result_evidence_sha256": workspace.evidence_hash,
            "previous_observed_decision_hash_or_null": None,
        }, expected_last_event_hash=projection["last_event_hash"],
    )
    projection = state.replay()
    state.append(
        event_type="OPPORTUNITY_OBSERVED",
        opportunity_id=workspace.opportunity_id,
        worker_id="fixture-private-worker", recorded_at=recorded_at,
        payload={
            "opportunity_id": workspace.opportunity_id,
            "scheduled_for": workspace.opportunity_id.removeprefix("ETHUSDT@"),
            "input_event_hash": input_event.event_hash,
            "input_event_sequence": input_event.sequence,
            "result_event_hash": result_event.event_hash,
            "result_event_sequence": result_event.sequence,
            "source_bundle_sha256": workspace.source_hash,
            "decision_sha256": workspace.decision_hash,
            "result_evidence_sha256": workspace.evidence_hash,
            "observed_at": recorded_at,
        }, expected_last_event_hash=projection["last_event_hash"],
    )
