"""Frame/time helpers. Pure functions on integer frames and a rational fps.

Seconds are always exact `Fraction`s (frame * den / num); floats appear only at the
edge where a caller formats them for FFmpeg.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction

_TIMECODE_RE = re.compile(r"^(\d+):([0-5]\d):([0-5]\d):(\d+)$")


def fps_fraction(num: int, den: int) -> Fraction:
    if num <= 0 or den <= 0:
        raise ValueError("fps numerator and denominator must be positive")
    return Fraction(num, den)


def frames_to_seconds(frames: int, num: int, den: int) -> Fraction:
    """Exact seconds for a frame number: frame * den / num."""
    return Fraction(frames) / fps_fraction(num, den)


def seconds_to_frames(seconds: Fraction | int, num: int, den: int) -> int:
    """Nearest frame to a time in seconds (ties round up)."""
    exact = Fraction(seconds) * fps_fraction(num, den)
    return math.floor(exact + Fraction(1, 2))


def nominal_fps(num: int, den: int) -> int:
    """Whole frames per timecode second: 30000/1001 -> 30, 24 -> 24."""
    return max(1, round(fps_fraction(num, den)))


def format_timecode(frame: int, num: int, den: int) -> str:
    """Frame number -> non-drop-frame `HH:MM:SS:FF`."""
    if frame < 0:
        raise ValueError("frame must be >= 0")
    base = nominal_fps(num, den)
    seconds, ff = divmod(frame, base)
    minutes, ss = divmod(seconds, 60)
    hh, mm = divmod(minutes, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def parse_timecode(text: str, num: int, den: int) -> int:
    """Non-drop-frame `HH:MM:SS:FF` -> frame number.

    Policy: the label counts `round(fps)` frames per second and never skips numbers
    (no drop-frame). For 30000/1001 the label therefore runs slightly slower than the
    wall clock, exactly like a non-drop-frame editor's timecode. `FF` must be below
    the nominal frame rate. Semicolon (drop-frame) separators are rejected.
    """
    match = _TIMECODE_RE.match(text.strip())
    if match is None:
        raise ValueError(f"invalid timecode {text!r}; expected HH:MM:SS:FF")
    hh, mm, ss, ff = (int(g) for g in match.groups())
    base = nominal_fps(num, den)
    if ff >= base:
        raise ValueError(f"frame field {ff} must be below {base} for this frame rate")
    return ((hh * 60 + mm) * 60 + ss) * base + ff
