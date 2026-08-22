"""Strict live-input boundary for the replacement Challenger."""

import json
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json


_CAPABILITY_TOKEN = object()
_MAX_CAPTURE_BYTES = 2 * 1024 * 1024


class ChallengerReplacementLiveInputError(ValueError):
    """The replacement live-input boundary failed closed."""

    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _capture_validator():
    schema = json.loads(
        resources.files("crypto_quant")
        .joinpath("schemas", "challenger-replacement-live-capture-v1.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _strict_json(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_CAPTURE_BYTES:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SIZE_INVALID"
        )

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ChallengerReplacementLiveInputError(
                    "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
                )
            result[key] = value
        return result

    def reject_number(_value):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
        )

    try:
        document = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except ChallengerReplacementLiveInputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
        ) from error
    if not isinstance(document, Mapping):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_JSON_INVALID"
        )
    return document


def load_challenger_replacement_live_capture_bytes(
    data, *, plan, build_identity, previous_source_bundle
):
    """Load bounded canonical bytes without granting runtime authority."""

    del plan, build_identity, previous_source_bundle
    document = _strict_json(data)
    if data != canonical_json(document).encode("utf-8"):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_CANONICAL_BYTES_REQUIRED"
        )
    if tuple(_capture_validator().iter_errors(document)):
        raise ChallengerReplacementLiveInputError(
            "CHALLENGER_REPLACEMENT_LIVE_CAPTURE_SCHEMA_INVALID"
        )
    return deepcopy(dict(document))


@dataclass(frozen=True, init=False)
class ChallengerReplacementLiveCapture:
    """Adapter-derived bytes which may enter the cohort runtime."""

    _document: Mapping[str, Any]
    _canonical_bytes: bytes

    def __init__(self, *, _token, document, canonical_bytes):
        if _token is not _CAPABILITY_TOKEN:
            raise TypeError("live capture capability is adapter-derived")
        object.__setattr__(self, "_document", deepcopy(dict(document)))
        object.__setattr__(self, "_canonical_bytes", bytes(canonical_bytes))

    @property
    def document(self):
        return deepcopy(dict(self._document))

    @property
    def canonical_bytes(self):
        return bytes(self._canonical_bytes)
