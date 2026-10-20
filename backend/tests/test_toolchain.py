import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from app.core.toolchain import (
    RunResult,
    discover_toolchain,
    parse_encoders,
    parse_version,
    resolve_executable,
    select_encoder,
)

VERSION_OUT = "ffmpeg version 7.1.1-full_build Copyright (c) 2000-2025 the FFmpeg developers\n"
PROBE_OUT = "ffprobe version 7.1.1-full_build Copyright (c) 2007-2025 the FFmpeg developers\n"
ENCODERS_OUT = """Encoders:
 V..... = Video
 A..... = Audio
 ------
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC (codec h264)
 V....D libsvtav1            SVT-AV1(Scalable Video Technology for AV1) encoder (codec av1)
 V....D h264_nvenc           NVIDIA NVENC H.264 encoder (codec h264)
 A....D aac                  AAC (Advanced Audio Coding)
 A....D pcm_s16le            PCM signed 16-bit little-endian
 S..... srt                  SubRip subtitle
"""


def fake_runner(
    version: str = VERSION_OUT, probe: str = PROBE_OUT, encoders: str = ENCODERS_OUT
) -> tuple[Callable[[Sequence[str]], RunResult], list[list[str]]]:
    calls: list[list[str]] = []

    def run(args: Sequence[str]) -> RunResult:
        calls.append(list(args))
        if "-encoders" in args:
            return RunResult(0, encoders)
        is_probe = Path(args[0]).stem.lower().startswith("ffprobe")
        return RunResult(0, probe if is_probe else version)

    return run, calls


def touch_tools(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    ffmpeg, ffprobe = directory / "ffmpeg.exe", directory / "ffprobe.exe"
    ffmpeg.write_text("")
    ffprobe.write_text("")
    return ffmpeg, ffprobe


def no_path(_: str) -> None:
    return None


def test_parse_version_and_malformed_output() -> None:
    assert parse_version(VERSION_OUT) == "7.1.1-full_build"
    assert parse_version(PROBE_OUT) == "7.1.1-full_build"
    assert parse_version("") is None
    assert parse_version("command not found") is None
    assert parse_version("\x00\x01 garbage\nffmpeg version 1") is None


def test_parse_encoders_reads_only_the_table() -> None:
    names = parse_encoders(ENCODERS_OUT)
    assert {"libx264", "libsvtav1", "h264_nvenc", "aac", "pcm_s16le"} <= names
    assert "=" not in names and "Video" not in names
    assert parse_encoders("") == frozenset()
    assert parse_encoders("nothing useful here\n V....D libx264 x") == frozenset()


def test_configured_path_wins_over_path(tmp_path: Path) -> None:
    ffmpeg, _ = touch_tools(tmp_path / "custom")
    found, problem = resolve_executable("ffmpeg", str(ffmpeg), which=lambda _: "/usr/bin/ffmpeg")
    assert (found, problem) == (str(ffmpeg), None)


def test_configured_directory_is_searched(tmp_path: Path) -> None:
    _, ffprobe = touch_tools(tmp_path / "bin")
    found, _ = resolve_executable("ffprobe", str(tmp_path / "bin"), which=no_path)
    assert found == str(ffprobe)


def test_falls_back_to_path_only_when_unconfigured() -> None:
    found, problem = resolve_executable("ffmpeg", "", which=lambda _: "/usr/bin/ffmpeg")
    assert (found, problem) == ("/usr/bin/ffmpeg", None)


def test_bad_configured_path_does_not_fall_back_to_path(tmp_path: Path) -> None:
    found, problem = resolve_executable(
        "ffmpeg", str(tmp_path / "typo"), which=lambda _: "/usr/bin/ffmpeg"
    )
    assert found is None
    assert problem is not None and problem.code == "ffmpeg_path_invalid"
    assert "FFMPEG_PATH" in problem.message and "winget install Gyan.FFmpeg" in problem.hint


def test_missing_tools_report_actionable_problems() -> None:
    toolchain = discover_toolchain(which=no_path)
    assert not toolchain.ok
    assert {p.code for p in toolchain.problems} == {"ffmpeg_not_found", "ffprobe_not_found"}
    for problem in toolchain.problems:
        assert "winget install Gyan.FFmpeg" in problem.hint
        assert "apt install ffmpeg" in problem.hint
    assert toolchain.selected_encoder is None


def test_paths_with_spaces_are_passed_as_single_arguments(tmp_path: Path) -> None:
    ffmpeg, ffprobe = touch_tools(tmp_path / "Program Files" / "my ffmpeg")
    runner, calls = fake_runner()
    toolchain = discover_toolchain(str(ffmpeg), str(ffprobe), runner=runner, which=no_path)
    assert toolchain.ok
    assert toolchain.ffmpeg.path == str(ffmpeg) and " " in toolchain.ffmpeg.path
    assert all(call[0] in (str(ffmpeg), str(ffprobe)) for call in calls)
    assert [str(ffmpeg), "-hide_banner", "-encoders"] in calls


def test_successful_discovery_reports_versions_and_encoders(tmp_path: Path) -> None:
    ffmpeg, ffprobe = touch_tools(tmp_path)
    runner, _ = fake_runner()
    toolchain = discover_toolchain(str(ffmpeg), str(ffprobe), runner=runner)
    assert toolchain.ffmpeg.version == "7.1.1-full_build"
    assert toolchain.ffprobe.version == "7.1.1-full_build"
    assert toolchain.encoders == {"libx264", "libsvtav1", "h264_nvenc", "aac", "pcm_s16le"}
    assert toolchain.selected_encoder is not None
    assert toolchain.selected_encoder.name == "libx264"


def test_malformed_version_output_is_a_problem(tmp_path: Path) -> None:
    ffmpeg, ffprobe = touch_tools(tmp_path)
    runner, _ = fake_runner(version="usage: not ffmpeg", probe="")
    toolchain = discover_toolchain(str(ffmpeg), str(ffprobe), runner=runner)
    assert {p.code for p in toolchain.problems} == {"ffmpeg_bad_output", "ffprobe_bad_output"}
    assert toolchain.encoders == frozenset()


def test_unrunnable_and_timed_out_tools_are_problems(tmp_path: Path) -> None:
    ffmpeg, ffprobe = touch_tools(tmp_path)

    def run(args: Sequence[str]) -> RunResult:
        if Path(args[0]).stem == "ffmpeg":
            raise PermissionError("access denied")
        raise subprocess.TimeoutExpired(list(args), 15)

    toolchain = discover_toolchain(str(ffmpeg), str(ffprobe), runner=run)
    assert {p.code for p in toolchain.problems} == {"ffmpeg_not_runnable", "ffprobe_not_runnable"}


def test_unreadable_encoder_list_is_a_problem(tmp_path: Path) -> None:
    ffmpeg, ffprobe = touch_tools(tmp_path)
    runner, _ = fake_runner(encoders="Encoders:\n no table here\n")
    toolchain = discover_toolchain(str(ffmpeg), str(ffprobe), runner=runner)
    assert [p.code for p in toolchain.problems] == ["encoders_unreadable"]


def test_no_usable_video_encoder_is_a_problem(tmp_path: Path) -> None:
    ffmpeg, ffprobe = touch_tools(tmp_path)
    runner, _ = fake_runner(encoders="Encoders:\n ------\n A....D aac  AAC\n")
    toolchain = discover_toolchain(str(ffmpeg), str(ffprobe), runner=runner)
    assert [p.code for p in toolchain.problems] == ["no_video_encoder"]


def test_software_fallback_order() -> None:
    everything = frozenset({"libx264", "libopenh264", "libsvtav1", "h264_nvenc", "h264_qsv"})
    first = select_encoder(everything)
    assert first is not None
    assert (first.name, first.fallback, first.note) == ("libx264", False, None)

    second = select_encoder(everything - {"libx264"})
    assert second is not None and (second.name, second.fallback) == ("libopenh264", True)
    assert second.note is not None
    assert "libx264 unavailable; using libopenh264" in second.note

    third = select_encoder(frozenset({"libsvtav1"}))
    assert third is not None and third.name == "libsvtav1" and third.fallback
    assert third.note is not None and "AV1" in third.note


def test_hardware_is_never_the_default() -> None:
    chosen = select_encoder(frozenset({"h264_nvenc", "h264_qsv", "libx264"}))
    assert chosen is not None and chosen.name == "libx264" and not chosen.hardware
    # Without the opt-in, a hardware-only FFmpeg has no usable encoder.
    assert select_encoder(frozenset({"h264_nvenc"})) is None


def test_hardware_opt_in() -> None:
    available = frozenset({"h264_nvenc", "libx264"})
    chosen = select_encoder(available, "h264_nvenc")
    assert chosen is not None and chosen.name == "h264_nvenc" and chosen.hardware

    missing = select_encoder(available, "h264_qsv")
    assert missing is not None and missing.name == "libx264" and missing.fallback
    assert missing.note is not None
    assert "h264_qsv was requested but is not available" in missing.note
