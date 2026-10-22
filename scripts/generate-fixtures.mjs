// Generates the lavfi test media (normal, no_audio, rotated, vfr) into backend/tests/.generated/.
// Pass extra arguments through, e.g. `npm run fixtures -- --out some/dir`.
import { BACKEND, requireVenv, run, venvPython } from "./lib/run.mjs";

requireVenv();
run(venvPython, ["-m", "tests.fixtures_gen", ...process.argv.slice(2)], { cwd: BACKEND });
