// Starts the backend (uvicorn --reload) and the frontend (Vite) together and stops both on exit.
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import net from "node:net";
import { join } from "node:path";
import { BACKEND, FRONTEND, isWindows, requireVenv, venvPython } from "./lib/run.mjs";

const host = process.env.VIDEOCUT_HOST ?? "127.0.0.1";
const backendPort = Number(process.env.VIDEOCUT_PORT ?? "8000");
const frontendPort = Number(process.env.VIDEOCUT_FRONTEND_PORT ?? "5173");

function portIsFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => server.close(() => resolve(true)));
    server.listen(port, host);
  });
}

requireVenv();
const viteBin = join(FRONTEND, "node_modules", "vite", "bin", "vite.js");
if (!existsSync(viteBin)) {
  console.error("Frontend dependencies missing. Run `npm run setup` first.");
  process.exit(1);
}

for (const [name, port, variable] of [
  ["backend", backendPort, "VIDEOCUT_PORT"],
  ["frontend", frontendPort, "VIDEOCUT_FRONTEND_PORT"],
]) {
  if (!(await portIsFree(port))) {
    console.error(
      `Port ${port} (${name}) is already in use. Stop the other process or set ${variable} to a free port.`,
    );
    process.exit(1);
  }
}

const children = [];
let shuttingDown = false;

function killTree(child) {
  if (child.exitCode !== null || child.pid === undefined) return;
  if (isWindows) {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      child.kill("SIGTERM");
    }
  }
}

function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  children.forEach(killTree);
  setTimeout(() => process.exit(code), 200);
}

function start(name, command, args, cwd) {
  const child = spawn(command, args, { cwd, stdio: "inherit", detached: !isWindows });
  children.push(child);
  child.on("exit", (code) => {
    if (!shuttingDown) {
      console.error(`\n${name} exited (code ${code}); stopping the other process.`);
      shutdown(code ?? 1);
    }
  });
  child.on("error", (error) => {
    console.error(`Failed to start ${name}: ${error.message}`);
    shutdown(1);
  });
}

console.log(`Backend:  http://${host}:${backendPort}/docs`);
console.log(`Frontend: http://${host}:${frontendPort}/  (proxies /api to the backend)`);

start(
  "backend",
  venvPython,
  ["-m", "uvicorn", "app.main:app", "--reload", "--host", host, "--port", String(backendPort)],
  BACKEND,
);
start("frontend", process.execPath, [viteBin, "--host", host], FRONTEND);

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
