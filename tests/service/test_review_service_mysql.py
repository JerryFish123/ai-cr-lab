import importlib
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity


@pytest.fixture
def mysql_env(monkeypatch):
    monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_USER", "ai_cr")
    monkeypatch.setenv("MYSQL_PASSWORD", "secret")
    monkeypatch.setenv("MYSQL_DATABASE", "ai_cr_lab")


@pytest.fixture
def review_service(mysql_env, monkeypatch):
    monkeypatch.setenv("REVIEW_DB_AUTO_INIT", "0")
    import biz.service.review_service as mod

    importlib.reload(mod)
    mod.ReviewService._initialized = False
    return mod.ReviewService


class TestMysqlConfig:
    def test_missing_host_raises(self, monkeypatch):
        monkeypatch.delenv("MYSQL_HOST", raising=False)
        monkeypatch.setenv("MYSQL_USER", "u")
        monkeypatch.setenv("MYSQL_PASSWORD", "p")
        monkeypatch.setenv("MYSQL_DATABASE", "d")
        import biz.service.review_service as mod

        with pytest.raises(RuntimeError, match="MYSQL_HOST"):
            mod.ReviewService._mysql_config()

    def test_config_ok(self, mysql_env):
        import biz.service.review_service as mod

        cfg = mod.ReviewService._mysql_config()
        assert cfg["host"] == "127.0.0.1"
        assert cfg["port"] == 3306
        assert cfg["charset"] == "utf8mb4"


class TestInitAndQueries:
    def test_init_db_creates_tables_and_indexes(self, review_service):
        cursor = MagicMock()
        # first two execute: CREATE TABLE; then for each index: SELECT then maybe CREATE
        cursor.fetchone.side_effect = [None, None]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = lambda s: s
        conn.__exit__ = lambda *a: False

        with patch.object(review_service, "_connect", return_value=conn):
            review_service.init_db()

        sqls = [c.args[0] for c in cursor.execute.call_args_list if c.args]
        joined = "\n".join(str(s) for s in sqls)
        assert "CREATE TABLE IF NOT EXISTS mr_review_log" in joined
        assert "CREATE TABLE IF NOT EXISTS push_review_log" in joined
        assert "CREATE INDEX idx_mr_review_log_updated_at" in joined
        assert "CREATE INDEX idx_push_review_log_updated_at" in joined
        assert review_service._initialized is True

    def test_insert_mr_uses_percent_s(self, review_service):
        cursor = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = lambda s: s
        conn.__exit__ = lambda *a: False

        entity = MergeRequestReviewEntity(
            project_name="demo",
            author="alice",
            source_branch="feat",
            target_branch="main",
            updated_at=1,
            commits=[{"message": "msg"}],
            score=80,
            url="https://example.com",
            review_result="ok",
            url_slug="slug",
            webhook_data={},
            additions=1,
            deletions=0,
            last_commit_id="abc",
        )
        review_service._initialized = True
        with patch.object(review_service, "_connect", return_value=conn):
            review_service.insert_mr_review_log(entity)

        sql = cursor.execute.call_args[0][0]
        assert "%s" in sql
        assert "?" not in sql
        assert "INSERT INTO mr_review_log" in sql

    def test_check_last_commit_id(self, review_service):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = lambda s: s
        conn.__exit__ = lambda *a: False
        review_service._initialized = True
        with patch.object(review_service, "_connect", return_value=conn):
            assert (
                review_service.check_mr_last_commit_id_exists("p", "s", "t", "sha")
                is True
            )
        assert "%s" in cursor.execute.call_args[0][0]

    def test_get_mr_logs_uses_pandas(self, review_service):
        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = lambda *a: False
        review_service._initialized = True
        fake_df = pd.DataFrame([{"project_name": "demo", "author": "a"}])
        with patch.object(review_service, "_connect", return_value=conn):
            with patch(
                "biz.service.review_service.pd.read_sql_query",
                return_value=fake_df,
            ) as read_sql:
                df = review_service.get_mr_review_logs(authors=["a"])
        assert list(df["project_name"]) == ["demo"]
        sql = read_sql.call_args.kwargs.get("sql") or read_sql.call_args[0][0]
        assert "author IN (%s)" in sql

    def test_insert_push_log(self, review_service):
        cursor = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = lambda s: s
        conn.__exit__ = lambda *a: False
        entity = PushReviewEntity(
            project_name="demo",
            author="bob",
            branch="main",
            updated_at=2,
            commits=[{"message": "p"}],
            score=70,
            review_result="r",
            url_slug="s",
            webhook_data={},
            additions=2,
            deletions=1,
        )
        review_service._initialized = True
        with patch.object(review_service, "_connect", return_value=conn):
            review_service.insert_push_review_log(entity)
        assert "INSERT INTO push_review_log" in cursor.execute.call_args[0][0]
        assert "%s" in cursor.execute.call_args[0][0]


def test_no_sqlite_import():
    import biz.service.review_service as mod
    import inspect

    source = inspect.getsource(mod)
    assert "sqlite3" not in source
    assert "pymysql" in source
