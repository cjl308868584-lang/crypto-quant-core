"""Canonical serialization and deterministic business identifiers.

Auditable payloads cannot contain binary floats. Decimal values are encoded as
canonical strings, object keys are ASCII, and integers stay in the exact JSON
range. This restricted domain removes cross-runtime numeric ambiguity.
"""

import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping

from .errors import CanonicalizationError

_MAX_SAFE_INTEGER = (1 << 53) - 1


def canonical_decimal(value: Any) -> str:
    """Return a non-exponent Decimal string and reject unsafe inputs."""

    if isinstance(value, bool) or isinstance(value, float):
        raise CanonicalizationError("binary float and bool are not Decimal inputs")
    try:
        number = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CanonicalizationError(f"invalid Decimal value: {value!r}") from exc
    if not number.is_finite():
        raise CanonicalizationError("NaN and Infinity are forbidden")
    if number.is_zero() and number.is_signed():
        raise CanonicalizationError("negative zero is forbidden")

    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def utc_datetime(value: datetime) -> str:
    """Serialize an aware datetime as UTC with millisecond precision."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalizationError("datetime must be timezone-aware")
    converted = value.astimezone(timezone.utc)
    milliseconds = converted.microsecond // 1000
    return converted.replace(microsecond=milliseconds * 1000).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, float):
        raise CanonicalizationError("binary float is forbidden in business payloads")
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise CanonicalizationError("integer exceeds the exact JSON safe range")
        return value
    if isinstance(value, datetime):
        return utc_datetime(value)
    if isinstance(value, Enum):
        return _normalize(value.value)
    if is_dataclass(value):
        return {
            field.name: _normalize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        normalized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("object keys must be strings")
            if not key.isascii():
                raise CanonicalizationError("object keys must be ASCII")
            normalized[key] = _normalize(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise CanonicalizationError(f"unsupported payload type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return deterministic UTF-8 JSON for the restricted business domain."""

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def business_hash(value: Any) -> str:
    """Hash canonical business content with SHA-256."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    """Derive an ID without wall-clock or random inputs."""

    if not prefix or not prefix.replace("_", "").replace("-", "").isalnum():
        raise CanonicalizationError("stable ID prefix must be alphanumeric, '-' or '_'")
    return f"{prefix}_{business_hash(value)}"
