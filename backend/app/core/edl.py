"""EDL v1 models and validation. No web-framework imports.

`contract/edl.schema.json` is the language-neutral source of truth. These Pydantic
models enforce the same per-field rules plus the cross-field invariants a standalone
JSON Schema cannot express (ordering, overlap, unique ids). Rules that depend on the
source video (`total_frames`, source fps) live in `validate_against_source`.

Policy: an EDL with zero segments is *valid* (it is the honest state after the user
deletes everything), but it cannot be exported: `ensure_exportable` rejects it.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SPEED_MIN = 0.25
SPEED_MAX = 16.0
# Crop width/height below this fraction of the displayed frame is rejected.
CROP_MIN_SIZE = 0.05
# Crop edges are compared with this slack so 0.1 + 0.9 style sums are not rejected.
_CROP_EPSILON = 1e-9


class EdlValidationError(ValueError):
    """Raised by core checks; `issues` holds one human-readable line per problem."""

    def __init__(self, issues: list[str]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Fps(_Strict):
    num: Annotated[int, Field(ge=1, description="Frame rate numerator, e.g. 30000.")]
    den: Annotated[int, Field(ge=1, description="Frame rate denominator, e.g. 1001.")]

    def as_fraction(self) -> Fraction:
        return Fraction(self.num, self.den)


class Segment(_Strict):
    id: Annotated[str, Field(min_length=1, max_length=64)]
    start: Annotated[int, Field(ge=0, description="First frame, inclusive.")]
    end: Annotated[int, Field(ge=1, description="Last frame, exclusive.")]
    speed: Annotated[float, Field(ge=SPEED_MIN, le=SPEED_MAX)] = 1.0
    mute: bool = False

    @model_validator(mode="after")
    def _start_before_end(self) -> Segment:
        if self.start >= self.end:
            raise ValueError(f"segment {self.id!r}: start must be less than end")
        return self


class Crop(_Strict):
    x: Annotated[float, Field(ge=0, le=1)]
    y: Annotated[float, Field(ge=0, le=1)]
    w: Annotated[float, Field(ge=CROP_MIN_SIZE, le=1)]
    h: Annotated[float, Field(ge=CROP_MIN_SIZE, le=1)]

    @model_validator(mode="after")
    def _inside_frame(self) -> Crop:
        if self.x + self.w > 1 + _CROP_EPSILON or self.y + self.h > 1 + _CROP_EPSILON:
            raise ValueError("crop must lie inside the frame (x + w <= 1 and y + h <= 1)")
        return self


class Edl(_Strict):
    version: Literal[1]
    fps: Fps
    segments: list[Segment]
    crop: Crop | None = None

    @model_validator(mode="after")
    def _ordered_unique_segments(self) -> Edl:
        seen: set[str] = set()
        previous_end = 0
        for segment in self.segments:
            if segment.id in seen:
                raise ValueError(f"duplicate segment id {segment.id!r}")
            seen.add(segment.id)
            if segment.start < previous_end:
                raise ValueError(
                    f"segment {segment.id!r} overlaps or precedes the previous segment"
                )
            previous_end = segment.end
        return self


def validate_against_source(edl: Edl, total_frames: int, source_fps: Fps | None = None) -> None:
    """Check the rules that need the source video. Raises `EdlValidationError`."""
    issues: list[str] = []
    if total_frames < 1:
        issues.append("source has no frames")
    if source_fps is not None and edl.fps.as_fraction() != source_fps.as_fraction():
        issues.append(
            f"EDL fps {edl.fps.num}/{edl.fps.den} does not match source fps "
            f"{source_fps.num}/{source_fps.den}"
        )
    for segment in edl.segments:
        if segment.end > total_frames:
            issues.append(
                f"segment {segment.id!r} ends at frame {segment.end}, "
                f"beyond the source's {total_frames} frames"
            )
    if issues:
        raise EdlValidationError(issues)


def ensure_exportable(edl: Edl) -> None:
    if not edl.segments:
        raise EdlValidationError(["the EDL has no segments, so there is nothing to export"])


def output_duration_seconds(edl: Edl) -> Fraction:
    """Expected output length: sum((end - start) / speed) in seconds."""
    total = Fraction(0)
    for segment in edl.segments:
        total += Fraction(segment.end - segment.start) / Fraction(str(segment.speed))
    return total * Fraction(edl.fps.den, edl.fps.num)
