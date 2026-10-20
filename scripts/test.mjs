// Runs every check the project has. Stops at the first failure.
import { join } from "node:path";
import { BACKEND, FRONTEND, ROOT, npmCommand, requireVenv, run, venvPython } from "./lib/run.mjs";

requireVenv();
const npm = npmCommand();

run(process.execPath, ["--test", "scripts/**/*.test.mjs"], { cwd: ROOT });
run(venvPython, ["-m", "ruff", "check", "."], { cwd: BACKEND });
run(venvPython, ["-m", "pytest"], { cwd: BACKEND });
run(process.execPath, [join(ROOT, "scripts", "generate-contract.mjs"), "--check"], { cwd: ROOT });
run(npm, ["run", "lint"], { cwd: FRONTEND });
run(npm, ["run", "typecheck"], { cwd: FRONTEND });
run(npm, ["test"], { cwd: FRONTEND });
run(npm, ["run", "build"], { cwd: FRONTEND });
run(process.execPath, [join(ROOT, "scripts", "check-licenses.mjs")], { cwd: ROOT });

console.log("\nAll checks passed.");
