import datetime

import pandas as pd

from biz.mock.dashboard_mock import PROJECTS, DashboardMockProvider
from biz.mock.dashboard_mock_gate import is_mock_query_unlocked
from biz.utils.dashboard_view import enrich_review_frame


def setup_function():
    DashboardMockProvider.reset_cache()


def test_query_gate_only_unlocks_with_query_1():
    assert is_mock_query_unlocked({"query": "1"}) is True
    assert is_mock_query_unlocked({"query": "0"}) is False
    assert is_mock_query_unlocked({}) is False
    assert is_mock_query_unlocked(None) is False


def test_mock_has_ten_multilingual_projects():
    names = {p["name"] for p in PROJECTS}
    assert len(names) == 10
    assert "ai-cr-test1" in names
    assert "ai-cr-test2" in names
    assert "pedido-core-java" in names
    assert "zahlung-gateway-java" in names
    assert "datenpipeline-etl-py" in names
    stacks = {p["stack"] for p in PROJECTS}
    assert stacks == {"frontend", "test", "java", "python"}


def test_mock_mr_dataset_rich_and_filterable():
    df = DashboardMockProvider.get_mr_review_logs()
    assert len(df) == 196
    assert df["project_name"].nunique() == 10
    assert df["author"].nunique() >= 8
    assert (df["additions"] >= 0).all()
    assert df["url"].str.startswith("https://github.com/").all()

    enriched = enrich_review_frame(df)
    kinds = set(enriched["kind"].unique())
    assert "with_prd" in kinds
    assert "no_prd" in kinds
    assert "legacy" in kinds

    start = int(datetime.datetime(2025, 8, 1).timestamp())
    end = int(datetime.datetime(2026, 10, 8, 23, 59, 59).timestamp())
    scoped = DashboardMockProvider.get_mr_review_logs(updated_at_gte=start, updated_at_lte=end)
    assert len(scoped) == len(df)

    one_proj = DashboardMockProvider.get_mr_review_logs(project_names=["ai-cr-test1"])
    assert (one_proj["project_name"] == "ai-cr-test1").all()
    assert len(one_proj) >= 5


def test_mock_push_dataset():
    df = DashboardMockProvider.get_push_review_logs()
    assert len(df) == 58
    assert "branch" in df.columns
    assert df["project_name"].nunique() >= 8


def test_mock_is_deterministic():
    a = DashboardMockProvider.get_mr_review_logs()
    DashboardMockProvider.reset_cache()
    b = DashboardMockProvider.get_mr_review_logs()
    pd.testing.assert_frame_equal(a, b)


def test_mock_review_reports_are_substantial():
    df = DashboardMockProvider.get_mr_review_logs()
    assert df["review_result"].str.len().min() > 800
    with_prd = df[df["review_result"].str.contains("已覆盖")]
    assert len(with_prd) > 0
    sample = with_prd.iloc[0]["review_result"]
    assert sample.count("- ") >= 18
    assert "变更摘要" in sample or "完成度" in sample
    assert "安全" in sample and "性能" in sample
