"""Generate test media with FFmpeg lavfi sources only (testsrc2 + sine). Nothing is committed.

Every fixture burns the frame number into the picture two ways:

* a 16-block black/white barcode in the top-left 256x16 pixels (bit k = block k, least
  significant bit first). Tests read it back with `read_frame_numbers`, so a cut is
  checked by content, not just duration. It needs no font, so it works everywhere.
* a human-readable number via drawtext, only when a font file is found on this machine.

Run `npm run fixtures` (or `python -m tests.fixtures_gen` from backend/) to write them to
backend/tests/.generated/. The fixtures are:

  normal    640x360, 30000/1001 fps, ~6 s, H.264 video + AAC sine audio
  no_audio  the same picture without an audio stream
  rotated   `normal` with a 90 degree display-matrix rotation (stored 640x360, shown 360x640)
  vfr       variable frame rate: 30 fps for 3 s, then 15 fps for 6 s (9 s, with audio)
  vfr_fast  60 fps for 1 s, then 20 fps for 3 s: declared rate 60, average 30 (4 s, with audio)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.toolchain import resolve_executable

SIZE = "640x360"
RATE = "30000/1001"
SECONDS = 6
BARCODE_BITS = 16
BLOCK = 16
FIXTURE_NAMES = ("normal", "no_audio", "rotated", "vfr", "vfr_fast")
DEFAULT_OUT = Path(__file__).resolve().parent / ".generated"

_FONT_CANDIDATES = (
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)

_BARCODE_FILTER = (
    "geq="
    f"lum='if(lt(Y,{BLOCK})*lt(X,{BARCODE_BITS * BLOCK}),"
    f"255*mod(floor(N/pow(2,floor(X/{BLOCK}))),2),lum(X,Y))':"
    "cb='cb(X,Y)':cr='cr(X,Y)'"
)


class FixtureError(RuntimeError):
    pass


def find_font() -> str | None:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def _drawtext_filter(font: str) -> str:
    escaped = font.replace("\\", "/").replace(":", "\\:")
    return (
        f"drawtext=fontfile='{escaped}':text='%{{n}}':x=(w-tw)/2:y=h-th-12:"
        "fontsize=48:fontcolor=white:box=1:boxcolor=black@0.6"
    )


def _video_graph(source: str, extra: str = "") -> str:
    filters = [source, _BARCODE_FILTER]
    font = find_font()
    if font is not None:
        filters.append(_drawtext_filter(font))
    if extra:
        filters.append(extra)
    filters.append("format=yuv420p")
    return ",".join(filters)


def _run(ffmpeg: str, args: Sequence[str]) -> None:
    command = [ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-y", *args]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if result.returncode != 0:
        raise FixtureError(f"ffmpeg failed ({result.returncode}): {result.stderr.strip()[-800:]}")


_VIDEO_ENCODE = ("-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-g", "15")
_AUDIO_ENCODE = ("-c:a", "aac", "-b:a", "128k")


def _sine(seconds: int) -> list[str]:
    return ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}"]


def generate_fixtures(ffmpeg: str, out_dir: Path) -> dict[str, Path]:
    """Write all fixtures into `out_dir` and return their paths by name."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: out_dir / f"{name}.mp4" for name in FIXTURE_NAMES}
    picture = f"testsrc2=size={SIZE}:rate={RATE}:duration={SECONDS}"

    _run(
        ffmpeg,
        [
            "-f", "lavfi", "-i", _video_graph(picture),
            *_sine(SECONDS),
            *_VIDEO_ENCODE, *_AUDIO_ENCODE, "-shortest",
            str(paths["normal"]),
        ],
    )  # fmt: skip
    _run(
        ffmpeg,
        ["-f", "lavfi", "-i", _video_graph(picture), *_VIDEO_ENCODE, "-an", str(paths["no_audio"])],
    )
    # -display_rotation is counter-clockwise and applies to the next input; -c copy keeps
    # the encoded frames and writes the rotation as a display matrix.
    _run(
        ffmpeg,
        [
            "-display_rotation", "90", "-i", str(paths["normal"]),
            "-c", "copy", str(paths["rotated"]),
        ],
    )  # fmt: skip
    vfr_pts = "setpts='if(lt(N,90),N/30,3+(N-90)/15)/TB'"
    _run(
        ffmpeg,
        [
            "-f", "lavfi",
            "-i", _video_graph(f"testsrc2=size={SIZE}:rate=30:duration=6", vfr_pts),
            *_sine(9),
            *_VIDEO_ENCODE, *_AUDIO_ENCODE, "-fps_mode", "passthrough", "-shortest",
            str(paths["vfr"]),
        ],
    )  # fmt: skip
    vfr_fast_pts = "setpts='if(lt(N,60),N/60,1+(N-60)/20)/TB'"
    _run(
        ffmpeg,
        [
            "-f", "lavfi",
            "-i", _video_graph(f"testsrc2=size={SIZE}:rate=60:duration=2", vfr_fast_pts),
            *_sine(4),
            *_VIDEO_ENCODE, *_AUDIO_ENCODE, "-fps_mode", "passthrough", "-shortest",
            str(paths["vfr_fast"]),
        ],
    )  # fmt: skip
    return paths


_READ_FILTER = (
    f"crop={BARCODE_BITS * BLOCK}:{BLOCK}:0:0,scale={BARCODE_BITS}:1:flags=neighbor,format=gray"
)


def read_frame_numbers(ffmpeg: str, media: Path, undo: str = "") -> list[int]:
    """Decode a fixture-derived video and return each frame's burned-in barcode number.

    `undo` is an optional filter that restores the barcode to the top-left, for outputs where
    rotation was baked into the pixels (the rotated fixture needs `transpose=clock`).
    """
    command = [
        ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-i", str(media),
        "-vf", f"{undo},{_READ_FILTER}" if undo else _READ_FILTER,
        "-fps_mode", "passthrough", "-f", "rawvideo", "-",
    ]  # fmt: skip
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        raise FixtureError(result.stderr.decode("utf-8", "replace").strip()[-800:])
    data = result.stdout
    if len(data) % BARCODE_BITS:
        raise FixtureError("decoded barcode data is not a whole number of frames")
    numbers = []
    for offset in range(0, len(data), BARCODE_BITS):
        row = data[offset : offset + BARCODE_BITS]
        numbers.append(sum(1 << bit for bit, value in enumerate(row) if value > 127))
    return numbers


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument(
        "--ffmpeg", default="", help="FFmpeg path (default: FFMPEG_PATH, then PATH)"
    )
    options = parser.parse_args(argv)

    configured = options.ffmpeg or os.environ.get("FFMPEG_PATH", "").strip()
    ffmpeg, problem = resolve_executable("ffmpeg", configured)
    if ffmpeg is None:
        print(
            f"{problem.message}\n{problem.hint}" if problem else "ffmpeg not found", file=sys.stderr
        )
        return 1
    try:
        paths = generate_fixtures(ffmpeg, options.out)
    except FixtureError as error:
        print(error, file=sys.stderr)
        return 1
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
