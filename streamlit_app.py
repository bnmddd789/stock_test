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
    "Close": "收盤",
    "AI_Score": "AI 分數",
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
    "Close": 2,
    "Entry_Open": 2,
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

    if df_all is not None and not df_all.empty and "Date" in df_all.columns:
        df_all = df_all.copy()
        df_all["Date"] = pd.to_datetime(df_all["Date"])

    return df_all, stock_dict, logs


def init_state():
    st.session_state.setdefault("refresh_token", 0)
    st.session_state.setdefault("loaded_refresh_token", None)
    st.session_state.setdefault("data_loaded", False)
    st.session_state.setdefault("market_data", None)
    st.session_state.setdefault("stock_dict", {})
    st.session_state.setdefault("last_logs", "")
    st.session_state.setdefault("scan_result", pd.DataFrame())
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
    benchmark_cache = {}

    for days in FORWARD_DAYS:
        value_col = f"Day{days}_Net_Value"
        profit_col = f"Day{days}_Net_Profit"

        if value_col not in result_df.columns or profit_col not in result_df.columns:
            continue

        valid_df = result_df[result_df[value_col].notna()].copy()
        if valid_df.empty:
            continue

        valid_count = int(len(valid_df))
        total_invest = stock_1.CAPITAL_PER_STOCK * valid_count
        strategy_value = float(valid_df[value_col].sum())
        strategy_profit = float(valid_df[profit_col].sum())
        strategy_return = strategy_profit / total_invest * 100

        if total_invest not in benchmark_cache:
            benchmark_df, _ = capture_output(
                stock_1.calc_benchmark_result,
                df_all,
                signal_date,
                total_invest,
                forward_days_list=FORWARD_DAYS,
                benchmark_ticker=stock_1.BENCHMARK_TICKER,
                benchmark_name=stock_1.BENCHMARK_NAME,
                expected_entry_date=market_entry_date,
            )
            benchmark_cache[total_invest] = benchmark_df

        benchmark_return = None
        benchmark_value = None
        benchmark_df = benchmark_cache[total_invest]

        if benchmark_df is not None and not benchmark_df.empty:
            bench_value_col = f"Day{days}_Net_Value"
            bench_return_col = f"Day{days}_Net_Return_%"
            if bench_value_col in benchmark_df.columns:
                benchmark_value = benchmark_df.iloc[0][bench_value_col]
                benchmark_return = benchmark_df.iloc[0][bench_return_col]

        diff_return = None
        diff_value = None
        winner = "N/A"

        if benchmark_return is not None and not pd.isna(benchmark_return):
            diff_return = strategy_return - float(benchmark_return)
            diff_value = strategy_value - float(benchmark_value)
            winner = "Top20" if diff_return > 0 else stock_1.BENCHMARK_NAME

        rows.append({
            "持有日": days,
            "有效檔數": valid_count,
            "投入金額": fmt_money(total_invest),
            "Top20 淨值": fmt_money(strategy_value),
            "Top20 報酬%": fmt_pct(strategy_return),
            f"{stock_1.BENCHMARK_NAME} 淨值": fmt_money(benchmark_value),
            f"{stock_1.BENCHMARK_NAME} 報酬%": fmt_pct(benchmark_return),
            "差距%": fmt_pct(diff_return),
            "差距金額": fmt_money(diff_value),
            "勝出": winner,
        })

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
        st.session_state.scan_result = result_df
        st.session_state.last_logs = f"{data_logs}\n{run_logs}".strip()

    cols = [
        "Rank", "ID", "Name", "Close", "AI_Score", "Avg_Value_20",
        "Volume_Ratio", "ROC_3", "ROC_5", "F_ROC_10", "Hint",
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
        "Rank", "ID", "Name", "AI_Score", "Entry_Date", "Entry_Open",
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
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("收盤", fmt_number(row.get("Close")))
    col2.metric("AI Score", fmt_number(row.get("AI_Score")))
    col3.metric("趨勢", row.get("Trend_View", "-"))
    market_rank = row.get("Market_Rank")
    market_total = row.get("Market_Total")
    if market_rank is None or market_total is None or pd.isna(market_rank) or pd.isna(market_total):
        rank_text = "-"
    else:
        rank_text = f"{int(market_rank)} / {int(market_total)}"
    col4.metric("市場排名", rank_text)

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

    cols = [
        "Date", "ID", "Name", "Close", "MA5", "MA20", "MA60",
        "Trend_Points", "Trend_View", "Score_Status", "Score_Reason",
        "AI_Score", "Market_PR_%",
        "ROC_1", "ROC_3", "ROC_5", "ROC_10", "ROC_20", "ROC_30",
        "Volume_Ratio", "Avg_Value_20", "Recent_20_High", "Recent_20_Low",
        "Reasons",
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
