# Golden render cases

Language-neutral cases for the FFmpeg argument builder. Every `*.json` file holds:

| Key | Meaning |
| --- | --- |
| `description` | What the case protects. |
| `probe` | Normalized probe data: `duration_seconds`, `fps` (rational, the project CFR rate), stored `width`/`height`, clockwise `rotation` (0/90/180/270), `has_audio`, `vfr`, optional codec names. |
| `edl` | An EDL v1 document (validates against `../edl.schema.json`). |
| `options` | `format` (`mp4`/`wav`), `quality` (`high`/`fast`), `encoder`, `input_path`, `output_path`. |
| `expected_args` | The exact argument list, **without** the executable. |

Any backend implementation (Python today, possibly TypeScript later) must produce exactly
`expected_args` for each file. The Python check is `backend/tests/test_golden.py`.

These files were written once from the builder's output and then reviewed by hand against
the policies in `backend/app/core/render.py`. They are not regenerated automatically: a diff
here means the rendering behavior changed and needs a deliberate review. The real-FFmpeg
tests in `backend/tests/test_render_media.py` check that the same graphs actually produce the
right frames, durations and streams.
