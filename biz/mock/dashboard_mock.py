"""Synthetic review logs for dashboard demos — never reads/writes MySQL."""
from __future__ import annotations

import datetime
import random

import pandas as pd

from biz.mock.report_templates import build_review_report

# Project inception for ai-cr-lab ops (~first ECS deploy era)
_MOCK_START = datetime.datetime(2025, 8, 1, 9, 0, 0)
_MOCK_END = datetime.datetime(2026, 10, 8, 23, 59, 59)
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

AUTHORS = [
    "JerryFish123",
    "chen.wei",
    "wang.lei",
    "zhang.yimin",
    "liu.hao",
    "zhao.xin",
    "sun.qiang",
    "maria.garcia",
    "lucas.mueller",
    "priya.sharma",
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


def _ts(dt: datetime.datetime) -> int:
    return int(dt.timestamp())


def _rand_ts(rng: random.Random, start: datetime.datetime, end: datetime.datetime) -> int:
    delta = end - start
    sec = rng.randint(0, max(int(delta.total_seconds()), 1))
    return _ts(start + datetime.timedelta(seconds=sec))


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


def _build_mr_rows(rng: random.Random, n: int) -> list[dict]:
    rows: list[dict] = []
    pr_counter: dict[str, int] = {p["name"]: rng.randint(20, 80) for p in PROJECTS}
    for _ in range(n):
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
                "updated_at": _rand_ts(rng, _MOCK_START, _MOCK_END),
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


def _build_push_rows(rng: random.Random, n: int) -> list[dict]:
    rows: list[dict] = []
    for _ in range(n):
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
                "updated_at": _rand_ts(rng, _MOCK_START, _MOCK_END),
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
            rng = random.Random(_SEED)
            cls._mr_df = pd.DataFrame(_build_mr_rows(rng, 196))
        return cls._mr_df

    @classmethod
    def _all_push(cls) -> pd.DataFrame:
        if cls._push_df is None:
            rng = random.Random(_SEED + 1)
            cls._push_df = pd.DataFrame(_build_push_rows(rng, 58))
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
    def describe(cls) -> str:
        start = _MOCK_START.strftime("%Y-%m-%d")
        end = _MOCK_END.strftime("%Y-%m-%d")
        return (
            f"10 个项目（{cls.stack_summary()}）· {start} 至 {end} · "
            f"{len(cls._all_mr())} 条 MR · {len(cls._all_push())} 条 Push"
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
