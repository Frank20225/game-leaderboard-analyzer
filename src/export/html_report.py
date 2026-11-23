"""Zero-dependency single-file interactive HTML report v2 (Tournament Roster Edition)."""

from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _encode_png_b64(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _compute_name_crop_fingerprint(crop_path: Path) -> dict[str, Any] | None:
    """Compute a compact 48x12 text silhouette vector + aspect ratio matching browser Canvas logic."""
    if not crop_path.is_file():
        return None
    try:
        arr = np.fromfile(str(crop_path), dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None or bgr.size == 0:
            return None
        # Convert BGR to standard luminance matching JS: 0.299*R + 0.587*G + 0.114*B
        b, g, r = bgr[:, :, 0].astype(np.float32), bgr[:, :, 1].astype(np.float32), bgr[:, :, 2].astype(np.float32)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        l_min, l_max = float(np.min(lum)), float(np.max(lum))
        norm = (lum - l_min) * 255.0 / max(1.0, l_max - l_min)
        ys, xs = np.where(norm > 145.0)
        if len(xs) >= 10 and len(ys) >= 5:
            x1 = max(0, int(np.percentile(xs, 2)) - 1)
            x2 = min(norm.shape[1], int(np.percentile(xs, 98)) + 2)
            y1 = max(0, int(np.percentile(ys, 4)) - 1)
            y2 = min(norm.shape[0], int(np.percentile(ys, 96)) + 2)
            roi = norm[y1:y2, x1:x2] if (x2 > x1 + 4 and y2 > y1 + 3) else norm
        else:
            roi = norm
        h_roi, w_roi = roi.shape[:2]
        aspect = round(float(w_roi) / max(1.0, float(h_roi)), 2)
        small = cv2.resize(roi.astype(np.float32), (48, 12), interpolation=cv2.INTER_AREA)
        vec = small.ravel()
        vec -= float(np.mean(vec))
        denom = float(np.linalg.norm(vec))
        if denom < 1e-6:
            return None
        q_vec = [int(round(float(v / denom) * 1000)) for v in vec]
        return {"a": aspect, "v": q_vec}
    except Exception:
        return None


def generate_html_report(
    analytics: dict[str, Any],
    icon_paths_by_name: dict[str, str],
    output_path: str | Path,
    cards_dir: str | Path | None = None,
    crops_dir: str | Path | None = None,
) -> Path:
    """Build a self-contained single-file interactive HTML report for tournament roster analysis."""
    icons_b64 = {
        name: _encode_png_b64(p) for name, p in icon_paths_by_name.items() if p and Path(p).is_file()
    }
    embedded_cards: dict[str, str] = {}
    if cards_dir is not None:
        cdir = Path(cards_dir)
        for key, fname in [
            ("meta_quadrant", "01_meta_quadrant.png"),
            ("copy_impact", "02_copy_count_impact.png"),
            ("tier_heatmap", "03_tier_heatmap_and_doubles.png"),
            ("synergy_matrix", "04_synergy_matrix.png"),
        ]:
            fp = cdir / fname
            if fp.is_file():
                embedded_cards[key] = _encode_png_b64(fp)

    name_fingerprints: dict[int, dict[str, Any]] = {}
    if crops_dir is not None:
        cr_dir = Path(crops_dir)
        for team in analytics.get("raw_data", []):
            rk = int(team["rank"])
            fp = _compute_name_crop_fingerprint(cr_dir / f"rank_{rk:03d}_name.png")
            if fp is not None:
                name_fingerprints[rk] = fp

    embedded_payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "analytics": {k: v for k, v in analytics.items() if k != "recognition_errors"},
        "icons": icons_b64,
        "cards": embedded_cards,
        "name_fps": name_fingerprints,
    }
    json_blob = json.dumps(embedded_payload, ensure_ascii=False).replace("</", "<\\/")
    safe_title = html.escape(analytics.get("report_title", "排位賽戰隊排陣分析報告"))

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title}</title>
<style>
  :root {{
    --bg: #0b1120; --card: #131c31; --card2: #1c2842; --text: #f8fafc;
    --muted: #94a3b8; --accent: #38bdf8; --accent2: #f59e0b; --green: #4ade80; --red: #f87171; --border: #273552;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "Microsoft JhengHei", "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
  .wrap {{ max-width: 1240px; margin: 0 auto; padding: 24px 16px 60px; }}
  header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 12px; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; }}
  h1 {{ margin: 0; font-size: 1.6rem; }}
  .sub {{ color: var(--muted); font-size: 0.9rem; margin-top: 4px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }}
  .kpi .lbl {{ color: var(--muted); font-size: 0.82rem; }}
  .kpi .val {{ font-size: 1.35rem; font-weight: 700; margin-top: 4px; color: var(--accent); }}
  .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }}
  .tab {{ background: var(--card); color: var(--muted); border: 1px solid var(--border); padding: 9px 15px; border-radius: 999px; cursor: pointer; font-weight: 600; font-size: 0.9rem; }}
  .tab.active {{ background: var(--accent); color: #0b1120; border-color: var(--accent); }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 18px; }}
  .card h2 {{ margin: 0 0 10px; font-size: 1.12rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }}
  .ico {{ width: 26px; height: 26px; border-radius: 50%; object-fit: cover; flex-shrink: 0; border: 1px solid rgba(255,255,255,.15); }}
  .lbl-flex {{ display: inline-flex; align-items: center; gap: 7px; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.87rem; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
  th {{ background: #0f172a; color: #cbd5e1; position: sticky; top: 0; z-index: 2; }}
  tr.team-row {{ cursor: pointer; transition: background 0.12s; }}
  tr.team-row:hover td {{ background: rgba(56,189,248,.09); }}
  .table-wrap {{ overflow-x: auto; max-height: 680px; }}
  .pill {{ display: inline-flex; align-items: center; gap: 4px; background: var(--card2); padding: 3px 8px; border-radius: 999px; font-size: 0.8rem; margin: 2px; }}
  .pill.dp {{ border: 1px solid rgba(245,158,11,.55); background: rgba(245,158,11,.14); }}
  .q-tag {{ padding: 2px 8px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; display: inline-block; }}
  .q-t0 {{ background: rgba(56,189,248,.2); color: #7dd3fc; }}
  .q-dark {{ background: rgba(74,222,128,.2); color: #86efac; }}
  .q-std {{ background: rgba(245,158,11,.2); color: #fde68a; }}
  .q-low {{ background: rgba(148,163,184,.2); color: #cbd5e1; }}
  .pos {{ color: var(--green); font-weight: 700; }}
  .neg {{ color: var(--red); font-weight: 700; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; align-items: center; }}
  .filter-bar {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; align-items: center; }}
  .chip-btn {{ background: #0f172a; color: var(--muted); border: 1px solid var(--border); border-radius: 999px; padding: 5px 12px; font-size: 0.82rem; cursor: pointer; font-weight: 600; }}
  .chip-btn.active {{ background: rgba(56,189,248,.2); color: #7dd3fc; border-color: var(--accent); }}
  input, select {{ background: #0b1120; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; font-size: 0.9rem; }}
  .quad-wrap {{ position: relative; width: 100%; overflow-x: auto; }}
  svg.quad {{ width: 100%; max-width: 960px; height: auto; display: block; margin: 0 auto; background: #0f172a; border-radius: 12px; border: 1px solid var(--border); }}
  .heat-cell {{ text-align: center; font-weight: 700; border-radius: 4px; }}
  .scout-box {{ background: #0f172a; border: 1px solid var(--accent); border-radius: 12px; padding: 14px 16px; margin: 4px 0; }}
  .scout-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; margin-top: 10px; }}
  .bo5-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }}
  .bo5-card h4 {{ margin: 0 0 6px; font-size: 0.88rem; color: var(--accent); }}
  .builder-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); gap: 10px; margin: 14px 0; }}
  .slot-box {{ background: #0f172a; border: 1px solid var(--border); border-radius: 10px; padding: 10px; text-align: center; }}
  .slot-box select {{ width: 100%; margin-top: 6px; }}
  .preset-btn {{ background: var(--card2); color: var(--text); border: 1px solid var(--accent); border-radius: 8px; padding: 7px 13px; cursor: pointer; font-weight: 600; font-size: 0.84rem; }}
  .preset-btn:hover {{ background: rgba(56,189,248,.2); }}
  .zoomable-img {{ cursor: zoom-in; transition: transform 0.15s, box-shadow 0.15s; border-radius: 12px; border: 1px solid var(--border); }}
  .zoomable-img:hover {{ box-shadow: 0 0 0 2px var(--accent); }}
  .cards-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr)); gap: 16px; }}
  .zoom-modal {{ position: fixed; inset: 0; background: rgba(5, 10, 20, 0.92); z-index: 9999; display: none; flex-direction: column; user-select: none; }}
  .zoom-modal.open {{ display: flex; }}
  .zoom-toolbar {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 18px; background: #0f172a; border-bottom: 1px solid var(--border); flex-wrap: wrap; gap: 10px; }}
  .zoom-stage {{ flex: 1; overflow: hidden; position: relative; display: flex; align-items: center; justify-content: center; cursor: grab; }}
  .zoom-stage.dragging {{ cursor: grabbing; }}
  .zoom-stage img {{ max-width: 94vw; max-height: 86vh; transform-origin: center center; transition: transform 0.05s linear; pointer-events: none; border-radius: 8px; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.82rem; margin-top: 28px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>{safe_title}</h1>
      <div class="sub" id="reportSub"></div>
    </div>
    <div class="sub" id="genTime"></div>
  </header>

  <section class="kpis" id="kpiRow"></section>

  <nav class="tabs">
    <button class="tab active" data-tab="raw">🔍 1. 排行榜查詢</button>
    <button class="tab" data-tab="quad">📊 2. 職業出場＆雙職業</button>
    <button class="tab" data-tab="synergy">🧩 3. 陣容搭配＆流派</button>
    <button class="tab" data-tab="builder">🧪 4. 我方陣容健檢</button>
  </nav>

  <section id="tab-raw" class="panel active">
    <div class="card">
      <h2>完整排行榜資料查詢 ＆ 實戰對手秒查（支援線上 Ctrl+V 截圖 OCR／免打泰文）</h2>
      <div class="scout-box" style="margin-bottom:14px;background:#0f172a;border-color:rgba(56,189,248,.55)">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
          <div>
            <b>📷 GitHub Pages 線上截圖秒查對手（免開本機伺服器）</b>
            <div class="sub" style="font-size:0.84rem;margin-top:2px">
              遊戲中按 <code>Win + Shift + S</code> 框選對手隊名後，直接在此網頁按 <b><code>Ctrl + V</code></b> 貼上！系統會以<b>「0.01秒原圖字形指紋」＋「免費多語系 OCR API (中/英/泰)」</b>雙重鎖定對手並展開對局提醒卡。
            </div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
            <select id="ocrModeSelect" style="font-size:0.82rem;padding:6px 10px">
              <option value="tesseract">⚡ 字形指紋 ＋ Tesseract.js 免費多語系 OCR (免Key)</option>
              <option value="ocrspace">☁️ 字形指紋 ＋ OCR.space 免費雲端 API</option>
              <option value="visual">👁️ 極速純原圖字形指紋比對 (0流量/泰文最穩)</option>
            </select>
            <input id="ocrSpaceKeyInput" type="text" placeholder="選填 OCR.space 免費 Key" style="display:none;width:175px;font-size:0.82rem;padding:6px 9px">
            <label class="preset-btn" style="display:inline-flex;align-items:center;gap:4px">
              📂 選擇或貼上截圖
              <input type="file" id="onlineScoutFile" accept="image/*" style="display:none">
            </label>
          </div>
        </div>
        <div id="onlineScoutResult" style="display:none;margin-top:12px;padding-top:10px;border-top:1px solid var(--border)"></div>
      </div>
      <div class="sub" style="background:#0f172a;border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:12px;line-height:1.6">
        🎯 <b>不截圖也能 3 秒查泰文對手：</b>
        先點下方<b>「語系秒篩」</b>（例如點 <code>🇹🇭 泰文隊</code>）＋<b>「外觀特徵」</b>（含數字 / 字數長短），免打字即可縮小範圍！<b>點擊表格任一戰隊列</b>可展開<b>【🎯 對手陣容特徵 ＆ 實戰對局提醒卡】</b>。
      </div>
      <div class="filter-bar" id="scriptFilterBar">
        <span class="sub" style="margin-right:4px">語系秒篩：</span>
        <button class="chip-btn active" data-script="all">🌐 全部語系</button>
        <button class="chip-btn" data-script="th">🇹🇭 泰文隊</button>
        <button class="chip-btn" data-script="zh">🇹🇼 中文隊</button>
        <button class="chip-btn" data-script="en">🔤 純英數隊</button>
      </div>
      <div class="filter-bar" id="featFilterBar">
        <span class="sub" style="margin-right:4px">外觀特徵：</span>
        <button class="chip-btn active" data-feat="all">📏 全部長度</button>
        <button class="chip-btn" data-feat="num">🔢 含數字 (0-9)</button>
        <button class="chip-btn" data-feat="sym">✨ 含特殊符號/點</button>
        <button class="chip-btn" data-feat="short">短名 (≤5字)</button>
        <button class="chip-btn" data-feat="mid">中名 (6~9字)</button>
        <button class="chip-btn" data-feat="long">長名 (≥10字)</button>
      </div>
      <div class="controls">
        <input id="searchInput" type="search" placeholder="輸入部分英數/中文字、跳字縮寫或排名 (如 #12, enc, 88)..." style="min-width:300px">
        <select id="occFilter"><option value="">篩選特定職業（全部）</option></select>
        <select id="dpFilter">
          <option value="">篩選雙職業組數（全部）</option>
          <option value="0">0 組雙職業（8異職）</option>
          <option value="1">1 組雙職業</option>
          <option value="2">2 組雙職業</option>
          <option value="3">3+ 組雙職業</option>
        </select>
        <span class="sub" id="rawCount"></span>
      </div>
      <div class="table-wrap"><table id="rawTable"></table></div>
    </div>
  </section>

  <section id="tab-quad" class="panel">
    <div class="card">
      <h2>14 職業環境總表 ＆ Meta 四象限戰略圖 <span class="sub" style="font-size:0.82rem">💡 點擊任何圖卡可全螢幕放大與滾輪縮放</span></h2>
      <div id="quadCardWrap" style="margin-bottom:14px"></div>
      <div class="sub" style="background:#0f172a;border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:12px;line-height:1.65">
        💡 <b>指標白話說明：</b><br>
        • <b>前段班偏好倍率</b>＝前段班（Top 50 / Top 10）出場率 ÷ 全場出場率。<b>&gt; 1.0x</b> 代表前段班強隊更愛帶；<b>≈ 1.0x</b> 代表各分段普及度相近；<b>&lt; 1.0x</b> 代表偏中後段帶得多。<br>
        • <b>名次相關性（-1 ～ +1）</b>＝衡量「帶越多隻該職業，名次是否越靠前」。<b>負值（綠色，如 -0.21 帶越多名次越前）代表強勢職業</b>；接近 0 代表無明顯關聯；<b>正值（紅色）代表偏中後段</b>。
      </div>
      <div class="table-wrap"><table id="occTable"></table></div>
      <details style="margin-top:12px">
        <summary style="cursor:pointer;color:var(--accent);font-weight:600">🔍 展開互動式 SVG 向量版四象限圖</summary>
        <div class="quad-wrap" id="quadSvgBox" style="margin-top:10px"></div>
      </details>
    </div>

    <div class="card">
      <h2>0 隻（不帶）vs 1 隻（單職業）vs 2 隻（雙職業）平均排名對比 <span class="sub" style="font-size:0.82rem">💡 點圖可放大縮放</span></h2>
      <p class="sub">賽制規定 8 人名單同職業最多 2 名。圖中越靠<b>右側</b>代表平均排名越高，紅菱（帶 2 隻雙職業）明顯在藍方（帶 1 隻單職業）右邊即代表該職業非常值得配置 2 隻跨局輪轉！</p>
      <div id="copyChartWrap" style="margin:12px 0"></div>
      <details style="margin-top:12px">
        <summary style="cursor:pointer;color:var(--accent);font-weight:600">📋 展開查看 0 / 1 / 2 隻原始數值明細表</summary>
        <div class="table-wrap" style="margin-top:10px"><table id="copyTable"></table></div>
      </details>
    </div>

    <div class="card">
      <h2>各名次區間職業出場率 ＆ 雙職業組數結構 <span class="sub" style="font-size:0.82rem">💡 點圖可放大縮放</span></h2>
      <div id="tierCardWrap" style="margin-bottom:12px"></div>
      <details style="margin-top:10px">
        <summary style="cursor:pointer;color:var(--accent);font-weight:600">📋 展開查看「各名次區間出場率明細表」與「雙職業組數結構表」</summary>
        <p class="sub" style="margin:10px 0 6px">💡 橫著從左往右看（左邊是前 10 名、右邊是後段班）：越左邊數字越高＝頂尖強隊越愛用。</p>
        <div class="table-wrap" style="margin-bottom:14px"><table id="tierHeatTable"></table></div>
        <h3 style="font-size:0.98rem;margin:10px 0 6px">戰隊「雙職業組數」策略結構（8 異職 vs 1 / 2 / 3 組雙職業）</h3>
        <div class="table-wrap"><table id="dpStructTable"></table></div>
      </details>
    </div>
  </section>

  <section id="tab-synergy" class="panel">
    <div class="card">
      <h2>主流 8 人建隊流派骨架（Roster Archetypes）</h2>
      <div class="table-wrap"><table id="archTable"></table></div>
    </div>

    <div class="card">
      <h2>常見綁定搭檔 ＆ 二選一搶位分析 <span class="sub" style="font-size:0.82rem">💡 點擊矩陣圖可全螢幕放大縮放</span></h2>
      <div id="synCardWrap" style="margin-bottom:14px"></div>
      <div class="cards-grid">
        <div>
          <h3 style="margin:0 0 6px;font-size:1rem;color:var(--green)">🔥 常見綁定搭檔（搭檔倍率 ≥ 1.15x）</h3>
          <p class="sub" style="margin:0 0 8px;font-size:0.82rem">倍率越高代表這兩個職業越常「成套綁定出場」。</p>
          <div class="table-wrap"><table id="synTable"></table></div>
        </div>
        <div>
          <h3 style="margin:0 0 6px;font-size:1rem;color:var(--accent2)">⚡ 二選一搶位組合（搭檔倍率 ≤ 0.85x）</h3>
          <p class="sub" style="margin:0 0 8px;font-size:0.82rem">帶了 A 就明顯較少帶 B，代表常在搶同一個位置。</p>
          <div class="table-wrap"><table id="subTable"></table></div>
        </div>
      </div>
      <details style="margin-top:14px">
        <summary style="cursor:pointer;color:var(--accent);font-weight:600">📋 展開查看「熱門三職業組合排行（前 35 組）」</summary>
        <div class="table-wrap" style="margin-top:10px"><table id="tripleTable"></table></div>
      </details>
    </div>
  </section>

  <section id="tab-builder" class="panel">
    <div class="card">
      <h2>🧪 我方 8 人名單健檢器 ＆ AI 換角最佳化模擬</h2>
      <p class="sub">依據本場 200 隊大數據（0/1/2 隻平均名次、搭檔倍率矩陣與同職上限 2 規則），即時評估你的 8 人名單強度，並比對排行榜上最相似的實戰強隊！</p>
      <div class="filter-bar" style="margin-top:10px">
        <span class="sub">一鍵套用大數據推薦陣容：</span>
        <button class="preset-btn" data-preset="補師,法師,詩人,賢者,德魯伊,法師,流氓,武僧">🔥 推薦一：雙法跨局控場陣（均排 #57.6）</button>
        <button class="preset-btn" data-preset="補師,法師,詩人,賢者,德魯伊,流氓,騎士,武僧">👑 推薦二：8 異職全能陣（Top 10 主流）</button>
        <button class="preset-btn" data-preset="補師,法師,詩人,賢者,德魯伊,詩人,流氓,武僧">🎵 推薦三：雙詩人雙流派陣（均排 #87.8）</button>
      </div>
      <div class="builder-grid" id="builderSlots"></div>
      <div id="builderResult"></div>
    </div>
  </section>

  <footer>Game Leaderboard Analyzer v2 — Tournament Roster Strategy Report</footer>
</div>

<div class="zoom-modal" id="imgZoomModal">
  <div class="zoom-toolbar">
    <div>
      <b id="zoomModalTitle" style="color:var(--accent)">圖表放大檢視</b>
      <span class="sub" style="margin-left:10px">💡 滾輪：自由縮放 ｜ 按住滑鼠左鍵：拖曳平移 ｜ 雙擊圖片：切換 100% / 220%</span>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <button class="chip-btn" id="btnZoomOut">➖ 縮小</button>
      <span id="zoomPctLabel" style="min-width:52px;text-align:center;font-weight:700">100%</span>
      <button class="chip-btn" id="btnZoomIn">➕ 放大</button>
      <button class="chip-btn" id="btnZoomReset">🔄 適應螢幕 (100%)</button>
      <a class="preset-btn" id="btnZoomDownload" download="chart.png" style="text-decoration:none;padding:5px 12px">💾 下載高清圖卡</a>
      <button class="preset-btn" id="btnZoomClose" style="background:rgba(248,113,113,.2);border-color:var(--red)">✖ 關閉 (Esc)</button>
    </div>
  </div>
  <div class="zoom-stage" id="zoomStage">
    <img id="zoomModalImg" src="" alt="Zoomed Chart">
  </div>
</div>

<script>
const DATA = {json_blob};
const A = DATA.analytics;
const ICONS = DATA.icons || {{}};
const pct = v => (Number(v || 0) * 100).toFixed(1) + '%';
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
const ico = n => ICONS[n] ? `<img class="ico" src="${{ICONS[n]}}" alt="${{esc(n)}}">` : '';
const qCls = q => q.includes('T0') ? 'q-t0' : q.includes('黑馬') ? 'q-dark' : q.includes('標配') ? 'q-std' : 'q-low';

document.getElementById('genTime').textContent = '產生時間：' + DATA.generated_at;
const ov = A.overview;
document.getElementById('reportSub').textContent = `涵蓋排名 #${{ov.min_rank}}～#${{ov.max_rank}}｜共 ${{ov.total_teams}} 隊（8人名單・同職上限2・統一範本 BO5）`;

const bestDP = [...A.double_pick_structure].sort((a,b) => a.avg_rank - b.avg_rank)[0];
const bestSyn = A.synergy_pairs[0];
document.getElementById('kpiRow').innerHTML = [
  ['分析隊伍數', ov.total_teams + ' 隊'],
  ['辨識職業數', ov.distinct_occupations + ' 種'],
  ['最強勢雙職業結構', bestDP ? `${{bestDP.label}} (均#${{bestDP.avg_rank}})` : '-'],
  ['最強綁定搭檔', bestSyn ? `${{bestSyn.combination}} (${{bestSyn.synergy_lift}}x)` : '-'],
].map(([l, v]) => `<div class="kpi"><div class="lbl">${{l}}</div><div class="val">${{esc(v)}}</div></div>`).join('');

document.querySelectorAll('.tab').forEach(btn => btn.onclick = () => {{
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
}});

// Render crisp inline SVG Meta Quadrant
(function renderQuad() {{
  const rows = A.occupation_frequency;
  if (!rows.length) return;
  const W = 920, H = 540, padL = 62, padR = 30, padT = 36, padB = 48;
  const minR = Math.max(1, Math.min(...rows.map(r => r.avg_rank)) - 2);
  const maxR = Math.max(...rows.map(r => r.avg_rank)) + 2.2;
  const xOf = p => padL + (p / 105) * (W - padL - padR);
  const yOf = r => padT + ((r - minR) / Math.max(1, maxR - minR)) * (H - padT - padB);
  const xMid = xOf(50), yMid = yOf(ov.overall_avg_rank);

  let items = '';
  rows.forEach((r, idx) => {{
    const cx = xOf(r.team_presence_rate * 100);
    const cy = yOf(r.avg_rank);
    const clipId = 'clip_' + idx;
    const imgTag = ICONS[r.occupation]
      ? `<defs><clipPath id="${{clipId}}"><circle cx="${{cx}}" cy="${{cy}}" r="15"/></clipPath></defs><image href="${{ICONS[r.occupation]}}" x="${{cx-15}}" y="${{cy-15}}" width="30" height="30" clip-path="url(#${{clipId}})"/>`
      : `<circle cx="${{cx}}" cy="${{cy}}" r="11" fill="#38bdf8"/>`;
    const ring = r.low_sample ? `<circle cx="${{cx}}" cy="${{cy}}" r="18" fill="none" stroke="#f59e0b" stroke-dasharray="4 3" stroke-width="1.5"/>` : '';
    items += `${{ring}}${{imgTag}}<text x="${{cx}}" y="${{cy+27}}" text-anchor="middle" fill="${{r.low_sample ? '#fcd34d' : '#f8fafc'}}" font-size="11" font-weight="700">${{esc(r.occupation)}} #${{r.avg_rank}}</text>`;
  }});

  document.getElementById('quadSvgBox').innerHTML = `
  <svg class="quad" viewBox="0 0 ${{W}} ${{H}}">
    <rect x="${{xMid}}" y="${{padT}}" width="${{W-padR-xMid}}" height="${{yMid-padT}}" fill="#38bdf8" fill-opacity="0.06"/>
    <line x1="${{xMid}}" y1="${{padT}}" x2="${{xMid}}" y2="${{H-padB}}" stroke="#475569" stroke-dasharray="6 4"/>
    <line x1="${{padL}}" y1="${{yMid}}" x2="${{W-padR}}" y2="${{yMid}}" stroke="#475569" stroke-dasharray="6 4"/>
    <text x="${{W-padR-8}}" y="${{padT+18}}" text-anchor="end" fill="#38bdf8" font-size="12" font-weight="700">★ T0 版本核心（高出場 × 高排）</text>
    <text x="${{padL+8}}" y="${{padT+18}}" text-anchor="start" fill="#4ade80" font-size="12" font-weight="700">⚡ 高端奇兵 / 黑馬</text>
    <text x="${{W-padR-8}}" y="${{H-padB-10}}" text-anchor="end" fill="#fbbf24" font-size="11.5" font-weight="700">⚖️ 普及標配</text>
    <text x="${{padL+8}}" y="${{H-padB-10}}" text-anchor="start" fill="#94a3b8" font-size="11.5" font-weight="700">🧊 冷門職</text>
    <text x="${{W/2}}" y="${{H-12}}" text-anchor="middle" fill="#cbd5e1" font-size="12">隊伍出場率 (%) →</text>
    <text x="20" y="${{H/2 - 86}}" text-anchor="middle" fill="#cbd5e1" font-size="12" font-weight="700">
      <tspan x="20" dy="0">↑</tspan>
      <tspan x="20" dy="16">排</tspan>
      <tspan x="20" dy="16">名</tspan>
      <tspan x="20" dy="16">越</tspan>
      <tspan x="20" dy="16">高</tspan>
      <tspan x="20" dy="26">平</tspan>
      <tspan x="20" dy="16">均</tspan>
      <tspan x="20" dy="16">排</tspan>
      <tspan x="20" dy="16">名</tspan>
    </text>
    ${{items}}
  </svg>`;
}})();

const fmtRho = r => {{
  const v = Number(r || 0);
  if (v <= -0.15) return `<span class="pos">${{v}} (🔥帶越多名次越前)</span>`;
  if (v <= -0.07) return `<span class="pos">${{v}} (↗偏前段)</span>`;
  if (v >= 0.15) return `<span class="neg">${{v}} (⚠️偏中後段)</span>`;
  if (v >= 0.07) return `<span class="neg">${{v}} (↘稍偏後段)</span>`;
  return `<span class="sub">${{v}} (➖無明顯關聯)</span>`;
}};

document.getElementById('occTable').innerHTML =
  '<thead><tr><th>職業</th><th>Meta 象限</th><th>隊伍出場率(隊數)</th><th>總席次佔比</th><th>雙職業率(帶2隻隊數)</th><th>平均排名</th><th title="前段班出場率 ÷ 全體出場率，>1.0x 代表前段班強隊更偏愛">前段班偏好倍率 ⓘ</th><th title="負值代表帶越多隻名次越靠前，正值代表偏向中後段班">名次相關性 ⓘ</th></tr></thead><tbody>' +
  A.occupation_frequency.map(r => `<tr><td><span class="lbl-flex">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td><td><span class="q-tag ${{qCls(r.quadrant)}}">${{esc(r.quadrant)}}</span></td><td><b>${{pct(r.team_presence_rate)}}</b> (${{r.team_count}}隊)</td><td>${{pct(r.slot_rate)}} (${{r.slot_count}})</td><td>${{pct(r.double_pick_rate)}} (${{r.double_pick_teams}}隊)</td><td><b>#${{r.avg_rank}}</b></td><td><b>${{r.top_tier_lift}}x</b></td><td>${{fmtRho(r.spearman_r)}}</td></tr>`).join('') +
  '</tbody>';

const CARDS = DATA.cards || {{}};
const mkZoomImg = (src, title, maxW = '1100px') =>
  `<img class="zoomable-img" src="${{src}}" alt="${{esc(title)}}" data-zoom-title="${{esc(title)}}" style="width:100%;max-width:${{maxW}};display:block;margin:0 auto">`;

if (CARDS.meta_quadrant && document.getElementById('quadCardWrap')) {{
  document.getElementById('quadCardWrap').innerHTML = mkZoomImg(CARDS.meta_quadrant, 'Meta 四象限戰略圖（點圖放大縮放）');
}}
if (CARDS.copy_impact) {{
  document.getElementById('copyChartWrap').innerHTML = mkZoomImg(CARDS.copy_impact, '0隻 vs 1隻(單職業) vs 2隻(雙職業) 平均排名影響');
}}
if (CARDS.tier_heatmap && document.getElementById('tierCardWrap')) {{
  document.getElementById('tierCardWrap').innerHTML = mkZoomImg(CARDS.tier_heatmap, '各名次區間職業出場率 ＆ 雙職業組隊結構');
}}
if (CARDS.synergy_matrix && document.getElementById('synCardWrap')) {{
  document.getElementById('synCardWrap').innerHTML = mkZoomImg(CARDS.synergy_matrix, '常見綁定搭檔 ＆ 二選一搶位矩陣（搭檔倍率）', '860px');
}}
if (document.getElementById('allShareCardsGrid')) {{
  const cardDefs = [
    ['meta_quadrant', '1. Meta 四象限戰略圖'],
    ['copy_impact', '2. 0 隻 vs 1 隻（單職業）vs 2 隻（雙職業）平均排名影響'],
    ['tier_heatmap', '3. 各名次區間職業出場率 ＆ 雙職業組隊結構'],
    ['synergy_matrix', '4. 常見綁定搭檔 ＆ 二選一搶位矩陣'],
  ];
  document.getElementById('allShareCardsGrid').innerHTML = cardDefs
    .filter(([k]) => CARDS[k])
    .map(([k, lbl]) => `<div class="card" style="background:#0f172a;margin:0"><h3 style="margin:0 0 8px;font-size:0.96rem;color:var(--accent)">${{esc(lbl)}} <span class="sub" style="font-size:0.78rem">（點擊放大）</span></h3>${{mkZoomImg(CARDS[k], lbl)}}</div>`)
    .join('');
}}

const fmtB = b => b && b.teams ? `<b>#${{b.avg_rank}}</b> <span class="sub">(${{b.teams}}隊${{b.low_sample?', n<5':''}})</span>` : '<span class="sub">-</span>';
document.getElementById('copyTable').innerHTML =
  '<thead><tr><th>職業</th><th>帶 0 隻（不帶）</th><th>帶 1 隻（單職業）</th><th>帶 2 隻（雙職業）</th><th>雙職業名次提升 (1隻→2隻)</th></tr></thead><tbody>' +
  A.occupation_frequency.map(r => {{
    const g = r.double_rank_gain;
    const gHtml = g === null || g === undefined ? '-' : `<span class="${{g>=0?'pos':'neg'}}">${{g>=0?'+':''}}${{g}} 名</span>`;
    return `<tr><td><span class="lbl-flex">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td><td>${{fmtB(r.copy_0)}}</td><td>${{fmtB(r.copy_1)}}</td><td>${{fmtB(r.copy_2)}}</td><td>${{gHtml}}</td></tr>`;
  }}).join('') + '</tbody>';

const tiers = A.ranking_analysis.tiers;
const firstTierKey = tiers.length ? tiers[0].tier : '';
const lastTierKey = tiers.length ? tiers[tiers.length - 1].tier : '';
document.getElementById('tierHeatTable').innerHTML =
  `<thead><tr><th>職業</th><th>全場出場率</th>${{tiers.map(t => `<th>${{esc(t.tier)}} 名<br><span class="sub">(${{t.team_count}}隊)</span></th>`).join('')}}<th>前段 vs 後段差</th><th>平均排名</th></tr></thead><tbody>` +
  A.ranking_analysis.occupation_tier_comparison.map(r => {{
    const firstV = r.tier_rates[firstTierKey] || 0;
    const lastV = r.tier_rates[lastTierKey] || 0;
    const diff = firstV - lastV;
    const trendTxt = diff >= 0.08 ? `↑ 前段愛帶 (+${{pct(diff)}})` : diff <= -0.08 ? `↓ 後段較多 (${{pct(diff)}})` : `— 差不多 (${{diff>=0?'+':''}}${{pct(diff)}})`;
    const trendCls = diff >= 0.08 ? 'pos' : diff <= -0.08 ? 'neg' : 'sub';
    return `<tr><td><span class="lbl-flex">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td><td>${{pct(r.team_presence_rate)}}</td>${{tiers.map(t => {{
      const v = r.tier_rates[t.tier] || 0;
      const alpha = (0.08 + v * 0.65).toFixed(2);
      return `<td class="heat-cell" style="background:rgba(56,189,248,${{alpha}})">${{pct(v)}}</td>`;
    }}).join('')}}<td class="${{trendCls}}">${{trendTxt}}</td><td><b>#${{r.avg_rank}}</b></td></tr>`;
  }}).join('') + '</tbody>';

document.getElementById('dpStructTable').innerHTML =
  '<thead><tr><th>雙職業組數配置</th><th>隊伍數</th><th>佔比</th><th>平均排名</th><th>中位排名</th><th>最高排名</th><th>Top 10 隊數</th></tr></thead><tbody>' +
  A.double_pick_structure.map(d => `<tr><td><b>${{esc(d.label)}}</b></td><td>${{d.team_count}}</td><td>${{pct(d.team_rate)}}</td><td><b>#${{d.avg_rank}}</b></td><td>#${{d.median_rank}}</td><td>#${{d.best_rank}}</td><td>${{d.top10_count}}</td></tr>`).join('') + '</tbody>';

document.getElementById('archTable').innerHTML =
  '<thead><tr><th>流派</th><th>隊數(佔比)</th><th>均排 / 最高</th><th>平均雙職業組數</th><th>核心必帶職</th><th>常見搖擺位</th><th>代表戰隊</th></tr></thead><tbody>' +
  (A.roster_archetypes || []).map(a => `<tr><td><b>${{esc(a.archetype_id)}}</b> ${{esc(a.archetype_name)}}</td><td>${{a.team_count}} (${{pct(a.team_rate)}})</td><td><b>#${{a.avg_rank}}</b> / #${{a.best_rank}}</td><td>${{a.avg_double_picks}}</td><td>${{esc(a.core_classes)}}</td><td class="sub">${{esc(a.flex_classes)}}</td><td class="sub">${{esc(a.sample_teams)}}</td></tr>`).join('') + '</tbody>';

const fillSyn = (id, rows) => {{
  document.getElementById(id).innerHTML =
    '<thead><tr><th>雙職組合</th><th>搭檔倍率</th><th>實際同隊佔比(隊數)</th><th>隨機預期</th><th>平均排名</th><th>代表戰隊</th></tr></thead><tbody>' +
    (rows.length ? rows.map(r => `<tr><td><b>${{esc(r.combination)}}</b></td><td class="${{r.synergy_lift>=1.15?'pos':'neg'}}">${{r.synergy_lift}}x</td><td>${{pct(r.team_rate)}} (${{r.team_count}}隊)</td><td>${{pct(r.expected_rate)}}</td><td>${{r.avg_rank ? '#'+r.avg_rank : '-'}}</td><td class="sub">${{esc(r.sample_teams)}}</td></tr>`).join('') : '<tr><td colspan="6" class="sub">無明顯項目</td></tr>') + '</tbody>';
}};
fillSyn('synTable', A.synergy_pairs || []);
fillSyn('subTable', A.substitution_pairs || []);

document.getElementById('tripleTable').innerHTML =
  '<thead><tr><th>三職業組合</th><th>隊數</th><th>佔比</th><th>平均排名</th><th>Top 10 佔比</th><th>代表戰隊</th></tr></thead><tbody>' +
  (A.triple_combinations || []).slice(0, 35).map(r => `<tr><td><b>${{esc(r.combination)}}</b></td><td>${{r.team_count}}</td><td>${{pct(r.team_rate)}}</td><td>#${{r.avg_rank}}</td><td>${{pct(r.top10_rate)}}</td><td class="sub">${{esc(r.sample_teams)}}</td></tr>`).join('') + '</tbody>';

// Opponent Roster Feature & Tactical Reminder Card Generator
function buildScoutCardHtml(team) {{
  const rawOccs = (team.occupations || []).filter(Boolean);
  const counts = {{}};
  rawOccs.forEach(o => counts[o] = (counts[o] || 0) + 1);
  const doubles = Object.keys(counts).filter(o => counts[o] >= 2);

  const tips = [];
  const default5Str = rawOccs.slice(0, 5).join(' / ');
  const bench3Str = rawOccs.slice(5, 8).join(' / ');
  tips.push(`📋 <b>遊戲內預設席次</b>：前 5 格預設先發【<b>${{esc(default5Str)}}</b>】｜後 3 格替補【<b>${{esc(bench3Str || '無')}}</b>】（開賽前仍可替換）。`);

  if ((counts['補師'] || 0) >= 2) {{
    tips.push('💉 <b>雙補師配置 (補師×2)</b>：對手擁有 2 隻補師可分攤 5v5 與 3v3 出戰紀錄，即使在 G4 (2v2) 禁選掉其 G3 的補師，對手 G4 席次 1 仍可保底有補師登場。');
  }} else if ((counts['補師'] || 0) === 1) {{
    tips.push('🚫 <b>單補師配置 (補師×1)</b>：對手僅 1 隻補師；若該補師在 G1 (5v5) 與 G3 (3v3) 皆出場，進入 G4 (2v2) 時<b>可優先禁選其 G3 的補師</b>，迫使對手在 2v2 打無補師局。');
  }} else {{
    tips.push('⚠️ <b>無正統補師名單</b>：對手 8 人名單中未攜帶補師，續航與復活容錯極低，可全力強壓換血。');
  }}

  if ((counts['法師'] || 0) >= 2) {{
    tips.push('❄️ <b>雙法師配置 (法師×2)</b>：對手配置 2 隻法師（多用於跨局分攤 G1/G3/G4 控場，使各局皆有法師控場不斷檔）。');
  }}
  if ((counts['詩人'] || 0) >= 2) {{
    tips.push('🎵 <b>雙詩人配置 (詩人×2)</b>：對手配置 2 隻詩人，可跨局分攤 3v3/2v2 輔助位，或於賽前切換「1 輔助流 ＋ 1 輸出流」。');
  }}
  if (counts['德魯伊']) {{
    tips.push('🌿 <b>德魯伊團戰範圍壓制</b>：對手帶有德魯伊，大範圍 AOE 傷害與控場在 5v5 團戰威脅極高，需注意分散站位。');
  }}
  if (counts['武僧']) {{
    tips.push('🥊 <b>武僧阿修羅減員威脅</b>：對手帶有武僧，核心戰術為阿修羅一拳秒殺製造人數差，需特別注意關鍵目標保護。');
  }}
  if (counts['煉金']) {{
    tips.push('⚗️ <b>煉金護貝＆毀裝干擾</b>：對手帶有煉金，具備護貝（保護隊友免於裝備破壞）與單體攻擊破壞我方裝備的能力。');
  }}
  if (counts['刺客'] || counts['流氓']) {{
    const burstNames = ['流氓', '刺客'].filter(c => counts[c]).join('、');
    tips.push(`🗡️ <b>高機動手長單體爆發（${{burstNames}}）</b>：機動性佳、手長且單體 DPS 爆發高，但本體偏軟，可透過控場鎖定後集火反殺。`);
  }}

  return `
  <div class="scout-box">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <div><b>🎯 #${{team.rank}} ${{esc(team.team_name)}} — 對手陣容特徵 ＆ 實戰對局提醒</b></div>
      <span class="sub">雙職業配置：${{doubles.length ? doubles.map(d => `<b>${{d}}×2</b>`).join('、') : '無（全 8 異職）'}}</span>
    </div>
    <div style="margin-top:8px;font-size:0.87rem;line-height:1.7">
      ${{tips.map(t => `<div>• ${{t}}</div>`).join('')}}
    </div>
  </div>`;
}}

// Tab 1 Filtering (Script + Visual Feature + Fuzzy Search + Click-to-Scout)
const occSel = document.getElementById('occFilter');
A.occupation_frequency.forEach(r => {{ const o = document.createElement('option'); o.value = r.occupation; o.textContent = r.occupation; occSel.appendChild(o); }});
const dpSel = document.getElementById('dpFilter');
let activeScript = 'all';
let activeFeat = 'all';
let expandedRanks = new Set();

function detectScript(name) {{
  const s = String(name || '');
  if (/[\u0e00-\u0e7f]/.test(s)) return 'th';
  if (/[\u4e00-\u9fff]/.test(s)) return 'zh';
  return 'en';
}}

function matchFeature(name, feat) {{
  const s = String(name || '').trim();
  const len = [...s].length;
  if (feat === 'num') return /\d/.test(s);
  if (feat === 'sym') return /[^a-zA-Z0-9\u4e00-\u9fff\u0e00-\u0e7f\s]/.test(s);
  if (feat === 'short') return len <= 5;
  if (feat === 'mid') return len >= 6 && len <= 9;
  if (feat === 'long') return len >= 10;
  return true;
}}

function fuzzyMatch(text, query) {{
  if (!query) return true;
  const t = String(text || '').toLowerCase();
  const q = query.toLowerCase().replace(/^#/, '');
  if (t.includes(q)) return true;
  // Subsequence match for quick alphanumeric abbreviation lookup (e.g. "exl" -> "Encore.EXLI")
  let qi = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {{
    if (t[ti] === q[qi]) qi++;
  }}
  return qi === q.length && q.length >= 2;
}}

document.querySelectorAll('#scriptFilterBar .chip-btn').forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll('#scriptFilterBar .chip-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeScript = btn.dataset.script;
    renderRaw();
  }};
}});

document.querySelectorAll('#featFilterBar .chip-btn').forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll('#featFilterBar .chip-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeFeat = btn.dataset.feat;
    renderRaw();
  }};
}});

window.toggleScoutRow = function(rank) {{
  if (expandedRanks.has(rank)) expandedRanks.delete(rank);
  else expandedRanks.add(rank);
  renderRaw();
}};

function renderRaw() {{
  const q = document.getElementById('searchInput').value.trim();
  const occ = occSel.value;
  const dp = dpSel.value;
  const filtered = A.raw_data.filter(r => {{
    if (activeScript !== 'all' && detectScript(r.team_name) !== activeScript) return false;
    if (activeFeat !== 'all' && !matchFeature(r.team_name, activeFeat)) return false;
    if (occ && !r.occupations.includes(occ)) return false;
    if (dp !== '') {{
      const dpc = r.double_pick_count || 0;
      if (dp === '3' ? dpc < 3 : dpc !== Number(dp)) return false;
    }}
    if (q) {{
      const rankHit = String(r.rank) === q.replace(/^#/, '') || ('#' + r.rank).includes(q);
      const nameHit = fuzzyMatch(r.team_name, q);
      const sigHit = (r.full_team_signature || '').toLowerCase().includes(q.toLowerCase());
      if (!rankHit && !nameHit && !sigHit) return false;
    }}
    return true;
  }});

  document.getElementById('rawCount').textContent = `顯示 ${{filtered.length}} / ${{A.raw_data.length}} 隊（點擊任一列展開對局提醒卡）`;
  const scriptBadge = s => s === 'th' ? '<span class="q-tag q-std" style="margin-right:6px">🇹🇭泰</span>' : s === 'zh' ? '<span class="q-tag q-t0" style="margin-right:6px">🇹🇼中</span>' : '<span class="q-tag q-low" style="margin-right:6px">🔤英</span>';

  let rowsHtml = '';
  filtered.forEach(r => {{
    const counts = {{}};
    (r.occupations || []).forEach(o => counts[o] = (counts[o] || 0) + 1);
    const isExp = expandedRanks.has(r.rank);
    rowsHtml += `<tr class="team-row" onclick="toggleScoutRow(${{r.rank}})">
      <td><b>#${{r.rank}}</b></td>
      <td>${{scriptBadge(detectScript(r.team_name))}}<b>${{esc(r.team_name)}}</b> <span class="sub" style="font-size:0.76rem">${{isExp ? '▲ 收合提醒' : '▼ 對局提醒'}}</span></td>
      <td>${{r.score ?? '-'}}</td>
      <td>${{r.double_pick_count}} 組</td>
      <td>${{r.occupations.map(o => `<span class="pill ${{counts[o]>=2?'dp':''}}">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')}}</td>
    </tr>`;
    if (isExp) {{
      rowsHtml += `<tr><td colspan="5" style="padding:4px 10px 14px;background:#090e1a">${{buildScoutCardHtml(r)}}</td></tr>`;
    }}
  }});

  document.getElementById('rawTable').innerHTML =
    '<thead><tr><th>排名</th><th>戰隊名稱（點擊展開對局提醒卡）</th><th>積分</th><th>雙職業</th><th>8 人名單配置（金色外框＝雙職業）</th></tr></thead><tbody>' +
    rowsHtml + '</tbody>';
}}
document.getElementById('searchInput').oninput = renderRaw;
occSel.onchange = renderRaw;
dpSel.onchange = renderRaw;
renderRaw();

// GitHub Pages Client-Side Screenshot Paste & Free OCR API (Tesseract.js CDN + OCR.space + Visual Fingerprint)
(function initOnlineImageScout() {{
  const NAME_FPS = DATA.name_fps || {{}};
  const modeSel = document.getElementById('ocrModeSelect');
  const keyInp = document.getElementById('ocrSpaceKeyInput');
  const fileInp = document.getElementById('onlineScoutFile');
  const resBox = document.getElementById('onlineScoutResult');

  if (keyInp) {{
    keyInp.value = localStorage.getItem('gla_ocrspace_key') || '';
    keyInp.onchange = () => localStorage.setItem('gla_ocrspace_key', keyInp.value.trim());
  }}
  if (modeSel && keyInp) {{
    modeSel.onchange = () => {{
      keyInp.style.display = modeSel.value === 'ocrspace' ? 'inline-block' : 'none';
    }};
  }}

  function quantile(sortedArr, q) {{
    if (!sortedArr.length) return 0;
    const pos = Math.floor((sortedArr.length - 1) * q);
    return sortedArr[Math.max(0, Math.min(sortedArr.length - 1, pos))];
  }}

  // Extract 48x12 visual silhouette fingerprint + high-contrast black-on-white OCR canvas from pasted image
  function preprocessAndExtractFp(imgEl) {{
    const w = imgEl.naturalWidth || imgEl.width;
    const h = imgEl.naturalHeight || imgEl.height;
    const c1 = document.createElement('canvas');
    c1.width = w; c1.height = h;
    const ctx1 = c1.getContext('2d');
    ctx1.drawImage(imgEl, 0, 0);
    const rgba = ctx1.getImageData(0, 0, w, h).data;

    const lum = new Float32Array(w * h);
    let lMin = 255, lMax = 0;
    for (let i = 0, p = 0; i < rgba.length; i += 4, p++) {{
      const v = 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2];
      lum[p] = v;
      if (v < lMin) lMin = v;
      if (v > lMax) lMax = v;
    }}
    const range = Math.max(1, lMax - lMin);
    const norm = new Float32Array(w * h);
    const xs = [], ys = [];
    for (let y = 0; y < h; y++) {{
      for (let x = 0; x < w; x++) {{
        const nv = ((lum[y * w + x] - lMin) * 255) / range;
        norm[y * w + x] = nv;
        if (nv > 145) {{ xs.push(x); ys.push(y); }}
      }}
    }}

    let x1 = 0, y1 = 0, x2 = w, y2 = h;
    if (xs.length >= 10 && ys.length >= 5) {{
      xs.sort((a, b) => a - b);
      ys.sort((a, b) => a - b);
      x1 = Math.max(0, quantile(xs, 0.02) - 1);
      x2 = Math.min(w, quantile(xs, 0.98) + 2);
      y1 = Math.max(0, quantile(ys, 0.04) - 1);
      y2 = Math.min(h, quantile(ys, 0.96) + 2);
      if (x2 <= x1 + 4 || y2 <= y1 + 3) {{ x1 = 0; y1 = 0; x2 = w; y2 = h; }}
    }}

    const rw = Math.max(1, x2 - x1), rh = Math.max(1, y2 - y1);
    const aspect = rw / rh;

    // Build normalized ROI canvas and resize to 48x12 for silhouette fingerprint
    const cRoi = document.createElement('canvas');
    cRoi.width = rw; cRoi.height = rh;
    const ctxRoi = cRoi.getContext('2d');
    const roiImg = ctxRoi.createImageData(rw, rh);
    for (let yy = 0; yy < rh; yy++) {{
      for (let xx = 0; xx < rw; xx++) {{
        const val = Math.round(norm[(y1 + yy) * w + (x1 + xx)]);
        const idx = (yy * rw + xx) * 4;
        roiImg.data[idx] = val; roiImg.data[idx + 1] = val; roiImg.data[idx + 2] = val; roiImg.data[idx + 3] = 255;
      }}
    }}
    ctxRoi.putImageData(roiImg, 0, 0);

    const FW = 48, FH = 12;
    const cFp = document.createElement('canvas');
    cFp.width = FW; cFp.height = FH;
    const ctxFp = cFp.getContext('2d');
    ctxFp.drawImage(cRoi, 0, 0, FW, FH);
    const fpData = ctxFp.getImageData(0, 0, FW, FH).data;
    const vec = new Float32Array(FW * FH);
    let sum = 0;
    for (let i = 0, p = 0; i < fpData.length; i += 4, p++) {{
      vec[p] = fpData[i];
      sum += fpData[i];
    }}
    const mean = sum / (FW * FH);
    let normSq = 0;
    for (let p = 0; p < vec.length; p++) {{
      vec[p] -= mean;
      normSq += vec[p] * vec[p];
    }}
    const denom = Math.sqrt(normSq) || 1;
    for (let p = 0; p < vec.length; p++) vec[p] /= denom;

    // Also build a 3x upscaled, padded black-text-on-white-bg image for high-accuracy OCR
    const scale = 3, pad = 18;
    const cOcr = document.createElement('canvas');
    cOcr.width = rw * scale + pad * 2;
    cOcr.height = rh * scale + pad * 2;
    const ctxOcr = cOcr.getContext('2d');
    ctxOcr.fillStyle = '#ffffff';
    ctxOcr.fillRect(0, 0, cOcr.width, cOcr.height);
    // Invert normalized ROI (bright text -> dark ink on white paper)
    const invImg = ctxRoi.createImageData(rw, rh);
    for (let i = 0; i < roiImg.data.length; i += 4) {{
      const v = roiImg.data[i];
      const ink = v > 130 ? Math.max(0, 255 - v) : 255;
      invImg.data[i] = ink; invImg.data[i + 1] = ink; invImg.data[i + 2] = ink; invImg.data[i + 3] = 255;
    }}
    const cInv = document.createElement('canvas');
    cInv.width = rw; cInv.height = rh;
    cInv.getContext('2d').putImageData(invImg, 0, 0);
    ctxOcr.drawImage(cInv, pad, pad, rw * scale, rh * scale);

    return {{ vec, aspect, ocrDataUrl: cOcr.toDataURL('image/png') }};
  }}

  function calcTextSim(a, b) {{
    const s1 = String(a || '').toLowerCase().replace(/[\s_\-\.]+/g, '');
    const s2 = String(b || '').toLowerCase().replace(/[\s_\-\.]+/g, '');
    if (!s1 || !s2) return 0;
    if (s1 === s2) return 1.0;
    if (s1.includes(s2) || s2.includes(s1)) {{
      return Math.max(0.84, Math.min(s1.length, s2.length) / Math.max(s1.length, s2.length));
    }}
    // Levenshtein edit similarity
    const m = s1.length, n = s2.length;
    const dp = Array.from({{ length: m + 1 }}, () => new Int32Array(n + 1));
    for (let i = 0; i <= m; i++) dp[i][0] = i;
    for (let j = 0; j <= n; j++) dp[0][j] = j;
    for (let i = 1; i <= m; i++) {{
      for (let j = 1; j <= n; j++) {{
        const cost = s1[i - 1] === s2[j - 1] ? 0 : 1;
        dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
      }}
    }}
    return Math.max(0, 1 - dp[m][n] / Math.max(m, n));
  }}

  function rankTeamsByFpAndText(fp, ocrText) {{
    const cleanOcr = String(ocrText || '').trim();
    const scored = A.raw_data.map(team => {{
      const tfp = NAME_FPS[team.rank];
      let visSim = 0;
      if (tfp && tfp.v && fp && fp.vec) {{
        let dot = 0;
        for (let i = 0; i < fp.vec.length && i < tfp.v.length; i++) {{
          dot += fp.vec[i] * (tfp.v[i] / 1000.0);
        }}
        // Penalize large aspect-ratio mismatch (e.g. short 3-char name vs long 12-char name)
        const aspectRatio = Math.min(fp.aspect, tfp.a) / Math.max(0.1, Math.max(fp.aspect, tfp.a));
        visSim = Math.max(0, dot) * (0.75 + 0.25 * aspectRatio);
      }}
      const txtSim = cleanOcr ? calcTextSim(cleanOcr, team.team_name) : 0;
      const combined = cleanOcr
        ? Math.max(txtSim, visSim * 0.92, txtSim * 0.65 + visSim * 0.35)
        : visSim;
      const reasons = [];
      if (txtSim >= 0.42) reasons.push(`OCR文字吻合 ${{Math.round(txtSim * 100)}}%`);
      if (visSim >= 0.35) reasons.push(`原圖字形吻合 ${{Math.round(visSim * 100)}}%`);
      return {{
        team,
        combined,
        txtSim,
        visSim,
        reason: reasons.join(' ＋ ') || `字形相似度 ${{Math.round(combined * 100)}}%`,
      }};
    }});
    scored.sort((a, b) => b.combined - a.combined || a.team.rank - b.team.rank);
    return scored.slice(0, 5);
  }}

  window.lockAndExpandScoutTeam = function(rank, name) {{
    activeScript = 'all';
    activeFeat = 'all';
    document.querySelectorAll('#scriptFilterBar .chip-btn').forEach(b => b.classList.toggle('active', b.dataset.script === 'all'));
    document.querySelectorAll('#featFilterBar .chip-btn').forEach(b => b.classList.toggle('active', b.dataset.feat === 'all'));
    document.getElementById('searchInput').value = '#' + rank;
    expandedRanks.add(rank);
    renderRaw();
    document.getElementById('rawTable').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }};

  function renderOnlineScoutMatches(rawDataUrl, ocrText, statusMsg, matches) {{
    resBox.style.display = 'block';
    resBox.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <img src="${{rawDataUrl}}" alt="pasted" style="height:32px;border-radius:6px;border:1px solid var(--accent)">
          <span>${{statusMsg}}</span>
          ${{ocrText ? `<span>｜OCR 辨識文字：<code style="color:var(--accent);font-weight:700">${{esc(ocrText)}}</code></span>` : ''}}
        </div>
        <button class="chip-btn" onclick="document.getElementById('onlineScoutResult').style.display='none'">✖ 關閉</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>吻合度</th><th>排名</th><th>戰隊名稱</th><th>對方 8 職業陣容（金框＝雙職業）</th><th>操作</th></tr></thead>
          <tbody>
            ${{matches.map((m, idx) => {{
              const t = m.team;
              const cnts = {{}};
              (t.occupations || []).forEach(o => cnts[o] = (cnts[o] || 0) + 1);
              return `<tr style="${{idx === 0 ? 'background:rgba(56,189,248,.13)' : ''}}">
                <td><span class="q-tag ${{idx === 0 ? 'q-t0' : 'q-dark'}}">${{esc(m.reason)}}</span></td>
                <td><b>#${{t.rank}}</b></td>
                <td><b>${{esc(t.team_name)}}</b></td>
                <td>${{t.occupations.map(o => `<span class="pill ${{cnts[o]>=2?'dp':''}}">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')}}</td>
                <td><button class="preset-btn" style="padding:4px 10px;font-size:0.78rem" onclick="lockAndExpandScoutTeam(${{t.rank}})">🎯 展開對局提醒</button></td>
              </tr>`;
            }}).join('')}}
          </tbody>
        </table>
      </div>
    `;
  }}

  let tesseractPromise = null;
  function loadTesseractJs() {{
    if (window.Tesseract) return Promise.resolve(window.Tesseract);
    if (tesseractPromise) return tesseractPromise;
    tesseractPromise = new Promise((resolve, reject) => {{
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js';
      s.onload = () => resolve(window.Tesseract);
      s.onerror = () => reject(new Error('無法載入 Tesseract.js CDN'));
      document.head.appendChild(s);
    }});
    return tesseractPromise;
  }}

  async function runFreeOcrApi(ocrDataUrl, mode) {{
    if (mode === 'visual') return '';
    if (mode === 'ocrspace') {{
      const apiKey = (keyInp && keyInp.value.trim()) || 'helloworld';
      const form = new FormData();
      form.append('base64Image', ocrDataUrl);
      form.append('language', 'cht');
      form.append('OCREngine', '2');
      form.append('scale', 'true');
      const resp = await fetch('https://api.ocr.space/parse/image', {{
        method: 'POST',
        headers: {{ 'apikey': apiKey }},
        body: form,
      }});
      const json = await resp.json();
      const parsed = json && json.ParsedResults && json.ParsedResults[0];
      return (parsed && parsed.ParsedText ? parsed.ParsedText : '').replace(/\s+/g, ' ').trim();
    }}
    // Default: Free Serverless Browser OCR via Tesseract.js (chi_tra + eng + tha)
    const Tesseract = await loadTesseractJs();
    const res = await Tesseract.recognize(ocrDataUrl, 'chi_tra+eng+tha');
    return (res && res.data && res.data.text ? res.data.text : '').replace(/\s+/g, ' ').trim();
  }}

  function handleScreenshotDataUrl(rawDataUrl) {{
    // Switch to Tab 1 if user pasted while viewing another tab
    document.querySelector('.tab[data-tab="raw"]').click();
    const img = new Image();
    img.onload = async () => {{
      const fp = preprocessAndExtractFp(img);
      const mode = modeSel ? modeSel.value : 'tesseract';
      // 1. Instant 0.01s Visual Fingerprint Top 5
      const initialMatches = rankTeamsByFpAndText(fp, '');
      const statusTxt = mode === 'visual'
        ? '✅ 已完成 200 隊原圖字形指紋比對'
        : '⏳ 已先列出字形最吻合前 5 隊，正在呼叫免費多語系 OCR API 強化精準度...';
      renderOnlineScoutMatches(rawDataUrl, '', statusTxt, initialMatches);

      if (mode !== 'visual') {{
        try {{
          const ocrText = await runFreeOcrApi(fp.ocrDataUrl, mode);
          const finalMatches = rankTeamsByFpAndText(fp, ocrText);
          renderOnlineScoutMatches(rawDataUrl, ocrText, '✅ 雙引擎（免費 OCR API ＋ 原圖字形指紋）比對完成', finalMatches);
          if (finalMatches.length > 0 && finalMatches[0].combined >= 0.45) {{
            expandedRanks.add(finalMatches[0].team.rank);
            renderRaw();
          }}
        }} catch (err) {{
          renderOnlineScoutMatches(rawDataUrl, '', `⚠️ OCR API 連線逾時（${{esc(err.message)}}），已自動採用「原圖字形指紋比對」結果`, initialMatches);
        }}
      }} else if (initialMatches.length > 0) {{
        expandedRanks.add(initialMatches[0].team.rank);
        renderRaw();
      }}
    }};
    img.src = rawDataUrl;
  }}

  window.addEventListener('paste', ev => {{
    const items = (ev.clipboardData && ev.clipboardData.items) || [];
    for (const item of items) {{
      if (item.type && item.type.startsWith('image/')) {{
        const file = item.getAsFile();
        if (!file) continue;
        const reader = new FileReader();
        reader.onload = () => handleScreenshotDataUrl(reader.result);
        reader.readAsDataURL(file);
        ev.preventDefault();
        break;
      }}
    }}
  }});

  if (fileInp) {{
    fileInp.onchange = ev => {{
      const file = ev.target.files && ev.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => handleScreenshotDataUrl(reader.result);
      reader.readAsDataURL(file);
    }};
  }}
}})();

// Tab 6: My 8-Player Roster Builder & Evaluator
(function initRosterBuilder() {{
  const allOccs = A.occupation_frequency.map(r => r.occupation);
  const occStats = {{}};
  A.occupation_frequency.forEach(r => occStats[r.occupation] = r);
  const synMatrix = A.synergy_matrix || {{}};

  const defaultRoster = ['補師', '法師', '詩人', '賢者', '德魯伊', '法師', '流氓', '武僧'];
  const slotsBox = document.getElementById('builderSlots');

  function renderSelects(roster) {{
    slotsBox.innerHTML = roster.map((c, idx) => `
      <div class="slot-box" style="${{idx < 5 ? 'border-color:rgba(56,189,248,.45)' : ''}}">
        <div class="sub" style="font-size:0.76rem">${{idx < 5 ? '預設先發 #' + (idx + 1) : '預設替補 #' + (idx + 1)}}</div>
        <div id="slotIco_${{idx}}" style="margin:6px 0">${{ico(c)}}</div>
        <select class="builder-sel" data-idx="${{idx}}">
          ${{allOccs.map(o => `<option value="${{esc(o)}}" ${{o === c ? 'selected' : ''}}>${{esc(o)}}</option>`).join('')}}
        </select>
      </div>
    `).join('');
    document.querySelectorAll('.builder-sel').forEach(sel => {{
      sel.onchange = () => evaluateCurrentBuilder();
    }});
  }}

  function scoreRoster(occs) {{
    const counts = {{}};
    occs.forEach(o => counts[o] = (counts[o] || 0) + 1);
    const violations = Object.keys(counts).filter(o => counts[o] > 2);

    // Compute expected rank contribution from each distinct occupation's copy_1 / copy_2 bucket
    let rankSum = 0;
    let weightSum = 0;
    const notes = [];
    Object.entries(counts).forEach(([o, cnt]) => {{
      const st = occStats[o];
      if (!st) return;
      const bucket = cnt >= 2 ? st.copy_2 : st.copy_1;
      const bRank = (bucket && bucket.teams >= 2 && bucket.avg_rank) ? bucket.avg_rank : st.avg_rank;
      const w = cnt >= 2 ? 2.2 : 1.0;
      rankSum += bRank * w;
      weightSum += w;
      if (cnt === 2 && st.double_rank_gain !== null && st.double_rank_gain >= 5) {{
        notes.push({{ type: 'pos', text: `✅ 【${{o}}×2 雙職業配置】大數據雙職業均排 #${{bucket.avg_rank}}（比單職業提升 +${{st.double_rank_gain}} 名）` }});
      }} else if (cnt === 2 && st.double_rank_gain !== null && st.double_rank_gain <= -5) {{
        notes.push({{ type: 'neg', text: `⚠️ 【${{o}}×2 雙職業警告】大數據顯示帶 2 隻【${{o}}】均排掉至 #${{bucket.avg_rank}}（${{st.double_rank_gain}} 名），建議改為單職業騰出席次` }});
      }} else if (cnt === 1 && o === '舞孃') {{
        notes.push({{ type: 'neg', text: `⚠️ 【單帶舞孃陷阱】本場 100 隊單帶舞孃均排僅 #111.7（不帶均排 #89.0），除非與詩人雙綁定否則建議換為德魯伊/武僧/刺客` }});
      }}
    }});

    const distinct = Object.keys(counts);
    const goodSyns = [];
    const subConflicts = [];
    let synBonus = 0;
    for (let i = 0; i < distinct.length; i++) {{
      for (let j = i + 1; j < distinct.length; j++) {{
        const a = distinct[i], b = distinct[j];
        const lift = (synMatrix[a] && synMatrix[a][b]) ? synMatrix[a][b] : 1.0;
        if (lift >= 1.15) {{
          goodSyns.push(`${{a}}＋${{b}} (${{lift}}x)`);
          synBonus += (lift - 1.0) * 6.5;
        }} else if (lift <= 0.82) {{
          subConflicts.push(`${{a}} vs ${{b}} (Lift ${{lift}}x)`);
          synBonus -= (0.85 - lift) * 5.0;
        }}
      }}
    }}

    const baseExpectedRank = weightSum ? (rankSum / weightSum) : ov.overall_avg_rank;
    const estRank = Math.max(1, Math.min(200, Math.round((baseExpectedRank - synBonus) * 10) / 10));
    return {{ counts, violations, estRank, notes, goodSyns, subConflicts }};
  }}

  function evaluateCurrentBuilder() {{
    const occs = [...document.querySelectorAll('.builder-sel')].map(s => s.value);
    occs.forEach((c, idx) => {{
      const box = document.getElementById('slotIco_' + idx);
      if (box) box.innerHTML = ico(c);
    }});

    const res = scoreRoster(occs);
    const dpCount = Object.values(res.counts).filter(v => v === 2).length;

    // Find best 1-slot swap suggestion
    let bestSwap = null;
    let bestRankAfter = res.estRank;
    for (let i = 0; i < 8; i++) {{
      const cur = occs[i];
      for (const cand of allOccs) {{
        if (cand === cur) continue;
        const trial = [...occs];
        trial[i] = cand;
        const tRes = scoreRoster(trial);
        if (tRes.violations.length === 0 && tRes.estRank < bestRankAfter - 0.8) {{
          bestRankAfter = tRes.estRank;
          bestSwap = {{ slot: i + 1, from: cur, to: cand, newRank: tRes.estRank, gain: Math.round((res.estRank - tRes.estRank) * 10) / 10 }};
        }}
      }}
    }}

    // Find Top 5 most similar real leaderboard teams (multiset intersection)
    const simTeams = A.raw_data.map(t => {{
      const tCounts = {{}};
      (t.occupations || []).forEach(o => tCounts[o] = (tCounts[o] || 0) + 1);
      let overlap = 0;
      Object.keys(res.counts).forEach(o => {{
        overlap += Math.min(res.counts[o] || 0, tCounts[o] || 0);
      }});
      return {{ team: t, overlap }};
    }}).sort((a, b) => (b.overlap - a.overlap) || (a.team.rank - b.team.rank)).slice(0, 5);

    const grade = res.violations.length ? '❌ 違規（同職超過2名）' : res.estRank <= 78 ? '🏆 S+ 爭冠T0級' : res.estRank <= 90 ? '🔥 S 前段強勢級' : res.estRank <= 100 ? '⚖️ A 標準中堅級' : '⚠️ B 建議調整席次';

    document.getElementById('builderResult').innerHTML = `
      <div class="scout-box" style="margin-top:12px">
        <div class="kpis" style="margin-bottom:12px">
          <div class="kpi"><div class="lbl">賽制合規檢查</div><div class="val ${{res.violations.length?'neg':'pos'}}" style="font-size:1.1rem">${{res.violations.length ? '❌ ' + res.violations.join(',') + ' 超過2隻' : '✅ 符合同職 ≤ 2 規則'}}</div></div>
          <div class="kpi"><div class="lbl">陣容戰力評級</div><div class="val" style="font-size:1.15rem">${{grade}}</div></div>
          <div class="kpi"><div class="lbl">大數據預估強度落點</div><div class="val">#${{res.estRank}} <span class="sub" style="font-size:0.8rem">(全場均#100.5)</span></div></div>
          <div class="kpi"><div class="lbl">雙職業結構</div><div class="val" style="font-size:1.1rem">${{dpCount}} 組雙職業 (${{8 - dpCount * 2}} 單職)</div></div>
        </div>
        <div style="line-height:1.7;font-size:0.9rem">
          ${{res.notes.map(n => `<div class="${{n.type}}">${{n.text}}</div>`).join('')}}
          <div>🔗 <b>觸發常見綁定搭檔 (${{res.goodSyns.length}} 組)</b>：${{res.goodSyns.length ? res.goodSyns.map(s => `<span class="pill">${{esc(s)}}</span>`).join(' ') : '<span class="sub">無明顯高倍率綁定組</span>'}}</div>
          ${{res.subConflicts.length ? `<div style="margin-top:4px">⚡ <b>二選一搶位提醒</b>：${{res.subConflicts.map(s => `<span class="pill">${{esc(s)}}</span>`).join(' ')}}（通常強隊二選一即可）</div>` : ''}}
          ${{bestSwap ? `<div style="margin-top:8px;padding:8px 12px;background:rgba(74,222,128,.12);border:1px solid var(--green);border-radius:8px">💡 <b>AI 單格換角最佳化建議</b>：若將 <b>席次 #${{bestSwap.slot}}【${{esc(bestSwap.from)}}】→ 換成【${{esc(bestSwap.to)}}】</b>，預估強度落點可從 <b>#${{res.estRank}} 提升至 #${{bestSwap.newRank}}（+${{bestSwap.gain}} 名）</b>！</div>` : '<div style="margin-top:8px;color:var(--green)">✨ <b>目前 8 人配置已達局部最佳解，無需單格換角！</b></div>'}}
        </div>
        <h3 style="margin:14px 0 8px;font-size:0.98rem">🏆 排行榜上與你最相似的 Top 5 實戰參考戰隊</h3>
        <div class="table-wrap">
          <table>
            <thead><tr><th>相似度</th><th>排名</th><th>戰隊名稱</th><th>積分</th><th>該隊 8 人名單</th></tr></thead>
            <tbody>
              ${{simTeams.map(({{team, overlap}}) => `<tr>
                <td><span class="q-tag ${{overlap>=7?'q-t0':overlap>=6?'q-dark':'q-std'}}"><b>${{overlap}} / 8 相同</b></span></td>
                <td><b>#${{team.rank}}</b></td>
                <td>${{esc(team.team_name)}}</td>
                <td>${{team.score ?? '-'}}</td>
                <td>${{team.occupations.map(o => `<span class="pill">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')}}</td>
              </tr>`).join('')}}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }}

  renderSelects(defaultRoster);
  evaluateCurrentBuilder();

  document.querySelectorAll('.preset-btn').forEach(btn => {{
    if (!btn.dataset.preset) return;
    btn.onclick = () => {{
      const arr = btn.dataset.preset.split(',');
      renderSelects(arr);
      evaluateCurrentBuilder();
    }};
  }});
}})();

// Universal Click-to-Zoom & Pan Lightbox Controller
(function initZoomLightbox() {{
  const modal = document.getElementById('imgZoomModal');
  const stage = document.getElementById('zoomStage');
  const img = document.getElementById('zoomModalImg');
  const titleEl = document.getElementById('zoomModalTitle');
  const pctEl = document.getElementById('zoomPctLabel');
  const dlBtn = document.getElementById('btnZoomDownload');
  if (!modal || !stage || !img) return;

  let scale = 1, tx = 0, ty = 0, dragging = false, startX = 0, startY = 0;

  function applyTransform() {{
    img.style.transform = `translate(${{tx}}px, ${{ty}}px) scale(${{scale}})`;
    if (pctEl) pctEl.textContent = Math.round(scale * 100) + '%';
  }}

  function openZoom(src, title) {{
    img.src = src;
    if (titleEl) titleEl.textContent = title || '統計圖卡放大檢視';
    if (dlBtn) {{
      dlBtn.href = src;
      dlBtn.download = (title || 'chart').replace(/[^\w\u4e00-\u9fff\-]+/g, '_') + '.png';
    }}
    scale = 1; tx = 0; ty = 0;
    applyTransform();
    modal.classList.add('open');
  }}

  function closeZoom() {{
    modal.classList.remove('open');
  }}

  document.addEventListener('click', ev => {{
    const t = ev.target.closest('.zoomable-img');
    if (t && t.src) {{
      openZoom(t.src, t.dataset.zoomTitle || t.alt);
    }}
  }});

  document.getElementById('btnZoomIn').onclick = () => {{ scale = Math.min(5, +(scale + 0.25).toFixed(2)); applyTransform(); }};
  document.getElementById('btnZoomOut').onclick = () => {{ scale = Math.max(0.5, +(scale - 0.25).toFixed(2)); applyTransform(); }};
  document.getElementById('btnZoomReset').onclick = () => {{ scale = 1; tx = 0; ty = 0; applyTransform(); }};
  document.getElementById('btnZoomClose').onclick = closeZoom;

  stage.addEventListener('wheel', ev => {{
    ev.preventDefault();
    const delta = ev.deltaY < 0 ? 0.2 : -0.2;
    scale = Math.max(0.5, Math.min(5, +(scale + delta).toFixed(2)));
    applyTransform();
  }}, {{ passive: false }});

  stage.addEventListener('mousedown', ev => {{
    if (ev.button !== 0) return;
    dragging = true;
    startX = ev.clientX - tx;
    startY = ev.clientY - ty;
    stage.classList.add('dragging');
  }});
  window.addEventListener('mousemove', ev => {{
    if (!dragging) return;
    tx = ev.clientX - startX;
    ty = ev.clientY - startY;
    applyTransform();
  }});
  window.addEventListener('mouseup', () => {{
    dragging = false;
    stage.classList.remove('dragging');
  }});
  stage.addEventListener('dblclick', () => {{
    if (scale > 1.05) {{ scale = 1; tx = 0; ty = 0; }}
    else {{ scale = 2.2; }}
    applyTransform();
  }});
  window.addEventListener('keydown', ev => {{
    if (ev.key === 'Escape' && modal.classList.contains('open')) closeZoom();
  }});
}})();
</script>
</body>
</html>
"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    return out
