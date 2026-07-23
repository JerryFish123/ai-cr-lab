"""Orchestrate conditional「需求完成情况」comment after code-quality review."""
from __future__ import annotations

import os
from typing import Callable

from biz.agent.agentic_reviewer import AgenticReviewError
from biz.prd.description import extract_description_body, parse_prd_intent
from biz.prd.extract import resolve_and_extract_prd
from biz.prd.requirement_reviewer import RequirementReviewer
from biz.utils.log import logger

AddNotesFn = Callable[[str], None]


def format_prd_parse_failure(reason: str) -> str:
    return f"## 需求完成情况\n\n**PRD解析失败**\n\n原因：{reason}"


def format_requirement_header(body: str) -> str:
    return f"## 需求完成情况\n\n{body}"


def maybe_post_requirement_review(
    *,
    webhook_data: dict,
    access_token: str,
    changes: list,
    commits_text: str,
    add_notes: AddNotesFn,
    repo_url: str | None,
    repo_key: str | None,
    ref: str | None,
    description_body: str | None = None,
) -> str | None:
    """If PR description has a PRD attachment, post coverage analysis or parse failure.

    Returns the posted body (including header / failure text) for DingTalk digest,
    or None when requirement review is skipped.
    Soft failures become a PR comment; do not raise to the caller.
    """
    body = description_body if description_body is not None else extract_description_body(webhook_data)
    intent = parse_prd_intent(body)
    if not intent.should_run_requirement_review:
        logger.info("PRD requirement review skipped: no PRD attachment in description")
        return None

    url = intent.primary_url
    logger.info("PRD requirement review starting: url=%s chapters=%s", url, intent.chapter_hints)
    # Prefer Contents API / repo PRD fallback when github.com attachments time out.
    extracted = resolve_and_extract_prd(
        url or "",
        access_token,
        repo_key=repo_key,
        ref=ref,
    )
    if not extracted.ok:
        note = format_prd_parse_failure(extracted.reason or "未知原因")
        add_notes(note)
        return note

    if not (repo_url and repo_key and ref):
        note = format_prd_parse_failure("无法从 webhook 解析仓库地址/ref，无法进行需求覆盖探查")
        add_notes(note)
        return note

    cache_root = os.getenv("REPO_CACHE_DIR", "data/repo_cache")
    # Keep PRD text only for this review call; do not persist to disk.
    prd_text = extracted.text
    try:
        reviewer = RequirementReviewer(
            repo_url=repo_url,
            repo_key=repo_key,
            ref=ref,
            cache_root=cache_root,
        )
        report = reviewer.review_requirements(
            diffs_text=str(changes),
            commits_text=commits_text,
            prd_text=prd_text,
            description=intent.raw_body,
            chapter_hints=intent.chapter_hints,
        )
        note = format_requirement_header(report)
        add_notes(note)
        return note
    except AgenticReviewError as e:
        logger.error("prd requirement review agentic failed: %s", e)
        note = format_prd_parse_failure(f"需求覆盖分析失败（agentic）: {e}")
        add_notes(note)
        return note
    except Exception as e:  # noqa: BLE001
        logger.error("prd requirement review unexpected error: %s", e)
        note = format_prd_parse_failure(f"需求覆盖分析未预期异常: {type(e).__name__}: {e}")
        add_notes(note)
        return note
    finally:
        # Drop large string reference ASAP after review finishes.
        prd_text = ""
        extracted.text = ""
