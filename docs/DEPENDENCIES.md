# Dependencies

Every dependency must be under a permissive license and justified in one line.
The policy is enforced by `npm run licenses` (part of `npm test`), using
`scripts/license-policy.json`. Python packages are installed from prebuilt wheels
only (`pip install --only-binary=:all:`), so no compiler toolchain is needed.

Versions are pinned in `backend/requirements*.txt` and `frontend/package-lock.json`.
Only direct dependencies are listed here; transitive ones are covered by the
license check.

## Backend (runtime) — `backend/requirements.txt`

| Package | License | Purpose |
| --- | --- | --- |
| fastapi | MIT | HTTP API framework |
| uvicorn | BSD-3-Clause | ASGI server |
| pydantic (via fastapi) | MIT | Request/response models (Pydantic v2) |

## Backend (development) — `backend/requirements-dev.txt`

| Package | License | Purpose |
| --- | --- | --- |
| pytest | MIT | Test runner |
| jsonschema | MIT | Checks `contract/edl.schema.json` against the Pydantic models in tests (pulls attrs, referencing, rpds-py, jsonschema-specifications, all MIT; wheels only) |
| httpx | BSD-3-Clause | Required by FastAPI's `TestClient` |
| ruff | MIT | Linting |
| pip-licenses | MIT | Python license-policy check |

## Frontend (runtime) — `frontend/package.json`

| Package | License | Purpose |
| --- | --- | --- |
| react, react-dom | MIT | UI library |

## Frontend (development)

| Package | License | Purpose |
| --- | --- | --- |
| vite, @vitejs/plugin-react | MIT | Dev server, bundler, React transform |
| typescript | Apache-2.0 | Type checking |
| tailwindcss, @tailwindcss/vite | MIT | Styling |
| vitest, jsdom | MIT | Unit test runner and DOM environment |
| @testing-library/react, /dom, /jest-dom | MIT | Component testing helpers |
| eslint, @eslint/js, typescript-eslint, eslint-plugin-react-hooks, globals | MIT | Linting |
| @types/react, @types/react-dom, @types/node | MIT | Type definitions |
| openapi-typescript | MIT | Generates `src/api/schema.d.ts` from `contract/openapi.json` |
| license-checker-rseidelsohn | BSD-3-Clause | npm license-policy check (maintained fork of `license-checker`) |

## License exceptions

Some transitive, build-time-only packages are not MIT/BSD/Apache/ISC. Each is
listed with its reason in `scripts/license-policy.json`:

| Package | License | Why accepted |
| --- | --- | --- |
| certifi (Python, via httpx) | MPL-2.0 | Unmodified; test client only, not a runtime requirement |
| lightningcss* (npm, via Tailwind) | MPL-2.0 | Unmodified build tool; never shipped in the built app |
| caniuse-lite (npm) | CC-BY-4.0 | Build-time data; not shipped |
| spdx-exceptions, spdx-ranges (npm) | CC-BY-3.0 | Data used by the license checker itself |

MPL-2.0 is a file-level weak copyleft license, so it is not on the general
allow list; each exception names exact packages and license strings.

## External tools (not dependencies, not bundled)

| Tool | License | Purpose |
| --- | --- | --- |
| FFmpeg / ffprobe | LGPL or GPL depending on build | Installed by the user; discovered by `/api/v1/health`; run by the media tests and (later) exports. CI installs it from the runner's package manager (Chocolatey on Windows, apt on Linux) only to run tests; nothing is redistributed. See [LICENSING.md](LICENSING.md) |

## GitHub Actions

Pinned to commit SHAs in `.github/workflows/ci.yml`.

| Action | Pinned upstream version |
| --- | --- |
| actions/checkout | v7.0.1 |
| actions/setup-node | v7.1.0 |
| actions/setup-python | v7.0.0 |

No new Python or npm dependency was added for the rendering core, golden tests, or
fixtures; they use the standard library, Pydantic, jsonschema and pytest already listed.

## Known notes

- `openapi-typescript` 7.x declares a peer dependency on TypeScript 5, while the
  project uses TypeScript 6. `frontend/package.json` has an `overrides` entry that
  resolves that peer to the project's TypeScript. Remove it once upstream widens
  the range.
- `npm ci` prints a deprecation warning for `glob@10` pulled in by the license
  checker. It is a development-only tool and is not part of the built app.
