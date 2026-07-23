"""Concise DingTalk notifications for PR/MR review lifecycle."""
from __future__ import annotations

import math
import os
import re
from typing import Any

from biz.utils.im import notifier
from biz.utils.log import logger
from biz.utils.token_util import count_tokens, truncate_text_by_tokens

_RISK_KW_RE = re.compile(
    r"(风险|安全|漏洞|注入|XSS|CSRF|越权|崩溃|死循环|数据丢失|泄露|敏感|硬编码.?密钥|"
    r"SQL\s*注入|RCE|任意文件|未授权|鉴权缺失|race\s*condition|null\s*pointer|"
    r"security|vulnerab|exploit|credential|secret|token\s*leak)",
    re.IGNORECASE,
)
_SCORE_LINE_RE = re.compile(r"^\s*(总分|评分明细|得分)[:：].*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*•]\s+(.+)$", re.MULTILINE)


def estimate_review_minutes(file_count: int, has_prd: bool) -> tuple[int, int]:
    """Heuristic ETA in minutes: (low, high)."""
    files = max(0, int(file_count))
    base = 3.0 + min(files, 20) * 0.5
    if has_prd:
        base += 3.0
    lo = max(2, int(math.floor(base * 0.85)))
    hi = max(lo + 1, int(math.ceil(base * 1.25)))
    return lo, hi


def format_eta_text(file_count: int, has_prd: bool) -> str:
    lo, hi = estimate_review_minutes(file_count, has_prd)
    if lo == hi:
        return f"约 {lo} 分钟"
    return f"约 {lo}–{hi} 分钟"


def format_review_started_markdown(
    *,
    project_name: str,
    author: str,
    source_branch: str,
    target_branch: str,
    url: str,
    has_prd: bool,
    file_count: int,
) -> str:
    prd_label = "是" if has_prd else "否"
    eta = format_eta_text(file_count, has_prd)
    return (
        f"### 审查已开始\n\n"
        f"- **项目**: {project_name}\n"
        f"- **提交者**: {author}\n"
        f"- **分支**: `{source_branch}` → `{target_branch}`\n"
        f"- **是否携带 PRD 分析**: {prd_label}\n"
        f"- **预计耗时**: {eta}\n"
        f"- [打开 PR/MR]({url})\n"
    )


def format_review_finished_markdown(
    *,
    project_name: str,
    author: str,
    url: str,
    digest_body: str,
) -> str:
    body = (digest_body or "").strip() or "未发现严重问题"
    return (
        f"### 审查完成：{project_name}\n\n"
        f"- **提交者**: {author}\n"
        f"- [打开 PR/MR]({url})\n\n"
        f"{body}\n"
    )


def fallback_digest(quality_report: str, requirement_report: str | None) -> str:
    """Local fallback when LLM digest fails: keep risk-looking bullets only."""
    text = _SCORE_LINE_RE.sub("", quality_report or "")
    risks: list[str] = []
    for m in _BULLET_RE.finditer(text):
        line = m.group(1).strip()
        if _RISK_KW_RE.search(line):
            risks.append(f"- {line}")
    if not risks:
        # Also scan numbered / heading-ish lines containing risk keywords.
        for raw in text.splitlines():
            line = raw.strip().lstrip("#").strip()
            if not line or len(line) > 200:
                continue
            if _RISK_KW_RE.search(line) and "总分" not in line:
                risks.append(f"- {line}")
            if len(risks) >= 8:
                break

    parts: list[str] = []

    if requirement_report is not None:
        parts.append("#### 需求完成情况")
        if "PRD解析失败" in requirement_report:
            # Keep failure short.
            reason = requirement_report
            for marker in ("原因：", "原因:"):
                if marker in requirement_report:
                    reason = requirement_report.split(marker, 1)[-1].strip().splitlines()[0]
                    break
            parts.append(f"- PRD 解析失败：{reason[:200]}")
        else:
            done, todo = _split_requirement_lines(requirement_report)
            parts.append("**未覆盖（重点）**")
            parts.extend(todo or ["- 无未覆盖项"])
            parts.append("**已覆盖**")
            parts.extend((done or ["- （未能从报告中识别已覆盖项）"])[:3])
        parts.append("")

    parts.append("#### 潜在风险问题")
    if risks:
        parts.extend(risks[:8])
    else:
        parts.append("- 未发现严重问题")

    return "\n".join(parts)


def _split_requirement_lines(report: str) -> tuple[list[str], list[str]]:
    done: list[str] = []
    todo: list[str] = []
    for m in _BULLET_RE.finditer(report or ""):
        line = m.group(1).strip()
        low = line.lower()
        if any(k in line for k in ("未覆盖", "未完成", "缺失", "未实现", "部分覆盖")):
            todo.append(f"- {line}")
        elif any(k in line for k in ("已覆盖", "已完成", "已实现")) or "covered" in low:
            done.append(f"- {line}")
    return done[:10], todo[:10]


def build_dingtalk_digest(
    *,
    quality_report: str,
    requirement_report: str | None,
    has_prd: bool,
) -> str:
    """Produce a short DingTalk digest via LLM, with local fallback."""
    try:
        return _llm_digest(
            quality_report=quality_report,
            requirement_report=requirement_report,
            has_prd=has_prd,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("dingtalk digest LLM failed, using fallback: %s", e)
        return fallback_digest(quality_report, requirement_report if has_prd else None)


def _llm_digest(
    *,
    quality_report: str,
    requirement_report: str | None,
    has_prd: bool,
) -> str:
    from biz.agent.prompts import load_prompt
    from biz.llm.factory import Factory

    max_tokens = int(os.getenv("DINGTALK_DIGEST_MAX_TOKENS", "6000"))
    q = quality_report or ""
    r = requirement_report or ""
    if count_tokens(q) > max_tokens:
        q = truncate_text_by_tokens(q, max_tokens)
    if r and count_tokens(r) > max_tokens // 2:
        r = truncate_text_by_tokens(r, max_tokens // 2)

    prompts = load_prompt("dingtalk_review_digest_prompt", os.getenv("REVIEW_STYLE", "professional"))
    user_content = prompts["user_message"]["content"].format(
        has_prd="是" if has_prd else "否",
        quality_report=q,
        requirement_report=r if has_prd else "（本次无 PRD 分析）",
    )
    client = Factory().getClient()
    result = client.completions(
        messages=[
            prompts["system_message"],
            {"role": "user", "content": user_content},
        ]
    )
    text = (result or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    if not text or "总分" in text[:80]:
        # Guard against model ignoring instructions.
        return fallback_digest(quality_report, requirement_report if has_prd else None)
    # Drop medium/minor leftovers if the model ignored severity rules.
    from biz.utils.review_report_format import trim_quality_report_for_publish

    return trim_quality_report_for_publish(text)


def notify_review_started(
    *,
    project_name: str,
    author: str,
    source_branch: str,
    target_branch: str,
    url: str,
    has_prd: bool,
    file_count: int,
    url_slug: str | None = None,
    webhook_data: dict | None = None,
) -> None:
    content = format_review_started_markdown(
        project_name=project_name,
        author=author,
        source_branch=source_branch,
        target_branch=target_branch,
        url=url,
        has_prd=has_prd,
        file_count=file_count,
    )
    notifier.send_notification(
        content=content,
        msg_type="markdown",
        title=f"审查开始：{project_name}",
        project_name=project_name,
        url_slug=url_slug,
        webhook_data=webhook_data or {},
    )


def notify_review_finished(
    *,
    project_name: str,
    author: str,
    url: str,
    quality_report: str,
    requirement_report: str | None,
    has_prd: bool,
    url_slug: str | None = None,
    webhook_data: dict | None = None,
) -> None:
    digest = build_dingtalk_digest(
        quality_report=quality_report,
        requirement_report=requirement_report,
        has_prd=has_prd,
    )
    content = format_review_finished_markdown(
        project_name=project_name,
        author=author,
        url=url,
        digest_body=digest,
    )
    notifier.send_notification(
        content=content,
        msg_type="markdown",
        title=f"审查完成：{project_name}",
        project_name=project_name,
        url_slug=url_slug,
        webhook_data=webhook_data or {},
    )


def pr_meta_from_webhook(webhook_data: dict) -> dict[str, Any]:
    """Best-effort extract common PR/MR fields for notifications."""
    # GitHub / Gitea PR
    if "pull_request" in webhook_data:
        pr = webhook_data["pull_request"]
        repo = webhook_data.get("repository") or {}
        user = pr.get("user") or webhook_data.get("sender") or {}
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        return {
            "project_name": repo.get("name") or "",
            "author": user.get("login") or user.get("username") or "",
            "source_branch": head.get("ref") or pr.get("head_branch") or "",
            "target_branch": base.get("ref") or pr.get("base_branch") or "",
            "url": pr.get("html_url") or pr.get("url") or "",
        }
    # GitLab MR
    attrs = webhook_data.get("object_attributes") or {}
    project = webhook_data.get("project") or {}
    user = webhook_data.get("user") or {}
    return {
        "project_name": project.get("name") or "",
        "author": user.get("username") or user.get("name") or "",
        "source_branch": attrs.get("source_branch") or "",
        "target_branch": attrs.get("target_branch") or "",
        "url": attrs.get("url") or "",
    }
