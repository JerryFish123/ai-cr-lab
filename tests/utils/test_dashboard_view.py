import pandas as pd

from biz.utils.dashboard_view import (
    classify_review,
    count_prd_reviews,
    enrich_review_frame,
    filter_enriched_frame,
    has_risk,
    summarize_review_for_table,
)
from biz.utils.review_report_format import PRD_MISSING_MESSAGE, normalize_triple_report


NO_PRD = normalize_triple_report(
    "",
    has_prd=False,
    risk_section="- SQL 注入风险，需参数化查询",
)

NO_PRD_CLEAN = normalize_triple_report(
    "",
    has_prd=False,
    risk_section="- 未发现明显安全或性能风险",
)

WITH_PRD = normalize_triple_report(
    """
### 1. PRD 覆盖情况
- Profile 页未覆盖
### 2. 非 PRD 范围的潜在波及
- 旧支付回调可能受影响
### 3. 安全与性能风险
- 硬编码密钥有泄露风险
""",
    has_prd=True,
)

LEGACY = "### 严重问题\n- XSS\n总分:80分"


class TestClassify:
    def test_kinds(self):
        assert classify_review(NO_PRD) == "no_prd"
        assert classify_review(WITH_PRD) == "with_prd"
        assert classify_review(LEGACY) == "legacy"
        assert classify_review("") == "legacy"
        assert classify_review(f"PRD解析失败\n{PRD_MISSING_MESSAGE}") == "no_prd"


class TestSummarizeAndRisk:
    def test_no_prd_with_risk(self):
        s = summarize_review_for_table(NO_PRD)
        assert s.startswith("无PRD")
        assert "风险" in s
        assert has_risk(NO_PRD) is True

    def test_no_prd_clean(self):
        s = summarize_review_for_table(NO_PRD_CLEAN)
        assert "无明显风险" in s
        assert has_risk(NO_PRD_CLEAN) is False

    def test_with_prd_counts(self):
        s = summarize_review_for_table(WITH_PRD)
        assert "未覆盖" in s
        assert "波及" in s
        assert "风险" in s
        assert has_risk(WITH_PRD) is True

    def test_legacy(self):
        assert summarize_review_for_table(LEGACY) == "旧格式报告"
        assert has_risk(LEGACY) is False


class TestCountAndEnrich:
    def test_count_matches_kind(self):
        rows = [NO_PRD, WITH_PRD, LEGACY, ""]
        assert count_prd_reviews(rows) == 1
        for r in rows:
            kind = classify_review(r)
            summary = summarize_review_for_table(r)
            if kind == "with_prd":
                assert "旧格式" not in summary
                assert "无PRD" not in summary
            elif kind == "no_prd":
                assert summary.startswith("无PRD")
            else:
                assert summary in ("旧格式报告", "—")

    def test_enrich_and_filter(self):
        df = pd.DataFrame(
            {
                "project_name": ["a", "b", "c"],
                "author": ["u1", "u2", "u1"],
                "review_result": [NO_PRD, WITH_PRD, LEGACY],
                "additions": [1, 2, 3],
                "deletions": [0, 0, 0],
            }
        )
        enriched = enrich_review_frame(df)
        assert list(enriched["kind"]) == ["no_prd", "with_prd", "legacy"]
        assert enriched["kind_label"].tolist() == ["无PRD", "有PRD", "旧格式"]

        only_prd = filter_enriched_frame(enriched, prd_filter="含PRD")
        assert len(only_prd) == 1
        assert only_prd.iloc[0]["kind"] == "with_prd"

        risky = filter_enriched_frame(enriched, risk_filter="有风险")
        assert len(risky) == 2
        assert set(risky["kind"]) == {"no_prd", "with_prd"}
