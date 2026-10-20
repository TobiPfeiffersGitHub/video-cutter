# Running on Windows

Commands work in PowerShell and in POSIX shells.

## Prerequisites

| Tool | Version | Install |
| --- | --- | --- |
| Python | 3.11 or newer | `winget install Python.Python.3.12` |
| Node.js | 20.19+ or 22.12+ (LTS; `.nvmrc` says 22) | `winget install OpenJS.NodeJS.LTS` |
| FFmpeg | any recent full build | `winget install Gyan.FFmpeg` |

Open a new terminal after installing so `PATH` is refreshed. Check:

```powershell
python --version
node --version
ffmpeg -version
```

FFmpeg is not needed to start the current application shell, but later packages
(health check, rendering, proxies, export) require it. If it is not on `PATH`,
set `FFMPEG_PATH` and `FFPROBE_PATH` to the full executable paths (see `.env.example`).

## Setup, start, test

```powershell
npm run setup   # creates backend/.venv, installs pinned wheels and npm packages
npm run dev     # backend on :8000, frontend on :5173 (open http://127.0.0.1:5173)
npm test        # lint, type check, tests, production build, license policy
```

Press `Ctrl+C` to stop; both the backend and the frontend are terminated.

## Notes

- `npm run setup` installs Python packages with `--only-binary=:all:`. If it
  fails with "no matching distribution", your Python version has no prebuilt
  wheel for a pinned package; use a Python version listed above (3.12 is what CI uses).
- The `backend/.venv` virtual environment is created and used by the scripts;
  you do not need to activate it.
- PowerShell may block `npm.ps1` with an execution-policy error. Use `npm.cmd`
  instead of `npm`, or run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
