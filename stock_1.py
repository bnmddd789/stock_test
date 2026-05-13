# -*- coding: utf-8 -*-
import sys, os, requests, urllib3
import numpy as np
import pandas as pd
from datetime import datetime
import yfinance as yf
import warnings
import traceback
import pickle

warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

print("=" * 80)
print(" 🚀 MANUS AI 動能妖股雷達 + 回測 + 歷史日期驗證 + 快取版 啟動")
print("   🎯 任務：掃描台股全市場，尋找 AI 7 大動能極限飆股")
print("   🧪 回測：T 日收盤算分數，T+1 開盤進場，避免偷看答案")
print("   💾 快取：避免每次啟動都重新下載資料")
print("   ⚠️ HINT：提示漲停、爆量、過熱、流動性問題")
print("=" * 80)

# ==========================================
# 參數設定
# ==========================================
BACKTEST_PERIOD = "3y"
SCAN_PERIOD = "120d"
TOP_N = 20
BATCH_SIZE = 40
CAPITAL_PER_STOCK = 100_000
BENCHMARK_TICKER = "00631L.TW"   # 0050 正2
BENCHMARK_NAME = "0050正2"
SAVE_CSV_OUTPUT = False
# 成交量 / 成交金額門檻
# 台股建議先用成交金額，比單純成交量合理
MIN_AVG_VALUE_20 = 50_000_000     # 20日均成交金額，預設 5000 萬
MIN_TODAY_VALUE = 20_000_000      # 訊號日成交金額，預設 2000 萬
MIN_AVG_VOLUME_20 = 300           # 20日均量，單位依 yfinance，通常為股數；此條件可視情況調整

# 交易成本
COMMISSION = 0.001425
SELL_TAX = 0.003

# 快取資料夾
CACHE_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "MANUS_CACHE")
CACHE_FILE = os.path.join(CACHE_DIR, f"MANUS_DATA_{BACKTEST_PERIOD}.pkl")

FEATURES = [
    'F_Hist_Vol',
    'F_BB_Width',
    'F_P_to_MA60',
    'F_Trend_Strength',
    'F_P_to_MA20',
    'F_P_to_BBUpper',
    'F_ROC_10'
]

WEIGHTS = [29.08, 19.33, 10.39, 7.67, 7.26, 5.09, 4.25]


# ==========================================
# 抓取台股清單
# ==========================================
def get_tw_stock_list():
    print("📋 抓取全台股清單 (上市+上櫃)...")
    stock_dict = {}

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}

        for m in [2, 4]:
            url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={m}"
            res = requests.get(url, headers=headers, verify=False, timeout=20)
            df = pd.read_html(res.text)[0].iloc[1:]

            for _, row in df.iterrows():
                try:
                    code_name = str(row[0]).split()

                    if len(code_name) == 2:
                        code, name = code_name
                        cat = str(row[4])

                        if len(code) == 4 or code.startswith('00'):
                            if cat not in ['權證', '牛熊證', '認購(售)權證']:
                                suffix = ".TW" if m == 2 else ".TWO"
                                stock_dict[f"{code}{suffix}"] = {
                                    "name": name,
                                    "ind": cat
                                }
                except:
                    continue

    except Exception as e:
        print(f"❌ 抓取清單失敗: {e}")
        print("👉 若看到 lxml 錯誤，請先執行：")
        print("   python -m pip install lxml html5lib beautifulsoup4")

    return stock_dict


# ==========================================
# 特徵計算
# ==========================================
def calc_features(df, ticker, name):
    close = df['Close']
    open_ = df['Open']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    daily_ret = close.pct_change()

    hist_vol = daily_ret.rolling(20).std() * np.sqrt(252) * 100

    std20 = close.rolling(20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    bb_width = (bb_upper - bb_lower) / ma20 * 100

    p_to_ma60 = (close / ma60 - 1) * 100
    trend_str = (ma5 / ma60 - 1) * 100
    p_to_ma20 = (close / ma20 - 1) * 100
    p_to_bbupper = (close / bb_upper - 1) * 100
    roc_10 = close.pct_change(10) * 100

    value = close * volume
    avg_value_20 = value.rolling(20).mean()
    avg_volume_20 = volume.rolling(20).mean()

    vol_ratio = volume / avg_volume_20
    value_ratio = value / avg_value_20

    roc_1 = close.pct_change(1) * 100
    roc_3 = close.pct_change(3) * 100
    roc_5 = close.pct_change(5) * 100
    roc_20 = close.pct_change(20) * 100
    roc_30 = close.pct_change(30) * 100

    # 台股一般股票漲停約 10%，這裡用 9.5% 當疑似漲停提示
    is_limit_up_like = roc_1 >= 9.5

    out = pd.DataFrame({
        'Date': df.index,
        'Ticker': ticker,
        'ID': ticker.replace(".TW", "").replace(".TWO", ""),
        'Name': name,

        'Open': open_.values,
        'High': high.values,
        'Low': low.values,
        'Close': close.values,
        'Volume': volume.values,

        'MA5': ma5.values,
        'MA20': ma20.values,
        'MA60': ma60.values,

        'Value': value.values,
        'Avg_Value_20': avg_value_20.values,
        'Avg_Volume_20': avg_volume_20.values,
        'Volume_Ratio': vol_ratio.values,
        'Value_Ratio': value_ratio.values,

        'ROC_1': roc_1.values,
        'ROC_3': roc_3.values,
        'ROC_5': roc_5.values,
        'ROC_20': roc_20.values,
        'ROC_30': roc_30.values,

        'Is_Limit_Up_Like': is_limit_up_like.values,

        'F_Hist_Vol': hist_vol.values,
        'F_BB_Width': bb_width.values,
        'F_P_to_MA60': p_to_ma60.values,
        'F_Trend_Strength': trend_str.values,
        'F_P_to_MA20': p_to_ma20.values,
        'F_P_to_BBUpper': p_to_bbupper.values,
        'F_ROC_10': roc_10.values,
    })

    # 計算連續疑似漲停天數，只用過去資料
    limit_flags = out['Is_Limit_Up_Like'].fillna(False).astype(bool).values
    consecutive = []
    count = 0

    for flag in limit_flags:
        if flag:
            count += 1
        else:
            count = 0
        consecutive.append(count)

    out['Consecutive_Limit_Up_Like'] = consecutive

    # 回測用資料，不參與選股分數
    out['Next_Open'] = out['Open'].shift(-1)
    out['Next2_Open'] = out['Open'].shift(-2)
    out['Next_OpenToOpen_Return'] = out['Next2_Open'] / out['Next_Open'] - 1

    out['Entry_Date'] = out['Date'].shift(-1)
    out['Exit_Date'] = out['Date'].shift(-2)

    feature_required_cols = FEATURES + [
        'MA5',
        'MA20',
        'MA60',
        'Avg_Value_20',
        'Avg_Volume_20',
        'Volume_Ratio',
        'Value_Ratio',
        'ROC_1',
        'ROC_3',
        'ROC_5',
        'ROC_20',
        'ROC_30',
    ]
    out = out.dropna(subset=feature_required_cols)

    return out


# ==========================================
# 下載全市場資料
# ==========================================
def download_all_data(stock_dict, period):
    print(f"⛏️ 下載歷史資料 period={period} ...")

    all_tickers = list(stock_dict.keys())
    all_feature_rows = []

    for i in range(0, len(all_tickers), BATCH_SIZE):
        batch = all_tickers[i:i + BATCH_SIZE]
        print(f"   下載進度: {min(i + BATCH_SIZE, len(all_tickers))}/{len(all_tickers)}...", end='\r')

        try:
            data = yf.download(
                batch,
                period=period,
                interval="1d",
                group_by='ticker',
                auto_adjust=True,
                progress=False,
                threads=True
            )

            for ticker in batch:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if ticker not in data.columns.get_level_values(0):
                            continue
                        df = data[ticker].copy()
                    else:
                        df = data.copy()

                    if df.empty:
                        continue

                    needed = ['Open', 'High', 'Low', 'Close', 'Volume']
                    if not all(c in df.columns for c in needed):
                        continue

                    df = df[needed].dropna()

                    if len(df) < 90:
                        continue

                    feature_df = calc_features(df, ticker, stock_dict[ticker]['name'])

                    if not feature_df.empty:
                        all_feature_rows.append(feature_df)

                except:
                    continue

        except Exception as e:
            print(f"\n⚠️ 批次下載失敗: {batch[:3]}... error={e}")
            continue

    print("\n✅ 歷史資料下載完成！")

    if len(all_feature_rows) == 0:
        return pd.DataFrame()

    df_all = pd.concat(all_feature_rows, ignore_index=True)
    df_all['Date'] = pd.to_datetime(df_all['Date'])

    return df_all


# ==========================================
# 快取功能
# ==========================================
def save_cache(df_all, stock_dict):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)

        payload = {
            'created_at': datetime.now(),
            'period': BACKTEST_PERIOD,
            'df_all': df_all,
            'stock_dict': stock_dict
        }

        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(payload, f)

        print(f"💾 已儲存快取：{CACHE_FILE}")

    except Exception as e:
        print(f"⚠️ 快取儲存失敗：{e}")


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return None, None

    try:
        with open(CACHE_FILE, 'rb') as f:
            payload = pickle.load(f)

        df_all = payload.get('df_all', pd.DataFrame())
        stock_dict = payload.get('stock_dict', {})
        created_at = payload.get('created_at', None)

        if df_all is None or df_all.empty:
            return None, None

        df_all['Date'] = pd.to_datetime(df_all['Date'])

        print(f"💾 已讀取快取資料：{CACHE_FILE}")
        if created_at:
            print(f"   快取建立時間：{created_at}")

        latest_date = df_all['Date'].max()
        print(f"   快取最新交易日：{latest_date.date()}")

        return df_all, stock_dict

    except Exception as e:
        print(f"⚠️ 讀取快取失敗：{e}")
        return None, None


def is_cache_fresh(df_all):
    latest_date = pd.to_datetime(df_all['Date']).max().date()
    today = datetime.now().date()

    if latest_date >= today:
        return True

    business_days_after_latest = pd.bdate_range(
        start=pd.to_datetime(latest_date) + pd.Timedelta(days=1),
        end=pd.to_datetime(today)
    )

    return len(business_days_after_latest) <= 1


def prepare_data(force_refresh=False):
    if not force_refresh:
        df_all, stock_dict = load_cache()
        if df_all is not None and not df_all.empty:
            if is_cache_fresh(df_all):
                return df_all, stock_dict
            latest_date = pd.to_datetime(df_all['Date']).max().date()
            print(f"⚠️ 快取資料偏舊，最新交易日為 {latest_date}，改為重新下載。")

    stock_dict = get_tw_stock_list()
    print(f"✅ 取得標的共 {len(stock_dict)} 檔。")

    if len(stock_dict) == 0:
        print("❌ 台股清單為 0，請先確認 lxml / html5lib / beautifulsoup4 是否已安裝。")
        return pd.DataFrame(), {}

    df_all = download_all_data(stock_dict, BACKTEST_PERIOD)

    if df_all.empty:
        print("❌ 沒有足夠資料可以運算。")
        return pd.DataFrame(), {}

    save_cache(df_all, stock_dict)

    return df_all, stock_dict


# ==========================================
# HINT 風險提示
# ==========================================
def build_hint(row):
    hints = []

    if row.get('Consecutive_Limit_Up_Like', 0) >= 2:
        hints.append(f"疑似連續漲停 {int(row['Consecutive_Limit_Up_Like'])} 天，隔日追高風險大")
    elif row.get('Is_Limit_Up_Like', False):
        hints.append("訊號日疑似漲停，隔日可能開高震盪")

    if row.get('ROC_3', 0) >= 20:
        hints.append(f"近3日漲幅 {row['ROC_3']:.1f}%，短線過熱")
    elif row.get('ROC_5', 0) >= 30:
        hints.append(f"近5日漲幅 {row['ROC_5']:.1f}%，短線過熱")

    if row.get('F_P_to_MA20', 0) >= 20:
        hints.append(f"距離20MA {row['F_P_to_MA20']:.1f}%，乖離偏大")

    if row.get('F_P_to_BBUpper', 0) >= 0:
        hints.append("收盤已突破布林上緣，可能是強突破，也可能短線過熱")

    if row.get('Volume_Ratio', 0) >= 3:
        hints.append(f"爆量，成交量約20日均量 {row['Volume_Ratio']:.1f} 倍")

    if row.get('Avg_Value_20', 0) < MIN_AVG_VALUE_20:
        hints.append("20日均成交金額不足，流動性風險")

    if row.get('Value', 0) < MIN_TODAY_VALUE:
        hints.append("訊號日成交金額偏低，進出可能滑價")

    if len(hints) == 0:
        hints.append("暫無明顯過熱提示，但仍需看隔日開盤與大盤狀況")

    return "；".join(hints)


# ==========================================
# 每日評分
# ==========================================
def score_one_day(day_df):
    day_df = day_df.copy()

    day_df = day_df.dropna(subset=FEATURES + [
        'Close',
        'MA5',
        'Avg_Value_20',
        'Value',
        'Avg_Volume_20',
    ]).copy()

    # 原本防守濾網：收盤價站上 5MA
    day_df = day_df[day_df['Close'] >= day_df['MA5']].copy()

    # 新增成交金額 / 成交量門檻
    day_df = day_df[
        (day_df['Avg_Value_20'] >= MIN_AVG_VALUE_20) &
        (day_df['Value'] >= MIN_TODAY_VALUE) &
        (day_df['Avg_Volume_20'] >= MIN_AVG_VOLUME_20)
    ].copy()

    if day_df.empty:
        return day_df

    for f in FEATURES:
        day_df[f + '_Rank'] = day_df[f].rank(pct=True)

    day_df['AI_Score'] = 0.0

    for f, w in zip(FEATURES, WEIGHTS):
        day_df['AI_Score'] += day_df[f + '_Rank'] * w

    day_df['AI_Score'] = day_df['AI_Score'] / sum(WEIGHTS) * 100

    if not day_df.empty:
        day_df['Hint'] = day_df.apply(build_hint, axis=1)

    return day_df


# ==========================================
# 今日掃描
# ==========================================
def run_today_scan(df_all):
    print("🧠 執行最新一日 AI 權重運算與全市場排名...")

    latest_date = df_all['Date'].max()
    latest_df = df_all[df_all['Date'].dt.date == latest_date.date()].copy()

    if latest_df.empty:
        print("❌ 沒有最新資料可以掃描。")
        return pd.DataFrame()

    scored = score_one_day(latest_df)

    if scored.empty:
        print("❌ 最新日沒有符合成交量與 MA5 條件的標的。")
        return pd.DataFrame()

    top20 = scored.sort_values(by='AI_Score', ascending=False).head(20)

    print("\n" + "=" * 100)
    print(f" 🎯 最新交易日 AI 動能極限妖股 TOP 20：{latest_date.date()}")
    print("=" * 100)
    print(f"{'排名':<4} | {'代號':<6} | {'股名':<8} | {'收盤':<8} | {'AI分數':<8} | {'20日均成交金額':<14} | HINT")
    print("-" * 100)

    for i, (_, row) in enumerate(top20.iterrows(), 1):
        avg_value = row['Avg_Value_20'] / 10000
        print(
            f"{i:<4} | {row['ID']:<6} | {str(row['Name'])[:6]:<8} | "
            f"{row['Close']:<8.2f} | {row['AI_Score']:<8.2f} | "
            f"{avg_value:>10.0f}萬 | {row['Hint']}"
        )

    print("=" * 100)

    return top20

def normalize_ticker_input(code):
    """
    支援輸入：
    2330
    2330.TW
    6187.TWO
    """
    code = code.strip().upper()

    if code.endswith(".TW") or code.endswith(".TWO"):
        return code

    if len(code) == 4 or code.startswith("00"):
        # 先預設上市 .TW，若找不到再試 .TWO
        return code + ".TW"

    return code


def analyze_single_stock(df_all, code):
    input_ticker = normalize_ticker_input(code)

    # 先找上市
    stock_df = df_all[df_all['Ticker'] == input_ticker].copy()

    # 如果上市找不到，改找上櫃
    if stock_df.empty and input_ticker.endswith(".TW"):
        input_ticker = input_ticker.replace(".TW", ".TWO")
        stock_df = df_all[df_all['Ticker'] == input_ticker].copy()

    if stock_df.empty:
        print(f"❌ 找不到股票資料：{code}")
        print("👉 請確認代號是否正確，或先執行模式 5 更新快取。")
        return pd.DataFrame()

    stock_df = stock_df.sort_values('Date').reset_index(drop=True)

    latest = stock_df.iloc[-1]
    latest_date = latest['Date']

    # 用最新交易日全市場資料計算該股 AI_Score 排名
    latest_market_df = df_all[df_all['Date'].dt.date == latest_date.date()].copy()
    scored_market = score_one_day(latest_market_df)

    stock_score_row = scored_market[scored_market['Ticker'] == latest['Ticker']]

    if not stock_score_row.empty:
        ai_score = stock_score_row.iloc[0]['AI_Score']
        scored_market = scored_market.copy()
        scored_market['Market_Rank'] = scored_market['AI_Score'].rank(ascending=False, method='min')
        scored_market['Market_PR'] = scored_market['AI_Score'].rank(pct=True)
        stock_score_row = scored_market[scored_market['Ticker'] == latest['Ticker']].iloc[0]
        market_rank = int(stock_score_row['Market_Rank'])
        market_total = len(scored_market)
        market_pr = stock_score_row['Market_PR'] * 100
        hint = stock_score_row['Hint']
    else:
        ai_score = np.nan
        market_rank = None
        market_total = len(scored_market)
        market_pr = np.nan
        hint = build_hint(latest)

    # ==============================
    # 趨勢評分
    # ==============================
    trend_points = 0
    reasons = []

    close = latest['Close']
    ma5 = latest['MA5']
    ma20 = latest['MA20']
    ma60 = latest['MA60']

    if close >= ma5:
        trend_points += 1
        reasons.append("收盤站上 MA5，短線仍偏強")
    else:
        trend_points -= 1
        reasons.append("收盤跌破 MA5，短線動能轉弱")

    if close >= ma20:
        trend_points += 1
        reasons.append("收盤站上 MA20，中短線趨勢仍在")
    else:
        trend_points -= 1
        reasons.append("收盤跌破 MA20，中短線轉弱")

    if close >= ma60:
        trend_points += 1
        reasons.append("收盤站上 MA60，中期趨勢偏多")
    else:
        trend_points -= 1
        reasons.append("收盤跌破 MA60，中期趨勢偏弱")

    if ma5 >= ma20:
        trend_points += 1
        reasons.append("MA5 高於 MA20，短線均線排列偏多")
    else:
        trend_points -= 1
        reasons.append("MA5 低於 MA20，短線均線排列偏弱")

    if ma20 >= ma60:
        trend_points += 1
        reasons.append("MA20 高於 MA60，中期均線排列偏多")
    else:
        trend_points -= 1
        reasons.append("MA20 低於 MA60，中期均線排列偏弱")

    if latest['F_ROC_10'] > 0:
        trend_points += 1
        reasons.append(f"近10日上漲 {latest['F_ROC_10']:.2f}%，短線有動能")
    else:
        trend_points -= 1
        reasons.append(f"近10日下跌 {latest['F_ROC_10']:.2f}%，短線動能不足")

    if latest['Volume_Ratio'] >= 1.5 and latest['ROC_1'] > 0:
        trend_points += 1
        reasons.append(f"量增價漲，成交量約20日均量 {latest['Volume_Ratio']:.2f} 倍")
    elif latest['Volume_Ratio'] >= 1.5 and latest['ROC_1'] < 0:
        trend_points -= 1
        reasons.append(f"爆量下跌，成交量約20日均量 {latest['Volume_Ratio']:.2f} 倍，需注意賣壓")

    # ==============================
    # 趨勢結論
    # ==============================
    if trend_points >= 5:
        trend_view = "偏多續強"
        action_view = "可列入強勢觀察，但若已連續大漲，不建議無腦追高。"
    elif trend_points >= 2:
        trend_view = "偏多整理"
        action_view = "趨勢仍偏多，可觀察是否沿 MA5 / MA20 續強。"
    elif trend_points >= -1:
        trend_view = "中性觀望"
        action_view = "方向不夠明確，建議等站回短均線或突破前高再看。"
    elif trend_points >= -4:
        trend_view = "偏弱修正"
        action_view = "短線轉弱，若已持有要注意 MA20 / MA60 支撐。"
    else:
        trend_view = "弱勢空方"
        action_view = "趨勢明顯偏弱，不適合用動能策略追進。"

    # ==============================
    # 壓力 / 支撐參考
    # ==============================
    recent_20_high = stock_df['High'].tail(20).max()
    recent_20_low = stock_df['Low'].tail(20).min()

    distance_to_20_high = (close / recent_20_high - 1) * 100
    distance_to_20_low = (close / recent_20_low - 1) * 100

    print("\n" + "=" * 100)
    print(f" 📈 單股趨勢分析：{latest['ID']} {latest['Name']}｜資料日：{latest_date.date()}")
    print("=" * 100)

    print(f"收盤價             : {close:.2f}")
    print(f"MA5 / MA20 / MA60  : {ma5:.2f} / {ma20:.2f} / {ma60:.2f}")
    print(f"趨勢分數           : {trend_points}")
    print(f"趨勢判斷           : {trend_view}")
    print(f"操作觀點           : {action_view}")

    if not np.isnan(ai_score):
        print(f"AI_Score           : {ai_score:.2f}")
        print(f"全市場排名         : {market_rank} / {market_total}")
        print(f"全市場 PR          : {market_pr:.2f}%")
    else:
        print("AI_Score           : 未通過當日篩選條件，可能是成交量或 MA5 條件不足")

    print("-" * 100)
    print("📊 動能與風險數據")
    print(f"近1日漲跌幅        : {latest['ROC_1']:.2f}%")
    print(f"近3日漲跌幅        : {latest['ROC_3']:.2f}%")
    print(f"近5日漲跌幅        : {latest['ROC_5']:.2f}%")
    print(f"近10日漲跌幅       : {latest['F_ROC_10']:.2f}%")
    print(f"近20日漲跌幅       : {latest['ROC_20']:.2f}%")
    print(f"近30日漲跌幅       : {latest['ROC_30']:.2f}%")
    print(f"20日歷史波動率     : {latest['F_Hist_Vol']:.2f}%")
    print(f"布林通道寬度       : {latest['F_BB_Width']:.2f}%")
    print(f"距離 MA20          : {latest['F_P_to_MA20']:.2f}%")
    print(f"距離 MA60          : {latest['F_P_to_MA60']:.2f}%")
    print(f"成交量 / 20日均量  : {latest['Volume_Ratio']:.2f} 倍")
    print(f"20日均成交金額     : {latest['Avg_Value_20'] / 10000:.0f} 萬")
    print("-" * 100)
    print("🧭 支撐 / 壓力參考")
    print(f"近20日高點         : {recent_20_high:.2f}，目前距離高點 {distance_to_20_high:.2f}%")
    print(f"近20日低點         : {recent_20_low:.2f}，目前距離低點 +{distance_to_20_low:.2f}%")
    print(f"短線支撐參考       : MA5={ma5:.2f}，MA20={ma20:.2f}")
    print(f"中期支撐參考       : MA60={ma60:.2f}")
    print("-" * 100)
    print("⚠️ HINT")
    print(hint)
    print("-" * 100)
    print("🔎 判斷原因")
    for r in reasons:
        print(f" - {r}")
    print("=" * 100)

    result = pd.DataFrame([{
        'Date': latest_date.date(),
        'ID': latest['ID'],
        'Name': latest['Name'],
        'Close': close,
        'MA5': ma5,
        'MA20': ma20,
        'MA60': ma60,
        'Trend_Points': trend_points,
        'Trend_View': trend_view,
        'Action_View': action_view,
        'AI_Score': ai_score,
        'Market_Rank': market_rank,
        'Market_Total': market_total,
        'Market_PR_%': market_pr,
        'ROC_1': latest['ROC_1'],
        'ROC_3': latest['ROC_3'],
        'ROC_5': latest['ROC_5'],
        'ROC_10': latest['F_ROC_10'],
        'ROC_20': latest['ROC_20'],
        'ROC_30': latest['ROC_30'],
        'Hist_Vol': latest['F_Hist_Vol'],
        'BB_Width': latest['F_BB_Width'],
        'P_to_MA20': latest['F_P_to_MA20'],
        'P_to_MA60': latest['F_P_to_MA60'],
        'Volume_Ratio': latest['Volume_Ratio'],
        'Avg_Value_20': latest['Avg_Value_20'],
        'Recent_20_High': recent_20_high,
        'Recent_20_Low': recent_20_low,
        'Hint': hint,
        'Reasons': "；".join(reasons)
    }])

    return result
# ==========================================
# 日期工具
# ==========================================
def normalize_input_date(date_str):
    date_str = date_str.strip()

    for fmt in ["%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"]:
        try:
            return pd.to_datetime(datetime.strptime(date_str, fmt).date())
        except:
            pass

    raise ValueError("日期格式錯誤，請輸入例如 2026/04/13 或 2026-04-13")


def get_nearest_trading_date(df_all, target_date):
    available_dates = sorted(pd.to_datetime(df_all['Date'].dt.date).unique())
    available_dates = [pd.to_datetime(d) for d in available_dates]

    valid_dates = [d for d in available_dates if d <= target_date]

    if len(valid_dates) == 0:
        return None

    return valid_dates[-1]


def get_next_trading_date(df_all, signal_date):
    available_dates = sorted(pd.to_datetime(df_all['Date'].dt.date).unique())
    available_dates = [pd.to_datetime(d) for d in available_dates]

    future_dates = [d for d in available_dates if d > signal_date]

    if len(future_dates) == 0:
        return None

    return future_dates[0]


def calc_benchmark_result(
    df_all,
    signal_date,
    total_capital,
    forward_days_list=[7, 14, 21, 30],
    benchmark_ticker=BENCHMARK_TICKER,
    benchmark_name=BENCHMARK_NAME,
    expected_entry_date=None
):
    """
    用相同總資金全部買進 Benchmark，例如 0050正2 00631L.TW。
    進場日：signal_date 下一個交易日開盤
    出場日：進場後第 n 個交易日開盤
    """

    bench_df = df_all[df_all['Ticker'] == benchmark_ticker].copy()

    if bench_df.empty:
        print(f"⚠️ 找不到 Benchmark 資料：{benchmark_ticker}")
        print("👉 若快取建立時沒有 00631L.TW，請先模式 4 重新下載並更新快取。")
        return pd.DataFrame()

    bench_df = bench_df.sort_values('Date').reset_index(drop=True)

    idx_list = bench_df.index[bench_df['Date'].dt.date == signal_date.date()].tolist()

    if len(idx_list) == 0:
        print(f"⚠️ Benchmark 在 {signal_date.date()} 沒有資料，無法比較。")
        return pd.DataFrame()

    signal_idx = idx_list[0]
    entry_idx = signal_idx + 1

    if entry_idx >= len(bench_df):
        print("⚠️ Benchmark 沒有下一交易日資料，無法計算進場。")
        return pd.DataFrame()

    entry_date = bench_df.loc[entry_idx, 'Date']
    entry_open = bench_df.loc[entry_idx, 'Open']

    if expected_entry_date is not None and entry_date.date() != expected_entry_date.date():
        print(f"⚠️ Benchmark 在 {expected_entry_date.date()} 沒有可用開盤資料，無法公平比較。")
        return pd.DataFrame()

    result = {
        'Benchmark': benchmark_name,
        'Ticker': benchmark_ticker,
        'Signal_Date': signal_date.date(),
        'Entry_Date': entry_date.date(),
        'Entry_Open': entry_open,
        'Invest_Amount': total_capital,
    }

    for n in forward_days_list:
        exit_idx = entry_idx + n

        if exit_idx < len(bench_df):
            exit_date = bench_df.loc[exit_idx, 'Date']
            exit_open = bench_df.loc[exit_idx, 'Open']
            ret = exit_open / entry_open - 1

            gross_value = total_capital * (1 + ret)

            buy_fee = total_capital * COMMISSION
            sell_fee = gross_value * COMMISSION
            sell_tax = gross_value * SELL_TAX
            total_cost = buy_fee + sell_fee + sell_tax

            net_value = gross_value - total_cost
            net_profit = net_value - total_capital
            net_return = net_profit / total_capital * 100

            result[f'Day{n}_Exit_Date'] = exit_date.date()
            result[f'Day{n}_Exit_Open'] = exit_open
            result[f'Day{n}_Net_Value'] = net_value
            result[f'Day{n}_Net_Profit'] = net_profit
            result[f'Day{n}_Net_Return_%'] = net_return
        else:
            result[f'Day{n}_Exit_Date'] = None
            result[f'Day{n}_Exit_Open'] = np.nan
            result[f'Day{n}_Net_Value'] = np.nan
            result[f'Day{n}_Net_Profit'] = np.nan
            result[f'Day{n}_Net_Return_%'] = np.nan

    return pd.DataFrame([result])
# ==========================================
# 指定歷史日期推薦 + 驗證到 30 日
# ==========================================
def run_historical_signal_test(
    df_all,
    target_date_str,
    top_n=20,
    forward_days_list=[1, 3, 5, 7, 10, 14, 21, 30],
    capital_per_stock=100_000
):
    try:
        target_date = normalize_input_date(target_date_str)
    except Exception as e:
        print(f"❌ {e}")
        return pd.DataFrame()

    df_all = df_all.copy()
    df_all['Date'] = pd.to_datetime(df_all['Date'])

    signal_date = get_nearest_trading_date(df_all, target_date)

    if signal_date is None:
        print("❌ 找不到指定日期以前的交易資料。")
        return pd.DataFrame()

    if signal_date != target_date:
        print(f"⚠️ 你輸入的日期 {target_date.date()} 不是交易日，改用前一個交易日：{signal_date.date()}")

    market_entry_date = get_next_trading_date(df_all, signal_date)

    if market_entry_date is None:
        print("❌ 找不到下一個交易日資料，無法驗證隔日開盤進場。")
        return pd.DataFrame()

    day_df = df_all[df_all['Date'].dt.date == signal_date.date()].copy()

    if day_df.empty:
        print(f"❌ {signal_date.date()} 沒有資料。")
        return pd.DataFrame()

    scored = score_one_day(day_df)

    if scored.empty:
        print(f"❌ {signal_date.date()} 沒有符合條件的股票。")
        return pd.DataFrame()

    selected = scored.sort_values(by='AI_Score', ascending=False).head(top_n).copy()

    result_rows = []

    for _, row in selected.iterrows():
        ticker = row['Ticker']

        stock_hist = df_all[df_all['Ticker'] == ticker].copy()
        stock_hist = stock_hist.sort_values('Date').reset_index(drop=True)

        idx_list = stock_hist.index[stock_hist['Date'].dt.date == signal_date.date()].tolist()

        if len(idx_list) == 0:
            continue

        signal_idx = idx_list[0]
        entry_idx = signal_idx + 1

        if entry_idx >= len(stock_hist):
            continue

        entry_date = stock_hist.loc[entry_idx, 'Date']

        if entry_date.date() != market_entry_date.date():
            continue

        entry_open = stock_hist.loc[entry_idx, 'Open']

        # 這檔股票從進場日開始，最多可以驗證幾個交易日
        max_available_days = len(stock_hist) - entry_idx - 1

        result = {
            'Signal_Date': signal_date.date(),
            'Entry_Date': entry_date.date(),
            'ID': row['ID'],
            'Name': row['Name'],
            'Rank': None,
            'Signal_Close': row['Close'],
            'Signal_MA5': row['MA5'],
            'AI_Score': row['AI_Score'],
            'Entry_Open': entry_open,
            'Invest_Amount': capital_per_stock,
            'Max_Available_Days': max_available_days,
            'Avg_Value_20': row['Avg_Value_20'],
            'Volume_Ratio': row['Volume_Ratio'],
            'ROC_3': row['ROC_3'],
            'ROC_5': row['ROC_5'],
            'ROC_10': row['F_ROC_10'],
            'Consecutive_Limit_Up_Like': row['Consecutive_Limit_Up_Like'],
            'Hint': row['Hint'],
        }

        for n in forward_days_list:
            exit_idx = entry_idx + n

            if exit_idx < len(stock_hist):
                exit_date = stock_hist.loc[exit_idx, 'Date']
                exit_open = stock_hist.loc[exit_idx, 'Open']
                ret = exit_open / entry_open - 1

                gross_value = capital_per_stock * (1 + ret)

                # 買進手續費 + 賣出手續費 + 證交稅
                buy_fee = capital_per_stock * COMMISSION
                sell_fee = gross_value * COMMISSION
                sell_tax = gross_value * SELL_TAX
                total_cost = buy_fee + sell_fee + sell_tax

                net_value = gross_value - total_cost
                net_profit = net_value - capital_per_stock
                net_return = net_profit / capital_per_stock * 100

                result[f'Day{n}_Exit_Date'] = exit_date.date()
                result[f'Day{n}_Exit_Open'] = exit_open
                result[f'Day{n}_Return_%'] = ret * 100
                result[f'Day{n}_Gross_Value'] = gross_value
                result[f'Day{n}_Cost'] = total_cost
                result[f'Day{n}_Net_Value'] = net_value
                result[f'Day{n}_Net_Profit'] = net_profit
                result[f'Day{n}_Net_Return_%'] = net_return
                result[f'Day{n}_Is_Available'] = True
            else:
                result[f'Day{n}_Exit_Date'] = None
                result[f'Day{n}_Exit_Open'] = np.nan
                result[f'Day{n}_Return_%'] = np.nan
                result[f'Day{n}_Gross_Value'] = np.nan
                result[f'Day{n}_Cost'] = np.nan
                result[f'Day{n}_Net_Value'] = np.nan
                result[f'Day{n}_Net_Profit'] = np.nan
                result[f'Day{n}_Net_Return_%'] = np.nan
                result[f'Day{n}_Is_Available'] = False

        result_rows.append(result)

    result_df = pd.DataFrame(result_rows)

    if result_df.empty:
        print("❌ 指定日期後續資料不足，無法驗證。")
        return result_df

    result_df = result_df.sort_values('AI_Score', ascending=False).reset_index(drop=True)
    result_df['Rank'] = result_df.index + 1

    # 找出目前至少有一檔可驗證的天數
    available_forward_days = []
    for n in forward_days_list:
        col = f'Day{n}_Net_Value'
        if col in result_df.columns and result_df[col].notna().any():
            available_forward_days.append(n)

    print("\n" + "=" * 120)
    print(f" 🎯 歷史指定日期推薦名單：{signal_date.date()}")
    print(f" 📌 進場假設：下一交易日 {result_df['Entry_Date'].iloc[0]} 開盤買進")
    print(" 🛡️ 防偷看：AI_Score 只使用推薦日收盤以前資料，未來價格只用於驗證")
    print(f" 💰 投入假設：每檔投入 {capital_per_stock:,.0f} 元")
    print(f" 📅 可驗證天數：{available_forward_days if available_forward_days else '目前尚無足夠未來資料'}")
    print("=" * 120)

    show_cols = [
        'Rank',
        'ID',
        'Name',
        'AI_Score',
        'Entry_Open',
        'Invest_Amount',
        'Max_Available_Days',
    ]

    # 不要只顯示 Day30，全部指定天數都顯示
    for n in forward_days_list:
        show_cols.append(f'Day{n}_Net_Value')
        show_cols.append(f'Day{n}_Net_Return_%')

    show_cols.append('Hint')

    exist_cols = [c for c in show_cols if c in result_df.columns]

    formatters = {
        'AI_Score': '{:.2f}'.format,
        'Entry_Open': '{:.2f}'.format,
        'Invest_Amount': '{:,.0f}'.format,
        'Max_Available_Days': '{:.0f}'.format,
    }

    for n in forward_days_list:
        value_col = f'Day{n}_Net_Value'
        ret_col = f'Day{n}_Net_Return_%'

        if value_col in result_df.columns:
            formatters[value_col] = lambda x: "" if pd.isna(x) else f"{x:,.0f}"

        if ret_col in result_df.columns:
            formatters[ret_col] = lambda x: "" if pd.isna(x) else f"{x:.2f}"

    print(result_df[exist_cols].to_string(index=False, justify='center', formatters=formatters))

    print("=" * 120)

    print("\n📊 Top N 投入金額驗證：")
    print(f"   每檔投入：{capital_per_stock:,.0f} 元")
    print(f"   推薦檔數：{len(result_df)} 檔")
    print(f"   若全數買進，初始總投入：{capital_per_stock * len(result_df):,.0f} 元")
    benchmark_cache = {}
    compare_rows = []

    for n in forward_days_list:
        net_value_col = f'Day{n}_Net_Value'
        net_profit_col = f'Day{n}_Net_Profit'
        net_return_col = f'Day{n}_Net_Return_%'

        if net_value_col not in result_df.columns:
            continue

        valid_df = result_df[result_df[net_value_col].notna()].copy()

        if valid_df.empty:
            print(f"   持有 {n:<2} 個交易日：資料不足，尚無法驗證")
            continue

        valid_count = len(valid_df)
        total_invest = capital_per_stock * valid_count
        total_value = valid_df[net_value_col].sum()
        total_profit = valid_df[net_profit_col].sum()
        total_return = total_profit / total_invest * 100
        avg_value = valid_df[net_value_col].mean()
        win_rate = (valid_df[net_profit_col] > 0).mean() * 100

        # Benchmark：用相同總資金全部買 0050正2
        bench_value = np.nan
        bench_profit = np.nan
        bench_return = np.nan
        diff_value = np.nan
        diff_return = np.nan
        winner = "N/A"

        if total_invest not in benchmark_cache:
            benchmark_cache[total_invest] = calc_benchmark_result(
                df_all=df_all,
                signal_date=signal_date,
                total_capital=total_invest,
                forward_days_list=forward_days_list,
                benchmark_ticker=BENCHMARK_TICKER,
                benchmark_name=BENCHMARK_NAME,
                expected_entry_date=market_entry_date
            )

        benchmark_df = benchmark_cache[total_invest]

        if benchmark_df is not None and not benchmark_df.empty:
            bench_value_col = f'Day{n}_Net_Value'
            bench_profit_col = f'Day{n}_Net_Profit'
            bench_return_col = f'Day{n}_Net_Return_%'

            if bench_value_col in benchmark_df.columns:
                bench_value = benchmark_df.iloc[0][bench_value_col]
                bench_profit = benchmark_df.iloc[0][bench_profit_col]
                bench_return = benchmark_df.iloc[0][bench_return_col]

                if not pd.isna(bench_value):
                    diff_value = total_value - bench_value
                    diff_return = total_return - bench_return
                    winner = "策略勝" if diff_value > 0 else "0050正2勝"

        print(
            f"   持有 {n:<2} 個交易日："
            f"策略總資產 {total_value:>10,.0f} 元｜"
            f"策略報酬 {total_return:>7.2f}%｜"
            f"{BENCHMARK_NAME}總資產 {bench_value:>10,.0f} 元｜"
            f"{BENCHMARK_NAME}報酬 {bench_return:>7.2f}%｜"
            f"差額 {diff_value:>10,.0f} 元｜"
            f"差距 {diff_return:>7.2f}%｜"
            f"{winner}"
        )

        compare_rows.append({
            'Days': n,
            'Strategy_Valid_Count': valid_count,
            'Strategy_Invest': total_invest,
            'Strategy_Net_Value': total_value,
            'Strategy_Net_Profit': total_profit,
            'Strategy_Net_Return_%': total_return,
            'Strategy_Win_Rate_%': win_rate,
            'Benchmark': BENCHMARK_NAME,
            'Benchmark_Ticker': BENCHMARK_TICKER,
            'Benchmark_Net_Value': bench_value,
            'Benchmark_Net_Profit': bench_profit,
            'Benchmark_Net_Return_%': bench_return,
            'Diff_Value': diff_value,
            'Diff_Return_%': diff_return,
            'Winner': winner
        })

    print("\n✅ 歷史日期驗證完成。")

    return result_df


# ==========================================
# 全期間回測
# ==========================================
'''''
def run_backtest(df_all, top_n=20):
    print(f"🧪 開始全期間回測：每日買進 Top {top_n}，T+1 開盤進場...")

    df_all = df_all.copy()
    df_all = df_all.sort_values(['Date', 'Ticker'])

    dates = sorted(df_all['Date'].unique())

    equity = 1.0
    prev_weights = {}
    records = []
    trade_records = []

    for d in dates:
        day_df = df_all[df_all['Date'] == d].copy()
        day_df = day_df.dropna(subset=['Next_Open', 'Next2_Open', 'Next_OpenToOpen_Return'])

        if day_df.empty:
            continue

        scored = score_one_day(day_df)

        if scored.empty:
            continue

        selected = scored.sort_values(by='AI_Score', ascending=False).head(top_n).copy()

        if selected.empty:
            continue

        selected_count = len(selected)
        target_weight = 1.0 / selected_count

        new_weights = {
            row['Ticker']: target_weight
            for _, row in selected.iterrows()
        }

        all_pos = set(prev_weights.keys()) | set(new_weights.keys())

        buy_turnover = 0.0
        sell_turnover = 0.0

        for t in all_pos:
            old_w = prev_weights.get(t, 0.0)
            new_w = new_weights.get(t, 0.0)

            diff = new_w - old_w

            if diff > 0:
                buy_turnover += diff
            elif diff < 0:
                sell_turnover += abs(diff)

        cost = buy_turnover * COMMISSION + sell_turnover * (COMMISSION + SELL_TAX)

        equity_before_cost = equity
        equity *= (1 - cost)

        period_return = 0.0
        individual_returns = {}

        for _, row in selected.iterrows():
            ticker = row['Ticker']
            r = row['Next_OpenToOpen_Return']
            individual_returns[ticker] = r
            period_return += target_weight * r

            trade_records.append({
                'Signal_Date': row['Date'],
                'Entry_Date': row['Entry_Date'],
                'Exit_Date': row['Exit_Date'],
                'Ticker': row['Ticker'],
                'ID': row['ID'],
                'Name': row['Name'],
                'AI_Score': row['AI_Score'],
                'Signal_Close': row['Close'],
                'Entry_Open': row['Next_Open'],
                'Exit_Open': row['Next2_Open'],
                'Return': r,
                'Hint': row['Hint']
            })

        equity_before_return = equity
        equity *= (1 + period_return)

        post_weights = {}

        if 1 + period_return != 0:
            for t, w in new_weights.items():
                r = individual_returns.get(t, 0.0)
                post_weights[t] = w * (1 + r) / (1 + period_return)

        prev_weights = post_weights

        records.append({
            'Signal_Date': d,
            'Entry_Date': selected['Entry_Date'].iloc[0],
            'Exit_Date': selected['Exit_Date'].iloc[0],
            'Hold_Count': selected_count,
            'Buy_Turnover': buy_turnover,
            'Sell_Turnover': sell_turnover,
            'Cost': cost,
            'Period_Return': period_return,
            'Equity_Before_Cost': equity_before_cost,
            'Equity_Before_Return': equity_before_return,
            'Equity': equity,
            'Top1_ID': selected.iloc[0]['ID'],
            'Top1_Name': selected.iloc[0]['Name'],
            'Top1_Score': selected.iloc[0]['AI_Score'],
            'Top1_Hint': selected.iloc[0]['Hint']
        })

    result_df = pd.DataFrame(records)
    trade_df = pd.DataFrame(trade_records)

    if result_df.empty:
        print("❌ 回測結果為空，可能資料不足。")
        return result_df, trade_df

    result_df['Peak'] = result_df['Equity'].cummax()
    result_df['Drawdown'] = result_df['Equity'] / result_df['Peak'] - 1

    total_return = result_df['Equity'].iloc[-1] - 1
    max_drawdown = result_df['Drawdown'].min()

    daily_ret = result_df['Period_Return']
    win_rate = (daily_ret > 0).mean()

    if daily_ret.std() != 0:
        sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    else:
        sharpe = np.nan

    days = len(result_df)
    annual_return = result_df['Equity'].iloc[-1] ** (252 / days) - 1 if days > 0 else np.nan

    print("\n" + "=" * 80)
    print(" 🧪 回測結果摘要")
    print("=" * 80)
    print(f"回測天數             : {days}")
    print(f"Top N                : {top_n}")
    print(f"期末資金倍率         : {result_df['Equity'].iloc[-1]:.4f}")
    print(f"總報酬率             : {total_return * 100:.2f}%")
    print(f"年化報酬率           : {annual_return * 100:.2f}%")
    print(f"最大回撤             : {max_drawdown * 100:.2f}%")
    print(f"每日勝率             : {win_rate * 100:.2f}%")
    print(f"Sharpe Ratio 粗估    : {sharpe:.2f}")
    print("=" * 80)

    return result_df, trade_df

'''
# ==========================================
# 儲存結果
# ==========================================
def save_csv(df, prefix):
    if not SAVE_CSV_OUTPUT:
        print("ℹ️ CSV 輸出已關閉，結果只顯示在畫面上。")
        return

    if df is None or df.empty:
        return

    try:
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(desktop_path, f"{prefix}_{timestamp}.csv")
        df.to_csv(file_path, index=False, encoding='utf-8-sig')
        print(f"📁 已儲存：{file_path}")

    except Exception as e:
        print(f"⚠️ 儲存失敗：{e}")


# ==========================================
# 選單循環
# ==========================================
def menu_loop(df_all, stock_dict):
    while True:
        print("\n" + "=" * 80)
        print("請選擇功能：")
        print("1. 最新 Top20 掃描")
        #print("2. 全期間回測")
        print("2. 指定歷史日期推薦 + 1/3/5/10/20/30 日驗證")
        print("3. 顯示目前資料狀態")
        print("4. 重新下載並更新快取")
        print("5. 單股趨勢分析 / 預測")
        print("0. 離開")
        print("=" * 80)

        mode = input("請輸入模式 0/1/2/3/4/5/6：").strip()

        if mode == "0":
            print("✅ 已離開程式。")
            break

        elif mode == "1":
            top20 = run_today_scan(df_all)
            save_csv(top20, "MANUS_Top20")
        
       #elif mode == "2":
            #bt_result, bt_trades = run_backtest(df_all, top_n=TOP_N)
            #save_csv(bt_result, "MANUS_Backtest_Result")
            #save_csv(bt_trades, "MANUS_Backtest_Trades")
        
        elif mode == "2":
            target_date = input("請輸入你想回放的日期，例如 2026/04/13：").strip()
            historical_result = run_historical_signal_test(
                df_all,
                target_date_str=target_date,
                top_n=TOP_N,
                forward_days_list=[1, 3, 5, 7, 10, 14, 21, 30],
                capital_per_stock=CAPITAL_PER_STOCK
            )
            save_csv(historical_result, "MANUS_Historical_Test")

        elif mode == "3":
            print("\n📊 目前資料狀態")
            print(f"資料筆數        : {len(df_all)}")
            print(f"股票數量        : {df_all['Ticker'].nunique()}")
            print(f"最早交易日      : {df_all['Date'].min().date()}")
            print(f"最新交易日      : {df_all['Date'].max().date()}")
            print(f"快取路徑        : {CACHE_FILE}")
            print(f"成交金額門檻    : 20日均成交金額 >= {MIN_AVG_VALUE_20 / 10000:.0f} 萬")
            print(f"訊號日金額門檻  : 當日成交金額 >= {MIN_TODAY_VALUE / 10000:.0f} 萬")

        elif mode == "4":
            print("🔄 重新下載資料並更新快取...")
            df_new, stock_new = prepare_data(force_refresh=True)

            if df_new is not None and not df_new.empty:
                df_all = df_new
                stock_dict = stock_new
                print("✅ 資料已更新，回到選單。")
            else:
                print("❌ 更新失敗，保留原資料。")
        elif mode == "5":
            code = input("請輸入股票代號，例如 2330 或 6187：").strip()
            single_result = analyze_single_stock(df_all, code)
            save_csv(single_result, "MANUS_Single_Stock_Analysis")
        else:
            print("❌ 輸入錯誤，請重新選擇。")


# ==========================================
# 主程式
# ==========================================
def main():
    df_all, stock_dict = prepare_data(force_refresh=False)

    if df_all is None or df_all.empty:
        print("❌ 沒有資料可以執行。")
        input("👉 請按 Enter 鍵關閉視窗...")
        return

    print(f"✅ 特徵資料筆數：{len(df_all)}")
    print(f"✅ 股票數量：{df_all['Ticker'].nunique()}")
    print(f"✅ 資料期間：{df_all['Date'].min().date()} ~ {df_all['Date'].max().date()}")

    menu_loop(df_all, stock_dict)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n" + "!" * 80)
        print("❌ 程式執行中發生錯誤：")
        traceback.print_exc()
        print("!" * 80)
        input("👉 請按 Enter 鍵關閉視窗...")
