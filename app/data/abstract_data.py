from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

INT = "int"
FLOAT = "float"
STRING = "string"
BOOL = "bool"
DATETIME = "datetime"
EXPANDED = "expanded"

ExpandedField = list[Any]


class AbstractData:
    FIELDS: ClassVar[dict[str, str]] = {}

    @classmethod
    def from_row(cls, row: Any) -> "AbstractData":
        values: dict[str, Any] = {}
        for name, type_token in cls.FIELDS.items():
            if type_token == EXPANDED:
                # expanded fields are not columns; they are filled later by
                # DataCollection.expand_property.
                values[name] = []
                continue
            raw_value = cls._read_row_value(row, name)
            values[name] = cls.fix_type(type_token, raw_value)
        return cls(**values)

    @staticmethod
    def _read_row_value(row: Any, name: str) -> Any:
        if isinstance(row, dict):
            return row.get(name)
        return getattr(row, name, None)

    @staticmethod
    def fix_type(type_token: str, value: Any) -> Any:
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
        return value

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
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
        # Guards post-construction dynamic sets (e.g. expand_property) against
        # typo'd field names; underscore/dunder names bypass it for dataclass
        # and internal machinery.
        if not name.startswith("_") and name not in type(self).FIELDS:
            raise AttributeError(
                f"{type(self).__name__} has no field {name!r} "
                f"(allowed fields: {sorted(type(self).FIELDS)})"
            )
        super().__setattr__(name, value)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in type(self).FIELDS}
