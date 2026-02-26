from __future__ import annotations

import re
from pathlib import Path
from typing import List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Matches GitHub web URLs like:
#   https://github.com/owner/repo/blob/main/path/to/file.yaml
_GITHUB_BLOB_RE = re.compile(
    r"^(https?://github\.com)/"
    r"([^/]+/[^/]+)/"       # owner/repo
    r"blob/"
    r"([^/]+)/"             # branch/ref
    r"(.+)$"                # file path
)

# Matches GitHub raw URLs
_GITHUB_RAW_RE = re.compile(
    r"^https?://raw\.githubusercontent\.com/.+$"
)


def parse_sources(raw: str) -> List[str]:
    parts = re.split(r"[,\s]+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def _to_github_raw_url(url: str) -> str:
    match = _GITHUB_BLOB_RE.match(url)
    if not match:
        return url

    _, repo_path, ref, file_path = match.groups()
    return f"https://raw.githubusercontent.com/{repo_path}/{ref}/{file_path}"


def _needs_conversion(url: str) -> bool:
    if _GITHUB_RAW_RE.match(url):
        return False
    if _GITHUB_BLOB_RE.match(url):
        return True
    return False


def fetch_source(url: str, token: str | None = None) -> str:
    if url.startswith(("http://", "https://")):
        if _needs_conversion(url):
            url = _to_github_raw_url(url)
        return _fetch_http(url, token)
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


def _fetch_http(url: str, token: str | None = None) -> str:
    headers: dict[str, str] = {"Accept": "application/vnd.github.raw+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"Failed to fetch {url}: {e.reason}") from e
