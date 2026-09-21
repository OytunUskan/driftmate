"""Shared state store for channel adapters.

Holds the short-ID -> context mapping used by notification channels to
correlate inline-keyboard callbacks with their originating action. This is an
adapter-level concern; the core package never imports it. V1 ships an
in-memory implementation whose data is lost on restart.
"""

from typing import Any, Optional, Protocol


class StateStore(Protocol):
    def set(self, key: str, value: Any) -> None: ...

    def get(self, key: str) -> Optional[Any]: ...

    def delete(self, key: str) -> None: ...


class InMemoryStateStore:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
