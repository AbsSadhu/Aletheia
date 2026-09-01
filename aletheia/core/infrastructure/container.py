from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any


@dataclass
class _FactoryRegistration:
    factory: Callable[[], Any]
    singleton: bool


class ServiceContainer:
    def __init__(self) -> None:
        self._singletons: dict[str, Any] = {}
        self._factories: dict[str, _FactoryRegistration] = {}
        self._lock = RLock()

    def register_singleton(self, name: str, instance: Any) -> None:
        with self._lock:
            self._singletons[name] = instance

    def register_factory(
        self,
        name: str,
        factory: Callable[[], Any],
        *,
        singleton: bool = True,
    ) -> None:
        with self._lock:
            self._factories[name] = _FactoryRegistration(factory=factory, singleton=singleton)

    def resolve(self, name: str) -> Any:
        with self._lock:
            if name in self._singletons:
                return self._singletons[name]

            registration = self._factories.get(name)
            if registration is None:
                raise KeyError(f"Service '{name}' is not registered.")

            instance = registration.factory()
            if registration.singleton:
                self._singletons[name] = instance
            return instance

    def has(self, name: str) -> bool:
        return name in self._singletons or name in self._factories
