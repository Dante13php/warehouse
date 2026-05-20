"""Expand-string validation: the CloudSale RequestValidator ``expandable:`` port.

``validate_expand`` parses a user expand string (``resource[f1,f2],other``) and
whitelists it against a per-endpoint ``expandable`` spec. It mirrors CloudSale
``checkExpandable``.

Security contract: the returned resource/field names are validated against the
``expandable`` whitelist, so they are safe to use as response keys and as the
basis for which child storages to call. Names not in the whitelist are rejected
(never reflected back). The whitelist IS the trust boundary — callers MUST NOT
pass raw, un-whitelisted expand input into ``getattr(ioc, ...)``, dynamic class
resolution, or SQL identifiers. The empty-bracket ("all fields") path expands
ONLY to the spec's declared field names, never to arbitrary user input.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from fastapi import Query
from fastapi.exceptions import RequestValidationError

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")

_ENTRY_RE = re.compile(
    r"^(?P<name>[a-zA-Z0-9_]+)(?:\[(?P<fields>[a-zA-Z0-9_,]+)\])?$"
)


def validate_expand(
    raw: str | None,
    expandable: dict[str, list[str]],
) -> dict[str, list[str]]:
    if not raw:
        return {}

    parsed = _parse(raw)

    result: dict[str, list[str]] = {}
    for resource_name, requested_fields in parsed.items():
        if resource_name not in expandable:
            _raise_validation_error(
                raw, f"resource {resource_name!r} is not expandable"
            )
        allowed_fields = expandable[resource_name]
        if requested_fields is None:
            # Bracket-less resource expands to the spec's fields, never to
            # arbitrary user input.
            result[resource_name] = list(allowed_fields)
            continue
        for field_name in requested_fields:
            if field_name not in allowed_fields:
                _raise_validation_error(
                    raw,
                    f"field {field_name!r} is not expandable on "
                    f"resource {resource_name!r}",
                )
        result[resource_name] = list(requested_fields)

    return result


def _parse(raw: str) -> dict[str, list[str] | None]:
    result: dict[str, list[str] | None] = {}
    entries = raw.split(",")

    # Commas separate top-level entries but also appear inside []; re-join tokens
    # belonging to the same bracketed group via depth tracking.
    merged: list[str] = []
    buffer = ""
    depth = 0
    for entry in entries:
        depth += entry.count("[") - entry.count("]")
        if buffer:
            buffer += "," + entry
        else:
            buffer = entry
        if depth == 0:
            merged.append(buffer)
            buffer = ""
        elif depth < 0:
            _raise_validation_error(raw, "unbalanced brackets")
    if buffer:
        _raise_validation_error(raw, "unbalanced brackets")

    for token in merged:
        token = token.strip()
        if not token:
            continue
        match = _ENTRY_RE.match(token)
        if match is None:
            _raise_validation_error(raw, f"invalid expand token: {token!r}")
        resource_name = match.group("name")
        fields_str = match.group("fields")
        if fields_str is not None:
            fields = [f.strip() for f in fields_str.split(",") if f.strip()]
            for field_name in fields:
                if not _NAME_RE.match(field_name):
                    _raise_validation_error(
                        raw, f"invalid field name {field_name!r} in expand"
                    )
            result[resource_name] = fields
        else:
            result[resource_name] = None

    return result


def _raise_validation_error(raw: str | None, detail: str) -> None:
    from pydantic_core import InitErrorDetails, PydanticCustomError, ValidationError

    pydantic_error = PydanticCustomError(
        "expand_parse_error",
        "{detail}",
        {"detail": detail},
    )
    pydantic_ve = ValidationError.from_exception_data(
        title="expand",
        input_type="python",
        line_errors=[
            InitErrorDetails(
                type=pydantic_error,
                loc=("query", "expand"),
                input=raw,
            )
        ],
    )
    raise RequestValidationError(errors=pydantic_ve.errors())


def expand_dependency(
    expandable: dict[str, list[str]],
) -> Callable[..., dict[str, list[str]]]:
    def _dep(expand: str | None = Query(default=None)) -> dict[str, list[str]]:
        return validate_expand(expand, expandable)

    return _dep
