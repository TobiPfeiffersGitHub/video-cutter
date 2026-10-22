"""GET /api/v1/health. Reads the toolchain discovered at startup; never runs tools."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import Settings
from app.core.edl import CROP_MIN_SIZE, SPEED_MAX, SPEED_MIN
from app.core.toolchain import Toolchain

router = APIRouter(tags=["meta"])


class ToolStatus(BaseModel):
    available: bool
    path: str | None
    version: str | None


class SelectedEncoder(BaseModel):
    name: str
    hardware: bool
    fallback: bool
    note: str | None


class Encoders(BaseModel):
    available: list[str]
    selected: SelectedEncoder | None
    hardware_opt_in: str | None


class Limits(BaseModel):
    max_upload_bytes: int
    speed_min: float
    speed_max: float
    crop_min_size: float


class HealthProblem(BaseModel):
    code: str
    message: str
    hint: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ffmpeg: ToolStatus
    ffprobe: ToolStatus
    encoders: Encoders
    limits: Limits
    problems: list[HealthProblem]


def build_health(toolchain: Toolchain, settings: Settings) -> HealthResponse:
    selected = toolchain.selected_encoder
    return HealthResponse(
        status="ok" if toolchain.ok else "degraded",
        ffmpeg=ToolStatus(
            available=toolchain.ffmpeg.available,
            path=toolchain.ffmpeg.path,
            version=toolchain.ffmpeg.version,
        ),
        ffprobe=ToolStatus(
            available=toolchain.ffprobe.available,
            path=toolchain.ffprobe.path,
            version=toolchain.ffprobe.version,
        ),
        encoders=Encoders(
            available=sorted(toolchain.encoders),
            selected=SelectedEncoder(
                name=selected.name,
                hardware=selected.hardware,
                fallback=selected.fallback,
                note=selected.note,
            )
            if selected
            else None,
            hardware_opt_in=settings.hardware_encoder or None,
        ),
        limits=Limits(
            max_upload_bytes=settings.max_upload_bytes,
            speed_min=SPEED_MIN,
            speed_max=SPEED_MAX,
            crop_min_size=CROP_MIN_SIZE,
        ),
        problems=[HealthProblem(**vars(problem)) for problem in toolchain.problems],
    )


@router.get("/health", response_model=HealthResponse, summary="Tool and limit status")
def health(request: Request) -> HealthResponse:
    """Always 200: missing tools are reported in `problems` with a fix, not as an error."""
    return build_health(request.app.state.toolchain, request.app.state.settings)
