// Enforces scripts/license-policy.json for installed Python and npm dependencies.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { evaluate } from "./lib/licenses.mjs";
import { FRONTEND, ROOT, npmCommand, requireVenv, run, venvPython } from "./lib/run.mjs";

const policy = JSON.parse(readFileSync(join(ROOT, "scripts", "license-policy.json"), "utf8"));

function pythonEntries() {
  requireVenv();
  const out = run(venvPython, ["-m", "piplicenses", "--from=mixed", "--format=json"], {
    capture: true,
    label: "pip-licenses --from=mixed --format=json",
  });
  return JSON.parse(out)
    .filter((p) => p.Name !== "videocut-backend")
    .map((p) => ({ name: p.Name, license: p.License }));
}

function nodeEntries() {
  const out = run(
    npmCommand(),
    ["exec", "--", "license-checker-rseidelsohn", "--json", "--excludePrivatePackages"],
    { cwd: FRONTEND, capture: true, label: "license-checker-rseidelsohn --json" },
  );
  return Object.entries(JSON.parse(out)).map(([id, info]) => ({
    name: id.slice(0, id.lastIndexOf("@")),
    license: info.licenses,
  }));
}

let failed = false;
for (const [ecosystem, load] of [
  ["python", pythonEntries],
  ["node", nodeEntries],
]) {
  const entries = load();
  const { violations, excepted } = evaluate(entries, policy, ecosystem);
  console.log(`${ecosystem}: ${entries.length} packages, ${excepted.length} covered by documented exceptions`);
  for (const v of violations) {
    failed = true;
    console.error(`  VIOLATION ${v.name}: ${v.license} (${v.problem})`);
  }
}
if (failed) {
  console.error("\nLicense policy check failed. See docs/LICENSING.md and scripts/license-policy.json.");
  process.exit(1);
}
console.log("License policy check passed.");
