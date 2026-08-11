"""Concise DingTalk notifications for PR/MR review lifecycle."""
from __future__ import annotations

import math
import os
import re
from typing import Any

from biz.utils.im import notifier
from biz.utils.log import logger
from biz.utils.review_report_format import PRD_MISSING_MESSAGE
from biz.utils.token_util import count_tokens, truncate_text_by_tokens

_RISK_KW_RE = re.compile(
    r"(风险|安全|漏洞|注入|XSS|CSRF|越权|崩溃|死循环|数据丢失|泄露|敏感|硬编码.?密钥|"
    r"SQL\s*注入|RCE|任意文件|未授权|鉴权缺失|race\s*condition|null\s*pointer|"
    r"security|vulnerab|exploit|credential|secret|token\s*leak)",
    re.IGNORECASE,
)
_SCORE_LINE_RE = re.compile(r"^\s*(总分|评分明细|得分)[:：].*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*•]\s+(.+)$", re.MULTILINE)
_SECTION1_RE = re.compile(r"#{1,4}\s*1\.\s*PRD\s*覆盖", re.I)
_SECTION2_RE = re.compile(r"#{1,4}\s*2\.\s*非\s*PRD|#{1,4}\s*2\.\s*.*波及", re.I)
_SECTION3_RE = re.compile(r"#{1,4}\s*3\.\s*安全与性能|#{1,4}\s*安全与性能风险", re.I)


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
    body = (digest_body or "").strip() or "未发现明显安全或性能风险"
    return (
        f"### 审查完成：{project_name}\n\n"
        f"- **提交者**: {author}\n"
        f"- [打开 PR/MR]({url})\n\n"
        f"{body}\n"
    )


def _extract_section(text: str, start_pat: re.Pattern, next_pats: list[re.Pattern]) -> str:
    m = start_pat.search(text or "")
    if not m:
        return ""
    start = m.end()
    end = len(text)
    for np in next_pats:
        nm = np.search(text, start)
        if nm:
            end = min(end, nm.start())
    return text[start:end].strip()


def _bullets(section: str, limit: int = 5) -> list[str]:
    items = [f"- {m.group(1).strip()}" for m in _BULLET_RE.finditer(section or "")]
    return items[:limit]


def fallback_digest(quality_report: str, requirement_report: str | None = None) -> str:
    """Local fallback: three-section short digest from the full triple report."""
    text = _SCORE_LINE_RE.sub("", quality_report or "")
    has_missing = PRD_MISSING_MESSAGE in text or (requirement_report and "PRD解析失败" in requirement_report)

    s1 = _extract_section(text, _SECTION1_RE, [_SECTION2_RE, _SECTION3_RE])
    s2 = _extract_section(text, _SECTION2_RE, [_SECTION3_RE])
    s3 = _extract_section(text, _SECTION3_RE, [])

    parts: list[str] = ["#### 1. PRD 覆盖"]
    if has_missing or (not s1 and PRD_MISSING_MESSAGE in text):
        if requirement_report and "PRD解析失败" in requirement_report:
            reason = requirement_report
            for marker in ("原因：", "原因:"):
                if marker in requirement_report:
                    reason = requirement_report.split(marker, 1)[-1].strip().splitlines()[0]
                    break
            parts.append(f"- PRD解析失败：{reason[:200]}")
        else:
            parts.append(f"- {PRD_MISSING_MESSAGE}")
    else:
        uncovered = [
            ln
            for ln in _bullets(s1, 8)
            if "未覆盖" in ln or "未完成" in ln or "缺失" in ln or "未实现" in ln
        ]
        if not uncovered:
            # Prefer any bullets that are not "无未覆盖"
            uncovered = [ln for ln in _bullets(s1, 5) if "无未覆盖" not in ln][:5]
        parts.extend(uncovered or ["- 无未覆盖项"])

    parts.append("")
    parts.append("#### 2. 非PRD波及")
    if has_missing:
        parts.append(f"- {PRD_MISSING_MESSAGE}")
    else:
        blast = [ln for ln in _bullets(s2, 5) if "未发现" not in ln]
        parts.extend(blast or ["- 未发现"])

    parts.append("")
    parts.append("#### 3. 安全与性能风险")
    risk_src = s3 or text
    risks = []
    for m in _BULLET_RE.finditer(risk_src):
        line = m.group(1).strip()
        if "未发现" in line and "风险" in line:
            continue
        if _RISK_KW_RE.search(line) or s3:
            if "未发现" in line:
                continue
            risks.append(f"- {line}")
        if len(risks) >= 5:
            break
    if not risks and s3:
        risks = [ln for ln in _bullets(s3, 5) if "未发现" not in ln]
    if not risks:
        # Legacy: scan whole text for risk keywords
        for m in _BULLET_RE.finditer(text):
            line = m.group(1).strip()
            if _RISK_KW_RE.search(line):
                risks.append(f"- {line}")
            if len(risks) >= 5:
                break
    parts.extend(risks or ["- 未发现明显安全或性能风险"])
    return "\n".join(parts)


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
        return fallback_digest(quality_report, requirement_report if has_prd else None)
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
