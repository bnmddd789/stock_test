# -*- coding: utf-8 -*-
import contextlib
import io
import os
from datetime import datetime

import pandas as pd
import streamlit as st


os.environ.setdefault("BATCH_SIZE", "10")
os.environ.setdefault("YF_THREADS", "0")

import stock_1  # noqa: E402


st.set_page_config(
    page_title="台股 AI 動能掃描",
    page_icon="📈",
    layout="wide",
)


FORWARD_DAYS = [1, 3, 5, 7, 10, 14, 21, 30]

COLUMN_LABELS = {
    "Rank": "排名",
    "ID": "代號",
    "Name": "名稱",
    "Industry": "產業",
    "Close": "收盤",
    "AI_Score": "AI 分數",
    "Integrated_Score": "整合分數",
    "Institution_Score": "法人分數",
    "Conservative_Score": "保守分數",
    "Attack_Rank": "攻擊排名",
    "Aggressive_Rank": "攻擊排名",
    "Aggressive_Tier": "攻擊層級",
    "Conservative_Rank": "保守排名",
    "Conservative_Tier": "保守層級",
    "Conservative_Eligible": "保守候選",
    "Stage2_Trend_OK": "多頭排列",
    "Avg_Value_20": "20日均額",
    "Volume_Ratio": "量比",
    "ROC_1": "1日漲跌%",
    "ROC_3": "3日漲跌%",
    "ROC_5": "5日漲跌%",
    "ROC_10": "10日漲跌%",
    "ROC_20": "20日漲跌%",
    "ROC_30": "30日漲跌%",
    "F_ROC_10": "10日動能%",
    "Hint": "提醒",
    "Signal_Date": "訊號日",
    "Entry_Date": "進場日",
    "Entry_Open": "進場開盤",
    "Entry_Gap_%": "開盤跳空%",
    "Entry_Filter": "進場濾網",
    "Day1_Net_Return_%": "1日報酬%",
    "Day7_Net_Return_%": "7日報酬%",
    "Day30_Net_Return_%": "30日報酬%",
    "Date": "日期",
    "MA5": "MA5",
    "MA20": "MA20",
    "MA60": "MA60",
    "Trend_Points": "趨勢分",
    "Trend_View": "趨勢判斷",
    "Score_Status": "分數狀態",
    "Score_Reason": "未排名原因",
    "Market_PR_%": "市場 PR%",
    "Market_Status": "大盤燈號",
    "Market_Message": "大盤風控",
    "Market_Allowed": "允許新倉",
    "Stop_Loss_Price": "停損價",
    "Backtest_Stop_Price": "回測停損價",
    "Stop_Loss_Pct": "停損%",
    "Stop_Exit_Date": "停損/持有出場日",
    "Stop_Exit_Price": "停損/持有出場價",
    "Stop_Exit_Reason": "停損狀態",
    "Stop_Net_Return_%": "停損後報酬%",
    "Hold_Today_Date": "持有至今日",
    "Hold_Today_Close": "今日收盤",
    "Hold_Today_Net_Return_%": "持有至今報酬%",
    "Take_Profit_Low": "停利區間低",
    "Take_Profit_High": "停利區間高",
    "Sell_Zone": "停利觀察區",
    "Max_Buy_Price": "最高追價",
    "Suggested_Capital": "建議金額",
    "Suggested_Shares": "建議股數",
    "Exit_Rule": "出場規則",
    "Hist_Vol": "歷史波動",
    "BB_Width": "布林寬度",
    "P_to_MA20": "距 MA20%",
    "P_to_MA60": "距 MA60%",
    "Recent_20_High": "20日高點",
    "Recent_20_Low": "20日低點",
    "Reasons": "判斷原因",
}

DISPLAY_DIGITS = {
    "AI_Score": 2,
    "Integrated_Score": 2,
    "Institution_Score": 2,
    "Conservative_Score": 2,
    "Attack_Rank": 0,
    "Aggressive_Rank": 0,
    "Conservative_Rank": 0,
    "Close": 2,
    "Entry_Open": 2,
    "Entry_Gap_%": 2,
    "Avg_Value_20": 0,
    "Volume_Ratio": 2,
    "ROC_1": 2,
    "ROC_3": 2,
    "ROC_5": 2,
    "ROC_10": 2,
    "ROC_20": 2,
    "ROC_30": 2,
    "F_ROC_10": 2,
    "Day1_Net_Return_%": 2,
    "Day7_Net_Return_%": 2,
    "Day30_Net_Return_%": 2,
    "MA5": 2,
    "MA20": 2,
    "MA60": 2,
    "Trend_Points": 0,
    "Market_PR_%": 2,
    "Stop_Loss_Price": 2,
    "Backtest_Stop_Price": 2,
    "Stop_Loss_Pct": 1,
    "Stop_Exit_Price": 2,
    "Stop_Net_Return_%": 2,
    "Hold_Today_Close": 2,
    "Hold_Today_Net_Return_%": 2,
    "Take_Profit_Low": 2,
    "Take_Profit_High": 2,
    "Max_Buy_Price": 2,
    "Suggested_Capital": 0,
    "Suggested_Shares": 0,
    "Recent_20_High": 2,
    "Recent_20_Low": 2,
}

def capture_output(func, *args, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


def load_market_data(refresh_token=0, progress_callback=None):
    force_refresh = refresh_token > 0
    (df_all, stock_dict), logs = capture_output(
        stock_1.prepare_data,
        force_refresh=force_refresh,
        progress_callback=progress_callback,
    )
    stock_dict = normalize_stock_dict_industries(stock_dict)

    if df_all is not None and not df_all.empty and "Date" in df_all.columns:
        df_all = df_all.copy()
        df_all["Date"] = pd.to_datetime(df_all["Date"])
        df_all = attach_industry_column(df_all, stock_dict)

    return df_all, stock_dict, logs


def init_state():
    st.session_state.setdefault("refresh_token", 0)
    st.session_state.setdefault("loaded_refresh_token", None)
    st.session_state.setdefault("data_loaded", False)
    st.session_state.setdefault("market_data", None)
    st.session_state.setdefault("stock_dict", {})
    st.session_state.setdefault("last_logs", "")
    st.session_state.setdefault("scan_result", pd.DataFrame())
    st.session_state.setdefault("attack_result", pd.DataFrame())
    st.session_state.setdefault("conservative_result", pd.DataFrame())
    st.session_state.setdefault("history_result", pd.DataFrame())
    st.session_state.setdefault("history_comparison", pd.DataFrame())
    st.session_state.setdefault("single_result", pd.DataFrame())
    st.session_state.setdefault("fundamental_cache", {})


def get_data():
    st.session_state.data_loaded = True

    if (
        st.session_state.market_data is not None
        and st.session_state.loaded_refresh_token == st.session_state.refresh_token
    ):
        return (
            st.session_state.market_data,
            st.session_state.stock_dict,
            st.session_state.last_logs,
        )

    progress_bar = st.progress(0)
    status_box = st.empty()

    def update_progress(stage, current, total, message):
        total = max(int(total or 1), 1)
        current = max(int(current or 0), 0)
        ratio = min(current / total, 1.0)

        if stage == "cache":
            progress_value = 0.03 + (0.04 * ratio)
        elif stage == "stock_list":
            progress_value = 0.08 + (0.07 * ratio)
        elif stage == "download":
            progress_value = 0.15 + (0.78 * ratio)
        elif stage == "cache_save":
            progress_value = 0.94 + (0.04 * ratio)
        elif stage == "done":
            progress_value = 1.0
        else:
            progress_value = ratio

        progress_value = min(progress_value, 1.0)
        progress_bar.progress(progress_value)
        status_box.info(f"{progress_value * 100:.0f}%｜{message or '資料處理中...'}")

    update_progress("cache", 0, 1, "準備載入資料...")
    with st.spinner("載入資料中，第一次可能需要幾分鐘..."):
        df_all, stock_dict, logs = load_market_data(
            st.session_state.refresh_token,
            progress_callback=update_progress,
        )
    progress_bar.progress(1.0)
    status_box.success("資料載入完成。")
    st.session_state.market_data = df_all
    st.session_state.stock_dict = stock_dict
    st.session_state.loaded_refresh_token = st.session_state.refresh_token
    st.session_state.last_logs = logs
    return df_all, stock_dict, logs


def has_valid_data(df_all):
    return df_all is not None and not df_all.empty and "Date" in df_all.columns


def existing_cols(df, cols):
    return [col for col in cols if col in df.columns]


def prepare_display_df(df, cols=None):
    view = df[existing_cols(df, cols)].copy() if cols else df.copy()

    for col, digits in DISPLAY_DIGITS.items():
        if col in view.columns:
            view[col] = pd.to_numeric(view[col], errors="coerce").round(digits)

    view = view.rename(columns=COLUMN_LABELS)
    return view


def render_table(df, cols=None, height=None):
    if df is None or df.empty:
        st.info("目前沒有資料。")
        return

    view = prepare_display_df(df, cols)
    st.dataframe(view, use_container_width=True, hide_index=True, height=height)


def fmt_number(value, digits=2):
    if value is None or pd.isna(value):
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def fmt_money(value):
    if value is None or pd.isna(value):
        return None
    return round(float(value), 0)


def fmt_pct(value):
    if value is None or pd.isna(value):
        return None
    return round(float(value), 2)


def compact_text(text, max_len=360):
    if not text:
        return ""

    text = " ".join(str(text).split())
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


def normalize_ticker_from_id(stock_id, df_all=None):
    value = str(stock_id or "").strip().upper()
    if not value:
        return ""

    if value.endswith(".TW") or value.endswith(".TWO"):
        return value

    if df_all is not None and not df_all.empty and "ID" in df_all.columns:
        matched = df_all[df_all["ID"].astype(str).str.upper() == value]
        if not matched.empty:
            return str(matched["Ticker"].iloc[0])

    return f"{value}.TW"


def get_local_stock_info(ticker, stock_dict):
    if not ticker:
        return {}
    return (stock_dict or {}).get(ticker, {}) or {}


def fetch_fundamentals(ticker, stock_dict):
    cache = st.session_state.fundamental_cache
    if ticker in cache:
        return cache[ticker]

    local_info = get_local_stock_info(ticker, stock_dict)
    result = {
        "ticker": ticker,
        "name": local_info.get("name", ""),
        "industry": local_info.get("ind", "產業分類暫無資料"),
        "sector": "",
        "business": "",
        "website": "",
        "metrics": {},
        "source": "本地股票清單",
        "error": "",
    }

    try:
        info = stock_1.yf.Ticker(ticker).info or {}

        dividend_yield = info.get("dividendYield")
        if dividend_yield is not None and dividend_yield <= 1:
            dividend_yield = dividend_yield * 100

        metrics = {
            "市值": info.get("marketCap"),
            "本益比": info.get("trailingPE"),
            "預估本益比": info.get("forwardPE"),
            "股價淨值比": info.get("priceToBook"),
            "EPS": info.get("trailingEps"),
            "殖利率%": dividend_yield,
        }

        result.update({
            "industry": info.get("industry") or result["industry"],
            "sector": info.get("sector") or "",
            "business": compact_text(info.get("longBusinessSummary")),
            "website": info.get("website") or "",
            "metrics": metrics,
            "source": "yfinance",
        })
    except Exception as exc:
        result["error"] = str(exc)

    if not result["business"]:
        result["business"] = f"目前可取得的分類為：{result['industry']}。"

    cache[ticker] = result
    return result


def render_fundamentals_panel(rows_df, df_all=None, stock_dict=None, key_prefix="fund"):
    if rows_df is None or rows_df.empty:
        return

    st.markdown("**個股產業與基本面**")

    options = []
    for _, row in rows_df.iterrows():
        stock_id = row.get("ID", row.get("Ticker", ""))
        name = row.get("Name", "")
        ticker = normalize_ticker_from_id(stock_id, df_all)
        if not ticker:
            continue
        options.append((f"{stock_id} {name}".strip(), ticker))

    if not options:
        st.info("目前沒有可查看基本面的股票。")
        return

    labels = [label for label, _ in options]
    selected_label = st.selectbox("選擇股票", labels, key=f"{key_prefix}_select")
    selected_ticker = dict(options)[selected_label]
    local_info = get_local_stock_info(selected_ticker, stock_dict)

    st.caption(
        f"{selected_ticker}｜產業：{local_info.get('ind', '產業分類暫無資料')}"
    )

    if st.button("載入基本面", key=f"{key_prefix}_load", use_container_width=True):
        with st.spinner("抓取基本面資料中..."):
            fundamentals = fetch_fundamentals(selected_ticker, stock_dict)
        st.session_state[f"{key_prefix}_fundamentals"] = fundamentals

    fundamentals = st.session_state.get(f"{key_prefix}_fundamentals")
    if not fundamentals or fundamentals.get("ticker") != selected_ticker:
        st.info("按「載入基本面」後會顯示公司產業、業務摘要與常用估值指標。")
        return

    if fundamentals.get("error"):
        st.warning(f"線上基本面抓取失敗，先顯示本地產業資料：{fundamentals['error']}")

    metric_cols = st.columns(6)
    metrics = fundamentals.get("metrics", {})
    metric_items = [
        ("市值", metrics.get("市值")),
        ("本益比", metrics.get("本益比")),
        ("預估本益比", metrics.get("預估本益比")),
        ("股價淨值比", metrics.get("股價淨值比")),
        ("EPS", metrics.get("EPS")),
        ("殖利率%", metrics.get("殖利率%")),
    ]

    for col, (label, value) in zip(metric_cols, metric_items):
        if label == "市值" and value is not None and not pd.isna(value):
            display = f"{float(value) / 100000000:.0f} 億"
        else:
            display = fmt_number(value)
        col.metric(label, display)

    st.write(f"**產業**：{fundamentals.get('industry') or '-'}")
    if fundamentals.get("sector"):
        st.write(f"**Sector**：{fundamentals['sector']}")
    st.write(f"**公司做什麼**：{fundamentals.get('business') or '-'}")
    if fundamentals.get("website"):
        st.link_button("公司網站", fundamentals["website"])


INDUSTRY_DESCRIPTIONS = {
    "水泥工業": "主要看營建景氣、公共工程、煤電成本與區域報價；循環性偏高，殖利率與現金流穩定度也很重要。",
    "食品工業": "需求較防禦，重點看品牌通路、原物料成本、毛利率、現金股利與海外市場成長。",
    "塑膠工業": "受石化循環、油價與利差影響大，觀察報價、產能利用率、現金流與負債控管。",
    "紡織纖維": "重點看接單能見度、匯率、品牌客戶庫存，以及機能布料或高值化產品比重。",
    "電機機械": "觀察設備訂單、出口動能、自動化需求、毛利率與景氣循環位置。",
    "電器電纜": "與電網建設、銅價、台電強韌電網題材連動，需看存貨與原料價格波動。",
    "鋼鐵工業": "循環性強，主要看鋼價、原料成本、營建與製造需求、庫存去化速度。",
    "汽車工業": "看新車銷量、零組件出貨、電動車滲透率、匯率與供應鏈議價能力。",
    "建材營造": "重點看推案量、完工入帳、土地庫存、利率與房市政策。",
    "航運業": "高度景氣循環，觀察運價、油價、船隊供給、合約價與全球貿易需求。",
    "觀光餐旅": "看來客數、住房率、展店效率、薪資租金成本與消費景氣。",
    "金融保險": "重點看利差、放款品質、資本適足率、股債投資部位與股利政策。",
    "貿易百貨": "看通路市占、同店銷售、電商布局、庫存周轉與消費景氣。",
    "化學工業": "通常受原料報價、產品利差、下游需求與環保法規影響；基本面要看毛利率循環、存貨水位、現金流與負債比。",
    "生技醫療": "重點看產品線、法規審查、授權金、臨床進度與營收能見度，波動通常較高。",
    "油電燃氣": "偏公用事業屬性，觀察政策價格、能源成本、資本支出與股利穩定性。",
    "半導體業": "看製程或產品競爭力、庫存循環、資本支出、毛利率與 AI/HPC/車用需求。",
    "電腦及週邊設備": "看伺服器、NB/PC、AI 設備、品牌或代工訂單能見度與毛利結構。",
    "光電業": "景氣循環明顯，需看面板/光學/太陽能報價、稼動率與產品組合。",
    "通信網路業": "看網通設備、資料中心、5G/衛星通訊需求、客戶集中度與毛利率。",
    "電子零組件": "觀察終端需求、庫存去化、產品規格升級、車用/AI/伺服器占比與匯率。",
    "電子通路業": "重點看庫存周轉、代理線組合、應收帳款、現金流與景氣循環。",
    "資訊服務業": "看軟體訂閱、系統整合案量、雲端與資安需求、續約率與人力成本。",
    "其他電子業": "範圍較廣，需回到公司產品線，觀察訂單能見度、毛利率、客戶集中度與現金流。",
    "文化創意業": "看 IP 內容、授權收入、展演票房、平台分潤與固定成本。",
    "綠能環保": "看政策補助、專案入帳、電價或處理費、資本支出與負債。",
    "數位雲端": "觀察雲端服務、訂閱收入、客戶留存率、資安需求與營收成長品質。",
    "運動休閒": "看品牌客戶訂單、庫存循環、匯率、毛利率與終端消費需求。",
    "居家生活": "重點看通路銷售、原物料成本、庫存周轉、品牌力與房市/消費景氣。",
}


def normalize_stock_dict_industries(stock_dict):
    normalized = {}
    for ticker, info in (stock_dict or {}).items():
        item = dict(info or {})
        item["ind"] = stock_1.normalize_industry_name(item.get("ind")) or "產業分類暫無資料"
        normalized[ticker] = item
    return normalized


def attach_industry_column(df_all, stock_dict):
    if df_all is None or df_all.empty or "Ticker" not in df_all.columns:
        return df_all

    industry_map = {
        ticker: info.get("ind", "產業分類暫無資料")
        for ticker, info in (stock_dict or {}).items()
    }
    df_all = df_all.copy()
    existing = df_all["Industry"] if "Industry" in df_all.columns else ""
    df_all["Industry"] = df_all["Ticker"].map(industry_map)
    df_all["Industry"] = df_all["Industry"].fillna(existing).replace("", "產業分類暫無資料")
    return df_all


def build_local_business_intro(name, industry):
    clean_industry = stock_1.normalize_industry_name(industry) or "產業分類暫無資料"
    company = name or "該公司"
    detail = INDUSTRY_DESCRIPTIONS.get(
        clean_industry,
        "本地資料暫時只有產業分類；基本面可優先看營收成長、毛利率、營業利益率、現金流、負債比與股利穩定度。",
    )
    return f"{company} 目前本地資料歸類為「{clean_industry}」。{detail}"


def get_local_stock_info(ticker, stock_dict):
    if not ticker:
        return {}

    info = dict((stock_dict or {}).get(ticker, {}) or {})
    info["ind"] = stock_1.normalize_industry_name(info.get("ind")) or "產業分類暫無資料"
    return info


def fetch_fundamentals(ticker, stock_dict):
    local_info = get_local_stock_info(ticker, stock_dict)
    local_industry = local_info.get("ind", "產業分類暫無資料")
    local_name = local_info.get("name", "")

    cache = st.session_state.fundamental_cache
    if ticker in cache:
        cached = cache[ticker]
        cached["industry"] = stock_1.normalize_industry_name(
            cached.get("industry") or local_industry
        ) or local_industry
        cached["business"] = build_local_business_intro(
            cached.get("name") or local_name,
            cached.get("industry") or local_industry,
        )
        return cached

    result = {
        "ticker": ticker,
        "name": local_name,
        "industry": local_industry,
        "sector": "",
        "yfinance_industry": "",
        "business": build_local_business_intro(local_name, local_industry),
        "website": "",
        "metrics": {
            "市值": None,
            "本益比": None,
            "預估本益比": None,
            "股價淨值比": None,
            "EPS": None,
            "殖利率%": None,
        },
        "source": "本地股票清單",
        "error": "",
    }

    try:
        info = stock_1.yf.Ticker(ticker).info or {}

        dividend_yield = info.get("dividendYield")
        if dividend_yield is not None and dividend_yield <= 1:
            dividend_yield = dividend_yield * 100

        yf_industry = info.get("industry") or ""
        result.update({
            "name": info.get("longName") or info.get("shortName") or result["name"],
            "industry": result["industry"],
            "sector": info.get("sector") or "",
            "yfinance_industry": yf_industry,
            "business": build_local_business_intro(
                info.get("longName") or info.get("shortName") or result["name"],
                result["industry"],
            ),
            "website": info.get("website") or "",
            "metrics": {
                "市值": info.get("marketCap"),
                "本益比": info.get("trailingPE"),
                "預估本益比": info.get("forwardPE"),
                "股價淨值比": info.get("priceToBook"),
                "EPS": info.get("trailingEps"),
                "殖利率%": dividend_yield,
            },
            "source": "本地股票清單 + yfinance",
        })
    except Exception as exc:
        result["error"] = str(exc)

    cache[ticker] = result
    return result


def format_fundamental_metric(label, value):
    if value is None or pd.isna(value):
        return "-"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if label == "市值":
        return f"{number / 100000000:.0f} 億"
    if label == "殖利率%":
        return f"{number:.2f}%"
    return f"{number:.2f}"


def render_fundamentals_panel(rows_df, df_all=None, stock_dict=None, key_prefix="fund"):
    if rows_df is None or rows_df.empty:
        return

    st.markdown("**個股產業與基本面**")

    options = []
    for _, row in rows_df.iterrows():
        stock_id = row.get("ID", row.get("Ticker", ""))
        name = row.get("Name", "")
        ticker = row.get("Ticker") or normalize_ticker_from_id(stock_id, df_all)
        if not ticker:
            continue
        label = f"{stock_id} {name}".strip()
        if (label, ticker) not in options:
            options.append((label, ticker))

    if not options:
        st.info("目前沒有可載入基本面的股票。")
        return

    labels = [label for label, _ in options]
    selected_label = st.selectbox("選擇股票", labels, key=f"{key_prefix}_select")
    selected_ticker = options[labels.index(selected_label)][1]
    local_info = get_local_stock_info(selected_ticker, stock_dict)
    local_industry = local_info.get("ind", "產業分類暫無資料")
    stock_code = selected_ticker.split(".")[0]

    st.caption(f"{selected_ticker} | 產業：{local_industry}")

    if st.button("載入基本面", key=f"{key_prefix}_load", use_container_width=True):
        with st.spinner("正在抓取基本面資料..."):
            fundamentals = fetch_fundamentals(selected_ticker, stock_dict)
        st.session_state[f"{key_prefix}_fundamentals"] = fundamentals

    fundamentals = st.session_state.get(f"{key_prefix}_fundamentals")
    if not fundamentals or fundamentals.get("ticker") != selected_ticker:
        st.info("本地產業已先顯示；按「載入基本面」會嘗試補上估值、EPS、殖利率與公司介紹。")
        return

    if fundamentals.get("error"):
        st.warning(
            "線上估值資料暫時無法取得，先顯示本地產業資料。"
            f"原因：{compact_text(fundamentals['error'], 160)}"
        )

    metric_cols = st.columns(6)
    metrics = fundamentals.get("metrics", {})
    metric_items = [
        ("市值", metrics.get("市值")),
        ("本益比", metrics.get("本益比")),
        ("預估本益比", metrics.get("預估本益比")),
        ("股價淨值比", metrics.get("股價淨值比")),
        ("EPS", metrics.get("EPS")),
        ("殖利率%", metrics.get("殖利率%")),
    ]

    for col, (label, value) in zip(metric_cols, metric_items):
        col.metric(label, format_fundamental_metric(label, value))

    industry = stock_1.normalize_industry_name(fundamentals.get("industry")) or local_industry
    st.write(f"**產業類別**：{industry}")
    st.write(f"**基本面觀察**：{fundamentals.get('business') or build_local_business_intro(local_info.get('name'), industry)}")

    link_cols = st.columns(3)
    link_cols[0].link_button("Yahoo 股市", f"https://tw.stock.yahoo.com/quote/{selected_ticker}")
    link_cols[1].link_button("公開資訊觀測站", f"https://mops.twse.com.tw/mops/web/t146sb05?TYPEK=all&step=1&firstin=1&keyword4={stock_code}")
    if fundamentals.get("website"):
        link_cols[2].link_button("公司網站", fundamentals["website"])

    st.caption(f"資料來源：{fundamentals.get('source', '-')}")


def render_status(df_all):
    if not has_valid_data(df_all):
        st.warning("資料尚未載入。請先按「載入資料」或直接執行任一功能。")
        return

    latest = pd.to_datetime(df_all["Date"]).max().date()
    earliest = pd.to_datetime(df_all["Date"]).min().date()
    stocks = df_all["Ticker"].nunique() if "Ticker" in df_all.columns else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("資料起日", str(earliest))
    col2.metric("最新交易日", str(latest))
    col3.metric("股票數", f"{stocks:,}")
    col4.metric("資料列數", f"{len(df_all):,}")


def render_market_risk(df_all):
    if not has_valid_data(df_all):
        return

    risk = stock_1.market_risk_status(df_all)
    if risk.get("Market_Status") == "紅燈":
        st.error(risk.get("Market_Message"))
    elif risk.get("Market_Status") == "綠燈":
        st.success(risk.get("Market_Message"))
    else:
        st.info(risk.get("Market_Message"))


def render_attack_table(df):
    if df is None or df.empty:
        st.info("目前沒有強勢攻擊名單。")
        return

    cols = [
        "Attack_Rank", "ID", "Name", "Industry", "Close", "Integrated_Score",
        "AI_Score", "Institution_Score", "Aggressive_Tier",
        "Stop_Loss_Price", "Sell_Zone", "Max_Buy_Price", "Suggested_Capital",
        "Volume_Ratio", "F_ROC_10", "Hint",
    ]
    render_table(df, cols, height=300)


def render_conservative_table(df):
    if df is None or df.empty:
        st.info("目前沒有符合保守策略條件的股票。")
        return

    cols = [
        "Conservative_Rank", "ID", "Name", "Industry", "Close", "Conservative_Score",
        "Integrated_Score", "Institution_Score", "Conservative_Tier",
        "Stop_Loss_Price", "Sell_Zone", "Volume_Ratio", "ROC_3", "ROC_5", "Hint",
    ]
    render_table(df, cols, height=300)


def build_history_comparison(df_all, result_df, target_date):
    if result_df is None or result_df.empty:
        return pd.DataFrame()

    target = stock_1.normalize_input_date(target_date)
    signal_date = stock_1.get_nearest_trading_date(df_all, target)
    if signal_date is None:
        return pd.DataFrame()

    market_entry_date = stock_1.get_next_trading_date(df_all, signal_date)
    if market_entry_date is None:
        return pd.DataFrame()

    rows = []
    day_benchmark_cache = {}
    hold_benchmark_cache = {}

    def total_invest_for(valid_df):
        if "Invest_Amount" in valid_df.columns:
            return float(pd.to_numeric(valid_df["Invest_Amount"], errors="coerce").sum())
        return float(stock_1.CAPITAL_PER_STOCK * len(valid_df))

    def get_day_benchmark(total_invest, benchmark_ticker, benchmark_name):
        cache_key = (total_invest, benchmark_ticker)
        if cache_key not in day_benchmark_cache:
            benchmark_df, _ = capture_output(
                stock_1.calc_benchmark_result,
                df_all,
                signal_date,
                total_invest,
                forward_days_list=FORWARD_DAYS,
                benchmark_ticker=benchmark_ticker,
                benchmark_name=benchmark_name,
                expected_entry_date=market_entry_date,
            )
            day_benchmark_cache[cache_key] = benchmark_df
        return day_benchmark_cache[cache_key]

    def get_hold_benchmark(total_invest, benchmark_ticker, benchmark_name):
        cache_key = (total_invest, benchmark_ticker)
        if cache_key not in hold_benchmark_cache:
            benchmark_df, _ = capture_output(
                stock_1.calc_benchmark_to_latest,
                df_all,
                signal_date,
                total_invest,
                benchmark_ticker=benchmark_ticker,
                benchmark_name=benchmark_name,
                expected_entry_date=market_entry_date,
            )
            hold_benchmark_cache[cache_key] = benchmark_df
        return hold_benchmark_cache[cache_key]

    def read_day_benchmark(benchmark_df, days):
        if benchmark_df is None or benchmark_df.empty:
            return None, None
        value_col = f"Day{days}_Net_Value"
        return_col = f"Day{days}_Net_Return_%"
        if value_col not in benchmark_df.columns:
            return None, None
        return benchmark_df.iloc[0][value_col], benchmark_df.iloc[0][return_col]

    def read_hold_benchmark(benchmark_df):
        if benchmark_df is None or benchmark_df.empty:
            return None, None
        return benchmark_df.iloc[0]["Net_Value"], benchmark_df.iloc[0]["Net_Return_%"]

    def append_compare_row(mode, valid_count, total_invest, strategy_value, strategy_return, bench2, bench0050, note=""):
        bench2_value, bench2_return = bench2
        bench0050_value, bench0050_return = bench0050
        diff2 = None
        diff0050 = None
        if bench2_return is not None and not pd.isna(bench2_return):
            diff2 = strategy_return - float(bench2_return)
        if bench0050_return is not None and not pd.isna(bench0050_return):
            diff0050 = strategy_return - float(bench0050_return)

        winners = []
        if diff2 is not None:
            winners.append("勝正2" if diff2 > 0 else "輸正2")
        if diff0050 is not None:
            winners.append("勝0050" if diff0050 > 0 else "輸0050")

        rows.append({
            "比較方式": mode,
            "有效檔數": valid_count,
            "投入金額": fmt_money(total_invest),
            "策略淨值": fmt_money(strategy_value),
            "策略報酬%": fmt_pct(strategy_return),
            f"{stock_1.BENCHMARK_NAME} 淨值": fmt_money(bench2_value),
            f"{stock_1.BENCHMARK_NAME} 報酬%": fmt_pct(bench2_return),
            f"{stock_1.BENCHMARK_0050_NAME} 淨值": fmt_money(bench0050_value),
            f"{stock_1.BENCHMARK_0050_NAME} 報酬%": fmt_pct(bench0050_return),
            "對正2差距%": fmt_pct(diff2),
            "對0050差距%": fmt_pct(diff0050),
            "勝負": " / ".join(winners) if winners else "N/A",
            "備註": note,
        })

    for days in FORWARD_DAYS:
        value_col = f"Day{days}_Net_Value"
        profit_col = f"Day{days}_Net_Profit"

        if value_col not in result_df.columns or profit_col not in result_df.columns:
            continue

        valid_df = result_df[result_df[value_col].notna()].copy()
        if valid_df.empty:
            continue

        valid_count = int(len(valid_df))
        total_invest = total_invest_for(valid_df)
        strategy_value = float(valid_df[value_col].sum())
        strategy_profit = float(valid_df[profit_col].sum())
        strategy_return = strategy_profit / total_invest * 100

        bench2 = read_day_benchmark(
            get_day_benchmark(total_invest, stock_1.BENCHMARK_TICKER, stock_1.BENCHMARK_NAME),
            days,
        )
        bench0050 = read_day_benchmark(
            get_day_benchmark(total_invest, stock_1.BENCHMARK_0050_TICKER, stock_1.BENCHMARK_0050_NAME),
            days,
        )
        append_compare_row(
            f"持有 {days} 日",
            valid_count,
            total_invest,
            strategy_value,
            strategy_return,
            bench2,
            bench0050,
        )

    summary_modes = [
        ("自訂停損/持有至今", "Stop_Net_Value", "Stop_Net_Profit"),
        ("買入後持有至今", "Hold_Today_Net_Value", "Hold_Today_Net_Profit"),
    ]
    for mode, value_col, profit_col in summary_modes:
        if value_col not in result_df.columns or profit_col not in result_df.columns:
            continue

        valid_df = result_df[result_df[value_col].notna()].copy()
        if valid_df.empty:
            continue

        valid_count = int(len(valid_df))
        total_invest = total_invest_for(valid_df)
        strategy_value = float(valid_df[value_col].sum())
        strategy_profit = float(valid_df[profit_col].sum())
        strategy_return = strategy_profit / total_invest * 100
        bench2 = read_hold_benchmark(
            get_hold_benchmark(total_invest, stock_1.BENCHMARK_TICKER, stock_1.BENCHMARK_NAME)
        )
        bench0050 = read_hold_benchmark(
            get_hold_benchmark(total_invest, stock_1.BENCHMARK_0050_TICKER, stock_1.BENCHMARK_0050_NAME)
        )
        note = ""
        if "Stop_Exit_Reason" in valid_df.columns and mode.startswith("自訂停損"):
            stop_count = valid_df["Stop_Exit_Reason"].astype(str).str.contains("觸發停損").sum()
            note = f"觸發停損 {int(stop_count)} 檔"

        append_compare_row(
            mode,
            valid_count,
            total_invest,
            strategy_value,
            strategy_return,
            bench2,
            bench0050,
            note=note,
        )

    return pd.DataFrame(rows)


def sidebar():
    st.sidebar.header("資料")
    st.sidebar.caption(
        f"週期：{stock_1.BACKTEST_PERIOD}｜批次：{stock_1.BATCH_SIZE}｜"
        f"yfinance threads：{stock_1.YF_THREADS}"
    )

    if st.sidebar.button("載入資料", use_container_width=True):
        st.session_state.data_loaded = True

    if st.sidebar.button("強制重新下載", use_container_width=True):
        st.session_state.refresh_token += 1
        st.session_state.data_loaded = True
        st.session_state.market_data = None
        st.session_state.stock_dict = {}
        st.session_state.loaded_refresh_token = None
        st.session_state.fundamental_cache = {}
        st.session_state.scan_result = pd.DataFrame()
        st.session_state.attack_result = pd.DataFrame()
        st.session_state.conservative_result = pd.DataFrame()
        st.session_state.history_result = pd.DataFrame()
        st.session_state.history_comparison = pd.DataFrame()
        st.session_state.single_result = pd.DataFrame()

    st.sidebar.divider()
    st.sidebar.caption("Streamlit Community Cloud 部署時，主檔填 streamlit_app.py。")


def latest_tab():
    st.subheader("最新 Top20")
    st.caption("使用最新交易日資料計算 AI_Score，排序後取前 20 檔。")

    if st.button("掃描最新 Top20", type="primary", use_container_width=True):
        df_all, _, data_logs = get_data()
        if not has_valid_data(df_all):
            st.error("資料載入失敗，請看下方執行訊息。")
            return

        result_df, run_logs = capture_output(stock_1.run_today_scan, df_all)
        attack_df, attack_logs = capture_output(stock_1.run_aggressive_scan, df_all)
        conservative_df, conservative_logs = capture_output(stock_1.run_conservative_scan, df_all)
        st.session_state.scan_result = result_df
        st.session_state.attack_result = attack_df
        st.session_state.conservative_result = conservative_df
        st.session_state.last_logs = (
            f"{data_logs}\n{run_logs}\n{attack_logs}\n{conservative_logs}"
        ).strip()

    if not st.session_state.attack_result.empty:
        st.markdown(f"**強勢攻擊 Top{stock_1.AGGRESSIVE_TOP_N} / Top3**")
        render_attack_table(st.session_state.attack_result)

    if not st.session_state.conservative_result.empty:
        st.markdown(f"**保守策略 Top{stock_1.CONSERVATIVE_TOP_N} / Top3**")
        render_conservative_table(st.session_state.conservative_result)

    st.markdown("**Top20 觀察名單**")
    cols = [
        "Rank", "ID", "Name", "Industry", "Close", "AI_Score", "Integrated_Score",
        "Aggressive_Tier", "Conservative_Tier", "Avg_Value_20", "Volume_Ratio", "ROC_3",
        "ROC_5", "F_ROC_10", "Stop_Loss_Price", "Sell_Zone", "Max_Buy_Price", "Hint",
    ]
    render_table(st.session_state.scan_result, cols, height=520)
    render_fundamentals_panel(
        st.session_state.scan_result,
        st.session_state.market_data,
        st.session_state.stock_dict,
        key_prefix="latest",
    )


def history_tab():
    st.subheader("歷史日期驗證")
    st.caption("輸入指定日期，系統會用該交易日以前的資料選 Top20，再驗證後續報酬。")

    default_date = datetime.now().strftime("%Y/%m/%d")
    target_date = st.text_input("日期", value=default_date, placeholder="2026/04/13")
    stop_loss_pct = st.slider(
        "自訂停損%",
        min_value=3.0,
        max_value=20.0,
        value=float(stock_1.DEFAULT_STOP_LOSS_PCT),
        step=0.5,
        help="回測會用自訂停損%與技術停損價中較接近買進價的一個作為出場線。",
    )

    if st.button("驗證歷史 Top20", type="primary", use_container_width=True):
        df_all, _, data_logs = get_data()
        if not has_valid_data(df_all):
            st.error("資料載入失敗，請看下方執行訊息。")
            return

        result_df, run_logs = capture_output(
            stock_1.run_historical_signal_test,
            df_all,
            target_date_str=target_date,
            top_n=stock_1.TOP_N,
            forward_days_list=FORWARD_DAYS,
            capital_per_stock=stock_1.CAPITAL_PER_STOCK,
            stop_loss_pct=stop_loss_pct,
        )
        comparison_df = build_history_comparison(df_all, result_df, target_date)

        st.session_state.history_result = result_df
        st.session_state.history_comparison = comparison_df
        st.session_state.last_logs = f"{data_logs}\n{run_logs}".strip()

    if not st.session_state.history_comparison.empty:
        st.markdown("**績效比較**")
        bench_value_col = f"{stock_1.BENCHMARK_NAME} 淨值"
        if (
            bench_value_col in st.session_state.history_comparison.columns
            and st.session_state.history_comparison[bench_value_col].isna().all()
        ):
            st.warning(
                f"目前快取沒有 {stock_1.BENCHMARK_NAME} ({stock_1.BENCHMARK_TICKER}) "
                "資料。請按左側「強制重新下載」更新快取後再驗證。"
            )
        render_table(st.session_state.history_comparison, height=320)

    st.markdown("**推薦名單**")
    cols = [
        "Rank", "ID", "Name", "Industry", "AI_Score", "Integrated_Score",
        "Aggressive_Tier", "Conservative_Tier", "Entry_Date", "Entry_Open", "Entry_Gap_%",
        "Entry_Filter", "Backtest_Stop_Price", "Stop_Loss_Pct", "Sell_Zone",
        "Stop_Exit_Date", "Stop_Exit_Price", "Stop_Exit_Reason", "Stop_Net_Return_%",
        "Hold_Today_Date", "Hold_Today_Close", "Hold_Today_Net_Return_%",
        "Day1_Net_Return_%", "Day7_Net_Return_%", "Day30_Net_Return_%",
        "Avg_Value_20", "Volume_Ratio", "Hint",
    ]
    render_table(st.session_state.history_result, cols, height=430)
    render_fundamentals_panel(
        st.session_state.history_result,
        st.session_state.market_data,
        st.session_state.stock_dict,
        key_prefix="history",
    )


def single_tab():
    st.subheader("單股分析")
    code = st.text_input("股票代號", value="", placeholder="例如 2330 或 6187")

    if st.button("分析單股", type="primary", use_container_width=True):
        df_all, _, data_logs = get_data()
        if not has_valid_data(df_all):
            st.error("資料載入失敗，請看下方執行訊息。")
            return

        result_df, run_logs = capture_output(stock_1.analyze_single_stock, df_all, code)
        st.session_state.single_result = result_df
        st.session_state.last_logs = f"{data_logs}\n{run_logs}".strip()

    result_df = st.session_state.single_result
    if result_df is None or result_df.empty:
        st.info("輸入股票代號後按分析。")
        return

    row = result_df.iloc[0]
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("收盤", fmt_number(row.get("Close")))
    col2.metric("AI Score", fmt_number(row.get("AI_Score")))
    col3.metric("整合分數", fmt_number(row.get("Integrated_Score")))
    col4.metric("趨勢", row.get("Trend_View", "-"))
    market_rank = row.get("Market_Rank")
    market_total = row.get("Market_Total")
    if market_rank is None or market_total is None or pd.isna(market_rank) or pd.isna(market_total):
        rank_text = "-"
    else:
        rank_text = f"{int(market_rank)} / {int(market_total)}"
    col5.metric("市場排名", rank_text)

    market_message = row.get("Market_Message", "")
    if isinstance(market_message, str) and market_message.strip():
        if row.get("Market_Status") == "紅燈":
            st.error(market_message)
        else:
            st.success(market_message)

    action_view = row.get("Action_View", "")
    if isinstance(action_view, str) and action_view.strip():
        st.info(action_view)

    score_status = row.get("Score_Status", "")
    score_reason = row.get("Score_Reason", "")
    if isinstance(score_status, str) and score_status.strip():
        if score_status == "列入候選池":
            st.success(score_reason)
        else:
            st.warning(f"{score_status}：{score_reason}")

    hint = row.get("Hint", "")
    if isinstance(hint, str) and hint.strip():
        st.warning(hint)

    if isinstance(row.get("Conservative_Tier", ""), str) and row.get("Conservative_Tier", "").strip():
        st.success(
            f"保守策略入選：{row.get('Conservative_Tier')}｜保守分數 {fmt_number(row.get('Conservative_Score'))}"
        )

    plan_cols = st.columns(4)
    plan_cols[0].metric("停損價", fmt_number(row.get("Stop_Loss_Price")))
    plan_cols[1].metric("最高追價", fmt_number(row.get("Max_Buy_Price")))
    capital = row.get("Suggested_Capital")
    plan_cols[2].metric("建議金額", "-" if capital is None or pd.isna(capital) else f"{float(capital):,.0f}")
    shares = row.get("Suggested_Shares")
    plan_cols[3].metric("建議股數", "-" if shares is None or pd.isna(shares) else f"{float(shares):,.0f}")
    st.metric("停利觀察區", row.get("Sell_Zone", "-"))
    if isinstance(row.get("Exit_Rule", ""), str) and row.get("Exit_Rule", "").strip():
        st.caption(row.get("Exit_Rule"))

    cols = [
        "Date", "ID", "Name", "Industry", "Close", "MA5", "MA20", "MA60",
        "Trend_Points", "Trend_View", "Score_Status", "Score_Reason",
        "AI_Score", "Integrated_Score", "Institution_Score", "Conservative_Score",
        "Aggressive_Rank", "Aggressive_Tier", "Conservative_Rank", "Conservative_Tier", "Market_PR_%",
        "ROC_1", "ROC_3", "ROC_5", "ROC_10", "ROC_20", "ROC_30",
        "Volume_Ratio", "Avg_Value_20", "Stop_Loss_Price", "Sell_Zone", "Max_Buy_Price",
        "Suggested_Capital", "Recent_20_High", "Recent_20_Low", "Reasons",
    ]
    render_table(result_df, cols, height=260)
    render_fundamentals_panel(
        result_df,
        st.session_state.market_data,
        st.session_state.stock_dict,
        key_prefix="single",
    )


def main():
    init_state()
    sidebar()

    st.title("台股 AI 動能掃描")
    st.caption("資料來源包含 yfinance 與公開資料。結果僅供研究，不構成投資建議。")

    df_all = None
    if st.session_state.data_loaded:
        df_all, _, _ = get_data()
    render_status(df_all)
    render_market_risk(df_all)

    tab1, tab2, tab3 = st.tabs(["最新 Top20", "歷史驗證", "單股分析"])
    with tab1:
        latest_tab()
    with tab2:
        history_tab()
    with tab3:
        single_tab()

    with st.expander("執行訊息", expanded=False):
        st.text(st.session_state.last_logs or "尚無訊息")


if __name__ == "__main__":
    main()
