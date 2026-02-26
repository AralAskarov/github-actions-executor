from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class TypeMeta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api_version: str = Field(..., alias="apiVersion")
    kind: str


class ObjectMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)


class Resource(BaseModel, ABC):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    API_VERSION: ClassVar[str]
    KIND: ClassVar[str]

    api_version: str = Field(..., alias="apiVersion")
    kind: str

    @abstractmethod
    def to_github_actions(self) -> Dict[str, Any]:
        pass
