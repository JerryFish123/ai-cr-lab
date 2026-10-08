"""Synthetic review logs for dashboard demos — never reads/writes MySQL."""
from __future__ import annotations

import datetime
import random

import pandas as pd

from biz.utils.review_report_format import normalize_triple_report

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
    "yuki.tanaka",
    "maria.garcia",
    "chen.wei",
    "priya.sharma",
    "lucas.mueller",
    "alex.kim",
    "fatima.alhassan",
    "jean.dubois",
    "minseo.park",
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


def _legacy_report(rng: random.Random, stack: str) -> str:
    issues = [
        "未关闭的 JDBC 连接可能导致连接池耗尽",
        "前端 bundle 体积超 500KB，建议 lazy-load",
        "缺少对 /api/v2 的集成测试",
        "日志中打印了 partial token",
    ]
    score = rng.randint(62, 92)
    picked = rng.sample(issues, k=rng.randint(1, 3))
    body = "\n".join(f"- {x}" for x in picked)
    return f"### 严重问题\n{body}\n\n### 中等问题\n- 建议补充 README 变更说明\n\n总分:{score}分"


def _with_prd_report(rng: random.Random, stack: str, topic: str) -> str:
    uncovered = rng.choice(
        [
            f"- PRD 3.{rng.randint(1,4)} {topic} 未覆盖（缺少 {rng.choice(_MARKETS)} 文案校验）",
            "- 部分覆盖：导出 Excel 列宽与 PRD 不一致",
            "- 已覆盖：列表筛选与 PRD 一致\n- 未覆盖：批量操作二次确认弹窗",
        ]
    )
    blast = rng.choice(
        [
            "- 波及旧版结算回调，需回归 payment notify",
            "- 未发现",
            "- 波及权限中心 role cache 刷新逻辑",
            "- 可能影响 datenpipeline-etl-py 下游字段映射",
        ]
    )
    risk = rng.choice(
        [
            "- SQL 拼接存在注入风险，请改用 PreparedStatement / 参数化",
            "- 未发现明显安全或性能风险",
            "- 接口无限流，存在被刷风险",
            "- 硬编码 API Key，建议迁移至密钥管理",
            "- N+1 查询，分页接口 P99 可能劣化",
        ]
    )
    raw = f"""### 1. PRD 覆盖情况
{uncovered}
### 2. 非 PRD 范围的潜在波及
{blast}
### 3. 安全与性能风险
{risk}"""
    return normalize_triple_report(raw, has_prd=True)


def _no_prd_report(rng: random.Random, stack: str) -> str:
    risk = rng.choice(
        [
            "- 未发现明显安全或性能风险",
            "- 缺少输入长度校验，可能导致 DoS",
            "- 敏感字段未脱敏写入日志",
        ]
    )
    return normalize_triple_report("", has_prd=False, risk_section=risk)


def _review_for_kind(rng: random.Random, kind: str, stack: str, topic: str) -> str:
    if kind == "legacy":
        return _legacy_report(rng, stack)
    if kind == "with_prd":
        return _with_prd_report(rng, stack, topic)
    return _no_prd_report(rng, stack)


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
                "review_result": _review_for_kind(rng, kind, stack, topic),
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
        branch = rng.choice(_PUSH_BRANCHES)
        kind = _kind_roll(rng)
        adds, dels = _lines_for_stack(rng, stack)
        msg = f"push: {rng.choice(_COMMIT_MSGS).format(topic=topic, market=rng.choice(_MARKETS), scope='push')}"
        rows.append(
            {
                "project_name": name,
                "author": author,
                "branch": branch,
                "updated_at": _rand_ts(rng, _MOCK_START, _MOCK_END),
                "commit_messages": msg,
                "score": rng.randint(0, 100) if kind == "legacy" else None,
                "review_result": _review_for_kind(rng, kind, stack, topic),
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
