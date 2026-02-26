from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from github_actions_executor.api.base import Resource


@dataclass
class GeneratorConfig:
    include_defaults: bool = True
    default_runner: str = "ubuntu-latest"
    trigger_branches: List[str] = field(default_factory=lambda: ["main"])
    default_flow_style: bool = False
    sort_keys: bool = False


class WorkflowGenerator:
    def __init__(self, config: Optional[GeneratorConfig] = None) -> None:
        self.config = config or GeneratorConfig()
        self._configs: List[Resource] = []
        self._pipelines: List[Resource] = []

    def add_resource(self, resource: Resource) -> None:
        if resource.kind == "LoomConfig":
            self._configs.append(resource)
        elif resource.kind == "LoomPipeline":
            self._pipelines.append(resource)

    def add_resources(self, resources: List[Resource]) -> None:
        for r in resources:
            self.add_resource(r)

    def generate(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        # Merge global env from configs
        global_env = self._merge_configs()

        # Merge pipelines
        for pipeline in self._pipelines:
            pipeline_output = pipeline.to_github_actions()

            # Use pipeline name if available
            if "name" in pipeline_output and "name" not in result:
                result["name"] = pipeline_output["name"]

            # Merge triggers
            if "on" in pipeline_output and "on" not in result:
                result["on"] = pipeline_output["on"]

            # Merge env
            if "env" in pipeline_output:
                global_env.update(pipeline_output["env"])

            # Merge jobs
            result.setdefault("jobs", {}).update(pipeline_output.get("jobs", {}))

        # Set defaults if not provided by pipelines
        if "on" not in result:
            result["on"] = {"push": {"branches": self.config.trigger_branches}}

        if global_env:
            result["env"] = global_env

        # Override runner if configured
        if self.config.default_runner != "ubuntu-latest":
            for job in result.get("jobs", {}).values():
                job["runs-on"] = self.config.default_runner

        return result

    def generate_yaml(self) -> str:
        return yaml.dump(
            self.generate(),
            default_flow_style=self.config.default_flow_style,
            sort_keys=self.config.sort_keys,
            allow_unicode=True,
        )

    def _merge_configs(self) -> Dict[str, str]:
        merged: Dict[str, str] = {}
        for cfg in self._configs:
            gh = cfg.to_github_actions()
            if "env" in gh:
                merged.update(gh["env"])
        return merged

    def clear(self) -> None:
        self._configs.clear()
        self._pipelines.clear()
