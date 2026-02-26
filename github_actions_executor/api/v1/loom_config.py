from __future__ import annotations

from typing import Any, ClassVar, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from github_actions_executor.api.base import Resource


class Credentials(BaseModel):
    model_config = ConfigDict(extra="allow")

    username: Optional[str] = None
    password: Optional[str] = None


class GlobalConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    vars: Dict[str, str] = Field(default_factory=dict)
    email: Optional[Credentials] = None


class LoomConfig(Resource):
    API_VERSION: ClassVar[str] = "v1"
    KIND: ClassVar[str] = "LoomConfig"

    global_config: GlobalConfig = Field(..., alias="global")

    def to_github_actions(self) -> Dict[str, Any]:
        if self.global_config.vars:
            return {"env": dict(self.global_config.vars)}
        return {}
