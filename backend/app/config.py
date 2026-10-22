"""Runtime settings read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_MAX_UPLOAD_BYTES = 8 * 1024**3
HARDWARE_ENCODERS = ("h264_nvenc", "h264_qsv")


@dataclass(frozen=True)
class Settings:
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    # Opt-in only. Empty means software encoding; hardware is never the default.
    hardware_encoder: str = ""
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        hardware = env.get("VIDEOCUT_HARDWARE_ENCODER", "").strip()
        if hardware and hardware not in HARDWARE_ENCODERS:
            raise ValueError(
                f"VIDEOCUT_HARDWARE_ENCODER must be empty or one of {', '.join(HARDWARE_ENCODERS)}"
            )
        raw_limit = env.get("VIDEOCUT_MAX_UPLOAD_BYTES", "").strip()
        try:
            limit = int(raw_limit) if raw_limit else DEFAULT_MAX_UPLOAD_BYTES
        except ValueError:
            raise ValueError("VIDEOCUT_MAX_UPLOAD_BYTES must be an integer (bytes)") from None
        if limit < 1:
            raise ValueError("VIDEOCUT_MAX_UPLOAD_BYTES must be positive")
        return cls(
            ffmpeg_path=env.get("FFMPEG_PATH", "").strip(),
            ffprobe_path=env.get("FFPROBE_PATH", "").strip(),
            hardware_encoder=hardware,
            max_upload_bytes=limit,
        )
