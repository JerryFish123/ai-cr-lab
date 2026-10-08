"""Dashboard demo/mock data — isolated from ReviewService and MySQL."""

from biz.mock.dashboard_mock import DashboardMockProvider
from biz.mock.dashboard_mock_gate import is_mock_query_unlocked

__all__ = ["DashboardMockProvider", "is_mock_query_unlocked"]
