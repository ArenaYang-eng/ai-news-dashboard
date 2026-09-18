"""
AI 落地應用新聞儀表板
資料來源：Google 試算表（透過公開 CSV 匯出連結讀取，不需要另外申請憑證）

部署前準備：
1. 打開你的 AI 新聞試算表 → 右上角「共用」→ 設定為「知道連結的人」可檢視
2. 從網址列複製試算表 ID（網址中 /d/ 和 /edit 之間那一長串英數字）
3. 部署到 Streamlit Community Cloud 時，在 App settings → Secrets 貼上：
   SHEET_ID = "你的試算表ID"
   SHEET_NAME = "AI_News"
   （本機測試時，也可以直接建立 .streamlit/secrets.toml 放同樣內容）
"""

import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ==== 頁面設定 ====
st.set_page_config(
    page_title="AI 落地應用新聞儀表板",
    page_icon="🤖",
    layout="wide",
)

# ==== 自訂樣式，讓畫面更現代化 ====
st.markdown("""
<style>
    .main { background-color: #f7f8fa; }
    div[data-testid="stMetric"] {
        background-color: white;
        border: 1px solid #e6e6e6;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetricLabel"] { font-size: 14px; color: #666; }
    div[data-testid="stMetricValue"] { font-size: 28px; font-weight: 700; }
    h1 { font-weight: 800; }
    .stTabs [data-baseweb="tab"] { font-size: 15px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

COLOR_SEQUENCE = ["#4C6FFF", "#00C2A8", "#FFB020", "#FF6B6B", "#845EF7",
                   "#20C997", "#FF8787", "#4DABF7", "#FFD43B", "#63E6BE"]


# ==== 讀取資料 ====
@st.cache_data(ttl=1800)  # 快取 30 分鐘，避免每次重整頁面都重新打 Google 一次
def load_data():
    sheet_id = st.secrets.get("SHEET_ID", "")
    sheet_name = st.secrets.get("SHEET_NAME", "AI_News")

    if not sheet_id:
        return None

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    df = pd.read_csv(url)

    # 欄位名稱標準化（避免大小寫或空白差異造成抓不到欄位）
    df.columns = [c.strip() for c in df.columns]

    # 排除週報自動插入的標記列
    if "title" in df.columns:
        df = df[df["title"] != "【本週報告】"]

    # 日期欄位轉換
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])

    # 從 summary_zh 尾端的括號抓出類別（落地應用 / 研究/發布/政策）
    def extract_category(text):
        if not isinstance(text, str):
            return "未分類"
        m = re.search(r"（([^（）]+)）\s*$", text)
        return m.group(1) if m else "未分類"

    if "summary_zh" in df.columns:
        df["category"] = df["summary_zh"].apply(extract_category)
    else:
        df["category"] = "未分類"

    if "region" not in df.columns:
        df["region"] = "未標示"
    df["region"] = df["region"].fillna("未標示").replace("", "未標示")

    if "tags" not in df.columns:
        df["tags"] = ""

    df["week"] = df["date"].dt.to_period("W").apply(lambda p: p.start_time)

    return df


df = load_data()

# ==== 標題 ====
st.title("🤖 AI 落地應用新聞儀表板")

if df is None:
    st.warning(
        "尚未設定資料來源。請在 Streamlit 的 Secrets 設定裡加入：\n\n"
        "```\nSHEET_ID = \"你的試算表ID\"\nSHEET_NAME = \"AI_News\"\n```\n\n"
        "試算表 ID 是網址中 `/d/` 和 `/edit` 之間那一長串英數字，"
        "並確認試算表共用設定為「知道連結的人可檢視」。"
    )
    st.stop()

if df.empty:
    st.info("目前試算表裡還沒有資料。")
    st.stop()

# ==== 側邊篩選器 ====
with st.sidebar:
    st.header("篩選條件")

    min_date, max_date = df["date"].min().date(), df["date"].max().date()
    date_range = st.date_input(
        "日期範圍",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    regions = sorted(df["region"].unique().tolist())
    selected_regions = st.multiselect("地區", regions, default=regions)

    categories = sorted(df["category"].unique().tolist())
    selected_categories = st.multiselect("類別", categories, default=categories)

    keyword = st.text_input("關鍵字搜尋（標題/摘要）", "")

    st.caption(f"資料共 {len(df)} 篇，最後更新：{df['date'].max().strftime('%Y-%m-%d')}")

# ==== 套用篩選 ====
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

mask = (
    (df["date"].dt.date >= start_date)
    & (df["date"].dt.date <= end_date)
    & (df["region"].isin(selected_regions))
    & (df["category"].isin(selected_categories))
)

if keyword:
    kw_mask = (
        df["title"].str.contains(keyword, case=False, na=False)
        | df["summary_zh"].str.contains(keyword, case=False, na=False)
    )
    mask = mask & kw_mask

filtered = df[mask]

# ==== KPI 卡片 ====
col1, col2, col3, col4 = st.columns(4)
col1.metric("符合條件文章數", len(filtered))
col2.metric("涵蓋地區數", filtered["region"].nunique())
col3.metric("落地應用篇數", int((filtered["category"] == "落地應用").sum()))
if len(filtered) > 0:
    date_span_days = (filtered["date"].max() - filtered["date"].min()).days + 1
    avg_per_week = len(filtered) / max(date_span_days / 7, 1)
    col4.metric("平均每週篇數", f"{avg_per_week:.1f}")
else:
    col4.metric("平均每週篇數", "—")

st.divider()

# ==== 圖表區 ====
tab1, tab2, tab3 = st.tabs(["📈 趨勢與分布", "🏷️ 主題標籤", "📋 文章清單"])

with tab1:
    c1, c2 = st.columns([2, 1])

    with c1:
        st.subheader("每週文章數量趨勢")
        weekly_counts = filtered.groupby("week").size().reset_index(name="count")
        fig = px.area(
            weekly_counts, x="week", y="count",
            color_discrete_sequence=[COLOR_SEQUENCE[0]],
        )
        fig.update_traces(line=dict(width=3), fillcolor="rgba(76,111,255,0.15)")
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis_title="週次", yaxis_title="文章數",
            margin=dict(t=10, b=10, l=10, r=10),
            height=320,
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("落地應用 vs 研究/發布/政策")
        cat_counts = filtered["category"].value_counts().reset_index()
        cat_counts.columns = ["category", "count"]
        fig = px.pie(
            cat_counts, names="category", values="count", hole=0.5,
            color_discrete_sequence=COLOR_SEQUENCE,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(
            margin=dict(t=10, b=10, l=10, r=10), height=320,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("各地區文章數量")
    region_counts = filtered["region"].value_counts().reset_index()
    region_counts.columns = ["region", "count"]
    region_counts = region_counts.sort_values("count", ascending=True)
    fig = px.bar(
        region_counts, x="count", y="region", orientation="h",
        color="region", color_discrete_sequence=COLOR_SEQUENCE,
        text="count",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False, xaxis_title="文章數", yaxis_title="",
        margin=dict(t=10, b=10, l=10, r=10), height=max(300, 40 * len(region_counts)),
    )
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("熱門標籤 Top 15")
    all_tags = (
        filtered["tags"].dropna().astype(str)
        .str.split(",")
        .explode()
        .str.strip()
    )
    all_tags = all_tags[all_tags != ""]
    tag_counts = all_tags.value_counts().head(15).reset_index()
    tag_counts.columns = ["tag", "count"]
    tag_counts = tag_counts.sort_values("count", ascending=True)

    if tag_counts.empty:
        st.info("目前篩選範圍內沒有標籤資料。")
    else:
        fig = px.bar(
            tag_counts, x="count", y="tag", orientation="h",
            color="count", color_continuous_scale=["#dbe4ff", "#4C6FFF"],
            text="count",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            showlegend=False, coloraxis_showscale=False,
            xaxis_title="出現次數", yaxis_title="",
            margin=dict(t=10, b=10, l=10, r=10), height=460,
        )
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader(f"文章清單（共 {len(filtered)} 篇）")
    display_df = filtered.sort_values("date", ascending=False)[
        ["date", "region", "category", "title", "source", "tags", "url"]
    ].copy()
    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "url": st.column_config.LinkColumn("連結", display_text="開啟"),
            "date": st.column_config.TextColumn("日期"),
            "region": st.column_config.TextColumn("地區"),
            "category": st.column_config.TextColumn("類別"),
            "title": st.column_config.TextColumn("標題", width="large"),
            "source": st.column_config.TextColumn("來源"),
            "tags": st.column_config.TextColumn("標籤"),
        },
    )
