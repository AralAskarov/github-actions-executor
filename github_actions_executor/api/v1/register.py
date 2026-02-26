from github_actions_executor.scheme import scheme
from .loom_config import LoomConfig
from .loom_pipeline import LoomPipeline


def register_v1_types() -> None:
    scheme.register("v1", "LoomConfig", LoomConfig)
    scheme.register("v1", "LoomPipeline", LoomPipeline)


register_v1_types()
