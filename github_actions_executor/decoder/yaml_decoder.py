from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Union

import yaml
from pydantic import ValidationError

from github_actions_executor.api.base import Resource
from github_actions_executor.scheme import Scheme


class DecodeError(Exception):
    pass


class Decoder:
    def __init__(self, scheme: Scheme) -> None:
        self._scheme = scheme

    def decode(self, data: Union[str, bytes, Dict[str, Any]]) -> Resource:
        if isinstance(data, (str, bytes)):
            try:
                parsed = yaml.safe_load(data)
            except yaml.YAMLError as e:
                raise DecodeError(f"YAML parsing failed: {e}") from e
        else:
            parsed = data

        if not isinstance(parsed, dict):
            raise DecodeError(f"Expected dict, got {type(parsed).__name__}")

        return self._decode_dict(parsed)

    def decode_all(self, data: Union[str, bytes]) -> List[Resource]:
        return [self._decode_dict(doc) for doc in self._iter_docs(data) if doc is not None]

    def _iter_docs(self, data: Union[str, bytes]) -> Iterator[Optional[Dict[str, Any]]]:
        try:
            yield from yaml.safe_load_all(data)
        except yaml.YAMLError as e:
            raise DecodeError(f"YAML parsing failed: {e}") from e

    def _decode_dict(self, data: Dict[str, Any]) -> Resource:
        api_version = data.get("apiVersion")
        kind = data.get("kind")

        if not api_version:
            raise DecodeError("Missing required field: apiVersion")
        if not kind:
            raise DecodeError("Missing required field: kind")

        cls = self._scheme.lookup(api_version, kind)
        if cls is None:
            raise DecodeError(f"Unknown type: apiVersion={api_version}, kind={kind}")

        try:
            return cls.model_validate(data)
        except ValidationError as e:
            msgs = "; ".join(f"{err['loc']}: {err['msg']}" for err in e.errors())
            raise DecodeError(f"Validation failed for {api_version}/{kind}: {msgs}") from e

    def can_decode(self, api_version: str, kind: str) -> bool:
        return self._scheme.is_registered(api_version, kind)


def create_decoder() -> Decoder:
    from github_actions_executor.scheme import scheme
    return Decoder(scheme)
