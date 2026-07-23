"""Lazy local clone/fetch of repositories for agentic review."""
from __future__ import annotations

import errno
import fcntl
import os
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from biz.utils.log import logger


def _sanitize_key(key: str) -> str:
    """Turn a project key into a safe directory name."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)


def _pick_token_for_host(host: str | None) -> str | None:
    """Return the configured PAT env var value for this host, or None.

    Resolution:
      - ``github.com`` / ``*.github.com`` -> ``GITHUB_ACCESS_TOKEN``
      - host contains ``gitea`` -> ``GITEA_ACCESS_TOKEN``
      - otherwise (incl. self-hosted GitLab) -> ``GITLAB_ACCESS_TOKEN``
    """
    if not host:
        return None
    h = host.lower()
    if h == "github.com" or h.endswith(".github.com"):
        return os.getenv("GITHUB_ACCESS_TOKEN")
    if "gitea" in h:
        return os.getenv("GITEA_ACCESS_TOKEN")
    return os.getenv("GITLAB_ACCESS_TOKEN")


def _auth_url(url: str) -> str:
    """Return ``url`` with credentials injected based on its host.

    No-op for non-HTTPS URLs, already-credentialed URLs, or when no
    matching token env var is set. The token is URL-encoded so special
    characters (``+``, ``/``, ``=``, ``@``) don't corrupt the URL.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return url
    if "@" in (parsed.netloc or ""):
        return url
    host = parsed.hostname
    if not host:
        return url
    token = _pick_token_for_host(host)
    if not token:
        return url
    userinfo = f"oauth2:{quote(token, safe='')}"
    return urlunparse(parsed._replace(netloc=f"{userinfo}@{parsed.netloc}"))


def _mirror_prefix() -> str:
    """Normalized ``GIT_CLONE_MIRROR_PREFIX`` (trailing slash), or empty."""
    raw = (os.getenv("GIT_CLONE_MIRROR_PREFIX") or "").strip()
    if not raw:
        return ""
    return raw if raw.endswith("/") else f"{raw}/"


def _peel_mirror(url: str) -> str:
    """Strip configured mirror prefix so auth/host logic sees the real URL."""
    prefix = _mirror_prefix()
    if prefix and url.startswith(prefix):
        return url[len(prefix) :]
    return url


def _strip_userinfo(url: str) -> str:
    """Remove embedded credentials from an HTTPS URL (for token refresh)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return url
    netloc = parsed.netloc or ""
    if "@" not in netloc:
        return url
    hostport = netloc.rsplit("@", 1)[-1]
    return urlunparse(parsed._replace(netloc=hostport))


def _is_github_https(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return host == "github.com" or host.endswith(".github.com")


def _transport_url(url: str) -> str:
    """Build the URL actually used for git clone/fetch.

    Domestic ECS often cannot reach ``github.com`` git over HTTPS; set
    ``GIT_CLONE_MIRROR_PREFIX`` (e.g. ``https://ghproxy.net/``) to route
    github.com traffic through a mirror — same pattern as
    ``scripts/deploy/remote-update.sh``.

    Important: common mirrors return HTTP 403 when the nested URL embeds
    ``oauth2:<token>@``. For mirrored github.com clones we therefore use a
    *bare* HTTPS URL (works for public repos). Direct (non-mirror) clones
    still get host-based credential injection for private repos.
    """
    canonical = _strip_userinfo(_peel_mirror(url))
    prefix = _mirror_prefix()
    if prefix and _is_github_https(canonical):
        if canonical.startswith(prefix):
            return canonical
        return f"{prefix}{canonical}"
    return _auth_url(canonical)


class LocalRepoSyncer:
    """Lazily clone (first sync) or fetch+checkout (subsequent) a remote repo.

    State lives under `cache_root`. Each project has:
        cache_root/<safe_key>/        — git working tree
        cache_root/<safe_key>.lock    — fcntl file lock
    """

    def __init__(
        self,
        cache_root: Path | str,
        *,
        clone_timeout: int = 300,
        lock_wait_seconds: int = 60,
    ) -> None:
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.clone_timeout = clone_timeout
        self.lock_wait_seconds = lock_wait_seconds

    def sync_to(self, *, url: str, key: str, ref: str) -> Path:
        """Ensure repo for `key` is locally available and `ref` is checked out.

        Returns the local repo path (working tree).
        Raises RuntimeError on failure.
        """
        safe = _sanitize_key(key)
        target = self.cache_root / safe
        lock_path = self.cache_root / f"{safe}.lock"

        with self._lock(lock_path):
            if not (target / ".git").exists():
                self._clone(_transport_url(url), target)
            self._ensure_authenticated_remote(target, preferred_url=url)
            self._fetch_and_checkout(target, ref)
        return target

    def _ensure_authenticated_remote(self, target: Path, preferred_url: str | None = None) -> None:
        """Rewrite ``origin`` to an auth + mirror transport URL.

        Handles:
          1. Repo cloned before auth/mirror support (bare github URL).
          2. Token env var rotated — re-inject credentials.
          3. ``GIT_CLONE_MIRROR_PREFIX`` enabled — rewrite origin so fetch
             also goes through the mirror (direct github.com often hangs).

        Silently no-ops if ``origin`` doesn't exist. Raises on set-url
        failure; the caller's soft-degrade will then kick in.
        """
        try:
            r = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return
        except FileNotFoundError:
            # git binary missing; let the subsequent fetch raise.
            return
        existing = r.stdout.strip()
        base = preferred_url or existing
        new_url = _transport_url(base)
        if new_url == existing:
            return
        logger.info("updating origin transport URL for %s (mirror/auth)", target.name)
        try:
            subprocess.run(
                ["git", "remote", "set-url", "origin", new_url],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            stderr = (e.stderr or "").strip() if hasattr(e, "stderr") else str(e)
            raise RuntimeError(f"git remote set-url failed: {stderr}") from e

    @contextmanager
    def _lock(self, lock_path: Path):
        lock_path.touch(exist_ok=True)
        f = open(lock_path, "w")
        deadline = time.monotonic() + self.lock_wait_seconds
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    logger.warning("could not acquire lock %s within %ds, proceeding without lock",
                                   lock_path, self.lock_wait_seconds)
                    break
                time.sleep(0.5)
        try:
            yield
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            f.close()

    def _clone(self, url: str, target: Path) -> None:
        # Redact oauth2 tokens whether in netloc or inside a mirror path.
        redacted = re.sub(r"oauth2:[^/@\s]+@", "oauth2:***@", url)
        logger.info("cloning %s -> %s", redacted, target)
        try:
            subprocess.run(
                ["git", "clone", url, str(target)],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.clone_timeout,
            )
        except subprocess.TimeoutExpired as e:
            # Partial clone dirs block the next attempt.
            if target.exists():
                subprocess.run(["rm", "-rf", str(target)], check=False)
            raise RuntimeError(f"git clone timed out after {self.clone_timeout}s") from e
        except subprocess.CalledProcessError as e:
            if target.exists():
                subprocess.run(["rm", "-rf", str(target)], check=False)
            raise RuntimeError(f"git clone failed: {e.stderr.strip()}") from e

    def _fetch_and_checkout(self, target: Path, ref: str) -> None:
        try:
            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=target, check=True, capture_output=True, text=True, timeout=self.clone_timeout,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"git fetch failed: {e.stderr.strip()}") from e
        # Determine if ref looks like a SHA (hex, length >= 7) or a branch name.
        is_sha = bool(re.fullmatch(r"[0-9a-fA-F]{7,40}", ref))
        if is_sha:
            cmd = ["git", "reset", "--hard", ref]
        else:
            # Use origin/<ref> as the source of truth so the working tree
            # tracks new commits pushed to the remote since the last sync.
            cmd = ["git", "reset", "--hard", f"origin/{ref}"]
        try:
            subprocess.run(
                cmd, cwd=target, check=True, capture_output=True, text=True, timeout=self.clone_timeout,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"git checkout failed: {e.stderr.strip()}") from e
