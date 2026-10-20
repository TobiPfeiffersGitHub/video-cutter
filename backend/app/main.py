from fastapi import FastAPI

app = FastAPI(title="videocut", version="0.1.0")


@app.get("/api/v1/ping", tags=["meta"])
def ping() -> dict[str, str]:
    """Liveness check. The tool-aware health endpoint arrives in a later package."""
    return {"status": "ok"}
