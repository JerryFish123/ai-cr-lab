# -*- coding: utf-8 -*-
import math
from pathlib import Path

import streamlit as st

st.set_page_config(layout="wide", page_title="ai-cr-lab", page_icon="🔬", initial_sidebar_state="collapsed")

import datetime
import os
import hashlib
import hmac
import base64
import time
import pandas as pd
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.font_manager as fm
from matplotlib.ticker import MaxNLocator
from streamlit_cookies_manager import CookieManager

load_dotenv("conf/.env")

from biz.mock.dashboard_mock import DashboardMockProvider
from biz.mock.dashboard_mock_gate import is_mock_query_unlocked
from biz.service.review_service import ReviewService
from biz.utils.dashboard_view import count_prd_reviews, enrich_review_frame, filter_enriched_frame

ReviewService.init_db()

# --- Brand palette ---
C_PRIMARY = "#0f766e"
C_PRIMARY_LIGHT = "#14b8a6"
C_INK = "#0c1222"
C_MUTED = "#64748b"
C_BORDER = "#d7e0ea"
C_ADD = "#34d399"
C_DEL = "#f87171"

# Zone tints (functional area backgrounds — not pure white)
Z_FILTER_BG = ("#ecfdf5", "#f0fdfa")
Z_METRIC_BGS = [
    ("#ecfdf5", "#d1fae5"),  # teal — 总审查
    ("#eff6ff", "#dbeafe"),  # blue — 项目数
    ("#fff7ed", "#ffedd5"),  # amber — 行数
    ("#f5f3ff", "#ede9fe"),  # violet — PRD
]
Z_CHART_BG = ("#f0f9ff", "#e0f2fe")
Z_TABLE_BG = "#fffbeb"
Z_DETAIL_BG = ("#fefce8", "#fef9c3")


def set_global_font():
    font_path = "fonts/SourceHanSansCN-Regular.otf"
    if Path(font_path).exists():
        try:
            fm.fontManager.addfont(font_path)
            mpl.rcParams["font.family"] = "Source Han Sans CN"
        except Exception as e:
            st.warning(f"字体加载失败，使用默认字体。错误信息：{e}")
    else:
        st.warning(f"字体文件未找到：{font_path}，将使用默认字体。")
    mpl.rcParams["axes.unicode_minus"] = False


set_global_font()

DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")
USER_CREDENTIALS = {DASHBOARD_USER: DASHBOARD_PASSWORD}
SECRET_KEY = os.getenv(
    "DASHBOARD_SECRET_KEY",
    "fac8cf149bdd616c07c1a675c4571ccacc40d7f7fe16914cfe0f9f9d966bb773",
)
cookies = CookieManager()


def generate_token(username):
    timestamp = str(int(time.time()))
    message = f"{username}:{timestamp}"
    signature = hmac.new(SECRET_KEY.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(f"{message}:{base64.b64encode(signature).decode()}".encode()).decode()


def verify_token(token):
    try:
        decoded = base64.b64decode(token.encode()).decode()
        message, signature = decoded.rsplit(":", 1)
        username, timestamp = message.split(":", 1)
        expected_signature = hmac.new(SECRET_KEY.encode(), message.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected_signature, base64.b64decode(signature)):
            return None
        if int(time.time()) - int(timestamp) > 30 * 24 * 60 * 60:
            return None
        return username
    except Exception:
        return None


def check_login_status():
    if not cookies.ready():
        st.stop()
    if "login_status" not in st.session_state:
        st.session_state["login_status"] = False
    auth_token = cookies.get("auth_token")
    if auth_token:
        username = verify_token(auth_token)
        if username and username in USER_CREDENTIALS:
            st.session_state["login_status"] = True
            st.session_state["username"] = username
            st.session_state["saved_username"] = username
    return st.session_state["login_status"]


def set_login_status(username, remember):
    st.session_state["login_status"] = True
    st.session_state["username"] = username
    st.session_state["saved_username"] = username if remember else ""
    if remember:
        cookies["auth_token"] = generate_token(username)
    elif "auth_token" in cookies:
        del cookies["auth_token"]
    cookies.save()


def get_saved_credentials():
    auth_token = cookies.get("auth_token")
    if auth_token:
        username = verify_token(auth_token)
        if username:
            return username, ""
    return st.session_state.get("saved_username", ""), ""


def authenticate(username, password, remember_password=False):
    if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
        set_login_status(username, remember_password)
        return True
    return False


def get_data(service_func, authors=None, project_names=None, updated_at_gte=None, updated_at_lte=None, columns=None):
    df = service_func(
        authors=authors,
        project_names=project_names,
        updated_at_gte=updated_at_gte,
        updated_at_lte=updated_at_lte,
    )
    if df.empty:
        return pd.DataFrame(columns=columns)
    if "updated_at" in df.columns:
        df["updated_at"] = df["updated_at"].apply(
            lambda ts: datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(ts, (int, float))
            else ts
        )

    def format_delta(row):
        if not math.isnan(row["additions"]) and not math.isnan(row["deletions"]):
            return f"+{int(row['additions'])}  -{int(row['deletions'])}"
        return ""

    if "additions" in df.columns and "deletions" in df.columns:
        df["delta"] = df.apply(format_delta, axis=1)
    else:
        df["delta"] = ""
    return df[columns]


def _parse_date_range(range_val, default_start, default_end):
    if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
        start_date, end_date = range_val[0], range_val[1]
    elif isinstance(range_val, datetime.date):
        start_date = end_date = range_val
    else:
        start_date, end_date = default_start, default_end
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def _chart_figsize(n_rows: int) -> tuple[float, float]:
    """Height scales with bar count so charts stay compact and readable."""
    n = max(int(n_rows), 1)
    height = max(2.0, min(0.38 * n + 0.9, 6.5))
    return (6.8, height)


def _style_chart_axes(ax, *, horizontal=False):
    ax.set_facecolor("#f0f9ff")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(C_BORDER)
    ax.spines["bottom"].set_color(C_BORDER)
    ax.tick_params(colors=C_MUTED, labelsize=9)
    ax.grid(axis="x" if horizontal else "y", color="#e8edf2", linestyle="-", linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)


def _annotate_hbars(ax, bars, fmt="{:.0f}"):
    xmax = ax.get_xlim()[1] or 1
    pad = max(xmax * 0.03, 0.15)
    for bar in bars:
        w = bar.get_width()
        if w == 0:
            continue
        ax.text(
            w + pad,
            bar.get_y() + bar.get_height() / 2,
            fmt.format(w),
            va="center",
            ha="left",
            fontsize=8,
            color=C_INK,
            fontweight=600,
        )


def _zone_band(label: str, zone: str, hint: str = ""):
    hint_html = f'<span class="zone-hint">{hint}</span>' if hint else ""
    st.markdown(
        f'<div class="zone-band zone-{zone}">'
        f'<span class="zone-label">{label}</span>{hint_html}</div>',
        unsafe_allow_html=True,
    )


def _render_chart_panel(title: str, subtitle: str, render_fn):
    """Native Streamlit bordered container — charts must live inside, not in raw HTML."""
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if subtitle:
            st.caption(subtitle)
        render_fn()


def generate_count_chart(df, group_col: str, *, color: str = C_PRIMARY):
    if df.empty:
        st.info("暂无数据")
        return
    counts = df[group_col].value_counts().reset_index()
    counts.columns = [group_col, "count"]
    counts = counts.sort_values("count", ascending=True).tail(12)

    fig, ax = plt.subplots(figsize=_chart_figsize(len(counts)))
    y_pos = range(len(counts))
    bars = ax.barh(
        y_pos,
        counts["count"],
        color=color,
        height=0.65,
        edgecolor="white",
        linewidth=0.6,
    )
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(counts[group_col], fontsize=9)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    _style_chart_axes(ax, horizontal=True)
    _annotate_hbars(ax, bars)
    ax.set_xlabel("审查次数", fontsize=9, color=C_MUTED, labelpad=6)
    ax.margins(x=0.12)
    plt.tight_layout(pad=0.6)
    st.pyplot(fig, use_container_width=True, clear_figure=True)


def generate_delta_chart(df, group_col: str):
    if df.empty:
        st.info("暂无数据")
        return
    if "additions" not in df.columns or "deletions" not in df.columns:
        st.warning("缺少 additions / deletions 列，无法绘制行数图")
        return

    add = df.groupby(group_col)["additions"].sum().reset_index()
    add.columns = [group_col, "additions"]
    sub = df.groupby(group_col)["deletions"].sum().reset_index()
    sub.columns = [group_col, "deletions"]
    merged = add.merge(sub, on=group_col, how="outer").fillna(0)
    merged["total"] = merged["additions"] + merged["deletions"]
    merged = merged.sort_values("total", ascending=True).tail(12)

    fig, ax = plt.subplots(figsize=_chart_figsize(len(merged)))
    y = range(len(merged))
    h = 0.34
    ax.barh([i - h / 2 for i in y], merged["additions"], height=h, color=C_ADD, label="新增", edgecolor="white")
    ax.barh([i + h / 2 for i in y], merged["deletions"], height=h, color=C_DEL, label="删除", edgecolor="white")
    ax.set_yticks(list(y))
    ax.set_yticklabels(merged[group_col], fontsize=9)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    _style_chart_axes(ax, horizontal=True)
    ax.set_xlabel("行数", fontsize=9, color=C_MUTED, labelpad=6)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    ax.margins(x=0.12)
    plt.tight_layout(pad=0.6)
    st.pyplot(fig, use_container_width=True, clear_figure=True)


# --- Global CSS ---
st.markdown(
    f"""
    <style>
    #MainMenu {{visibility: hidden;}}
    header[data-testid="stHeader"] {{display: none !important;}}
    footer {{visibility: hidden;}}
    div.block-container {{
        padding-top: 0.75rem !important;
        padding-bottom: 1.5rem !important;
        max-width: 1200px;
    }}
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: "Outfit", "Source Han Sans CN", sans-serif; }}
    .main {{
        background:
          radial-gradient(900px 420px at 100% -8%, rgba(20, 184, 166, 0.14), transparent 55%),
          radial-gradient(700px 380px at 0% 20%, rgba(59, 130, 246, 0.08), transparent 50%),
          linear-gradient(180deg, #eef2f7 0%, #e2e8f0 100%);
    }}
    .stButton>button {{
        background: linear-gradient(135deg, #0f766e, #0d9488);
        color: white; border: none; border-radius: 10px; font-weight: 600;
    }}
    .stButton>button:hover {{ box-shadow: 0 4px 14px rgba(15, 118, 110, 0.25); }}

    /* ── Top header bar ── */
    .dash-header-bar {{
        background: linear-gradient(135deg, #0f766e 0%, #134e4a 55%, #115e59 100%);
        border-radius: 14px; padding: 0.85rem 1.15rem; margin-bottom: 0.65rem;
        box-shadow: 0 4px 18px rgba(15, 118, 110, 0.22);
    }}
    .dash-header-bar .name {{ font-size: 1.35rem; font-weight: 700; color: #f0fdfa; letter-spacing: -0.02em; }}
    .dash-header-bar .tag {{ font-size: 0.8rem; color: #99f6e4; margin-top: 0.1rem; }}
    a.pro-link {{
        display: inline-flex; align-items: center; justify-content: center;
        padding: 0.4rem 0.9rem; background: rgba(255,255,255,0.14); color: #ecfdf5 !important;
        text-decoration: none; border-radius: 10px; font-size: 0.85rem; font-weight: 600;
        border: 1px solid rgba(255,255,255,0.22);
    }}
    a.pro-link:hover {{ background: rgba(255,255,255,0.22); }}

    /* ── Zone section bands ── */
    .zone-band {{
        display: flex; align-items: center; gap: 0.55rem;
        padding: 0.45rem 0.75rem; border-radius: 10px 10px 0 0;
        margin-top: 0.85rem; margin-bottom: 0;
        font-size: 0.82rem; font-weight: 700; letter-spacing: 0.04em;
    }}
    .zone-band .zone-hint {{ font-weight: 500; font-size: 0.76rem; opacity: 0.85; margin-left: auto; }}
    .zone-band.zone-filter {{ background: linear-gradient(90deg, #0f766e, #14b8a6); color: #ecfdf5; }}
    .zone-band.zone-metrics {{ background: linear-gradient(90deg, #1e40af, #3b82f6); color: #eff6ff; }}
    .zone-band.zone-charts {{ background: linear-gradient(90deg, #0369a1, #0ea5e9); color: #f0f9ff; }}
    .zone-band.zone-records {{ background: linear-gradient(90deg, #b45309, #f59e0b); color: #fffbeb; }}

    /* ── Filter panel (teal tint) ── */
    .element-container:has(.zone-filter) + .element-container [data-testid="stVerticalBlockBorderWrapper"] {{
        background: linear-gradient(145deg, {Z_FILTER_BG[0]} 0%, {Z_FILTER_BG[1]} 100%) !important;
        border-color: #5eead4 !important;
        border-top: none !important;
        border-radius: 0 0 12px 12px !important;
        padding: 0.75rem 0.9rem 0.5rem !important;
        box-shadow: 0 2px 10px rgba(15, 118, 110, 0.08);
    }}

    /* ── Metric cards (4 distinct tints) ── */
    div[data-testid="stMetric"] {{
        border-radius: 12px; padding: 0.55rem 0.75rem;
        box-shadow: 0 2px 6px rgba(15,23,42,0.06);
    }}
    div[data-testid="stMetric"] label {{ font-size: 0.78rem !important; font-weight: 600 !important; }}
    div[data-testid="stMetricValue"] {{ font-weight: 800 !important; font-size: 1.45rem !important; }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(1) [data-testid="stMetric"] {{
        background: linear-gradient(135deg, {Z_METRIC_BGS[0][0]}, {Z_METRIC_BGS[0][1]});
        border: 1px solid #6ee7b7;
    }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(1) [data-testid="stMetric"] label {{ color: #047857 !important; }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(1) [data-testid="stMetricValue"] {{ color: #064e3b !important; }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(2) [data-testid="stMetric"] {{
        background: linear-gradient(135deg, {Z_METRIC_BGS[1][0]}, {Z_METRIC_BGS[1][1]});
        border: 1px solid #93c5fd;
    }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(2) [data-testid="stMetric"] label {{ color: #1d4ed8 !important; }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(2) [data-testid="stMetricValue"] {{ color: #1e3a8a !important; }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(3) [data-testid="stMetric"] {{
        background: linear-gradient(135deg, {Z_METRIC_BGS[2][0]}, {Z_METRIC_BGS[2][1]});
        border: 1px solid #fdba74;
    }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(3) [data-testid="stMetric"] label {{ color: #c2410c !important; }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(3) [data-testid="stMetricValue"] {{ color: #9a3412 !important; }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(4) [data-testid="stMetric"] {{
        background: linear-gradient(135deg, {Z_METRIC_BGS[3][0]}, {Z_METRIC_BGS[3][1]});
        border: 1px solid #c4b5fd;
    }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(4) [data-testid="stMetric"] label {{ color: #6d28d9 !important; }}
    .element-container:has(.zone-metrics) + .element-container [data-testid="column"]:nth-child(4) [data-testid="stMetricValue"] {{ color: #4c1d95 !important; }}

    /* ── Chart panels (sky blue tint) ── */
    .element-container:has(.zone-charts) ~ .element-container:has([data-testid="stVerticalBlockBorderWrapper"]) [data-testid="stVerticalBlockBorderWrapper"] {{
        background: linear-gradient(180deg, {Z_CHART_BG[0]} 0%, {Z_CHART_BG[1]} 100%) !important;
        border-color: #7dd3fc !important;
        border-radius: 12px !important;
        padding: 0.65rem 0.85rem 0.45rem !important;
        box-shadow: 0 2px 8px rgba(14, 165, 233, 0.10);
    }}
    .element-container:has(.zone-charts) ~ .element-container:has([data-testid="stVerticalBlockBorderWrapper"]) [data-testid="stVerticalBlockBorderWrapper"] p {{
        color: #0c4a6e;
    }}
    div[data-testid="stPyplotGlobalElement"] {{ margin-top: -0.25rem; padding-bottom: 0 !important; }}
    div[data-testid="stPyplotGlobalElement"] img {{ display: block; width: 100%; height: auto; }}

    /* ── Records table (warm amber tint) ── */
    .element-container:has(.zone-records) + .element-container [data-testid="stDataFrame"] {{
        border: 1px solid #fcd34d; border-radius: 0 0 12px 12px; overflow: hidden;
        box-shadow: 0 2px 10px rgba(245, 158, 11, 0.10);
    }}
    .element-container:has(.zone-records) + .element-container [data-testid="stDataFrame"] > div {{
        background: {Z_TABLE_BG};
    }}

    /* ── Report expander (soft yellow) ── */
    div[data-testid="stExpander"] {{
        background: linear-gradient(180deg, {Z_DETAIL_BG[0]}, {Z_DETAIL_BG[1]}) !important;
        border: 1px solid #fde047 !important; border-radius: 12px !important;
    }}
    div[data-testid="stExpander"] summary {{ color: #854d0e !important; font-weight: 600; }}

    /* ── Tabs ── */
    [data-testid="stTabs"] {{
        background: linear-gradient(180deg, #f0fdfa, #ccfbf1);
        border: 1px solid #99f6e4; border-radius: 12px;
        padding: 0.35rem 0.75rem 0.15rem; margin-bottom: 0.25rem;
    }}
    [data-testid="stTabs"] button {{ font-weight: 600; color: #0f766e !important; }}
    [data-testid="stTabs"] [aria-selected="true"] {{
        color: #134e4a !important; border-color: #0f766e !important;
        background: rgba(255,255,255,0.55); border-radius: 8px 8px 0 0;
    }}

    .empty-panel {{
        margin: 0.75rem 0; padding: 1.75rem 1rem; border: 1px dashed #94a3b8;
        border-radius: 12px; background: linear-gradient(180deg, #f1f5f9, #e2e8f0); text-align: center;
    }}
    .empty-panel h3 {{ margin: 0 0 0.35rem; color: #0c1222; font-size: 1.05rem; }}
    .empty-panel p {{ margin: 0; color: #64748b; font-size: 0.9rem; }}

    /* ── Login ── */
    .login-container {{
        background: linear-gradient(160deg, #ecfdf5 0%, #f0fdfa 40%, #eff6ff 100%);
        border: 1px solid #99f6e4; border-radius: 16px;
        padding: 1rem; box-shadow: 0 10px 40px rgba(15,118,110,0.10);
    }}
    .login-title {{ text-align: center; color: #134e4a; font-size: 2rem; font-weight: 700; }}
    .login-sub {{ text-align: center; color: #64748b; font-size: 0.92rem; }}
    .platform-mark {{
        text-align: center; font-size: 0.75rem; font-weight: 700;
        letter-spacing: 0.16em; color: #0f766e; margin-top: 0.5rem;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown('<div class="platform-mark">AI-CR-LAB</div>', unsafe_allow_html=True)
        st.markdown('<h1 class="login-title">代码审查控制台</h1>', unsafe_allow_html=True)
        st.markdown('<p class="login-sub">GitHub · JerryFish123/ai-cr-lab</p>', unsafe_allow_html=True)
        if DASHBOARD_USER == "admin" and DASHBOARD_PASSWORD == "admin":
            st.warning("检测到默认账号密码 admin/admin，请在 .env 中修改 DASHBOARD_USER / DASHBOARD_PASSWORD。")
        saved_username, saved_password = get_saved_credentials()
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("用户名", value=saved_username)
            password = st.text_input("密码", type="password", value=saved_password)
            remember_password = st.checkbox("记住登录", value=bool(saved_username))
            if st.form_submit_button("登 录"):
                if authenticate(username, password, remember_password):
                    st.rerun()
                else:
                    st.error("用户名或密码错误")
        st.markdown("</div>", unsafe_allow_html=True)


def logout():
    st.session_state["login_status"] = False
    st.session_state.pop("username", None)
    st.session_state.pop("saved_username", None)
    if "auth_token" in cookies:
        del cookies["auth_token"]
    cookies.save()
    st.rerun()


PRO_VERSION_URL = "https://github.com/JerryFish123/ai-cr-lab"


def _row_label(row) -> str:
    return f"{row.get('project_name') or ''} · {row.get('author') or ''} · {row.get('updated_at') or ''}"


def _mock_mode_active() -> bool:
    """?query=1 → auto demo data; no extra click, no MySQL reads for dashboard."""
    return is_mock_query_unlocked(st.query_params)


def _resolve_log_fetcher(use_mock: bool, *, kind: str):
    if use_mock:
        return (
            DashboardMockProvider.get_mr_review_logs
            if kind == "mr"
            else DashboardMockProvider.get_push_review_logs
        )
    svc = ReviewService()
    return svc.get_mr_review_logs if kind == "mr" else svc.get_push_review_logs


def _render_charts(df):
    _zone_band("统计图表", "charts", "审查次数 · 变更行数")
    r1c1, r1c2 = st.columns(2, gap="medium")
    with r1c1:
        _render_chart_panel(
            "项目审查次数",
            "各仓库 PR/MR 审查量（Top 12）",
            lambda: generate_count_chart(df, "project_name", color=C_PRIMARY),
        )
    with r1c2:
        _render_chart_panel(
            "开发者审查次数",
            "按提交者汇总（Top 12）",
            lambda: generate_count_chart(df, "author", color=C_PRIMARY_LIGHT),
        )
    r2c1, r2c2 = st.columns(2, gap="medium")
    with r2c1:
        _render_chart_panel(
            "项目变更行数",
            "绿色 = 新增 · 红色 = 删除",
            lambda: generate_delta_chart(df, "project_name"),
        )
    with r2c2:
        _render_chart_panel(
            "开发者变更行数",
            "绿色 = 新增 · 红色 = 删除",
            lambda: generate_delta_chart(df, "author"),
        )


def main_page():
    h1, h2 = st.columns([7, 3])
    with h1:
        st.markdown(
            '<div class="dash-header-bar"><div class="name">ai-cr-lab</div>'
            '<div class="tag">代码审查统计 · JerryFish123/ai-cr-lab</div></div>',
            unsafe_allow_html=True,
        )
    with h2:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("退出登录", key="logout_button", use_container_width=True):
                logout()
        with c2:
            st.markdown(
                f'<div style="display:flex;justify-content:flex-end;padding-top:0.2rem;">'
                f'<a href="{PRO_VERSION_URL}" target="_blank" class="pro-link">GitHub</a></div>',
                unsafe_allow_html=True,
            )

    use_mock = _mock_mode_active()

    current_date = datetime.date.today()
    start_default = (
        DashboardMockProvider.default_start_date()
        if use_mock
        else current_date - datetime.timedelta(days=90)
    )
    show_push_tab = os.environ.get("PUSH_REVIEW_ENABLED", "0") == "1"

    if show_push_tab:
        mr_tab, push_tab = st.tabs(["合并请求", "代码推送"])
    else:
        mr_tab = st.container()

    def display_data(tab, service_func, columns, column_config, *, has_url: bool):
        with tab:
            _zone_band("筛选条件", "filter", "时间段 · 项目 · PRD · 风险")
            with st.container(border=True):
                fc1, fc2, fc3, fc4 = st.columns([2.2, 1.4, 1.4, 1.4])
                with fc1:
                    date_range = st.date_input(
                        "统计时间段",
                        value=(start_default, current_date),
                        key=f"{tab}_date_range",
                        help="一次选择起止日期",
                    )
                start_date, end_date = _parse_date_range(date_range, start_default, current_date)
                start_ts = int(datetime.datetime.combine(start_date, datetime.time.min).timestamp())
                end_ts = int(datetime.datetime.combine(end_date, datetime.time.max).timestamp())

                raw = get_data(service_func, updated_at_gte=start_ts, updated_at_lte=end_ts, columns=columns)
                base_df = enrich_review_frame(pd.DataFrame(raw))
                unique_authors = sorted(base_df["author"].dropna().unique().tolist()) if not base_df.empty else []
                unique_projects = sorted(base_df["project_name"].dropna().unique().tolist()) if not base_df.empty else []

                with fc2:
                    authors = st.multiselect("开发者", unique_authors, default=[], key=f"{tab}_authors")
                with fc3:
                    project_names = st.multiselect("项目名称", unique_projects, default=[], key=f"{tab}_projects")
                with fc4:
                    prd_filter = st.selectbox("PRD 状态", ["全部", "含PRD", "无PRD", "旧格式"], key=f"{tab}_prd_filter")

                fc5, fc6 = st.columns([1.4, 2.6])
                with fc5:
                    risk_filter = st.selectbox("风险状态", ["全部", "有风险", "无明显风险"], key=f"{tab}_risk_filter")
                with fc6:
                    st.caption(f"当前区间：**{start_date}** → **{end_date}**（共 {(end_date - start_date).days + 1} 天）")

            df = filter_enriched_frame(
                base_df,
                authors=authors,
                project_names=project_names,
                prd_filter=prd_filter,
                risk_filter=risk_filter,
            )

            _zone_band("核心指标", "metrics")
            m1, m2, m3, m4 = st.columns(4)
            total_records = len(df)
            project_count = int(df["project_name"].nunique()) if not df.empty else 0
            total_lines = (
                int(df["additions"].fillna(0).sum() + df["deletions"].fillna(0).sum())
                if not df.empty and "additions" in df.columns
                else 0
            )
            prd_count = count_prd_reviews(df["review_result"]) if (not df.empty and "review_result" in df.columns) else 0
            m1.metric("总审查次数", total_records)
            m2.metric("涉及项目数", project_count)
            m3.metric("代码变更总行数", total_lines)
            m4.metric("含 PRD 审查次数", prd_count)

            if df.empty:
                empty_hint = (
                    "请扩大统计时间段或放宽筛选条件。"
                    if use_mock
                    else "调整时间段或筛选条件，或确认 Webhook 已指向 <code>/review/webhook</code>。"
                )
                st.markdown(
                    f'<div class="empty-panel"><h3>暂无审查记录</h3><p>{empty_hint}</p></div>',
                    unsafe_allow_html=True,
                )
                return

            _render_charts(df)

            _zone_band("审查记录", "records", "明细列表 · 报告下钻")
            display_cols = [
                c
                for c in [
                    "project_name", "author", "source_branch", "target_branch", "branch",
                    "updated_at", "delta", "kind_label", "summary", "url",
                ]
                if c in df.columns
            ]
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True, column_config=column_config)

            labels = [_row_label(row) for _, row in df.iterrows()]
            with st.expander("查看完整审查报告", expanded=False):
                selected = st.selectbox("选择记录", labels, key=f"{tab}_detail_pick", label_visibility="collapsed")
                row = df.iloc[labels.index(selected)]
                report = str(row.get("review_result") or "").strip() or "_（无审查正文）_"
                st.markdown(report)
                if has_url and row.get("url"):
                    st.markdown(f"[打开 PR/MR]({row.get('url')})")

    mr_columns = [
        "project_name", "author", "source_branch", "target_branch", "updated_at",
        "delta", "url", "review_result", "additions", "deletions",
    ]
    mr_column_config = {
        "project_name": "项目名称",
        "author": "开发者",
        "source_branch": "源分支",
        "target_branch": "目标分支",
        "updated_at": "更新时间",
        "delta": "变更行数",
        "kind_label": "类型",
        "summary": "审查摘要",
        "url": st.column_config.LinkColumn("PR 链接", max_chars=100, display_text="打开"),
    }
    display_data(mr_tab, _resolve_log_fetcher(use_mock, kind="mr"), mr_columns, mr_column_config, has_url=True)

    if show_push_tab:
        push_columns = [
            "project_name", "author", "branch", "updated_at",
            "delta", "review_result", "additions", "deletions",
        ]
        push_column_config = {
            "project_name": "项目名称",
            "author": "开发者",
            "branch": "分支",
            "updated_at": "更新时间",
            "delta": "变更行数",
            "kind_label": "类型",
            "summary": "审查摘要",
        }
        display_data(push_tab, _resolve_log_fetcher(use_mock, kind="push"), push_columns, push_column_config, has_url=False)


if check_login_status():
    main_page()
else:
    login_page()
