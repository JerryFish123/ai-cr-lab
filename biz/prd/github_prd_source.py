"""Resolve PRD bytes via GitHub API when github.com HTTPS is unreachable.

Domestic ECS can reach ``api.github.com`` but often times out on
``github.com/user-attachments`` and ``raw.githubusercontent.com``.
Prefer Contents API (``Accept: application/vnd.github.raw``), and when the
PR only links a user-attachment, fall back to a PRD file already in the repo.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse

import requests

from biz.utils.log import logger

_BLOB_RE = re.compile(
    r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)$"
)
_RAW_RE = re.compile(
    r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<ref>[^/]+)/(?P<path>.+)$"
)
_DOC_NAME_RE = re.compile(r"\.(?:pdf|docx?)$", re.IGNORECASE)
_PRD_NAME_RE = re.compile(r"prd|需求|产品需求", re.IGNORECASE)


@dataclass(frozen=True)
class GithubFileRef:
    owner: str
    repo: str
    ref: str
    path: str


def split_repo_key(repo_key: str | None) -> tuple[str, str] | None:
    if not repo_key or "/" not in repo_key:
        return None
    owner, repo = repo_key.split("/", 1)
    owner, repo = owner.strip(), repo.strip()
    if not owner or not repo:
        return None
    return owner, repo


def filename_hint_from_url(url: str) -> str:
    path = unquote(urlparse(url or "").path or "")
    name = path.rstrip("/").rsplit("/", 1)[-1] if path else ""
    return name


def parse_github_repo_file_url(url: str) -> GithubFileRef | None:
    """Parse github.com blob / raw.githubusercontent.com file URLs."""
    if not url:
        return None
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    path = unquote(parsed.path or "")

    if host in ("github.com", "www.github.com"):
        m = _BLOB_RE.match(path)
        if not m:
            return None
        return GithubFileRef(
            owner=m.group("owner"),
            repo=m.group("repo"),
            ref=m.group("ref"),
            path=m.group("path"),
        )

    if host == "raw.githubusercontent.com":
        m = _RAW_RE.match(path)
        if not m:
            return None
        return GithubFileRef(
            owner=m.group("owner"),
            repo=m.group("repo"),
            ref=m.group("ref"),
            path=m.group("path"),
        )
    return None


def _api_headers(token: str, *, raw: bool) -> dict[str, str]:
    accept = "application/vnd.github.raw" if raw else "application/vnd.github+json"
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ai-cr-lab-prd-extractor/1.0",
    }


def fetch_repo_file_bytes(
    *,
    owner: str,
    repo: str,
    path: str,
    ref: str,
    token: str,
    timeout: int | None = None,
) -> bytes:
    """Download a repo file via Contents API raw media type."""
    t = timeout if timeout is not None else int(os.getenv("PRD_API_TIMEOUT", "60"))
    api = (
        f"https://api.github.com/repos/{owner}/{repo}/contents/"
        f"{quote(path, safe='/')}?ref={quote(ref, safe='')}"
    )
    resp = requests.get(api, headers=_api_headers(token, raw=True), timeout=t)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Contents API HTTP {resp.status_code} for {owner}/{repo}:{path}@{ref}"
        )
    data = resp.content or b""
    if not data:
        raise RuntimeError(f"Contents API returned empty body for {path}")
    return data


def _score_prd_path(path: str, hint: str) -> tuple[int, int, str]:
    """Lower tuple sorts better."""
    name = path.rsplit("/", 1)[-1]
    hint_l = (hint or "").lower()
    name_l = name.lower()
    path_l = path.lower()
    hint_stem = hint_l.rsplit(".", 1)[0] if hint_l else ""
    name_stem = name_l.rsplit(".", 1)[0]

    rank = 50
    if hint_l and name_l == hint_l:
        rank = 0
    elif hint_stem and (hint_stem in name_stem or name_stem in hint_stem):
        rank = 1
    elif _PRD_NAME_RE.search(name):
        rank = 2
    elif _PRD_NAME_RE.search(path):
        rank = 3
    else:
        rank = 40

    preferred_dir = 0 if path_l.startswith(("doc/", "docs/", "prd/", "prds/")) else 1
    return (rank, preferred_dir, path_l)


def find_prd_path_in_repo(
    *,
    owner: str,
    repo: str,
    ref: str,
    token: str,
    hint_filename: str = "",
    timeout: int | None = None,
) -> str | None:
    """Pick best PRD-like path from the git tree at ``ref``."""
    t = timeout if timeout is not None else int(os.getenv("PRD_API_TIMEOUT", "60"))
    commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{quote(ref, safe='')}"
    commit_resp = requests.get(commit_url, headers=_api_headers(token, raw=False), timeout=t)
    if commit_resp.status_code != 200:
        logger.warning(
            "prd repo fallback: commit lookup failed HTTP %s for %s/%s@%s",
            commit_resp.status_code,
            owner,
            repo,
            ref,
        )
        return None
    tree_sha = ((commit_resp.json() or {}).get("commit") or {}).get("tree", {}).get("sha")
    if not tree_sha:
        return None

    tree_url = (
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/"
        f"{tree_sha}?recursive=1"
    )
    tree_resp = requests.get(tree_url, headers=_api_headers(token, raw=False), timeout=t)
    if tree_resp.status_code != 200:
        logger.warning(
            "prd repo fallback: tree lookup failed HTTP %s for %s/%s",
            tree_resp.status_code,
            owner,
            repo,
        )
        return None

    entries = (tree_resp.json() or {}).get("tree") or []
    candidates: list[str] = []
    for item in entries:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        if not path or not _DOC_NAME_RE.search(path):
            continue
        name = path.rsplit("/", 1)[-1]
        if _PRD_NAME_RE.search(name) or _PRD_NAME_RE.search(path):
            candidates.append(path)
            continue
        hint = (hint_filename or "").lower()
        if hint and hint in name.lower():
            candidates.append(path)
            continue
        hint_stem = hint.rsplit(".", 1)[0] if hint else ""
        if hint_stem and len(hint_stem) >= 4 and hint_stem in name.lower():
            candidates.append(path)

    if not candidates:
        return None
    candidates.sort(key=lambda p: _score_prd_path(p, hint_filename))
    return candidates[0]


def resolve_prd_bytes_via_github_api(
    *,
    url: str,
    token: str | None,
    repo_key: str | None = None,
    ref: str | None = None,
) -> tuple[bytes | None, str]:
    """Try API paths. Returns (bytes|None, source_label_or_error)."""
    if not token:
        return None, "无 GitHub Token，无法走 Contents API"

    file_ref = parse_github_repo_file_url(url)
    if file_ref:
        try:
            data = fetch_repo_file_bytes(
                owner=file_ref.owner,
                repo=file_ref.repo,
                path=file_ref.path,
                ref=file_ref.ref,
                token=token,
            )
            return data, f"contents-api:{file_ref.owner}/{file_ref.repo}/{file_ref.path}@{file_ref.ref}"
        except Exception as e:  # noqa: BLE001
            logger.warning("prd contents-api blob/raw failed: %s", e)

    parts = split_repo_key(repo_key)
    if not parts or not ref:
        return None, "缺少 repo_key/ref，无法仓库回退"
    owner, repo = parts
    hint = filename_hint_from_url(url)
    try:
        path = find_prd_path_in_repo(
            owner=owner,
            repo=repo,
            ref=ref,
            token=token,
            hint_filename=hint,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("prd repo tree search failed: %s", e)
        return None, f"仓库 PRD 检索失败: {type(e).__name__}: {e}"

    if not path:
        return None, f"仓库内未找到 PRD 文档（hint={hint or '无'}）"

    try:
        data = fetch_repo_file_bytes(
            owner=owner, repo=repo, path=path, ref=ref, token=token
        )
        return data, f"contents-api-fallback:{owner}/{repo}/{path}@{ref}"
    except Exception as e:  # noqa: BLE001
        logger.warning("prd contents-api fallback fetch failed: %s", e)
        return None, f"仓库 PRD 下载失败: {type(e).__name__}: {e}"
