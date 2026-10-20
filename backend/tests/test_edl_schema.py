"""The JSON Schema file and the Pydantic models must accept and reject the same documents."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.core.edl import Edl
from app.main import create_app
from app.openapi import build_openapi

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contract" / "edl.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)

FPS = {"num": 30000, "den": 1001}


def doc(segments: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "version": 1,
        "fps": FPS,
        "segments": segments if segments is not None else [{"id": "a", "start": 0, "end": 10}],
    }
    return {**base, **extra}


def seg(**fields: Any) -> dict[str, Any]:
    return {"id": "a", "start": 0, "end": 10, **fields}


# Documents decided purely by per-field rules: schema and model must agree.
AGREEMENT_CASES: list[tuple[str, dict[str, Any], bool]] = [
    ("minimal", doc(), True),
    ("empty segments", doc(segments=[]), True),
    ("crop null", doc(crop=None), True),
    ("crop full", doc(crop={"x": 0, "y": 0, "w": 1, "h": 1}), True),
    ("crop min size", doc(crop={"x": 0, "y": 0, "w": 0.05, "h": 0.05}), True),
    ("crop too small", doc(crop={"x": 0, "y": 0, "w": 0.049, "h": 0.5}), False),
    ("crop negative", doc(crop={"x": -0.1, "y": 0, "w": 0.5, "h": 0.5}), False),
    ("crop missing field", doc(crop={"x": 0, "y": 0, "w": 0.5}), False),
    ("crop extra field", doc(crop={"x": 0, "y": 0, "w": 0.5, "h": 0.5, "r": 1}), False),
    ("fps zero", {**doc(), "fps": {"num": 0, "den": 1}}, False),
    ("fps float", {**doc(), "fps": {"num": 29.97, "den": 1}}, False),
    ("fps missing den", {**doc(), "fps": {"num": 30}}, False),
    ("version 2", {**doc(), "version": 2}, False),
    ("version missing", {"fps": FPS, "segments": []}, False),
    ("extra top-level", {**doc(), "title": "x"}, False),
    ("speed min", doc([seg(speed=0.25)]), True),
    ("speed max", doc([seg(speed=16)]), True),
    ("speed below", doc([seg(speed=0.2499)]), False),
    ("speed above", doc([seg(speed=16.0001)]), False),
    ("mute true", doc([seg(mute=True)]), True),
    ("mute string", doc([seg(mute="yes")]), False),
    ("start negative", doc([seg(start=-1)]), False),
    ("end zero", doc([seg(end=0)]), False),
    ("start float", doc([seg(start=1.5)]), False),
    ("empty id", doc([seg(id="")]), False),
    ("long id", doc([seg(id="x" * 65)]), False),
    ("segment extra", doc([seg(label="x")]), False),
    ("missing end", doc([{"id": "a", "start": 0}]), False),
]


def model_accepts(document: dict[str, Any]) -> bool:
    try:
        Edl.model_validate(document)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize(
    ("name", "document", "valid"), AGREEMENT_CASES, ids=[c[0] for c in AGREEMENT_CASES]
)
def test_schema_and_model_agree(name: str, document: dict[str, Any], valid: bool) -> None:
    assert VALIDATOR.is_valid(document) is valid, f"schema disagrees on {name}"
    assert model_accepts(document) is valid, f"model disagrees on {name}"


# Cross-field rules: only the model can enforce them. The schema is deliberately more
# permissive, and this test pins that gap so it cannot widen unnoticed.
CORE_ONLY_CASES: list[tuple[str, dict[str, Any]]] = [
    ("start == end", doc([seg(start=5, end=5)])),
    ("start > end", doc([seg(start=9, end=3)])),
    ("overlap", doc([seg(id="a", start=0, end=10), seg(id="b", start=5, end=20)])),
    ("unordered", doc([seg(id="a", start=20, end=30), seg(id="b", start=0, end=10)])),
    ("duplicate id", doc([seg(id="a", start=0, end=10), seg(id="a", start=10, end=20)])),
    ("crop overflows x", doc(crop={"x": 0.6, "y": 0, "w": 0.5, "h": 0.5})),
    ("crop overflows y", doc(crop={"x": 0, "y": 0.6, "w": 0.5, "h": 0.5})),
]


@pytest.mark.parametrize(("name", "document"), CORE_ONLY_CASES, ids=[c[0] for c in CORE_ONLY_CASES])
def test_cross_field_rules_are_enforced_by_the_model_only(
    name: str, document: dict[str, Any]
) -> None:
    assert VALIDATOR.is_valid(document), f"schema unexpectedly rejects {name}"
    assert not model_accepts(document), f"model must reject {name}"


def test_schema_is_a_valid_json_schema() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_openapi_exposes_edl_without_adding_a_route() -> None:
    document = build_openapi(create_app())
    schemas = document["components"]["schemas"]
    assert {"Edl", "Fps", "Segment", "Crop"} <= set(schemas)
    assert not any("edl" in path.lower() for path in document["paths"])
    assert schemas["Edl"]["properties"]["segments"]["items"] == {
        "$ref": "#/components/schemas/Segment"
    }


def test_openapi_constraints_match_the_schema_file() -> None:
    schemas = build_openapi(create_app())["components"]["schemas"]
    keywords = ("type", "minimum", "maximum", "minLength", "maxLength", "default")
    for name in ("Fps", "Segment", "Crop"):
        expected = SCHEMA["$defs"][name]
        actual = schemas[name]
        assert actual["required"] == expected["required"]
        for field, rules in expected["properties"].items():
            for keyword in keywords:
                if keyword in rules:
                    assert actual["properties"][field].get(keyword) == rules[keyword], (
                        name,
                        field,
                        keyword,
                    )
