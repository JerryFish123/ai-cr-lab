"""Parse PR/MR description for PRD attachment URLs and chapter intent."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ![alt](url) images vs [text](url) files
_MD_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\((?P<url>https?://[^)\s]+)\)",
    re.IGNORECASE,
)
_MD_LINK_RE = re.compile(
    r"(?<!!)\[(?P<text>[^\]]*)\]\((?P<url>https?://[^)\s]+)\)",
    re.IGNORECASE,
)
_BARE_URL_RE = re.compile(r"(?P<url>https?://[^\s<>\"')\]]+)", re.IGNORECASE)

_DOC_EXT_RE = re.compile(r"\.(?:pdf|docx?)(?:\?|$|#)", re.IGNORECASE)
# Avoid \b around PRD: Python \w includes CJK, so「本期PRD」不会匹配 \bPRD\b
_DOC_IN_TEXT_RE = re.compile(
    r"(?:"
    r"\.pdf\b|\.docx?\b"
    r"|(?<![A-Za-z])PDF(?![A-Za-z])"
    r"|(?<![A-Za-z])DOCX?(?![A-Za-z])"
    r"|(?<![A-Za-z])PRD(?![A-Za-z])"
    r"|需求文档|产品需求|Word\s*文档|附件"
    r")",
    re.IGNORECASE,
)

_GITHUB_ATTACH_RE = re.compile(
    r"https?://(?:www\.)?github\.com/user-attachments/(?:assets|files)/[^\s<>\"')\]]+",
    re.IGNORECASE,
)

# Loose chapter mentions: 3.2 / 第3.2节 / §4.1 / 章节 1.2
_CHAPTER_RE = re.compile(
    r"(?:"
    r"第\s*\d+(?:\.\d+)+\s*节"
    r"|§\s*\d+(?:\.\d+)*"
    r"|章节\s*\d+(?:\.\d+)*"
    r"|(?:对照|范围|改造|涉及|本期).{0,40}?\d+\.\d+"
    r"|\b\d+\.\d+(?:\.\d+)*\b"
    r")",
    re.IGNORECASE,
)

_PRD_HINT_RE = re.compile(
    r"(?<![A-Za-z])PRD(?![A-Za-z])|需求文档|产品需求|\.pdf\b|\.docx?\b|(?<![A-Za-z])PDF(?![A-Za-z])|Word",
    re.IGNORECASE,
)


@dataclass
class PrdIntent:
    """Parsed intent from PR description — no rigid template required."""

    raw_body: str
    attachment_urls: list[str] = field(default_factory=list)
    chapter_hints: list[str] = field(default_factory=list)
    has_chapter_intent: bool = False
    has_prd_hint: bool = False

    @property
    def should_run_requirement_review(self) -> bool:
        """Trigger only when a PRD file link is present in the description."""
        return bool(self.attachment_urls)

    @property
    def primary_url(self) -> str | None:
        if not self.attachment_urls:
            return None
        for url in self.attachment_urls:
            if "prd" in url.lower():
                return url
        return self.attachment_urls[0]


def _normalize_url(url: str) -> str:
    return url.rstrip(").,;\"'")


def _is_github_attachment(url: str) -> bool:
    return bool(_GITHUB_ATTACH_RE.match(url) or "user-attachments/" in url.lower())


def _link_text_suggests_document(link_text: str) -> bool:
    t = (link_text or "").strip()
    if not t:
        return False
    if _DOC_EXT_RE.search(t):
        return True
    if _DOC_IN_TEXT_RE.search(t):
        return True
    return False


def _is_prd_candidate(
    url: str,
    *,
    link_text: str = "",
    body_has_prd_hint: bool = False,
    body_has_chapter_intent: bool = False,
) -> bool:
    """Decide whether a URL looks like a PRD/document attachment."""
    u = _normalize_url(url)
    if not u:
        return False
    if _DOC_EXT_RE.search(u):
        return True
    if _link_text_suggests_document(link_text):
        # Prefer GitHub attachments; also allow any URL if text clearly says .pdf/.prd
        if (
            _is_github_attachment(u)
            or _DOC_EXT_RE.search(link_text)
            or re.search(r"(?<![A-Za-z])PRD(?![A-Za-z])", link_text, re.I)
        ):
            return True
    # Modern GitHub: user-attachments/assets/<uuid> has no extension.
    # Accept when description signals PRD/PDF/Word OR chapter scope (product path).
    if _is_github_attachment(u) and (body_has_prd_hint or body_has_chapter_intent):
        return True
    return False


def parse_prd_intent(body: str | None) -> PrdIntent:
    """Extract attachment URLs and chapter-like hints from natural-language body."""
    text = (body or "").strip()
    if not text:
        return PrdIntent(raw_body="")

    body_has_prd_hint = bool(_PRD_HINT_RE.search(text))
    chapters = [m.group(0).strip() for m in _CHAPTER_RE.finditer(text)]
    chapter_hints: list[str] = []
    ch_seen: set[str] = set()
    for c in chapters:
        if c not in ch_seen:
            ch_seen.add(c)
            chapter_hints.append(c)
    body_has_chapter_intent = bool(chapter_hints)

    image_urls = {_normalize_url(m.group("url")) for m in _MD_IMAGE_RE.finditer(text)}

    urls: list[str] = []
    seen: set[str] = set()

    def _add(url: str, link_text: str = "", *, from_image_blacklist: bool = False) -> None:
        u = _normalize_url(url)
        if not u or u in seen:
            return
        # Image markdown URLs are skipped for bare-url pickup; explicit file links may override.
        if from_image_blacklist and u in image_urls and not _link_text_suggests_document(link_text):
            return
        if not _is_prd_candidate(
            u,
            link_text=link_text,
            body_has_prd_hint=body_has_prd_hint,
            body_has_chapter_intent=body_has_chapter_intent,
        ):
            return
        seen.add(u)
        urls.append(u)

    for m in _MD_LINK_RE.finditer(text):
        _add(m.group("url"), link_text=m.group("text") or "", from_image_blacklist=False)

    for m in _BARE_URL_RE.finditer(text):
        _add(m.group("url"), link_text="", from_image_blacklist=True)

    # Prefer paths/names that look like PRD or have extensions
    urls.sort(
        key=lambda u: (
            0 if "prd" in u.lower() else 1,
            0 if _DOC_EXT_RE.search(u) else 1,
        )
    )

    return PrdIntent(
        raw_body=text,
        attachment_urls=urls,
        chapter_hints=chapter_hints[:20],
        has_chapter_intent=body_has_chapter_intent,
        has_prd_hint=body_has_prd_hint,
    )


def extract_description_body(webhook_data: dict) -> str:
    """Pull PR/MR description from common webhook shapes."""
    if not webhook_data:
        return ""
    pr = webhook_data.get("pull_request") or {}
    if isinstance(pr, dict) and pr.get("body"):
        return str(pr.get("body") or "")
    attrs = webhook_data.get("object_attributes") or {}
    if isinstance(attrs, dict) and attrs.get("description"):
        return str(attrs.get("description") or "")
    return ""
