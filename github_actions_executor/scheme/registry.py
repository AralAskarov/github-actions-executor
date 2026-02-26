from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Type

from github_actions_executor.api.base import Resource


@dataclass(frozen=True)
class VersionKind:
    version: str
    kind: str

    def __str__(self) -> str:
        return f"{self.version}/{self.kind}"


class Scheme:
    def __init__(self) -> None:
        self._registry: Dict[VersionKind, Type[Resource]] = {}

    def register(self, api_version: str, kind: str, cls: Type[Resource]) -> None:
        self._registry[VersionKind(api_version, kind)] = cls

    def lookup(self, api_version: str, kind: str) -> Optional[Type[Resource]]:
        return self._registry.get(VersionKind(api_version, kind))

    def is_registered(self, api_version: str, kind: str) -> bool:
        return self.lookup(api_version, kind) is not None

    def known_types(self) -> list[VersionKind]:
        return list(self._registry.keys())


scheme = Scheme()
