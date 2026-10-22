"""Probe data + EDL -> FFmpeg argument list. Pure functions, no web-framework imports.

One export is one `filter_complex`:

    [0:v]fps=N/D,settb=AVTB,split=K[v0]..   project rate, microsecond time base, K branches
    [v0]trim=..,setpts=..[,fps=N/D:round=..][sv0]   per-segment trim and speed
    [0:a]aformat=..,asplit=M[a0] 48 kHz stereo; only unmuted segments consume a branch
    [a0]atrim=..,asetpts=..,atempo=..[sa0]   or anullsrc+atrim silence when muted
    [sv0][sa0]..concat=n=K:v=1:a=1[vcat][aout]
    [vcat]crop=..,format=yuv420p[vout]

Policies (also documented in docs/ARCHITECTURE.md):

* Speed changes need two things, both found by running real FFmpeg (see test_render_media):
  `fps` leaves a time base of one frame per tick, so `settb=AVTB` must follow it or
  `setpts=.../speed` rounds timestamps to whole frames and frames collide; and `setpts`
  leaves each frame's duration unchanged, which makes `concat` misplace the next segment and
  `-fps_mode cfr` duplicate frames. A per-segment `fps=N/D` after `setpts` rebuilds
  constant-rate frames. Speeding up uses `round=up`: the segment starts on its first source
  frame and holds the latest source frame at or before each output time (4x gives source
  frames 0, 4, 8, ...). Slowing down uses `round=near`, which repeats each frame for an even
  time; `up` would add a frame to slowed segments. Output lengths match
  round(frames / speed) either way.
* Segment lengths are whole output frames with the fraction carried across segments
  (`output_frame_counts`), and a sped-up segment is forced to exactly that many frames
  (`tpad` clone + `trim=end_frame`) on both the video and the audio branch. Without this,
  per-segment rounding accumulated: 28 segments at 1.5x came out 19 frames too long.
* Seconds are `frame * den / num`, rounded *down* to microseconds. Video is normalized
  to the project CFR rate first, so a start rounded down still includes its frame and an
  end rounded down still excludes the next one (frames are ~33 ms apart, rounding is 1 us).
* Audio is always converted to 48 kHz stereo so silence and speech concatenate.
* MP4 from a source without audio has no audio stream. MP4 from a source with audio always
  has one; muted segments are silent. WAV from a source without audio is silence of the
  expected duration, so a WAV export never fails for lack of audio.
* Crop pixels: round half up, then down to even, minimum 2, clamped inside the (even) frame.
  Without a crop, an odd displayed size is trimmed to even because yuv420p requires it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.edl import (
    Crop,
    Edl,
    Segment,
    ensure_exportable,
    output_duration_seconds,
    validate_against_source,
)
from app.core.probe import ProbeData
from app.core.timecode import frames_to_seconds

OUTPUT_AUDIO_RATE = 48000
OUTPUT_AUDIO_LAYOUT = "stereo"
OUTPUT_AUDIO_CHANNELS = 2
AAC_BITRATE = "192k"
# Every atempo stage stays inside this range so older FFmpeg builds accept it.
ATEMPO_MIN = Fraction(1, 2)
ATEMPO_MAX = Fraction(2)

Quality = Literal["high", "fast"]
# Per quality: options for each MP4 video encoder. Encoders do not share rate-control
# vocabulary, so nothing here is passed to an encoder it was not written for.
_ENCODER_OPTIONS: dict[str, dict[Quality, tuple[str, ...]]] = {
    "libx264": {
        "high": ("-preset", "medium", "-crf", "18"),
        "fast": ("-preset", "veryfast", "-crf", "23"),
    },
    # libopenh264 has no CRF or preset; it is bitrate controlled.
    "libopenh264": {
        "high": ("-b:v", "10M"),
        "fast": ("-b:v", "5M"),
    },
    "libsvtav1": {
        "high": ("-preset", "6", "-crf", "28"),
        "fast": ("-preset", "10", "-crf", "35"),
    },
    "h264_nvenc": {
        "high": ("-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0"),
        "fast": ("-preset", "p3", "-rc", "vbr", "-cq", "26", "-b:v", "0"),
    },
    "h264_qsv": {
        "high": ("-preset", "medium", "-global_quality", "20"),
        "fast": ("-preset", "veryfast", "-global_quality", "26"),
    },
}
SUPPORTED_ENCODERS = tuple(_ENCODER_OPTIONS)


class RenderOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["mp4", "wav"] = "mp4"
    quality: Quality = "high"
    # MP4 only; ignored for WAV.
    encoder: str = "libx264"
    input_path: str
    output_path: str


@dataclass(frozen=True)
class RenderPlan:
    """Everything a runner needs: arguments plus what the output should look like."""

    args: tuple[str, ...]
    filter_complex: str
    expected_duration: Fraction
    output_width: int | None
    output_height: int | None
    has_audio: bool
    encoder: str | None


def even_floor(value: int) -> int:
    return value - (value % 2)


def crop_pixels(
    crop: Crop, displayed_width: int, displayed_height: int
) -> tuple[int, int, int, int]:
    """Normalized crop -> (x, y, w, h) in even pixels on the displayed frame."""
    frame_w, frame_h = even_floor(displayed_width), even_floor(displayed_height)
    if frame_w < 2 or frame_h < 2:
        raise ValueError("the displayed frame is too small to crop to even dimensions")

    def pixels(fraction: float, extent: int) -> int:
        return even_floor(math.floor(Fraction(str(fraction)) * extent + Fraction(1, 2)))

    x = min(pixels(crop.x, displayed_width), frame_w - 2)
    y = min(pixels(crop.y, displayed_height), frame_h - 2)
    w = min(max(2, pixels(crop.w, displayed_width)), frame_w - x)
    h = min(max(2, pixels(crop.h, displayed_height)), frame_h - y)
    return x, y, w, h


def atempo_stages(speed: float) -> list[Fraction]:
    """Factors whose product is `speed`, each within 0.5..2.0. Empty for speed 1."""
    remaining = Fraction(str(speed))
    stages: list[Fraction] = []
    while remaining > ATEMPO_MAX:
        stages.append(ATEMPO_MAX)
        remaining /= ATEMPO_MAX
    while remaining < ATEMPO_MIN:
        stages.append(ATEMPO_MIN)
        remaining /= ATEMPO_MIN
    if remaining != 1:
        stages.append(remaining)
    return stages


def _number(value: Fraction | float) -> str:
    return f"{float(value):.9g}"


def _seconds(value: Fraction, *, nearest: bool = False) -> str:
    """Seconds to microsecond precision: floored by default, nearest for durations."""
    scaled = value * 1_000_000
    micros = math.floor(scaled + Fraction(1, 2)) if nearest else math.floor(scaled)
    whole, fraction = divmod(micros, 1_000_000)
    return f"{whole}.{fraction:06d}".rstrip("0").rstrip(".")


def output_frame_counts(edl: Edl) -> list[int]:
    """Whole output frames each segment emits, rounded cumulatively.

    A segment lasts (end - start) / speed frames, usually not a whole number. Rounding each
    segment on its own accumulates (28 segments at 1.5x came out 20% too long), so the
    fractional part is carried: segment i emits round(running total after i) minus the frames
    already emitted, which keeps the total within half a frame of the exact length. A segment
    always emits at least one frame; later segments absorb that.
    """
    counts: list[int] = []
    exact_total = Fraction(0)
    emitted = 0
    for segment in edl.segments:
        exact_total += Fraction(segment.end - segment.start) / Fraction(str(segment.speed))
        count = max(1, math.floor(exact_total + Fraction(1, 2)) - emitted)
        counts.append(count)
        emitted += count
    return counts


def _frames_duration(frames: int, edl: Edl) -> str:
    return _seconds(frames_to_seconds(frames, edl.fps.num, edl.fps.den), nearest=True)


def _video_chain(index: int, segment: Segment, edl: Edl, frames: int) -> str:
    start = _seconds(frames_to_seconds(segment.start, edl.fps.num, edl.fps.den))
    end = _seconds(frames_to_seconds(segment.end, edl.fps.num, edl.fps.den))
    speed = Fraction(str(segment.speed))
    if speed == 1:
        retime = "setpts=PTS-STARTPTS"
    else:
        rounding = "up" if speed > 1 else "near"
        retime = (
            f"setpts=(PTS-STARTPTS)/{_number(speed)},"
            f"fps={edl.fps.num}/{edl.fps.den}:round={rounding},"
            f"tpad=stop=-1:stop_mode=clone,trim=end_frame={frames}"
        )
    return f"[v{index}]trim=start={start}:end={end},{retime}[sv{index}]"


def _audio_chain(index: int, segment: Segment, edl: Edl, frames: int, *, silent: bool) -> str:
    duration = _frames_duration(frames, edl)
    if silent:
        return (
            f"anullsrc=r={OUTPUT_AUDIO_RATE}:cl={OUTPUT_AUDIO_LAYOUT},"
            f"atrim=duration={duration}[sa{index}]"
        )
    start = _seconds(frames_to_seconds(segment.start, edl.fps.num, edl.fps.den))
    end = _seconds(frames_to_seconds(segment.end, edl.fps.num, edl.fps.den))
    chain = f"[a{index}]atrim=start={start}:end={end},asetpts=PTS-STARTPTS"
    for stage in atempo_stages(segment.speed):
        chain += f",atempo={_number(stage)}"
    if Fraction(str(segment.speed)) != 1:
        # Same whole-frame length as the video branch, so concat never pads one to match.
        chain += f",apad,atrim=end={duration}"
    return f"{chain}[sa{index}]"


def _split(source: str, prefix: str, indexes: list[int], filter_name: str, first: str) -> str:
    labels = "".join(f"[{prefix}{i}]" for i in indexes)
    if len(indexes) == 1:
        return f"{source}{first}{labels}"
    return f"{source}{first},{filter_name}={len(indexes)}{labels}"


def _filter_complex(
    probe: ProbeData,
    edl: Edl,
    options: RenderOptions,
    crop_rect: tuple[int, int, int, int] | None,
    frame_size: tuple[int, int],
) -> tuple[str, bool]:
    """Returns the graph and whether it produces an `[aout]` stream."""
    wav = options.format == "wav"
    # MP4 without source audio stays video-only; WAV always needs an audio stream.
    with_audio = probe.has_audio or wav
    all_indexes = list(range(len(edl.segments)))
    chains: list[str] = []
    counts = output_frame_counts(edl)

    if not wav:
        normalize = f"fps={edl.fps.num}/{edl.fps.den},settb=AVTB"
        chains.append(_split("[0:v]", "v", all_indexes, "split", normalize))
        chains.extend(_video_chain(i, s, edl, counts[i]) for i, s in enumerate(edl.segments))

    silent = [not probe.has_audio or s.mute for s in edl.segments]
    if with_audio:
        speaking = [i for i in all_indexes if not silent[i]]
        if speaking:
            chains.append(
                _split(
                    "[0:a]",
                    "a",
                    speaking,
                    "asplit",
                    f"aformat=sample_rates={OUTPUT_AUDIO_RATE}:channel_layouts={OUTPUT_AUDIO_LAYOUT}",
                )
            )
        chains.extend(
            _audio_chain(i, s, edl, counts[i], silent=silent[i]) for i, s in enumerate(edl.segments)
        )

    inputs = "".join(
        ("" if wav else f"[sv{i}]") + (f"[sa{i}]" if with_audio else "") for i in all_indexes
    )
    count = len(edl.segments)
    if wav:
        chains.append(f"{inputs}concat=n={count}:v=0:a=1[aout]")
    else:
        audio_out = "[aout]" if with_audio else ""
        chains.append(f"{inputs}concat=n={count}:v=1:a={int(with_audio)}[vcat]{audio_out}")
        if crop_rect is not None:
            x, y, w, h = crop_rect
            tail = f"[vcat]crop={w}:{h}:{x}:{y},format=yuv420p[vout]"
        else:
            width, height = frame_size
            displayed = even_floor(width), even_floor(height)
            if displayed != frame_size:
                tail = f"[vcat]crop={displayed[0]}:{displayed[1]}:0:0,format=yuv420p[vout]"
            else:
                tail = "[vcat]format=yuv420p[vout]"
        chains.append(tail)
    return ";".join(chains), with_audio


def build_render_plan(probe: ProbeData, edl: Edl, options: RenderOptions) -> RenderPlan:
    """Validate the EDL against the source and build the FFmpeg arguments.

    Raises `EdlValidationError` for an unexportable EDL and `ValueError` for an encoder
    this builder has no options for. The returned arguments exclude the executable.
    """
    ensure_exportable(edl)
    validate_against_source(edl, probe.total_frames, probe.fps)

    frame_size = probe.displayed_size
    crop_rect = crop_pixels(edl.crop, *frame_size) if edl.crop is not None else None
    graph, with_audio = _filter_complex(probe, edl, options, crop_rect, frame_size)

    args = [
        "-hide_banner",
        "-nostdin",
        "-y",
        "-progress",
        "pipe:1",
        "-nostats",
        "-i",
        options.input_path,
        "-filter_complex",
        graph,
    ]
    width: int | None = None
    height: int | None = None
    encoder: str | None = None
    if options.format == "wav":
        args += [
            "-map",
            "[aout]",
            "-c:a",
            "pcm_s16le",
            "-ar",
            str(OUTPUT_AUDIO_RATE),
            "-ac",
            str(OUTPUT_AUDIO_CHANNELS),
        ]
    else:
        if options.encoder not in _ENCODER_OPTIONS:
            raise ValueError(
                f"unsupported MP4 encoder {options.encoder!r}; "
                f"expected one of {', '.join(SUPPORTED_ENCODERS)}"
            )
        encoder = options.encoder
        if crop_rect is not None:
            width, height = crop_rect[2], crop_rect[3]
        else:
            width, height = even_floor(frame_size[0]), even_floor(frame_size[1])
        args += ["-map", "[vout]"]
        if with_audio:
            args += ["-map", "[aout]"]
        args += [
            "-c:v",
            encoder,
            *_ENCODER_OPTIONS[encoder][options.quality],
            "-pix_fmt",
            "yuv420p",
            "-fps_mode",
            "cfr",
            "-r",
            f"{edl.fps.num}/{edl.fps.den}",
        ]
        if with_audio:
            args += ["-c:a", "aac", "-b:a", AAC_BITRATE, "-ar", str(OUTPUT_AUDIO_RATE)]
        else:
            args += ["-an"]
        args += ["-movflags", "+faststart"]
    args.append(options.output_path)

    return RenderPlan(
        args=tuple(args),
        filter_complex=graph,
        expected_duration=output_duration_seconds(edl),
        output_width=width,
        output_height=height,
        has_audio=with_audio,
        encoder=encoder,
    )
