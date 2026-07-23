from unittest.mock import MagicMock, patch

from biz.prd.pipeline import format_prd_parse_failure, maybe_post_requirement_review


GH_PAYLOAD = {
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


class TestMaybePostRequirementReview:
    def test_skip_without_attachment(self):
        notes = MagicMock()
        result = maybe_post_requirement_review(
            webhook_data={"pull_request": {"body": "refactor only"}},
            access_token="t",
            changes=[],
            commits_text="c",
            add_notes=notes,
            repo_url="https://x.git",
            repo_key="o/r",
            ref="sha",
        )
        notes.assert_not_called()
        assert result is None

    def test_parse_failure_comment(self):
        notes = MagicMock()
        with patch(
            "biz.prd.pipeline.download_and_extract",
            return_value=MagicMock(ok=False, reason="HTTP 403", text=""),
        ):
            result = maybe_post_requirement_review(
                webhook_data=GH_PAYLOAD,
                access_token="t",
                changes=["+x"],
                commits_text="c",
                add_notes=notes,
                repo_url="https://github.com/o/demo.git",
                repo_key="o/demo",
                ref="abc",
            )
        notes.assert_called_once()
        body = notes.call_args[0][0]
        assert "PRD解析失败" in body
        assert "HTTP 403" in body
        assert result == body

    def test_success_posts_requirement_header(self):
        notes = MagicMock()
        with patch(
            "biz.prd.pipeline.download_and_extract",
            return_value=MagicMock(ok=True, reason="", text="PRD正文"),
        ):
            with patch("biz.prd.pipeline.RequirementReviewer") as MockRR:
                MockRR.return_value.review_requirements.return_value = (
                    "章节 3.2 已覆盖\n完成度:约80%\n建议：无"
                )
                result = maybe_post_requirement_review(
                    webhook_data=GH_PAYLOAD,
                    access_token="t",
                    changes=["+x"],
                    commits_text="c",
                    add_notes=notes,
                    repo_url="https://github.com/o/demo.git",
                    repo_key="o/demo",
                    ref="abc",
                )
        notes.assert_called_once()
        body = notes.call_args[0][0]
        assert body.startswith("## 需求完成情况")
        assert "完成度:约80%" in body
        assert result == body


def test_format_failure():
    assert "原因：x" in format_prd_parse_failure("x")
