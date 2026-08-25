"""Immutable accelerated-Canary operational supersession record."""

import copy
import hashlib
import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_accelerated_canary_plan import (
    ChallengerReplacementAcceleratedCanaryPlanError,
    build_challenger_replacement_accelerated_canary_plan,
)
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _read_owner_controlled_regular_file,
    _strict_json_bytes,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_SCHEMA = (
    "challenger-replacement-accelerated-canary-supersession-v1.schema.json"
)
_ZERO_HASH = "0" * 64
_ARTIFACT_SHA256 = _ZERO_HASH


class ChallengerReplacementAcceleratedCanarySupersessionError(ValueError):
    """The operational supersession record failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    try:
        resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
        schema = json.loads(resource.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)
    except (OSError, SchemaError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_SCHEMA_INVALID"
        ) from error


def _schema_errors(value: Mapping[str, Any]) -> Tuple[Any, ...]:
    try:
        return tuple(_validator().iter_errors(value))
    except ChallengerReplacementAcceleratedCanarySupersessionError:
        raise
    except (OSError, SchemaError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_SCHEMA_INVALID"
        ) from error


def challenger_replacement_accelerated_canary_supersession_hash(
    record: Mapping[str, Any],
) -> str:
    """Hash the record while excluding only its self-hash field."""

    return artifact_self_hash(record, "record_hash")


def _identity(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "reason": record["reason"],
        "predecessor": record["predecessor"],
        "successor": record["successor"],
        "changed_operational_rules": record["changed_operational_rules"],
        "preserved_economic_authority": record[
            "preserved_economic_authority"
        ],
        "effectivity": record["effectivity"],
    }


def build_challenger_replacement_accelerated_canary_supersession(
) -> Dict[str, Any]:
    """Build the parameterless future-activation-only supersession."""

    plan = build_challenger_replacement_accelerated_canary_plan()
    plan_bytes = canonical_json(plan).encode("utf-8") + b"\n"
    record = {
        "$schema": (
            "./challenger-replacement-accelerated-canary-"
            "supersession-v1.schema.json"
        ),
        "schema_version": "1.0.0",
        "record_id": (
            "challenger_replacement_accelerated_canary_supersession_"
            + _ZERO_HASH
        ),
        "record_hash": _ZERO_HASH,
        "reason": (
            "SUPERSEDED_FUTURE_ACTIVATION_"
            "ACCELERATED_OPERATIONAL_QUALIFICATION"
        ),
        "predecessor": {
            "v069_operational_plan": {
                "file_sha256": (
                    "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3"
                ),
                "plan_id": (
                    "challenger_replacement_plan_v3_"
                    "e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f"
                ),
                "plan_hash": (
                    "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486"
                ),
            },
            "v073_readiness_release": {
                "release_tag": "v0.73.0",
                "peeled_commit": "34bd0e9ba96c769b7301c482730a03fb975c24ce",
                "manifest_hash": (
                    "0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0"
                ),
            },
            "v074_economic_plan": {
                "file_sha256": (
                    "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297"
                ),
                "plan_id": (
                    "challenger_replacement_economic_evaluation_plan_"
                    "13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e"
                ),
                "plan_hash": (
                    "7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4"
                ),
            },
            "v074_release": {
                "release_tag": "v0.74.0",
                "tag_object": "86624de8be8d5117e4b4ef6fd825a9eb711c7c38",
                "peeled_commit": "bfe0080b0a29a74550449a1eb2ac2907a2d2ddac",
                "manifest_file_sha256": (
                    "0db974c9d143abee2e3fc078c09db8893a82754f1c4209178fb982d3d449db12"
                ),
                "manifest_hash": (
                    "699b50fe198b25934e67433d95ea75deb3f6e0657fa8c440a61c7d6c5349e2ec"
                ),
                "tree_hash": (
                    "fe58cc252f9b548e6eedb25e8249c6329cd20ee50f7a0cec48fe88abbbe4bb8e"
                ),
            },
        },
        "successor": {
            "file_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "target_release": "v0.75.0",
        },
        "changed_operational_rules": [
            "SEVEN_DAY_NATURAL_CYCLE_GATE_TO_CONTINUOUS_72_HOUR_QUALIFICATION",
            "NATURAL_PRE_E0_PRODUCT_ROUNDTRIPS_TO_EXCLUDED_OPERATIONAL_CEREMONY",
            "PERMANENT_STREAM_LOCK_TO_IMMUTABLE_FAILED_BLOCK_AND_APPROVED_NEW_BLOCK",
            "BROAD_TERMINAL_OPERATIONAL_FAILURES_TO_FOUR_ABSOLUTE_STAGE_HARD_STOPS",
        ],
        "preserved_economic_authority": {
            "v074_economic_plan_disposition": (
                "IMMUTABLE_UNCHANGED_AUTHORITY"
            ),
            "file_sha256": (
                "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297"
            ),
            "plan_id": (
                "challenger_replacement_economic_evaluation_plan_"
                "13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e"
            ),
            "plan_hash": (
                "7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4"
            ),
            "economic_start_or_window_changed": False,
        },
        "effectivity": {
            "applies_to": (
                "ONLY_START_RECEIPTS_CREATED_AFTER_V075_"
                "AND_BINDING_SUCCESSOR_PLAN"
            ),
            "retroactive_effect": "NONE",
            "existing_events_disposition": "IMMUTABLE_RETAINED",
            "failed_blocks_disposition": "IMMUTABLE_RETAINED",
            "economic_window_disposition": "V074_UNCHANGED",
        },
        "authority": {
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "broker_requests_allowed": False,
            "real_orders_allowed": False,
            "fund_movement_allowed": False,
            "ceremony_authorized": False,
            "e0_activation_authorized": False,
            "market_requests": 0,
            "private_account_requests": 0,
            "production_state_writes": 0,
            "economic_outcome_reads": 0,
        },
        "status": "SUPERSESSION_PREREGISTERED_NOT_ACTIVATED",
        "warnings": [
            "V074_ECONOMIC_AUTHORITY_PRESERVED",
            "SUPERSESSION_HAS_NO_RETROACTIVE_EFFECT",
            "NO_INSTALL_START_CREDENTIAL_ORDER_FUND_OR_CANARY_AUTHORITY",
        ],
    }
    record["record_id"] = stable_id(
        "challenger_replacement_accelerated_canary_supersession",
        _identity(record),
    )
    record["record_hash"] = (
        challenger_replacement_accelerated_canary_supersession_hash(record)
    )
    if _schema_errors(record):
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_SCHEMA_INVALID"
        )
    return copy.deepcopy(record)


def challenger_replacement_accelerated_canary_supersession_reasons(
    record: Mapping[str, Any],
) -> Tuple[str, ...]:
    """Return deterministic fail-closed integrity reasons."""

    reasons = []
    try:
        if _schema_errors(record):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
                "SUPERSESSION_SCHEMA_INVALID"
            )
        if record.get(
            "record_hash"
        ) != challenger_replacement_accelerated_canary_supersession_hash(
            record
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
                "SUPERSESSION_HASH_MISMATCH"
            )
        if record.get("record_id") != stable_id(
            "challenger_replacement_accelerated_canary_supersession",
            _identity(record),
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
                "SUPERSESSION_ID_MISMATCH"
            )
        if business_hash(record) != business_hash(
            build_challenger_replacement_accelerated_canary_supersession()
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
                "SUPERSESSION_SEMANTIC_MISMATCH"
            )
    except (
        ChallengerReplacementAcceleratedCanaryPlanError,
        ChallengerReplacementAcceleratedCanarySupersessionError,
    ) as error:
        reasons.append(error.reason_code)
    except (
        CanonicalizationError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        reasons.append(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_SEMANTIC_MISMATCH"
        )
    return tuple(dict.fromkeys(reasons))


def _mapped_json_error(error: ChallengerReplacementPlanError) -> str:
    if error.reason_code.endswith("JSON_DUPLICATE_KEY"):
        return (
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_JSON_DUPLICATE_KEY"
        )
    if error.reason_code.endswith("JSON_FLOAT_FORBIDDEN"):
        return (
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_JSON_FLOAT_FORBIDDEN"
        )
    return (
        "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
        "SUPERSESSION_JSON_INVALID"
    )


def load_challenger_replacement_accelerated_canary_supersession(
    path: Path,
) -> Dict[str, Any]:
    """Load only owner-controlled canonical bytes for the frozen record."""

    try:
        record_path = Path(path)
    except (OSError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_PATH_INVALID"
        ) from error
    if not record_path.is_absolute():
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_PATH_INVALID"
        )
    try:
        body = _read_owner_controlled_regular_file(record_path)
    except (ChallengerReplacementPlanError, OSError, ValueError) as error:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_PATH_INVALID"
        ) from error
    try:
        record = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            _mapped_json_error(error)
        ) from error
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_JSON_INVALID"
        ) from error
    try:
        canonical = canonical_json(record).encode("utf-8")
    except (
        CanonicalizationError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
    ) as error:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_JSON_INVALID"
        ) from error
    if body != canonical + b"\n":
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_CANONICAL_BYTES_REQUIRED"
        )
    if hashlib.sha256(body).hexdigest() != _ARTIFACT_SHA256:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "SUPERSESSION_FILE_SHA256_MISMATCH"
        )
    reasons = challenger_replacement_accelerated_canary_supersession_reasons(
        record
    )
    if reasons:
        raise ChallengerReplacementAcceleratedCanarySupersessionError(
            reasons[0]
        )
    return copy.deepcopy(record)
