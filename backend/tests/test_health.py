import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_MAX_UPLOAD_BYTES, Settings
from app.core import toolchain as toolchain_module
from app.core.toolchain import EncoderChoice, Problem, Toolchain, ToolInfo
from app.main import create_app

GOOD = Toolchain(
    ffmpeg=ToolInfo("ffmpeg", "C:/ff mpeg/ffmpeg.exe", "7.1"),
    ffprobe=ToolInfo("ffprobe", "C:/ff mpeg/ffprobe.exe", "7.1"),
    encoders=frozenset({"libx264", "aac"}),
    selected_encoder=EncoderChoice("libx264", hardware=False, fallback=False),
)


def get_health(settings: Settings, toolchain: Toolchain) -> dict[str, Any]:
    with TestClient(create_app(settings, toolchain)) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    return response.json()


def test_health_reports_tools_encoders_and_limits() -> None:
    body = get_health(Settings(max_upload_bytes=123), GOOD)
    assert body["status"] == "ok"
    assert body["ffmpeg"] == {
        "available": True,
        "path": "C:/ff mpeg/ffmpeg.exe",
        "version": "7.1",
    }
    assert body["encoders"]["available"] == ["aac", "libx264"]
    assert body["encoders"]["selected"]["name"] == "libx264"
    assert body["encoders"]["hardware_opt_in"] is None
    assert body["limits"] == {
        "max_upload_bytes": 123,
        "speed_min": 0.25,
        "speed_max": 16.0,
        "crop_min_size": 0.05,
    }
    assert body["problems"] == []


def test_health_degrades_with_actionable_problems_instead_of_failing() -> None:
    missing = Toolchain(
        ffmpeg=ToolInfo("ffmpeg"),
        ffprobe=ToolInfo("ffprobe"),
        problems=(
            Problem("ffmpeg_not_found", "ffmpeg was not found", "winget install Gyan.FFmpeg"),
        ),
    )
    body = get_health(Settings(), missing)
    assert body["status"] == "degraded"
    assert body["ffmpeg"]["available"] is False
    assert body["encoders"]["selected"] is None
    assert body["problems"][0]["hint"] == "winget install Gyan.FFmpeg"


def test_health_requests_do_not_run_any_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("a tool was run while serving /health")

    monkeypatch.setattr(toolchain_module.subprocess, "run", forbidden)
    with TestClient(create_app(Settings(), GOOD)) as client:
        for _ in range(3):
            assert client.get("/api/v1/health").status_code == 200


def test_discovery_runs_once_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = 0

    def fake_discover(*_: object, **__: object) -> Toolchain:
        nonlocal runs
        runs += 1
        return GOOD

    monkeypatch.setattr("app.main.discover_toolchain", fake_discover)
    with TestClient(create_app(Settings())) as client:
        for _ in range(3):
            client.get("/api/v1/health")
    assert runs == 1


def test_settings_defaults_and_validation() -> None:
    assert Settings.from_env({}).max_upload_bytes == DEFAULT_MAX_UPLOAD_BYTES
    assert Settings.from_env({}).hardware_encoder == ""
    padded = Settings.from_env({"FFMPEG_PATH": " C:/a b/ffmpeg.exe "})
    assert padded.ffmpeg_path == "C:/a b/ffmpeg.exe"
    assert Settings.from_env({"VIDEOCUT_HARDWARE_ENCODER": "h264_qsv"}).hardware_encoder == (
        "h264_qsv"
    )
    for bad in (
        {"VIDEOCUT_HARDWARE_ENCODER": "x264"},
        {"VIDEOCUT_MAX_UPLOAD_BYTES": "lots"},
        {"VIDEOCUT_MAX_UPLOAD_BYTES": "0"},
    ):
        with pytest.raises(ValueError):
            Settings.from_env(bad)


def test_ping_works_without_lifespan() -> None:
    response = TestClient(create_app(Settings(), GOOD)).get("/api/v1/ping")
    assert response.json() == {"status": "ok"}


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg/ffprobe not installed locally (CI provisioning arrives with the rendering core)",
)
def test_health_against_locally_installed_tools() -> None:
    with TestClient(create_app(Settings())) as client:
        body = client.get("/api/v1/health").json()
    assert body["status"] == "ok", body["problems"]
    assert body["ffmpeg"]["version"] and body["ffprobe"]["version"]
    assert Path(body["ffmpeg"]["path"]).is_file()
    assert body["encoders"]["selected"] is not None
    assert body["encoders"]["selected"]["hardware"] is False
