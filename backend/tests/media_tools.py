"""Helpers for tests that run real FFmpeg/ffprobe on generated media."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.core.probe import ProbeData, parse_ffprobe_json, probe_command
from app.core.render import RenderPlan


def ffprobe_json(ffprobe: str, path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [ffprobe, *probe_command(path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def probe_media(ffprobe: str, path: Path) -> ProbeData:
    return parse_ffprobe_json(ffprobe_json(ffprobe, path))


def run_plan(ffmpeg: str, plan: RenderPlan) -> None:
    result = subprocess.run([ffmpeg, *plan.args], capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"ffmpeg failed:\n{result.stderr[-2000:]}"


def stream(info: dict[str, Any], codec_type: str) -> dict[str, Any] | None:
    return next((s for s in info["streams"] if s["codec_type"] == codec_type), None)


def stream_duration(info: dict[str, Any], codec_type: str) -> float:
    found = stream(info, codec_type)
    assert found is not None, f"no {codec_type} stream"
    if "duration" in found:
        return float(found["duration"])
    return float(info["format"]["duration"])
