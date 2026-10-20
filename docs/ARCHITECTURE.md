# Architecture

This document describes the architecture decided in `SYSTEM_PROMPT.md` and marks
what exists today. **Currently implemented: the application shell and CI only.**

## Decided design

- **Non-destructive editing.** The frontend never touches video bytes. It edits a
  small JSON document, the Edit Decision List (EDL). The backend turns the EDL
  into one FFmpeg command. Times are integer frames with a rational fps.
- **Contract first.** `contract/edl.schema.json` is the EDL source of truth.
  FastAPI generates `contract/openapi.json`; the frontend generates its types from it.
- **Pure core.** Domain logic (EDL validation, frame/time math, FFmpeg argument
  building, progress math) lives in `backend/app/core/` with no web-framework imports.
- **Stack.** React + Vite + TypeScript + Tailwind; Python 3.11+, FastAPI,
  Pydantic v2, SQLAlchemy 2, Alembic; SQLite locally; external FFmpeg/ffprobe;
  in-process worker threads.
- **Storage and users behind interfaces.** Every table carries `user_id`; every
  repository call requires it; media URLs are issued by the API.

## Repository layout today

```
backend/
  app/main.py        FastAPI app (one liveness route: GET /api/v1/ping)
  app/api/           route modules (empty)
  app/core/          pure domain logic (empty)
  tests/             pytest
frontend/
  src/               React shell; src/api/ holds the typed-fetch helpers
scripts/             cross-platform Node scripts: setup, dev, test, license check
docs/                this folder
.github/workflows/   ci.yml
```

Directories from the target layout that have no code yet (`contract/`, `jobs/`,
`storage/`, `db/`, `auth/`, `e2e/`) are created by the packages that need them.

## Development wiring

- `npm run dev` starts uvicorn (`--reload`) and Vite together. Vite proxies
  `/api` to the backend, so the frontend always uses same-origin relative URLs.
- Developer commands are Node scripts using argument lists (never `shell=True`
  on the Python side), so they behave the same in PowerShell and POSIX shells.
- The backend does not use asyncio subprocess APIs; FFmpeg will run through
  `subprocess.Popen` in worker threads (a later package).

## Not implemented yet

Health/tool discovery, EDL contract, rendering core, persistence, uploads, jobs,
proxies, timeline UI, export, authentication, and deployment.
