"""Rich, stack-aware mock review report bodies for dashboard demos."""
from __future__ import annotations

import random
import re

from biz.utils.review_report_format import normalize_triple_report

_MARKETS = ["zh-CN", "en-US", "ja-JP", "de-DE", "es-ES", "fr-FR", "ko-KR"]

_OTHER_PROJECTS = [
    "zahlung-gateway-java",
    "inventaire-api-java",
    "merchant-console-web",
    "datenpipeline-etl-py",
    "reco-ranking-py",
    "checkout-micro-ui",
]


def _topic_title(topic: str) -> str:
    return "".join(p.capitalize() for p in re.split(r"[-_]", topic))


def _line(path: str, line: int) -> str:
    return f"`{path}:{line}`"


def _pick_paths(rng: random.Random, stack: str, project: str, topic: str, n: int) -> list[str]:
    tt = _topic_title(topic)
    pkg = project.split("-")[0]
    pools: dict[str, list[str]] = {
        "frontend": [
            f"src/pages/{topic}/ListPage.tsx",
            f"src/pages/{topic}/DetailPage.tsx",
            f"src/components/{topic}/FilterBar.tsx",
            f"src/components/{topic}/BatchExportModal.tsx",
            f"src/hooks/use{tt}.ts",
            f"src/api/{topic}Client.ts",
            f"src/locales/{topic}.json",
            f"src/store/{topic}Slice.ts",
            "src/utils/request.ts",
            "src/utils/authGuard.ts",
        ],
        "java": [
            f"src/main/java/com/{pkg}/web/{tt}Controller.java",
            f"src/main/java/com/{pkg}/service/{tt}Service.java",
            f"src/main/java/com/{pkg}/service/impl/{tt}ServiceImpl.java",
            f"src/main/java/com/{pkg}/repo/{tt}Repository.java",
            f"src/main/java/com/{pkg}/dto/{tt}Request.java",
            f"src/main/resources/mapper/{tt}Mapper.xml",
            f"src/test/java/com/{pkg}/service/{tt}ServiceTest.java",
            f"src/test/java/com/{pkg}/web/{tt}ControllerIT.java",
        ],
        "python": [
            f"app/services/{topic}_service.py",
            f"app/services/{topic}_repository.py",
            f"app/api/routes/{topic}.py",
            f"app/schemas/{topic}.py",
            f"app/models/{topic}.py",
            f"app/tasks/{topic}_sync.py",
            f"tests/unit/test_{topic}_service.py",
            f"tests/integration/test_{topic}_api.py",
        ],
        "test": [
            f"src/main/java/com/demo/controller/{tt}Controller.java",
            f"src/main/java/com/demo/service/{tt}Service.java",
            f"src/main/java/com/demo/mapper/{tt}Mapper.java",
            f"src/test/java/com/demo/{tt}ApiTest.java",
            f"src/test/java/com/demo/{tt}ServiceTest.java",
            "src/main/resources/application.yml",
            "src/main/resources/db/migration/V3__sku_index.sql",
        ],
    }
    pool = pools.get(stack, pools["java"])
    picked = list(rng.sample(pool, k=min(n, len(pool))))
    while len(picked) < max(n, 8):
        picked.append(rng.choice(pool))
    return picked


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {ln}" for ln in lines)


def _sub_bullets(title: str, lines: list[str]) -> str:
    return f"**{title}**\n" + _bullets(lines)


def _change_summary(
    rng: random.Random,
    *,
    stack: str,
    topic: str,
    project_name: str,
    paths: list[str],
    market: str,
) -> str:
    tt = _topic_title(topic)
    adds = rng.randint(120, 890)
    dels = rng.randint(15, 320)
    files = rng.randint(4, 14)
    apis = [
        f"GET /api/v1/{topic.replace('-', '/')}",
        f"POST /api/v1/{topic.replace('-', '/')}",
        f"PUT /api/v1/{topic.replace('-', '/')}/{{id}}",
    ]
    api = rng.choice(apis)
    lines = [
        f"本 PR 在 `{project_name}` 实现 **{tt}** 相关能力，主要改动 {files} 个文件（+{adds}/-{dels}）",
        f"核心入口：{_line(paths[0], rng.randint(18, 95))}，新增/调整接口 `{api}`",
        f"目标市场 **{market}**，涉及 i18n、权限与审计日志联动",
        f"依赖变更：{'升级 Spring Boot 3.2 patch' if stack == 'java' else '升级 React Query v5' if stack == 'frontend' else '新增 pydantic v2 校验'}（需关注兼容性）",
    ]
    return _sub_bullets("变更摘要", lines)


def _covered_items(
    rng: random.Random,
    *,
    prd_sec: int,
    tt: str,
    paths: list[str],
    market: str,
) -> list[str]:
    pool = [
        f"PRD {prd_sec}.1 列表分页：{_line(paths[0], rng.randint(40, 120))} 支持 page/size/sort，默认排序与 PRD 一致",
        f"PRD {prd_sec}.2 组合查询：{_line(paths[1], rng.randint(20, 80))} 支持 skuCode/categoryCode/status 多条件 AND 查询",
        f"PRD {prd_sec}.2 空结果：无数据时返回空数组 + 标准 pagination meta，非 404",
        f"PRD {prd_sec}.3 错误码：{_line(paths[2], rng.randint(10, 60))} 映射 PRD 附录错误码表（40001/40002/50001）",
        f"PRD {prd_sec}.3 权限：写操作校验角色 `{rng.choice(['ADMIN', 'OPS', 'MERCHANT'])}`，读操作允许 `{rng.choice(['VIEWER', 'GUEST'])}`",
        f"PRD {prd_sec}.4 审计：创建/更新/删除写入 audit_log（operator, action, entityId, diff 摘要）",
        f"PRD {prd_sec}.4 幂等：重复 POST 同 bizKey 返回 409 + 已有 resourceId，符合 PRD 幂等章节",
        f"PRD {prd_sec}.5 多语言：{_line(paths[5] if len(paths) > 5 else paths[0], 12)} 接入 i18n key，`{market}` 文案走资源文件",
        f"PRD {prd_sec}.5 导出：CSV 列顺序与 PRD 样例一致（id,name,status,updatedAt）",
        f"PRD {prd_sec}.6 软删除：删除为 status=DELETED，列表默认过滤，与 PRD 数据保留策略一致",
        f"PRD {prd_sec}.6 并发：更新带 version 字段乐观锁，冲突返回 409",
    ]
    return rng.sample(pool, k=rng.randint(5, 8))


def _uncovered_items(
    rng: random.Random,
    *,
    prd_sec: int,
    tt: str,
    paths: list[str],
    market: str,
) -> list[str]:
    pool = [
        f"PRD {prd_sec}.7 批量操作：`Batch{tt}Modal` 缺少二次确认弹窗与 PRD 文案（「确认影响 N 条记录」）",
        f"PRD {prd_sec}.7 批量失败：部分失败时 PRD 要求逐条错误明细，当前仅返回整体失败",
        f"PRD {prd_sec}.8 多语言：`de-DE`/`fr-FR` 错误提示仍为英文 fallback，未走 `{paths[4] if len(paths) > 4 else paths[0]}`",
        f"PRD {prd_sec}.8 数字/日期：{market} 区域格式未按 PRD 做本地化（千分位、时区）",
        f"PRD {prd_sec}.9 导出 Excel：缺少「更新时间」列；列宽未按 PRD 样例设置",
        f"PRD {prd_sec}.9 导出限流：PRD 要求单用户 5 次/分钟，代码未实现",
        f"PRD {prd_sec}.10 空态页：列表无数据引导文案与 PRD 3.x 不一致",
        f"PRD {prd_sec}.10 超时重试：前端未实现 PRD 规定的 3 次指数退避（1s/2s/4s）",
        f"PRD {prd_sec}.11 消息通知：状态变更后应触发 MQ 事件，当前仅写库未 publish",
        f"PRD {prd_sec}.11 回滚：PRD 要求提供 admin 回滚入口，未见实现",
    ]
    return rng.sample(pool, k=rng.randint(3, 6))


def _test_suggestions(rng: random.Random, *, tt: str, paths: list[str], stack: str) -> list[str]:
    pool = [
        f"单测：补 `{paths[-2]}` 覆盖边界（空列表、非法 pageSize、无权限角色）",
        f"单测：{_line(paths[1], rng.randint(50, 200))} 并发更新 version 冲突场景",
        f"集成：Mock 下游 payment/inventory 超时与 5xx，验证重试与降级",
        f"集成：验证 audit_log 写入字段完整性与 traceId 贯通",
        f"E2E：{rng.choice(_MARKETS)} 语言切换 + 导出全链路",
        f"性能：列表 1 万条数据 P99 < 200ms（需 explain 验证索引命中）",
        f"安全：未登录/越权访问写接口应 401/403",
        f"回归：批量操作、导出、删除后列表刷新（手工清单见 PR 描述）",
    ]
    if stack == "frontend":
        pool.append(f"Storybook：补 `{paths[2]}` 空态/错误态/loading 三态截图")
    return rng.sample(pool, k=rng.randint(4, 6))


def _blast_items(rng: random.Random, *, topic: str, paths: list[str], project_name: str) -> list[str]:
    downstream = rng.choice([p for p in _OTHER_PROJECTS if p != project_name])
    pool = [
        f"**支付回调** · `PaymentNotifyListener#onMessage` 与本 PR 共用 `HmacUtils.verify()`，需回归 notify 重放、签名校验失败、乱序到达",
        f"**缓存** · Redis key `{topic}:*` → `product:{topic}:*`，可能影响 `{downstream}` 库存扣减缓存命中率，需联调",
        f"**DTO 字段** · {_line(paths[3], rng.randint(10, 40))} 将 `status` 重命名为 `state`，ETL 任务 `{downstream}` 需同步字段映射",
        f"**权限** · `RoleContextHolder` 线程上下文在本 PR 新增异步分支，管理员 impersonate 场景需回归",
        f"**异常码** · {_line(paths[4], rng.randint(80, 150))} 调整全局 `@ControllerAdvice`，其他 Controller 错误码前缀可能变化",
        f"**DB 迁移** · 新增索引 `idx_{topic}_status_updated` 可能锁表，发布窗口需低峰执行",
        f"**MQ** · 新增 topic `{topic}.changed` 事件，消费方 `{downstream}` 若未订阅可能丢同步",
        f"**配置** · `application.yml` 默认 timeout 从 3s 改为 5s，可能影响网关 SLA 告警阈值",
        f"**前端路由** · 深链 `/orders/{topic}` 参数变更，旧 bookmark 可能 404",
        "未发现对鉴权链路、公共中间件或共享库的破坏性变更",
    ]
    picked = rng.sample(pool, k=rng.randint(4, 7))
    if not any("未发现" in x for x in picked) and rng.random() < 0.25:
        picked.append("未发现其他模块的连锁影响")
    return picked


def _risk_items(rng: random.Random, *, paths: list[str], stack: str) -> str:
    high_sec = [
        f"{_line(paths[1], rng.randint(60, 180))} SQL 拼接 userInput，存在注入风险 → 改 PreparedStatement / MyBatis `#{{}}`",
        f"{_line(paths[0], rng.randint(30, 90))} 日志打印完整 request body（phone/email/idCard），违反脱敏规范",
        f"{_line(paths[2], rng.randint(20, 70))} 硬编码 `sk-live-***` API Key，需迁移 KMS / Vault",
        f"新增 `{rng.choice(['POST', 'PUT', 'DELETE'])}` 接口未接入 API Gateway 鉴权白名单",
        f"{_line(paths[5] if len(paths) > 5 else paths[0], rng.randint(10, 50))} `@CrossOrigin(origins='*')` 过宽",
    ]
    perf = [
        f"{_line(paths[1], rng.randint(100, 220))} 循环内调用 repository / HTTP client，N+1 明显，P99 预估 +80~180ms",
        f"{_line(paths[0], rng.randint(40, 120))} 列表/导出无 limit 上限，单次可拉 10w+ 行进内存",
        f"Redis key 无 TTL，热点 `{rng.choice(['sku', 'category', 'session'])}` 可能长期占用",
        f"{_line(paths[3], rng.randint(50, 140))} 同步调用第三方 API 未设 connect/read timeout",
        f"缺少接口级限流（QPS/并发），存在被刷风险",
    ]
    reliability = [
        f"{_line(paths[2], rng.randint(40, 100))} catch Exception 后吞掉堆栈，仅返回「系统繁忙」不利于排障",
        f"事务边界不完整：写 audit 成功但主表 rollback 时可能不一致",
        f"幂等键仅内存去重，多实例部署可能重复提交",
        f"缺少分布式锁，批量更新存在并发覆盖",
    ]
    if stack == "frontend":
        perf.append(f"{_line(paths[0], 1)} 大列表未虚拟滚动，1k+ 行可能卡顿")
        high_sec.append(f"{_line(paths[6] if len(paths) > 6 else paths[0], 20)} 使用 dangerouslySetInnerHTML 渲染用户输入")

    parts = [
        _sub_bullets("安全（高优先级）", rng.sample(high_sec, k=rng.randint(2, 4))),
        _sub_bullets("性能", rng.sample(perf, k=rng.randint(3, 5))),
        _sub_bullets("可靠性 / 可维护性", rng.sample(reliability, k=rng.randint(2, 4))),
    ]
    return "\n\n".join(parts)


def build_with_prd_report(
    rng: random.Random,
    *,
    stack: str,
    topic: str,
    project_name: str,
    market: str,
) -> str:
    paths = _pick_paths(rng, stack, project_name, topic, 8)
    tt = _topic_title(topic)
    prd_sec = rng.randint(2, 5)
    completion = rng.randint(62, 93)
    blocking = rng.choice(
        [
            "批量二次确认、导出限流",
            "多语言 de-DE/fr-FR 验收项",
            "MQ 事件 publish 与回滚入口",
            "无阻塞项，可灰度发布",
        ]
    )

    s1_parts = [
        _change_summary(rng, stack=stack, topic=topic, project_name=project_name, paths=paths, market=market),
        _sub_bullets("已覆盖", _covered_items(rng, prd_sec=prd_sec, tt=tt, paths=paths, market=market)),
        _sub_bullets("未覆盖 / 部分覆盖", _uncovered_items(rng, prd_sec=prd_sec, tt=tt, paths=paths, market=market)),
        _sub_bullets("测试与回归建议", _test_suggestions(rng, tt=tt, paths=paths, stack=stack)),
        (
            f"**完成度评估**\n"
            f"- 功能完成度：约 **{completion}%**（主流程可验收，边缘场景见未覆盖项）\n"
            f"- 阻塞发布项：{blocking}\n"
            f"- 建议：未覆盖项中标记 **P0** 的需在合并前补齐或拆 follow-up PR"
        ),
    ]
    s1 = "\n\n".join(s1_parts)

    s2 = _bullets(_blast_items(rng, topic=topic, paths=paths, project_name=project_name))
    s3 = _risk_items(rng, paths=paths, stack=stack)

    raw = (
        f"### 1. PRD 覆盖\n\n{s1}\n\n"
        f"### 2. 非 PRD 波及\n\n{s2}\n\n"
        f"### 3. 安全与性能风险\n\n{s3}"
    )
    return normalize_triple_report(raw, has_prd=True)


def build_no_prd_report(rng: random.Random, *, stack: str, topic: str, project_name: str) -> str:
    paths = _pick_paths(rng, stack, project_name, topic, 6)
    tt = _topic_title(topic)

    logic = [
        f"{_line(paths[0], rng.randint(30, 100))} 边界条件：`pageSize=0` / 负数未校验",
        f"{_line(paths[1], rng.randint(40, 120))} 空指针：`optional.get()` 未判空",
        f"{_line(paths[2], rng.randint(20, 80))} 魔法数字 `{rng.randint(100, 9999)}` 应提取常量",
        f"缺少对 `{tt}NotFound` 异常的统一处理，部分接口返回 500",
        f"单元测试未覆盖删除/并发更新/权限拒绝三类场景",
    ]
    security = [
        f"{_line(paths[0], rng.randint(50, 150))} 缺少输入长度校验，超长 payload 可能导致 DoS",
        f"{_line(paths[1], rng.randint(60, 180))} 异常栈直接返回客户端，泄露内部路径",
        f"{_line(paths[3], rng.randint(10, 50))} 敏感字段写入 info 日志",
        f"CSRF / 鉴权：写接口未校验 Referer / token scope",
    ]
    perf = [
        f"{_line(paths[1], rng.randint(90, 200))} 同步 HTTP 未设超时，线程池可能被占满",
        f"{_line(paths[4], rng.randint(30, 90))} LIKE '%xxx%' 模糊查询无索引，数据量上升后全表扫描",
        f"批量接口未分批，单次可能加载过多 ID",
    ]
    maintain = [
        f"方法 `{tt}Service.process()` 超过 120 行，建议拆分",
        f"DTO 与 Entity 字段重复映射 3 处，可引入 MapStruct",
        "README 未更新新环境变量 `FEATURE_{}_ENABLED`".format(topic.upper().replace("-", "_")),
    ]

    risk_body = "\n\n".join(
        [
            _sub_bullets("代码逻辑", rng.sample(logic, k=rng.randint(3, 5))),
            _sub_bullets("安全", rng.sample(security, k=rng.randint(3, 4))),
            _sub_bullets("性能", rng.sample(perf, k=rng.randint(2, 4))),
            _sub_bullets("可维护性", rng.sample(maintain, k=rng.randint(2, 3))),
            _sub_bullets(
                "建议",
                [
                    f"补充 PRD 或至少提供 `{project_name}` 本需求的验收清单后再做覆盖度审查",
                    f"优先修复安全（高）项后再合并",
                    f"补集成测试：`{paths[-1]}`",
                ],
            ),
        ]
    )
    return normalize_triple_report("", has_prd=False, risk_section=risk_body)


def build_legacy_report(rng: random.Random, *, stack: str, topic: str, project_name: str) -> str:
    paths = _pick_paths(rng, stack, project_name, topic, 6)
    severe = [
        f"{_line(paths[0], rng.randint(40, 120))} 未关闭 Connection/Stream，连接池可能耗尽",
        f"{_line(paths[1], rng.randint(50, 180))} NPE：`list.get(0)` 未判空",
        f"{_line(paths[2], rng.randint(30, 90))} 并发 check-then-act 竞态，可能重复创建",
        f"{_line(paths[3], rng.randint(20, 70))} 敏感 token 写入日志",
        f"SQL 注入风险：字符串拼接 `{rng.choice(['orderId', 'userId', 'skuCode'])}`",
        f"缺少 `/api/v2/{topic}` 集成测试",
        f"前端 bundle +{rng.randint(280, 520)}KB，需 code-splitting",
        f"Breaking change：公开 API 响应字段删除 `{rng.choice(['name', 'status', 'type'])}` 未 deprecation",
    ]
    medium = [
        "建议补充 README / CHANGELOG 迁移说明",
        "魔法数字与重复代码块，可读性一般",
        f"{_line(paths[4], rng.randint(10, 60))} 方法超过 80 行，建议拆分",
        "异常处理不一致：部分 catch 后 return null",
        "缺少 API 文档 / Swagger 注解更新",
    ]
    minor = [
        "命名风格与仓库现有约定略有差异（camelCase vs snake_case）",
        "部分 TODO 注释未关联 ticket",
        "import 未使用的静态分析告警",
        "Commit message 与变更范围不完全匹配",
    ]
    score = rng.randint(58, 86)
    return (
        f"### 严重问题\n{_bullets(rng.sample(severe, k=rng.randint(4, 6)))}\n\n"
        f"### 中等问题\n{_bullets(rng.sample(medium, k=rng.randint(3, 5)))}\n\n"
        f"### 轻微问题\n{_bullets(rng.sample(minor, k=rng.randint(2, 4)))}\n\n"
        f"### 审查结论\n"
        f"- 变更涉及 **{project_name}** `{topic}` 模块，建议修复严重项后再合并\n"
        f"- 预估修复工作量：{rng.randint(2, 8)} 人日\n\n"
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
