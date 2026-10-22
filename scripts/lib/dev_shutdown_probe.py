"""Starts scripts/dev.mjs, interrupts it like a terminal would, and checks nothing is left.

Usage: dev_shutdown_probe.py NODE DEV_SCRIPT HOST BACKEND_PORT FRONTEND_PORT [SIGNAL]
Prints one JSON line. Exit code 0 only if dev.mjs exited and both ports were released.

SIGNAL is `interrupt` (default: Ctrl+Break on Windows, SIGINT elsewhere), or `hangup`
(SIGHUP, POSIX only). Python is used because Node cannot deliver a console control event
on Windows: `child.kill("SIGINT")` there terminates the process without running handlers.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time

WINDOWS = os.name == "nt"
STARTUP_SECONDS = 90
EXIT_SECONDS = 20
RELEASE_SECONDS = 10


def accepts(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_for(condition, seconds: float, proc: subprocess.Popen | None = None) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(0.25)
    return condition()


def kill_tree(proc: subprocess.Popen) -> None:
    if WINDOWS:
        subprocess.run(["taskkill", "/pid", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


def main() -> int:
    node, script, host, backend, frontend = sys.argv[1:6]
    kind = sys.argv[6] if len(sys.argv) > 6 else "interrupt"
    ports = [int(backend), int(frontend)]
    env = {**os.environ, "VIDEOCUT_HOST": host, "VIDEOCUT_PORT": backend}
    env["VIDEOCUT_FRONTEND_PORT"] = frontend
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0
    proc = subprocess.Popen(
        [node, script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    result: dict[str, object] = {"signal": kind}
    try:
        ready = wait_for(lambda: all(accepts(host, p) for p in ports), STARTUP_SECONDS, proc)
        result["started"] = ready
        if not ready:
            return 2
        if kind == "hangup":
            os.kill(proc.pid, signal.SIGHUP)
        elif WINDOWS:
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(proc.pid, signal.SIGINT)
        result["exited"] = wait_for(lambda: proc.poll() is not None, EXIT_SECONDS)
        result["ports_released"] = wait_for(
            lambda: not any(accepts(host, p) for p in ports), RELEASE_SECONDS
        )
        return 0 if result["exited"] and result["ports_released"] else 1
    finally:
        if proc.poll() is None:
            kill_tree(proc)
        print(json.dumps(result))


if __name__ == "__main__":
    raise SystemExit(main())
