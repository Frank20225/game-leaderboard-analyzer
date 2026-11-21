# 🏆 Game Leaderboard Analyzer

> ### 🌐 線上互動戰報（GitHub Pages 點擊即看）
> - **歷次排位賽戰報總覽首頁**：**https://frank20225.github.io/game-leaderboard-analyzer/**
> - **最新 200 隊完整分析（1120 女武神環境分析報告）**：**https://frank20225.github.io/game-leaderboard-analyzer/reports/2026-11-20-valkyrie-200/index.html**
>   *(內建：200 隊泰/中/英快篩秒查對手、點擊戰隊展開 BO5 5v5/1v1/3v3/2v2 拆陣推演、Meta 四象限、0/1/2 隻雙開效益圖、協同互斥矩陣，以及「我方 8 人名單健檢模擬器」！)*

---

Windows 本機執行的遊戲排行榜影片分析與戰隊排陣情報工具。輸入 OBS 錄製的 MP4 影片，自動偵測捲動與清晰影格、擷取最多 200 隊排行榜資料（支援中/英/泰戰隊名稱與第 1～3 名徽章）、辨識每隊 8 個職業圖示，並產出完整的 7 工作表 Excel 報告與可直接分享的靜態網頁 / PNG 統計圖卡 / 文字戰報 / 跨期趨勢分析。

## 快速開始

1. 首次使用請雙擊 **`setup.bat`**（建立 `.venv` 並安裝 `requirements.txt`）。
2. 之後雙擊 **`run.bat`**，自動開啟本機網頁操作介面（`http://127.0.0.1:8765`）。
3. 依照網頁上方步驟完成：
   - **1. 選擇影片 & ROI** → **2. OCR 擷取與稽核** → **3. 職業圖示確認** → **4. 人工校對修正** → **5. 匯出與分享包** → **📈 6. 多期趨勢對比**。
   - **實戰秒查對手**：比賽配對時按 `Win + Shift + S` 擷取對手隊名，切到本機網頁直接按 **`Ctrl + V`** 即可透過 OCR＋原圖字形比對秒查對手 8 職業陣容；或直接在上方 **GitHub Pages 線上戰報**使用「🇹🇭 泰文隊 / 🇹🇼 中文隊 / 🔤 英數隊 ＋ 字長快篩」3 秒鎖定對手！

## 深度學習筆記（Computer Vision × OCR × 無監督分群 × 賽事資料科學）

- [`learning/01_stage1_video_and_roi.md`](./learning/01_stage1_video_and_roi.md) — 影片讀取、HSV 色彩空間、時間變異排除個人列、相位相關捲動追蹤與時間中位數去游標
- [`learning/02_stage2_ocr_and_dedup.md`](./learning/02_stage2_ocr_and_dedup.md) — 1～3 名徽章分類、數字墨跡緊密裁切前處理、中/英/泰路由、跨影格投票與業務防呆稽核
- [`learning/03_stage3_icon_clustering.md`](./learning/03_stage3_icon_clustering.md) — 空位偵測、圓心對齊、多線索特徵向量、餘弦/NCC 相似度矩陣與層次式分群
- [`learning/04_stage4_analytics_and_stats.md`](./learning/04_stage4_analytics_and_stats.md) — 賽制驅動分析、四象限、0/1/2 雙開邊際效益、Synergy Lift 協同互斥矩陣與多期趨勢追蹤

## 注意事項

- 原始影片皆以**唯讀模式**讀取，不會被修改或移動。
- 所有分析中繼檔與輸出皆保存於 `outputs/`（已列入 `.gitignore`）。
- 確認過的職業圖示資料庫保存於 `data/icon_db/`，隨專案版本控制並供未來影片自動複用。
