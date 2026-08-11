"""Post-process review Markdown for PR comments / digests."""
from __future__ import annotations

import re

PRD_MISSING_MESSAGE = "PRD缺失无法结合业务分析代码"

_MEDIUM_MINOR_HEADING_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*.*(🟡|🟢|中等问题|轻微问题|优化建议).*$",
    re.IGNORECASE,
)
_MEDIUM_MINOR_BULLET_RE = re.compile(
    r"^\s*[-*•]\s*(?:🟡|🟢)\s*",
)
_MEDIUM_MINOR_LABEL_RE = re.compile(
    r"^\s*[-*•]\s*.*(?:🟡|🟢|中等问题|轻微问题)\s*[:：]?",
    re.IGNORECASE,
)
_SECTION_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_SCORE_LINE_RE = re.compile(r"^\s*(总分|评分明细|得分)\s*[:：].*$")

_SECTION1_RE = re.compile(r"#{1,4}\s*1\.\s*PRD\s*覆盖", re.I)
_SECTION2_RE = re.compile(r"#{1,4}\s*2\.\s*非\s*PRD|#{1,4}\s*2\.\s*.*波及", re.I)
_SECTION3_RE = re.compile(r"#{1,4}\s*3\.\s*安全与性能|#{1,4}\s*安全与性能风险", re.I)


def looks_like_triple_report(text: str | None) -> bool:
    """True if report has the three required section markers (or risk + coverage)."""
    if not text or not text.strip():
        return False
    t = text.strip()
    if "总分" in t[:200] and "PRD" not in t[:400]:
        # Old scored-only dumps without triple structure.
        pass
    has1 = bool(_SECTION1_RE.search(t) or "PRD 覆盖" in t or "PRD覆盖" in t)
    has2 = bool(_SECTION2_RE.search(t) or "潜在波及" in t or "非 PRD" in t)
    has3 = bool(_SECTION3_RE.search(t) or "安全与性能" in t)
    return has1 and has2 and has3


def trim_quality_report_for_publish(text: str) -> str:
    """Drop medium/minor issue sections and score lines."""
    if not text:
        return text

    out: list[str] = []
    skipping = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if _SCORE_LINE_RE.match(line):
            continue
        if _MEDIUM_MINOR_HEADING_RE.match(line):
            skipping = True
            continue
        if skipping:
            if _SECTION_HEADING_RE.match(line) and not _MEDIUM_MINOR_HEADING_RE.match(line):
                skipping = False
            else:
                continue

        if _MEDIUM_MINOR_BULLET_RE.match(line) or _MEDIUM_MINOR_LABEL_RE.match(line):
            continue
        out.append(line)

    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _extract_section_body(text: str, start_pat: re.Pattern, next_pats: list[re.Pattern]) -> str:
    m = start_pat.search(text)
    if not m:
        return ""
    start = m.end()
    end = len(text)
    for np in next_pats:
        nm = np.search(text, start)
        if nm:
            end = min(end, nm.start())
    return text[start:end].strip()


def normalize_triple_report(
    raw: str,
    *,
    has_prd: bool,
    missing_message: str | None = None,
    risk_section: str | None = None,
) -> str:
    """Ensure a single well-formed three-section report."""
    miss = missing_message or PRD_MISSING_MESSAGE
    text = trim_quality_report_for_publish(raw or "")

    if not has_prd:
        risk = risk_section or _extract_section_body(
            text, _SECTION3_RE, []
        ) or text
        risk = risk.strip()
        if risk and not risk.lstrip().startswith("#"):
            risk_block = f"### 3. 安全与性能风险\n\n{risk}"
        elif risk:
            # Strip leading title variants then re-add canonical
            risk_body = _SECTION3_RE.sub("", risk, count=1).strip()
            risk_block = f"### 3. 安全与性能风险\n\n{risk_body or '- 未发现明显安全或性能风险'}"
        else:
            risk_block = "### 3. 安全与性能风险\n\n- 未发现明显安全或性能风险"
        return (
            "## AI 代码审查\n\n"
            f"### 1. PRD 覆盖情况\n\n{miss}\n\n"
            f"### 2. 非 PRD 范围的潜在波及\n\n{miss}\n\n"
            f"{risk_block}"
        ).strip()

    # has_prd: prefer model structure, fill gaps
    s1 = _extract_section_body(text, _SECTION1_RE, [_SECTION2_RE, _SECTION3_RE])
    s2 = _extract_section_body(text, _SECTION2_RE, [_SECTION3_RE])
    s3 = _extract_section_body(text, _SECTION3_RE, [])

    if not s1 and not s2 and not s3:
        # Model ignored structure — keep whole text under coverage, empty blast, empty risk note
        s1 = text or "- （未能解析覆盖结论）"
        s2 = "- 未发现"
        s3 = "- 未发现明显安全或性能风险"
    else:
        s1 = s1 or "- （未能识别覆盖结论）"
        s2 = s2 or "- 未发现"
        s3 = s3 or "- 未发现明显安全或性能风险"

    # Uncovered emphasis: if model listed 未覆盖 items, leave as-is
    return (
        "## AI 代码审查\n\n"
        f"### 1. PRD 覆盖情况\n\n{s1}\n\n"
        f"### 2. 非 PRD 范围的潜在波及\n\n{s2}\n\n"
        f"### 3. 安全与性能风险\n\n{s3}"
    ).strip()


def summarize_review_for_table(review_result: str, max_len: int = 80) -> str:
    """Short summary for dashboard table."""
    text = (review_result or "").strip()
    if not text:
        return "—"
    if PRD_MISSING_MESSAGE in text:
        risk = _extract_section_body(text, _SECTION3_RE, [])
        bullets = re.findall(r"^\s*[-*•]\s+(.+)$", risk, re.M)
        if bullets and "未发现" not in bullets[0]:
            return f"无PRD · 风险{min(len(bullets), 9)}项"[:max_len]
        return "无PRD · 仅风险评价"
    uncovered = 0
    if "未覆盖" in text:
        sec = _extract_section_body(text, _SECTION1_RE, [_SECTION2_RE, _SECTION3_RE])
        uncovered = len(
            [
                ln
                for ln in sec.splitlines()
                if re.match(r"^\s*[-*•]\s+", ln)
                and "无未覆盖" not in ln
                and "未发现" not in ln
            ]
        )
    risk_sec = _extract_section_body(text, _SECTION3_RE, [])
    risks = len(
        [
            ln
            for ln in risk_sec.splitlines()
            if re.match(r"^\s*[-*•]\s+", ln) and "未发现" not in ln
        ]
    )
    return f"未覆盖{uncovered} · 风险{risks}"[:max_len]


def count_prd_reviews(series_or_list) -> int:
    """Count rows whose review_result looks like a PRD-backed triple review."""
    n = 0
    for val in series_or_list:
        text = str(val or "")
        if not text:
            continue
        if PRD_MISSING_MESSAGE in text:
            continue
        if "PRD 覆盖情况" in text or "PRD覆盖情况" in text:
            n += 1
    return n


def prioritize_uncovered_requirements(report: str) -> str:
    """Legacy helper for prd.pipeline; prefer normalize_triple_report for new path."""
    text = (report or "").strip()
    if not text or "PRD解析失败" in text:
        return text

    bullets = re.findall(r"^\s*[-*•]\s+(.+)$", text, re.M)
    uncovered: list[str] = []
    covered: list[str] = []
    for line in bullets:
        if any(k in line for k in ("未覆盖", "未完成", "缺失", "未实现", "部分覆盖")):
            uncovered.append(f"- {line}")
        elif any(k in line for k in ("已覆盖", "已完成", "已实现")):
            covered.append(f"- {line}")

    # Also catch non-bullet lines like "章节 3.2 已覆盖"
    if not covered and not uncovered:
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("完成度"):
                continue
            if any(k in line for k in ("未覆盖", "未完成", "缺失", "未实现", "部分覆盖")):
                uncovered.append(f"- {line.lstrip('-*• ').strip()}")
            elif any(k in line for k in ("已覆盖", "已完成", "已实现")):
                covered.append(f"- {line.lstrip('-*• ').strip()}")

    footer_lines = [
        ln for ln in text.splitlines()
        if ln.strip().startswith("完成度") or ln.strip().startswith("建议")
    ]
    parts = [
        "### 未覆盖（重点）",
        *(uncovered or ["- 无未覆盖项"]),
        "",
        "### 已覆盖",
        *(covered or ["- （未能从报告中识别已覆盖项）"]),
    ]
    if footer_lines:
        parts.append("")
        parts.extend(footer_lines)
    return "\n".join(parts)
