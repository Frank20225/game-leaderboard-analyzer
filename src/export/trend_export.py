"""Exporters for multi-snapshot longitudinal trend analysis:
- 4-sheet Excel (Meta Shift, Double-Pick Shift, Team Trajectory, Roster Changes)
- 2 PNG trend charts (01_meta_trend_lines.png, 02_meta_movers_delta.png)
- Self-contained interactive HTML report (trend_report.html)
- Discord/LINE Markdown summary (summary.md)
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from openpyxl import Workbook

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.export.excel_writer import _autofit_columns, _style_table

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Noto Sans CJK TC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def write_trend_excel(trend: dict[str, Any], output_path: str | Path) -> Path:
    wb = Workbook()
    labels = trend["labels"]

    # 1. Meta Shift
    ws1 = wb.active
    ws1.title = "Meta Shift"
    h1 = [
        "職業", "趨勢標籤",
        *[f"{l} 攜帶率" for l in labels],
        "攜帶率變化(首→末)",
        *[f"{l} 雙開率" for l in labels],
        "雙開率變化(首→末)",
        "均排變化(正=升)",
    ]
    n = len(labels)
    rows1 = [
        [
            r["occupation"], r["trend_tag"],
            *r["presence_series"], r["presence_delta"],
            *r["double_pick_series"], r["double_pick_delta"],
            r["avg_rank_gain"] if r["avg_rank_gain"] is not None else "-",
        ]
        for r in trend["occupation_trends"]
    ]
    pct_cols1 = set(range(3, 3 + n + 1)) | set(range(3 + n + 1, 3 + 2 * n + 2))
    _style_table(ws1, h1, rows1, start_row=1, pct_cols=pct_cols1)
    ws1.freeze_panes = "A2"
    _autofit_columns(ws1)

    # 2. Double-Pick Shift
    ws2 = wb.create_sheet("Double-Pick Shift")
    h2 = ["雙開配置", *[f"{l} 佔比" for l in labels], "佔比變化(首→末)"]
    rows2 = [[d["label"], *d["rate_series"], d["rate_delta"]] for d in trend["double_pick_trends"]]
    _style_table(ws2, h2, rows2, start_row=1, pct_cols=set(range(2, 2 + n + 1)))
    ws2.freeze_panes = "A2"
    _autofit_columns(ws2)

    # 3. Team Trajectory
    ws3 = wb.create_sheet("Team Trajectory")
    h3 = ["戰隊名稱", "狀態", "出現期數", *[f"{l} 排名" for l in labels], "淨排名變化(正=升)", "換角紀錄", "最新 8 人名單"]
    rows3 = [
        [
            t["team_name"], t["status"], t["appearances"],
            *[r if r is not None else "-" for r in t["rank_series"]],
            t["net_rank_change"], t["roster_change_notes"], t["latest_roster"],
        ]
        for t in trend["team_trajectories"]
    ]
    _style_table(ws3, h3, rows3, start_row=1)
    ws3.freeze_panes = "A2"
    _autofit_columns(ws3, max_w=55)

    # 4. Roster Changes
    ws4 = wb.create_sheet("Roster Changes")
    h4 = ["戰隊名稱", "前期", "後期", "前期排名", "後期排名", "名次變化(正=升)", "換角明細", "換角前陣容", "換角後陣容"]
    rows4 = [
        [
            c["team_name"], c["from_period"], c["to_period"],
            c["rank_before"], c["rank_after"], c["rank_delta"],
            c["diff_summary"], c["roster_before"], c["roster_after"],
        ]
        for c in trend["roster_changes"]
    ]
    if not rows4:
        rows4 = [["(本期比對尚未偵測到同隊換角紀錄)", "", "", "", "", "", "", "", ""]]
    _style_table(ws4, h4, rows4, start_row=1)
    ws4.freeze_panes = "A2"
    _autofit_columns(ws4, max_w=55)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out


def generate_trend_cards(trend: dict[str, Any], cards_dir: str | Path) -> list[str]:
    out_dir = Path(cards_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    labels = trend["labels"]
    title = trend.get("trend_title", "排位賽多期趨勢分析")
    occ_trends = trend.get("occupation_trends", [])
    if not occ_trends:
        return created

    # Card 1: Top 8 Occupations Presence Rate Trend Lines
    top8 = sorted(occ_trends, key=lambda r: -max(r["presence_series"]))[:8]
    x = np.arange(len(labels))
    palette = ["#38bdf8", "#4ade80", "#fbbf24", "#f43f5e", "#a855f7", "#fb923c", "#2dd4bf", "#e879f9"]

    fig, ax = plt.subplots(figsize=(11.2, 6.4), facecolor="#0f172a")
    ax.set_facecolor("#162033")
    for idx, r in enumerate(top8):
        ys = [v * 100 for v in r["presence_series"]]
        col = palette[idx % len(palette)]
        ax.plot(x, ys, marker="o", linewidth=2.4, markersize=7, color=col, label=f"{r['occupation']} ({ys[-1]:.0f}%)")
        ax.text(x[-1] + 0.05, ys[-1], f"{r['occupation']} {ys[-1]:.0f}%", color=col, va="center", fontsize=9.2, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color="#f8fafc", fontsize=10.5, fontweight="bold")
    ax.set_xlim(-0.15, len(labels) - 0.35)
    ax.set_ylim(0, 108)
    ax.set_ylabel("隊伍攜帶率 (%)", color="#e2e8f0", fontsize=11)
    ax.tick_params(axis="y", colors="#cbd5e1")
    ax.grid(True, color="#334155", linestyle=":", alpha=0.6)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.legend(loc="lower left", ncol=2, facecolor="#0f172a", edgecolor="#475569", labelcolor="#f8fafc", fontsize=9)
    ax.set_title(f"{title}｜熱門職業攜帶率跨期演變", color="#ffffff", fontsize=14, fontweight="bold", pad=14)
    fig.tight_layout()
    p1 = out_dir / "01_meta_trend_lines.png"
    fig.savefig(str(p1), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    created.append(str(p1))

    # Card 2: Meta Movers (Rising vs Falling Presence Delta)
    movers = sorted(occ_trends, key=lambda r: r["presence_delta"])
    y = np.arange(len(movers))
    deltas = [r["presence_delta"] * 100 for r in movers]
    colors = ["#4ade80" if d >= 0 else "#f87171" for d in deltas]

    fig, ax = plt.subplots(figsize=(10.5, max(5.6, len(movers) * 0.45)), facecolor="#0f172a")
    ax.set_facecolor("#162033")
    ax.axvline(0, color="#94a3b8", linewidth=1.2)
    bars = ax.barh(y, deltas, color=colors, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels([r["occupation"] for r in movers], color="#f8fafc", fontsize=10.5, fontweight="bold")
    max_abs = max(max(abs(d) for d in deltas), 10.0)
    ax.set_xlim(-max_abs * 1.35, max_abs * 1.35)
    for b, r in zip(bars, movers):
        d = r["presence_delta"] * 100
        ha = "left" if d >= 0 else "right"
        pad = 0.8 if d >= 0 else -0.8
        ax.text(
            d + pad,
            b.get_y() + b.get_height() / 2,
            f"{d:+.1f}% ({r['first_presence']*100:.0f}%→{r['latest_presence']*100:.0f}%)",
            va="center",
            ha=ha,
            color="#f8fafc",
            fontsize=9,
            fontweight="bold",
        )
    ax.set_xlabel(f"攜帶率變化量：{labels[0]} → {labels[-1]} (%)", color="#e2e8f0", fontsize=11)
    ax.tick_params(axis="x", colors="#cbd5e1")
    ax.grid(axis="x", color="#334155", linestyle=":", alpha=0.6)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.set_title(f"{title}｜職業環境漲跌榜（{labels[0]} → {labels[-1]}）", color="#ffffff", fontsize=14, fontweight="bold", pad=14)
    fig.tight_layout()
    p2 = out_dir / "02_meta_movers_delta.png"
    fig.savefig(str(p2), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    created.append(str(p2))

    return created


def generate_trend_summary(trend: dict[str, Any], output_path: str | Path | None = None) -> str:
    labels = trend["labels"]
    sc = trend["summary_counts"]
    lines = [
        f"## 📈 {trend['trend_title']}",
        f"- **對比期數**：{' → '.join(labels)}（共 {sc['snapshot_count']} 期｜追蹤 {sc['tracked_teams']} 隊｜偵測到 {sc['roster_change_events']} 次中途換角）",
        "",
        "### 🔥 崛起職業（攜帶率上升最多）",
    ]
    rising = [r for r in trend["occupation_trends"] if r["presence_delta"] > 0][:5]
    if rising:
        for r in rising:
            lines.append(
                f"- **{r['occupation']}**：`{r['first_presence']*100:.1f}% → {r['latest_presence']*100:.1f}%`（**+{r['presence_delta']*100:.1f}%**｜雙開變化 {r['double_pick_delta']*100:+.1f}%）"
            )
    else:
        lines.append("- 本次各期攜帶率無明顯上升。")

    falling = sorted([r for r in trend["occupation_trends"] if r["presence_delta"] < 0], key=lambda r: r["presence_delta"])[:5]
    if falling:
        lines.extend(["", "### 🧊 衰退職業（攜帶率下降最多）"])
        for r in falling:
            lines.append(
                f"- **{r['occupation']}**：`{r['first_presence']*100:.1f}% → {r['latest_presence']*100:.1f}%`（**{r['presence_delta']*100:.1f}%**）"
            )

    if trend["roster_changes"]:
        lines.extend(["", "### 🔄 強隊換角與排名變動亮點"])
        for c in trend["roster_changes"][:8]:
            sign = "+" if c["rank_delta"] >= 0 else ""
            lines.append(
                f"- **{c['team_name']}**（{c['from_period']}→{c['to_period']}）：`{c['diff_summary']}` ｜ 排名 **#{c['rank_before']} → #{c['rank_after']} ({sign}{c['rank_delta']})**"
            )

    text = "\n".join(lines).strip() + "\n"
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text


def generate_trend_html(trend: dict[str, Any], output_path: str | Path) -> Path:
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "trend": trend,
    }
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    safe_title = html.escape(trend.get("trend_title", "排位賽多期趨勢分析"))
    doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title}</title>
<style>
  :root {{ --bg:#0b1120; --card:#131c31; --text:#f8fafc; --muted:#94a3b8; --accent:#38bdf8; --green:#4ade80; --red:#f87171; --border:#273552; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:"Microsoft JhengHei","Segoe UI",sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
  .wrap {{ max-width:1200px; margin:0 auto; padding:24px 16px 60px; }}
  h1 {{ margin:0 0 6px; }}
  .sub {{ color:var(--muted); font-size:.9rem; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px; margin:16px 0; }}
  table {{ width:100%; border-collapse:collapse; font-size:.88rem; }}
  th,td {{ padding:8px 10px; border-bottom:1px solid var(--border); text-align:left; }}
  th {{ background:#0f172a; color:#cbd5e1; position:sticky; top:0; }}
  .table-wrap {{ overflow-x:auto; max-height:560px; }}
  .pos {{ color:var(--green); font-weight:700; }}
  .neg {{ color:var(--red); font-weight:700; }}
  input {{ background:#0b1120; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 12px; margin-bottom:10px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>📈 {safe_title}</h1>
  <div class="sub" id="sub"></div>

  <div class="card">
    <h2>1. 職業環境跨期漲跌（Meta Shift）</h2>
    <div class="table-wrap"><table id="metaTbl"></table></div>
  </div>

  <div class="card">
    <h2>2. 雙開組數策略演變</h2>
    <div class="table-wrap"><table id="dpTbl"></table></div>
  </div>

  <div class="card">
    <h2>3. 戰隊中途換角偵測與排名變化</h2>
    <div class="table-wrap"><table id="changeTbl"></table></div>
  </div>

  <div class="card">
    <h2>4. 全體戰隊跨期排名軌跡查詢</h2>
    <input id="q" type="search" placeholder="搜尋戰隊名稱...">
    <div class="table-wrap"><table id="teamTbl"></table></div>
  </div>
</div>
<script>
const D = {blob};
const T = D.trend;
const pct = v => (Number(v||0)*100).toFixed(1) + '%';
const esc = s => String(s??'').replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
document.getElementById('sub').textContent = `對比期數：${{T.labels.join(' → ')}} ｜ 產生時間：${{D.generated_at}}`;

document.getElementById('metaTbl').innerHTML =
  `<thead><tr><th>職業</th><th>趨勢</th>${{T.labels.map(l=>`<th>${{esc(l)}} 攜帶率</th>`).join('')}}<th>攜帶率變化</th>${{T.labels.map(l=>`<th>${{esc(l)}} 雙開率</th>`).join('')}}<th>均排變化(正=升)</th></tr></thead><tbody>` +
  T.occupation_trends.map(r => `<tr><td><b>${{esc(r.occupation)}}</b></td><td>${{esc(r.trend_tag)}}</td>${{r.presence_series.map(v=>`<td>${{pct(v)}}</td>`).join('')}}<td class="${{r.presence_delta>0?'pos':r.presence_delta<0?'neg':''}}">${{r.presence_delta>=0?'+':''}}${{pct(r.presence_delta)}}</td>${{r.double_pick_series.map(v=>`<td>${{pct(v)}}</td>`).join('')}}<td class="${{(r.avg_rank_gain||0)>0?'pos':(r.avg_rank_gain||0)<0?'neg':''}}">${{r.avg_rank_gain===null?'-':(r.avg_rank_gain>=0?'+':'')+r.avg_rank_gain}}</td></tr>`).join('') + '</tbody>';

document.getElementById('dpTbl').innerHTML =
  `<thead><tr><th>雙開配置</th>${{T.labels.map(l=>`<th>${{esc(l)}}</th>`).join('')}}<th>變化</th></tr></thead><tbody>` +
  T.double_pick_trends.map(d => `<tr><td><b>${{esc(d.label)}}</b></td>${{d.rate_series.map(v=>`<td>${{pct(v)}}</td>`).join('')}}<td class="${{d.rate_delta>0?'pos':d.rate_delta<0?'neg':''}}">${{d.rate_delta>=0?'+':''}}${{pct(d.rate_delta)}}</td></tr>`).join('') + '</tbody>';

document.getElementById('changeTbl').innerHTML =
  '<thead><tr><th>戰隊</th><th>區間</th><th>換角明細</th><th>排名變化</th><th>換角後 8 人名單</th></tr></thead><tbody>' +
  (T.roster_changes.length ? T.roster_changes.map(c => `<tr><td><b>${{esc(c.team_name)}}</b></td><td>${{esc(c.from_period)}}→${{esc(c.to_period)}}</td><td><code>${{esc(c.diff_summary)}}</code></td><td class="${{c.rank_delta>0?'pos':c.rank_delta<0?'neg':''}}">#${{c.rank_before}} → #${{c.rank_after}} (${{c.rank_delta>=0?'+':''}}${{c.rank_delta}})</td><td class="sub">${{esc(c.roster_after)}}</td></tr>`).join('') : '<tr><td colspan="5" class="sub">未偵測到同隊換角</td></tr>') + '</tbody>';

function renderTeams() {{
  const kw = document.getElementById('q').value.trim().toLowerCase();
  const rows = T.team_trajectories.filter(t => !kw || t.team_name.toLowerCase().includes(kw) || t.latest_roster.toLowerCase().includes(kw));
  document.getElementById('teamTbl').innerHTML =
    `<thead><tr><th>戰隊</th><th>狀態</th>${{T.labels.map(l=>`<th>${{esc(l)}}</th>`).join('')}}<th>換角紀錄</th><th>最新名單</th></tr></thead><tbody>` +
    rows.map(t => `<tr><td><b>${{esc(t.team_name)}}</b></td><td>${{esc(t.status)}}</td>${{t.rank_series.map(r=>`<td>${{r===null?'-':'#'+r}}</td>`).join('')}}<td class="sub">${{esc(t.roster_change_notes||'-')}}</td><td class="sub">${{esc(t.latest_roster)}}</td></tr>`).join('') + '</tbody>';
}}
document.getElementById('q').oninput = renderTeams;
renderTeams();
</script>
</body>
</html>
"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out


def export_trend_package(trend: dict[str, Any], out_dir: str | Path) -> dict[str, Any]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "trend_analytics.json").write_text(
        json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    excel_p = write_trend_excel(trend, target / "trend_report.xlsx")
    html_p = generate_trend_html(trend, target / "trend_report.html")
    cards = generate_trend_cards(trend, target / "cards")
    summary_p = target / "summary.md"
    summary_txt = generate_trend_summary(trend, summary_p)
    manifest = {
        "trend_id": target.name,
        "trend_title": trend["trend_title"],
        "labels": trend["labels"],
        "summary_counts": trend["summary_counts"],
        "excel_path": str(excel_p),
        "html_path": str(html_p),
        "card_paths": cards,
        "summary_path": str(summary_p),
        "summary_text": summary_txt,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
