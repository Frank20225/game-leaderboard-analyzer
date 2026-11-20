# Game Leaderboard Analyzer

Windows 本機執行的遊戲排行榜影片分析工具。輸入 OBS 錄製的 MP4 影片，自動偵測捲動與清晰影格、擷取最多 200 隊排行榜資料（支援中/英/泰戰隊名稱與第 1～3 名徽章）、辨識每隊 8 個職業圖示，並產出完整的 7 工作表 Excel 報告與可直接分享的靜態網頁 / PNG 統計圖卡 / 文字戰報。

## 快速開始

1. 首次使用請雙擊 **`setup.bat`**（建立 `.venv` 並安裝 `requirements.txt`）。
2. 之後雙擊 **`run.bat`**，自動開啟本機網頁操作介面（`http://127.0.0.1:8765`）。
3. 依照網頁上方 6 步驟完成選片 → ROI 確認 → OCR 擷取 → 職業圖示命名/分群 → 人工校對 → 匯出與分享。

## 分享分析結果（GitHub Pages）

1. 在網頁介面點擊「**發佈至 `docs/`（GitHub Pages）**」，會自動更新 `docs/index.html` 與 `docs/reports/<報表名稱>/`。
2. 將專案推送至 GitHub 後，於倉庫 **Settings → Pages → Build and deployment** 選擇 `Deploy from a branch`，分支選 `main`、資料夾選 `/docs` 並儲存。
3. 稍候約 1 分鐘即可透過 `https://<你的帳號>.github.io/<repo名稱>/` 公開分享歷次互動戰報。

## 注意事項

- 原始影片皆以**唯讀模式**讀取，不會被修改或移動。
- 所有分析中繼檔與輸出皆保存於 `outputs/`（已列入 `.gitignore`）。
- 確認過的職業圖示資料庫保存於 `data/icon_db/`，可隨專案版本控制並供未來影片自動複用。
