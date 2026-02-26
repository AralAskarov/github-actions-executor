from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

import click

from github_actions_executor.api import v1 as _  # noqa: F401
from github_actions_executor.decoder import DecodeError, create_decoder
from github_actions_executor.fetcher import parse_sources, fetch_all
from github_actions_executor.generator import WorkflowGenerator, GeneratorConfig
from github_actions_executor.validator import create_default_validator_chain

logger = logging.getLogger("github_actions_executor")


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


def _generate_output(resources, default_runner: Optional[str] = None) -> str:
    config = GeneratorConfig(
        default_runner=default_runner or "ubuntu-latest",
    )
    generator = WorkflowGenerator(config)
    generator.add_resources(resources)
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
@click.option("--force", is_flag=True, help="Generate even if validation fails")
def _run(sources, token, output, default_runner, force):
    try:
        source_list = parse_sources(sources)
        if not source_list:
            logger.error("No sources provided")
            sys.exit(1)

        logger.info("=== Input parameters ===")
        logger.info(f"  token:          {'***' if token else '<not set>'}")
        logger.info(f"  output:         {output or '<stdout>'}")
        logger.info(f"  default-runner: {default_runner or 'ubuntu-latest'}")
        logger.info(f"  force:          {force}")
        logger.info(f"  sources ({len(source_list)}):")
        for src in source_list:
            logger.info(f"    - {src}")

        logger.info("Fetching sources...")
        yaml_content = fetch_all(source_list, token=token)

        decoder = create_decoder()
        resources = decoder.decode_all(yaml_content)

        if not resources:
            logger.warning("No resources found in fetched files")
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
