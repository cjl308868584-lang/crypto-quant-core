"""Pure semantic projection for replacement DecisionOpportunity events."""

import base64
from copy import deepcopy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Mapping

from .canonical import business_hash, canonical_json, utc_datetime
from .challenger_replacement_opportunity_evidence import (
    ChallengerReplacementOpportunityEvidenceError,
    load_challenger_replacement_fixture_result_evidence_bytes,
    load_challenger_replacement_simulation_result_evidence_bytes,
)
from .challenger_replacement_binance_private_contract import (
    ChallengerReplacementBinancePrivateContractError,
    PRIVATE_EVENT_TYPES,
    apply_challenger_replacement_private_event,
)
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)


CADENCE = timedelta(hours=4)
OPEN_OFFSET = timedelta(seconds=120)
CLOSE_OFFSET = timedelta(seconds=600)
PLAN_ID = (
    "challenger_replacement_plan_v3_"
    "e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f"
)
PLAN_HASH = "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486"
_HASH_CHARS = frozenset("0123456789abcdef")
_EVENT_TYPES = {
    "INPUT_PREPARED",
    "RESULT_PREPARED",
    "OPPORTUNITY_OBSERVED",
    "OPPORTUNITY_MISSED",
}
_CANARY_COMPANION_TYPES = {"CANARY_AUTHORITY_ARTIFACT_PUBLISHED",
    "CEREMONY_STATE_RECONCILED", "CANARY_STAGE_BLOCK_STARTED",
    "CANARY_EQUITY_RECONCILED", "CANARY_STRATEGY_CYCLE_RECONCILED"}


class ChallengerReplacementOpportunityError(ValueError):
    """DecisionOpportunity semantics failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def invalid(reason="CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"):
    raise ChallengerReplacementOpportunityError(reason)


def canonical_time(value, *, grid=False):
    if not isinstance(value, str):
        invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"
        ) from error
    parsed = parsed.astimezone(timezone.utc)
    if (
        parsed.microsecond % 1000
        or utc_datetime(parsed) != value
        or (
            grid
            and (
                parsed.hour % 4
                or parsed.minute
                or parsed.second
                or parsed.microsecond
            )
        )
    ):
        invalid()
    return parsed


def opportunity_id_for(scheduled_for: str) -> str:
    """Derive the only v3 opportunity identifier from a UTC grid time."""

    canonical_time(scheduled_for, grid=True)
    return "ETHUSDT@" + scheduled_for


def opportunity_window(scheduled):
    return scheduled + OPEN_OFFSET, scheduled + CLOSE_OFFSET


def _hash_valid(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and not set(value) - _HASH_CHARS
    )


def validate_build_identity(value):
    candidate_keys = {
        "reviewed_code_checkpoint", "package_version",
        "predecessor_manifest_identity", "executable_core_hash",
    }
    predecessor = {
        "repository": "cjl308868584-lang/crypto-quant-core",
        "visibility": "PUBLIC",
        "release_tag": "v0.75.0",
        "tag_object": "4bd4b2e21c760d6fad2a27903c67ee509ac116c9",
        "peeled_commit": "a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5",
        "package_version": "0.75.0",
        "manifest_version": "1.69.0",
        "manifest_hash": "b15479590536c302e173a41a758c9113cd7452b0000d8b6c5cb5c2ad8b9404d9",
        "manifest_file_sha256": "df1695827975cbeb9c094b8182839e132219a52a19dc4166677a742d48442220",
        "build_input_tree_hash": "07812c0a352dabab3742aa1c3417eaa8a8363e46a5059e49323f2b1c0d8a4a78",
        "main_ci_run": 32869868571,
    }
    if isinstance(value, Mapping) and set(value) == candidate_keys:
        if (
            value["package_version"] != "0.76.0"
            or value["predecessor_manifest_identity"] != predecessor
            or not isinstance(value["reviewed_code_checkpoint"], str)
            or len(value["reviewed_code_checkpoint"]) != 40
            or set(value["reviewed_code_checkpoint"]) - _HASH_CHARS
            or not _hash_valid(value["executable_core_hash"])
        ):
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_IDENTITY_INVALID")
        return dict(value)
    keys = {
        "release_tag",
        "peeled_commit",
        "package_version",
        "manifest_version",
        "build_input_tree_hash",
        "manifest_hash",
        "manifest_file_sha256",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != keys
        or (
            value["release_tag"], value["package_version"],
            value["manifest_version"]
        ) not in {
            ("v0.70.0", "0.70.0", "1.64.0"),
            ("v0.70.0-fixture", "0.70.0", "1.64.0"),
            ("v0.72.0-fixture", "0.72.0", "1.66.0"),
            ("v0.76.0-fixture", "0.76.0", "1.70.0"),
        }
        or not isinstance(value["peeled_commit"], str)
        or len(value["peeled_commit"]) != 40
        or set(value["peeled_commit"]) - _HASH_CHARS
        or not all(
            _hash_valid(value[name])
            for name in (
                "build_input_tree_hash",
                "manifest_hash",
                "manifest_file_sha256",
            )
        )
    ):
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_IDENTITY_INVALID")
    return dict(value)


def _decode_canonical(value, claimed_hash):
    if not isinstance(value, str) or not _hash_valid(claimed_hash):
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    try:
        data = base64.b64decode(value, validate=True)
        document = _strict_json_bytes(data)
        if canonical_json(document).encode("utf-8") != data:
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    except ChallengerReplacementOpportunityError:
        raise
    except (ChallengerReplacementPlanError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID"
        ) from error
    if not data or hashlib.sha256(data).hexdigest() != claimed_hash:
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    return data


def _payload(event):
    try:
        header = json.loads(event.final_bytes.decode("utf-8"))
        payload_bytes = base64.b64decode(
            header["payload_bytes_base64"], validate=True
        )
        payload = _strict_json_bytes(payload_bytes)
    except (ChallengerReplacementPlanError, KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID"
        ) from error
    if not isinstance(payload, Mapping):
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    return header, payload


def _exact(payload, keys):
    if set(payload) != set(keys):
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")


def initial_opportunity_projection(*, plan, build_identity):
    """Return the root-independent initial v0.70 semantic projection."""

    if not isinstance(plan, Mapping):
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_IDENTITY_INVALID")
    build_identity = validate_build_identity(build_identity)
    latest_snapshot = None
    if build_identity["package_version"] in {"0.72.0", "0.76.0"}:
        from .challenger_replacement_simulation import (
            build_challenger_replacement_genesis_snapshot,
        )
        from .challenger_replacement_simulation_contract import (
            build_challenger_replacement_simulation_contract,
        )

        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        if build_identity["package_version"] == "0.76.0":
            from .challenger_replacement_economic_plan import (
                build_challenger_replacement_economic_plan,
            )
            from .challenger_replacement_public_simulation import (
                build_challenger_replacement_public_genesis_snapshot,
            )
            from .challenger_replacement_public_simulation_contract import (
                build_challenger_replacement_public_simulation_contract,
            )

            latest_snapshot = build_challenger_replacement_public_genesis_snapshot(
                plan=plan,
                public_contract=build_challenger_replacement_public_simulation_contract(
                    plan=plan,
                    economic_plan=build_challenger_replacement_economic_plan(),
                    predecessor_contract=predecessor,
                ),
            )
        else:
            latest_snapshot = build_challenger_replacement_genesis_snapshot(
                plan=plan, contract=predecessor
            )
    return {
        "opportunities": {},
        "active_opportunity_id": None,
        "first_scheduled_for": None,
        "last_terminal_scheduled_for": None,
        "next_required_opportunity": None,
        "terminal_scheduled_for": (),
        "terminal_opportunity_count": 0,
        "observed_opportunity_count": 0,
        "missed_opportunity_count": 0,
        "current_consecutive_missed": 0,
        "maximum_consecutive_missed": 0,
        "missed_reason_counts": {},
        "maximum_detection_delay_seconds": 0,
        "_previous_observed_source_bytes": None,
        "_previous_observed_decision_bytes": None,
        "_previous_observed_decision_hash": None,
        "_latest_next_snapshot": latest_snapshot,
        "_terminal_ids": set(),
    }


def _expected_scheduled(projection):
    previous = projection["last_terminal_scheduled_for"]
    if previous is None:
        return None
    return utc_datetime(canonical_time(previous, grid=True) + CADENCE)


def _validate_schedule(projection, opportunity_id, scheduled_for):
    if opportunity_id_for(scheduled_for) != opportunity_id:
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    expected = _expected_scheduled(projection)
    if expected is not None and scheduled_for != expected:
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")


def apply_opportunity_event(projection, event, *, plan, build_identity):
    """Apply one validated v0.70 event to a mutable semantic projection."""

    header, payload = _payload(event)
    event_type = header.get("event_type")
    opportunity_id = header.get("slot_id")
    if event_type in _CANARY_COMPANION_TYPES:
        if (header.get("plan_hash") != PLAN_HASH
                or header.get("build_identity_hash") != business_hash(build_identity)):
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        return
    if event_type in PRIVATE_EVENT_TYPES:
        if (
            header.get("plan_hash") != PLAN_HASH
            or header.get("build_identity_hash") != business_hash(build_identity)
        ):
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        if (event_type == "BINANCE_RECONCILIATION_INPUTS_CAPTURED"
                and opportunity_id not in projection["opportunities"]):
            return
        try:
            apply_challenger_replacement_private_event(projection, event)
        except ChallengerReplacementBinancePrivateContractError as error:
            raise ChallengerReplacementOpportunityError(
                error.reason_code
            ) from error
        return
    if (
        event_type not in _EVENT_TYPES
        or header.get("plan_hash") != PLAN_HASH
        or header.get("build_identity_hash") != business_hash(build_identity)
        or opportunity_id in projection["_terminal_ids"]
        or not isinstance(opportunity_id, str)
        or payload.get("opportunity_id") != opportunity_id
    ):
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    scheduled_for = payload.get("scheduled_for")
    _validate_schedule(projection, opportunity_id, scheduled_for)

    if event_type == "INPUT_PREPARED":
        _exact(payload, (
            "opportunity_id", "scheduled_for", "capture_open", "capture_close",
            "source_bundle_bytes_base64", "source_bundle_sha256",
        ))
        if (
            projection["active_opportunity_id"] is not None
            or opportunity_id in projection["opportunities"]
        ):
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        scheduled = canonical_time(scheduled_for, grid=True)
        opened, closed = opportunity_window(scheduled)
        recorded = canonical_time(header.get("recorded_at"))
        if (
            payload["capture_open"] != utc_datetime(opened)
            or payload["capture_close"] != utc_datetime(closed)
            or not opened <= recorded <= closed
        ):
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        source_bytes = _decode_canonical(
            payload["source_bundle_bytes_base64"],
            payload["source_bundle_sha256"],
        )
        projection["opportunities"][opportunity_id] = {
            "stage": event_type,
            "outcome": None,
            "scheduled_for": scheduled_for,
            "capture_open": payload["capture_open"],
            "capture_close": payload["capture_close"],
            "source_bundle_bytes": source_bytes,
            "source_bundle_sha256": payload["source_bundle_sha256"],
            "input_event_hash": event.event_hash,
            "input_event_sequence": event.sequence,
            "input_recorded_at": header["recorded_at"],
        }
        projection["active_opportunity_id"] = opportunity_id
        if projection["first_scheduled_for"] is None:
            projection["first_scheduled_for"] = scheduled_for
        return

    if event_type == "OPPORTUNITY_MISSED":
        _exact(payload, (
            "opportunity_id", "scheduled_for", "detected_at",
            "missed_after_event_hash_or_null", "missed_after_stage_or_null",
            "reason_code",
        ))
        detected = canonical_time(payload["detected_at"])
        _, closed = opportunity_window(canonical_time(scheduled_for, grid=True))
        if (
            header.get("recorded_at") != payload["detected_at"]
            or detected <= closed
            or payload["reason_code"]
            not in plan["opportunity_policy"]["missed_reason_codes"]
        ):
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        active = projection["active_opportunity_id"]
        if active is None:
            if (
                payload["missed_after_event_hash_or_null"] is not None
                or payload["missed_after_stage_or_null"] is not None
                or opportunity_id in projection["opportunities"]
            ):
                invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
            slot = {
                "stage": event_type,
                "outcome": "MISSED",
                "scheduled_for": scheduled_for,
            }
            projection["opportunities"][opportunity_id] = slot
            if projection["first_scheduled_for"] is None:
                projection["first_scheduled_for"] = scheduled_for
        else:
            if active != opportunity_id:
                invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
            slot = projection["opportunities"][opportunity_id]
            if (
                slot["stage"] not in {"INPUT_PREPARED", "RESULT_PREPARED"}
                or (
                    slot["stage"] == "RESULT_PREPARED"
                    and build_identity["package_version"] == "0.72.0"
                )
                or payload["missed_after_stage_or_null"] != slot["stage"]
                or payload["missed_after_event_hash_or_null"]
                != event.previous_event_hash
            ):
                invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
            slot.update(stage=event_type, outcome="MISSED")
        slot["reason_code"] = payload["reason_code"]
        slot["detected_at"] = payload["detected_at"]
        delay = int(
            (detected - canonical_time(scheduled_for, grid=True)).total_seconds()
        )
        projection["maximum_detection_delay_seconds"] = max(
            projection["maximum_detection_delay_seconds"], delay
        )
        projection["missed_opportunity_count"] += 1
        projection["current_consecutive_missed"] += 1
        projection["maximum_consecutive_missed"] = max(
            projection["maximum_consecutive_missed"],
            projection["current_consecutive_missed"],
        )
        reasons = projection["missed_reason_counts"]
        reasons[payload["reason_code"]] = reasons.get(payload["reason_code"], 0) + 1
        latest = projection["_latest_next_snapshot"]
        if latest is not None and latest["position_state"] != "FLAT":
            from .evidence import artifact_self_hash

            latest = deepcopy(latest)
            latest["economic_gap_locked"] = True
            latest["snapshot_hash"] = artifact_self_hash(latest, "snapshot_hash")
            projection["_latest_next_snapshot"] = latest
        _terminalize(projection, opportunity_id, scheduled_for)
        return

    if projection["active_opportunity_id"] != opportunity_id:
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    slot = projection["opportunities"].get(opportunity_id)
    if slot is None:
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")

    if event_type == "RESULT_PREPARED":
        _exact(payload, (
            "opportunity_id", "scheduled_for", "input_event_hash",
            "input_event_sequence", "source_bundle_sha256",
            "decision_bytes_base64", "decision_sha256",
            "result_evidence_bytes_base64", "result_evidence_sha256",
            "previous_observed_decision_hash_or_null",
        ))
        if (
            slot["stage"] != "INPUT_PREPARED"
            or payload["input_event_hash"] != slot["input_event_hash"]
            or payload["input_event_sequence"] != slot["input_event_sequence"]
            or payload["source_bundle_sha256"] != slot["source_bundle_sha256"]
            or payload["previous_observed_decision_hash_or_null"]
            != projection["_previous_observed_decision_hash"]
        ):
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        decision_bytes = _decode_canonical(
            payload["decision_bytes_base64"], payload["decision_sha256"]
        )
        evidence_bytes = _decode_canonical(
            payload["result_evidence_bytes_base64"],
            payload["result_evidence_sha256"],
        )
        try:
            evidence_header = json.loads(evidence_bytes)
            if build_identity["package_version"] == "0.76.0":
                if (
                    evidence_header.get("$schema")
                    != "./challenger-replacement-public-simulation-result-v1.schema.json"
                    or evidence_header.get("schema_version") != "1.0.0"
                ):
                    invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
                from .challenger_replacement_economic_plan import (
                    build_challenger_replacement_economic_plan,
                )
                from .challenger_replacement_public_simulation import (
                    build_challenger_replacement_public_simulation_input,
                    load_challenger_replacement_public_simulation_result_bytes,
                )
                from .challenger_replacement_public_market_capture import (
                    load_challenger_replacement_public_market_capture_bytes,
                )
                from .challenger_replacement_public_simulation_contract import (
                    build_challenger_replacement_public_simulation_contract,
                )
                from .challenger_replacement_simulation_contract import (
                    build_challenger_replacement_simulation_contract,
                )

                predecessor = build_challenger_replacement_simulation_contract(
                    plan=plan
                )
                economic = build_challenger_replacement_economic_plan()
                public_contract = (
                    build_challenger_replacement_public_simulation_contract(
                        plan=plan,
                        economic_plan=economic,
                        predecessor_contract=predecessor,
                    )
                )
                previous_bundle = None
                previous_bytes = projection["_previous_observed_source_bytes"]
                if previous_bytes is not None:
                    previous_capture = (
                        load_challenger_replacement_public_market_capture_bytes(
                            previous_bytes,
                            plan=plan,
                            build_identity=build_identity,
                            previous_source_bundle=None,
                        )
                    )
                    previous_bundle = {
                        "klines": previous_capture.document["normalized"]["bars"]
                    }
                capture = load_challenger_replacement_public_market_capture_bytes(
                    slot["source_bundle_bytes"],
                    plan=plan,
                    build_identity=build_identity,
                    previous_source_bundle=previous_bundle,
                )
                source = build_challenger_replacement_public_simulation_input(
                    capture,
                    plan=plan,
                    economic_plan=economic,
                    predecessor_contract=predecessor,
                    public_contract=public_contract,
                    build_identity=build_identity,
                )
                evidence = load_challenger_replacement_public_simulation_result_bytes(
                    evidence_bytes,
                    source=source,
                    previous_projection=projection["_latest_next_snapshot"],
                    plan=plan,
                    economic_plan=economic,
                    public_contract=public_contract,
                    build_identity=build_identity,
                    sequence=event.sequence,
                    parent_event_hash=event.previous_event_hash,
                )
                observed_at = evidence["opportunity"]["captured_at"]
                if canonical_json(evidence["decision"]).encode("utf-8") != decision_bytes:
                    invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
            elif build_identity["package_version"] == "0.72.0":
                if (
                    evidence_header.get("$schema")
                    != "./challenger-replacement-opportunity-result-evidence-v2.schema.json"
                    or evidence_header.get("schema_version") != "2.0.0"
                ):
                    invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
                from .challenger_replacement_simulation_contract import (
                    build_challenger_replacement_simulation_contract,
                )

                evidence = load_challenger_replacement_simulation_result_evidence_bytes(
                    evidence_bytes,
                    plan=plan,
                    contract=build_challenger_replacement_simulation_contract(plan=plan),
                    build_identity=build_identity,
                )
                observed_at = evidence["opportunity"]["observed_at"]
                source_document = _strict_json_bytes(slot["source_bundle_bytes"])
                if (
                    evidence["opportunity"]["opportunity_id"] != opportunity_id
                    or evidence["opportunity"]["scheduled_for"] != scheduled_for
                    or evidence["source"] != {
                        "input_id": source_document["input_id"],
                        "input_hash": source_document["input_hash"],
                    }
                    or canonical_json(evidence["decision"]).encode("utf-8")
                    != decision_bytes
                ):
                    invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
            else:
                if (
                    evidence_header.get("$schema")
                    != "./challenger-replacement-opportunity-result-evidence-v1.schema.json"
                    or evidence_header.get("schema_version") != "1.0.0"
                ):
                    invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
                observed_at = evidence_header["observed_at"]
                evidence = load_challenger_replacement_fixture_result_evidence_bytes(
                    evidence_bytes,
                    opportunity_id=opportunity_id,
                    scheduled_for=scheduled_for,
                    observed_at=observed_at,
                    source_bundle_sha256=slot["source_bundle_sha256"],
                    decision_sha256=payload["decision_sha256"],
                )
        except (ChallengerReplacementOpportunityEvidenceError, KeyError) as error:
            raise ChallengerReplacementOpportunityError(
                "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID"
            ) from error
        if (
            header["recorded_at"] != observed_at
            or canonical_time(header["recorded_at"])
            < canonical_time(slot["input_recorded_at"])
        ):
            invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        slot.update(
            stage=event_type,
            decision_bytes=decision_bytes,
            decision_sha256=payload["decision_sha256"],
            result_evidence=evidence,
            result_evidence_sha256=payload["result_evidence_sha256"],
            result_event_hash=event.event_hash,
            result_event_sequence=event.sequence,
            result_recorded_at=header["recorded_at"],
        )
        return

    _exact(payload, (
        "opportunity_id", "scheduled_for", "input_event_hash",
        "input_event_sequence", "result_event_hash", "result_event_sequence",
        "source_bundle_sha256", "decision_sha256",
        "result_evidence_sha256", "observed_at",
    ))
    expected = {
        "opportunity_id": opportunity_id,
        "scheduled_for": scheduled_for,
        "input_event_hash": slot.get("input_event_hash"),
        "input_event_sequence": slot.get("input_event_sequence"),
        "result_event_hash": slot.get("result_event_hash"),
        "result_event_sequence": slot.get("result_event_sequence"),
        "source_bundle_sha256": slot.get("source_bundle_sha256"),
        "decision_sha256": slot.get("decision_sha256"),
        "result_evidence_sha256": slot.get("result_evidence_sha256"),
        "observed_at": (
            slot.get("result_evidence", {}).get("observed_at")
            if build_identity["package_version"] == "0.70.0"
            else slot.get("result_evidence", {}).get("opportunity", {}).get(
                "captured_at"
                if build_identity["package_version"] == "0.76.0"
                else "observed_at"
            )
        ),
    }
    if (
        slot["stage"] != "RESULT_PREPARED"
        or dict(payload) != expected
        or header.get("recorded_at") != payload["observed_at"]
        or canonical_time(header["recorded_at"])
        < canonical_time(slot["result_recorded_at"])
    ):
        invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    slot.update(stage=event_type, outcome="OBSERVED")
    projection["observed_opportunity_count"] += 1
    projection["current_consecutive_missed"] = 0
    projection["_previous_observed_source_bytes"] = slot["source_bundle_bytes"]
    projection["_previous_observed_decision_bytes"] = slot["decision_bytes"]
    projection["_previous_observed_decision_hash"] = slot["decision_sha256"]
    if build_identity["package_version"] in {"0.72.0", "0.76.0"}:
        projection["_latest_next_snapshot"] = deepcopy(
            slot["result_evidence"]["next_snapshot"]
        )
    _terminalize(projection, opportunity_id, scheduled_for)


def _terminalize(projection, opportunity_id, scheduled_for):
    projection["active_opportunity_id"] = None
    projection["terminal_opportunity_count"] += 1
    projection["last_terminal_scheduled_for"] = scheduled_for
    projection["terminal_scheduled_for"] = (
        *projection["terminal_scheduled_for"], scheduled_for
    )
    projection["_terminal_ids"].add(opportunity_id)
    next_scheduled = utc_datetime(
        canonical_time(scheduled_for, grid=True) + CADENCE
    )
    projection["next_required_opportunity"] = {
        "opportunity_id": opportunity_id_for(next_scheduled),
        "scheduled_for": next_scheduled,
    }


def public_opportunity_projection(projection):
    public = {
        key: value
        for key, value in projection.items()
        if not key.startswith("_")
    }
    public["latest_next_snapshot_or_null"] = deepcopy(
        projection.get("_latest_next_snapshot")
    )
    return public
