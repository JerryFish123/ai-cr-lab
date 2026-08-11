from unittest.mock import patch

from biz.utils.im.review_notify import (
    build_dingtalk_digest,
    estimate_review_minutes,
    fallback_digest,
    format_eta_text,
    format_review_finished_markdown,
    format_review_started_markdown,
    pr_meta_from_webhook,
)
from biz.utils.review_report_format import PRD_MISSING_MESSAGE, normalize_triple_report


class TestEstimateReviewMinutes:
    def test_more_files_increases_eta(self):
        lo1, hi1 = estimate_review_minutes(2, False)
        lo2, hi2 = estimate_review_minutes(20, False)
        assert lo2 >= lo1
        assert hi2 >= hi1

    def test_prd_adds_time(self):
        lo_no, hi_no = estimate_review_minutes(5, False)
        lo_yes, hi_yes = estimate_review_minutes(5, True)
        assert lo_yes > lo_no
        assert hi_yes > hi_no

    def test_eta_text_range(self):
        text = format_eta_text(5, True)
        assert text.startswith("约 ")
        assert "分钟" in text


class TestFormatMessages:
    def test_started_includes_prd_and_eta(self):
        md = format_review_started_markdown(
            project_name="demo",
            author="alice",
            source_branch="feat",
            target_branch="main",
            url="https://example.com/pr/1",
            has_prd=True,
            file_count=4,
        )
        assert "审查已开始" in md
        assert "是否携带 PRD 分析**: 是" in md
        assert "预计耗时" in md
        assert "alice" in md
        assert "https://example.com/pr/1" in md

    def test_started_without_prd(self):
        md = format_review_started_markdown(
            project_name="demo",
            author="bob",
            source_branch="a",
            target_branch="b",
            url="https://x/y",
            has_prd=False,
            file_count=1,
        )
        assert "是否携带 PRD 分析**: 否" in md

    def test_finished_wraps_digest(self):
        md = format_review_finished_markdown(
            project_name="demo",
            author="alice",
            url="https://example.com/pr/1",
            digest_body="#### 3. 安全与性能风险\n- SQL 注入风险",
        )
        assert "审查完成：demo" in md
        assert "SQL 注入风险" in md
        assert "总分" not in md


class TestFallbackDigest:
    def test_no_prd_fixed_and_risk(self):
        quality = normalize_triple_report(
            "",
            has_prd=False,
            risk_section="- 存在 SQL 注入风险，用户输入未校验",
        )
        out = fallback_digest(quality, None)
        assert "1. PRD 覆盖" in out
        assert PRD_MISSING_MESSAGE in out
        assert "3. 安全与性能风险" in out
        assert "SQL 注入" in out
        assert "总分" not in out

    def test_no_risk_message(self):
        quality = normalize_triple_report("", has_prd=False, risk_section="- 未发现明显安全或性能风险")
        out = fallback_digest(quality, None)
        assert "未发现明显安全或性能风险" in out

    def test_with_prd_triple(self):
        quality = normalize_triple_report(
            """
### 1. PRD 覆盖情况
- Profile 未覆盖
### 2. 非 PRD 范围的潜在波及
- 旧支付回调
### 3. 安全与性能风险
- 硬编码密钥有泄露风险
""",
            has_prd=True,
        )
        out = fallback_digest(quality, None)
        assert "1. PRD 覆盖" in out
        assert "Profile" in out or "未覆盖" in out
        assert "2. 非PRD波及" in out
        assert "支付" in out
        assert "泄露" in out
        assert out.index("1. PRD 覆盖") < out.index("3. 安全与性能风险")


class TestBuildDigest:
    def test_llm_success(self):
        with patch(
            "biz.utils.im.review_notify._llm_digest",
            return_value="#### 3. 安全与性能风险\n- 越权风险",
        ):
            out = build_dingtalk_digest(
                quality_report="long...",
                requirement_report=None,
                has_prd=False,
            )
        assert "越权风险" in out

    def test_llm_failure_uses_fallback(self):
        with patch(
            "biz.utils.im.review_notify._llm_digest",
            side_effect=RuntimeError("boom"),
        ):
            quality = normalize_triple_report(
                "",
                has_prd=False,
                risk_section="- XSS 漏洞可被利用",
            )
            out = build_dingtalk_digest(
                quality_report=quality,
                requirement_report=None,
                has_prd=False,
            )
        assert "XSS" in out
        assert "总分" not in out


class TestPrMeta:
    def test_github_payload(self):
        meta = pr_meta_from_webhook(
            {
                "pull_request": {
                    "user": {"login": "u"},
                    "head": {"ref": "feat"},
                    "base": {"ref": "main"},
                    "html_url": "https://github.com/o/r/pull/1",
                },
                "repository": {"name": "r"},
            }
        )
        assert meta["project_name"] == "r"
        assert meta["author"] == "u"
        assert meta["source_branch"] == "feat"
        assert meta["url"].endswith("/pull/1")
