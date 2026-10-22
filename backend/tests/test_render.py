"""Pure tests for the render planner. No FFmpeg is run here."""

from fractions import Fraction
from typing import Any

import pytest

from app.core.edl import Crop, Edl, EdlValidationError
from app.core.probe import ProbeData
from app.core.render import (
    SUPPORTED_ENCODERS,
    RenderOptions,
    atempo_stages,
    build_render_plan,
    crop_pixels,
    output_frame_counts,
)

FPS = {"num": 30000, "den": 1001}


def make_probe(**overrides: Any) -> ProbeData:
    base: dict[str, Any] = {
        "duration_seconds": 60.0,
        "fps": FPS,
        "width": 1920,
        "height": 1080,
        "has_audio": True,
    }
    return ProbeData.model_validate({**base, **overrides})


def make_edl(segments: list[dict[str, Any]], crop: dict[str, float] | None = None) -> Edl:
    return Edl.model_validate({"version": 1, "fps": FPS, "segments": segments, "crop": crop})


def seg(index: int, start: int, end: int, speed: float = 1.0, mute: bool = False) -> dict[str, Any]:
    return {"id": f"s{index}", "start": start, "end": end, "speed": speed, "mute": mute}


def options(**overrides: Any) -> RenderOptions:
    base = {"input_path": "in.mp4", "output_path": "out.mp4"}
    return RenderOptions.model_validate({**base, **overrides})


@pytest.mark.parametrize(
    ("speed", "expected"),
    [
        (1.0, []),
        (1.5, ["1.5"]),
        (2.0, ["2"]),
        (4.0, ["2", "2"]),
        (16.0, ["2", "2", "2", "2"]),
        (0.5, ["0.5"]),
        (0.25, ["0.5", "0.5"]),
        (0.3, ["0.5", "0.6"]),
        (3.0, ["2", "1.5"]),
        (10.0, ["2", "2", "2", "1.25"]),
    ],
)
def test_atempo_stages_stay_in_range_and_multiply_to_speed(
    speed: float, expected: list[str]
) -> None:
    stages = atempo_stages(speed)
    assert [f"{float(s):g}" for s in stages] == expected
    product = Fraction(1)
    for stage in stages:
        assert Fraction(1, 2) <= stage <= 2
        product *= stage
    assert product == Fraction(str(speed))


@pytest.mark.parametrize(
    ("crop", "size", "expected"),
    [
        ({"x": 0.1, "y": 0.0, "w": 0.8, "h": 1.0}, (1920, 1080), (192, 0, 1536, 1080)),
        # 0.333 * 1920 = 639.36 -> 639 -> even 638
        ({"x": 0.0, "y": 0.0, "w": 0.333, "h": 0.5}, (1920, 1080), (0, 0, 638, 540)),
        # Odd frame: only the even part (1918 x 1078) is usable.
        ({"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}, (1919, 1079), (0, 0, 1918, 1078)),
        # Minimum size 0.05 of a tiny frame still gives at least 2 pixels.
        ({"x": 0.95, "y": 0.95, "w": 0.05, "h": 0.05}, (20, 20), (18, 18, 2, 2)),
        # Rounding half up: 0.5 * 11 = 5.5 -> 6.
        ({"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0}, (11, 10), (6, 0, 4, 10)),
    ],
)
def test_crop_pixels_are_even_and_inside_the_frame(
    crop: dict[str, float], size: tuple[int, int], expected: tuple[int, int, int, int]
) -> None:
    result = crop_pixels(Crop.model_validate(crop), *size)
    assert result == expected
    x, y, w, h = result
    assert all(v % 2 == 0 for v in result)
    assert x + w <= size[0] and y + h <= size[1]


def test_rotation_swaps_the_displayed_frame_for_crop_and_output_size() -> None:
    probe = make_probe(width=1920, height=1080, rotation=90)
    edl = make_edl([seg(1, 0, 30)], {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.5})
    plan = build_render_plan(probe, edl, options())
    assert (plan.output_width, plan.output_height) == (1080, 960)
    assert "crop=1080:960:0:0" in plan.filter_complex


def test_odd_displayed_size_without_crop_is_trimmed_to_even() -> None:
    plan = build_render_plan(
        make_probe(width=641, height=361), make_edl([seg(1, 0, 30)]), options()
    )
    assert (plan.output_width, plan.output_height) == (640, 360)
    assert "crop=640:360:0:0,format=yuv420p" in plan.filter_complex


def test_trim_bounds_are_floored_microseconds_and_speed_forces_a_whole_frame_count() -> None:
    plan = build_render_plan(make_probe(), make_edl([seg(1, 1, 2, speed=4.0)]), options())
    # frame 1 = 1001/30000 s = 0.0333666..., frame 2 = 0.0667333...; 1/4 frame -> at least 1.
    assert (
        "trim=start=0.033366:end=0.066733,setpts=(PTS-STARTPTS)/4,fps=30000/1001:round=up,"
        "tpad=stop=-1:stop_mode=clone,trim=end_frame=1[sv0]" in plan.filter_complex
    )
    assert (
        "atrim=start=0.033366:end=0.066733,asetpts=PTS-STARTPTS,atempo=2,atempo=2,"
        "apad,atrim=end=0.033367[sa0]" in plan.filter_complex
    )


def test_unit_speed_segments_need_no_frame_forcing() -> None:
    graph = build_render_plan(make_probe(), make_edl([seg(1, 0, 30)]), options()).filter_complex
    assert "tpad" not in graph and "apad" not in graph and "end_frame" not in graph


def edl_of(*segments: tuple[int, int, float]) -> Edl:
    return make_edl([seg(i, a, b, speed) for i, (a, b, speed) in enumerate(segments, 1)])


def test_frame_counts_are_exact_when_lengths_are_whole() -> None:
    assert output_frame_counts(edl_of((0, 120, 4.0), (130, 160, 1.0), (170, 180, 0.5))) == [
        30, 30, 20
    ]  # fmt: skip


def test_frame_counts_carry_the_fraction_so_the_total_does_not_drift() -> None:
    # Each segment is 5 / 1.5 = 3.33 frames; rounding each alone would give 4 and a 20% error.
    counts = output_frame_counts(edl_of(*[(i * 6, i * 6 + 5, 1.5) for i in range(28)]))
    assert sum(counts) == 93  # round(28 * 10 / 3)
    assert set(counts) <= {3, 4}


def test_frame_counts_never_drop_a_segment() -> None:
    # 1 frame at 16x is 1/16 of a frame; it still emits one, later segments absorb it.
    counts = output_frame_counts(edl_of(*[(i * 2, i * 2 + 1, 16.0) for i in range(32)]))
    assert min(counts) >= 1
    assert abs(sum(counts) - 32 * (1 / 16)) <= 32  # bounded by the one-frame minimum
    assert sum(counts) <= 32


def test_expected_duration_is_the_sum_of_segment_durations_over_speed() -> None:
    edl = make_edl([seg(1, 0, 300), seg(2, 300, 600, speed=4.0)])
    plan = build_render_plan(make_probe(), edl, options())
    assert plan.expected_duration == Fraction(375) * Fraction(1001, 30000)


def test_muted_segments_become_silence_and_do_not_consume_an_audio_branch() -> None:
    edl = make_edl([seg(1, 0, 30), seg(2, 30, 60, mute=True), seg(3, 60, 90)])
    graph = build_render_plan(make_probe(), edl, options()).filter_complex
    assert "asplit=2[a0][a2]" in graph
    assert "[a1]" not in graph
    assert "anullsrc=r=48000:cl=stereo,atrim=duration=1.001[sa1]" in graph
    assert "[sv0][sa0][sv1][sa1][sv2][sa2]concat=n=3:v=1:a=1[vcat][aout]" in graph


def test_all_muted_has_no_source_audio_branch_but_keeps_an_audio_stream() -> None:
    edl = make_edl([seg(1, 0, 30, mute=True), seg(2, 30, 60, mute=True)])
    plan = build_render_plan(make_probe(), edl, options())
    assert "[0:a]" not in plan.filter_complex
    assert plan.has_audio and "[aout]" in plan.filter_complex
    assert "-an" not in plan.args


def test_mp4_without_source_audio_is_video_only() -> None:
    plan = build_render_plan(make_probe(has_audio=False), make_edl([seg(1, 0, 30)]), options())
    assert not plan.has_audio
    assert "anullsrc" not in plan.filter_complex and "[aout]" not in plan.filter_complex
    assert "-an" in plan.args and "aac" not in plan.args
    assert plan.args.count("-map") == 1


def test_wav_without_source_audio_is_silence_of_the_expected_duration() -> None:
    edl = make_edl([seg(1, 0, 30), seg(2, 60, 90, speed=2.0)])
    plan = build_render_plan(
        make_probe(has_audio=False), edl, options(format="wav", output_path="out.wav")
    )
    assert "[0:v]" not in plan.filter_complex and "[0:a]" not in plan.filter_complex
    assert plan.filter_complex.endswith("concat=n=2:v=0:a=1[aout]")
    assert plan.output_width is None and plan.encoder is None
    assert plan.args[-9:] == (
        "-map", "[aout]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "out.wav"
    )  # fmt: skip


def test_wav_with_audio_never_touches_the_video_stream() -> None:
    plan = build_render_plan(
        make_probe(), make_edl([seg(1, 0, 30)]), options(format="wav", output_path="out.wav")
    )
    assert "[0:v]" not in plan.filter_complex and "-c:v" not in plan.args


def test_encoder_specific_options_are_never_shared() -> None:
    edl = make_edl([seg(1, 0, 30)])
    for encoder in SUPPORTED_ENCODERS:
        args = build_render_plan(make_probe(), edl, options(encoder=encoder)).args
        assert args[args.index("-c:v") + 1] == encoder
        assert ("-crf" in args) == (encoder in ("libx264", "libsvtav1"))
        assert ("-preset" in args) == (encoder != "libopenh264")
    nvenc = build_render_plan(make_probe(), edl, options(encoder="h264_nvenc")).args
    assert "-crf" not in nvenc and "-cq" in nvenc


def test_fast_quality_uses_a_faster_x264_preset() -> None:
    args = build_render_plan(make_probe(), make_edl([seg(1, 0, 30)]), options(quality="fast")).args
    assert args[args.index("-preset") + 1] == "veryfast"
    assert args[args.index("-crf") + 1] == "23"


def test_vfr_sources_render_cfr_at_the_project_rate() -> None:
    args = build_render_plan(make_probe(vfr=True), make_edl([seg(1, 0, 30)]), options()).args
    assert args[args.index("-fps_mode") + 1] == "cfr"
    assert args[args.index("-r") + 1] == "30000/1001"
    assert "[0:v]fps=30000/1001,settb=AVTB[v0]" in args[args.index("-filter_complex") + 1]


def test_unsupported_encoder_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported MP4 encoder"):
        build_render_plan(make_probe(), make_edl([seg(1, 0, 30)]), options(encoder="mpeg2video"))


def test_unexportable_edls_are_rejected() -> None:
    with pytest.raises(EdlValidationError, match="nothing to export"):
        build_render_plan(make_probe(), make_edl([]), options())
    with pytest.raises(EdlValidationError, match="beyond the source"):
        build_render_plan(make_probe(duration_seconds=1.0), make_edl([seg(1, 0, 300)]), options())
    other_rate = make_probe(fps={"num": 25, "den": 1})
    with pytest.raises(EdlValidationError, match="does not match source fps"):
        build_render_plan(other_rate, make_edl([seg(1, 0, 10)]), options())
