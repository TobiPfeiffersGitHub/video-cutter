// Starts the real `npm run dev` script on free ports, interrupts it the way a terminal does,
// and checks it exited and released both ports (no orphaned uvicorn/Vite). The signal is
// delivered by scripts/lib/dev_shutdown_probe.py because Node cannot send a console control
// event on Windows. Needs `npm run setup` to have been run, like the rest of `npm test`.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import net from "node:net";
import { join } from "node:path";
import { test } from "node:test";
import { ROOT, isWindows, requireVenv, venvPython } from "./lib/run.mjs";

const HOST = "127.0.0.1";

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, HOST, () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function probe(kind) {
  requireVenv();
  const [backend, frontend] = [await freePort(), await freePort()];
  const result = spawnSync(
    venvPython,
    [
      join(ROOT, "scripts", "lib", "dev_shutdown_probe.py"),
      process.execPath,
      join(ROOT, "scripts", "dev.mjs"),
      HOST,
      String(backend),
      String(frontend),
      kind,
    ],
    { encoding: "utf8", timeout: 150_000 },
  );
  const line = result.stdout.trim().split("\n").pop() ?? "";
  let report;
  try {
    report = JSON.parse(line);
  } catch {
    assert.fail(`probe printed no JSON (status ${result.status}): ${result.stdout}${result.stderr}`);
  }
  return { report, status: result.status };
}

test("dev stops both servers and frees both ports on interrupt", async () => {
  const { report, status } = await probe("interrupt");
  assert.deepEqual(report, { signal: "interrupt", started: true, exited: true, ports_released: true });
  assert.equal(status, 0);
});

test("dev stops both servers and frees both ports on hangup", { skip: isWindows }, async () => {
  const { report, status } = await probe("hangup");
  assert.deepEqual(report, { signal: "hangup", started: true, exited: true, ports_released: true });
  assert.equal(status, 0);
});
