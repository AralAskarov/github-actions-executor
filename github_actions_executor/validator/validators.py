from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from github_actions_executor.api.base import Resource


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def success(cls) -> ValidationResult:
        return cls(valid=True)

    @classmethod
    def failure(cls, *errors: str) -> ValidationResult:
        return cls(valid=False, errors=list(errors))

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.valid = False

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)

    def merge(self, other: ValidationResult) -> ValidationResult:
        return ValidationResult(
            valid=self.valid and other.valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
        )


class Validator(ABC):
    @abstractmethod
    def validate(self, resource: Resource) -> ValidationResult:
        pass

    def handles(self, resource: Resource) -> bool:
        return True


class RequiredFieldsValidator(Validator):
    def validate(self, resource: Resource) -> ValidationResult:
        result = ValidationResult.success()
        if not resource.api_version:
            result.add_error("apiVersion is required")
        if not resource.kind:
            result.add_error("kind is required")
        return result


class JobReferenceValidator(Validator):
    def handles(self, resource: Resource) -> bool:
        return resource.kind == "LoomPipeline"

    def validate(self, resource: Resource) -> ValidationResult:
        from github_actions_executor.api.v1.loom_pipeline import LoomPipeline

        if not isinstance(resource, LoomPipeline):
            return ValidationResult.success()

        result = ValidationResult.success()
        defined_jobs = set(resource.pipeline.jobs.keys())

        for stage in resource.pipeline.stages:
            if stage.job not in defined_jobs:
                result.add_error(
                    f"Stage '{stage.name}' references undefined job '{stage.job}'. "
                    f"Available jobs: {', '.join(sorted(defined_jobs)) or 'none'}"
                )
        return result


class UniqueStageNamesValidator(Validator):
    def handles(self, resource: Resource) -> bool:
        return resource.kind == "LoomPipeline"

    def validate(self, resource: Resource) -> ValidationResult:
        from github_actions_executor.api.v1.loom_pipeline import LoomPipeline

        if not isinstance(resource, LoomPipeline):
            return ValidationResult.success()

        result = ValidationResult.success()
        seen: set[str] = set()
        for stage in resource.pipeline.stages:
            if stage.name in seen:
                result.add_warning(f"Duplicate stage name: '{stage.name}'")
            seen.add(stage.name)
        return result


class ValidatorChain:
    def __init__(self, validators: Optional[List[Validator]] = None) -> None:
        self._validators = validators or []

    def add(self, validator: Validator) -> ValidatorChain:
        self._validators.append(validator)
        return self

    def validate(self, resource: Resource) -> ValidationResult:
        result = ValidationResult.success()
        for v in self._validators:
            if v.handles(resource):
                result = result.merge(v.validate(resource))
        return result


def create_default_validator_chain() -> ValidatorChain:
    return ValidatorChain([
        RequiredFieldsValidator(),
        JobReferenceValidator(),
        UniqueStageNamesValidator(),
    ])
