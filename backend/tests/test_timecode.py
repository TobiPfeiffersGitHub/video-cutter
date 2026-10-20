from fractions import Fraction

import pytest

from app.core.timecode import (
    format_timecode,
    frames_to_seconds,
    nominal_fps,
    parse_timecode,
    seconds_to_frames,
)


def test_frames_to_seconds_is_exact_for_ntsc() -> None:
    assert frames_to_seconds(30000, 30000, 1001) == Fraction(1001)
    assert frames_to_seconds(0, 30000, 1001) == 0
    assert frames_to_seconds(1, 25, 1) == Fraction(1, 25)


def test_seconds_to_frames_round_trips_every_frame() -> None:
    for frame in (0, 1, 2, 29, 30, 1799, 107892):
        assert seconds_to_frames(frames_to_seconds(frame, 30000, 1001), 30000, 1001) == frame


def test_seconds_to_frames_rounds_to_nearest() -> None:
    assert seconds_to_frames(Fraction(1, 2), 25, 1) == 13  # 12.5 rounds up
    assert seconds_to_frames(Fraction(49, 100), 25, 1) == 12


@pytest.mark.parametrize(
    ("num", "den", "nominal"), [(30000, 1001, 30), (24000, 1001, 24), (25, 1, 25), (60, 1, 60)]
)
def test_nominal_fps(num: int, den: int, nominal: int) -> None:
    assert nominal_fps(num, den) == nominal


def test_timecode_round_trip_ntsc() -> None:
    assert parse_timecode("00:00:01:00", 30000, 1001) == 30
    assert parse_timecode("00:01:00:05", 30000, 1001) == 1805
    assert parse_timecode("01:00:00:00", 30000, 1001) == 108000
    for frame in (0, 29, 30, 1805, 108000, 123456):
        assert parse_timecode(format_timecode(frame, 30000, 1001), 30000, 1001) == frame


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "1:2:3",
        "00:00:00;00",
        "00:60:00:00",
        "00:00:60:00",
        "00:00:00:30",
        "aa:00:00:00",
        "00:00:00:-1",
    ],
)
def test_parse_timecode_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_timecode(bad, 30000, 1001)


def test_helpers_reject_non_positive_fps() -> None:
    with pytest.raises(ValueError):
        frames_to_seconds(1, 0, 1)
    with pytest.raises(ValueError):
        frames_to_seconds(1, 30, 0)
