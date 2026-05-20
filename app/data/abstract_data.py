"""AbstractData base for dataclass Data classes.

Ports the CloudSale ``AbstractData`` ``FIELDS`` / ``expanded`` semantics onto
Python dataclasses. A subclass declares a ``FIELDS`` map (field name -> type
token). ``FIELDS`` is the authoritative field whitelist and the source for type
coercion. The ``expanded`` token marks list-valued nested child fields that are
NOT read from the DB row; they are populated later by
``DataCollection.expand_property``.

Field storage remains the dataclass mechanism. The CloudSale magic
``__get``/``__set`` whitelist is reproduced as a ``__setattr__`` guard that
rejects writes to names not in ``FIELDS`` (post-construction dynamic sets such
as ``expand_property``). Dataclass ``__init__`` already restricts construction
to declared fields.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

# Type tokens used in FIELDS. Mirror CloudSale fixType tokens plus "expanded".
INT = "int"
FLOAT = "float"
STRING = "string"
BOOL = "bool"
DATETIME = "datetime"
EXPANDED = "expanded"

# Typing alias for annotating an expanded (list-valued nested child) field.
ExpandedField = list[Any]


class AbstractData:
    """Base mixin for ``@dataclass`` Data classes.

    Subclasses MUST set ``FIELDS`` and declare matching dataclass fields. Example::

        @dataclass
        class RecipeData(AbstractData):
            FIELDS = {"id": "int", "name": "string", "products": "expanded"}
            id: int
            name: str
            products: list[Any] = field(default_factory=list)
    """

    FIELDS: ClassVar[dict[str, str]] = {}

    @classmethod
    def from_row(cls, row: Any) -> "AbstractData":
        """Build an instance from a DB row by mapping ``FIELDS`` keys.

        ``expanded`` fields are NOT read from the row; they default to an empty
        list and are populated later by ``DataCollection.expand_property``. Each
        non-expanded field value is passed through ``fix_type``.

        Subclasses may override for custom mapping.
        """
        values: dict[str, Any] = {}
        for name, type_token in cls.FIELDS.items():
            if type_token == EXPANDED:
                values[name] = []
                continue
            raw_value = cls._read_row_value(row, name)
            values[name] = cls.fix_type(type_token, raw_value)
        return cls(**values)

    @staticmethod
    def _read_row_value(row: Any, name: str) -> Any:
        """Read a column from a row that may be a mapping or an attribute object."""
        if isinstance(row, dict):
            return row.get(name)
        return getattr(row, name, None)

    @staticmethod
    def fix_type(type_token: str, value: Any) -> Any:
        """Coerce ``value`` according to ``type_token``.

        Mirrors CloudSale ``fixType``. ``None`` passes through unchanged for all
        tokens. ``expanded`` returns the value as-is (list passthrough). An
        unknown token returns the value unchanged.
        """
        if value is None:
            return None
        if type_token == INT:
            return int(value)
        if type_token == FLOAT:
            return float(value)
        if type_token == STRING:
            return str(value)
        if type_token == BOOL:
            return bool(value)
        if type_token == DATETIME:
            return AbstractData._parse_datetime(value)
        # EXPANDED and any unknown token: passthrough.
        return value

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        """Parse a datetime value into a timezone-aware UTC ``datetime``."""
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def __setattr__(self, name: str, value: Any) -> None:
        """Reject writes to names not declared in ``FIELDS``.

        Leading-underscore/dunder names are always allowed (internal/dataclass
        machinery). All other names must appear in ``FIELDS``. Dataclass
        ``__init__`` only sets declared fields, so construction is unaffected;
        the guard covers post-construction dynamic sets (e.g. ``expand_property``).
        """
        if not name.startswith("_") and name not in type(self).FIELDS:
            raise AttributeError(
                f"{type(self).__name__} has no field {name!r} "
                f"(allowed fields: {sorted(type(self).FIELDS)})"
            )
        super().__setattr__(name, value)

    def to_dict(self) -> dict[str, Any]:
        """Return the field map for response shaping / storage values.

        Honors ``FIELDS`` declaration order. Includes ``expanded`` fields as
        their current list value.
        """
        return {name: getattr(self, name) for name in type(self).FIELDS}
