from unittest.mock import MagicMock, patch

from biz.review.triple_review import run_triple_review
from biz.utils.review_report_format import PRD_MISSING_MESSAGE, looks_like_triple_report


NO_PRD_WEBHOOK = {
    "pull_request": {
        "body": "refactor only",
        "head": {"sha": "abc", "ref": "feat"},
        "base": {"ref": "main"},
    },
    "repository": {
        "name": "demo",
        "full_name": "o/demo",
        "clone_url": "https://github.com/o/demo.git",
    },
}

WITH_PRD_WEBHOOK = {
    "pull_request": {
        "body": (
            "对照 3.2\n"
            "[prd.pdf](https://github.com/user-attachments/files/1/prd.pdf)"
        ),
        "head": {"sha": "abc", "ref": "feat"},
        "base": {"ref": "main"},
    },
    "repository": {
        "name": "demo",
        "full_name": "o/demo",
        "clone_url": "https://github.com/o/demo.git",
    },
}


class TestRunTripleReview:
    def test_no_prd_fixed_sections_and_risk(self):
        reviewer = MagicMock()
        reviewer.review.return_value = "### 3. 安全与性能风险\n\n- SQL 注入风险，需参数化"

        with patch("biz.review.triple_review.AgenticReviewer", return_value=reviewer):
            out = run_triple_review(
                changes=["+x"],
                commits_text="c",
                webhook_data=NO_PRD_WEBHOOK,
                access_token="t",
                platform_url="https://github.com",
                repo_url="https://github.com/o/demo.git",
                repo_key="o/demo",
                ref="abc",
            )

        assert PRD_MISSING_MESSAGE in out
        assert "SQL 注入" in out
        assert looks_like_triple_report(out)
        assert "总分" not in out
        reviewer.review.assert_called_once()
        assert reviewer.review.call_args.kwargs["prompt_key"] == "risk_only_review_prompt"

    def test_prd_extract_fail_still_risk(self):
        reviewer = MagicMock()
        reviewer.review.return_value = "- 硬编码密钥有泄露风险"

        with patch("biz.review.triple_review.AgenticReviewer", return_value=reviewer), patch(
            "biz.review.triple_review.resolve_and_extract_prd",
            return_value=MagicMock(ok=False, reason="HTTP 403", text=""),
        ):
            out = run_triple_review(
                changes=["+x"],
                commits_text="c",
                webhook_data=WITH_PRD_WEBHOOK,
                access_token="t",
                platform_url="https://github.com",
                repo_url="https://github.com/o/demo.git",
                repo_key="o/demo",
                ref="abc",
            )

        assert "PRD解析失败" in out
        assert "泄露" in out
        assert looks_like_triple_report(out)
        assert "总分" not in out

    def test_full_triple_prompt(self):
        triple = """
## AI 代码审查
### 1. PRD 覆盖情况
- **未覆盖（重点）** 登录页
### 2. 非 PRD 范围的潜在波及
- 未发现
### 3. 安全与性能风险
- 未发现明显安全或性能风险
"""
        reviewer = MagicMock()
        reviewer.review.return_value = triple

        with patch("biz.review.triple_review.AgenticReviewer", return_value=reviewer), patch(
            "biz.review.triple_review.resolve_and_extract_prd",
            return_value=MagicMock(ok=True, reason="", text="PRD body"),
        ):
            out = run_triple_review(
                changes=["+x"],
                commits_text="c",
                webhook_data=WITH_PRD_WEBHOOK,
                access_token="t",
                platform_url="https://github.com",
                repo_url="https://github.com/o/demo.git",
                repo_key="o/demo",
                ref="abc",
            )

        assert looks_like_triple_report(out)
        assert "登录页" in out
        assert "总分" not in out
        assert reviewer.review.call_args.kwargs["prompt_key"] == "triple_review_prompt"
