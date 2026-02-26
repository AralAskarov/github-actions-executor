from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from github_actions_executor.api.base import Resource

STATUS_MAP = {
    "SUCCESS": "success()",
    "FAILURE": "failure()",
    "ALWAYS": "always()",
}

_CONDITION_RE = re.compile(r"^(\w+)\s*(==|!=)\s*(.+)$")


def _build_condition(condition: str, statuses: str | None = None) -> str:
    m = _CONDITION_RE.match(condition.strip())
    if not m:
        raise ValueError(f"Invalid condition: {condition}")

    var, op, val = m.group(1), m.group(2), m.group(3).strip()
    parts = [f"${{{{ env.{var} }}}} {op} '{val}'"]

    if statuses:
        func = STATUS_MAP.get(statuses.upper(), "success()")
        parts.append(func)

    return " && ".join(parts)


class JobInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    params: Dict[str, str] = Field(default_factory=dict)
    secure_params: Dict[str, str] = Field(default_factory=dict)


class JobOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    files: Dict[str, str] = Field(default_factory=dict)


class JobWhen(BaseModel):
    model_config = ConfigDict(extra="allow")

    statuses: Optional[str] = None
    condition: Optional[str] = None


class Job(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    command: str
    variables: Dict[str, str] = Field(default_factory=dict)
    services: List[str] = Field(default_factory=list)
    input: Optional[JobInput] = None
    output: Optional[JobOutput] = None
    when: Optional[JobWhen] = None

    def to_github_job(self, job_name: str, needs: list[str] | None = None) -> Dict[str, Any]:
        job_def: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "container": {"image": self.path},
        }

        if needs:
            job_def["needs"] = needs

        # Build env from variables + input params
        env: Dict[str, str] = {}
        if self.variables:
            env.update(self.variables)
        if self.input:
            env.update({
                k.replace(".", "_").upper(): v
                for k, v in self.input.params.items()
            })
            env.update({
                k.replace(".", "_").upper(): v
                for k, v in self.input.secure_params.items()
            })
        if env:
            job_def["env"] = env

        # Build steps
        steps: List[Dict[str, Any]] = [
            {"uses": "actions/checkout@v4"},
            {"name": f"Run {self.command}", "run": f"loom {self.command}"},
        ]

        # Upload artifacts if output files defined
        if self.output and self.output.files:
            paths = list(self.output.files.values())
            steps.append({
                "name": "Upload artifacts",
                "if": "always()",
                "uses": "actions/upload-artifact@v4",
                "with": {
                    "name": f"{job_name}-artifacts",
                    "path": "\n".join(paths),
                },
            })

        job_def["steps"] = steps

        # Conditional execution
        if self.when:
            if self.when.condition:
                job_def["if"] = _build_condition(self.when.condition, self.when.statuses)
            elif self.when.statuses:
                func = STATUS_MAP.get(self.when.statuses.upper(), "success()")
                job_def["if"] = func

        return job_def


class Stage(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    job: str


class PipelineSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    name: Optional[str] = None
    vars: Dict[str, str] = Field(default_factory=dict)
    stages: List[Stage] = Field(default_factory=list)
    jobs: Dict[str, Job] = Field(default_factory=dict)


class LoomPipeline(Resource):
    API_VERSION: ClassVar[str] = "v1"
    KIND: ClassVar[str] = "LoomPipeline"

    pipeline: PipelineSpec

    def to_github_actions(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        # Pipeline name
        if self.pipeline.name:
            result["name"] = self.pipeline.name

        # Default trigger
        result["on"] = {"push": {"branches": ["main"]}}

        # Global env from pipeline vars
        if self.pipeline.vars:
            result["env"] = dict(self.pipeline.vars)

        # Build jobs with needs chain from stage ordering
        jobs: Dict[str, Any] = {}
        stage_job_map = {s.job: s.name for s in self.pipeline.stages}
        ordered_jobs = [s.job for s in self.pipeline.stages]

        for i, job_name in enumerate(ordered_jobs):
            job = self.pipeline.jobs.get(job_name)
            if not job:
                continue
            needs = [ordered_jobs[i - 1]] if i > 0 else None
            jobs[job_name] = job.to_github_job(job_name, needs=needs)

        # Add any jobs not referenced in stages
        for job_name, job in self.pipeline.jobs.items():
            if job_name not in jobs:
                jobs[job_name] = job.to_github_job(job_name)

        if jobs:
            result["jobs"] = jobs

        return result
