# -*- coding: utf-8 -*-
import contextlib
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

import stock_1


HOST = "0.0.0.0"
PORT = 8765
WEB_FILE = Path(__file__).with_name("stock_mobile.html")

DF_ALL = None
STOCK_DICT = None
FUNDAMENTAL_CACHE = {}


def capture_output(func, *args, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


def ensure_data(force_refresh=False):
    global DF_ALL, STOCK_DICT

    if force_refresh or DF_ALL is None or DF_ALL.empty:
        (DF_ALL, STOCK_DICT), logs = capture_output(
            stock_1.prepare_data,
            force_refresh=force_refresh
        )
    else:
        logs = ""

    return logs


def clean_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def frame_to_records(df, limit=None):
    if df is None or df.empty:
        return []

    if limit is not None:
        df = df.head(limit)

    records = []
    for row in df.to_dict(orient="records"):
        records.append({key: clean_value(value) for key, value in row.items()})
    return records


def compact_text(text, max_len=220):
    if not text:
        return None

    text = " ".join(str(text).split())
    if len(text) <= max_len:
        return text

    return text[:max_len].rstrip() + "..."


def resolve_ticker(record):
    ticker = record.get("Ticker")
    if ticker:
        return ticker

    stock_id = str(record.get("ID") or "").strip()
    if not stock_id or DF_ALL is None or DF_ALL.empty:
        return None

    matched = DF_ALL[DF_ALL["ID"].astype(str) == stock_id]
    if matched.empty:
        return None

    return matched["Ticker"].iloc[0]


def local_stock_info(ticker):
    if not ticker or not STOCK_DICT:
        return {}

    return STOCK_DICT.get(ticker, {}) or {}


def get_fundamentals(ticker):
    if not ticker:
        return {}

    if ticker in FUNDAMENTAL_CACHE:
        return FUNDAMENTAL_CACHE[ticker]

    local_info = local_stock_info(ticker)
    result = {
        "Ticker": ticker,
        "Industry": local_info.get("ind"),
        "Sector": None,
        "Business": None,
        "MarketCap": None,
        "PE": None,
        "ForwardPE": None,
        "PB": None,
        "EPS": None,
        "DividendYield_%": None,
        "Website": None,
    }

    try:
        ticker_obj = stock_1.yf.Ticker(ticker)
        info = ticker_obj.info or {}

        dividend_yield = info.get("dividendYield")
        if dividend_yield is not None and dividend_yield <= 1:
            dividend_yield = dividend_yield * 100

        result.update({
            "Industry": info.get("industry") or result["Industry"],
            "Sector": info.get("sector") or result["Sector"],
            "Business": compact_text(info.get("longBusinessSummary")),
            "MarketCap": clean_value(info.get("marketCap")),
            "PE": clean_value(info.get("trailingPE")),
            "ForwardPE": clean_value(info.get("forwardPE")),
            "PB": clean_value(info.get("priceToBook")),
            "EPS": clean_value(info.get("trailingEps")),
            "DividendYield_%": clean_value(dividend_yield),
            "Website": info.get("website"),
        })
    except Exception:
        pass

    if not result["Business"]:
        industry = result["Industry"] or "產業分類暫無資料"
        result["Business"] = f"目前可取得的分類為：{industry}。"

    FUNDAMENTAL_CACHE[ticker] = result
    return result


def attach_fundamentals(records):
    enriched = []

    for record in records:
        ticker = resolve_ticker(record)
        record = dict(record)
        record["Fundamentals"] = get_fundamentals(ticker)
        enriched.append(record)

    return enriched


def data_status():
    if DF_ALL is None or DF_ALL.empty:
        return {
            "loaded": False,
            "rows": 0,
            "stocks": 0,
            "startDate": None,
            "endDate": None,
            "topN": stock_1.TOP_N,
        }

    return {
        "loaded": True,
        "rows": int(len(DF_ALL)),
        "stocks": int(DF_ALL["Ticker"].nunique()),
        "startDate": clean_value(DF_ALL["Date"].min()),
        "endDate": clean_value(DF_ALL["Date"].max()),
        "topN": stock_1.TOP_N,
    }


def build_history_comparison(result_df, target_date, forward_days_list):
    if result_df is None or result_df.empty:
        return []

    target = stock_1.normalize_input_date(target_date)
    signal_date = stock_1.get_nearest_trading_date(DF_ALL, target)
    if signal_date is None:
        return []

    market_entry_date = stock_1.get_next_trading_date(DF_ALL, signal_date)
    if market_entry_date is None:
        return []

    rows = []
    benchmark_cache = {}

    for days in forward_days_list:
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
        win_rate = float((valid_df[profit_col] > 0).mean() * 100)

        if total_invest not in benchmark_cache:
            benchmark_df, _ = capture_output(
                stock_1.calc_benchmark_result,
                DF_ALL,
                signal_date,
                total_invest,
                forward_days_list=forward_days_list,
                benchmark_ticker=stock_1.BENCHMARK_TICKER,
                benchmark_name=stock_1.BENCHMARK_NAME,
                expected_entry_date=market_entry_date
            )
            benchmark_cache[total_invest] = benchmark_df

        benchmark_df = benchmark_cache[total_invest]
        benchmark_value = None
        benchmark_profit = None
        benchmark_return = None

        if benchmark_df is not None and not benchmark_df.empty:
            bench_value_col = f"Day{days}_Net_Value"
            bench_profit_col = f"Day{days}_Net_Profit"
            bench_return_col = f"Day{days}_Net_Return_%"

            if bench_value_col in benchmark_df.columns:
                benchmark_value = clean_value(benchmark_df.iloc[0][bench_value_col])
                benchmark_profit = clean_value(benchmark_df.iloc[0][bench_profit_col])
                benchmark_return = clean_value(benchmark_df.iloc[0][bench_return_col])

        diff_return = None
        diff_value = None
        winner = "N/A"

        if benchmark_return is not None:
            diff_return = strategy_return - float(benchmark_return)
            diff_value = strategy_value - float(benchmark_value)
            winner = "Top20" if diff_return > 0 else stock_1.BENCHMARK_NAME

        rows.append({
            "days": days,
            "validCount": valid_count,
            "invest": total_invest,
            "strategyValue": strategy_value,
            "strategyProfit": strategy_profit,
            "strategyReturn": strategy_return,
            "strategyWinRate": win_rate,
            "benchmarkName": stock_1.BENCHMARK_NAME,
            "benchmarkValue": benchmark_value,
            "benchmarkProfit": benchmark_profit,
            "benchmarkReturn": benchmark_return,
            "diffValue": diff_value,
            "diffReturn": diff_return,
            "winner": winner,
        })

    return rows


def json_response(handler, payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler, content, content_type="text/html; charset=utf-8", status=200):
    body = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class StockHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        try:
            if parsed.path in ["/", "/index.html"]:
                text_response(self, WEB_FILE.read_text(encoding="utf-8"))
                return

            if parsed.path == "/api/status":
                json_response(self, {"ok": True, "status": data_status()})
                return

            if parsed.path == "/api/scan":
                logs = ensure_data(force_refresh=False)
                df, run_logs = capture_output(stock_1.run_today_scan, DF_ALL)
                rows = attach_fundamentals(frame_to_records(df, limit=20))
                json_response(self, {
                    "ok": True,
                    "status": data_status(),
                    "rows": rows,
                    "logs": logs + run_logs,
                })
                return

            if parsed.path == "/api/history":
                target_date = params.get("date", [""])[0].strip()
                if not target_date:
                    json_response(self, {"ok": False, "error": "請輸入日期"}, status=400)
                    return

                logs = ensure_data(force_refresh=False)
                df, run_logs = capture_output(
                    stock_1.run_historical_signal_test,
                    DF_ALL,
                    target_date_str=target_date,
                    top_n=stock_1.TOP_N,
                    forward_days_list=[1, 3, 5, 7, 10, 14, 21, 30],
                    capital_per_stock=stock_1.CAPITAL_PER_STOCK
                )
                comparison = build_history_comparison(
                    df,
                    target_date,
                    [1, 3, 5, 7, 10, 14, 21, 30]
                )
                json_response(self, {
                    "ok": True,
                    "status": data_status(),
                    "rows": attach_fundamentals(frame_to_records(df)),
                    "comparison": comparison,
                    "logs": logs + run_logs,
                })
                return

            if parsed.path == "/api/single":
                code = params.get("code", [""])[0].strip()
                if not code:
                    json_response(self, {"ok": False, "error": "請輸入股票代號"}, status=400)
                    return

                logs = ensure_data(force_refresh=False)
                df, run_logs = capture_output(stock_1.analyze_single_stock, DF_ALL, code)
                json_response(self, {
                    "ok": True,
                    "status": data_status(),
                    "rows": attach_fundamentals(frame_to_records(df)),
                    "logs": logs + run_logs,
                })
                return

            if parsed.path == "/api/refresh":
                logs = ensure_data(force_refresh=True)
                json_response(self, {
                    "ok": True,
                    "status": data_status(),
                    "logs": logs,
                })
                return

            text_response(self, "Not found", "text/plain; charset=utf-8", status=404)

        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc)}, status=500)


def main():
    if not WEB_FILE.exists():
        raise FileNotFoundError(f"找不到前端檔案：{WEB_FILE}")

    server = ThreadingHTTPServer((HOST, PORT), StockHandler)
    print(f"手機版介面已啟動：http://127.0.0.1:{PORT}")
    print(f"同一個 Wi-Fi 的手機請開：http://你的電腦IP:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
