from __future__ import annotations

import re
from pathlib import Path
from typing import List
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# GitHub: https://github.com/owner/repo/blob/main/path/file.yaml
_GITHUB_BLOB_RE = re.compile(
    r"^(https?://github\.com)/"
    r"([^/]+/[^/]+)/"       # owner/repo
    r"blob/"
    r"([^/]+)/"             # branch/ref
    r"(.+)$"                # file path
)
_GITHUB_RAW_RE = re.compile(r"^https?://raw\.githubusercontent\.com/.+$")

# GitLab: https://gitlab.com/group/project/-/blob/branch/path/file.yaml
_GITLAB_BLOB_RE = re.compile(
    r"^(https?://[^/]+)/"   # base URL
    r"(.+?)/"                # project path (group/subgroup/project)
    r"-/blob/"
    r"([^/]+)/"              # branch/ref
    r"(.+)$"                 # file path
)
_GITLAB_RAW_RE = re.compile(r"^https?://[^/]+/.+/-/raw/.+$")


def parse_sources(raw: str) -> List[str]:
    parts = re.split(r"[,\s]+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def _detect_platform(url: str) -> str:
    if "github.com" in url or "raw.githubusercontent.com" in url:
        return "github"
    if "/-/blob/" in url or "/-/raw/" in url or "/api/v4/projects/" in url:
        return "gitlab"
    return "unknown"


def _to_raw_url(url: str) -> str:
    """Convert browser blob URL to a raw/API URL."""
    # GitHub blob -> raw
    gh = _GITHUB_BLOB_RE.match(url)
    if gh:
        _, repo_path, ref, file_path = gh.groups()
        return f"https://raw.githubusercontent.com/{repo_path}/{ref}/{file_path}"

    # GitLab blob -> API raw
    gl = _GITLAB_BLOB_RE.match(url)
    if gl:
        base, project_path, ref, file_path = gl.groups()
        return (
            f"{base}/api/v4/projects/{quote(project_path, safe='')}"
            f"/repository/files/{quote(file_path, safe='')}/raw?ref={ref}"
        )

    return url


def _needs_conversion(url: str) -> bool:
    if _GITHUB_RAW_RE.match(url) or _GITLAB_RAW_RE.match(url):
        return False
    if _GITHUB_BLOB_RE.match(url) or _GITLAB_BLOB_RE.match(url):
        return True
    return False


def fetch_source(url: str, token: str | None = None) -> str:
    if url.startswith(("http://", "https://")):
        if _needs_conversion(url):
            url = _to_raw_url(url)
        platform = _detect_platform(url)
        return _fetch_http(url, token, platform)
    path = Path(url)
    if not path.exists():
        raise FileNotFoundError(f"Local file not found: {url}")
    return path.read_text(encoding="utf-8")


def fetch_all(sources: List[str], token: str | None = None) -> str:
    docs: List[str] = []
    for src in sources:
        content = fetch_source(src, token)
        docs.append(content)
    return "\n---\n".join(docs)


def _fetch_http(url: str, token: str | None = None, platform: str = "github") -> str:
    headers: dict[str, str] = {}
    if token:
        if platform == "gitlab":
            headers["PRIVATE-TOKEN"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
            headers["Accept"] = "application/vnd.github.raw+json"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"Failed to fetch {url}: {e.reason}") from e
