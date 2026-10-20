from fractions import Fraction
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.edl import (
    Edl,
    EdlValidationError,
    Fps,
    ensure_exportable,
    output_duration_seconds,
    validate_against_source,
)


def make(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "fps": {"num": 30000, "den": 1001},
        "segments": [
            {"id": "s1", "start": 0, "end": 372, "speed": 1.0, "mute": False},
            {"id": "s2", "start": 372, "end": 900, "speed": 4.0, "mute": True},
            {"id": "s3", "start": 1350, "end": 1800},
        ],
        "crop": {"x": 0.1, "y": 0.0, "w": 0.8, "h": 1.0},
    }
    document.update(overrides)
    return document


def test_spec_example_is_valid_and_defaults_apply() -> None:
    edl = Edl.model_validate(make())
    assert edl.segments[2].speed == 1.0
    assert edl.segments[2].mute is False
    assert edl.fps.as_fraction() == Fraction(30000, 1001)


def test_crop_is_optional() -> None:
    document = make()
    del document["crop"]
    assert Edl.model_validate(document).crop is None
    assert Edl.model_validate(make(crop=None)).crop is None


def test_one_frame_segment_is_allowed() -> None:
    assert Edl.model_validate(make(segments=[{"id": "a", "start": 5, "end": 6}]))


@pytest.mark.parametrize(
    "fps",
    [
        {"num": 0, "den": 1},
        {"num": 30, "den": 0},
        {"num": -30, "den": 1},
        {"num": 29.97, "den": 1},
        {"num": "30", "den": 1},
    ],
)
def test_fps_must_be_positive_integers(fps: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Edl.model_validate(make(fps=fps))


@pytest.mark.parametrize(
    "segment",
    [
        {"id": "a", "start": 10, "end": 10},
        {"id": "a", "start": 10, "end": 9},
        {"id": "a", "start": -1, "end": 5},
        {"id": "a", "start": 0.5, "end": 5},
        {"id": "a", "start": 0, "end": 5.5},
        {"id": "", "start": 0, "end": 5},
        {"id": "a", "start": 0, "end": 5, "speed": 0.24},
        {"id": "a", "start": 0, "end": 5, "speed": 16.01},
        {"id": "a", "start": 0, "end": 5, "speed": 0},
        {"id": "a", "start": 0, "end": 5, "extra": 1},
    ],
)
def test_invalid_segments_are_rejected(segment: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Edl.model_validate(make(segments=[segment]))


@pytest.mark.parametrize("speed", [0.25, 16, 16.0, 1])
def test_speed_bounds_are_inclusive(speed: float) -> None:
    assert Edl.model_validate(make(segments=[{"id": "a", "start": 0, "end": 5, "speed": speed}]))


def test_overlapping_unordered_and_duplicate_segments_are_rejected() -> None:
    overlap = [{"id": "a", "start": 0, "end": 10}, {"id": "b", "start": 9, "end": 20}]
    unordered = [{"id": "a", "start": 20, "end": 30}, {"id": "b", "start": 0, "end": 10}]
    duplicate = [{"id": "a", "start": 0, "end": 10}, {"id": "a", "start": 10, "end": 20}]
    for segments in (overlap, unordered, duplicate):
        with pytest.raises(ValidationError):
            Edl.model_validate(make(segments=segments))


def test_version_must_be_one() -> None:
    with pytest.raises(ValidationError):
        Edl.model_validate(make(version=2))
    document = make()
    del document["version"]
    with pytest.raises(ValidationError):
        Edl.model_validate(document)


@pytest.mark.parametrize(
    "crop",
    [
        {"x": -0.01, "y": 0, "w": 0.5, "h": 0.5},
        {"x": 0.6, "y": 0, "w": 0.5, "h": 0.5},
        {"x": 0, "y": 0.6, "w": 0.5, "h": 0.5},
        {"x": 0, "y": 0, "w": 0.04, "h": 0.5},
        {"x": 0, "y": 0, "w": 0.5, "h": 0.04},
        {"x": 0, "y": 0, "w": 1.01, "h": 1},
        {"x": 0, "y": 0, "w": 0.5},
    ],
)
def test_invalid_crops_are_rejected(crop: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Edl.model_validate(make(crop=crop))


def test_crop_edges_and_minimum_size_are_inclusive() -> None:
    assert Edl.model_validate(make(crop={"x": 0, "y": 0, "w": 1, "h": 1}))
    assert Edl.model_validate(make(crop={"x": 0.95, "y": 0.95, "w": 0.05, "h": 0.05}))
    # 0.1 + 0.9 is not exactly 1.0 in floating point and must still be accepted.
    assert Edl.model_validate(make(crop={"x": 0.1, "y": 0.1, "w": 0.9, "h": 0.9}))


def test_empty_edl_is_valid_but_not_exportable() -> None:
    edl = Edl.model_validate(make(segments=[]))
    with pytest.raises(EdlValidationError, match="nothing to export"):
        ensure_exportable(edl)
    ensure_exportable(Edl.model_validate(make()))


def test_source_limit_is_inclusive_of_total_frames() -> None:
    edl = Edl.model_validate(make())
    validate_against_source(edl, total_frames=1800, source_fps=Fps(num=30000, den=1001))
    with pytest.raises(EdlValidationError) as error:
        validate_against_source(edl, total_frames=1799)
    assert "s3" in error.value.issues[0]


def test_source_fps_must_match_by_value_not_spelling() -> None:
    edl = Edl.model_validate(make(fps={"num": 60000, "den": 2002}))
    validate_against_source(edl, 1800, Fps(num=30000, den=1001))
    with pytest.raises(EdlValidationError, match="does not match"):
        validate_against_source(edl, 1800, Fps(num=30, den=1))


def test_source_with_no_frames_is_rejected() -> None:
    with pytest.raises(EdlValidationError, match="no frames"):
        validate_against_source(Edl.model_validate(make(segments=[])), 0)


def test_output_duration_sums_segments_over_speed() -> None:
    document = make(
        fps={"num": 30, "den": 1},
        segments=[
            {"id": "a", "start": 0, "end": 60, "speed": 4},
            {"id": "b", "start": 100, "end": 130, "speed": 0.5},
        ],
        crop=None,
    )
    assert output_duration_seconds(Edl.model_validate(document)) == Fraction(15 + 60, 30)


def test_output_duration_at_ntsc_is_exact() -> None:
    document = make(segments=[{"id": "a", "start": 0, "end": 30000}], crop=None)
    assert output_duration_seconds(Edl.model_validate(document)) == Fraction(1001)
