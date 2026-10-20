from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.config import Settings
from app.core.toolchain import Toolchain, discover_toolchain
from app.openapi import build_openapi


def create_app(settings: Settings | None = None, toolchain: Toolchain | None = None) -> FastAPI:
    """Build the app. Tools are discovered once at startup, unless a toolchain is injected."""
    resolved = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved
        app.state.toolchain = toolchain or discover_toolchain(
            resolved.ffmpeg_path, resolved.ffprobe_path, resolved.hardware_encoder
        )
        yield

    app = FastAPI(title="videocut", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api/v1")

    @app.get("/api/v1/ping", tags=["meta"])
    def ping() -> dict[str, str]:
        """Liveness check that does not depend on FFmpeg."""
        return {"status": "ok"}

    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]
    return app


app = create_app()
