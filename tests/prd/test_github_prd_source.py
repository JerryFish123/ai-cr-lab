from unittest.mock import MagicMock, patch

from biz.prd.github_prd_source import (
    filename_hint_from_url,
    find_prd_path_in_repo,
    parse_github_repo_file_url,
    resolve_prd_bytes_via_github_api,
)


class TestParseGithubRepoFileUrl:
    def test_blob(self):
        ref = parse_github_repo_file_url(
            "https://github.com/o/r/blob/feat/doc/PRD-0723迭代.pdf"
        )
        assert ref is not None
        assert ref.owner == "o"
        assert ref.repo == "r"
        assert ref.ref == "feat"
        assert ref.path == "doc/PRD-0723迭代.pdf"

    def test_raw(self):
        ref = parse_github_repo_file_url(
            "https://raw.githubusercontent.com/o/r/main/docs/a.pdf"
        )
        assert ref is not None
        assert ref.path == "docs/a.pdf"
        assert ref.ref == "main"

    def test_user_attachment_not_repo_file(self):
        assert (
            parse_github_repo_file_url(
                "https://github.com/user-attachments/files/1/prd.pdf"
            )
            is None
        )


class TestFindPrdPath:
    def test_prefers_hint_match(self):
        commit = MagicMock()
        commit.status_code = 200
        commit.json.return_value = {"commit": {"tree": {"sha": "tree1"}}}

        tree = MagicMock()
        tree.status_code = 200
        tree.json.return_value = {
            "tree": [
                {"type": "blob", "path": "readme.md"},
                {"type": "blob", "path": "doc/other.pdf"},
                {"type": "blob", "path": "doc/PRD-0723迭代.pdf"},
            ]
        }

        with patch(
            "biz.prd.github_prd_source.requests.get",
            side_effect=[commit, tree],
        ):
            path = find_prd_path_in_repo(
                owner="o",
                repo="r",
                ref="abc",
                token="t",
                hint_filename="PRD-0723.pdf",
            )
        assert path == "doc/PRD-0723迭代.pdf"


class TestResolveViaApi:
    def test_fallback_fetches_repo_prd(self):
        with patch(
            "biz.prd.github_prd_source.find_prd_path_in_repo",
            return_value="doc/PRD.pdf",
        ):
            with patch(
                "biz.prd.github_prd_source.fetch_repo_file_bytes",
                return_value=b"%PDF-1.4",
            ):
                data, source = resolve_prd_bytes_via_github_api(
                    url="https://github.com/user-attachments/files/1/PRD-0723.pdf",
                    token="t",
                    repo_key="o/r",
                    ref="sha",
                )
        assert data == b"%PDF-1.4"
        assert "contents-api-fallback" in source
        assert "doc/PRD.pdf" in source


def test_filename_hint():
    assert (
        filename_hint_from_url(
            "https://github.com/user-attachments/files/1/PRD-0723.pdf"
        )
        == "PRD-0723.pdf"
    )
