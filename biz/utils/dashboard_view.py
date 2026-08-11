"""Dashboard helpers: classify / summarize / enrich review rows for Streamlit UI."""
from __future__ import annotations

import re
from typing import Literal

import pandas as pd

from biz.utils.review_report_format import (
    PRD_MISSING_MESSAGE,
    _SECTION1_RE,
    _SECTION2_RE,
    _SECTION3_RE,
    _extract_section_body,
)

ReviewKind = Literal["no_prd", "with_prd", "legacy"]

KIND_LABELS: dict[ReviewKind, str] = {
    "no_prd": "无PRD",
    "with_prd": "有PRD",
    "legacy": "旧格式",
}

_BULLET_RE = re.compile(r"^\s*[-*•]\s+(.+)$")
_NO_FINDING_RE = re.compile(r"未发现|无未覆盖|无明显")


def classify_review(text: str | None) -> ReviewKind:
    """Classify a stored review_result for dashboard metrics/filters."""
    t = (text or "").strip()
    if not t:
        return "legacy"
    if PRD_MISSING_MESSAGE in t or "PRD解析失败" in t:
        return "no_prd"
    if "PRD 覆盖情况" in t or "PRD覆盖情况" in t:
        return "with_prd"
    return "legacy"


def _count_finding_bullets(section: str) -> int:
    n = 0
    for raw in (section or "").splitlines():
        m = _BULLET_RE.match(raw)
        if not m:
            continue
        body = m.group(1).strip()
        if not body or _NO_FINDING_RE.search(body):
            continue
        # Skip section labels that are not findings
        if body.startswith("**未覆盖") or body.startswith("**已覆盖"):
            continue
        n += 1
    return n


def _risk_bullet_count(text: str) -> int:
    risk = _extract_section_body(text, _SECTION3_RE, [])
    if not risk:
        # Legacy reports may list risks without section heading
        if classify_review(text) == "legacy":
            return 0
        return 0
    return _count_finding_bullets(risk)


def has_risk(text: str | None) -> bool:
    """True when risk section has at least one concrete finding."""
    t = (text or "").strip()
    if not t:
        return False
    return _risk_bullet_count(t) > 0


def summarize_review_for_table(review_result: str | None, max_len: int = 80) -> str:
    """Short summary aligned with classify_review kinds."""
    text = (review_result or "").strip()
    if not text:
        return "—"

    kind = classify_review(text)
    if kind == "legacy":
        return "旧格式报告"[:max_len]

    risks = _risk_bullet_count(text)
    if kind == "no_prd":
        if risks:
            return f"无PRD · 风险{min(risks, 9)}项"[:max_len]
        return "无PRD · 无明显风险"[:max_len]

    s1 = _extract_section_body(text, _SECTION1_RE, [_SECTION2_RE, _SECTION3_RE])
    s2 = _extract_section_body(text, _SECTION2_RE, [_SECTION3_RE])
    uncovered = _count_finding_bullets(s1)
    # Prefer counting bullets under 未覆盖 emphasis when present
    if "未覆盖" in s1:
        uncovered_lines = [
            ln
            for ln in s1.splitlines()
            if _BULLET_RE.match(ln)
            and "无未覆盖" not in ln
            and "未发现" not in ln
            and ("未覆盖" in ln or "未完成" in ln or "缺失" in ln or "未实现" in ln or "部分覆盖" in ln)
        ]
        # If explicit uncovered bullets exist use them; else keep general finding count
        if uncovered_lines:
            uncovered = len(uncovered_lines)
    blast = _count_finding_bullets(s2)
    return f"未覆盖{uncovered} · 波及{blast} · 风险{risks}"[:max_len]


def count_prd_reviews(series_or_list) -> int:
    """Count rows classified as with_prd (same source as table kind)."""
    n = 0
    for val in series_or_list:
        if classify_review(str(val or "")) == "with_prd":
            n += 1
    return n


def enrich_review_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Add kind / kind_label / summary / has_risk columns from review_result."""
    out = df.copy()
    if out.empty:
        out["kind"] = pd.Series(dtype=object)
        out["kind_label"] = pd.Series(dtype=object)
        out["summary"] = pd.Series(dtype=object)
        out["has_risk"] = pd.Series(dtype=bool)
        return out

    if "review_result" not in out.columns:
        out["kind"] = "legacy"
        out["kind_label"] = KIND_LABELS["legacy"]
        out["summary"] = "—"
        out["has_risk"] = False
        return out

    texts = out["review_result"].fillna("").astype(str)
    out["kind"] = texts.map(classify_review)
    out["kind_label"] = out["kind"].map(lambda k: KIND_LABELS.get(k, "旧格式"))
    out["summary"] = texts.map(summarize_review_for_table)
    out["has_risk"] = texts.map(has_risk)
    return out


def filter_enriched_frame(
    df: pd.DataFrame,
    *,
    authors: list | None = None,
    project_names: list | None = None,
    prd_filter: str = "全部",
    risk_filter: str = "全部",
) -> pd.DataFrame:
    """Apply local filters on an already date-scoped enriched frame."""
    if df.empty:
        return df
    out = df
    if authors:
        out = out[out["author"].isin(authors)]
    if project_names:
        out = out[out["project_name"].isin(project_names)]
    if prd_filter == "含PRD":
        out = out[out["kind"] == "with_prd"]
    elif prd_filter == "无PRD":
        out = out[out["kind"] == "no_prd"]
    elif prd_filter == "旧格式":
        out = out[out["kind"] == "legacy"]
    if risk_filter == "有风险":
        out = out[out["has_risk"] == True]  # noqa: E712
    elif risk_filter == "无明显风险":
        out = out[out["has_risk"] == False]  # noqa: E712
    return out.reset_index(drop=True)
