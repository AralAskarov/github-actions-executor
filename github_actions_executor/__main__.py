from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import click

from github_actions_executor.api import v1 as _  # noqa: F401
from github_actions_executor.decoder import DecodeError, create_decoder
from github_actions_executor.fetcher import parse_sources, fetch_all
from github_actions_executor.generator import WorkflowGenerator, GeneratorConfig
from github_actions_executor.validator import create_default_validator_chain

logger = logging.getLogger("github_actions_executor")


def parse_pipeline_vars(raw: str | None) -> Dict[str, str]:
    """Parse 'KEY1=val1; KEY2=val2' into a dict. Tolerates extra whitespace."""
    result: Dict[str, str] = {}
    if not raw or not raw.strip():
        return result
    for pair in raw.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        result[key.strip()] = value.strip()
    return result


def load_yaml_files(paths: List[str]) -> str:
    contents = []
    for path in paths:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        contents.append(file_path.read_text(encoding="utf-8"))
    return "\n---\n".join(contents)


def _validate_resources(resources, force: bool = False) -> bool:
    validator_chain = create_default_validator_chain()
    has_errors = False

    for resource in resources:
        result = validator_chain.validate(resource)

        for warning in result.warnings:
            logger.warning(warning)

        if not result.valid:
            for error in result.errors:
                logger.error(error)
            has_errors = True

    if has_errors and not force:
        logger.error("Validation failed. Use --force to generate anyway.")
        return False

    return True


def _generate_output(resources, default_runner: Optional[str] = None, extra_vars: Optional[Dict[str, str]] = None) -> str:
    config = GeneratorConfig(
        default_runner=default_runner or "ubuntu-latest",
    )
    generator = WorkflowGenerator(config)
    generator.add_resources(resources)
    if extra_vars:
        generator.add_extra_vars(extra_vars)
    return generator.generate_yaml()


def _write_output(output: str, path: Optional[str]) -> None:
    if path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
        logger.info(f"Generated: {path}")
    else:
        sys.stdout.write(output)


@click.group()
def cli():
    pass


@cli.command("generate")
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("-o", "--output", default=None, type=click.Path(), help="Output file path")
@click.option("--default-runner", default=None, help="Default runner for all jobs")
@click.option("--force", is_flag=True, help="Generate even if validation fails")
def _generate(input_files, output, default_runner, force):
    try:
        yaml_content = load_yaml_files(input_files)
        decoder = create_decoder()
        resources = decoder.decode_all(yaml_content)

        if not resources:
            logger.warning("No resources found in input files")
            sys.exit(1)

        if not _validate_resources(resources, force):
            sys.exit(1)

        result = _generate_output(resources, default_runner)
        _write_output(result, output)

    except DecodeError as e:
        logger.error(f"Decode error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"{e}")
        sys.exit(1)


@cli.command("validate")
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
def _validate(input_files):
    try:
        yaml_content = load_yaml_files(input_files)
        decoder = create_decoder()
        resources = decoder.decode_all(yaml_content)

        if not resources:
            logger.warning("No resources found in input files")
            sys.exit(1)

        validator_chain = create_default_validator_chain()
        has_errors = False

        for resource in resources:
            logger.info(f"Validating: {resource.api_version}/{resource.kind}")
            result = validator_chain.validate(resource)

            for warning in result.warnings:
                logger.warning(f"  {warning}")

            if result.valid:
                logger.info("  ✓ Valid")
            else:
                for error in result.errors:
                    logger.error(f"  ✗ {error}")
                has_errors = True

        if has_errors:
            sys.exit(1)

    except DecodeError as e:
        logger.error(f"Decode error: {e}")
        sys.exit(1)


@cli.command("run")
@click.option("--sources", required=True, help="YAML sources (comma/space separated)")
@click.option("--token", default=None, help="GitHub token for remote sources")
@click.option("-o", "--output", default=None, type=click.Path(), help="Output file path")
@click.option("--default-runner", default=None, help="Default runner for all jobs")
@click.option("--pipeline-vars", default=None, help="Extra variables: KEY1=val1; KEY2=val2")
@click.option("--force", is_flag=True, help="Generate even if validation fails")
def _run(sources, token, output, default_runner, pipeline_vars, force):
    try:
        source_list = parse_sources(sources)
        if not source_list:
            logger.error("No sources provided")
            sys.exit(1)

        logger.info("=== Input parameters ===")
        logger.info(f"  token:          {'***' if token else '<not set>'}")
        logger.info(f"  output:         {output or '<stdout>'}")
        logger.info(f"  default-runner: {default_runner or 'ubuntu-latest'}")
        logger.info(f"  pipeline-vars:  {pipeline_vars or '<not set>'}")
        logger.info(f"  force:          {force}")
        logger.info(f"  sources ({len(source_list)}):")
        for src in source_list:
            logger.info(f"    - {src}")

        extra_vars = parse_pipeline_vars(pipeline_vars)
        if extra_vars:
            logger.info(f"  resolved vars ({len(extra_vars)}):")
            for k, v in extra_vars.items():
                logger.info(f"    {k} = {v}")

        logger.info("Fetching sources...")
        yaml_content = fetch_all(source_list, token=token)

        decoder = create_decoder()
        resources = decoder.decode_all(yaml_content)

        if not resources:
            logger.warning("No resources found in fetched files")
            sys.exit(1)

        if not _validate_resources(resources, force):
            sys.exit(1)

        result = _generate_output(resources, default_runner, extra_vars)
        _write_output(result, output)

    except DecodeError as e:
        logger.error(f"Decode error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"{e}")
        sys.exit(1)


@cli.command("generate-matrix")
@click.option("--sources", required=True, help="YAML sources (comma/space separated)")
@click.option("--token", default=None, help="GitHub token for remote sources")
@click.option("--pipeline-vars", default=None, help="Extra variables: KEY1=val1; KEY2=val2")
@click.option("--force", is_flag=True, help="Generate even if validation fails")
def _generate_matrix(sources, token, pipeline_vars, force):
    """Generate a JSON matrix for GitHub Actions dynamic jobs."""
    import json

    try:
        source_list = parse_sources(sources)
        if not source_list:
            logger.error("No sources provided")
            sys.exit(1)

        yaml_content = fetch_all(source_list, token=token)
        decoder = create_decoder()
        resources = decoder.decode_all(yaml_content)

        if not resources:
            logger.warning("No resources found")
            sys.exit(1)

        if not _validate_resources(resources, force):
            sys.exit(1)

        config = GeneratorConfig()
        generator = WorkflowGenerator(config)
        generator.add_resources(resources)
        extra_vars = parse_pipeline_vars(pipeline_vars)
        if extra_vars:
            generator.add_extra_vars(extra_vars)
        workflow = generator.generate()

        jobs = workflow.get("jobs", {})
        global_env = workflow.get("env", {})

        matrix_items = []
        for job_name, job_def in jobs.items():
            item = {
                "job_name": job_name,
                "image": job_def.get("container", {}).get("image", ""),
                "command": "",
                "env_json": json.dumps({**global_env, **job_def.get("env", {})}),
            }
            for step in job_def.get("steps", []):
                if "run" in step and step.get("name", "").startswith("Run "):
                    item["command"] = step["run"]
                    break
            matrix_items.append(item)

        output = json.dumps({"include": matrix_items})
        sys.stdout.write(output)

    except DecodeError as e:
        logger.error(f"Decode error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"{e}")
        sys.exit(1)


@cli.command("list-types")
def _list_types():
    from github_actions_executor.scheme import scheme

    logger.info("Registered types:")
    for vk in scheme.known_types():
        logger.info(f"  - {vk}")


def main():
    logging.basicConfig(
        stream=sys.stdout,
        format="[%(asctime)s] [%(levelname)-5s] [%(filename)s:%(lineno)-3s] %(message)s",
    )
    logging.getLogger("github_actions_executor").setLevel(
        os.getenv("LOG_LEVEL") or logging.INFO
    )
    cli()


if __name__ == "__main__":
    main()
