# videocut

A local-first, browser-based video cutter: upload a video, cut or speed up
ranges, crop, and export MP4 or WAV. Windows first, portable to Linux.
Licensed under MIT (see [LICENSE](LICENSE)).

## Status

Early development. **Implemented:** a FastAPI backend with a liveness route and
`GET /api/v1/health` (FFmpeg/ffprobe versions, encoders, limits), the EDL
contract (JSON Schema, Pydantic models, frame/time helpers, generated OpenAPI and
TypeScript types), a React/Vite/Tailwind application shell, and CI.
**Not implemented yet:** rendering, upload, preview, timeline, editing, crop,
export, projects, and authentication.

## Prerequisites

- Python 3.11+ (CI uses 3.12)
- Node.js 20.19+ or 22.12+ (see `.nvmrc`)
- FFmpeg and ffprobe, installed separately (not bundled; the app starts without it
  but `/api/v1/health` reports `degraded`). Windows: `winget install Gyan.FFmpeg`. Debian/Ubuntu:
  `sudo apt install ffmpeg`. See [docs/RUNNING_WINDOWS.md](docs/RUNNING_WINDOWS.md).

## Quick start

```
npm run setup   # one-time: Python venv + pinned wheels + npm packages
npm run dev     # backend http://127.0.0.1:8000, frontend http://127.0.0.1:5173
npm test        # backend + frontend lint/tests, type check, build, license policy
```

`npm run dev` starts both servers and `Ctrl+C` stops both. The frontend dev
server proxies `/api` to the backend. Copy `.env.example` to `.env` to document
overrides; the scripts read ordinary environment variables
(`VIDEOCUT_PORT`, `VIDEOCUT_FRONTEND_PORT`, `VIDEOCUT_HOST`).

## Troubleshooting

- **FFmpeg not found** (`/api/v1/health` shows `degraded` with a hint): install it
  and open a new terminal, or set `FFMPEG_PATH` / `FFPROBE_PATH` to the
  executables. Restart the backend afterwards, since tools are discovered once at startup.
- **Port in use:** `npm run dev` refuses to start and names the port. Stop the
  other process or set `VIDEOCUT_PORT` (backend, default 8000) /
  `VIDEOCUT_FRONTEND_PORT` (frontend, default 5173).
- **Large upload rejected:** uploads do not exist yet. When they arrive, a
  configurable maximum size will apply and this section will document it.
- **`no matching distribution` during setup:** setup installs wheels only, so a
  Python version without prebuilt packages fails by design. Use Python 3.12.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Dependencies and license policy](docs/DEPENDENCIES.md)
- [Licensing notes (not legal advice)](docs/LICENSING.md)
- [Running on Windows](docs/RUNNING_WINDOWS.md)
- [Product spec](SYSTEM_PROMPT.md) and [implementation packages](IMPLEMENTATION_PACKAGES.md)
