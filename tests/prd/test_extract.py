from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from docx import Document

from biz.prd.extract import (
    cleanup_stale_prd_temps,
    download_and_extract,
    extract_bytes,
    prd_tmp_root,
)


def _make_docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestExtractBytes:
    def test_docx_ok(self):
        data = _make_docx_bytes("退款失败要更新订单状态")
        result = extract_bytes(data, url="https://x/a.docx", content_type="")
        assert result.ok is True
        assert "退款失败" in result.text

    def test_empty_bytes(self):
        result = extract_bytes(b"", url="https://x/a.pdf")
        assert result.ok is False
        assert "空" in result.reason

    def test_legacy_doc_rejected(self):
        result = extract_bytes(b"\xd0\xcf\x11\xe0", url="https://x/a.doc")
        assert result.ok is False
        assert ".doc" in result.reason

    def test_image_magic_rejected(self):
        # PNG magic — typical mistaken GitHub assets upload
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        result = extract_bytes(png, url="https://github.com/user-attachments/assets/uuid")
        assert result.ok is False
        assert "图片" in result.reason


class TestDownloadCleanup:
    def test_temp_file_deleted_after_download(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRD_TMP_DIR", str(tmp_path))
        data = _make_docx_bytes("hello prd")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        mock_resp.iter_content = lambda chunk_size=65536: [data]
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda *a: False

        with patch("biz.prd.extract.requests.get", return_value=mock_resp):
            result = download_and_extract("https://example.com/a.docx", token="t")

        assert result.ok is True
        leftovers = list(Path(tmp_path).glob("prd_*"))
        assert leftovers == [], f"temp PRD files should be deleted, found {leftovers}"

    def test_cleanup_stale(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRD_TMP_DIR", str(tmp_path))
        stale = prd_tmp_root() / "prd_old.bin"
        stale.write_bytes(b"x")
        # Force mtime into the past
        import os
        os.utime(stale, (0, 0))
        n = cleanup_stale_prd_temps(max_age_seconds=1)
        assert n == 1
        assert not stale.exists()
