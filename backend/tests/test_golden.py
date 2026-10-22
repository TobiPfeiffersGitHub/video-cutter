"""Every contract/golden/*.json must produce exactly its expected FFmpeg argument list.

These files are language-neutral: a future non-Python backend must pass the same ones.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.core.edl import Edl
from app.core.probe import ProbeData
from app.core.render import RenderOptions, build_render_plan

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
GOLDEN_FILES = sorted((CONTRACT / "golden").glob("*.json"))
EDL_VALIDATOR = Draft202012Validator(json.loads((CONTRACT / "edl.schema.json").read_text("utf-8")))

# Scenarios the packages promise coverage for; a missing file is a regression.
REQUIRED_CASES = {
    "speed_extremes",
    "mixed_mute",
    "all_muted",
    "no_audio_mp4",
    "no_audio_wav",
    "rotated_crop",
    "vfr_source",
    "single_frame",
    "crop_even_rounding",
    "wav_cuts",
    "encoder_libopenh264",
    "encoder_libsvtav1",
    "encoder_h264_nvenc",
    "encoder_h264_qsv",
}


def test_all_required_golden_cases_exist() -> None:
    names = {path.stem for path in GOLDEN_FILES}
    assert REQUIRED_CASES <= names, f"missing golden cases: {sorted(REQUIRED_CASES - names)}"


@pytest.mark.parametrize("path", GOLDEN_FILES, ids=lambda p: p.stem)
def test_golden_case(path: Path) -> None:
    case: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    assert set(case) == {"description", "probe", "edl", "options", "expected_args"}
    assert not list(EDL_VALIDATOR.iter_errors(case["edl"])), "golden EDL violates the schema"

    plan = build_render_plan(
        ProbeData.model_validate(case["probe"]),
        Edl.model_validate(case["edl"]),
        RenderOptions.model_validate(case["options"]),
    )
    assert list(plan.args) == case["expected_args"]
