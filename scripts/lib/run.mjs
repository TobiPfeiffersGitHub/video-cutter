import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(fileURLToPath(new URL("..", import.meta.url)), "..");
export const BACKEND = join(ROOT, "backend");
export const FRONTEND = join(ROOT, "frontend");
export const isWindows = process.platform === "win32";

export const venvPython = join(
  BACKEND,
  ".venv",
  isWindows ? "Scripts" : "bin",
  isWindows ? "python.exe" : "python",
);

export function npmCommand() {
  return isWindows ? "npm.cmd" : "npm";
}

// On Windows, .cmd shims cannot be spawned without a shell. Arguments passed here are
// fixed literals from our own scripts, never user input.
const needsShell = (command) => isWindows && command.toLowerCase().endsWith(".cmd");

// Runs a command with an argument list. Throws on failure.
export function run(command, args, options = {}) {
  const { capture = false, cwd = ROOT, env = {}, label } = options;
  console.log(`\n> ${label ?? [command, ...args].join(" ")}`);
  const result = spawnSync(command, args, {
    cwd,
    env: { ...process.env, ...env },
    stdio: capture ? ["ignore", "pipe", "inherit"] : "inherit",
    encoding: "utf8",
    maxBuffer: 256 * 1024 * 1024,
    shell: needsShell(command),
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`Command failed with exit code ${result.status}: ${command} ${args.join(" ")}`);
  }
  return result.stdout;
}

export { needsShell };

export function requireVenv() {
  if (!existsSync(venvPython)) {
    throw new Error("backend/.venv not found. Run `npm run setup` first.");
  }
}
