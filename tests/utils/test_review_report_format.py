from biz.utils.review_report_format import (
    PRD_MISSING_MESSAGE,
    count_prd_reviews,
    looks_like_triple_report,
    normalize_triple_report,
    summarize_review_for_table,
    trim_quality_report_for_publish,
)


class TestTrimQualityReport:
    def test_strips_medium_minor_sections_and_score(self):
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
        assert "总分" not in out

    def test_strips_emoji_bullets(self):
        report = "- 🔴 越权风险\n- 🟡 变量命名\n- 🟢 加个空行"
        out = trim_quality_report_for_publish(report)
        assert "越权风险" in out
        assert "变量命名" not in out
        assert "空行" not in out


class TestNormalizeTripleReport:
    def test_no_prd_fixed_copy_plus_risk(self):
        out = normalize_triple_report(
            "",
            has_prd=False,
            risk_section="- XSS 注入风险，需转义",
        )
        assert PRD_MISSING_MESSAGE in out
        assert out.count(PRD_MISSING_MESSAGE) >= 2
        assert "### 1. PRD 覆盖情况" in out
        assert "### 2. 非 PRD 范围的潜在波及" in out
        assert "### 3. 安全与性能风险" in out
        assert "XSS" in out
        assert "总分" not in out

    def test_has_prd_three_sections(self):
        raw = """
## AI 代码审查
### 1. PRD 覆盖情况
- **未覆盖（重点）** Profile 页
### 2. 非 PRD 范围的潜在波及
- 旧支付回调可能受影响
### 3. 安全与性能风险
- 未发现明显安全或性能风险
"""
        out = normalize_triple_report(raw, has_prd=True)
        assert looks_like_triple_report(out)
        assert "Profile" in out
        assert "支付" in out
        assert "总分" not in out


class TestSummarizeAndCount:
    def test_summarize_no_prd(self):
        text = normalize_triple_report("", has_prd=False, risk_section="- SQL 注入")
        s = summarize_review_for_table(text)
        assert "无PRD" in s

    def test_count_prd_reviews(self):
        with_prd = normalize_triple_report(
            "### 1. PRD 覆盖情况\n- ok\n### 2. 非 PRD 范围的潜在波及\n- 未发现\n### 3. 安全与性能风险\n- 未发现明显安全或性能风险",
            has_prd=True,
        )
        no_prd = normalize_triple_report("", has_prd=False, risk_section="- x")
        assert count_prd_reviews([with_prd, no_prd, ""]) == 1
