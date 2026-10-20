# Licensing notes

**This is not legal advice.** It records design decisions and the obligations we
are aware of. Consult a lawyer before distributing anything.

## Application code

The videocut source code is MIT licensed (see `LICENSE`). All dependencies must
be permissive (MIT, BSD, Apache-2.0, ISC, PostgreSQL or similar). AGPL, SSPL,
BUSL, source-available and commercial-only components are not allowed. The
policy is checked automatically; see [DEPENDENCIES.md](DEPENDENCIES.md).

## FFmpeg

FFmpeg is **not distributed with videocut** and is not linked into it. It is an
external executable that the user installs, located through `FFMPEG_PATH` /
`FFPROBE_PATH` or `PATH`, and run as a separate process.

- FFmpeg itself is LGPL-2.1+ or GPL-2+ depending on how it was built.
  Builds that include `libx264` (the default MP4 encoder) are **GPL**.
- For local use, the user obtains FFmpeg under its own license terms and
  videocut only invokes it.
- **Future container images:** publishing a Docker image that contains an FFmpeg
  build means *distributing* that build. For a GPL build this brings GPL
  obligations (license text, offer of corresponding source for FFmpeg and its
  libraries). Review them before any image is published. CI provisioning FFmpeg
  on a runner for tests is not distribution.

## H.264 and other codecs

H.264 (and AAC) are patent-encumbered formats. Software licenses such as GPL do
not grant patent rights. Encoding and distributing H.264 may require patent
licenses in some jurisdictions or commercial settings. videocut does not
provide or assume any such license.

## Content and trademarks

- Only files uploaded by the user are processed; no DRM circumvention.
- Test media is generated with FFmpeg `lavfi` sources; no third-party media is committed.
- The UI is original. Third-party trademarks are mentioned only factually
  (for example "FFmpeg").
