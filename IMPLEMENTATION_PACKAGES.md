# videocut: Commit-Sized Implementation Packages

This document splits SYSTEM_PROMPT.md into ordered implementation packages.
Each package should result in one focused, tested commit. This document is a
plan, not a claim that any package has been implemented.

There are 12 packages: 10 for the local editor through Phase 2, followed by two
optional packages for authentication and cloud readiness. Related features are
grouped into larger coherent commits rather than separate commits per component.

The first **implementation** commit is Package 01: setup and GitHub Actions CI.
Do not combine it with video editing features. This planning document can be
committed separately before implementation.

## How To Use These Prompts

For each session, give the coding assistant the shared system prompt below and
the prompt for exactly one package. Complete packages in order. Do not ask it to
implement the entire original brief in one session.

Suggested commit subjects are provided, not executed commands. Only create a
commit when explicitly requested, after reviewing the diff and running checks.
Never rewrite existing history or fabricate dates, authors, or test evidence.
The goal is a useful, reviewable development history.

## Shared System Prompt

```text
You are implementing videocut, a local-first video editor, in this repository.
Read SYSTEM_PROMPT.md in full and inspect the existing code before editing.
Treat that document as the product and architecture specification. The selected
package below is the boundary for this session, not permission to build later
packages. If the source brief asks for all phases, the selected package's stop
condition takes precedence for this session.

Begin with a short plan naming the files and checks needed for this package.
Implement the smallest complete, reviewable change that satisfies it. Preserve
existing user changes. Do not add placeholders for future features or unrelated
refactors. Add tests with the behavior they protect, not in a later test-only
commit. Keep the repository runnable and its existing checks passing.

Keep the decided stack: React, Vite, TypeScript, Zustand, Tailwind; Python 3.11+,
FastAPI, Pydantic v2, SQLAlchemy 2, Alembic; SQLite locally; external FFmpeg and
ffprobe; worker threads. Keep core domain logic free of web-framework imports.
Use rational fps and integer frames. The EDL schema is the source of truth.
Never manipulate video bytes in the frontend or export from a preview proxy.

Before adding dependencies, verify permissive licenses, including transitive
dependencies, and record license and purpose in docs/DEPENDENCIES.md. Verify
Python installs with pip install --only-binary=:all: on Windows. Require prebuilt
packages, not a Rust or C/C++ toolchain. Enforce the license policy in tests.
Do not bundle FFmpeg. Generate media fixtures with FFmpeg lavfi only.

Use pathlib and subprocess argument lists, never shell=True or asyncio subprocess
APIs. Developer and test commands must work in PowerShell and POSIX shells.
Keep storage behind the specified interface. Require user_id in repositories
from their introduction, even before authentication exists. The API owns media
URLs. Do not add Keycloak or cloud infrastructure before explicit approval.

Update relevant docs and CI as functionality arrives. Regenerate committed
OpenAPI and frontend API types whenever an API contract changes. CI must detect
generated-contract drift once generation exists. Do not weaken checks to pass.

Run the package checks and existing relevant regression checks. Report commands,
actual outcomes, assumptions, and remaining gaps. Never claim unrun tests or
unmeasured performance. At a phase boundary, also run the full test command and
the app, then report the phase gate. If blocked, explain the blocker; do not mark
the package complete or silently change the architecture.

Stop after this package. Provide its suggested commit subject and a concise diff
summary. Create exactly one commit only if the user explicitly authorized it;
stage only this package's files. Do not start the next package automatically.
```

## Sequence

| Package | Phase | Deliverable |
| --- | --- | --- |
| 01 | 0 | Runnable setup and GitHub Actions CI |
| 02 | 0 | Health, EDL contract and generated API types |
| 03 | 0 | Rendering core, golden tests, fixtures and Phase 0 gate |
| 04 | 1 | User-scoped persistence, storage and streaming uploads |
| 05 | 1 | Jobs, proxy preparation, media serving and project API |
| 06 | 1 | Upload UI, frame-aware player and interactive timeline |
| 07 | 1 | Segment editing, autosave, edited preview and crop |
| 08 | 1 | MP4/WAV export, download and Phase 1 gate |
| 09 | 2 | Undo/redo, project reopening and waveform |
| 10 | 2 | Cancellation, cleanup, polish, measurements and Phase 2 gate |
| 11 | 3, approval required | OIDC authentication, signed media and isolation |
| 12 | 4, approval required | Containers, Postgres, object storage and separate worker |

## Phase 0: Foundations

### Package 01: Setup And CI

Suggested commit: `chore: bootstrap app and cross-platform CI`

```text
Create the minimal runnable repository structure from the brief, with a FastAPI
app and a React/Vite/TypeScript/Tailwind frontend. Show a minimal application
shell, not a marketing page or a pretend editor. Add a small backend smoke test
and a frontend smoke test that really execute. Do not add database, uploads,
FFmpeg processing, authentication, or deployment yet.

Provide backend/pyproject.toml, reproducible dependency inputs for both stacks,
Node/Python version declarations, .gitignore, and a safe example environment
file. Use Python 3.11+ and a supported Node LTS compatible with the chosen Vite.
Add cross-platform root commands for setup, dev, and test. Dev must start both
apps and terminate both cleanly; route frontend API calls through a dev proxy.
Avoid installing dependencies that are not used yet.

Create .github/workflows/ci.yml now. Trigger on push and pull_request, use
read-only repository permissions, cancel superseded runs, and set timeouts.
Run on windows-latest and ubuntu-latest. Install Python packages using
--only-binary=:all: and install frontend packages with npm ci. Cache downloads
using dependency-file keys. Run real backend/frontend tests, lint, TypeScript
checks, the frontend production build, and Python/npm license-policy checks.
Use pip-licenses and license-checker, with explicit handling of license
expressions and missing metadata; do not merely print license inventories.
Pin action revisions and document their upstream versions. Do not add CD,
deployment secrets, containers, or fake success steps.

Create initial docs/ARCHITECTURE.md, docs/DEPENDENCIES.md, docs/LICENSING.md and
docs/RUNNING_WINDOWS.md. Explain MIT application code versus externally installed
FFmpeg, GPL distribution obligations for future images, H.264 patents, and that
this is not legal advice. Update README with prerequisites, one-command setup,
start and test, plus troubleshooting for missing FFmpeg, occupied ports, and
future upload limits, clearly marking features not implemented yet.

Verify setup, tests, and production build locally; start both apps and exercise
the smoke path. Validate workflow syntax. A local run does not prove hosted CI
passed: report GitHub matrix execution as pending unless actually observed.
Stop with a runnable foundation and executable CI, not the whole Phase 0.
```

### Package 02: Health And Contracts

Suggested commit: `feat: add tool health and typed EDL contracts`

```text
Implement GET /api/v1/health with configured limits, FFmpeg/ffprobe versions,
available encoders, and actionable missing-tool errors. Resolve FFMPEG_PATH and
FFPROBE_PATH before PATH. Discover encoders at startup, not on every request.
Describe software fallback order libx264, libopenh264, libsvtav1, and detected
opt-in h264_nvenc/h264_qsv; hardware must never be the default. Keep discovery
separate from HTTP handlers and do not introduce rendering yet.
Test missing executables, configured paths containing spaces, malformed output,
and encoder selection. Verify health against locally installed tools when
available. Document Windows winget installation and Linux distribution packages.

Add contract/edl.schema.json, matching Pydantic v2 models and pure core validation
and frame/time helpers. Enforce rational positive fps, integer inclusive-start/
exclusive-end frames, ordered non-overlapping segments, unique segment IDs,
speed 0.25 through 16, default mute=false, and normalized crop bounds/minimum size.
Validate source-dependent limits such as total_frames in core, since a standalone
JSON Schema cannot express every cross-field or source-dependent constraint.
Document any policy needed for an empty EDL or non-drop-frame HH:MM:SS:FF input.
Expose the EDL model in the generated API components without adding a fake route.
Generate and commit contract/openapi.json and frontend types using
openapi-typescript. Provide deterministic regeneration and CI drift checks.
Test schema/model agreement and boundary/invalid cases, including 30000/1001 fps.
```

### Package 03: Rendering Core And Phase 0 Gate

Suggested commit: `feat: add tested FFmpeg rendering core and fixtures`

```text
Implement pure probe-data-to-render-plan and FFmpeg argument-list functions in
backend/app/core. Cover frame-to-seconds math, expected output duration, atempo
stages restricted to 0.5 through 2, silence for mute/no-audio cases, trim/setpts,
concat, rotation-aware even-pixel crop and yuv420p. Generate one filter_complex,
not shell strings. Handle MP4 encoder/quality options, CFR output, AAC 192k,
faststart, and audio-only 48 kHz pcm_s16le WAV. Do not execute jobs or add routes.
Define a consistent no-audio WAV policy and encoder-specific options; do not
pass libx264-only settings blindly to fallback or hardware encoders.
Add language-neutral contract/golden JSON cases with probe, edl, options and
exact expected argument lists. Test speed extremes, mixed mute, all-muted,
no-audio, rotation, VFR metadata, one frame, crop, WAV and encoder fallbacks.

Add a cross-platform FFmpeg lavfi fixture generator using testsrc2 and sine,
including burned-in frame numbers. Generate normal, no-audio, rotated, and VFR
sources; avoid committing generated media. Handle font discovery portably and
make fixture generation reproducible. Add executable integration smoke tests
that run the argument builder output and inspect results with ffprobe.
Extend CI to provision external FFmpeg on Windows/Linux, generate fixtures, and
run these tests. Keep installation checks explicit rather than silently skipping
required media tests. The root test command must now run all existing checks,
license checks, golden tests and generated-contract drift checks.
Run both apps, health, generation, build, and the full test command. Report Phase
0 results and any gaps. Do not begin uploads until this gate passes.
```

## Phase 1: Usable Editor

### Package 04: Persistence, Storage And Uploads

Suggested commit: `feat: add user-scoped storage and streaming uploads`

```text
Add SQLAlchemy 2, Alembic and initial asset/project/job tables with user_id on
every application table. Enable SQLite WAL locally without SQLite-only domain
queries. Introduce repositories requiring user_id for every operation and a
fixed current_user dependency. Do not implement Keycloak.
Test migrations from an empty database and prove user A cannot read, update or
delete user B's rows. Keep session ownership and transaction boundaries explicit.
Account for framework-owned migration bookkeeping separately from user data.

Implement the specified Storage interface and local disk storage under a
configurable data directory. Reject path traversal and use server-generated keys.
Implement POST /api/v1/assets as a bounded-memory streaming upload with a
configurable byte limit, including requests without Content-Length. Persist the
asset as processing for the later worker pipeline; do not fake preview readiness.
Test stored content, oversize rejection, interrupted upload cleanup, handle
closure, and ownership. Demonstrate bounded chunking; reserve the full measured
3 GB RSS acceptance run for Package 10. Update upload-limit troubleshooting.
```

### Package 05: Media Pipeline And Project API

Suggested commit: `feat: prepare seekable previews and persist editing projects`

```text
Implement an in-process thread worker with configurable concurrency, default 1,
persisted job states, and a subprocess.Popen runner that drains progress and
stderr without deadlock. Add pure out_time_us progress parsing and expected-
duration calculations. Add scoped GET /api/v1/jobs/{id} and its SSE events route;
support polling and client disconnects without leaking resources.
On startup mark interrupted running jobs failed; define queued-job recovery.
Test scheduling, bounded diagnostics, malformed progress, restart recovery and
isolation with controlled child processes. Structure process ownership so later
tree cancellation is possible, but do not add the cancellation endpoint yet.

Connect completed uploads to probe/proxy worker jobs. Parse duration, rational
fps, displayed dimensions, rotation, codecs and audio presence; detect VFR and
choose/document a rational CFR project rate with one-frame cut tolerance.
Generate at-most-720p H.264/AAC CFR proxies, veryfast preset, faststart and
roughly 0.5-second keyframe spacing. Handle no-audio and rotated sources, and
fail clearly if a suitable H.264 proxy encoder is unavailable.
Add scoped GET /api/v1/assets/{id} with metadata, state, proxy progress and an
API-issued media_url only when ready. Test the real pipeline and failure paths
using generated fixtures. Retain originals for export.

Serve proxy media through an ownership-checked route with HTTP Range support.
Test actual 206 bodies and Content-Range for normal, suffix and open-ended
ranges, plus 416 for unsatisfiable ranges. Never expose arbitrary disk paths.
Implement scoped DELETE /api/v1/assets/{id}. Define dependent-project and active-
job behavior explicitly; reject unsafe deletion until cancellation is available.
Close streams before file deletion and test Windows-compatible cleanup.

Implement project creation, listing, retrieval and update under /api/v1/projects,
using POST/GET on the collection and GET/PUT on /{id}. Each project owns one
accessible asset and one validated EDL. Use source metadata for bounds checks
on every write. This clarifies the brief's ambiguous collection-level PUT.
Test ownership, invalid edits, missing/unready assets, round trips and concurrent
save behavior. Keep the API suitable for debounced autosave and regenerate types.
```

### Package 06: Upload, Player And Timeline UI

Suggested commit: `feat: add video upload playback and interactive timeline`

```text
Build an original, responsive editor shell with drag/drop and file-picker upload,
real upload progress, preparing-preview progress and recoverable error states.
Use generated API types and API-issued media_url values. Create/open a project
when the asset is ready. Play only the proxy in an HTML5 video element.
Add play/pause, frame stepping, boundary jumps and J/K/L shuttle controls. Track
frames using requestVideoFrameCallback with a documented fallback; seek to
(frame + 0.5) * den / num. Handle unsupported reverse playback deliberately.
Test upload-to-preview, seeking, controls, focus handling and error states with
Playwright and generated fixtures. Verify desktop and mobile layouts.

Render the ruler on canvas and segments from the EDL. Add playhead scrubbing,
segment selection, range dragging, zoom via Ctrl+wheel, pan, and snapping to
playhead/segment edges. Keep pointer-to-frame math independent and testable.
Throttle seeks through requestAnimationFrame and skip while a seek is pending.
Test zoom/pan coordinate mapping, drag constraints, snapping and selection in
unit/browser tests. Include a 300-segment scenario; defer the measured FPS
report to Package 10, without claiming 60 fps based on rendering tests alone.
```

### Package 07: Editing, Preview And Crop

Suggested commit: `feat: add segment editing crop and edited preview`

```text
Add pure editing operations and Zustand project state for split (S), delete
(Delete), speed, mute, I/O marks, cut range and speed range. Add validated start/
end entry as frame numbers or HH:MM:SS:FF. Preserve source order and bounds.
Debounce autosave and make failed/stale saves visible without overwriting newer
edits. Add play-edited mode using animation-frame boundary checks to skip cuts,
apply browser-supported rates with visible clamping, preserve pitch and honor
mute. Restore ordinary playback settings when leaving edited mode.
Test editing math, empty/full ranges, numeric validation, autosave races and
preview behavior. Do not implement undo/redo yet.

Add a draggable/resizable crop overlay with handles, outside dimming, numeric
inputs and free/16:9/9:16/1:1/4:3 aspect presets. Map to the actual displayed video
rectangle, excluding letterboxing and accounting for rotation. Store normalized
EDL values, enforce minimum size and show even-pixel export dimensions using
the same documented rounding policy as the backend.
Test drag/resize bounds, aspect presets, numeric edits, resized viewports,
portrait rotation and letterboxed playback. Verify desktop/mobile screenshots.
```

### Package 08: Export And Phase 1 Gate

Suggested commit: `feat: export and download edited MP4 and WAV media`

```text
Implement scoped POST /api/v1/projects/{id}/exports with format and quality.
Snapshot the validated EDL and original asset reference when queueing. Execute
the existing argument builder in the worker, expose progress/encoder choice,
and add GET /api/v1/exports/{job_id}/download with attachment disposition.
Never render from the proxy; reject unfinished or inaccessible downloads.
Run automated real-FFmpeg acceptance tests: 60-second source with three cuts,
duration and seam-frame accuracy within one frame, 4x and mixed 0.5x/16x speed,
A/V stream duration difference under 40 ms, crop dimensions, no audio, rotation,
VFR, all muted and one-frame output. Verify WAV is pcm_s16le/48 kHz/no video with
the expected duration. Check actual seam content, not duration alone. Explain
and resolve failures rather than loosening the brief's tolerances silently.

Add the export dialog with MP4/WAV, quality, expected duration, actual encoder,
progress via SSE with polling fallback, completion and download states. Show
bounded useful FFmpeg errors. Cancellation is delivered in Package 10; do not
display a working-looking Cancel control before its endpoint exists.
Add the acceptance Playwright flow: upload a generated fixture, split, delete,
change speed, crop, export MP4, download and inspect the file with ffprobe. Also
exercise WAV download. Run the full test command and both apps for the Phase 1
gate. Report the explicit cancellation deferral to Phase 2, matching its phase
scope even though the frontend feature list mentions it earlier.
```

## Phase 2: Hardening

### Package 09: History, Projects And Waveform

Suggested commit: `feat: add edit history project reopening and waveforms`

```text
Add bounded plain-JSON EDL history with undo/redo controls and shortcuts. Group
continuous drag/input changes into useful transactions, clear redo after a new
edit and avoid recording autosave/server acknowledgements as user edits.
Undo/redo must update preview and autosave. Test every editing operation,
history limits, drag grouping, project switches and failed saves.

Add a scoped project list and reopen workflow using the existing API. Restore
the saved EDL, preview and asset status without leaking previous project state.
Handle loading, empty lists, missing assets and unsaved changes. Test reload
persistence, switching projects and navigation in Playwright.

Compute bounded-size waveform peaks JSON via an FFmpeg PCM pipe in a worker,
without loading entire audio files into memory. Persist/cache peaks through
storage and expose them through an ownership-checked API route. Handle silence,
no audio, failed generation and zoom-dependent rendering.
Draw the waveform on the existing timeline canvas. Test peaks, timing alignment,
cache behavior, ownership and rendering without blocking timeline interactions.
```

### Package 10: Hardening And Phase 2 Gate

Suggested commit: `feat: harden job lifecycle and verify editor performance`

```text
Implement scoped POST /api/v1/jobs/{id}/cancel and connect the export Cancel
control. Stop complete FFmpeg process trees on Windows and Linux, close handles
before deleting partial files and handle completion/cancel races idempotently.
Cover queued and running jobs, including preparation jobs where applicable.
Add configurable cleanup for abandoned temp files and expired exports without
deleting active jobs or referenced originals/proxies. Test real process-tree
termination, isolation, cleanup boundaries and file-lock behavior on Windows CI.

Finish keyboard shortcut help, focus-safe shortcuts and actionable errors for
missing tools, unsupported uploads, interrupted jobs and failed saves/exports.
Add targeted regression tests for defects found; do not use this package as a
substitute for tests omitted from earlier packages.
Add reproducible benchmark commands and record machine/tool versions, inputs,
method and actual results in docs/PERFORMANCE.md: 1080p30 proxy speed relative
to real time, export speed, peak backend RSS growth during an actual 3 GB
streaming upload, and timeline FPS while dragging with 300 segments. Target
proxy speed >=3x real time, upload RSS growth <300 MB and timeline 60 fps.
Avoid allocating the upload body in client memory. Report idle baseline and
sampling method. Explain misses and proposed changes; never invent numbers.
Run the complete pytest/Playwright/license/build/contract suite and the app.
Report all Phase 2 acceptance evidence, assumptions and known gaps. If a required
measurement is blocked, mark the gate incomplete. STOP after Phase 2 and wait
for explicit approval before starting any Phase 3 work.
```

## Phase 3: Authentication, Only After Approval

### Package 11: Authentication And Isolation

Suggested commit: `feat: add OIDC authentication and secure user media access`

```text
First verify explicit Phase 3 approval. Add docker-compose.yml for Keycloak dev
mode and a committed importable realm export with a public Authorization Code
plus PKCE client, self-registration and local redirect origins. Commit no real
secrets; document Docker Desktop or Java requirements on Windows. Test realm
import and discovery. Do not replace repository ownership checks with UI checks.

Add frontend login/logout using an approved OIDC library. Replace fixed
current_user with backend PyJWT JWKS validation of signature, issuer, audience
and expiry; user_id is sub. Handle key rotation and invalid tokens safely.
Use access tokens for API calls, not identity tokens. Test login, logout,
expiry, invalid claims, unknown keys and user-scoped API access. Define how
existing default-user projects are handled without silently assigning them.

Issue short-lived HMAC-signed media_url values for video playback. Bind each
signature to the resource, user and expiry, support Range requests, and keep
frontend URL consumption unchanged. Prevent tampering, expiry bypass and token
leakage in logs. Define refresh behavior for long playback sessions.
Test two real identities across assets, projects, jobs, events, cancellation,
waveforms, media and downloads, including guessed IDs and forged/expired URLs.
Run the full suite and app for the Phase 3 gate. Phase 4 needs separate approval.
```

## Phase 4: Cloud Readiness, Only After Approval

### Package 12: Cloud Readiness

Suggested commit: `feat: add portable cloud storage and worker deployment`

```text
First verify explicit Phase 4 approval. Add a Python-slim backend Dockerfile
with distribution FFmpeg and a static frontend production build. Configure
runtime behavior through environment variables and document persistence,
health, proxy routing and upload limits. Do not commit secrets.
Test the built images and a real upload/export. Document FFmpeg/GPL distribution
obligations and distinguish local CI provisioning from distributing images.
Do not add automatic deployment without a separately agreed deployment target.

Add DATABASE_URL-based Postgres support using existing migrations/repositories.
Implement S3-compatible Storage behind the existing interface; materialize
originals/proxies to managed local scratch for FFmpeg and release them safely.
Document credentials through environment variables only. Verify licenses and
prebuilt driver packages before adding them.
Run repository/isolation tests against SQLite and Postgres, plus storage contract
tests against local disk and an explicitly configured S3-compatible test service.
Test interrupted transfers, scratch cleanup and export/download integrity.

Make the existing worker runnable as a separate process using the jobs table,
not Redis or a new broker. Define atomic job claiming, ownership, recovery and
cancellation signaling. Preserve the in-process local mode and clarify that
API startup must not mark a separate worker's live jobs interrupted.
Test duplicate-claim prevention, worker failure/restart, cancellation across
processes and complete upload-to-export behavior. Extend CI for these new
integration paths without weakening Windows-first local checks.
Document static frontend hosting versus the container host needed for long
FFmpeg jobs; a static/serverless frontend host does not run the media worker.
Run the full suite and deployed-style app for the Phase 4 gate, then stop.
```

## Coverage And Deliberate Clarifications

- Setup and CI arrive first; deployment does not. CI grows with each capability.
- Schema/model validation, generated API types and golden rendering cases are
  foundation work, before upload/editor implementation.
- User scoping begins with persistence in Package 04. Public authentication and
  full authenticated route isolation remain Phase 3, not a retrofit of ownership.
- Media processing tests accompany its implementation. Package 10 adds measured
  performance and remaining regressions, not all tests at the end.
- The brief's cancellation UI is deferred to Package 10 because its phase plan
  places job cancellation in Phase 2. This is explicit, not a nonfunctional button.
- Cross-field EDL invariants require core validation as well as JSON Schema.
  Ambiguous policies must be documented and tested, not silently invented.
- Encoder availability does not prove hardware usability. Hardware remains
  opt-in; failed initialization must produce a clear diagnostic.
- A package is complete only when its checks pass or blockers are explicitly
  reported. Hosted CI and benchmark results must never be inferred from local
  smoke tests. Phase 3 and Phase 4 each require the user's go-ahead.