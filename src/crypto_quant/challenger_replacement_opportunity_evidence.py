"""Fixture-only structural evidence for v3 opportunity state tests."""

import copy
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from typing import Any, Dict

from jsonschema import Draft202012Validator

from .canonical import canonical_json, utc_datetime
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)


_SCHEMA = "challenger-replacement-opportunity-result-evidence-v1.schema.json"
_MAX_BYTES = 65_536


class ChallengerReplacementOpportunityEvidenceError(ValueError):
    """Fixture opportunity evidence failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _invalid(reason="CHALLENGER_REPLACEMENT_OPPORTUNITY_EVIDENCE_INVALID"):
    raise ChallengerReplacementOpportunityEvidenceError(reason)


def _canonical_time(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.microsecond % 1000 == 0
        and utc_datetime(parsed.astimezone(timezone.utc)) == value
    )


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _document(
    *, opportunity_id, scheduled_for, observed_at,
    source_bundle_sha256, decision_sha256
) -> Dict[str, Any]:
    return {
        "$schema": "./" + _SCHEMA,
        "schema_version": "1.0.0",
        "mode": "FIXTURE_ONLY_NO_BROKER_NO_ORDER",
        "opportunity_id": opportunity_id,
        "scheduled_for": scheduled_for,
        "observed_at": observed_at,
        "source_bundle_sha256": source_bundle_sha256,
        "decision_sha256": decision_sha256,
        "authority": {
            "network_requests": 0,
            "broker_requests": 0,
            "orders": 0,
            "credentials_used": False,
            "production_state_writes": 0,
        },
    }


def _validate(document, expected):
    if tuple(_validator().iter_errors(document)):
        _invalid()
    if (
        document != expected
        or document["opportunity_id"] != "ETHUSDT@" + document["scheduled_for"]
        or not _canonical_time(document["scheduled_for"])
        or not _canonical_time(document["observed_at"])
    ):
        _invalid()
    scheduled = _time(document["scheduled_for"])
    observed = _time(document["observed_at"])
    if not scheduled + timedelta(seconds=120) <= observed <= scheduled + timedelta(
        seconds=600
    ):
        _invalid()


def build_challenger_replacement_fixture_result_evidence(
    *, opportunity_id, scheduled_for, observed_at,
    source_bundle_sha256, decision_sha256
):
    """Build zero-authority structural evidence for tests only."""

    document = _document(
        opportunity_id=opportunity_id,
        scheduled_for=scheduled_for,
        observed_at=observed_at,
        source_bundle_sha256=source_bundle_sha256,
        decision_sha256=decision_sha256,
    )
    _validate(document, document)
    return copy.deepcopy(document)


def load_challenger_replacement_fixture_result_evidence_bytes(
    data: bytes, *, opportunity_id, scheduled_for, observed_at,
    source_bundle_sha256, decision_sha256
):
    """Replay canonical fixture bytes against exact caller bindings."""

    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_BYTES:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVIDENCE_BYTES_INVALID")
    try:
        document = dict(_strict_json_bytes(data))
        canonical = canonical_json(document).encode("utf-8")
    except (ChallengerReplacementPlanError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityEvidenceError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVIDENCE_BYTES_INVALID"
        ) from error
    if data != canonical:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVIDENCE_BYTES_INVALID")
    expected = _document(
        opportunity_id=opportunity_id,
        scheduled_for=scheduled_for,
        observed_at=observed_at,
        source_bundle_sha256=source_bundle_sha256,
        decision_sha256=decision_sha256,
    )
    _validate(document, expected)
    return copy.deepcopy(document)
