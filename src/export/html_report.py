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
  th {{ background: #0f172a; color: #cbd5e1; position: sticky; top: 0; }}
  tr:hover td {{ background: rgba(56,189,248,.06); }}
  .table-wrap {{ overflow-x: auto; max-height: 620px; }}
  .pill {{ display: inline-flex; align-items: center; gap: 4px; background: var(--card2); padding: 3px 8px; border-radius: 999px; font-size: 0.8rem; margin: 2px; }}
  .q-tag {{ padding: 2px 8px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; display: inline-block; }}
  .q-t0 {{ background: rgba(56,189,248,.2); color: #7dd3fc; }}
  .q-dark {{ background: rgba(74,222,128,.2); color: #86efac; }}
  .q-std {{ background: rgba(245,158,11,.2); color: #fde68a; }}
  .q-low {{ background: rgba(148,163,184,.2); color: #cbd5e1; }}
  .pos {{ color: var(--green); font-weight: 700; }}
  .neg {{ color: var(--red); font-weight: 700; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; align-items: center; }}
  input, select {{ background: #0b1120; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; font-size: 0.9rem; }}
  .quad-wrap {{ position: relative; width: 100%; overflow-x: auto; }}
  svg.quad {{ width: 100%; max-width: 960px; height: auto; display: block; margin: 0 auto; background: #0f172a; border-radius: 12px; border: 1px solid var(--border); }}
  .heat-cell {{ text-align: center; font-weight: 700; border-radius: 4px; }}
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
    <button class="tab active" data-tab="raw">1. 完整排行榜查詢</button>
    <button class="tab" data-tab="quad">2. Meta 四象限＆出場率</button>
    <button class="tab" data-tab="doubles">3. 0/1/2隻 雙開效益</button>
    <button class="tab" data-tab="tiers">4. 各名次區間趨勢＆雙開結構</button>
    <button class="tab" data-tab="synergy">5. 協同/互斥＆建隊流派</button>
  </nav>

  <section id="tab-raw" class="panel active">
    <div class="card">
      <h2>完整排行榜資料查詢</h2>
      <div class="controls">
        <input id="searchInput" type="search" placeholder="搜尋戰隊名稱或排名...">
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

const occSel = document.getElementById('occFilter');
A.occupation_frequency.forEach(r => {{ const o = document.createElement('option'); o.value = r.occupation; o.textContent = r.occupation; occSel.appendChild(o); }});
const dpSel = document.getElementById('dpFilter');

function renderRaw() {{
  const q = document.getElementById('searchInput').value.trim().toLowerCase();
  const occ = occSel.value;
  const dp = dpSel.value;
  const filtered = A.raw_data.filter(r => {{
    if (occ && !r.occupations.includes(occ)) return false;
    if (dp !== '') {{
      const dpc = r.double_pick_count || 0;
      if (dp === '3' ? dpc < 3 : dpc !== Number(dp)) return false;
    }}
    if (q && !(String(r.rank).includes(q) || (r.team_name || '').toLowerCase().includes(q) || (r.full_team_signature || '').toLowerCase().includes(q))) return false;
    return true;
  }});
  document.getElementById('rawCount').textContent = `顯示 ${{filtered.length}} / ${{A.raw_data.length}} 隊`;
  document.getElementById('rawTable').innerHTML =
    '<thead><tr><th>排名</th><th>戰隊名稱</th><th>積分</th><th>雙開</th><th>8 人名單配置</th></tr></thead><tbody>' +
    filtered.map(r => `<tr><td><b>#${{r.rank}}</b></td><td>${{esc(r.team_name)}}</td><td>${{r.score ?? '-'}}</td><td>${{r.double_pick_count}}</td><td>${{r.occupations.map(o => `<span class="pill">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')}}</td></tr>`).join('') + '</tbody>';
}}
document.getElementById('searchInput').oninput = renderRaw;
occSel.onchange = renderRaw;
dpSel.onchange = renderRaw;
renderRaw();
</script>
</body>
</html>
"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    return out
