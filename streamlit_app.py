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


def capture_output(func, *args, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


@st.cache_resource(show_spinner=False)
def load_market_data(refresh_token=0, _progress_callback=None):
    force_refresh = refresh_token > 0
    (df_all, stock_dict), logs = capture_output(
        stock_1.prepare_data,
        force_refresh=force_refresh,
        progress_callback=_progress_callback,
    )

    if df_all is not None and not df_all.empty and "Date" in df_all.columns:
        df_all = df_all.copy()
        df_all["Date"] = pd.to_datetime(df_all["Date"])

    return df_all, stock_dict, logs


def init_state():
    st.session_state.setdefault("refresh_token", 0)
    st.session_state.setdefault("data_loaded", False)
    st.session_state.setdefault("last_logs", "")
    st.session_state.setdefault("scan_result", pd.DataFrame())
    st.session_state.setdefault("history_result", pd.DataFrame())
    st.session_state.setdefault("history_comparison", pd.DataFrame())
    st.session_state.setdefault("single_result", pd.DataFrame())


def get_data():
    st.session_state.data_loaded = True
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
            _progress_callback=update_progress,
        )
    progress_bar.progress(1.0)
    status_box.success("資料載入完成。")
    st.session_state.last_logs = logs
    return df_all, stock_dict, logs


def has_valid_data(df_all):
    return df_all is not None and not df_all.empty and "Date" in df_all.columns


def existing_cols(df, cols):
    return [col for col in cols if col in df.columns]


def render_table(df, cols=None):
    if df is None or df.empty:
        st.info("目前沒有資料。")
        return

    view = df[existing_cols(df, cols)] if cols else df
    st.dataframe(view, use_container_width=True, hide_index=True)


def fmt_number(value, digits=2):
    if value is None or pd.isna(value):
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


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
            "投入金額": total_invest,
            "Top20 淨值": strategy_value,
            "Top20 報酬%": strategy_return,
            f"{stock_1.BENCHMARK_NAME} 淨值": benchmark_value,
            f"{stock_1.BENCHMARK_NAME} 報酬%": benchmark_return,
            "差距%": diff_return,
            "差距金額": diff_value,
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
        load_market_data.clear()

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
    render_table(st.session_state.scan_result, cols)


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
        render_table(st.session_state.history_comparison)

    st.markdown("**推薦名單**")
    cols = [
        "Rank", "ID", "Name", "AI_Score", "Entry_Date", "Entry_Open",
        "Day1_Net_Return_%", "Day7_Net_Return_%", "Day30_Net_Return_%",
        "Avg_Value_20", "Volume_Ratio", "Hint",
    ]
    render_table(st.session_state.history_result, cols)


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

    hint = row.get("Hint", "")
    if isinstance(hint, str) and hint.strip():
        st.warning(hint)

    cols = [
        "Date", "ID", "Name", "Close", "MA5", "MA20", "MA60",
        "Trend_Points", "Trend_View", "AI_Score", "Market_PR_%",
        "ROC_1", "ROC_3", "ROC_5", "ROC_10", "ROC_20", "ROC_30",
        "Volume_Ratio", "Avg_Value_20", "Recent_20_High", "Recent_20_Low",
        "Reasons",
    ]
    render_table(result_df, cols)


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
