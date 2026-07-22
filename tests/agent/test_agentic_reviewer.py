from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from biz.agent.agentic_reviewer import AgenticReviewError, AgenticReviewer


def _fake_remote(tmp_path: Path) -> Path:
    import subprocess
    remote = tmp_path / "remote.git"
    remote.mkdir()
    subprocess.run(["git", "init", "--bare", "-q"], cwd=remote, check=True)
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


class TestAgenticReviewer:
    def test_review_returns_llm_content(self, tmp_path, monkeypatch):
        remote = _fake_remote(tmp_path)
        cache = tmp_path / "cache"

        # Mock the LLM client to return a fixed review.
        mock_client = MagicMock()
        mock_client.chat_with_tools.return_value = {
            "content": "Looks good. 总分:90分",
            "tool_calls": [],
            "raw": None,
        }
        from biz.agent.llm_adapter import LLMAdapter
        adapter = LLMAdapter(mock_client, use_native=True)

        reviewer = AgenticReviewer(
            repo_url=str(remote),
            repo_key="test/proj",
            ref="main",
            cache_root=cache,
            adapter=adapter,
            max_iterations=5,
        )
        result = reviewer.review(diffs_text="diff content", commits_text="msg")
        assert "Looks good" in result

    def test_review_fails_when_output_missing_score_marker(self, tmp_path, monkeypatch):
        """Missing `总分` marker must abort + notify, not post agent monologue."""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        remote = _fake_remote(tmp_path)
        cache = tmp_path / "cache"

        mock_client = MagicMock()
        mock_client.chat_with_tools.return_value = {
            "content": (
                "The AST query doesn't find references, but the files do exist. "
                "Let me check the openspec folder for the design docs."
            ),
            "tool_calls": [],
            "raw": None,
        }
        from biz.agent.llm_adapter import LLMAdapter
        adapter = LLMAdapter(mock_client, use_native=True)

        reviewer = AgenticReviewer(
            repo_url=str(remote),
            repo_key="test/proj_noreview",
            ref="main",
            cache_root=cache,
            adapter=adapter,
            max_iterations=3,
        )
        with patch("biz.agent.agentic_reviewer.notifier.send_notification") as mock_notify:
            with pytest.raises(AgenticReviewError, match="总分"):
                reviewer.review(diffs_text="d", commits_text="c")
        mock_notify.assert_called_once()

    def test_review_fails_on_runner_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        remote = _fake_remote(tmp_path)
        cache = tmp_path / "cache"

        from biz.agent.runner import TokenBudgetExceeded
        from biz.agent.llm_adapter import LLMAdapter

        mock_client = MagicMock()
        adapter = LLMAdapter(mock_client, use_native=True)

        with patch("biz.agent.agentic_reviewer.AgentRunner") as MockRunner:
            mock_instance = MagicMock()
            mock_instance.run.side_effect = TokenBudgetExceeded("too big")
            MockRunner.return_value = mock_instance

            reviewer = AgenticReviewer(
                repo_url=str(remote),
                repo_key="test/proj2",
                ref="main",
                cache_root=cache,
                adapter=adapter,
                max_iterations=5,
            )
            with patch("biz.agent.agentic_reviewer.notifier.send_notification") as mock_notify:
                with pytest.raises(AgenticReviewError, match="Agent 运行失败"):
                    reviewer.review(diffs_text="d", commits_text="c")
            mock_notify.assert_called_once()