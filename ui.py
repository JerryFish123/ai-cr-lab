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

from biz.service.review_service import ReviewService
from biz.utils.dashboard_view import count_prd_reviews, enrich_review_frame, filter_enriched_frame

ReviewService.init_db()

# --- Brand palette ---
C_PRIMARY = "#0f766e"
C_PRIMARY_LIGHT = "#14b8a6"
C_ACCENT = "#3dd6c6"
C_INK = "#0c1222"
C_MUTED = "#64748b"
C_BORDER = "#d7e0ea"
C_ADD = "#34d399"
C_DEL = "#f87171"
C_CARD = "#ffffff"

_DEFAULT_CHART_FIGSIZE = (6.2, 3.8)


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
    """Normalize st.date_input range (tuple or single date)."""
    if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
        start_date, end_date = range_val[0], range_val[1]
    elif isinstance(range_val, datetime.date):
        start_date = end_date = range_val
    else:
        start_date, end_date = default_start, default_end
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def _style_chart_axes(ax, *, horizontal=False):
    ax.set_facecolor("#fafbfc")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(C_BORDER)
    ax.spines["bottom"].set_color(C_BORDER)
    ax.tick_params(colors=C_MUTED, labelsize=9)
    ax.grid(axis="x" if horizontal else "y", color="#e8edf2", linestyle="-", linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)


def _annotate_hbars(ax, bars, fmt="{:.0f}"):
    for bar in bars:
        w = bar.get_width()
        if w == 0:
            continue
        ax.text(
            w + max(abs(w) * 0.02, 0.08),
            bar.get_y() + bar.get_height() / 2,
            fmt.format(w),
            va="center",
            ha="left",
            fontsize=8,
            color=C_INK,
            fontweight=600,
        )


def _chart_card(title: str, subtitle: str = ""):
    sub = f'<div class="chart-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="chart-card"><div class="chart-head"><div class="chart-title">{title}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


def _chart_card_end():
    st.markdown("</div>", unsafe_allow_html=True)


def generate_count_chart(df, group_col: str, title_hint: str, *, color: str = C_PRIMARY):
    if df.empty:
        st.info("没有数据可供展示")
        return
    counts = df[group_col].value_counts().reset_index()
    counts.columns = [group_col, "count"]
    counts = counts.sort_values("count", ascending=True).tail(12)

    fig, ax = plt.subplots(figsize=_DEFAULT_CHART_FIGSIZE)
    y_pos = range(len(counts))
    bars = ax.barh(
        y_pos,
        counts["count"],
        color=color,
        height=0.62,
        edgecolor="white",
        linewidth=0.6,
    )
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(counts[group_col], fontsize=9)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    _style_chart_axes(ax, horizontal=True)
    _annotate_hbars(ax, bars)
    ax.set_xlabel("审查次数", fontsize=9, color=C_MUTED, labelpad=8)
    plt.tight_layout()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)


def generate_delta_chart(df, group_col: str):
    if df.empty:
        st.info("没有数据可供展示")
        return
    if "additions" not in df.columns or "deletions" not in df.columns:
        st.warning("无法生成代码行数图表：缺少必要的数据列")
        return

    add = df.groupby(group_col)["additions"].sum().reset_index()
    add.columns = [group_col, "additions"]
    sub = df.groupby(group_col)["deletions"].sum().reset_index()
    sub.columns = [group_col, "deletions"]
    merged = add.merge(sub, on=group_col, how="outer").fillna(0)
    merged["total"] = merged["additions"] + merged["deletions"]
    merged = merged.sort_values("total", ascending=True).tail(12)

    fig, ax = plt.subplots(figsize=_DEFAULT_CHART_FIGSIZE)
    y = range(len(merged))
    h = 0.36
    ax.barh([i - h / 2 for i in y], merged["additions"], height=h, color=C_ADD, label="新增", edgecolor="white")
    ax.barh([i + h / 2 for i in y], merged["deletions"], height=h, color=C_DEL, label="删除", edgecolor="white")
    ax.set_yticks(list(y))
    ax.set_yticklabels(merged[group_col], fontsize=9)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    _style_chart_axes(ax, horizontal=True)
    ax.set_xlabel("行数", fontsize=9, color=C_MUTED, labelpad=8)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    plt.tight_layout()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)


# --- Global CSS ---
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    header[data-testid="stHeader"] {display: none !important;}
    footer {visibility: hidden;}
    div.block-container {padding-top: 0.5rem !important; padding-bottom: 1rem !important; max-width: 1280px;}
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: "Outfit", "Source Han Sans CN", sans-serif; }
    .main {
        background:
          radial-gradient(1000px 480px at 100% -10%, rgba(61, 214, 198, 0.12), transparent 50%),
          radial-gradient(800px 400px at 0% 0%, rgba(15, 118, 110, 0.08), transparent 45%),
          linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
    }
    .stButton>button {
        background: linear-gradient(135deg, #0f766e, #0d9488);
        color: white; border: none; border-radius: 10px; font-weight: 600;
    }
    .stButton>button:hover { box-shadow: 0 4px 14px rgba(15, 118, 110, 0.28); }
    div[data-testid="stMetric"] {
        background: #fff; border: 1px solid #e2e8f0; border-radius: 14px;
        padding: 0.65rem 0.85rem; box-shadow: 0 1px 3px rgba(15,23,42,0.04);
    }
    div[data-testid="stMetric"] label { color: #64748b !important; font-size: 0.82rem !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #0c1222 !important; font-weight: 700 !important; }
    .filter-panel {
        background: #fff; border: 1px solid #e2e8f0; border-radius: 16px;
        padding: 1rem 1.15rem 0.35rem; margin: 0.75rem 0 1rem;
        box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
    }
    .filter-panel-title {
        font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em;
        text-transform: uppercase; color: #0f766e; margin-bottom: 0.65rem;
    }
    .section-title {
        font-size: 1.05rem; font-weight: 700; color: #0c1222;
        margin: 1.25rem 0 0.65rem; padding-left: 0.65rem;
        border-left: 3px solid #14b8a6;
    }
    .chart-card {
        background: #fff; border: 1px solid #e2e8f0; border-radius: 14px;
        padding: 0.85rem 0.9rem 0.25rem; margin-bottom: 0.75rem;
        box-shadow: 0 2px 12px rgba(15, 23, 42, 0.035);
        min-height: 420px;
    }
    .chart-head { margin-bottom: 0.35rem; padding-bottom: 0.5rem; border-bottom: 1px solid #f1f5f9; }
    .chart-title { font-size: 0.95rem; font-weight: 700; color: #0c1222; }
    .chart-sub { font-size: 0.78rem; color: #64748b; margin-top: 0.15rem; }
    .detail-panel {
        margin: 0.75rem 0 1rem; padding: 1rem 1.15rem;
        border: 1px solid #e2e8f0; border-radius: 14px; background: #fff;
    }
    .empty-panel {
        margin: 1rem 0; padding: 2rem 1.25rem; border: 1px dashed #cbd5e1;
        border-radius: 14px; background: rgba(255,255,255,0.85); text-align: center;
    }
    .empty-panel h3 { margin: 0 0 0.4rem; color: #0c1222; font-size: 1.1rem; }
    .empty-panel p { margin: 0; color: #64748b; font-size: 0.92rem; }
    .dash-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 0.35rem 0 0.5rem; margin-bottom: 0.25rem;
    }
    .dash-brand .name { font-size: 1.45rem; font-weight: 700; color: #0c1222; letter-spacing: -0.02em; }
    .dash-brand .tag { font-size: 0.82rem; color: #64748b; margin-top: 0.1rem; }
    a.pro-link {
        display: inline-flex; align-items: center; justify-content: center;
        padding: 0.45rem 1rem; background: #0c1222; color: #e8eef8 !important;
        text-decoration: none; border-radius: 10px; font-size: 0.88rem; font-weight: 600;
    }
    .login-container {
        background: #fff; border: 1px solid #e2e8f0; border-radius: 16px;
        padding: 1rem; box-shadow: 0 10px 40px rgba(15,23,42,0.06);
    }
    .login-title { text-align: center; color: #0c1222; font-size: 2rem; font-weight: 700; }
    .login-sub { text-align: center; color: #64748b; font-size: 0.92rem; }
    .platform-mark {
        text-align: center; font-size: 0.75rem; font-weight: 700;
        letter-spacing: 0.16em; color: #0f766e; margin-top: 0.5rem;
    }
    [data-testid="stTabs"] button { font-weight: 600; }
    [data-testid="stTabs"] [aria-selected="true"] { color: #0f766e !important; border-color: #14b8a6 !important; }
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


def main_page():
    h1, h2 = st.columns([7, 3])
    with h1:
        st.markdown(
            '<div class="dash-brand"><div class="name">ai-cr-lab</div>'
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
                f'<div style="display:flex;justify-content:flex-end;padding-top:0.25rem;">'
                f'<a href="{PRO_VERSION_URL}" target="_blank" class="pro-link">GitHub</a></div>',
                unsafe_allow_html=True,
            )

    current_date = datetime.date.today()
    start_default = current_date - datetime.timedelta(days=7)
    show_push_tab = os.environ.get("PUSH_REVIEW_ENABLED", "0") == "1"

    if show_push_tab:
        mr_tab, push_tab = st.tabs(["合并请求", "代码推送"])
    else:
        mr_tab = st.container()

    def display_data(tab, service_func, columns, column_config, *, has_url: bool):
        with tab:
            st.markdown('<div class="filter-panel"><div class="filter-panel-title">筛选条件</div>', unsafe_allow_html=True)
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

            fc5, fc6 = st.columns([1.4, 1.4])
            with fc5:
                risk_filter = st.selectbox("风险状态", ["全部", "有风险", "无明显风险"], key=f"{tab}_risk_filter")
            with fc6:
                st.caption(f"当前区间：**{start_date}** → **{end_date}**（共 {(end_date - start_date).days + 1} 天）")
            st.markdown("</div>", unsafe_allow_html=True)

            df = filter_enriched_frame(
                base_df,
                authors=authors,
                project_names=project_names,
                prd_filter=prd_filter,
                risk_filter=risk_filter,
            )

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
                st.markdown(
                    '<div class="empty-panel"><h3>暂无审查记录</h3>'
                    "<p>调整时间段或筛选条件，或确认 Webhook 已指向 <code>/review/webhook</code>。</p></div>",
                    unsafe_allow_html=True,
                )
                return

            st.markdown('<div class="section-title">审查记录</div>', unsafe_allow_html=True)
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
            selected = st.selectbox("查看完整审查报告", labels, key=f"{tab}_detail_pick")
            row = df.iloc[labels.index(selected)]
            report = str(row.get("review_result") or "").strip() or "_（无审查正文）_"
            st.markdown('<div class="detail-panel">', unsafe_allow_html=True)
            st.markdown(report)
            if has_url and row.get("url"):
                st.markdown(f"[打开 PR/MR]({row.get('url')})")
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown('<div class="section-title">统计图表</div>', unsafe_allow_html=True)
            r1c1, r1c2 = st.columns(2)
            with r1c1:
                _chart_card("项目审查次数", "各仓库 PR/MR 审查量（Top 12）")
                generate_count_chart(df, "project_name", "project", color=C_PRIMARY)
                _chart_card_end()
            with r1c2:
                _chart_card("开发者审查次数", "按提交者汇总（Top 12）")
                generate_count_chart(df, "author", "author", color=C_PRIMARY_LIGHT)
                _chart_card_end()
            r2c1, r2c2 = st.columns(2)
            with r2c1:
                _chart_card("项目变更行数", "绿色=新增 · 红色=删除")
                generate_delta_chart(df, "project_name")
                _chart_card_end()
            with r2c2:
                _chart_card("开发者变更行数", "绿色=新增 · 红色=删除")
                generate_delta_chart(df, "author")
                _chart_card_end()

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
    display_data(mr_tab, ReviewService().get_mr_review_logs, mr_columns, mr_column_config, has_url=True)

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
        display_data(push_tab, ReviewService().get_push_review_logs, push_columns, push_column_config, has_url=False)


if check_login_status():
    main_page()
else:
    login_page()
