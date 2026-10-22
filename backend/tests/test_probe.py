from typing import Any

import pytest

from app.core.probe import ProbeError, parse_ffprobe_json


def ffprobe_doc(video: dict[str, Any] | None = None, audio: bool = True) -> dict[str, Any]:
    video_stream = {
        "codec_type": "video",
        "codec_name": "h264",
        "width": 1920,
        "height": 1080,
        "r_frame_rate": "30000/1001",
        "avg_frame_rate": "30000/1001",
        **(video or {}),
    }
    streams: list[dict[str, Any]] = [video_stream]
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return {"streams": streams, "format": {"duration": "12.5"}}


def test_cfr_source_with_audio() -> None:
    probe = parse_ffprobe_json(ffprobe_doc())
    assert (probe.fps.num, probe.fps.den) == (30000, 1001)
    assert probe.has_audio and not probe.vfr
    assert probe.rotation == 0 and probe.displayed_size == (1920, 1080)
    assert probe.total_frames == 374  # floor(12.5 * 30000 / 1001)
    assert (probe.video_codec, probe.audio_codec) == ("h264", "aac")


def test_no_audio_stream() -> None:
    probe = parse_ffprobe_json(ffprobe_doc(audio=False))
    assert not probe.has_audio and probe.audio_codec is None


@pytest.mark.parametrize(
    ("side_data_rotation", "expected", "displayed"),
    [
        (0, 0, (1920, 1080)),
        (-90, 90, (1080, 1920)),
        (90, 270, (1080, 1920)),
        (180, 180, (1920, 1080)),
    ],
)
def test_display_matrix_rotation_is_normalized_to_clockwise(
    side_data_rotation: int, expected: int, displayed: tuple[int, int]
) -> None:
    doc = ffprobe_doc({"side_data_list": [{"rotation": side_data_rotation}]})
    probe = parse_ffprobe_json(doc)
    assert probe.rotation == expected and probe.displayed_size == displayed


def test_legacy_rotate_tag() -> None:
    probe = parse_ffprobe_json(ffprobe_doc({"tags": {"rotate": "90"}}))
    assert probe.rotation == 90


def test_vfr_is_detected_and_uses_the_declared_rate() -> None:
    probe = parse_ffprobe_json(ffprobe_doc({"r_frame_rate": "30/1", "avg_frame_rate": "1800/89"}))
    assert probe.vfr
    assert (probe.fps.num, probe.fps.den) == (30, 1)


def test_tiny_rate_differences_are_not_vfr() -> None:
    probe = parse_ffprobe_json(ffprobe_doc({"r_frame_rate": "25/1", "avg_frame_rate": "2499/100"}))
    assert not probe.vfr


def test_stream_duration_is_the_fallback() -> None:
    doc = ffprobe_doc({"duration": "3.5"})
    doc["format"] = {}
    assert parse_ffprobe_json(doc).duration_seconds == 3.5


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"streams": [{"codec_type": "audio"}], "format": {"duration": "1"}}, "no video stream"),
        (ffprobe_doc({"r_frame_rate": "0/0", "avg_frame_rate": "0/0"}), "frame rate"),
        ({**ffprobe_doc(), "format": {}}, "duration"),
    ],
)
def test_unusable_probe_output_is_rejected(doc: dict[str, Any], message: str) -> None:
    with pytest.raises(ProbeError, match=message):
        parse_ffprobe_json(doc)


def test_json_text_is_accepted() -> None:
    import json

    assert parse_ffprobe_json(json.dumps(ffprobe_doc())).width == 1920
