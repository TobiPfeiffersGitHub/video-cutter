"""Run the builder's arguments through real FFmpeg and inspect the result with ffprobe.

Phase 0 smoke coverage. The full acceptance matrix (60 s source, seam content at every
cut, tolerances) belongs to the export package; these prove the argument lists are valid
and that the core policies (cuts, speed, mute, crop, rotation, VFR, WAV) behave.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from fixtures_gen import read_frame_numbers
from media_tools import ffprobe_json, probe_media, run_plan, stream, stream_duration

from app.core.edl import Edl
from app.core.render import RenderOptions, RenderPlan, build_render_plan
from app.core.toolchain import Toolchain

FRAME = Fraction(1001, 30000)
AV_SYNC_TOLERANCE = 0.040

Export = Callable[..., tuple[RenderPlan, dict[str, Any], Path]]


@pytest.fixture
def export(ffmpeg: str, ffprobe: str, fixtures: dict[str, Path], tmp_path: Path) -> Export:
    """Build, run and probe one export. Returns (plan, ffprobe json of output, output path)."""

    def run(
        source: str,
        segments: list[dict[str, Any]],
        crop: dict[str, float] | None = None,
        **option_overrides: Any,
    ) -> tuple[RenderPlan, dict[str, Any], Path]:
        probe = probe_media(ffprobe, fixtures[source])
        edl = Edl.model_validate(
            {
                "version": 1,
                "fps": {"num": probe.fps.num, "den": probe.fps.den},
                "segments": segments,
                "crop": crop,
            }
        )
        fmt = option_overrides.get("format", "mp4")
        output = tmp_path / f"out_{source}.{fmt}"
        options = RenderOptions(
            input_path=str(fixtures[source]),
            output_path=str(output),
            **option_overrides,
        )
        plan = build_render_plan(probe, edl, options)
        run_plan(ffmpeg, plan)
        return plan, ffprobe_json(ffprobe, output), output

    return run


def seg(index: int, start: int, end: int, speed: float = 1.0, mute: bool = False) -> dict[str, Any]:
    return {"id": f"s{index}", "start": start, "end": end, "speed": speed, "mute": mute}


def assert_duration(info: dict[str, Any], plan: RenderPlan, frames: int = 1) -> None:
    actual = float(info["format"]["duration"])
    assert abs(actual - float(plan.expected_duration)) <= float(FRAME) * frames, (
        f"duration {actual} vs expected {float(plan.expected_duration)}"
    )


def assert_av_in_sync(info: dict[str, Any]) -> None:
    gap = abs(stream_duration(info, "video") - stream_duration(info, "audio"))
    assert gap < AV_SYNC_TOLERANCE, f"A/V stream durations differ by {gap * 1000:.1f} ms"


def test_fixtures_are_probed_as_designed(ffprobe: str, fixtures: dict[str, Path]) -> None:
    normal = probe_media(ffprobe, fixtures["normal"])
    assert (normal.fps.num, normal.fps.den) == (30000, 1001)
    assert normal.has_audio and normal.rotation == 0 and not normal.vfr
    assert not probe_media(ffprobe, fixtures["no_audio"]).has_audio
    rotated = probe_media(ffprobe, fixtures["rotated"])
    assert rotated.rotation in (90, 270) and rotated.displayed_size == (360, 640)
    vfr = probe_media(ffprobe, fixtures["vfr"])
    assert vfr.vfr and (vfr.fps.num, vfr.fps.den) == (30, 1)
    fast = probe_media(ffprobe, fixtures["vfr_fast"])
    assert fast.vfr and (fast.fps.num, fast.fps.den) == (60, 1)


def test_barcode_reads_back_source_frame_numbers(ffmpeg: str, fixtures: dict[str, Path]) -> None:
    numbers = read_frame_numbers(ffmpeg, fixtures["normal"])
    assert numbers == list(range(len(numbers))) and len(numbers) >= 170


def test_cuts_keep_exactly_the_edl_frames_and_stay_in_sync(ffmpeg: str, export: Export) -> None:
    plan, info, output = export("normal", [seg(1, 10, 40), seg(2, 60, 90), seg(3, 120, 150)])
    assert read_frame_numbers(ffmpeg, output) == [
        *range(10, 40), *range(60, 90), *range(120, 150)
    ]  # fmt: skip
    assert_duration(info, plan)
    assert_av_in_sync(info)
    video = stream(info, "video")
    assert video is not None and video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
    assert video["r_frame_rate"] == "30000/1001"
    audio = stream(info, "audio")
    assert audio is not None and audio["codec_name"] == "aac"


def test_single_frame_segment(ffmpeg: str, export: Export) -> None:
    plan, info, output = export("normal", [seg(1, 50, 51)])
    assert read_frame_numbers(ffmpeg, output) == [50]
    assert_duration(info, plan)


def test_four_times_speed_samples_every_fourth_frame_and_the_next_cut_stays_exact(
    ffmpeg: str, export: Export
) -> None:
    plan, info, output = export("normal", [seg(1, 0, 120, speed=4.0), seg(2, 130, 160)])
    # 120 frames at 4x -> source frames 0, 4, 8, ... 116, then the 1x segment untouched.
    assert read_frame_numbers(ffmpeg, output) == [*range(0, 120, 4), *range(130, 160)]
    assert_duration(info, plan)
    assert_av_in_sync(info)


def test_slow_motion_repeats_frames_and_the_next_cut_stays_exact(
    ffmpeg: str, export: Export
) -> None:
    plan, info, output = export("normal", [seg(1, 20, 40, speed=0.5), seg(2, 60, 80)])
    numbers = read_frame_numbers(ffmpeg, output)
    assert numbers == [n for frame in range(20, 40) for n in (frame, frame)] + list(range(60, 80))
    assert_duration(info, plan)
    assert_av_in_sync(info)


def test_mixed_half_and_sixteen_times_speed_chain_atempo(export: Export) -> None:
    plan, info, _ = export("normal", [seg(1, 0, 20, speed=0.5), seg(2, 40, 168, speed=16.0)])
    assert "atempo=0.5" in plan.filter_complex
    assert plan.filter_complex.count("atempo=2") == 4
    assert_duration(info, plan, frames=2)
    assert_av_in_sync(info)


def test_muted_segments_are_silent_and_the_rest_is_not(
    ffmpeg: str, export: Export, tmp_path: Path
) -> None:
    import re
    import subprocess

    plan, info, output = export(
        "normal", [seg(1, 0, 60), seg(2, 60, 120, mute=True), seg(3, 120, 150)]
    )
    assert_duration(info, plan)
    assert_av_in_sync(info)

    def mean_volume(start: float, length: float) -> float:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostdin", "-ss", str(start), "-t", str(length),
             "-i", str(output), "-af", "volumedetect", "-vn", "-f", "null", "-"],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
        match = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", result.stderr)
        assert match, result.stderr[-500:]
        return float("-inf") if match.group(1) == "-inf" else float(match.group(1))

    frame = float(FRAME)
    assert mean_volume(5 * frame, 40 * frame) > -40  # inside segment 1 (frames 0-60)
    assert mean_volume(65 * frame, 40 * frame) < -80  # inside the muted segment
    assert mean_volume(125 * frame, 20 * frame) > -40  # inside segment 3


def test_all_muted_keeps_an_audio_track_of_silence(export: Export) -> None:
    plan, info, _ = export(
        "normal", [seg(1, 0, 60, mute=True), seg(2, 90, 150, speed=2.0, mute=True)]
    )
    assert stream(info, "audio") is not None
    assert_duration(info, plan)
    assert_av_in_sync(info)


def test_source_without_audio_gives_video_only_mp4(ffmpeg: str, export: Export) -> None:
    plan, info, output = export("no_audio", [seg(1, 10, 40), seg(2, 60, 90, speed=2.0)])
    assert stream(info, "audio") is None and stream(info, "video") is not None
    assert_duration(info, plan)
    assert read_frame_numbers(ffmpeg, output)[:30] == list(range(10, 40))


def test_crop_dimensions_are_the_expected_even_pixels(export: Export) -> None:
    plan, info, _ = export(
        "normal", [seg(1, 0, 60)], crop={"x": 0.1, "y": 0.0, "w": 0.333, "h": 0.5}
    )
    video = stream(info, "video")
    assert video is not None
    # 640x360: w = 0.333 * 640 = 213.12 -> 213 -> 212, h = 180
    assert (video["width"], video["height"]) == (212, 180)
    assert (plan.output_width, plan.output_height) == (212, 180)


def test_rotated_source_is_autorotated_and_cropped_in_displayed_space(export: Export) -> None:
    plan, info, _ = export("rotated", [seg(1, 0, 60)])
    video = stream(info, "video")
    assert video is not None and (video["width"], video["height"]) == (360, 640)
    assert (plan.output_width, plan.output_height) == (360, 640)
    assert not video.get("side_data_list"), "rotation must be baked in, not kept as metadata"

    plan, info, _ = export(
        "rotated", [seg(1, 0, 60)], crop={"x": 0.0, "y": 0.5, "w": 1.0, "h": 0.5}
    )
    video = stream(info, "video")
    assert video is not None and (video["width"], video["height"]) == (360, 320)


def test_vfr_source_is_rendered_constant_frame_rate(export: Export) -> None:
    plan, info, _ = export("vfr", [seg(1, 0, 100)])
    video = stream(info, "video")
    assert video is not None
    assert video["r_frame_rate"] == video["avg_frame_rate"] == "30/1"
    assert_duration(info, plan)
    assert abs(int(video["nb_frames"]) - 100) <= 1


def test_wav_has_the_specified_format_and_duration(export: Export) -> None:
    plan, info, _ = export(
        "normal",
        [seg(1, 0, 60), seg(2, 60, 120, speed=2.0, mute=True), seg(3, 120, 150)],
        format="wav",
    )
    assert stream(info, "video") is None
    audio = stream(info, "audio")
    assert audio is not None
    assert (audio["codec_name"], audio["sample_rate"], audio["channels"]) == (
        "pcm_s16le",
        "48000",
        2,
    )
    assert_duration(info, plan)


def test_wav_from_a_source_without_audio_is_silence_of_the_expected_duration(
    export: Export,
) -> None:
    plan, info, _ = export("no_audio", [seg(1, 0, 60), seg(2, 90, 150, speed=2.0)], format="wav")
    audio = stream(info, "audio")
    assert audio is not None and audio["codec_name"] == "pcm_s16le"
    assert_duration(info, plan)


def test_available_fallback_encoders_produce_playable_mp4(
    toolchain: Toolchain, export: Export
) -> None:
    """Runs every software encoder this FFmpeg has. Hardware encoders are never run."""
    names = {"libx264": "h264", "libopenh264": "h264", "libsvtav1": "av1"}
    present = [name for name in names if name in toolchain.encoders]
    assert "libx264" in present
    for encoder in present:
        plan, info, _ = export("normal", [seg(1, 0, 30), seg(2, 60, 90)], encoder=encoder)
        video = stream(info, "video")
        assert video is not None and video["codec_name"] == names[encoder], encoder
        assert plan.encoder == encoder
        assert_duration(info, plan)


@pytest.mark.parametrize(("speed", "start", "end"), [(1.5, 20, 80), (3.0, 20, 80), (16.0, 10, 170)])
def test_speeding_up_holds_the_latest_source_frame_at_each_output_time(
    ffmpeg: str, export: Export, speed: float, start: int, end: int
) -> None:
    plan, info, output = export("normal", [seg(1, start, end, speed=speed), seg(2, 172, 177)])
    count = int((end - start) / speed)
    expected = [start + math.floor(k * Fraction(str(speed))) for k in range(count)]
    assert read_frame_numbers(ffmpeg, output) == [*expected, *range(172, 177)]
    assert_duration(info, plan)
    assert_av_in_sync(info)


@pytest.mark.parametrize("speed", [0.25, 0.75])
def test_slowing_down_stays_near_the_ideal_frame_and_the_next_cut_is_exact(
    ffmpeg: str, export: Export, speed: float
) -> None:
    plan, info, output = export("normal", [seg(1, 20, 40, speed=speed), seg(2, 60, 70)])
    numbers = read_frame_numbers(ffmpeg, output)
    count = round(20 / speed)
    assert numbers[count:] == list(range(60, 70))
    slowed = numbers[:count]
    assert slowed == sorted(slowed)
    # round=near is not a clean floor formula, so allow one source frame of slack.
    assert all(abs(n - (20 + k * speed)) <= 1 for k, n in enumerate(slowed))
    assert_duration(info, plan)
    assert_av_in_sync(info)


@pytest.mark.parametrize(("speed", "length"), [(1.5, 5), (3.0, 5), (0.75, 5), (16.0, 16)])
def test_many_sped_segments_do_not_accumulate_duration_error(
    ffmpeg: str, export: Export, speed: float, length: int
) -> None:
    """Regression: per-segment rounding made 28 segments at 1.5x come out 19 frames long."""
    step = length + 1
    segments = [seg(i, i * step, i * step + length, speed=speed) for i in range(170 // step)]
    plan, info, output = export("normal", segments)
    frames = len(read_frame_numbers(ffmpeg, output))
    exact = float(plan.expected_duration / FRAME)
    assert abs(frames - exact) <= 1, f"{frames} frames, exact {exact:.1f}"
    assert_duration(info, plan)
    assert_av_in_sync(info)


def test_rotated_source_cuts_are_exact_in_the_baked_in_orientation(
    ffmpeg: str, export: Export
) -> None:
    _, _, output = export("rotated", [seg(1, 10, 20), seg(2, 40, 45)])
    numbers = read_frame_numbers(ffmpeg, output, undo="transpose=clock")
    assert numbers == [*range(10, 20), *range(40, 45)]


def test_vfr_with_a_high_declared_rate_is_resampled_to_that_rate_exactly(
    ffmpeg: str, export: Export
) -> None:
    """60 fps for 1 s then 20 fps for 3 s: the project rate is the declared 60."""
    plan, info, output = export("vfr_fast", [seg(1, 0, 120)])
    video = stream(info, "video")
    assert video is not None
    assert video["r_frame_rate"] == video["avg_frame_rate"] == "60/1"
    numbers = read_frame_numbers(ffmpeg, output)
    # Source frames 0..59 are one per project frame; 60..79 each cover three project frames.
    assert numbers == [*range(60), *[n for n in range(60, 80) for _ in range(3)]]
    assert abs(float(info["format"]["duration"]) - float(plan.expected_duration)) <= 1 / 60
