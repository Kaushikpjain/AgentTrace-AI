"""Canonical JSON serialization (TRACE_SCHEMA.md section 5, ADR-013).

Rules:
- Decimal -> normalized plain string ("80.00" -> "80"); NaN/Infinity rejected.
- float -> rejected (money and identifiers must never be floats).
- str -> NFC-normalized; dict keys must be str and are sorted.
- Enum -> value; datetime -> ISO-8601 UTC with "Z" (naive rejected);
  pydantic BaseModel -> model_dump(mode="python"); tuple -> list.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

type JsonValue = str | int | bool | list[JsonValue] | dict[str, JsonValue] | None


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented canonically."""


def decimal_to_str(value: Decimal) -> str:
    """Return the normalized plain-string form of a finite Decimal."""
    if not value.is_finite():
        raise CanonicalizationError(f"non-finite Decimal is not allowed: {value!r}")
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")


def to_json_value(value: Any) -> JsonValue:
    """Convert a supported Python value into a JSON-pure value following canonical rules."""
    # bool must be checked before int (bool is a subclass of int).
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CanonicalizationError("floats are not allowed in canonical JSON; use Decimal")
    if isinstance(value, Decimal):
        return decimal_to_str(value)
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Enum):
        return to_json_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise CanonicalizationError("naive datetimes are not allowed; use UTC")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, BaseModel):
        return to_json_value(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        out: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"dict keys must be str, got {type(key).__name__}")
            out[unicodedata.normalize("NFC", key)] = to_json_value(item)
        return out
    if isinstance(value, list | tuple):
        return [to_json_value(item) for item in value]
    raise CanonicalizationError(f"unsupported type for canonical JSON: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Serialize a value to canonical UTF-8 JSON bytes."""
    return json.dumps(
        to_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_str(value: Any) -> str:
    """Serialize a value to a canonical JSON string."""
    return canonical_bytes(value).decode("utf-8")
