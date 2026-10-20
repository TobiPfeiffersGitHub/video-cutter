// One-command setup: backend venv + pinned Python deps, then frontend deps via npm ci.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { BACKEND, FRONTEND, ROOT, isWindows, npmCommand, run, venvPython } from "./lib/run.mjs";

const MIN_PYTHON = [3, 11];
const MIN_NODE_MAJOR = 20;

function fail(message) {
  console.error(`\nSetup failed: ${message}`);
  process.exit(1);
}

function findPython() {
  const candidates = isWindows
    ? [["py", ["-3"]], ["python", []], ["python3", []]]
    : [["python3", []], ["python", []]];
  for (const [command, prefix] of candidates) {
    const probe = spawnSync(
      command,
      [...prefix, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
      { encoding: "utf8" },
    );
    if (probe.status !== 0) continue;
    const [major, minor] = probe.stdout.trim().split(" ").map(Number);
    if (major > MIN_PYTHON[0] || (major === MIN_PYTHON[0] && minor >= MIN_PYTHON[1])) {
      return [command, prefix];
    }
  }
  return null;
}

const nodeMajor = Number(process.versions.node.split(".")[0]);
if (nodeMajor < MIN_NODE_MAJOR) {
  fail(`Node ${MIN_NODE_MAJOR}+ is required (found ${process.versions.node}). See .nvmrc.`);
}

if (!existsSync(venvPython)) {
  const python = findPython();
  if (!python) fail(`Python ${MIN_PYTHON.join(".")}+ was not found on PATH.`);
  run(python[0], [...python[1], "-m", "venv", join(BACKEND, ".venv")]);
}

// Wheels only: nothing may compile on install (no Rust or C/C++ toolchain required).
run(venvPython, [
  "-m", "pip", "install", "--only-binary=:all:", "-r", join(BACKEND, "requirements-dev.txt"),
]);
run(npmCommand(), ["ci"], { cwd: FRONTEND });

console.log("\nSetup complete. Next: `npm run dev` or `npm test`.");
console.log(`Repository root: ${ROOT}`);
