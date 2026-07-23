from biz.utils.review_report_format import (
    prioritize_uncovered_requirements,
    trim_quality_report_for_publish,
)


class TestTrimQualityReport:
    def test_strips_medium_minor_sections(self):
        report = """
### 严重问题
- SQL 注入

### 🟡 中等问题
- 命名不规范

### 🟢 轻微问题 / 优化建议
- 可以加注释

评分明细：安全 20
总分:70分
"""
        out = trim_quality_report_for_publish(report)
        assert "SQL 注入" in out
        assert "命名不规范" not in out
        assert "可以加注释" not in out
        assert "中等问题" not in out
        assert "轻微问题" not in out
        assert "总分:70分" in out

    def test_strips_emoji_bullets(self):
        report = "- 🔴 越权风险\n- 🟡 变量命名\n- 🟢 加个空行"
        out = trim_quality_report_for_publish(report)
        assert "越权风险" in out
        assert "变量命名" not in out
        assert "空行" not in out


class TestPrioritizeUncovered:
    def test_uncovered_first(self):
        report = """
## 需求完成情况
- 第3章 Banner 已覆盖
- 第5章 Profile 未覆盖，缺页面
完成度:约70%
"""
        out = prioritize_uncovered_requirements(report)
        assert "未覆盖（重点）" in out
        assert out.index("未覆盖（重点）") < out.index("已覆盖")
        assert "Profile" in out
        assert "Banner" in out
        assert "完成度:约70%" in out

    def test_empty_uncovered(self):
        out = prioritize_uncovered_requirements("- 第3章 已覆盖\n完成度:约100%")
        assert "无未覆盖项" in out
