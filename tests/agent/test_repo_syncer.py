import subprocess
from pathlib import Path

import pytest

from biz.agent.repo_syncer import LocalRepoSyncer, _transport_url


class TestTransportUrl:
    def test_no_mirror_when_unset(self, monkeypatch):
        monkeypatch.delenv("GIT_CLONE_MIRROR_PREFIX", raising=False)
        monkeypatch.setenv("GITHUB_ACCESS_TOKEN", "tok")
        assert _transport_url("https://github.com/o/r.git") == \
            "https://oauth2:tok@github.com/o/r.git"

    def test_wraps_github_with_mirror_prefix_without_embedded_creds(self, monkeypatch):
        # ghproxy returns 403 if oauth2:token@ is nested in the mirrored URL.
        monkeypatch.setenv("GIT_CLONE_MIRROR_PREFIX", "https://ghproxy.net")
        monkeypatch.setenv("GITHUB_ACCESS_TOKEN", "tok")
        assert _transport_url("https://github.com/o/r.git") == \
            "https://ghproxy.net/https://github.com/o/r.git"

    def test_mirror_skips_non_github(self, monkeypatch):
        monkeypatch.setenv("GIT_CLONE_MIRROR_PREFIX", "https://ghproxy.net/")
        monkeypatch.setenv("GITLAB_ACCESS_TOKEN", "gl")
        assert _transport_url("https://gitlab.example.com/o/r.git") == \
            "https://oauth2:gl@gitlab.example.com/o/r.git"


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    """Create a local bare git repo acting as 'remote'."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    subprocess.run(["git", "init", "--bare", "-q"], cwd=remote, check=True)
    # Make an initial commit on a working tree and push.
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "[email protected]"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=work, check=True)
    (work / "f.txt").write_text("v1\n")
    subprocess.run(["git", "add", "-A"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=work, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=work, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=work, check=True)
    return remote


class TestLocalRepoSyncer:
    def test_first_clone_creates_local_repo(self, tmp_path, bare_remote):
        cache = tmp_path / "cache"
        syncer = LocalRepoSyncer(cache_root=cache)
        path = syncer.sync_to(url=str(bare_remote), key="proj", ref="main")
        assert path.exists()
        assert (path / "f.txt").exists()

    def test_second_sync_updates_to_new_commit(self, tmp_path, bare_remote):
        cache = tmp_path / "cache"
        syncer = LocalRepoSyncer(cache_root=cache)

        # First sync.
        syncer.sync_to(url=str(bare_remote), key="proj", ref="main")

        # Add new commit on the remote.
        work = tmp_path / "work"
        (work / "f.txt").write_text("v2\n")
        subprocess.run(["git", "add", "-A"], cwd=work, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=work, check=True)
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=work, check=True)

        # Second sync fetches new state.
        path = syncer.sync_to(url=str(bare_remote), key="proj", ref="main")
        assert (path / "f.txt").read_text() == "v2\n"

    def test_clone_failure_raises(self, tmp_path):
        cache = tmp_path / "cache"
        syncer = LocalRepoSyncer(cache_root=cache, clone_timeout=5)
        with pytest.raises(RuntimeError):
            syncer.sync_to(url="https://nonexistent.example.invalid/repo.git", key="proj", ref="main")

    def test_key_sanitized_to_safe_dirname(self, tmp_path, bare_remote):
        cache = tmp_path / "cache"
        syncer = LocalRepoSyncer(cache_root=cache)
        path = syncer.sync_to(url=str(bare_remote), key="group/sub/proj", ref="main")
        # 'group/sub/proj' -> 'group_sub_proj' (or similar; just check it's under cache)
        assert str(path).startswith(str(cache))
