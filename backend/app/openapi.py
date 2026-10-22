"""OpenAPI generation. Adds the EDL contract models to `components.schemas`.

FastAPI only lists models that a route uses. The EDL is a contract, not a route
payload yet, so it is merged in here instead of adding a placeholder endpoint.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI

from app.core.edl import Edl

_REF_TEMPLATE = "#/components/schemas/{model}"


def contract_schemas() -> dict[str, Any]:
    schema = Edl.model_json_schema(ref_template=_REF_TEMPLATE, mode="validation")
    definitions = schema.pop("$defs", {})
    return {"Edl": schema, **definitions}


def build_openapi(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema is None:
        from fastapi.openapi.utils import get_openapi

        document = get_openapi(
            title=app.title, version=app.version, routes=app.routes, description=app.description
        )
        schemas = document.setdefault("components", {}).setdefault("schemas", {})
        for name, schema in contract_schemas().items():
            schemas.setdefault(name, schema)
        document["components"]["schemas"] = dict(sorted(schemas.items()))
        app.openapi_schema = document
    return app.openapi_schema


def dump_openapi(document: dict[str, Any]) -> str:
    """Deterministic text form: sorted keys, 2-space indent, LF, trailing newline."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
