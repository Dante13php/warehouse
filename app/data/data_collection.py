"""DataCollection: a generic typed wrapper around ``list[T]``.

Ports the CloudSale ``AbstractDataCollection`` utilities to Python: attach
grouped child values onto each parent item (``expand_property``), extract a
property across items, index items by a property, and group items by a property.

Usage (parent -> children single-level expand)::

    parents = DataCollection(parent_storage_rows)
    children = DataCollection(child_storage_rows)
    grouped = children.group_by_property("parent_id")  # {parent_id: [child, ...]}
    parents.expand_property("children", "id", grouped)
    # each parent.children is now its list of children (or [] if none)
"""

from __future__ import annotations

from typing import Any, Generic, Iterator, TypeVar

from app.data.abstract_data import AbstractData

T = TypeVar("T", bound=AbstractData)


class DataCollection(Generic[T]):
    """Typed wrapper around ``list[T]`` (``T`` bound to ``AbstractData``)."""

    def __init__(self, items: list[T] | None = None) -> None:
        self._items: list[T] = list(items) if items is not None else []

    # --- construction / mutation ------------------------------------------

    def add(self, item: T) -> None:
        self._items.append(item)

    # --- sequence protocol -------------------------------------------------

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> T:
        return self._items[index]

    def __bool__(self) -> bool:
        return bool(self._items)

    # --- CloudSale AbstractDataCollection utilities -----------------------

    def expand_property(
        self,
        expanded_property: str,
        group_key_property: str,
        grouped_values: dict[Any, list[Any]],
    ) -> None:
        """Attach grouped child values onto each item.

        For each item, set ``item.<expanded_property> =
        grouped_values.get(item.<group_key_property>, [])``. Direct port of
        CloudSale ``expandProperty``: a missing key yields an empty list.

        ``expanded_property`` must be a field declared ``expanded`` in the item's
        ``FIELDS``; ``AbstractData``'s ``__setattr__`` guard rejects a misnamed
        target.
        """
        for item in self._items:
            key = getattr(item, group_key_property)
            setattr(item, expanded_property, grouped_values.get(key, []))

    def extract_property_values(self, property_name: str) -> list[Any]:
        """Return ``[item.<property_name> for item in items]``."""
        return [getattr(item, property_name) for item in self._items]

    def extract_property_values_as_keys(self, property_name: str) -> dict[Any, T]:
        """Return ``{item.<property_name>: item}`` (last item wins on collision)."""
        return {getattr(item, property_name): item for item in self._items}

    def group_by_property(self, property_name: str) -> dict[Any, list[T]]:
        """Group items into lists keyed by ``item.<property_name>``."""
        grouped: dict[Any, list[T]] = {}
        for item in self._items:
            key = getattr(item, property_name)
            grouped.setdefault(key, []).append(item)
        return grouped

    # --- serialization -----------------------------------------------------

    def to_list(self) -> list[T]:
        """Return a shallow copy of the underlying item list."""
        return list(self._items)

    def to_dicts(self) -> list[dict[str, Any]]:
        """Return ``[item.to_dict() for item in items]`` for response shaping."""
        return [item.to_dict() for item in self._items]
