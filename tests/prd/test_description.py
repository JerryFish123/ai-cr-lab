from biz.prd.description import extract_description_body, parse_prd_intent

ASSETS = "https://github.com/user-attachments/assets/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FILES_PDF = "https://github.com/user-attachments/files/12345678/My-PRD.pdf"


class TestParsePrdIntent:
    def test_no_attachment_skips(self):
        intent = parse_prd_intent("纯技术重构，对照章节 3.2")
        assert intent.should_run_requirement_review is False
        assert intent.has_chapter_intent is True

    def test_pdf_markdown_link_files_path(self):
        body = (
            "本期对照 PRD 3.2、3.5 改造退款失败流转。\n"
            f"[prd.pdf]({FILES_PDF})"
        )
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is True
        assert intent.primary_url.endswith("prd.pdf") or "My-PRD.pdf" in intent.primary_url
        assert intent.has_chapter_intent is True

    def test_assets_url_with_pdf_link_text(self):
        body = f"对照 3.2\n[需求说明.pdf]({ASSETS})"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is True
        assert intent.primary_url == ASSETS

    def test_assets_url_with_prd_link_text(self):
        body = f"对照章节 3.2\n[本期PRD]({ASSETS})"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is True

    def test_bare_assets_url_with_prd_hint_in_body(self):
        body = f"附件为完整 PRD（PDF）。对照 3.2。\n{ASSETS}"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is True
        assert ASSETS in intent.attachment_urls

    def test_image_markdown_not_treated_as_prd(self):
        # 仅图片 + 章节：仍可能把 assets 当候选（章节意图），但纯 ![] 会被 bare 路径排除
        body = f"附图：\n![截图]({ASSETS})"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is False

    def test_image_with_chapter_still_skips_image_only(self):
        body = f"对照 3.2\n![截图]({ASSETS})"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is False

    def test_file_link_overrides_same_url_used_as_image(self):
        body = f"对照 3.2\n[a.pdf]({ASSETS})\n![x]({ASSETS})"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is True
        assert ASSETS in intent.attachment_urls

    def test_bare_assets_with_chapter_only(self):
        """产品路径：只写章节号 + 拖文件（正文不一定出现 PRD 字样）。"""
        body = f"本期对照 3.2、3.5 改造退款失败。\n{ASSETS}"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is True

    def test_bare_assets_without_prd_or_chapter_skips(self):
        body = f"随便贴个链接\n{ASSETS}"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is False

    def test_bare_docx_url(self):
        body = "见 https://example.com/docs/需求.docx 章节 4.1"
        intent = parse_prd_intent(body)
        assert intent.should_run_requirement_review is True
        assert "需求.docx" in intent.primary_url

    def test_empty_body(self):
        intent = parse_prd_intent("")
        assert intent.should_run_requirement_review is False


class TestExtractDescriptionBody:
    def test_github(self):
        body = extract_description_body({"pull_request": {"body": "hello"}})
        assert body == "hello"

    def test_gitlab(self):
        body = extract_description_body({"object_attributes": {"description": "mr"}})
        assert body == "mr"
