"""Synthetic review logs for dashboard demos — never reads/writes MySQL."""
from __future__ import annotations

import datetime
import random

import pandas as pd

from biz.mock.report_templates import build_review_report

# Project inception for ai-cr-lab ops (~first ECS deploy era)
_MOCK_START = datetime.datetime(2025, 8, 1, 9, 0, 0)
# Fixed day grid for timestamp slots — generation never depends on "today"
_SLOT_LAST_DATE = datetime.date(2026, 10, 8)
_SLOT_SPAN_DAYS = (_SLOT_LAST_DATE - _MOCK_START.date()).days
_SEED = 20250801

# 10 repos: 前端3 · 测试2 · Java3 · Python2 — multilingual slugs / labels
PROJECTS: list[dict] = [
    {"name": "merchant-console-web", "stack": "frontend", "weight": 14, "org": "JerryFish123"},
    {"name": "i18n-design-system", "stack": "frontend", "weight": 11, "org": "JerryFish123"},
    {"name": "checkout-micro-ui", "stack": "frontend", "weight": 10, "org": "JerryFish123"},
    {"name": "ai-cr-test1", "stack": "test", "weight": 8, "org": "JerryFish123"},
    {"name": "ai-cr-test2", "stack": "test", "weight": 7, "org": "JerryFish123"},
    {"name": "pedido-core-java", "stack": "java", "weight": 16, "org": "JerryFish123"},
    {"name": "zahlung-gateway-java", "stack": "java", "weight": 15, "org": "JerryFish123"},
    {"name": "inventaire-api-java", "stack": "java", "weight": 13, "org": "JerryFish123"},
    {"name": "reco-ranking-py", "stack": "python", "weight": 12, "org": "JerryFish123"},
    {"name": "datenpipeline-etl-py", "stack": "python", "weight": 11, "org": "JerryFish123"},
]

# GitHub-style handles: Name + noun/animal + digits (same vibe as JerryFish123)
AUTHORS = [
    "JerryFish123",
    "MikeCat88",
    "AmyCode42",
    "JackFox99",
    "LilyFish2024",
    "LukeBear17",
    "NinaWolf66",
    "OscarHawk007",
    "RubyDeer33",
    "TonyShark2025",
]

_MR_BRANCHES = [
    ("feat/{topic}", "main"),
    ("fix/{topic}", "main"),
    ("hotfix/{topic}", "release/1.x"),
    ("refactor/{topic}", "develop"),
    ("chore/i18n-{topic}", "main"),
]

_PUSH_BRANCHES = ["main", "develop", "release/2.1", "staging", "feat/quick-fix"]

_TOPICS = [
    "oauth-callback", "sku-query", "redis-cache", "invoice-pdf", "locale-fallback",
    "payment-webhook", "inventory-lock", "batch-export", "rate-limit", "dark-mode",
    "graphql-n+1", "kafka-retry", "csv-import", "role-matrix", "audit-log",
]

_COMMIT_MSGS = [
    "feat: add {topic} for {market} market",
    "fix({scope}): resolve {topic} regression",
    "refactor: extract {topic} module",
    "chore: i18n strings for {topic} (zh-CN, en-US, ja-JP)",
    "perf: optimize {topic} query path",
    "test: cover {topic} edge cases",
]

_MARKETS = ["zh-CN", "en-US", "ja-JP", "de-DE", "es-ES", "fr-FR", "ko-KR"]

_STREAM_MR = 0
_STREAM_PUSH = 1


def _mock_end_date() -> datetime.date:
    return datetime.date.today()


def _mock_start_ts() -> int:
    return int(_MOCK_START.timestamp())


def _mock_end_ts() -> int:
    end = datetime.datetime.combine(_mock_end_date(), datetime.time(23, 59, 59))
    return int(end.timestamp())


def _ts(dt: datetime.datetime) -> int:
    return int(dt.timestamp())


def _row_rng(index: int, stream: int) -> random.Random:
    """Per-row RNG: same index + stream always yields identical field values."""
    return random.Random(_SEED + stream * 10_000_000 + index)


def _slot_datetime(index: int, *, stream: int) -> datetime.datetime:
    """Deterministic timestamp from row index — independent of today's date."""
    span = max(_SLOT_SPAN_DAYS, 1)
    day_offset = (index * 17 + stream * 31) % (span + 1)
    seconds = (index * 3607 + stream * 521) % 86400
    day = _MOCK_START.date() + datetime.timedelta(days=day_offset)
    base = datetime.datetime.combine(day, datetime.time.min)
    return base + datetime.timedelta(seconds=seconds)


def _pick_weighted(rng: random.Random, items: list[dict]) -> dict:
    weights = [i["weight"] for i in items]
    return rng.choices(items, weights=weights, k=1)[0]


def _kind_roll(rng: random.Random) -> str:
    return rng.choices(["with_prd", "no_prd", "legacy"], weights=[42, 38, 20], k=1)[0]


def _lines_for_stack(rng: random.Random, stack: str) -> tuple[int, int]:
    if stack == "frontend":
        return rng.randint(20, 420), rng.randint(5, 180)
    if stack == "test":
        return rng.randint(10, 220), rng.randint(3, 90)
    if stack == "java":
        return rng.randint(40, 680), rng.randint(10, 320)
    return rng.randint(30, 520), rng.randint(8, 240)


def _build_mr_rows(n: int, *, stream: int = _STREAM_MR) -> list[dict]:
    rows: list[dict] = []
    pr_counter: dict[str, int] = {
        p["name"]: 20 + _row_rng(i, stream + 900).randint(0, 60) for i, p in enumerate(PROJECTS)
    }
    for i in range(n):
        rng = _row_rng(i, stream)
        proj = _pick_weighted(rng, PROJECTS)
        name = proj["name"]
        stack = proj["stack"]
        org = proj["org"]
        author = rng.choice(AUTHORS)
        topic = rng.choice(_TOPICS)
        market = rng.choice(_MARKETS)
        src_tpl, tgt = rng.choice(_MR_BRANCHES)
        source = src_tpl.format(topic=topic)
        pr_counter[name] += 1
        pr_num = pr_counter[name]
        kind = _kind_roll(rng)
        adds, dels = _lines_for_stack(rng, stack)
        msg = rng.choice(_COMMIT_MSGS).format(topic=topic, market=market, scope=name.split("-")[0])
        rows.append(
            {
                "project_name": name,
                "author": author,
                "source_branch": source,
                "target_branch": tgt,
                "updated_at": _ts(_slot_datetime(i, stream=stream)),
                "commit_messages": msg,
                "score": rng.randint(0, 100) if kind == "legacy" else None,
                "url": f"https://github.com/{org}/{name}/pull/{pr_num}",
                "review_result": build_review_report(
                    rng, kind, stack=stack, topic=topic, project_name=name, market=market
                ),
                "additions": adds,
                "deletions": dels,
            }
        )
    rows.sort(key=lambda r: r["updated_at"], reverse=True)
    return rows


def _build_push_rows(n: int, *, stream: int = _STREAM_PUSH) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        rng = _row_rng(i, stream)
        proj = _pick_weighted(rng, PROJECTS)
        name = proj["name"]
        stack = proj["stack"]
        author = rng.choice(AUTHORS)
        topic = rng.choice(_TOPICS)
        market = rng.choice(_MARKETS)
        branch = rng.choice(_PUSH_BRANCHES)
        kind = _kind_roll(rng)
        adds, dels = _lines_for_stack(rng, stack)
        msg = f"push: {rng.choice(_COMMIT_MSGS).format(topic=topic, market=market, scope='push')}"
        rows.append(
            {
                "project_name": name,
                "author": author,
                "branch": branch,
                "updated_at": _ts(_slot_datetime(i, stream=stream)),
                "commit_messages": msg,
                "score": rng.randint(0, 100) if kind == "legacy" else None,
                "review_result": build_review_report(
                    rng, kind, stack=stack, topic=topic, project_name=name, market=market
                ),
                "additions": adds,
                "deletions": dels,
            }
        )
    rows.sort(key=lambda r: r["updated_at"], reverse=True)
    return rows


def _filter_frame(
    df: pd.DataFrame,
    *,
    authors: list | None,
    project_names: list | None,
    updated_at_gte: int | None,
    updated_at_lte: int | None,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df
    # Mock data only exists between project inception and today (inclusive).
    out = out[(out["updated_at"] >= _mock_start_ts()) & (out["updated_at"] <= _mock_end_ts())]
    if authors:
        out = out[out["author"].isin(authors)]
    if project_names:
        out = out[out["project_name"].isin(project_names)]
    if updated_at_gte is not None:
        out = out[out["updated_at"] >= updated_at_gte]
    if updated_at_lte is not None:
        out = out[out["updated_at"] <= updated_at_lte]
    return out.reset_index(drop=True)


class DashboardMockProvider:
    """In-memory review log provider with the same query surface as ReviewService."""

    _mr_df: pd.DataFrame | None = None
    _push_df: pd.DataFrame | None = None

    @classmethod
    def reset_cache(cls) -> None:
        cls._mr_df = None
        cls._push_df = None

    @classmethod
    def _all_mr(cls) -> pd.DataFrame:
        if cls._mr_df is None:
            cls._mr_df = pd.DataFrame(_build_mr_rows(196, stream=_STREAM_MR))
        return cls._mr_df

    @classmethod
    def _all_push(cls) -> pd.DataFrame:
        if cls._push_df is None:
            cls._push_df = pd.DataFrame(_build_push_rows(58, stream=_STREAM_PUSH))
        return cls._push_df

    @classmethod
    def project_names(cls) -> list[str]:
        return [p["name"] for p in PROJECTS]

    @classmethod
    def stack_summary(cls) -> str:
        parts = ["前端×3", "测试×2", "Java×3", "Python×2"]
        return " · ".join(parts)

    @classmethod
    def default_start_date(cls) -> datetime.date:
        return _MOCK_START.date()

    @classmethod
    def default_end_date(cls) -> datetime.date:
        return _mock_end_date()

    @classmethod
    def describe(cls) -> str:
        start = _MOCK_START.strftime("%Y-%m-%d")
        end = _mock_end_date().strftime("%Y-%m-%d")
        visible_mr = len(
            cls.get_mr_review_logs(
                updated_at_gte=_mock_start_ts(),
                updated_at_lte=_mock_end_ts(),
            )
        )
        visible_push = len(
            cls.get_push_review_logs(
                updated_at_gte=_mock_start_ts(),
                updated_at_lte=_mock_end_ts(),
            )
        )
        return (
            f"10 个项目（{cls.stack_summary()}）· {start} 至 {end} · "
            f"{visible_mr} 条 MR · {visible_push} 条 Push"
        )

    @classmethod
    def get_mr_review_logs(
        cls,
        authors: list | None = None,
        project_names: list | None = None,
        updated_at_gte: int | None = None,
        updated_at_lte: int | None = None,
    ) -> pd.DataFrame:
        return _filter_frame(
            cls._all_mr(),
            authors=authors,
            project_names=project_names,
            updated_at_gte=updated_at_gte,
            updated_at_lte=updated_at_lte,
        )

    @classmethod
    def get_push_review_logs(
        cls,
        authors: list | None = None,
        project_names: list | None = None,
        updated_at_gte: int | None = None,
        updated_at_lte: int | None = None,
    ) -> pd.DataFrame:
        return _filter_frame(
            cls._all_push(),
            authors=authors,
            project_names=project_names,
            updated_at_gte=updated_at_gte,
            updated_at_lte=updated_at_lte,
        )
