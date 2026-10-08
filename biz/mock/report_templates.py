"""Rich, stack-aware mock review report bodies for dashboard demos."""
from __future__ import annotations

import random
import re

from biz.utils.review_report_format import normalize_triple_report

_MARKETS = ["zh-CN", "en-US", "ja-JP", "de-DE", "es-ES", "fr-FR", "ko-KR"]


def _topic_title(topic: str) -> str:
    return "".join(p.capitalize() for p in re.split(r"[-_]", topic))


def _pick_paths(rng: random.Random, stack: str, project: str, topic: str, n: int) -> list[str]:
    tt = _topic_title(topic)
    pkg = project.split("-")[0]
    pools: dict[str, list[str]] = {
        "frontend": [
            f"src/pages/{topic}/ListPage.tsx",
            f"src/components/{topic}/FilterBar.tsx",
            f"src/hooks/use{tt}.ts",
            f"src/api/{topic}Client.ts",
            f"src/locales/{topic}.json",
            "src/utils/request.ts",
        ],
        "java": [
            f"src/main/java/com/{pkg}/{tt}Controller.java",
            f"src/main/java/com/{pkg}/service/{tt}Service.java",
            f"src/main/java/com/{pkg}/repo/{tt}Repository.java",
            f"src/main/resources/mapper/{tt}Mapper.xml",
            f"src/test/java/com/{pkg}/{tt}ServiceTest.java",
        ],
        "python": [
            f"app/services/{topic}_service.py",
            f"app/api/routes/{topic}.py",
            f"app/models/{topic}.py",
            f"tests/test_{topic}.py",
            "app/core/cache.py",
        ],
        "test": [
            f"src/main/java/com/demo/{tt}Controller.java",
            f"src/main/java/com/demo/service/{tt}Service.java",
            f"src/test/java/com/demo/{tt}ApiTest.java",
            "src/main/resources/application.yml",
        ],
    }
    pool = pools.get(stack, pools["java"])
    return rng.sample(pool, k=min(n, len(pool)))


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {ln}" for ln in lines)


def build_with_prd_report(
    rng: random.Random,
    *,
    stack: str,
    topic: str,
    project_name: str,
    market: str,
) -> str:
    paths = _pick_paths(rng, stack, project_name, topic, 5)
    tt = _topic_title(topic)
    prd_sec = rng.randint(2, 5)

    covered_pool = [
        f"PRD {prd_sec}.{rng.randint(1,3)} 列表分页：`{paths[0]}` 已实现 page/size，与文档一致",
        f"PRD {prd_sec}.{rng.randint(1,3)} {tt} 查询：`{paths[1]}` 支持多条件组合筛选",
        f"PRD {prd_sec}.{rng.randint(1,3)} 错误码映射：`{paths[2]}` 返回结构与 PRD 错误码表一致",
        f"PRD {prd_sec}.{rng.randint(1,3)} 权限校验：接口已加 `@PreAuthorize` / RBAC 校验，符合 PRD 角色矩阵",
        f"PRD {prd_sec}.{rng.randint(1,3)} 审计日志：关键写操作写入 audit 表，字段与 PRD 对齐",
    ]
    uncovered_pool = [
        f"PRD {prd_sec}.{rng.randint(1,3)} 批量操作：`Batch{tt}Modal` 缺少二次确认弹窗（PRD 明确要求）",
        f"PRD {prd_sec}.{rng.randint(1,3)} 多语言：{market} / de-DE 文案仍为硬编码 fallback，未走 i18n 资源文件",
        f"PRD {prd_sec}.{rng.randint(1,3)} 导出 Excel：列宽、表头与 PRD 样例不一致（缺少「更新时间」列）",
        f"PRD {prd_sec}.{rng.randint(1,3)} 空态页：列表无数据时的引导文案与 PRD 3.x 不一致",
        f"PRD {prd_sec}.{rng.randint(1,3)} 超时重试：前端未实现 PRD 规定的 3 次指数退避",
    ]

    covered = rng.sample(covered_pool, k=rng.randint(2, 4))
    uncovered = rng.sample(uncovered_pool, k=rng.randint(1, 3))
    completion = rng.randint(68, 94)

    s1 = (
        "**已覆盖**\n"
        + _bullets(covered)
        + "\n\n**未覆盖 / 部分覆盖**\n"
        + _bullets(uncovered)
        + f"\n\n**完成度**：约 {completion}%（核心读写路径已覆盖，边缘验收项待补）"
    )

    blast_pool = [
        f"`PaymentNotifyListener` 与本 PR 共用 `HmacUtils`，需回归 payment notify 重放与签名校验",
        f"Redis cache key 由 `{topic}:` 调整为 `product:{topic}:`，可能影响下游库存服务缓存命中",
        f"`{paths[3]}` 变更了 DTO 字段名，datenpipeline-etl-py 同步任务需确认字段映射",
        f"权限中心 role cache 刷新逻辑与本 PR 共用 `RoleContextHolder`，需回归管理员场景",
        f"`{paths[4]}` 调整了全局异常处理，可能影响其他模块错误码输出",
        "未发现对鉴权链路或公共中间件的破坏性变更",
    ]
    blast = rng.sample(blast_pool, k=rng.randint(2, 4))
    if not any("未发现" in b for b in blast) and rng.random() < 0.35:
        blast.append("未发现其他模块的连锁影响")

    risk_pool = [
        f"**安全** · `{paths[1]}` 存在 SQL/查询拼接，建议改为参数化或 QueryDSL",
        f"**安全** · `{paths[0]}` 日志打印完整 request body（含 phone/email），建议脱敏",
        f"**安全** · `{paths[2]}` 硬编码 API Key / token，建议迁移至 KMS 或环境变量",
        f"**安全** · 新增接口未接入网关鉴权白名单，存在未授权访问风险",
        f"**性能** · `{paths[1]}` 循环内调用 repository，存在 N+1，P99 可能 +80~150ms",
        f"**性能** · `{paths[0]}` 导出/列表接口未限流，存在被刷风险",
        f"**性能** · `{paths[3]}` 大对象全量加载进内存，建议分页或流式处理",
        f"**性能** · Redis 未设置 TTL，热点 key 可能长期占用内存",
    ]
    risks = rng.sample(risk_pool, k=rng.randint(2, 5))

    raw = (
        f"### 1. PRD 覆盖情况\n\n{s1}\n\n"
        f"### 2. 非 PRD 范围的潜在波及\n\n{_bullets(blast)}\n\n"
        f"### 3. 安全与性能风险\n\n{_bullets(risks)}"
    )
    return normalize_triple_report(raw, has_prd=True)


def build_no_prd_report(rng: random.Random, *, stack: str, topic: str, project_name: str) -> str:
    paths = _pick_paths(rng, stack, project_name, topic, 4)
    risk_pool = [
        f"**安全** · `{paths[0]}` 缺少输入长度校验，超长 payload 可能导致 DoS",
        f"**安全** · `{paths[1]}` 异常栈直接返回客户端，可能泄露内部路径",
        f"**安全** · `{paths[2]}` 使用 `eval` / 动态拼接表达式，存在注入面",
        f"**性能** · `{paths[1]}` 同步调用外部 HTTP 未设超时，线程池可能被占满",
        f"**性能** · `{paths[3]}` 未建索引的模糊查询，数据量上升后全表扫描",
        "未发现明显安全或性能风险（变更集中在单元测试与文档）",
    ]
    risks = rng.sample(risk_pool, k=rng.randint(2, 4))
    return normalize_triple_report("", has_prd=False, risk_section=_bullets(risks))


def build_legacy_report(rng: random.Random, *, stack: str, topic: str, project_name: str) -> str:
    paths = _pick_paths(rng, stack, project_name, topic, 4)
    severe = [
        f"`{paths[0]}` 未关闭的连接/资源可能导致泄漏（连接池耗尽）",
        f"`{paths[1]}` 缺少空指针防护，边界条件下可能 NPE",
        f"`{paths[2]}` 并发场景下存在 check-then-act 竞态",
        f"`{paths[3]}` 敏感字段写入日志，不符合安全规范",
        "前端 bundle 体积 +420KB，建议路由级 code-splitting",
        "缺少对 `/api/v2/{topic}` 的集成测试覆盖",
    ]
    medium = [
        "建议补充 README / CHANGELOG 中的迁移说明",
        "魔法数字未提取常量，可读性一般",
        "部分方法超过 80 行，建议拆分",
    ]
    picked_s = rng.sample(severe, k=rng.randint(2, 4))
    picked_m = rng.sample(medium, k=rng.randint(1, 2))
    score = rng.randint(62, 88)
    return (
        f"### 严重问题\n{_bullets(picked_s)}\n\n"
        f"### 中等问题\n{_bullets(picked_m)}\n\n"
        f"### 轻微问题\n- 命名风格与仓库现有约定略有差异\n- 部分注释为 TODO，建议跟进\n\n"
        f"总分:{score}分"
    )


def build_review_report(
    rng: random.Random,
    kind: str,
    *,
    stack: str,
    topic: str,
    project_name: str,
    market: str,
) -> str:
    if kind == "legacy":
        return build_legacy_report(rng, stack=stack, topic=topic, project_name=project_name)
    if kind == "with_prd":
        return build_with_prd_report(
            rng, stack=stack, topic=topic, project_name=project_name, market=market
        )
    return build_no_prd_report(rng, stack=stack, topic=topic, project_name=project_name)
