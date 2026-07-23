"""Agentic review focused on PRD chapter coverage (需求完成情况)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from biz.agent.agentic_reviewer import (
    AgenticReviewError,
    AgenticReviewer,
    ReviewLog,
    _collect_tool_calls,
    _estimate_tokens,
    _fail_agentic,
)
from biz.agent.prompts import load_prompt
from biz.agent.repo_syncer import LocalRepoSyncer
from biz.agent.runner import AgentRunner
from biz.utils.log import logger

_COMPLETION_MARKERS = ("完成度", "%")


def _safe_format(template: str, **kwargs: str) -> str:
    """Replace {name} placeholders without str.format (PRD may contain braces)."""
    out = template
    for key, value in kwargs.items():
        out = out.replace("{" + key + "}", value)
    return out


def _looks_like_requirement_report(text: str | None) -> bool:
    """Requirement report should mention completion percentage; no 总分 required."""
    if not text or len(text.strip()) < 40:
        return False
    return all(m in text for m in _COMPLETION_MARKERS) or ("完成度" in text and "%" in text)


class RequirementReviewer(AgenticReviewer):
    """Reuse repo sync + tools; different prompt and success gate."""

    def review_requirements(
        self,
        *,
        diffs_text: str,
        commits_text: str,
        prd_text: str,
        description: str,
        chapter_hints: list[str] | None = None,
    ) -> str:
        start = time.monotonic()
        try:
            syncer = LocalRepoSyncer(cache_root=self.cache_root)
            repo_root = syncer.sync_to(url=self.repo_url, key=self.repo_key, ref=self.ref)
        except Exception as e:
            _fail_agentic(
                f"需求审查：仓库同步失败: {e}",
                project=self.repo_key,
                ref=self.ref,
            )

        adapter = self._build_adapter()
        registry = self._build_registry(repo_root)
        # Slightly fewer iterations than full code review — coverage focused.
        max_iter = int(os.getenv("PRD_AGENT_MAX_ITERATIONS", str(min(self.max_iterations, 16))))
        runner = AgentRunner(
            adapter=adapter,
            registry=registry,
            max_iterations=max_iter,
            total_token_cap=self.total_token_cap,
        )

        prompts = load_prompt(
            "prd_requirement_review_prompt",
            style=os.getenv("REVIEW_STYLE", "professional"),
        )
        chapters = "、".join(chapter_hints or []) or (
            "（描述未写明具体章节号，请从 PR 描述与 PRD 正文自行推断本期范围）"
        )
        user_content = _safe_format(
            prompts["user_message"]["content"],
            diffs_text=diffs_text,
            commits_text=commits_text,
            repo_root=str(repo_root),
            prd_text=prd_text,
            description=description or "（空）",
            chapter_hints=chapters,
        )
        system = prompts["system_message"]
        system = {
            **system,
            "content": _safe_format(system["content"], repo_root=str(repo_root)),
        }
        messages = [system, {"role": "user", "content": user_content}]

        run_meta: dict[str, Any] = {}
        try:
            result = runner.run(messages, out=run_meta)
        except Exception as e:
            _fail_agentic(
                f"需求审查 Agent 运行失败: {e}",
                project=self.repo_key,
                ref=self.ref,
            )

        if not _looks_like_requirement_report(result):
            preview = (result or "")[:240].replace("\n", " ")
            _fail_agentic(
                f"需求审查输出缺少完成度标记（len={len(result or '')}）: {preview}",
                project=self.repo_key,
                ref=self.ref,
            )

        run_messages = run_meta.get("messages", messages)
        log_entry = ReviewLog(
            event="prd_requirement_review",
            project=self.repo_key,
            ref=self.ref,
            strategy="prd_agentic",
            iterations=run_meta.get("iterations", 0),
            total_tokens_est=_estimate_tokens(run_messages),
            duration_ms=int((time.monotonic() - start) * 1000),
            review_result_length=len(result),
            score=0,
            degraded=False,
            tool_calls=_collect_tool_calls(run_messages),
        )
        logger.info(json.dumps(asdict(log_entry), ensure_ascii=False))
        return result
