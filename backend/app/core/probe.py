"""Normalized probe data and ffprobe JSON parsing. No web-framework imports.

`ProbeData` is the language-neutral shape used in `contract/golden/`. It mirrors what the
renderer needs, not everything ffprobe reports.

Project frame-rate policy (initial, used until the media pipeline refines it): a constant
frame rate source uses its `avg_frame_rate`; a variable frame rate source (average and
declared rate differ) uses the declared `r_frame_rate`, which is the stream's base rate.
Rendering normalizes every source to that rate, so cut boundaries are accurate to one frame.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.edl import Fps

# Averages and declared rates closer than this ratio are treated as the same rate.
_VFR_TOLERANCE = Fraction(1, 200)


class ProbeError(ValueError):
    """The probe output has no usable video stream or duration."""


class ProbeData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    duration_seconds: Annotated[float, Field(gt=0)]
    fps: Fps
    # Stored (coded) dimensions. The displayed frame swaps them for 90/270 rotation.
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]
    # Clockwise degrees the player applies for display, normalized to 0/90/180/270.
    rotation: Literal[0, 90, 180, 270] = 0
    has_audio: bool = False
    vfr: bool = False
    video_codec: str | None = None
    audio_codec: str | None = None

    @property
    def displayed_size(self) -> tuple[int, int]:
        """(width, height) after rotation metadata is applied."""
        if self.rotation in (90, 270):
            return self.height, self.width
        return self.width, self.height

    @property
    def total_frames(self) -> int:
        """Frames at the project rate: floor(duration * fps)."""
        exact = Fraction(str(self.duration_seconds)) * self.fps.as_fraction()
        return math.floor(exact)


def probe_command(path: str | Path) -> list[str]:
    """Arguments (without the executable) that make ffprobe print the JSON we parse."""
    return [
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]


def _parse_rate(text: object) -> Fraction | None:
    if not isinstance(text, str) or "/" not in text:
        return None
    numerator, _, denominator = text.partition("/")
    try:
        num, den = int(numerator), int(denominator)
    except ValueError:
        return None
    return Fraction(num, den) if num > 0 and den > 0 else None


def _rotation_clockwise(stream: Mapping[str, Any]) -> Literal[0, 90, 180, 270]:
    # FFmpeg >= 6 reports a display matrix whose rotation is counter-clockwise degrees;
    # older builds report a clockwise `rotate` tag.
    degrees: float | None = None
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            degrees = -float(side_data["rotation"])
            break
    if degrees is None:
        tag = stream.get("tags", {}).get("rotate")
        if tag is not None:
            degrees = float(tag)
    if degrees is None:
        return 0
    quarter = round(degrees / 90) % 4
    return (0, 90, 180, 270)[quarter]  # type: ignore[return-value]


def _duration(data: Mapping[str, Any], video: Mapping[str, Any]) -> float:
    for source in (data.get("format", {}), video):
        try:
            value = float(source["duration"])
        except (KeyError, TypeError, ValueError):
            continue
        if value > 0:
            return value
    raise ProbeError("the file has no readable duration")


def parse_ffprobe_json(raw: str | Mapping[str, Any]) -> ProbeData:
    """Turn `ffprobe -print_format json -show_format -show_streams` output into `ProbeData`."""
    data: Mapping[str, Any] = json.loads(raw) if isinstance(raw, str) else raw
    streams: Sequence[Mapping[str, Any]] = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ProbeError("the file has no video stream")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    declared = _parse_rate(video.get("r_frame_rate"))
    average = _parse_rate(video.get("avg_frame_rate"))
    rate = average or declared
    if rate is None:
        raise ProbeError("the video stream has no readable frame rate")
    vfr = bool(
        declared is not None
        and average is not None
        and abs(declared - average) / declared > _VFR_TOLERANCE
    )
    if vfr and declared is not None:
        rate = declared

    return ProbeData(
        duration_seconds=_duration(data, video),
        fps=Fps(num=rate.numerator, den=rate.denominator),
        width=int(video["width"]),
        height=int(video["height"]),
        rotation=_rotation_clockwise(video),
        has_audio=audio is not None,
        vfr=vfr,
        video_codec=video.get("codec_name"),
        audio_codec=audio.get("codec_name") if audio else None,
    )
