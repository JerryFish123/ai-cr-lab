# -*- coding: utf-8 -*-
import math
from pathlib import Path

import streamlit as st

# 设置Streamlit主题 - 必须是第一个st命令
st.set_page_config(layout="wide", page_title="ai-cr-lab", page_icon="🔬", initial_sidebar_state="expanded")

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
import streamlit as st
from matplotlib.ticker import MaxNLocator
from streamlit_cookies_manager import CookieManager

load_dotenv("conf/.env")

from biz.service.review_service import ReviewService
from biz.utils.dashboard_view import count_prd_reviews, enrich_review_frame, filter_enriched_frame

ReviewService.init_db()


def set_global_font():
    """设置全局字体，如果字体文件不存在则忽略并使用默认字体"""
    font_path = "fonts/SourceHanSansCN-Regular.otf"
    if Path(font_path).exists():
        try:
            fm.fontManager.addfont(font_path)
            mpl.rcParams["font.family"] = "Source Han Sans CN"
        except Exception as e:
            st.warning(f"字体加载失败，使用默认字体。错误信息：{e}")
    else:
        st.warning(f"字体文件未找到：{font_path}，将使用默认字体。")

    mpl.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题


# 在项目启动时调用
set_global_font()

# 从环境变量中读取用户名和密码
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")
USER_CREDENTIALS = {
    DASHBOARD_USER: DASHBOARD_PASSWORD
}

# 用于生成和验证token的密钥
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "fac8cf149bdd616c07c1a675c4571ccacc40d7f7fe16914cfe0f9f9d966bb773")

# 初始化cookie管理器
cookies = CookieManager()


def generate_token(username):
    """生成包含时间戳的认证token"""
    timestamp = str(int(time.time()))
    message = f"{username}:{timestamp}"

    # 使用HMAC-SHA256生成签名
    signature = hmac.new(
        SECRET_KEY.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()

    # 将消息和签名编码为base64
    token = base64.b64encode(f"{message}:{base64.b64encode(signature).decode()}".encode()).decode()
    return token


def verify_token(token):
    """验证token的有效性并提取用户名"""
    try:
        # 解码token
        decoded = base64.b64decode(token.encode()).decode()
        message, signature = decoded.rsplit(":", 1)
        username, timestamp = message.split(":", 1)

        # 验证签名
        expected_signature = hmac.new(
            SECRET_KEY.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()

        actual_signature = base64.b64decode(signature)

        if not hmac.compare_digest(expected_signature, actual_signature):
            return None

        # 检查token是否过期（30天）
        if int(time.time()) - int(timestamp) > 30 * 24 * 60 * 60:
            return None

        return username
    except:
        return None


# 检查登录状态
def check_login_status():
    if not cookies.ready():
        st.stop()

    if 'login_status' not in st.session_state:
        st.session_state['login_status'] = False

    # 尝试从cookie获取token
    auth_token = cookies.get('auth_token')
    if auth_token:
        username = verify_token(auth_token)
        if username and username in USER_CREDENTIALS:
            st.session_state['login_status'] = True
            st.session_state['username'] = username
            st.session_state['saved_username'] = username

    return st.session_state['login_status']


# 设置登录状态
def set_login_status(username, remember):
    st.session_state['login_status'] = True
    st.session_state['username'] = username
    st.session_state['saved_username'] = username if remember else ''

    if remember:
        # 生成并保存token到cookie
        auth_token = generate_token(username)
        cookies['auth_token'] = auth_token
    else:
        # 如果不记住登录状态，清除cookie
        if 'auth_token' in cookies:
            del cookies['auth_token']
    cookies.save()


# 获取保存的用户名
def get_saved_credentials():
    auth_token = cookies.get('auth_token')
    if auth_token:
        username = verify_token(auth_token)
        if username:
            return username, ''
    return st.session_state.get('saved_username', ''), ''


# 登录验证函数
def authenticate(username, password, remember_password=False):
    if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
        set_login_status(username, remember_password)
        return True
    return False


# 获取数据函数
def get_data(service_func, authors=None, project_names=None, updated_at_gte=None, updated_at_lte=None, columns=None):
    df = service_func(authors=authors, project_names=project_names, updated_at_gte=updated_at_gte,
                      updated_at_lte=updated_at_lte)

    if df.empty:
        return pd.DataFrame(columns=columns)

    if "updated_at" in df.columns:
        df["updated_at"] = df["updated_at"].apply(
            lambda ts: datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(ts, (int, float)) else ts
        )

    def format_delta(row):
        if not math.isnan(row['additions']) and not math.isnan(row['deletions']):
            return f"+{int(row['additions'])}  -{int(row['deletions'])}"
        else:
            return ""

    if "additions" in df.columns and "deletions" in df.columns:
        df["delta"] = df.apply(format_delta, axis=1)
    else:
        df["delta"] = ""

    data = df[columns]
    return data


# 隐藏默认的Streamlit菜单和页眉（display:none 避免 visibility:hidden 仍占位导致顶部留白）
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        header[data-testid="stHeader"] {display: none !important;}
        footer {visibility: hidden;}
        div.block-container {padding-top: 0rem !important; padding-bottom: 0.5rem !important;}
        .main .block-container {margin-top: 0 !important;}
        section[data-testid="stMain"] > div {padding-top: 0rem !important;}
    </style>
    """, unsafe_allow_html=True)

# 自定义CSS样式（ai-cr-lab 品牌色：墨蓝 + 青绿）
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: "Outfit", "Source Han Sans CN", sans-serif; }
    .main {
        background:
          radial-gradient(900px 420px at 0% 0%, rgba(61, 214, 198, 0.10), transparent 55%),
          linear-gradient(180deg, #f4f7fb 0%, #eef3f8 100%);
        padding-top: 0rem;
    }
    .stButton>button {
        background-color: #0f766e;
        color: white;
        border-radius: 10px;
        padding: 0.5rem 1.4rem;
        border: none;
        transition: all 0.25s ease;
        font-weight: 600;
    }
    .stButton>button:hover {
        background-color: #0d9488;
        box-shadow: 0 4px 14px rgba(15, 118, 110, 0.25);
        color: #ffffff;
    }
    .stTextInput>div>div>input {
        border: 1px solid #c9d4e0;
        border-radius: 8px;
        padding: 0.5rem;
    }
    .stCheckbox>div>div>input { accent-color: #0f766e; }
    .stDataFrame {
        border: 1px solid #d7e0ea;
        border-radius: 10px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .stMarkdown { font-size: 16px; }
    .login-title {
        text-align: center;
        color: #0c1222;
        margin: 0.35rem 0 0.15rem;
        font-size: 2.4rem;
        font-weight: 700;
        letter-spacing: -0.03em;
    }
    .login-sub {
        text-align: center;
        color: #5b6b7c;
        font-size: 0.95rem;
        margin-bottom: 1rem;
    }
    .login-container {
        background: rgba(255,255,255,0.92);
        border: 1px solid #d7e0ea;
        border-radius: 16px;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
        margin-top: 0rem;
        padding: 0.5rem 0.25rem 1rem;
    }
    .platform-mark {
        text-align: center;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: #0f766e;
        margin-top: 0.75rem;
    }
    a.pro-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.5rem 1.2rem;
        background: #0c1222;
        color: #e8eef8 !important;
        text-decoration: none;
        border-radius: 10px;
        font-size: 0.92rem;
        font-weight: 600;
        transition: all 0.25s ease;
        border: none;
        box-sizing: border-box;
        min-height: 2.25rem;
        line-height: 1.5;
        white-space: nowrap;
    }
    a.pro-link:hover {
        background: #1a2740;
        color: #fff !important;
    }
    .pro-link-wrap {
        display: flex;
        align-items: center;
        justify-content: flex-start;
        margin-left: 0.5rem;
        min-width: 0;
        overflow: hidden;
    }
    .pro-link-wrap .pro-link { max-width: 100%; }
    .empty-panel {
        margin: 0.75rem 0 1.25rem;
        padding: 1.75rem 1.25rem;
        border: 1px dashed #b7c5d4;
        border-radius: 14px;
        background: rgba(255,255,255,0.7);
        text-align: center;
    }
    .empty-panel h3 {
        margin: 0 0 0.4rem;
        color: #0c1222;
        font-size: 1.15rem;
        font-weight: 700;
    }
    .empty-panel p {
        margin: 0;
        color: #5b6b7c;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .dash-brand {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        margin: 0 0 0.35rem 0;
    }
    .dash-brand .name {
        font-size: 1.35rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: #0c1222;
        line-height: 1.15;
    }
    .dash-brand .tag {
        font-size: 0.82rem;
        color: #5b6b7c;
    }
    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.78);
        border: 1px solid #d7e0ea;
        border-radius: 12px;
        padding: 0.55rem 0.75rem 0.65rem;
        margin-bottom: 0.35rem;
    }
    .detail-panel {
        margin: 0.5rem 0 1rem;
        padding: 1rem 1.1rem;
        border: 1px solid #d7e0ea;
        border-radius: 12px;
        background: rgba(255,255,255,0.85);
    }
    </style>
    """,
    unsafe_allow_html=True
)


# 登录界面
def login_page():
    # 使用 st.columns 创建居中布局
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown('<div class="platform-mark">AI-CR-LAB</div>', unsafe_allow_html=True)
        st.markdown('<h1 class="login-title">代码审查控制台</h1>', unsafe_allow_html=True)
        st.markdown('<p class="login-sub">GitHub · JerryFish123/ai-cr-lab</p>', unsafe_allow_html=True)

        # 如果用户名和密码都为 'admin'，提示用户修改密码
        if DASHBOARD_USER == "admin" and DASHBOARD_PASSWORD == "admin":
            st.warning(
                "安全提示：检测到默认用户名和密码为 'admin'，存在安全风险！\n\n"
                "请立即修改：\n"
                "1. 打开 `.env` 文件\n"
                "2. 修改 `DASHBOARD_USER` 和 `DASHBOARD_PASSWORD` 变量\n"
                "3. 保存并重启应用"
            )
            st.write(f"当前用户名: `{DASHBOARD_USER}`, 当前密码: `{DASHBOARD_PASSWORD}`")

        # 获取保存的用户名和密码
        saved_username, saved_password = get_saved_credentials()

        # 创建一个form，支持回车提交
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("👤 用户名", value=saved_username)
            password = st.text_input("🔑 密码", type="password", value=saved_password)
            remember_password = st.checkbox("记住密码", value=bool(saved_username))
            submit = st.form_submit_button("登 录")

            if submit:
                if authenticate(username, password, remember_password):
                    st.rerun()  # 重新运行应用以显示主要内容
                else:
                    st.error("用户名或密码错误")
        st.markdown('</div>', unsafe_allow_html=True)


# 2×2 图表画布
_DEFAULT_CHART_FIGSIZE = (5.5, 3.6)
_DEFAULT_XTICK_FONT = 9


# 生成项目提交数量图表
def generate_project_count_chart(df, figsize=_DEFAULT_CHART_FIGSIZE, xtick_fs=_DEFAULT_XTICK_FONT):
    if df.empty:
        st.info("没有数据可供展示")
        return

    # 计算每个项目的提交数量
    project_counts = df['project_name'].value_counts().reset_index()
    project_counts.columns = ['project_name', 'count']

    # 生成颜色列表，每个项目一个颜色
    colors = plt.colormaps['tab20'].resampled(len(project_counts))

    # 显示提交数量柱状图
    fig1, ax1 = plt.subplots(figsize=figsize)
    ax1.bar(
        project_counts['project_name'],
        project_counts['count'],
        color=[colors(i) for i in range(len(project_counts))]
    )
    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.xticks(rotation=45, ha='right', fontsize=xtick_fs)
    plt.tight_layout()
    st.pyplot(fig1)
    plt.close(fig1)


# 生成人员提交数量图表
def generate_author_count_chart(df, figsize=_DEFAULT_CHART_FIGSIZE, xtick_fs=_DEFAULT_XTICK_FONT):
    if df.empty:
        st.info("没有数据可供展示")
        return

    # 计算每个人员的提交数量
    author_counts = df['author'].value_counts().reset_index()
    author_counts.columns = ['author', 'count']

    # 生成颜色列表，每个项目一个颜色
    colors = plt.colormaps['Paired'].resampled(len(author_counts))
    # 显示提交数量柱状图
    fig1, ax1 = plt.subplots(figsize=figsize)
    ax1.bar(
        author_counts['author'],
        author_counts['count'],
        color=[colors(i) for i in range(len(author_counts))]
    )
    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.xticks(rotation=45, ha='right', fontsize=xtick_fs)
    plt.tight_layout()
    st.pyplot(fig1)
    plt.close(fig1)


def generate_author_code_line_chart(df, figsize=_DEFAULT_CHART_FIGSIZE, xtick_fs=_DEFAULT_XTICK_FONT):
    if df.empty:
        st.info("没有数据可供展示")
        return

    if 'additions' not in df.columns or 'deletions' not in df.columns:
        st.warning("无法生成代码行数图表：缺少必要的数据列")
        return

    author_code_lines_add = df.groupby('author')['additions'].sum().reset_index()
    author_code_lines_add.columns = ['author', 'additions']
    author_code_lines_del = df.groupby('author')['deletions'].sum().reset_index()
    author_code_lines_del.columns = ['author', 'deletions']
    fig3, ax3 = plt.subplots(figsize=figsize)
    ax3.bar(
        author_code_lines_add['author'],
        author_code_lines_add['additions'],
        color=(0.7, 1, 0.7)
    )
    ax3.bar(
        author_code_lines_del['author'],
        -author_code_lines_del['deletions'],
        color=(1, 0.7, 0.7)
    )
    ax3.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
    plt.xticks(rotation=45, ha='right', fontsize=xtick_fs)
    plt.tight_layout()
    st.pyplot(fig3)
    plt.close(fig3)


def generate_project_code_line_chart(df, figsize=_DEFAULT_CHART_FIGSIZE, xtick_fs=_DEFAULT_XTICK_FONT):
    """按项目汇总增删行数，展示形式与 generate_author_code_line_chart 一致（绿色柱为新增，红色柱为删减为负轴）"""
    if df.empty:
        st.info("没有数据可供展示")
        return

    if 'additions' not in df.columns or 'deletions' not in df.columns:
        st.warning("无法生成项目代码行数图表：缺少必要的数据列")
        return

    proj_add = df.groupby('project_name')['additions'].sum().reset_index()
    proj_add.columns = ['project_name', 'additions']
    proj_del = df.groupby('project_name')['deletions'].sum().reset_index()
    proj_del.columns = ['project_name', 'deletions']

    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(
        proj_add['project_name'],
        proj_add['additions'],
        color=(0.7, 1, 0.7),
    )
    ax.bar(
        proj_del['project_name'],
        -proj_del['deletions'],
        color=(1, 0.7, 0.7),
    )
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
    plt.xticks(rotation=45, ha='right', fontsize=xtick_fs)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


# 退出登录函数
def logout():
    # 清除session状态
    st.session_state['login_status'] = False
    st.session_state.pop('username', None)
    st.session_state.pop('saved_username', None)

    # 清除cookie
    if 'auth_token' in cookies:
        del cookies['auth_token']
    cookies.save()

    st.rerun()


# Pro 版文档链接（登录后展示）
PRO_VERSION_URL = "https://github.com/JerryFish123/ai-cr-lab"


def _row_label(row) -> str:
    project = row.get("project_name") or ""
    author = row.get("author") or ""
    when = row.get("updated_at") or ""
    return f"{project} · {author} · {when}"


# 主要内容
def main_page():
    head_left, head_right = st.columns([7.2, 2.8])
    with head_left:
        st.markdown(
            '<div class="dash-brand">'
            '<div class="name">ai-cr-lab</div>'
            '<div class="tag">代码审查统计 · JerryFish123/ai-cr-lab</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with head_right:
        sub_col_logout, sub_col_pro = st.columns([1.3, 1.5])
        with sub_col_logout:
            if st.button("退出登录", key="logout_button", use_container_width=True):
                logout()
        with sub_col_pro:
            st.markdown(
                '<div class="pro-link-wrap">'
                '<a href="' + PRO_VERSION_URL + '" target="_blank" rel="noopener noreferrer" class="pro-link">GitHub 仓库</a>'
                '</div>',
                unsafe_allow_html=True
            )

    current_date = datetime.date.today()
    start_date_default = current_date - datetime.timedelta(days=7)
    show_push_tab = os.environ.get('PUSH_REVIEW_ENABLED', '0') == '1'

    if show_push_tab:
        mr_tab, push_tab = st.tabs(["合并请求", "代码推送"])
    else:
        mr_tab = st.container()

    def display_data(tab, service_func, columns, column_config, *, has_url: bool):
        with tab:
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                start_date = st.date_input("开始日期", start_date_default, key=f"{tab}_start_date")
            with f2:
                end_date = st.date_input("结束日期", current_date, key=f"{tab}_end_date")

            start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
            end_datetime = datetime.datetime.combine(end_date, datetime.time.max)

            # Single DB fetch for date range; filter locally afterwards.
            raw = get_data(
                service_func,
                updated_at_gte=int(start_datetime.timestamp()),
                updated_at_lte=int(end_datetime.timestamp()),
                columns=columns,
            )
            base_df = enrich_review_frame(pd.DataFrame(raw))

            unique_authors = sorted(base_df["author"].dropna().unique().tolist()) if not base_df.empty else []
            unique_projects = sorted(base_df["project_name"].dropna().unique().tolist()) if not base_df.empty else []

            with f3:
                authors = st.multiselect("开发者", unique_authors, default=[], key=f"{tab}_authors")
            with f4:
                project_names = st.multiselect("项目名称", unique_projects, default=[], key=f"{tab}_projects")

            f5, f6 = st.columns(2)
            with f5:
                prd_filter = st.selectbox(
                    "PRD 状态",
                    ["全部", "含PRD", "无PRD", "旧格式"],
                    key=f"{tab}_prd_filter",
                )
            with f6:
                risk_filter = st.selectbox(
                    "风险状态",
                    ["全部", "有风险", "无明显风险"],
                    key=f"{tab}_risk_filter",
                )

            df = filter_enriched_frame(
                base_df,
                authors=authors,
                project_names=project_names,
                prd_filter=prd_filter,
                risk_filter=risk_filter,
            )

            total_records = len(df)
            project_count = int(df["project_name"].nunique()) if not df.empty else 0
            if not df.empty and "additions" in df.columns and "deletions" in df.columns:
                total_lines = int(df["additions"].fillna(0).sum() + df["deletions"].fillna(0).sum())
            else:
                total_lines = 0
            prd_count = count_prd_reviews(df["review_result"]) if (not df.empty and "review_result" in df.columns) else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("总审查次数", total_records)
            m2.metric("涉及项目数", project_count)
            m3.metric("代码变更总行数", total_lines)
            m4.metric("含 PRD 审查次数", prd_count)

            if df.empty:
                st.markdown(
                    '<div class="empty-panel">'
                    "<h3>暂无审查记录</h3>"
                    "<p>在业务仓库配置 Webhook 指向 "
                    "<code>/review/webhook</code> 后，合并请求或推送产生的审查会显示在这里；"
                    "也可放宽上方日期 / PRD / 风险筛选后再试。</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                return

            display_cols = [
                c for c in [
                    "project_name", "author", "source_branch", "target_branch", "branch",
                    "updated_at", "delta", "kind_label", "summary", "url",
                ]
                if c in df.columns
            ]
            st.dataframe(
                df[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config=column_config,
            )

            labels = [_row_label(row) for _, row in df.iterrows()]
            selected = st.selectbox("查看完整审查报告", labels, key=f"{tab}_detail_pick")
            row = df.iloc[labels.index(selected)]
            report = str(row.get("review_result") or "").strip() or "_（无审查正文）_"
            st.markdown('<div class="detail-panel">', unsafe_allow_html=True)
            st.markdown(report)
            if has_url and row.get("url"):
                st.markdown(f"[打开 PR/MR]({row.get('url')})")
            st.markdown('</div>', unsafe_allow_html=True)

            chart_title_css = (
                "<div style='text-align:center;font-size:clamp(12px,1vw,15px);"
                "line-height:1.2;margin:0.4rem 0 0.25rem 0;'><b>{}</b></div>"
            )
            r1c1, r1c2 = st.columns(2)
            with r1c1:
                st.markdown(chart_title_css.format("项目审查次数"), unsafe_allow_html=True)
                generate_project_count_chart(df)
            with r1c2:
                st.markdown(chart_title_css.format("开发者审查次数"), unsafe_allow_html=True)
                generate_author_count_chart(df)
            r2c1, r2c2 = st.columns(2)
            with r2c1:
                st.markdown(chart_title_css.format("项目变更行数"), unsafe_allow_html=True)
                if 'additions' in df.columns and 'deletions' in df.columns:
                    generate_project_code_line_chart(df)
                else:
                    st.info("无法显示代码行数图表：缺少必要的数据列")
            with r2c2:
                st.markdown(chart_title_css.format("开发者变更行数"), unsafe_allow_html=True)
                if 'additions' in df.columns and 'deletions' in df.columns:
                    generate_author_code_line_chart(df)
                else:
                    st.info("无法显示代码行数图表：缺少必要的数据列")

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
    display_data(
        mr_tab,
        ReviewService().get_mr_review_logs,
        mr_columns,
        mr_column_config,
        has_url=True,
    )

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
        display_data(
            push_tab,
            ReviewService().get_push_review_logs,
            push_columns,
            push_column_config,
            has_url=False,
        )


# 应用入口
if check_login_status():
    main_page()
else:
    login_page()
