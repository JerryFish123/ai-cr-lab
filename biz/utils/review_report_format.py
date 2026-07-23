"""Post-process review Markdown for PR comments / digests."""
from __future__ import annotations

import re

_SCORE_KEEP_RE = re.compile(r"总分|评分明细|得分|完成度")
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


def trim_quality_report_for_publish(text: str) -> str:
    """Drop medium/minor issue sections; keep severe findings and scores."""
    if not text:
        return text

    out: list[str] = []
    skipping = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if _MEDIUM_MINOR_HEADING_RE.match(line):
            skipping = True
            continue
        if skipping:
            if _SECTION_HEADING_RE.match(line) and not _MEDIUM_MINOR_HEADING_RE.match(line):
                skipping = False
            else:
                # Still allow score lines even if model nested them oddly.
                if _SCORE_KEEP_RE.search(line):
                    skipping = False
                    out.append(line)
                continue

        if _MEDIUM_MINOR_BULLET_RE.match(line) or _MEDIUM_MINOR_LABEL_RE.match(line):
            continue
        out.append(line)

    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def prioritize_uncovered_requirements(report: str) -> str:
    """Rewrite requirement report so uncovered items are first and emphasized."""
    text = (report or "").strip()
    if not text or "PRD解析失败" in text:
        return text

    uncovered: list[str] = []
    covered: list[str] = []
    other: list[str] = []
    completion = ""

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            # Drop old section headers; we rebuild structure.
            if any(k in stripped for k in ("未覆盖", "未完成", "已覆盖", "已完成", "需求完成")):
                continue
            other.append(stripped)
            continue
        if "完成度" in stripped:
            completion = stripped
            continue
        bullet = stripped
        if re.match(r"^[-*•]\s+", stripped):
            body = re.sub(r"^[-*•]\s+", "", stripped)
        else:
            body = stripped
        if any(k in body for k in ("未覆盖", "未完成", "缺失", "未实现", "部分覆盖")):
            uncovered.append(f"- {body}" if not body.startswith("-") else body)
        elif any(k in body for k in ("已覆盖", "已完成", "已实现")):
            covered.append(f"- {body}" if not body.startswith("-") else body)
        else:
            other.append(stripped)

    parts: list[str] = []
    if other:
        parts.extend(other)
        parts.append("")
    parts.append("### 未覆盖（重点）")
    if uncovered:
        parts.extend(uncovered)
    else:
        parts.append("- 无未覆盖项")
    parts.append("")
    parts.append("### 已覆盖")
    if covered:
        parts.extend(covered)
    else:
        parts.append("- （报告中未识别到已覆盖项）")
    if completion:
        parts.append("")
        parts.append(completion)
    return "\n".join(parts).strip()
