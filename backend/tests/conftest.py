"""Shared fixtures. Media tests need a real FFmpeg and fail loudly without one.

A missing FFmpeg must never turn the media tests into silent skips: they are the only
proof that the argument builder produces files FFmpeg accepts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures_gen import generate_fixtures

from app.config import Settings
from app.core.toolchain import Toolchain, discover_toolchain

INSTALL_FAILURE = (
    "These tests require FFmpeg and ffprobe with libx264 and aac. {detail}\n"
    "Install: `winget install Gyan.FFmpeg` (Windows) or `sudo apt install ffmpeg` "
    "(Debian/Ubuntu),\n"
    "or point FFMPEG_PATH and FFPROBE_PATH at them."
)


def pytest_configure(config: pytest.Config) -> None:
    # Keep temp files in the project instead of the shared %TEMP%/pytest-of-<user> tree.
    # On Windows that tree contains a `pytest-current` link whose removal can be denied at
    # session end, which crashed pytest after the tests had already run.
    if config.option.basetemp is None:
        config.option.basetemp = config.rootpath / ".pytest_tmp"


@pytest.fixture(scope="session")
def toolchain() -> Toolchain:
    settings = Settings.from_env()
    found = discover_toolchain(settings.ffmpeg_path, settings.ffprobe_path)
    if not (found.ffmpeg.available and found.ffprobe.available):
        details = "; ".join(f"{p.message}" for p in found.problems) or "FFmpeg was not found."
        pytest.fail(INSTALL_FAILURE.format(detail=details), pytrace=False)
    missing = {"libx264", "aac"} - found.encoders
    if missing:
        pytest.fail(
            INSTALL_FAILURE.format(detail=f"Missing encoders: {', '.join(sorted(missing))}."),
            pytrace=False,
        )
    return found


@pytest.fixture(scope="session")
def ffmpeg(toolchain: Toolchain) -> str:
    assert toolchain.ffmpeg.path is not None
    return toolchain.ffmpeg.path


@pytest.fixture(scope="session")
def ffprobe(toolchain: Toolchain) -> str:
    assert toolchain.ffprobe.path is not None
    return toolchain.ffprobe.path


@pytest.fixture(scope="session")
def fixtures(ffmpeg: str, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return generate_fixtures(ffmpeg, tmp_path_factory.mktemp("media"))
