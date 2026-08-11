"""Triple-section AI review: PRD coverage / blast radius / security-performance risks."""
from __future__ import annotations

import os
import re

from biz.agent.agentic_reviewer import AgenticReviewer, _fail_agentic
from biz.prd.description import extract_description_body, parse_prd_intent
from biz.prd.extract import resolve_and_extract_prd
from biz.utils.log import logger
from biz.utils.review_report_format import (
    PRD_MISSING_MESSAGE,
    looks_like_triple_report,
    normalize_triple_report,
)

SECTION_RISK = "### 3. 安全与性能风险"


def run_triple_review(
    *,
    changes: list,
    commits_text: str,
    webhook_data: dict,
    access_token: str,
    platform_url: str,
    repo_url: str | None,
    repo_key: str | None,
    ref: str | None,
) -> str:
    """Produce a single Markdown report with three fixed sections."""
    if not (repo_url and repo_key and ref):
        _fail_agentic(
            "无法从 webhook 解析仓库地址/项目/ref，无法启动三向审查",
            project=str(repo_key or ""),
            ref=str(ref or ""),
        )

    description = extract_description_body(webhook_data)
    intent = parse_prd_intent(description)
    has_prd_attachment = intent.should_run_requirement_review
    diffs_text = str(changes)
    cache_root = os.getenv("REPO_CACHE_DIR", "data/repo_cache")
    reviewer = AgenticReviewer(
        repo_url=repo_url,
        repo_key=repo_key,
        ref=ref,
        cache_root=cache_root,
    )

    if not has_prd_attachment:
        logger.info("triple review: no PRD attachment; risk-only path")
        risk_body = reviewer.review(
            diffs_text=diffs_text,
            commits_text=commits_text,
            prompt_key="risk_only_review_prompt",
            extra_format={},
            validate=lambda t: bool(t and ("安全" in t or "性能" in t or "风险" in t or "-" in t)),
        )
        return normalize_triple_report(
            "",
            has_prd=False,
            risk_section=_ensure_risk_section(risk_body),
        )

    # Has PRD attachment — download then full triple agentic review.
    extracted = resolve_and_extract_prd(
        intent.primary_url or "",
        access_token,
        repo_key=repo_key,
        ref=ref,
    )
    if not extracted.ok:
        logger.warning("triple review: PRD extract failed: %s", extracted.reason)
        risk_body = reviewer.review(
            diffs_text=diffs_text,
            commits_text=commits_text,
            prompt_key="risk_only_review_prompt",
            extra_format={},
            validate=lambda t: bool(t and len(t.strip()) > 10),
        )
        fail_msg = f"PRD解析失败，无法结合业务分析代码（{extracted.reason or '未知原因'}）"
        return normalize_triple_report(
            "",
            has_prd=False,
            missing_message=fail_msg,
            risk_section=_ensure_risk_section(risk_body),
        )

    chapter_hints = ", ".join(intent.chapter_hints) if intent.chapter_hints else "（无）"
    report = reviewer.review(
        diffs_text=diffs_text,
        commits_text=commits_text,
        prompt_key="triple_review_prompt",
        extra_format={
            "description": description,
            "chapter_hints": chapter_hints,
            "prd_text": extracted.text,
        },
        validate=looks_like_triple_report,
    )
    return normalize_triple_report(report, has_prd=True)


def _ensure_risk_section(risk_body: str) -> str:
    text = (risk_body or "").strip()
    if not text:
        return f"{SECTION_RISK}\n\n- 未发现明显安全或性能风险"
    if re.search(r"安全与性能风险|严重问题|潜在风险", text):
        if not text.lstrip().startswith("#"):
            return f"{SECTION_RISK}\n\n{text}"
        # Already has some heading — normalize later.
        return text
    return f"{SECTION_RISK}\n\n{text}"
