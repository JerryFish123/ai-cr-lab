"""End-to-end integration tests for the AgenticReviewer pipeline.

These tests run against a real local git remote (no mocking of RepoSyncer)
with a mock LLM client. They exercise the full pipeline:
  LocalRepoSyncer -> AgentRunner -> LLMAdapter -> mock BaseClient.

Test 2 exercises failure when AgentRunner raises (notify + no diff_only fallback).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from biz.agent.agentic_reviewer import AgenticReviewer
from biz.agent.llm_adapter import LLMAdapter
from biz.agent.runner import TokenBudgetExceeded


@pytest.fixture
def tiny_remote(tmp_path: Path) -> Path:
    """Create a bare git remote with one initial commit on `main`."""
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


class TestEndToEndAgentic:
    def test_agentic_reviewer_completes_with_mock_llm(self, tmp_path, tiny_remote):
        cache = tmp_path / "cache"

        mock_client = MagicMock()
        mock_client.chat_with_tools.return_value = {
            "content": "Review complete. 总分:85分",
            "tool_calls": [],
            "raw": None,
        }
        adapter = LLMAdapter(mock_client, use_native=True)

        reviewer = AgenticReviewer(
            repo_url=str(tiny_remote),
            repo_key="int/proj",
            ref="main",
            cache_root=cache,
            adapter=adapter,
            max_iterations=3,
        )

        result = reviewer.review(diffs_text="+ new line", commits_text="add line")

        assert "85" in result
        assert (cache / "int_proj").exists()
        assert mock_client.chat_with_tools.called

    def test_agentic_reviewer_raises_when_runner_raises(self, tmp_path, tiny_remote, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        cache = tmp_path / "cache"

        mock_client = MagicMock()
        adapter = LLMAdapter(mock_client, use_native=True)

        with patch("biz.agent.agentic_reviewer.AgentRunner") as MockRunner:
            mock_instance = MagicMock()
            mock_instance.run.side_effect = TokenBudgetExceeded("over")
            MockRunner.return_value = mock_instance

            reviewer = AgenticReviewer(
                repo_url=str(tiny_remote),
                repo_key="int/proj",
                ref="main",
                cache_root=cache,
                adapter=adapter,
                max_iterations=3,
            )
            with patch("biz.agent.agentic_reviewer.notifier.send_notification"):
                from biz.agent.agentic_reviewer import AgenticReviewError
                with pytest.raises(AgenticReviewError, match="Agent 运行失败"):
                    reviewer.review(diffs_text="d", commits_text="c")