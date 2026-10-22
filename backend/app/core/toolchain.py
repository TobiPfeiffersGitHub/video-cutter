"""FFmpeg/ffprobe discovery and encoder selection. No web-framework imports.

Discovery runs once at startup. Running a tool goes through an injectable `Runner`
so tests never need a real FFmpeg for the failure paths.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Software fallback order from the spec. Hardware encoders are opt-in only.
SOFTWARE_ENCODER_ORDER = ("libx264", "libopenh264", "libsvtav1")
HARDWARE_ENCODER_NAMES = ("h264_nvenc", "h264_qsv")
# Encoders reported by /health; later packages rely on these.
REPORTED_ENCODERS = (*SOFTWARE_ENCODER_ORDER, *HARDWARE_ENCODER_NAMES, "aac", "pcm_s16le")

INSTALL_HINT = (
    "Install FFmpeg: on Windows run `winget install Gyan.FFmpeg` and open a new terminal; "
    "on Debian/Ubuntu run `sudo apt install ffmpeg`. Alternatively set FFMPEG_PATH and "
    "FFPROBE_PATH to the executables."
)
_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str = ""


Runner = Callable[[Sequence[str]], RunResult]


def subprocess_runner(args: Sequence[str]) -> RunResult:
    """Run an argument list (never a shell string) with a timeout."""
    completed = subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    return RunResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class Problem:
    code: str
    message: str
    hint: str


@dataclass(frozen=True)
class ToolInfo:
    name: str
    path: str | None = None
    version: str | None = None

    @property
    def available(self) -> bool:
        return self.path is not None and self.version is not None


@dataclass(frozen=True)
class EncoderChoice:
    name: str
    hardware: bool
    fallback: bool
    note: str | None = None


@dataclass(frozen=True)
class Toolchain:
    ffmpeg: ToolInfo
    ffprobe: ToolInfo
    encoders: frozenset[str] = frozenset()
    selected_encoder: EncoderChoice | None = None
    problems: tuple[Problem, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.problems


def resolve_executable(
    name: str,
    configured: str,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[str | None, Problem | None]:
    """Resolve a tool: the configured path first, then PATH.

    An explicitly configured path that does not work is an error; it never silently
    falls back to PATH, since that would hide a typo.
    """
    env_var = f"{name.upper()}_PATH"
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_dir():
            for filename in (name, f"{name}.exe"):
                inside = candidate / filename
                if inside.is_file():
                    return str(inside), None
        elif candidate.is_file():
            return str(candidate), None
        return None, Problem(
            code=f"{name}_path_invalid",
            message=f"{env_var} is set to {configured!r}, but no {name} executable exists there.",
            hint=f"Fix or unset {env_var}. {INSTALL_HINT}",
        )
    found = which(name)
    if found:
        return found, None
    return None, Problem(
        code=f"{name}_not_found",
        message=f"{name} was not found on PATH and {env_var} is not set.",
        hint=INSTALL_HINT,
    )


_VERSION_RE = re.compile(r"^(?:ffmpeg|ffprobe) version (\S+)", re.IGNORECASE)


def parse_version(output: str) -> str | None:
    lines = output.strip().splitlines()
    match = _VERSION_RE.match(lines[0]) if lines else None
    return match.group(1) if match else None


_ENCODER_RE = re.compile(r"^\s([VAS][A-Z.]{5})\s+(\S+)\s")


def parse_encoders(output: str) -> frozenset[str]:
    """Names from `ffmpeg -encoders`; only lines after the `------` separator count."""
    names: set[str] = set()
    in_table = False
    for line in output.splitlines():
        if not in_table:
            in_table = line.strip().startswith("---")
            continue
        match = _ENCODER_RE.match(line)
        if match:
            names.add(match.group(2))
    return frozenset(names)


def select_encoder(available: frozenset[str], hardware_opt_in: str = "") -> EncoderChoice | None:
    """Pick the MP4 video encoder. Software unless hardware was explicitly requested.

    "Available" means compiled into FFmpeg, not that the GPU works; a failed hardware
    initialization is reported by the rendering step, not guessed here.
    """
    note = ""
    if hardware_opt_in:
        if hardware_opt_in in available:
            return EncoderChoice(hardware_opt_in, hardware=True, fallback=False)
        note = f"Hardware encoder {hardware_opt_in} was requested but is not available. "
    for index, name in enumerate(SOFTWARE_ENCODER_ORDER):
        if name in available:
            details = ""
            if index > 0:
                skipped = ", ".join(SOFTWARE_ENCODER_ORDER[:index])
                details = f"{skipped} unavailable; using {name}."
                if name == "libsvtav1":
                    details += " MP4 output will be AV1, which some players cannot decode."
            full = (note + details).strip() or None
            return EncoderChoice(name, hardware=False, fallback=index > 0 or bool(note), note=full)
    return None


def _probe_tool(name: str, path: str, runner: Runner) -> tuple[ToolInfo, Problem | None]:
    try:
        result = runner([path, "-version"])
    except (OSError, subprocess.SubprocessError) as error:
        return ToolInfo(name, path), Problem(
            code=f"{name}_not_runnable",
            message=f"{name} at {path!r} could not be run: {error}",
            hint=INSTALL_HINT,
        )
    version = parse_version(result.stdout) if result.returncode == 0 else None
    if version is None:
        return ToolInfo(name, path), Problem(
            code=f"{name}_bad_output",
            message=f"{name} at {path!r} did not report a version; it may not be FFmpeg.",
            hint=INSTALL_HINT,
        )
    return ToolInfo(name, path, version), None


def _read_encoders(ffmpeg_path: str, runner: Runner) -> frozenset[str]:
    try:
        result = runner([ffmpeg_path, "-hide_banner", "-encoders"])
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    return parse_encoders(result.stdout) if result.returncode == 0 else frozenset()


def discover_toolchain(
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    hardware_encoder: str = "",
    runner: Runner = subprocess_runner,
    which: Callable[[str], str | None] = shutil.which,
) -> Toolchain:
    problems: list[Problem] = []
    infos: dict[str, ToolInfo] = {}
    for name, configured in (("ffmpeg", ffmpeg_path), ("ffprobe", ffprobe_path)):
        path, problem = resolve_executable(name, configured, which)
        if path is None:
            infos[name] = ToolInfo(name)
        else:
            infos[name], problem = _probe_tool(name, path, runner)
        if problem:
            problems.append(problem)

    encoders: frozenset[str] = frozenset()
    selected: EncoderChoice | None = None
    ffmpeg = infos["ffmpeg"]
    if ffmpeg.path is not None and ffmpeg.available:
        encoders = _read_encoders(ffmpeg.path, runner)
        if not encoders:
            problems.append(
                Problem(
                    code="encoders_unreadable",
                    message="`ffmpeg -encoders` produced no recognizable encoder list.",
                    hint="Check that FFMPEG_PATH points to a complete FFmpeg build. "
                    + INSTALL_HINT,
                )
            )
        else:
            selected = select_encoder(encoders, hardware_encoder)
            if selected is None:
                problems.append(
                    Problem(
                        code="no_video_encoder",
                        message="FFmpeg has none of libx264, libopenh264 or libsvtav1.",
                        hint="Install a full FFmpeg build with libx264. " + INSTALL_HINT,
                    )
                )
    return Toolchain(
        ffmpeg=ffmpeg,
        ffprobe=infos["ffprobe"],
        encoders=encoders & frozenset(REPORTED_ENCODERS),
        selected_encoder=selected,
        problems=tuple(problems),
    )
