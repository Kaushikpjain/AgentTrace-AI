from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel

from agenttrace.trace.canonical import (
    CanonicalizationError,
    canonical_bytes,
    canonical_str,
    decimal_to_str,
    to_json_value,
)
from agenttrace.trace.fingerprint import fingerprint


class Color(StrEnum):
    RED = "red"


class Item(BaseModel):
    price: Decimal
    color: Color


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("80.00"), "80"),
        (Decimal("80"), "80"),
        (Decimal("0.50"), "0.5"),
        (Decimal("0.00"), "0"),
        (Decimal("-0"), "0"),
        (Decimal("1E+2"), "100"),
        (Decimal("123.450"), "123.45"),
    ],
)
def test_decimal_normalization(value: Decimal, expected: str) -> None:
    assert decimal_to_str(value) == expected


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_non_finite_decimal_rejected(value: Decimal) -> None:
    with pytest.raises(CanonicalizationError):
        to_json_value(value)


def test_float_rejected_even_when_nested() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_bytes({"a": [1, {"b": 1.5}]})


def test_non_string_keys_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_bytes({1: "x"})


def test_unsupported_type_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_bytes({"a": object()})


def test_sorted_compact_output() -> None:
    assert canonical_str({"b": 1, "a": [True, None, "x"]}) == '{"a":[true,null,"x"],"b":1}'


def test_nfc_normalization_of_strings_and_keys() -> None:
    decomposed = "é"  # e + combining acute
    composed = "é"
    assert canonical_bytes({decomposed: decomposed}) == canonical_bytes({composed: composed})


def test_enum_datetime_model_and_tuple() -> None:
    when = datetime(2026, 11, 23, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    value = {
        "c": Color.RED,
        "t": when,
        "m": Item(price=Decimal("9.90"), color=Color.RED),
        "x": (1, 2),
    }
    assert to_json_value(value) == {
        "c": "red",
        "t": "2026-11-23T04:30:00Z",
        "m": {"price": "9.9", "color": "red"},
        "x": [1, 2],
    }


def test_naive_datetime_rejected() -> None:
    with pytest.raises(CanonicalizationError):
        to_json_value(datetime(2026, 1, 1))  # intentionally naive


def test_bool_not_confused_with_int() -> None:
    assert canonical_str([True, 1]) == "[true,1]"


def test_to_json_value_is_idempotent() -> None:
    value = {
        "amount": Decimal("12.30"),
        "items": [{"q": 2}],
        "when": datetime(2026, 1, 1, tzinfo=UTC),
    }
    once = to_json_value(value)
    assert to_json_value(once) == once


def test_fingerprint_format_and_stability() -> None:
    fp = fingerprint({"a": Decimal("1.0")})
    assert fp.startswith("sha256:") and len(fp) == len("sha256:") + 64
    assert fp == fingerprint({"a": Decimal("1")})
    assert fp != fingerprint({"a": Decimal("1.01")})


# P1: canonical bytes invariant under key permutation and Decimal scale.
_json_leaf = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.text(max_size=8),
    st.decimals(
        allow_nan=False, allow_infinity=False, places=2, min_value=-(10**6), max_value=10**6
    ),
)
_json_tree = st.recursive(
    _json_leaf,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=6), children, max_size=4),
    ),
    max_leaves=20,
)


def _reverse_keys(value: object) -> object:
    if isinstance(value, dict):
        return {k: _reverse_keys(value[k]) for k in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_keys(v) for v in value]
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.0001"))  # different scale, same value
    return value


@given(_json_tree)
def test_p1_key_order_and_decimal_scale_invariance(value: object) -> None:
    assert canonical_bytes(value) == canonical_bytes(_reverse_keys(value))
