from __future__ import annotations

from typing import Any, Generic, Iterator, TypeVar

from app.data.abstract_data import AbstractData

T = TypeVar("T", bound=AbstractData)


class DataCollection(Generic[T]):
    def __init__(self, items: list[T] | None = None) -> None:
        self._items: list[T] = list(items) if items is not None else []

    def add(self, item: T) -> None:
        self._items.append(item)

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> T:
        return self._items[index]

    def __bool__(self) -> bool:
        return bool(self._items)

    def expand_property(
        self,
        expanded_property: str,
        group_key_property: str,
        grouped_values: dict[Any, list[Any]],
    ) -> None:
        for item in self._items:
            key = getattr(item, group_key_property)
            setattr(item, expanded_property, grouped_values.get(key, []))

    def extract_property_values(self, property_name: str) -> list[Any]:
        return [getattr(item, property_name) for item in self._items]

    def extract_property_values_as_keys(self, property_name: str) -> dict[Any, T]:
        # Last item wins on key collision.
        return {getattr(item, property_name): item for item in self._items}

    def group_by_property(self, property_name: str) -> dict[Any, list[T]]:
        grouped: dict[Any, list[T]] = {}
        for item in self._items:
            key = getattr(item, property_name)
            grouped.setdefault(key, []).append(item)
        return grouped

    def to_list(self) -> list[T]:
        return list(self._items)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._items]
