# stock_test

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

部署後先直接開：

```text
https://你的服務網址.onrender.com/api/status
```

正常會看到 JSON，例如 `{"ok": true, ...}`。如果看到 HTML 或 Render 錯誤頁，代表目前打到的不是後端 API，或後端啟動失敗；請回 Render Logs 看 Python 錯誤。
