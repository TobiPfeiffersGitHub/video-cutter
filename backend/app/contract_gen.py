"""Writes contract/openapi.json: `python -m app.contract_gen <output-path>`."""

from __future__ import annotations

import sys
from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.openapi import build_openapi, dump_openapi


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.contract_gen <output-path>", file=sys.stderr)
        return 2
    # Default settings keep the document independent of the caller's environment.
    document = build_openapi(create_app(Settings()))
    Path(argv[0]).write_text(dump_openapi(document), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
