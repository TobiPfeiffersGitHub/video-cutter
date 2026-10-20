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

The app starts without FFmpeg, but `GET /api/v1/health` then reports
`status: "degraded"` with the fix, and later packages (rendering, proxies, export)
require it. If FFmpeg is not on `PATH`, set `FFMPEG_PATH` and `FFPROBE_PATH` to
the executables or to their folder (paths containing spaces are fine). On
Debian/Ubuntu install it with `sudo apt install ffmpeg`.

Check what the backend found (with `npm run dev` running):

```powershell
curl http://127.0.0.1:8000/api/v1/health
```

Tools are discovered once at startup: restart the backend after installing FFmpeg.
`VIDEOCUT_HARDWARE_ENCODER` (`h264_nvenc` or `h264_qsv`) opts in to a hardware
encoder; it is off by default.

## Setup, start, test

```powershell
npm run setup   # creates backend/.venv, installs pinned wheels and npm packages
npm run dev     # backend on :8000, frontend on :5173 (open http://127.0.0.1:5173)
npm test        # lint, type check, tests, production build, license policy, contract drift
npm run contract  # regenerate contract/openapi.json and frontend/src/api/schema.d.ts
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
