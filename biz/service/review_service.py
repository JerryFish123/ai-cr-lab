"""Review log persistence backed by MySQL (PyMySQL)."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import pandas as pd
import pymysql
from pymysql.connections import Connection

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity
from biz.utils.log import logger


class ReviewService:
    _initialized = False

    @staticmethod
    def _mysql_config() -> dict:
        host = (os.getenv("MYSQL_HOST") or "").strip()
        user = (os.getenv("MYSQL_USER") or "").strip()
        password = os.getenv("MYSQL_PASSWORD")
        database = (os.getenv("MYSQL_DATABASE") or "").strip()
        port_raw = (os.getenv("MYSQL_PORT") or "3306").strip()

        missing = [
            name
            for name, value in (
                ("MYSQL_HOST", host),
                ("MYSQL_USER", user),
                ("MYSQL_DATABASE", database),
            )
            if not value
        ]
        if not password:
            missing.append("MYSQL_PASSWORD")
        if missing:
            raise RuntimeError(
                "MySQL 配置缺失: "
                + ", ".join(missing)
                + "。请在 conf/.env 中配置，或通过 docker-compose 注入。"
            )
        try:
            port = int(port_raw)
        except ValueError as e:
            raise RuntimeError(f"MYSQL_PORT 无效: {port_raw!r}") from e

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password if password is not None else "",
            "database": database,
            "charset": "utf8mb4",
            "autocommit": False,
            "cursorclass": pymysql.cursors.Cursor,
        }

    @staticmethod
    def _connect() -> Connection:
        return pymysql.connect(**ReviewService._mysql_config())

    @staticmethod
    @contextmanager
    def _connection() -> Iterator[Connection]:
        conn = ReviewService._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def init_db() -> None:
        """初始化数据库及表结构。"""
        try:
            with ReviewService._connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mr_review_log (
                        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        project_name VARCHAR(255) NULL,
                        author VARCHAR(255) NULL,
                        source_branch VARCHAR(255) NULL,
                        target_branch VARCHAR(255) NULL,
                        updated_at BIGINT NULL,
                        commit_messages TEXT NULL,
                        score INT NULL,
                        url TEXT NULL,
                        review_result MEDIUMTEXT NULL,
                        additions INT NOT NULL DEFAULT 0,
                        deletions INT NOT NULL DEFAULT 0,
                        last_commit_id VARCHAR(255) NOT NULL DEFAULT ''
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS push_review_log (
                        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        project_name VARCHAR(255) NULL,
                        author VARCHAR(255) NULL,
                        branch VARCHAR(255) NULL,
                        updated_at BIGINT NULL,
                        commit_messages TEXT NULL,
                        score INT NULL,
                        review_result MEDIUMTEXT NULL,
                        additions INT NOT NULL DEFAULT 0,
                        deletions INT NOT NULL DEFAULT 0
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                # Prefer information_schema guard over CREATE INDEX IF NOT EXISTS
                # for broader MySQL compatibility.
                for table, index_name, column in (
                    ("mr_review_log", "idx_mr_review_log_updated_at", "updated_at"),
                    ("push_review_log", "idx_push_review_log_updated_at", "updated_at"),
                ):
                    cursor.execute(
                        """
                        SELECT 1 FROM information_schema.statistics
                        WHERE table_schema = DATABASE()
                          AND table_name = %s
                          AND index_name = %s
                        LIMIT 1
                        """,
                        (table, index_name),
                    )
                    if cursor.fetchone() is None:
                        cursor.execute(
                            f"CREATE INDEX {index_name} ON {table} ({column})"
                        )
            ReviewService._initialized = True
            logger.info("MySQL review tables ready")
        except Exception as e:
            logger.error("Database initialization failed: %s", e)
            raise

    @staticmethod
    def _ensure_db() -> None:
        if not ReviewService._initialized:
            ReviewService.init_db()

    @staticmethod
    def insert_mr_review_log(entity: MergeRequestReviewEntity) -> None:
        """插入合并请求审核日志"""
        ReviewService._ensure_db()
        try:
            with ReviewService._connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO mr_review_log (
                        project_name, author, source_branch, target_branch,
                        updated_at, commit_messages, score, url, review_result,
                        additions, deletions, last_commit_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entity.project_name,
                        entity.author,
                        entity.source_branch,
                        entity.target_branch,
                        entity.updated_at,
                        entity.commit_messages,
                        entity.score,
                        entity.url,
                        entity.review_result,
                        entity.additions,
                        entity.deletions,
                        entity.last_commit_id,
                    ),
                )
        except Exception as e:
            logger.error("Error inserting MR review log: %s", e)

    @staticmethod
    def get_mr_review_logs(
        authors: list = None,
        project_names: list = None,
        updated_at_gte: int = None,
        updated_at_lte: int = None,
    ) -> pd.DataFrame:
        """获取符合条件的合并请求审核日志"""
        ReviewService._ensure_db()
        try:
            query = """
                SELECT project_name, author, source_branch, target_branch,
                       updated_at, commit_messages, score, url, review_result,
                       additions, deletions
                FROM mr_review_log
                WHERE 1=1
            """
            params: list = []

            if authors:
                placeholders = ", ".join(["%s"] * len(authors))
                query += f" AND author IN ({placeholders})"
                params.extend(authors)

            if project_names:
                placeholders = ", ".join(["%s"] * len(project_names))
                query += f" AND project_name IN ({placeholders})"
                params.extend(project_names)

            if updated_at_gte is not None:
                query += " AND updated_at >= %s"
                params.append(updated_at_gte)

            if updated_at_lte is not None:
                query += " AND updated_at <= %s"
                params.append(updated_at_lte)

            query += " ORDER BY updated_at DESC"
            with ReviewService._connection() as conn:
                return pd.read_sql_query(sql=query, con=conn, params=params)
        except Exception as e:
            logger.error("Error retrieving MR review logs: %s", e)
            return pd.DataFrame()

    @staticmethod
    def check_mr_last_commit_id_exists(
        project_name: str,
        source_branch: str,
        target_branch: str,
        last_commit_id: str,
    ) -> bool:
        """检查指定项目的 Merge Request 是否已经存在相同的 last_commit_id"""
        ReviewService._ensure_db()
        try:
            with ReviewService._connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM mr_review_log
                    WHERE project_name = %s AND source_branch = %s
                      AND target_branch = %s AND last_commit_id = %s
                    """,
                    (project_name, source_branch, target_branch, last_commit_id),
                )
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            logger.error("Error checking last_commit_id: %s", e)
            return False

    @staticmethod
    def insert_push_review_log(entity: PushReviewEntity) -> None:
        """插入推送审核日志"""
        ReviewService._ensure_db()
        try:
            with ReviewService._connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO push_review_log (
                        project_name, author, branch, updated_at, commit_messages,
                        score, review_result, additions, deletions
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entity.project_name,
                        entity.author,
                        entity.branch,
                        entity.updated_at,
                        entity.commit_messages,
                        entity.score,
                        entity.review_result,
                        entity.additions,
                        entity.deletions,
                    ),
                )
        except Exception as e:
            logger.error("Error inserting push review log: %s", e)

    @staticmethod
    def get_push_review_logs(
        authors: list = None,
        project_names: list = None,
        updated_at_gte: int = None,
        updated_at_lte: int = None,
    ) -> pd.DataFrame:
        """获取符合条件的推送审核日志"""
        ReviewService._ensure_db()
        try:
            query = """
                SELECT project_name, author, branch, updated_at, commit_messages,
                       score, review_result, additions, deletions
                FROM push_review_log
                WHERE 1=1
            """
            params: list = []

            if authors:
                placeholders = ", ".join(["%s"] * len(authors))
                query += f" AND author IN ({placeholders})"
                params.extend(authors)

            if project_names:
                placeholders = ", ".join(["%s"] * len(project_names))
                query += f" AND project_name IN ({placeholders})"
                params.extend(project_names)

            if updated_at_gte is not None:
                query += " AND updated_at >= %s"
                params.append(updated_at_gte)

            if updated_at_lte is not None:
                query += " AND updated_at <= %s"
                params.append(updated_at_lte)

            query += " ORDER BY updated_at DESC"
            with ReviewService._connection() as conn:
                return pd.read_sql_query(sql=query, con=conn, params=params)
        except Exception as e:
            logger.error("Error retrieving push review logs: %s", e)
            return pd.DataFrame()


# Eager init when MySQL is configured (Docker / production).
# Set REVIEW_DB_AUTO_INIT=0 in unit tests to skip connect-on-import.
if os.getenv("MYSQL_HOST") and os.getenv("REVIEW_DB_AUTO_INIT", "1") != "0":
    ReviewService.init_db()
