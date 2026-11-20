"""Zero-dependency single-file interactive HTML report generator (share/report.html)."""

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
) -> Path:
    """Build a self-contained single-file interactive HTML report with embedded Base64 icons."""
    icons_b64 = {
        name: _encode_png_b64(p) for name, p in icon_paths_by_name.items() if p and Path(p).is_file()
    }
    embedded_payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "analytics": {k: v for k, v in analytics.items() if k != "recognition_errors"},
        "icons": icons_b64,
    }
    json_blob = json.dumps(embedded_payload, ensure_ascii=False).replace("</", "<\\/")
    safe_title = html.escape(analytics.get("report_title", "排位賽職業環境分析報告"))

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title}</title>
<style>
  :root {{
    --bg: #0f172a; --card: #1e293b; --card2: #263449; --text: #f8fafc;
    --muted: #94a3b8; --accent: #38bdf8; --accent2: #f59e0b; --green: #22c55e; --border: #334155;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "Microsoft JhengHei", "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
  .wrap {{ max-width: 1220px; margin: 0 auto; padding: 24px 16px 60px; }}
  header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 12px; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 22px; }}
  h1 {{ margin: 0; font-size: 1.65rem; }}
  .sub {{ color: var(--muted); font-size: 0.92rem; margin-top: 4px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 22px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }}
  .kpi .lbl {{ color: var(--muted); font-size: 0.82rem; }}
  .kpi .val {{ font-size: 1.55rem; font-weight: 700; margin-top: 4px; color: var(--accent); }}
  .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }}
  .tab {{ background: var(--card); color: var(--muted); border: 1px solid var(--border); padding: 9px 16px; border-radius: 999px; cursor: pointer; font-weight: 600; font-size: 0.92rem; transition: .15s; }}
  .tab.active {{ background: var(--accent); color: #0f172a; border-color: var(--accent); }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 18px; }}
  .card h2 {{ margin: 0 0 12px; font-size: 1.15rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }}
  .bar-row {{ display: grid; grid-template-columns: 160px 1fr 125px; align-items: center; gap: 10px; margin: 8px 0; }}
  .bar-label {{ display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.92rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .ico {{ width: 28px; height: 28px; border-radius: 50%; object-fit: cover; flex-shrink: 0; border: 1px solid rgba(255,255,255,.15); }}
  .ico-sm {{ width: 24px; height: 24px; border-radius: 50%; object-fit: cover; vertical-align: middle; }}
  .track {{ background: #0f172a; border-radius: 999px; height: 20px; overflow: hidden; position: relative; }}
  .fill {{ height: 100%; border-radius: 999px; transition: width .3s ease; }}
  .bar-val {{ text-align: right; font-variant-numeric: tabular-nums; font-size: 0.88rem; color: #e2e8f0; }}
  .toggle-btn {{ background: var(--card2); color: var(--text); border: 1px solid var(--border); padding: 5px 12px; border-radius: 8px; cursor: pointer; font-size: 0.84rem; }}
  .toggle-btn.active {{ background: var(--accent2); color: #0f172a; border-color: var(--accent2); font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
  th {{ background: #162033; color: #cbd5e1; position: sticky; top: 0; }}
  tr:hover td {{ background: rgba(56,189,248,.06); }}
  .table-wrap {{ overflow-x: auto; max-height: 640px; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; align-items: center; }}
  input, select {{ background: #0f172a; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; font-size: 0.9rem; }}
  .pill {{ display: inline-flex; align-items: center; gap: 4px; background: var(--card2); padding: 3px 8px; border-radius: 999px; font-size: 0.8rem; margin: 2px; }}
  .pos {{ color: #4ade80; font-weight: 700; }}
  .neg {{ color: #f87171; font-weight: 700; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.82rem; margin-top: 32px; }}
  @media (max-width: 640px) {{ .bar-row {{ grid-template-columns: 115px 1fr 85px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1 id="reportTitle">{safe_title}</h1>
      <div class="sub" id="reportSub"></div>
    </div>
    <div class="sub" id="genTime"></div>
  </header>

  <section class="kpis" id="kpiRow"></section>

  <nav class="tabs">
    <button class="tab active" data-tab="occ">職業出場率</button>
    <button class="tab" data-tab="tier">Top 10 / 50 / 100 區間對比</button>
    <button class="tab" data-tab="combos">雙・三・八職業組合</button>
    <button class="tab" data-tab="raw">完整排行榜查詢</button>
  </nav>

  <section id="tab-occ" class="panel active">
    <div class="card">
      <h2>
        <span>各職業出場統計</span>
        <span>
          <button class="toggle-btn active" id="btnMetricTeam">隊伍攜帶率 (/隊數)</button>
          <button class="toggle-btn" id="btnMetricSlot">總人次佔比 (/總格數)</button>
        </span>
      </h2>
      <div id="occBars"></div>
    </div>
    <div class="card">
      <h2>職業詳細數據表</h2>
      <div class="table-wrap"><table id="occTable"></table></div>
    </div>
  </section>

  <section id="tab-tier" class="panel">
    <div class="card">
      <h2>Top 10 / Top 50 / Top 100 職業攜帶率與排名關聯</h2>
      <p class="sub">Spearman 相關係數為負值代表該職業越常出現在高排名（名次數字越小）；高排優勢比 (Lift) &gt; 1.0 代表前段班更偏好該職業。</p>
      <div class="table-wrap"><table id="tierTable"></table></div>
    </div>
  </section>

  <section id="tab-combos" class="panel">
    <div class="card">
      <h2>熱門雙職業組合（每隊去重）</h2>
      <div class="table-wrap"><table id="pairTable"></table></div>
    </div>
    <div class="card">
      <h2>同職業雙開 / 三開統計</h2>
      <div class="table-wrap"><table id="dupTable"></table></div>
    </div>
    <div class="card">
      <h2>熱門三職業組合（每隊去重）</h2>
      <div class="table-wrap"><table id="tripleTable"></table></div>
    </div>
    <div class="card">
      <h2>完整八職業陣容排行（保留重複數量）</h2>
      <div class="table-wrap"><table id="fullTable"></table></div>
    </div>
  </section>

  <section id="tab-raw" class="panel">
    <div class="card">
      <h2>完整排行榜資料</h2>
      <div class="controls">
        <input id="searchInput" type="search" placeholder="搜尋戰隊名稱或排名...">
        <select id="occFilter"><option value="">篩選特定職業（全部）</option></select>
        <span class="sub" id="rawCount"></span>
      </div>
      <div class="table-wrap"><table id="rawTable"></table></div>
    </div>
  </section>

  <footer>Generated by Game Leaderboard Analyzer — Self-contained interactive report</footer>
</div>

<script>
const DATA = {json_blob};
const A = DATA.analytics;
const ICONS = DATA.icons || {{}};
const pct = v => (Number(v || 0) * 100).toFixed(1) + '%';
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
const iconHtml = (name, cls='ico') => ICONS[name] ? `<img class="${{cls}}" src="${{ICONS[name]}}" alt="${{esc(name)}}" title="${{esc(name)}}">` : '';

document.getElementById('genTime').textContent = '產生時間：' + DATA.generated_at;
const ov = A.overview;
document.getElementById('reportSub').textContent = `涵蓋排名 #${{ov.min_rank}} ～ #${{ov.max_rank}}｜共 ${{ov.total_teams}} 隊、${{ov.total_non_empty_slots}} 個有效職業格`;

document.getElementById('kpiRow').innerHTML = [
  ['分析隊伍數', ov.total_teams + ' 隊'],
  ['辨識職業種類', ov.distinct_occupations + ' 種'],
  ['最熱門職業', A.occupation_frequency[0] ? A.occupation_frequency[0].occupation + ' (' + pct(A.occupation_frequency[0].team_presence_rate) + ')' : '-'],
  ['最熱門雙人組', A.pair_combinations[0] ? A.pair_combinations[0].combination : '-'],
].map(([l, v]) => `<div class="kpi"><div class="lbl">${{l}}</div><div class="val">${{esc(v)}}</div></div>`).join('');

// Tabs
document.querySelectorAll('.tab').forEach(btn => btn.onclick = () => {{
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
}});

let occMetric = 'team';
function renderOccBars() {{
  const rows = [...A.occupation_frequency].sort((a, b) =>
    occMetric === 'team' ? b.team_presence_rate - a.team_presence_rate : b.slot_rate - a.slot_rate
  );
  const maxVal = Math.max(...rows.map(r => occMetric === 'team' ? r.team_presence_rate : r.slot_rate), 0.1);
  document.getElementById('occBars').innerHTML = rows.map(r => {{
    const val = occMetric === 'team' ? r.team_presence_rate : r.slot_rate;
    const w = Math.max(2, (val / maxVal) * 100);
    const color = occMetric === 'team' ? 'linear-gradient(90deg,#0284c7,#38bdf8)' : 'linear-gradient(90deg,#d97706,#fbbf24)';
    const txt = occMetric === 'team' ? `${{pct(val)}} (${{r.team_count}}隊)` : `${{pct(val)}} (${{r.slot_count}}次)`;
    return `<div class="bar-row"><div class="bar-label">${{iconHtml(r.occupation)}}<span>${{esc(r.occupation)}}</span></div><div class="track"><div class="fill" style="width:${{w}}%;background:${{color}}"></div></div><div class="bar-val">${{txt}}</div></div>`;
  }}).join('');
}}
document.getElementById('btnMetricTeam').onclick = () => {{ occMetric='team'; btnMetricTeam.classList.add('active'); btnMetricSlot.classList.remove('active'); renderOccBars(); }};
document.getElementById('btnMetricSlot').onclick = () => {{ occMetric='slot'; btnMetricSlot.classList.add('active'); btnMetricTeam.classList.remove('active'); renderOccBars(); }};
renderOccBars();

document.getElementById('occTable').innerHTML =
  '<thead><tr><th>職業</th><th>總人次</th><th>總人次佔比</th><th>攜帶隊數</th><th>隊伍攜帶率</th><th>攜帶隊均數</th><th>多開隊數</th><th>平均排名</th><th>最高排名</th></tr></thead><tbody>' +
  A.occupation_frequency.map(r => `<tr><td><div class="bar-label">${{iconHtml(r.occupation,'ico-sm')}}<span>${{esc(r.occupation)}}</span></div></td><td>${{r.slot_count}}</td><td>${{pct(r.slot_rate)}}</td><td>${{r.team_count}}</td><td><b>${{pct(r.team_presence_rate)}}</b></td><td>${{r.avg_per_carrying_team}}</td><td>${{r.multi_copy_teams}}</td><td>#${{r.avg_rank}}</td><td>#${{r.best_rank}}</td></tr>`).join('') +
  '</tbody>';

document.getElementById('tierTable').innerHTML =
  '<thead><tr><th>職業</th><th>整體攜帶率</th><th>Top 10</th><th>Top 50</th><th>Top 100</th><th>Top10 差值</th><th>高排優勢比(Lift)</th><th>平均排名</th><th>Spearman r</th></tr></thead><tbody>' +
  A.ranking_analysis.occupation_tier_comparison.map(r => {{
    const diff = r.top10_rate - r.team_presence_rate;
    const cls = diff >= 0 ? 'pos' : 'neg';
    return `<tr><td><div class="bar-label">${{iconHtml(r.occupation,'ico-sm')}}<span>${{esc(r.occupation)}}</span></div></td><td>${{pct(r.team_presence_rate)}}</td><td><b>${{pct(r.top10_rate)}}</b></td><td>${{pct(r.top50_rate)}}</td><td>${{pct(r.top100_rate)}}</td><td class="${{cls}}">${{diff>=0?'+':''}}${{pct(diff)}}</td><td>${{r.top_tier_lift}}x</td><td>#${{r.avg_rank}}</td><td>${{r.spearman_r}}</td></tr>`;
  }}).join('') + '</tbody>';

function fillComboTable(id, rows) {{
  document.getElementById(id).innerHTML =
    '<thead><tr><th>組合</th><th>隊數</th><th>佔比</th><th>平均排名</th><th>最高排名</th><th>Top 10 佔比</th><th>Top 50 佔比</th><th>代表戰隊</th></tr></thead><tbody>' +
    (rows.length ? rows.map(r => `<tr><td><b>${{esc(r.combination)}}</b></td><td>${{r.team_count}}</td><td>${{pct(r.team_rate)}}</td><td>#${{r.avg_rank}}</td><td>#${{r.best_rank}}</td><td>${{pct(r.top10_rate)}}</td><td>${{pct(r.top50_rate)}}</td><td class="sub">${{esc(r.sample_teams)}}</td></tr>`).join('') : '<tr><td colspan="8" class="sub">無符合條件的組合</td></tr>') +
    '</tbody>';
}}
fillComboTable('pairTable', A.pair_combinations.slice(0, 40));
fillComboTable('dupTable', [...A.same_class_doubles, ...A.same_class_triples]);
fillComboTable('tripleTable', A.triple_combinations.slice(0, 40));
fillComboTable('fullTable', A.full_team_combinations.slice(0, 60));

const occSel = document.getElementById('occFilter');
A.occupation_frequency.forEach(r => {{ const o = document.createElement('option'); o.value = r.occupation; o.textContent = r.occupation; occSel.appendChild(o); }});

function renderRaw() {{
  const q = document.getElementById('searchInput').value.trim().toLowerCase();
  const occ = occSel.value;
  const filtered = A.raw_data.filter(r => {{
    if (occ && !r.occupations.includes(occ)) return false;
    if (q && !(String(r.rank).includes(q) || (r.team_name || '').toLowerCase().includes(q) || (r.full_team_signature || '').toLowerCase().includes(q))) return false;
    return true;
  }});
  document.getElementById('rawCount').textContent = `顯示 ${{filtered.length}} / ${{A.raw_data.length}} 隊`;
  document.getElementById('rawTable').innerHTML =
    '<thead><tr><th>排名</th><th>戰隊名稱</th><th>積分</th><th>8 職業配置</th></tr></thead><tbody>' +
    filtered.map(r => `<tr><td><b>#${{r.rank}}</b></td><td>${{esc(r.team_name)}}</td><td>${{r.score ?? '-'}}</td><td>${{r.occupations.map(o => `<span class="pill">${{iconHtml(o,'ico-sm')}}<span>${{esc(o)}}</span></span>`).join('')}}</td></tr>`).join('') +
    '</tbody>';
}}
document.getElementById('searchInput').oninput = renderRaw;
occSel.onchange = renderRaw;
renderRaw();
</script>
</body>
</html>
"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    return out
