# stock_test

## Streamlit Community Cloud 部署

這個版本建議用 Streamlit Community Cloud 部署，主程式是：

```text
streamlit_app.py
```

部署流程：

1. 把專案 push 到 GitHub。
2. 到 Streamlit Community Cloud 建立 app。
3. Repository 選 `bnmddd789/stock_test`。
4. Branch 選 `main`。
5. Main file path 填 `streamlit_app.py`。
6. Deploy。

第一次按「掃描最新 Top20」或「載入資料」時，會下載市場資料並建立快取，可能需要幾分鐘。之後同一個 app session 會使用 Streamlit cache，不會每次重抓。

建議 Streamlit Secrets 或環境變數可保留預設值：

```text
BATCH_SIZE=10
YF_THREADS=0
```

## Render 部署檢查

這個專案要部署成 Render **Web Service**，不要部署成 Static Site。前端會呼叫同網域的 `/api/status`、`/api/scan` 等 API；如果部署成 Static Site，這些 API 路徑會回傳 HTML，因此瀏覽器會出現：

```text
Unexpected token '<', "<!DOCTYPE "... is not valid JSON
```

建議設定：

- Service type: `Web Service`
- Runtime: `Python`
- Build command: `pip install -r requirements.txt`
- Start command: `python -u stock_web.py`
- Health check path: `/api/status`
- Environment:
  - `BATCH_SIZE=10`
  - `YF_THREADS=0`
  - `FETCH_ONLINE_FUNDAMENTALS=0`

部署後先直接開：

```text
https://你的服務網址.onrender.com/api/status
```

正常會看到 JSON，例如 `{"ok": true, ...}`。如果看到 HTML 或 Render 錯誤頁，代表目前打到的不是後端 API，或後端啟動失敗；請回 Render Logs 看 Python 錯誤。

第一次按「掃描最新」時，如果 Render 還沒有快取資料，後端會先回 JSON 並在背景下載資料。等幾分鐘後再按一次掃描即可。這樣可以避免 Render 在單一 HTTP 請求中等待 yfinance 下載全市場資料而回 `502 Bad Gateway`。
