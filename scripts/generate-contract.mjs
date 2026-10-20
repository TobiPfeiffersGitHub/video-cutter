// Regenerates contract/openapi.json (from the FastAPI app) and frontend/src/api/schema.d.ts
// (via openapi-typescript). With --check, regenerates into a temp dir and fails if the
// committed files differ, so contract drift cannot reach main.
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { BACKEND, FRONTEND, ROOT, npmCommand, requireVenv, run, venvPython } from "./lib/run.mjs";

const check = process.argv.includes("--check");
const OPENAPI = join(ROOT, "contract", "openapi.json");
const TYPES = join(FRONTEND, "src", "api", "schema.d.ts");

requireVenv();
const outDir = check ? mkdtempSync(join(tmpdir(), "videocut-contract-")) : null;
const openapiOut = outDir ? join(outDir, "openapi.json") : OPENAPI;
const typesOut = outDir ? join(outDir, "schema.d.ts") : TYPES;

try {
  run(venvPython, ["-m", "app.contract_gen", openapiOut], { cwd: BACKEND });
  run(npmCommand(), ["exec", "--", "openapi-typescript", openapiOut, "-o", typesOut], {
    cwd: FRONTEND,
  });

  if (check) {
    // Compare ignoring CR so a CRLF checkout does not look like drift.
    const normalize = (path) => readFileSync(path, "utf8").replace(/\r\n/g, "\n");
    const stale = [[OPENAPI, openapiOut], [TYPES, typesOut]].filter(
      ([committed, fresh]) => normalize(committed) !== normalize(fresh),
    );
    if (stale.length > 0) {
      console.error("\nGenerated contract files are out of date:");
      for (const [committed] of stale) console.error(`  ${committed}`);
      console.error("Run `npm run contract` and commit the result.");
      process.exit(1);
    }
    console.log("\nContract files are up to date.");
  } else {
    // Keep LF line endings regardless of platform.
    for (const path of [OPENAPI, TYPES]) {
      writeFileSync(path, readFileSync(path, "utf8").replace(/\r\n/g, "\n"));
    }
  }
} finally {
  if (outDir) rmSync(outDir, { recursive: true, force: true });
}
