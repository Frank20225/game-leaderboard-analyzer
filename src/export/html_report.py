"""Zero-dependency single-file interactive HTML report v2 (Tournament Roster Edition)."""

from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _encode_png_b64(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def generate_html_report(
    analytics: dict[str, Any],
    icon_paths_by_name: dict[str, str],
    output_path: str | Path,
    cards_dir: str | Path | None = None,
) -> Path:
    """Build a self-contained single-file interactive HTML report for tournament roster analysis."""
    icons_b64 = {
        name: _encode_png_b64(p) for name, p in icon_paths_by_name.items() if p and Path(p).is_file()
    }
    embedded_cards: dict[str, str] = {}
    if cards_dir is not None:
        cdir = Path(cards_dir)
        dp_card = cdir / "02_copy_count_impact.png"
        if dp_card.is_file():
            embedded_cards["copy_impact"] = _encode_png_b64(dp_card)

    embedded_payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "analytics": {k: v for k, v in analytics.items() if k != "recognition_errors"},
        "icons": icons_b64,
        "cards": embedded_cards,
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
    <button class="tab active" data-tab="raw">1. 完整排行榜查詢 &amp; 對手秒查</button>
    <button class="tab" data-tab="quad">2. Meta 四象限＆出場率</button>
    <button class="tab" data-tab="doubles">3. 0/1/2隻 雙開效益</button>
    <button class="tab" data-tab="tiers">4. 各名次區間趨勢＆雙開結構</button>
    <button class="tab" data-tab="synergy">5. 協同/互斥＆建隊流派</button>
    <button class="tab" data-tab="builder">🧪 6. 我方 8 人名單健檢器</button>
  </nav>

  <section id="tab-raw" class="panel active">
    <div class="card">
      <h2>完整排行榜資料查詢 ＆ 實戰對手秒查（免打字／泰文友善）</h2>
      <div class="sub" style="background:#0f172a;border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:12px;line-height:1.6">
        🎯 <b>實戰排到泰文或無法複製的對手怎麼查？</b><br>
        1️⃣ 先點下方<b>「語系秒篩」</b>（例如點 <code>🇹🇭 泰文隊</code> 立即縮小範圍）＋<b>「外觀特徵」</b>（含數字 / 字數長短），3 秒內免打泰文即可鎖定對手！<br>
        2️⃣ <b>點擊表格任一戰隊列</b>，會立即展開該隊的<b>【🎯 BO5 五局（5v5 / 1v1 / 3v3 / 2v2）出場拆陣推演 ＆ 弱點針對情報卡】</b>。
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
          <option value="">篩選雙開組數（全部）</option>
          <option value="0">0 雙開（8異職）</option>
          <option value="1">1 組雙開</option>
          <option value="2">2 組雙開</option>
          <option value="3">3+ 組雙開</option>
        </select>
        <span class="sub" id="rawCount"></span>
      </div>
      <div class="table-wrap"><table id="rawTable"></table></div>
    </div>
  </section>

  <section id="tab-quad" class="panel">
    <div class="card">
      <h2>Meta 四象限戰略圖（X＝隊伍攜帶率，Y＝平均排名越上越強）</h2>
      <div class="quad-wrap" id="quadSvgBox"></div>
    </div>
    <div class="card">
      <h2>職業環境總表</h2>
      <div class="sub" style="background:#0f172a;border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:12px;line-height:1.65">
        💡 <b>指標說明：</b><br>
        • <b>高排 Lift（優勢比）</b>＝前段班（Top 50 / Top 10）攜帶率 ÷ 全體攜帶率。<b>&gt; 1.0x</b> 代表高端局更偏愛（越高越偏向高端黑馬）；<b>≈ 1.0x</b> 代表各分段普及度差不多；<b>&lt; 1.0x</b> 代表偏中後段帶得多。<br>
        • <b>Spearman r（排名相關係數，-1 ～ +1）</b>＝衡量「帶越多隻該職業，名次是否越靠前」。因名次數字越小越強，<b>負值（綠色，如 -0.20）代表強勢職業</b>；接近 0 代表與名次無明顯關聯；<b>正值（紅色）代表偏向後段班</b>。
      </div>
      <div class="table-wrap"><table id="occTable"></table></div>
    </div>
  </section>

  <section id="tab-doubles" class="panel">
    <div class="card">
      <h2>0 隻 vs 1 隻（單帶）vs 2 隻（滿編雙開）平均排名對比</h2>
      <p class="sub">賽制規定 8 人名單同職業最多 2 名。圖中越靠<b>右側</b>代表平均排名越高，紅菱（帶 2 隻）明顯在藍方（帶 1 隻）右邊即代表該職業非常值得雙開！</p>
      <div id="copyChartWrap" style="margin:12px 0"></div>
      <details style="margin-top:12px">
        <summary style="cursor:pointer;color:var(--accent);font-weight:600">📋 展開查看 0 / 1 / 2 隻原始數值明細表</summary>
        <div class="table-wrap" style="margin-top:10px"><table id="copyTable"></table></div>
      </details>
    </div>
  </section>

  <section id="tab-tiers" class="panel">
    <div class="card">
      <h2>各名次區間的職業熱門度（前段班 vs 中後段班差在哪？）</h2>
      <p class="sub">💡 <b>怎麼看？</b>橫著從左往右看（左邊是前 10 名、右邊是後段班）：<b>越左邊數字越高（底色越亮）</b>＝頂尖強隊越愛用；<b>左右差不多</b>＝各分段都會帶的標配；<b>越右邊越高</b>＝中後段隊伍帶得較多。</p>
      <div class="table-wrap"><table id="tierHeatTable"></table></div>
    </div>
    <div class="card">
      <h2>戰隊「雙開組數」策略結構（8 異職 vs 1 / 2 / 3 組雙開）</h2>
      <div class="table-wrap"><table id="dpStructTable"></table></div>
    </div>
  </section>

  <section id="tab-synergy" class="panel">
    <div class="card">
      <h2>主流 8 人建隊流派骨架（Roster Archetypes）</h2>
      <div class="table-wrap"><table id="archTable"></table></div>
    </div>
    <div class="card">
      <h2>強烈綁定搭檔（Synergy Lift ≥ 1.15）</h2>
      <p class="sub">排除熱門職相乘造成的假協同：Lift 越高代表兩個職業越常「成套出現」。</p>
      <div class="table-wrap"><table id="synTable"></table></div>
    </div>
    <div class="card">
      <h2>同定位互斥替代（Synergy Lift ≤ 0.85）</h2>
      <p class="sub">帶了 A 就明顯較少帶 B，代表這兩個職業常在搶同一個名單席次。</p>
      <div class="table-wrap"><table id="subTable"></table></div>
    </div>
    <div class="card">
      <h2>熱門三職業組合（每隊去重）</h2>
      <div class="table-wrap"><table id="tripleTable"></table></div>
    </div>
  </section>

  <section id="tab-builder" class="panel">
    <div class="card">
      <h2>🧪 我方 8 人名單健檢器 ＆ AI 換角最佳化模擬</h2>
      <p class="sub">依據本場 200 隊大數據（0/1/2 隻平均名次、Synergy Lift 協同矩陣與 BO5 鎖人規則），即時評估你的 8 人名單強度、抓出互斥陷阱，並比對排行榜上最相似的實戰強隊！</p>
      <div class="filter-bar" style="margin-top:10px">
        <span class="sub">一鍵套用大數據推薦陣容：</span>
        <button class="preset-btn" data-preset="補師,法師,詩人,賢者,德魯伊,法師,流氓,武僧">🔥 推薦一：雙法跨局控場陣（前5預設先發＋後3替補輪轉，均排 #57.6）</button>
        <button class="preset-btn" data-preset="補師,法師,詩人,賢者,德魯伊,流氓,騎士,武僧">👑 推薦二：8 異職全能冠軍陣（5v5德魯伊AOE＋1v1賢/流/騎/武）</button>
        <button class="preset-btn" data-preset="補師,法師,詩人,賢者,德魯伊,詩人,流氓,武僧">🎵 推薦三：雙詩人雙流派輪轉陣（分攤3v3/2v2或一輔一輸出，均排 #87.8）</button>
      </div>
      <div class="builder-grid" id="builderSlots"></div>
      <div id="builderResult"></div>
    </div>
  </section>

  <footer>Game Leaderboard Analyzer v2 — Tournament Roster Strategy Report</footer>
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
  ['最強勢雙開結構', bestDP ? `${{bestDP.label}} (均#${{bestDP.avg_rank}})` : '-'],
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
    <text x="${{W-padR-8}}" y="${{padT+18}}" text-anchor="end" fill="#38bdf8" font-size="12" font-weight="700">★ T0 版本核心（高攜帶 × 高排）</text>
    <text x="${{padL+8}}" y="${{padT+18}}" text-anchor="start" fill="#4ade80" font-size="12" font-weight="700">⚡ 高端奇兵 / 黑馬</text>
    <text x="${{W-padR-8}}" y="${{H-padB-10}}" text-anchor="end" fill="#fbbf24" font-size="11.5" font-weight="700">⚖️ 普及標配</text>
    <text x="${{padL+8}}" y="${{H-padB-10}}" text-anchor="start" fill="#94a3b8" font-size="11.5" font-weight="700">🧊 冷門職</text>
    <text x="${{W/2}}" y="${{H-12}}" text-anchor="middle" fill="#cbd5e1" font-size="12">隊伍攜帶率 (%) →</text>
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

document.getElementById('occTable').innerHTML =
  '<thead><tr><th>職業</th><th>Meta 象限</th><th>攜帶率(隊數)</th><th>總人次佔比</th><th>雙開率(隊數)</th><th>平均排名</th><th title="前段班攜帶率 ÷ 全體攜帶率，>1.0x 代表高端局更偏愛">高排Lift ⓘ</th><th title="負值代表帶越多隻排名越高，正值偏向後段班">Spearman r ⓘ</th></tr></thead><tbody>' +
  A.occupation_frequency.map(r => `<tr><td><span class="lbl-flex">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td><td><span class="q-tag ${{qCls(r.quadrant)}}">${{esc(r.quadrant)}}</span></td><td><b>${{pct(r.team_presence_rate)}}</b> (${{r.team_count}}隊)</td><td>${{pct(r.slot_rate)}} (${{r.slot_count}})</td><td>${{pct(r.double_pick_rate)}} (${{r.double_pick_teams}}隊)</td><td><b>#${{r.avg_rank}}</b></td><td>${{r.top_tier_lift}}x</td><td class="${{r.spearman_r<=-0.15?'pos':r.spearman_r>=0.15?'neg':''}}">${{r.spearman_r}}</td></tr>`).join('') +
  '</tbody>';

const CARDS = DATA.cards || {{}};
if (CARDS.copy_impact) {{
  document.getElementById('copyChartWrap').innerHTML = `<img src="${{CARDS.copy_impact}}" alt="0隻 vs 1隻 vs 2隻 平均排名影響" style="width:100%;max-width:1100px;display:block;margin:0 auto;border-radius:12px;border:1px solid var(--border)">`;
}}

const fmtB = b => b && b.teams ? `<b>#${{b.avg_rank}}</b> <span class="sub">(${{b.teams}}隊${{b.low_sample?', n<5':''}})</span>` : '<span class="sub">-</span>';
document.getElementById('copyTable').innerHTML =
  '<thead><tr><th>職業</th><th>帶 0 隻（不帶）</th><th>帶 1 隻（單帶）</th><th>帶 2 隻（滿編雙開）</th><th>雙開名次提升 (1→2)</th></tr></thead><tbody>' +
  A.occupation_frequency.map(r => {{
    const g = r.double_rank_gain;
    const gHtml = g === null || g === undefined ? '-' : `<span class="${{g>=0?'pos':'neg'}}">${{g>=0?'+':''}}${{g}} 名</span>`;
    return `<tr><td><span class="lbl-flex">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td><td>${{fmtB(r.copy_0)}}</td><td>${{fmtB(r.copy_1)}}</td><td>${{fmtB(r.copy_2)}}</td><td>${{gHtml}}</td></tr>`;
  }}).join('') + '</tbody>';

const tiers = A.ranking_analysis.tiers;
const firstTierKey = tiers.length ? tiers[0].tier : '';
const lastTierKey = tiers.length ? tiers[tiers.length - 1].tier : '';
document.getElementById('tierHeatTable').innerHTML =
  `<thead><tr><th>職業</th><th>全體平均</th>${{tiers.map(t => `<th>${{esc(t.tier)}} 名<br><span class="sub">(${{t.team_count}}隊)</span></th>`).join('')}}<th>前段 vs 後段差</th><th>平均排名</th></tr></thead><tbody>` +
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
  '<thead><tr><th>雙開組數配置</th><th>隊伍數</th><th>佔比</th><th>平均排名</th><th>中位排名</th><th>最高排名</th><th>Top 10 隊數</th></tr></thead><tbody>' +
  A.double_pick_structure.map(d => `<tr><td><b>${{esc(d.label)}}</b></td><td>${{d.team_count}}</td><td>${{pct(d.team_rate)}}</td><td><b>#${{d.avg_rank}}</b></td><td>#${{d.median_rank}}</td><td>#${{d.best_rank}}</td><td>${{d.top10_count}}</td></tr>`).join('') + '</tbody>';

document.getElementById('archTable').innerHTML =
  '<thead><tr><th>流派</th><th>隊數(佔比)</th><th>均排 / 最高</th><th>平均雙開</th><th>核心必帶職</th><th>常見搖擺位</th><th>代表戰隊</th></tr></thead><tbody>' +
  (A.roster_archetypes || []).map(a => `<tr><td><b>${{esc(a.archetype_id)}}</b> ${{esc(a.archetype_name)}}</td><td>${{a.team_count}} (${{pct(a.team_rate)}})</td><td><b>#${{a.avg_rank}}</b> / #${{a.best_rank}}</td><td>${{a.avg_double_picks}}</td><td>${{esc(a.core_classes)}}</td><td class="sub">${{esc(a.flex_classes)}}</td><td class="sub">${{esc(a.sample_teams)}}</td></tr>`).join('') + '</tbody>';

const fillSyn = (id, rows) => {{
  document.getElementById(id).innerHTML =
    '<thead><tr><th>組合</th><th>協同 Lift</th><th>實際佔比(隊數)</th><th>隨機預期</th><th>平均排名</th><th>代表戰隊</th></tr></thead><tbody>' +
    (rows.length ? rows.map(r => `<tr><td><b>${{esc(r.combination)}}</b></td><td class="${{r.synergy_lift>=1.15?'pos':'neg'}}">${{r.synergy_lift}}x</td><td>${{pct(r.team_rate)}} (${{r.team_count}}隊)</td><td>${{pct(r.expected_rate)}}</td><td>${{r.avg_rank ? '#'+r.avg_rank : '-'}}</td><td class="sub">${{esc(r.sample_teams)}}</td></tr>`).join('') : '<tr><td colspan="6" class="sub">無明顯項目</td></tr>') + '</tbody>';
}};
fillSyn('synTable', A.synergy_pairs || []);
fillSyn('subTable', A.substitution_pairs || []);

document.getElementById('tripleTable').innerHTML =
  '<thead><tr><th>三職業組合</th><th>隊數</th><th>佔比</th><th>平均排名</th><th>Top 10 佔比</th><th>代表戰隊</th></tr></thead><tbody>' +
  (A.triple_combinations || []).slice(0, 35).map(r => `<tr><td><b>${{esc(r.combination)}}</b></td><td>${{r.team_count}}</td><td>${{pct(r.team_rate)}}</td><td>#${{r.avg_rank}}</td><td>${{pct(r.top10_rate)}}</td><td class="sub">${{esc(r.sample_teams)}}</td></tr>`).join('') + '</tbody>';

// BO5 Lineup Predictor & Opponent Scouting Card Generator (Aligned with Verified Valkyrie Cup Meta)
function buildScoutCardHtml(team) {{
  const rawOccs = (team.occupations || []).filter(Boolean);
  // Create 8 indexed player slots preserving left-to-right order (Slot 1..5 = default 5v5 starters, Slot 6..8 = bench)
  const players = rawOccs.map((occ, i) => ({{ id: i + 1, occ, isDefaultStarter: i < 5 }}));
  const counts = {{}};
  rawOccs.forEach(o => counts[o] = (counts[o] || 0) + 1);
  const doubles = Object.keys(counts).filter(o => counts[o] >= 2);

  // --- 1. Predict G2 (1v1 Solo Duel) FIRST because G2 player is locked out of G3 (3v3) & G4 (2v2) ---
  // Verified 1v1 frequency order: 賢者 (1st) > 流氓 (2nd) > 騎士 (3rd) > 武僧 (4th)
  const g2Priority = ['賢者', '流氓', '騎士', '武僧', '刺客', '德魯伊', '詩人', '舞孃', '煉金', '十字', '鐵匠', '獵人', '法師'];
  let g2Candidates = [];
  for (const candOcc of g2Priority) {{
    const matchingPlayers = players.filter(p => p.occ === candOcc);
    if (matchingPlayers.length > 0) {{
      // If a team has 2 copies of this class, prefer sending the bench copy (Slot 6..8) so the starter copy can play G1->G4
      const chosen = matchingPlayers[matchingPlayers.length - 1];
      g2Candidates.push(chosen);
    }}
  }}
  const g2Player = g2Candidates[0] || players[0] || {{ id: 1, occ: '未知' }};
  const g2AltPlayer = g2Candidates.find(p => p.occ !== g2Player.occ) || null;
  let g2Reason = '';
  if (['賢者', '流氓', '騎士', '武僧'].includes(g2Player.occ)) {{
    const rankIdx = ['賢者', '流氓', '騎士', '武僧'].indexOf(g2Player.occ) + 1;
    g2Reason = `依實戰 1v1 出場率（賢者＞流氓＞騎士＞武僧），首選第 ${{rankIdx}} 順位單挑強職【${{g2Player.occ}}】` +
      (counts[g2Player.occ] >= 2 ? `（且該隊有雙開 ${{g2Player.occ}}×2，鎖掉 1 隻後 G3/G4 仍有另 1 隻可用）` : `（出戰後將被禁選，無法打 G3 3v3 與 G4 2v2）`) +
      (g2AltPlayer && ['賢者', '流氓', '騎士', '武僧'].includes(g2AltPlayer.occ) ? `；次選防備：【${{g2AltPlayer.occ}}】。` : '。');
  }} else {{
    g2Reason = `該隊未攜帶賢/流/騎/武四大單挑職，預計派出【${{g2Player.occ}}】打 G2 1v1。`;
  }}

  // --- 2. Predict G1 & G5 (5v5 Teamfight) ---
  // Verified 5v5 rules:
  // - Slots 1..5 are the in-game default starters, but teams rarely field 2 法師 or 2 補師 in the same 5v5
  //   (法師×2 overlaps control and loses to 德魯伊 in pure AOE; 補師×2 splits 1 to G1->G4 and 1 to G3; 詩人×2 rarely co-starts unless 1 supp + 1 DPS).
  // - Priority in 5v5: 補師 (1) > 法師 (1, control) > 詩人/舞孃 (support) > 德魯伊 (top 5v5 AOE + control) / 賢者 / 流氓 / 騎士 / 武僧 / 刺客 / 煉金 (coat protection).
  const g1Priority = ['補師', '法師', '詩人', '德魯伊', '賢者', '舞孃', '流氓', '騎士', '武僧', '刺客', '煉金', '十字', '鐵匠', '獵人'];
  const g1Players = [];
  const g1OccCounts = {{}};

  // Start from default starters (Slot 1..5) that don't violate single-copy-in-5v5 for 補師/法師/詩人
  for (const p of players.filter(x => x.isDefaultStarter)) {{
    const cap = ['補師', '法師', '詩人'].includes(p.occ) ? 1 : 2;
    if ((g1OccCounts[p.occ] || 0) < cap && g1Players.length < 5) {{
      g1Players.push(p);
      g1OccCounts[p.occ] = (g1OccCounts[p.occ] || 0) + 1;
    }}
  }}
  // Ensure 補師 and 法師 are swapped in from bench (Slot 6..8) if they were hidden on the bench!
  for (const mustOcc of ['補師', '法師']) {{
    if (!g1OccCounts[mustOcc] && counts[mustOcc]) {{
      const benchMust = players.find(p => p.occ === mustOcc && !g1Players.includes(p));
      if (benchMust) {{
        if (g1Players.length >= 5) {{
          const dropped = g1Players.pop();
          g1OccCounts[dropped.occ]--;
        }}
        g1Players.unshift(benchMust);
        g1OccCounts[mustOcc] = 1;
      }}
    }}
  }}
  // Fill any remaining slots up to 5 from bench using 5v5 priority (preferring single copy first)
  const benchCand = players
    .filter(p => !g1Players.includes(p))
    .sort((a, b) => g1Priority.indexOf(a.occ) - g1Priority.indexOf(b.occ));
  for (const p of benchCand) {{
    if (g1Players.length < 5 && !(g1OccCounts[p.occ] || 0)) {{
      g1Players.push(p);
      g1OccCounts[p.occ] = 1;
    }}
  }}
  for (const p of benchCand) {{
    if (g1Players.length < 5 && !g1Players.includes(p)) {{
      g1Players.push(p);
      g1OccCounts[p.occ] = (g1OccCounts[p.occ] || 0) + 1;
    }}
  }}

  // --- 3. Predict G3 (3v3 Small Teamfight — excludes G2 player!) ---
  // Verified 3v3 formula:
  // - Seat 1: MUST be 補師 (德魯伊 does NOT replace 補師). If team has 補師×2, use the 2nd 補師 (who did NOT play G1) so G1's 補師 locks into G4 Seat 1!
  // - Seat 2 (Support / Control): 詩人 > 舞孃 > 法師 > 煉金. (If team has 2 copies, prefer the copy that did NOT play G1 so G1's copy stays eligible for G4 Seat 1!)
  // - Seat 3 (Main DPS): 詩人(輸出流)/舞孃(輸出流) > 賢者 > 流氓 > 騎士/刺客/武僧 > 德魯伊.
  const eligibleG3 = players.filter(p => p.id !== g2Player.id);
  const g3Players = [];

  // G3 Seat 1: 補師
  const healers = eligibleG3.filter(p => p.occ === '補師');
  if (healers.length >= 2) {{
    // Pick the healer who did NOT play G1 so the G1 healer is saved for G4 Seat 1!
    const nonG1Healer = healers.find(h => !g1Players.includes(h)) || healers[1];
    g3Players.push(nonG1Healer);
  }} else if (healers.length === 1) {{
    g3Players.push(healers[0]);
  }}

  // G3 Seat 2: Support / Control (詩人 > 舞孃 > 法師 > 煉金)
  const suppOrder = ['詩人', '舞孃', '法師', '煉金', '德魯伊', '賢者'];
  for (const sOcc of suppOrder) {{
    const cands = eligibleG3.filter(p => p.occ === sOcc && !g3Players.includes(p));
    if (cands.length > 0) {{
      // If there's a copy that didn't play G1 (e.g. 2nd 詩人 or 2nd 法師), use it in G3 so the G1 copy locks into G4 Seat 1!
      const preferNonG1 = cands.find(c => !g1Players.includes(c)) || cands[0];
      g3Players.push(preferNonG1);
      break;
    }}
  }}

  // G3 Seat 3: Main DPS (詩人/舞孃[輸出流] > 賢者 > 流氓 > 騎士 > 刺客 > 武僧 > 德魯伊)
  const dpsOrder = ['詩人', '舞孃', '賢者', '流氓', '騎士', '刺客', '武僧', '德魯伊', '法師', '煉金', '鐵匠', '十字', '獵人'];
  for (const dOcc of dpsOrder) {{
    const cands = eligibleG3.filter(p => p.occ === dOcc && !g3Players.includes(p));
    if (cands.length > 0) {{
      // Avoid duplicate class inside the same 3v3 trio unless necessary
      if (!g3Players.some(x => x.occ === dOcc)) {{
        g3Players.push(cands[0]);
        break;
      }}
    }}
  }}
  for (const p of eligibleG3) {{
    if (g3Players.length < 3 && !g3Players.includes(p)) g3Players.push(p);
  }}

  // --- 4. Predict G4 (2v2 Duo — Strict Lock & Opponent Healer-Ban Logic!) ---
  // Rule:
  // - Seat 1 MUST be someone who played G1 (5v5) and did NOT play G2 (1v1) or G3 (3v3).
  // - Seat 2 MUST be picked from G3 (3v3) AFTER the opponent bans 1 G3 player (Opponent almost 100% bans G3's 補師!).
  const g4Seat1Pool = g1Players.filter(p => p.id !== g2Player.id && !g3Players.includes(p));
  const g3Banned = g3Players.find(p => p.occ === '補師') || g3Players[0];
  const g4Seat2Pool = g3Players.filter(p => p !== g3Banned);

  // Pick optimal (1 Support/Control + 1 DPS) pair from Seat 1 Pool x Seat 2 Pool
  const g4PrioritySeat1 = ['補師', '詩人', '舞孃', '法師', '賢者', '流氓', '騎士', '武僧', '刺客', '德魯伊', '煉金'];
  const sortedSeat1 = [...g4Seat1Pool].sort((a, b) => g4PrioritySeat1.indexOf(a.occ) - g4PrioritySeat1.indexOf(b.occ));
  const g4Seat1 = sortedSeat1[0] || eligibleG3.find(p => !g3Players.includes(p)) || players[0];

  // If Seat 1 is a Support/Healer/Control (補師/法師/煉金), prefer a pure DPS from G3 for Seat 2; if Seat 1 is a DPS, prefer G3's Support (詩人/舞孃/法師) for Seat 2!
  const seat1IsSupp = ['補師', '法師', '煉金'].includes(g4Seat1.occ);
  let g4Seat2 = g4Seat2Pool[0] || g3Players[0];
  if (g4Seat2Pool.length >= 2) {{
    g4Seat2 = seat1IsSupp ? g4Seat2Pool[g4Seat2Pool.length - 1] : g4Seat2Pool[0];
  }}

  // --- 5. Verified Tactical Notes & Counter Tips ---
  const tips = [];
  const default5Str = players.slice(0, 5).map(p => p.occ).join(' / ');
  const bench3Str = players.slice(5, 8).map(p => p.occ).join(' / ');
  tips.push(`📋 <b>遊戲內預設席次</b>：前 5 格預設先發【<b>${{esc(default5Str)}}</b>】｜後 3 格替補【<b>${{esc(bench3Str || '無')}}</b>】（開賽前可替換）。`);

  if ((counts['補師'] || 0) >= 2) {{
    tips.push('💉 <b>雙補師跨局保底陣 (補師×2)</b>：該隊不會同場上雙補，而是讓「補師A 打 G1 5v5 後休息直鎖 G4 2v2 席次1」、「補師B 打 G3 3v3」——即使我方在 G4 Ban 掉 G3 的補師，對手 G4 (2v2) 依然保底有補師！');
  }} else if ((counts['補師'] || 0) === 1) {{
    tips.push('🚫 <b>單補師 G4 必無補弱點</b>：對手僅 1 隻補師（必打 G1 5v5 與 G3 3v3），進入 G4 (2v2) 時我方<b>務必 Ban 掉其 G3 的補師</b>，即可逼對手在 G4 打「無補師局（1輔/控＋1輸出）」！');
  }}
  if ((counts['法師'] || 0) >= 2) {{
    tips.push('❄️ <b>雙法師跨局控場輪轉 (法師×2)</b>：兩隻法師同場機率極低（同場控制重疊且純 AOE 不如德魯伊），實戰是將兩隻法師拆給 G1→G4 與 G3，達成 5v5 / 3v3 / 2v2 全場次控場不斷檔。');
  }}
  if ((counts['詩人'] || 0) >= 2) {{
    tips.push('🎵 <b>雙詩人靈活流派切換 (詩人×2)</b>：多數拆給 G3 與 G4 確保每局皆有頂尖輔助；若同場出戰則必定為「1 輔助流 ＋ 1 輸出流」。');
  }}
  if (counts['德魯伊']) {{
    tips.push('🌿 <b>德魯伊 5v5 大範圍壓制</b>：德魯伊的大範圍 AOE 傷害高於法師且具控場，在 G1 / G5 (5v5) 團戰最具威脅，我方需避免扎堆吃滿傷害。');
  }}
  if (counts['武僧']) {{
    tips.push('🥊 <b>武僧阿修羅減員威脅</b>：對手擁有武僧，核心戰術是用阿修羅一拳秒殺讓我方瞬間減員（亦可能於 G2 1v1 或 G3/G4 登場），需高度注意關鍵回合保人。');
  }}
  if (counts['煉金']) {{
    tips.push('⚗️ <b>煉金護貝＆毀裝干擾</b>：對手帶有煉金，能為隊友上護貝免疫裝備破壞，並以單體攻擊破壞我方裝備（輔助位出場序：詩人＞舞孃＞法師＞煉金）。');
  }}

  const renderPills = (arr, roleHints = {{}}) => arr.map(p => {{
    const o = typeof p === 'string' ? p : p.occ;
    const hint = roleHints[o] ? `<span class="sub" style="font-size:0.72rem;margin-left:2px">(${{esc(roleHints[o])}})</span>` : '';
    return `<span class="pill">${{ico(o)}}<span>${{esc(o)}}</span>${{hint}}</span>`;
  }}).join('');

  // Annotate 詩人 / 舞孃 / 法師 roles in G3 & G4
  const g3Hints = {{ '補師': '必帶純輔' }};
  if (g3Players[1]) g3Hints[g3Players[1].occ] = g3Players[1].occ === '法師' ? '控場' : g3Players[1].occ === '煉金' ? '護貝/毀裝' : '輔助流';
  if (g3Players[2]) g3Hints[g3Players[2].occ] = ['詩人', '舞孃'].includes(g3Players[2].occ) ? '可切輸出流' : '主力輸出';

  return `
  <div class="scout-box">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <div><b>🎯 #${{team.rank}} ${{esc(team.team_name)}} — 實戰情報卡 ＆ BO5 五局出場推演</b></div>
      <span class="sub">雙開輪轉核心：${{doubles.length ? doubles.map(d => `<b>${{d}}×2</b>`).join('、') : '無（8 異職）'}}</span>
    </div>
    <div style="margin-top:8px;font-size:0.85rem;line-height:1.65">
      ${{tips.map(t => `<div>• ${{t}}</div>`).join('')}}
    </div>
    <div class="scout-grid">
      <div class="bo5-card">
        <h4>G1 &amp; G5｜5v5 團戰預測</h4>
        <div>${{renderPills(g1Players, {{ '補師': '純輔', '法師': '控場', '德魯伊': 'AOE+控' }})}}</div>
        <div class="sub" style="font-size:0.78rem;margin-top:4px">優先級：補師＞法師(控)＞詩/舞(輔)＋德魯伊(AOE)/單體爆發；雙開職原則不同場重疊</div>
      </div>
      <div class="bo5-card">
        <h4>G2｜1v1 單挑鎖人預測 ⚠️</h4>
        <div>${{renderPills([g2Player])}} ${{g2AltPlayer && ['賢者','流氓','騎士','武僧'].includes(g2AltPlayer.occ) ? `<span class="sub" style="font-size:0.75rem">備案:</span> ${{renderPills([g2AltPlayer])}}` : ''}}</div>
        <div class="sub" style="font-size:0.78rem;margin-top:4px">${{esc(g2Reason)}}</div>
      </div>
      <div class="bo5-card">
        <h4>G3｜3v3 三人戰預測（禁 G2）</h4>
        <div>${{renderPills(g3Players, g3Hints)}}</div>
        <div class="sub" style="font-size:0.78rem;margin-top:4px">鐵律：1 補師＋1 輔/控(詩＞舞＞法＞煉)＋1 輸出(詩/舞＞賢＞流＞騎/刺/武＞德)</div>
      </div>
      <div class="bo5-card">
        <h4>G4｜2v2 雙人戰預測（含 Ban 位）</h4>
        <div>${{renderPills([g4Seat1, g4Seat2])}}</div>
        <div class="sub" style="font-size:0.78rem;margin-top:4px">
          • <b>席次1（G1未打G2/G3池）</b>：${{g4Seat1Pool.map(p=>p.occ).join(' / ') || g4Seat1.occ}} → 預計派 <b>${{esc(g4Seat1.occ)}}</b><br>
          • <b>席次2（G3排除必Ban【${{esc(g3Banned ? g3Banned.occ : '補師')}}】）</b>：從 ${{g4Seat2Pool.map(p=>p.occ).join(' / ')}} 派 <b>${{esc(g4Seat2.occ)}}</b>
        </div>
      </div>
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

  document.getElementById('rawCount').textContent = `顯示 ${{filtered.length}} / ${{A.raw_data.length}} 隊（點擊任一列展開 BO5 拆陣情報卡）`;
  const scriptBadge = s => s === 'th' ? '<span class="q-tag q-std" style="margin-right:6px">🇹🇭泰</span>' : s === 'zh' ? '<span class="q-tag q-t0" style="margin-right:6px">🇹🇼中</span>' : '<span class="q-tag q-low" style="margin-right:6px">🔤英</span>';

  let rowsHtml = '';
  filtered.forEach(r => {{
    const counts = {{}};
    (r.occupations || []).forEach(o => counts[o] = (counts[o] || 0) + 1);
    const isExp = expandedRanks.has(r.rank);
    rowsHtml += `<tr class="team-row" onclick="toggleScoutRow(${{r.rank}})">
      <td><b>#${{r.rank}}</b></td>
      <td>${{scriptBadge(detectScript(r.team_name))}}<b>${{esc(r.team_name)}}</b> <span class="sub" style="font-size:0.76rem">${{isExp ? '▲ 收合情報' : '▼ 展開 BO5 推演'}}</span></td>
      <td>${{r.score ?? '-'}}</td>
      <td>${{r.double_pick_count}} 組</td>
      <td>${{r.occupations.map(o => `<span class="pill ${{counts[o]>=2?'dp':''}}">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')}}</td>
    </tr>`;
    if (isExp) {{
      rowsHtml += `<tr><td colspan="5" style="padding:4px 10px 14px;background:#090e1a">${{buildScoutCardHtml(r)}}</td></tr>`;
    }}
  }});

  document.getElementById('rawTable').innerHTML =
    '<thead><tr><th>排名</th><th>戰隊名稱（點擊展開 BO5 情報卡）</th><th>積分</th><th>雙開</th><th>8 人名單配置（金色外框＝雙開職）</th></tr></thead><tbody>' +
    rowsHtml + '</tbody>';
}}
document.getElementById('searchInput').oninput = renderRaw;
occSel.onchange = renderRaw;
dpSel.onchange = renderRaw;
renderRaw();

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
        notes.push({{ type: 'pos', text: `✅ 【${{o}}×2 滿編雙開】大數據雙開均排 #${{bucket.avg_rank}}（比單帶提升 +${{st.double_rank_gain}} 名）` }});
      }} else if (cnt === 2 && st.double_rank_gain !== null && st.double_rank_gain <= -5) {{
        notes.push({{ type: 'neg', text: `⚠️ 【${{o}}×2 雙開警告】大數據顯示雙開【${{o}}】均排掉至 #${{bucket.avg_rank}}（${{st.double_rank_gain}} 名），建議改為單帶騰出席次` }});
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
          <div class="kpi"><div class="lbl">雙開結構</div><div class="val" style="font-size:1.1rem">${{dpCount}} 組雙開 (${{8 - dpCount * 2}} 異職)</div></div>
        </div>
        <div style="line-height:1.7;font-size:0.9rem">
          ${{res.notes.map(n => `<div class="${{n.type}}">${{n.text}}</div>`).join('')}}
          <div>🔗 <b>觸發高協同搭檔 (${{res.goodSyns.length}} 組)</b>：${{res.goodSyns.length ? res.goodSyns.map(s => `<span class="pill">${{esc(s)}}</span>`).join(' ') : '<span class="sub">無明顯高 Lift 綁定組</span>'}}</div>
          ${{res.subConflicts.length ? `<div style="margin-top:4px">⚡ <b>同定位搶位提醒</b>：${{res.subConflicts.map(s => `<span class="pill">${{esc(s)}}</span>`).join(' ')}}（通常強隊二選一即可）</div>` : ''}}
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
    btn.onclick = () => {{
      const arr = btn.dataset.preset.split(',');
      renderSelects(arr);
      evaluateCurrentBuilder();
    }};
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
