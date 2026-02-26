FROM python:3.12-alpine

WORKDIR /app

COPY pyproject.toml ./
COPY github_actions_executor/ ./github_actions_executor/

RUN pip install --no-cache-dir .
