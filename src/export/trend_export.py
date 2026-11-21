"""Exporters for multi-snapshot longitudinal trend analysis (Locked-Roster League Edition):
- 5-sheet Excel (League Standings, Lineup Strength, Meta Shift, Double-Pick Shift, Roster Changes)
- 3 PNG trend charts (01_meta_trend_lines.png, 02_meta_movers_delta.png, 03_league_top25_standings.png)
- Self-contained interactive HTML report with embedded occupation icons (trend_report.html)
- Discord/LINE Markdown summary (summary.md)
"""

from __future__ import annotations

import base64
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

from src.config import ICON_DB_DIR
from src.export.excel_writer import _autofit_columns, _style_table

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Noto Sans CJK TC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _load_icon_db_b64() -> dict[str, str]:
    """Load Base64 occupation icons from data/icon_db so trend_report.html shows full class icons."""
    idx_path = ICON_DB_DIR / "index.json"
    if not idx_path.is_file():
        return {}
    try:
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        out: dict[str, str] = {}
        for item in data.get("occupations", []):
            name = item.get("name", "").strip()
            tfiles = item.get("template_files", [])
            if name and tfiles:
                p = ICON_DB_DIR / "templates" / tfiles[0]
                if p.is_file():
                    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                    out[name] = f"data:image/png;base64,{b64}"
        return out
    except Exception:
        return {}


def write_trend_excel(trend: dict[str, Any], output_path: str | Path) -> Path:
    wb = Workbook()
    labels = trend["labels"]
    n = len(labels)

    # 1. League Standings (Anchored on Current Rank #1..#200)
    ws0 = wb.active
    ws0.title = "League Standings"
    h0 = [
        "當下排名",
        "本期升降",
        "戰隊名稱",
        "當下積分",
        "本期積分成長(ΔScore)",
        "所屬陣容體系",
        *[f"{l} 排名" for l in labels],
        "歷史最高排名",
        "總淨爬升(首→末)",
        "副角色切換紀錄",
        "當下 8 人名單配置",
    ]
    rows0 = [
        [
            t["latest_rank"],
            t["status"],
            t["team_name"],
            t["latest_score"] if t["latest_score"] is not None else "-",
            t["recent_score_delta"] if t["recent_score_delta"] is not None else "-",
            t["archetype_tag"],
            *[r if r is not None else "-" for r in t["rank_series"]],
            t["best_rank"],
            t["net_rank_change"],
            t["roster_change_notes"],
            t["latest_roster"],
        ]
        for t in trend.get("league_standings", [])
    ]
    _style_table(ws0, h0, rows0, start_row=1)
    ws0.freeze_panes = "A2"
    _autofit_columns(ws0, max_w=55)

    # 2. Lineup Strength (Roster Archetype / System Momentum)
    ws_sys = wb.create_sheet("Lineup Strength")
    h_sys = [
        "陣容體系",
        "強度趨勢判定",
        "當下隊數",
        *[f"{l} 平均排名" for l in labels],
        "均排爬升(正=變強)",
        "隊伍平均淨爬升",
        "爬升隊伍比例(勝率動能)",
        "平均積分成長(ΔScore)",
        *[f"{l} Top30隊數" for l in labels],
        "Top30席次變化",
        "當下代表強隊",
    ]
    rows_sys = [
        [
            s["system_name"],
            s["verdict"],
            s["latest_team_count"],
            *[r if r is not None else "-" for r in s["avg_rank_series"]],
            s["avg_rank_gain"],
            s["avg_team_climb"],
            s["climber_rate"],
            s["avg_score_gain"] if s["avg_score_gain"] is not None else "-",
            *s["top30_series"],
            s["top30_delta"],
            s["sample_teams"],
        ]
        for s in trend.get("roster_strength_trends", [])
    ]
    _style_table(ws_sys, h_sys, rows_sys, start_row=1, pct_cols={4 + n + 3})
    ws_sys.freeze_panes = "A2"
    _autofit_columns(ws_sys, max_w=52)

    # 3. Meta Shift (Occupation Strength Momentum + Copy-1/Copy-2 Rank Shift)
    ws1 = wb.create_sheet("Meta Shift")
    h1 = [
        "職業",
        "強度趨勢",
        *[f"{l} 均排" for l in labels],
        "均排爬升(正=變強)",
        "單帶(1隻)均排爬升",
        "雙開(2隻)均排爬升",
        "持有戰隊爬升率",
        "平均積分成長(ΔScore)",
        "Top30攜帶率變化",
        *[f"{l} 攜帶率" for l in labels],
        "攜帶率變化(首→末)",
        *[f"{l} 雙開率" for l in labels],
        "雙開率變化(首→末)",
    ]
    rows1 = [
        [
            r["occupation"],
            r["trend_tag"],
            *[v if v is not None else "-" for v in r["avg_rank_series"]],
            r["avg_rank_gain"] if r["avg_rank_gain"] is not None else "-",
            r.get("copy1_rank_gain") if r.get("copy1_rank_gain") is not None else "-",
            r.get("copy2_rank_gain") if r.get("copy2_rank_gain") is not None else "-",
            r.get("climber_rate", 0.0),
            r.get("avg_score_gain") if r.get("avg_score_gain") is not None else "-",
            r.get("top30_presence_delta", 0.0),
            *r["presence_series"],
            r["presence_delta"],
            *r["double_pick_series"],
            r["double_pick_delta"],
        ]
        for r in trend["occupation_trends"]
    ]
    base_c = 2 + n
    pct_cols1 = (
        {base_c + 4, base_c + 6}
        | set(range(base_c + 7, base_c + 7 + n + 1))
        | set(range(base_c + 7 + n + 1, base_c + 7 + 2 * n + 2))
    )
    _style_table(ws1, h1, rows1, start_row=1, pct_cols=pct_cols1)
    ws1.freeze_panes = "A2"
    _autofit_columns(ws1)

    # 4. Double-Pick Shift
    ws2 = wb.create_sheet("Double-Pick Shift")
    h2 = [
        "雙開配置",
        *[f"{l} 佔比" for l in labels],
        "佔比變化(首→末)",
        *[f"{l} 平均排名" for l in labels],
        "均排爬升(正=變強)",
    ]
    rows2 = [
        [
            d["label"],
            *d["rate_series"],
            d["rate_delta"],
            *[v if v is not None else "-" for v in d.get("avg_rank_series", [])],
            d.get("avg_rank_gain") if d.get("avg_rank_gain") is not None else "-",
        ]
        for d in trend["double_pick_trends"]
    ]
    _style_table(ws2, h2, rows2, start_row=1, pct_cols=set(range(2, 2 + n + 1)))
    ws2.freeze_panes = "A2"
    _autofit_columns(ws2)

    # 5. Team Trajectory
    ws3 = wb.create_sheet("Team Trajectory")
    h3 = ["戰隊名稱", "當下排名", "狀態", "所屬體系", "出現期數", *[f"{l} 排名" for l in labels], "淨排名變化(正=升)", "副角色切換紀錄", "最新 8 人名單"]
    rows3 = [
        [
            t["team_name"],
            t["latest_rank"] if t["latest_rank"] is not None else "-",
            t["status"],
            t.get("archetype_tag", "-"),
            t["appearances"],
            *[r if r is not None else "-" for r in t["rank_series"]],
            t["net_rank_change"],
            t["roster_change_notes"],
            t["latest_roster"],
        ]
        for t in trend["team_trajectories"]
    ]
    _style_table(ws3, h3, rows3, start_row=1)
    ws3.freeze_panes = "A2"
    _autofit_columns(ws3, max_w=55)

    # 6. Roster Changes (Member 2nd-Character Switches)
    ws4 = wb.create_sheet("Roster Changes")
    h4 = ["戰隊名稱", "前期", "後期", "前期排名", "後期排名", "名次變化(正=升)", "積分成長(ΔScore)", "切換副角色明細", "切換前陣容", "切換後陣容"]
    rows4 = [
        [
            c["team_name"],
            c["from_period"],
            c["to_period"],
            c["rank_before"],
            c["rank_after"],
            c["rank_delta"],
            c.get("score_delta") if c.get("score_delta") is not None else "-",
            c["diff_summary"],
            c["roster_before"],
            c["roster_after"],
        ]
        for c in trend["roster_changes"]
    ]
    if not rows4:
        rows4 = [["(本期比對無戰隊切換副角色，全數以固定陣容對戰)", "", "", "", "", "", "", "", "", ""]]
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
    sys_trends = trend.get("roster_strength_trends", [])
    occ_trends = trend.get("occupation_trends", [])
    if not occ_trends:
        return created

    # Card 1: Roster Lineup System Strength Evolution (W1 Avg Rank -> Latest Avg Rank + Climber Rate %)
    # Even if 0 teams swap classes, this dumbbell chart shows which 8-man lineup archetype is climbing!
    fig, ax = plt.subplots(figsize=(11.5, 6.5), facecolor="#0f172a")
    ax.set_facecolor("#162033")
    if sys_trends:
        items = list(reversed(sys_trends))
        y = np.arange(len(items))
        r_first = [s["first_avg_rank"] or 100.0 for s in items]
        r_last = [s["latest_avg_rank"] or 100.0 for s in items]

        ax.axvline(100.5, color="#475569", linestyle="--", linewidth=1.2, label="全場平均線 (#100.5)")
        for idx, s in enumerate(items):
            f_val = r_first[idx]
            l_val = r_last[idx]
            gain = s["avg_rank_gain"]
            col = "#4ade80" if gain >= 1.0 else "#f87171" if gain <= -1.0 else "#94a3b8"
            ax.plot([f_val, l_val], [idx, idx], color=col, linewidth=3.0, zorder=2)
            ax.scatter([f_val], [idx], color="#64748b", s=70, zorder=3, label=f"{labels[0]} 均排" if idx == len(items) - 1 else "")
            ax.scatter([l_val], [idx], color=col, s=115, marker="D", zorder=4, label=f"{labels[-1]} 均排" if idx == len(items) - 1 else "")
            sign = "+" if gain >= 0 else ""
            txt = f"#{f_val:.1f} → #{l_val:.1f} ({sign}{gain:.1f}名｜爬升率 {s['climber_rate']*100:.0f}%)"
            offset = -1.8 if l_val <= f_val else 1.8
            ha = "left" if l_val <= f_val else "right"
            ax.text(l_val + offset, idx + 0.18, txt, color="#f8fafc", fontsize=9.2, fontweight="bold", ha=ha, va="bottom")

        ax.set_yticks(y)
        clean_lbls = [
            f"{s['system_name'].split(' ', 1)[-1]} ({s['latest_team_count']}隊)"
            for s in items
        ]
        ax.set_yticklabels(clean_lbls, color="#f8fafc", fontsize=10.2, fontweight="bold")
        all_v = r_first + r_last
        ax.set_xlim(max(all_v) + 18, max(1, min(all_v) - 22))  # Inverted X so right side = higher rank (#1)!
        ax.set_xlabel("陣容體系平均排名（越靠右側代表平均排名越高 →）", color="#e2e8f0", fontsize=11)
        ax.tick_params(axis="x", colors="#cbd5e1")
        ax.grid(True, color="#334155", linestyle=":", alpha=0.6)
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.legend(loc="lower left", facecolor="#0f172a", edgecolor="#475569", labelcolor="#f8fafc", fontsize=9.5)
        ax.set_title(f"{title}｜八大陣容體系跨期強度演變（{labels[0]} → {labels[-1]}）", color="#ffffff", fontsize=13.5, fontweight="bold", pad=14)
    fig.tight_layout()
    p1 = out_dir / "01_meta_trend_lines.png"
    fig.savefig(str(p1), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    created.append(str(p1))

    # Card 2: Occupation Strength Momentum (Avg Rank Climb ΔAvgRank + Climber Rate % + Top 30 Shift)
    movers = sorted(occ_trends, key=lambda r: (r["avg_rank_gain"] or 0.0))
    y = np.arange(len(movers))
    gains = [float(r["avg_rank_gain"] or 0.0) for r in movers]
    colors = ["#4ade80" if g >= 1.0 else "#f87171" if g <= -1.0 else "#38bdf8" for g in gains]

    fig, ax = plt.subplots(figsize=(11.0, max(5.8, len(movers) * 0.46)), facecolor="#0f172a")
    ax.set_facecolor("#162033")
    ax.axvline(0, color="#94a3b8", linewidth=1.2)
    bars = ax.barh(y, gains, color=colors, height=0.62)
    ax.set_yticks(y)
    ax.set_yticklabels([r["occupation"] for r in movers], color="#f8fafc", fontsize=10.5, fontweight="bold")
    max_abs = max(max(abs(g) for g in gains), 5.0)
    ax.set_xlim(-max_abs * 1.48, max_abs * 1.48)
    for b, r in zip(bars, movers):
        g = float(r["avg_rank_gain"] or 0.0)
        ha = "left" if g >= 0 else "right"
        pad = max_abs * 0.03 if g >= 0 else -max_abs * 0.03
        t30_d = r.get("top30_presence_delta", 0.0) * 100
        ax.text(
            g + pad,
            b.get_y() + b.get_height() / 2,
            f"{g:+.1f}名 (#{r['first_avg_rank']}→#{r['latest_avg_rank']}｜爬升率{r.get('climber_rate',0)*100:.0f}%｜Top30 {t30_d:+.1f}%)",
            va="center",
            ha=ha,
            color="#f8fafc",
            fontsize=8.8,
            fontweight="bold",
        )
    ax.set_xlabel(f"持有該職業戰隊之平均排名爬升量：{labels[0]} → {labels[-1]}（正值＝整體名次上升）", color="#e2e8f0", fontsize=10.8)
    ax.tick_params(axis="x", colors="#cbd5e1")
    ax.grid(axis="x", color="#334155", linestyle=":", alpha=0.6)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.set_title(f"{title}｜各職業實戰強度動能榜（平均名次爬升 ＆ Top 30 滲透率）", color="#ffffff", fontsize=13.5, fontweight="bold", pad=14)
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
        f"## 🏆 {trend['trend_title']}（聯賽當下積分榜 ＆ 陣容強度趨勢）",
        f"- **賽制背景**：成員鎖定、每人最多創建 2 隻角色｜**對比期數**：{' → '.join(labels)}（追蹤 {sc['tracked_teams']} 隊｜原陣容直衝 {sc.get('locked_roster_teams', 0)} 隊｜切換副角色 {sc['roster_change_events']} 隊）",
        "",
        f"### 👑 聯賽當下 Top 10 即時積分排行榜（以 {labels[-1]} 最新排名為主軸）",
    ]
    for t in trend.get("league_standings", [])[:10]:
        sc_txt = f"{t['latest_score']}分" if t["latest_score"] is not None else "-"
        if t.get("recent_score_delta") is not None:
            sc_txt += f" ({t['recent_score_delta']:+d})"
        lines.append(
            f"- **#{t['latest_rank']} {t['team_name']}**（`{t['status']}`｜前期 #{t['prev_rank'] or '-'}｜積分 **{sc_txt}**｜{t['archetype_tag']}）：`{t['latest_roster']}`"
        )

    sys_trends = trend.get("roster_strength_trends", [])
    if sys_trends:
        lines.extend(["", "### ⚔️ 八大陣容體系跨期強度趨勢（不靠換角也能看出的版本答案）"])
        for s in sys_trends:
            sign = "+" if s["avg_rank_gain"] >= 0 else ""
            lines.append(
                f"- **{s['system_name']}**（{s['verdict']}｜{s['latest_team_count']}隊）：均排 **#{s['first_avg_rank']} → #{s['latest_avg_rank']} ({sign}{s['avg_rank_gain']}名)**｜爬升勝率 **{s['climber_rate']*100:.0f}%**｜Top30 席次 `{s['top30_series'][0]}→{s['top30_series'][-1]} ({s['top30_delta']:+d})`"
            )

    lines.extend(["", "### 📊 單一職業實戰強度動能（持有戰隊均排爬升 Top 5）"])
    for r in trend["occupation_trends"][:5]:
        g = r["avg_rank_gain"] or 0.0
        c2_txt = f"｜雙開均排變化 {r['copy2_rank_gain']:+.1f}名" if r.get("copy2_rank_gain") is not None else ""
        lines.append(
            f"- **{r['occupation']}**（{r['trend_tag']}）：持有戰隊均排 **#{r['first_avg_rank']} → #{r['latest_avg_rank']} ({g:+.1f}名)**｜爬升比例 **{r.get('climber_rate',0)*100:.0f}%**｜Top30 佔比 `{r.get('first_top30_presence',0)*100:.1f}%→{r.get('latest_top30_presence',0)*100:.1f}%`{c2_txt}"
        )

    climbers = trend.get("top_climbers", [])[:5]
    if climbers:
        lines.extend(["", "### 🚀 本期最強爬升黑馬戰隊 Top 5"])
        for t in climbers:
            mode = f"切換副角色 `{t['roster_change_notes']}`" if t["roster_changed"] else "🔒 原陣容未換角直衝"
            lines.append(
                f"- **#{t['latest_rank']} {t['team_name']}**（**#{t['first_rank']} → #{t['latest_rank']}，狂升 +{t['net_rank_change']} 名**｜{t['archetype_tag']}｜{mode}）"
            )

    text = "\n".join(lines).strip() + "\n"
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text


def generate_trend_html(trend: dict[str, Any], output_path: str | Path) -> Path:
    icons_b64 = _load_icon_db_b64()
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "trend": trend,
        "icons": icons_b64,
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
  :root {{ --bg:#0b1120; --card:#131c31; --card2:#1c2842; --text:#f8fafc; --muted:#94a3b8; --accent:#38bdf8; --accent2:#f59e0b; --green:#4ade80; --red:#f87171; --border:#273552; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:"Microsoft JhengHei","Segoe UI",sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
  .wrap {{ max-width:1260px; margin:0 auto; padding:24px 16px 60px; }}
  h1 {{ margin:0 0 6px; font-size:1.55rem; }}
  .sub {{ color:var(--muted); font-size:.9rem; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin:16px 0; }}
  .kpi {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:13px 16px; }}
  .kpi .lbl {{ color:var(--muted); font-size:.82rem; }}
  .kpi .val {{ font-size:1.28rem; font-weight:700; color:var(--accent); margin-top:4px; }}
  .tabs {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
  .tab {{ background:var(--card); color:var(--muted); border:1px solid var(--border); padding:9px 15px; border-radius:999px; cursor:pointer; font-weight:600; font-size:.9rem; }}
  .tab.active {{ background:var(--accent); color:#0b1120; border-color:var(--accent); }}
  .panel {{ display:none; }}
  .panel.active {{ display:block; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px; margin:16px 0; }}
  .card h2 {{ margin:0 0 10px; font-size:1.12rem; }}
  table {{ width:100%; border-collapse:collapse; font-size:.87rem; }}
  th,td {{ padding:8px 10px; border-bottom:1px solid var(--border); text-align:left; }}
  th {{ background:#0f172a; color:#cbd5e1; position:sticky; top:0; z-index:2; }}
  tr:hover td {{ background:rgba(56,189,248,.07); }}
  .table-wrap {{ overflow-x:auto; max-height:660px; }}
  .pos {{ color:var(--green); font-weight:700; }}
  .neg {{ color:var(--red); font-weight:700; }}
  .ico {{ width:24px; height:24px; border-radius:50%; object-fit:cover; vertical-align:middle; border:1px solid rgba(255,255,255,.15); }}
  .pill {{ display:inline-flex; align-items:center; gap:4px; background:var(--card2); padding:2px 8px; border-radius:999px; font-size:.79rem; margin:2px; }}
  .pill.dp {{ border:1px solid rgba(245,158,11,.6); background:rgba(245,158,11,.15); }}
  .tag {{ padding:2px 8px; border-radius:999px; font-size:.78rem; font-weight:700; display:inline-block; background:var(--card2); }}
  .filter-bar {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; align-items:center; }}
  .chip-btn {{ background:#0f172a; color:var(--muted); border:1px solid var(--border); border-radius:999px; padding:5px 12px; font-size:.82rem; cursor:pointer; font-weight:600; }}
  .chip-btn.active {{ background:rgba(56,189,248,.2); color:#7dd3fc; border-color:var(--accent); }}
  input, select {{ background:#0b1120; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 12px; font-size:.9rem; }}
  .grid-2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:14px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🏆 {safe_title}</h1>
  <div class="sub" id="sub"></div>
  <section class="kpis" id="kpiRow"></section>

  <nav class="tabs">
    <button class="tab active" data-tab="standings">🏆 1. 聯賽當下積分排行榜（以當下名次為主軸）</button>
    <button class="tab" data-tab="archetypes">⚔️ 2. 八大陣容體系強度趨勢（不靠換角看環境）</button>
    <button class="tab" data-tab="classes">📊 3. 職業＆單雙開實戰強度動能</button>
    <button class="tab" data-tab="climbers">🚀 4. 黑馬爬升榜 / 掉分榜 ＆ 副角色切換</button>
  </nav>

  <section id="tab-standings" class="panel active">
    <div class="card">
      <h2>🏆 聯賽即時積分排行榜（依最新一期當下排名 #1 ～ #200 排序）</h2>
      <div class="sub" style="margin-bottom:10px">
        💡 比照職業運動聯賽積分榜：以<b>當下最新排名</b>為基準，結合<b>本期名次升降 (▲/▼)</b>、<b>當下積分與本期淨勝分成長 (+Δ積分)</b>、<b>所屬陣容體系</b>與<b>成員副角色切換紀錄</b>。金色外框代表該隊滿編雙開（×2）核心職業。
      </div>
      <div class="filter-bar" id="standingsFilterBar">
        <button class="chip-btn active" data-f="all">🌐 全部當下排名</button>
        <button class="chip-btn" data-f="top30">👑 Top 30 頂尖強隊</button>
        <button class="chip-btn" data-f="climb">🚀 本期大爬升 (▲+5以上)</button>
        <button class="chip-btn" data-f="fall">🔻 本期下滑 (▼-5以下)</button>
        <button class="chip-btn" data-f="locked">🔒 原陣容未換角</button>
        <button class="chip-btn" data-f="swapped">🔄 有切換副角色</button>
      </div>
      <div class="filter-bar">
        <input id="qStandings" type="search" placeholder="搜尋戰隊名稱、排名或職業..." style="min-width:260px">
        <select id="archFilter"><option value="">篩選陣容體系（全部）</option></select>
        <span class="sub" id="standingsCount"></span>
      </div>
      <div class="table-wrap"><table id="standingsTbl"></table></div>
    </div>
  </section>

  <section id="tab-archetypes" class="panel">
    <div class="card">
      <h2>⚔️ 八大陣容體系跨期強度趨勢（鎖定成員／每人限創 2 角賽制專用）</h2>
      <div class="sub" style="background:#0f172a;border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:12px;line-height:1.65">
        💡 <b>為什麼要看「陣容體系強度趨勢」？</b><br>
        由於比賽開始後<b>無法更換隊員、且每位隊員最多只能創建 2 隻角色</b>，全伺服器各職業的「總攜帶率 %」幾乎不會大幅變動。<br>
        因此真正的 Meta 趨勢不在於「多少人換職業」，而在於隨賽程推進：<b>哪一套 8 人陣容體系的「平均排名正在集體往上爬」、「爬升隊伍比例（勝率動能）最高」、「擠進 Top 30 的席次變多」</b>！
      </div>
      <div class="table-wrap"><table id="sysTbl"></table></div>
    </div>
    <div class="card">
      <h2>雙開組數策略（0 雙開 vs 1 / 2 / 3 組雙開）跨期平均排名演變</h2>
      <div class="table-wrap"><table id="dpTbl"></table></div>
    </div>
  </section>

  <section id="tab-classes" class="panel">
    <div class="card">
      <h2>📊 14 職業＆「單帶 vs 雙開」跨期實戰強度動能表</h2>
      <div class="sub" style="margin-bottom:10px">
        💡 即使某職業的全場總攜帶率不變，只要<b>「持有該職業戰隊的均排爬升 (Δ均排 &gt; 0)」</b>、<b>「雙開(2隻)均排持續領跑」</b>或<b>「Top 30 高端佔有率上升」</b>，就代表該職業在實戰對局中正在幫隊伍贏下分數！
      </div>
      <div class="table-wrap"><table id="metaTbl"></table></div>
    </div>
  </section>

  <section id="tab-climbers" class="panel">
    <div class="grid-2">
      <div class="card">
        <h2>🚀 本期最強爬升黑馬榜 Top 15</h2>
        <div class="table-wrap"><table id="climbersTbl"></table></div>
      </div>
      <div class="card">
        <h2>🔻 本期排名退化警報榜 Top 15</h2>
        <div class="table-wrap"><table id="fallersTbl"></table></div>
      </div>
    </div>
    <div class="card">
      <h2>🔄 成員副角色（二號角）切換偵測與排名效益</h2>
      <div class="sub" style="margin-bottom:10px">在無法換人的前提下，名單出現 1～2 個職業變動代表隊員切換了預先練好的第 2 隻角色上場。此表追蹤切換副角色後的實際名次與積分效益：</div>
      <div class="table-wrap"><table id="changeTbl"></table></div>
    </div>
  </section>
</div>
<script>
const D = {blob};
const T = D.trend;
const ICONS = D.icons || {{}};
const pct = v => (Number(v||0)*100).toFixed(1) + '%';
const esc = s => String(s??'').replace(/[&<>"']/g, m => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]));
const ico = n => ICONS[n] ? `<img class="ico" src="${{ICONS[n]}}" alt="${{esc(n)}}">` : '';

document.getElementById('sub').textContent = `對比期數：${{T.labels.join(' → ')}} ｜ 賽制：成員鎖定・每人限創2角・8人同職上限2 ｜ 產生時間：${{D.generated_at}}`;

document.querySelectorAll('.tab').forEach(btn => btn.onclick = () => {{
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
}});

const bestSys = (T.roster_strength_trends || [])[0];
const bestOcc = (T.occupation_trends || [])[0];
const topTeam = (T.league_standings || [])[0];
document.getElementById('kpiRow').innerHTML = [
  ['當下聯賽榜首', topTeam ? `#1 ${{topTeam.team_name}} (${{topTeam.latest_score ?? '-'}}分)` : '-'],
  ['最強勢上分體系', bestSys ? `${{bestSys.system_name.replace(/^[^ ]+ /,'')}} (+${{bestSys.avg_rank_gain}}名)` : '-'],
  ['最強動能職業', bestOcc ? `${{bestOcc.occupation}} (均排+${{bestOcc.avg_rank_gain}}名)` : '-'],
  ['原陣容直衝 / 切換副角', `${{T.summary_counts.locked_roster_teams || 0}} 隊 / ${{T.summary_counts.roster_change_events || 0}} 隊`],
].map(([l,v]) => `<div class="kpi"><div class="lbl">${{l}}</div><div class="val">${{esc(v)}}</div></div>`).join('');

// Tab 1: League Standings (Anchored on latest rank #1..#200)
const standings = T.league_standings || [];
const archSel = document.getElementById('archFilter');
[...new Set(standings.map(t => t.archetype_tag).filter(Boolean))].forEach(a => {{
  const o = document.createElement('option'); o.value = a; o.textContent = a; archSel.appendChild(o);
}});
let activeStandFilter = 'all';

document.querySelectorAll('#standingsFilterBar .chip-btn').forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll('#standingsFilterBar .chip-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeStandFilter = btn.dataset.f;
    renderStandings();
  }};
}});

function renderStandings() {{
  const kw = document.getElementById('qStandings').value.trim().toLowerCase();
  const arch = archSel.value;
  const rows = standings.filter(t => {{
    if (activeStandFilter === 'top30' && t.latest_rank > 30) return false;
    if (activeStandFilter === 'climb' && t.recent_rank_change < 5) return false;
    if (activeStandFilter === 'fall' && t.recent_rank_change > -5) return false;
    if (activeStandFilter === 'locked' && t.roster_changed) return false;
    if (activeStandFilter === 'swapped' && !t.roster_changed) return false;
    if (arch && t.archetype_tag !== arch) return false;
    if (kw && !(String(t.latest_rank).includes(kw) || t.team_name.toLowerCase().includes(kw) || t.latest_roster.toLowerCase().includes(kw))) return false;
    return true;
  }});

  document.getElementById('standingsCount').textContent = `顯示 ${{rows.length}} / ${{standings.length}} 隊`;
  document.getElementById('standingsTbl').innerHTML =
    `<thead><tr><th>當下排名</th><th>本期升降</th><th>戰隊名稱</th><th>當下積分 (本期Δ)</th><th>所屬陣容體系</th>${{T.labels.slice(0,-1).map(l=>`<th>${{esc(l)}}</th>`).join('')}}<th>當下 8 人名單（金框＝雙開）</th><th>副角色切換</th></tr></thead><tbody>` +
    rows.map(t => {{
      const rc = t.recent_rank_change || 0;
      const rcCls = rc > 0 ? 'pos' : rc < 0 ? 'neg' : 'sub';
      const scDelta = t.recent_score_delta !== null && t.recent_score_delta !== undefined ? `<span class="${{t.recent_score_delta>=0?'pos':'neg'}}" style="font-size:.8rem">(${{t.recent_score_delta>=0?'+':''}}${{t.recent_score_delta}})</span>` : '';
      const cnts = {{}};
      (t.latest_occs || []).forEach(o => cnts[o] = (cnts[o]||0)+1);
      const pills = (t.latest_occs && t.latest_occs.length)
        ? t.latest_occs.map(o => `<span class="pill ${{cnts[o]>=2?'dp':''}}">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')
        : `<span class="sub">${{esc(t.latest_roster)}}</span>`;
      const prevCols = (t.rank_series || []).slice(0,-1).map(r => `<td class="sub">${{r===null?'-':'#'+r}}</td>`).join('');
      return `<tr>
        <td><b style="font-size:1rem">#${{t.latest_rank}}</b></td>
        <td class="${{rcCls}}">${{esc(t.status)}}</td>
        <td><b>${{esc(t.team_name)}}</b></td>
        <td><b>${{t.latest_score ?? '-'}}</b> ${{scDelta}}</td>
        <td><span class="tag">${{esc(t.archetype_tag)}}</span></td>
        ${{prevCols}}
        <td>${{pills}}</td>
        <td class="sub" style="font-size:.8rem">${{t.roster_changed ? `<span class="pos">${{esc(t.roster_change_notes)}}</span>` : '🔒 固定陣容'}}</td>
      </tr>`;
    }}).join('') + '</tbody>';
}}
document.getElementById('qStandings').oninput = renderStandings;
archSel.onchange = renderStandings;
renderStandings();

// Tab 2: Roster Lineup System Strength Trends
document.getElementById('sysTbl').innerHTML =
  `<thead><tr><th>陣容體系</th><th>強度趨勢判定</th><th>當下隊數</th>${{T.labels.map(l=>`<th>${{esc(l)}} 均排</th>`).join('')}}<th>體系均排爬升</th><th>爬升隊伍比例(勝率動能)</th><th>平均積分成長</th><th>Top 30 席次變化</th><th>當下代表強隊</th></tr></thead><tbody>` +
  (T.roster_strength_trends || []).map(s => {{
    const g = s.avg_rank_gain || 0;
    const td = s.top30_delta || 0;
    return `<tr>
      <td><b>${{esc(s.system_name)}}</b></td>
      <td><span class="tag">${{esc(s.verdict)}}</span></td>
      <td>${{s.latest_team_count}} 隊</td>
      ${{s.avg_rank_series.map(v => `<td><b>${{v===null?'-':'#'+v}}</b></td>`).join('')}}
      <td class="${{g>0?'pos':g<0?'neg':''}}">${{g>=0?'+':''}}${{g}} 名</td>
      <td class="${{s.climber_rate>=0.55?'pos':s.climber_rate<=0.40?'neg':''}}"><b>${{pct(s.climber_rate)}}</b> (${{s.climber_count}}隊上升)</td>
      <td>${{s.avg_score_gain !== null ? (s.avg_score_gain>=0?'+':'')+s.avg_score_gain+' 分' : '-'}}</td>
      <td class="${{td>0?'pos':td<0?'neg':''}}">${{s.top30_series[0]}} → ${{s.top30_series[s.top30_series.length-1]}} (${{td>=0?'+':''}}${{td}})</td>
      <td class="sub">${{esc(s.sample_teams)}}</td>
    </tr>`;
  }}).join('') + '</tbody>';

document.getElementById('dpTbl').innerHTML =
  `<thead><tr><th>雙開配置</th>${{T.labels.map(l=>`<th>${{esc(l)}} 佔比</th>`).join('')}}<th>佔比變化</th>${{T.labels.map(l=>`<th>${{esc(l)}} 均排</th>`).join('')}}<th>均排爬升(正=變強)</th></tr></thead><tbody>` +
  T.double_pick_trends.map(d => {{
    const rg = d.avg_rank_gain;
    return `<tr><td><b>${{esc(d.label)}}</b></td>${{d.rate_series.map(v=>`<td>${{pct(v)}}</td>`).join('')}}<td class="${{d.rate_delta>0?'pos':d.rate_delta<0?'neg':''}}">${{d.rate_delta>=0?'+':''}}${{pct(d.rate_delta)}}</td>${{(d.avg_rank_series||[]).map(v=>`<td><b>${{v===null?'-':'#'+v}}</b></td>`).join('')}}<td class="${{(rg||0)>0?'pos':(rg||0)<0?'neg':''}}">${{rg===null||rg===undefined?'-':(rg>=0?'+':'')+rg+' 名'}}</td></tr>`;
  }}).join('') + '</tbody>';

// Tab 3: Occupation & Copy-Count Performance Momentum
document.getElementById('metaTbl').innerHTML =
  `<thead><tr><th>職業</th><th>強度動能</th>${{T.labels.map(l=>`<th>${{esc(l)}} 均排</th>`).join('')}}<th>持有戰隊均排爬升</th><th>單帶(1隻)均排變化</th><th>雙開(2隻)均排變化</th><th>持有戰隊爬升率</th><th>平均Δ積分</th><th>Top30高端佔比變化</th><th>全場攜帶率(${{esc(T.labels[T.labels.length-1])}})</th></tr></thead><tbody>` +
  T.occupation_trends.map(r => {{
    const g = r.avg_rank_gain || 0;
    const c1 = r.copy1_rank_gain;
    const c2 = r.copy2_rank_gain;
    const t30 = r.top30_presence_delta || 0;
    return `<tr>
      <td><span style="display:inline-flex;align-items:center;gap:6px;font-weight:700">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td>
      <td><span class="tag">${{esc(r.trend_tag)}}</span></td>
      ${{r.avg_rank_series.map(v=>`<td><b>${{v===null?'-':'#'+v}}</b></td>`).join('')}}
      <td class="${{g>0?'pos':g<0?'neg':''}}"><b>${{g>=0?'+':''}}${{g}} 名</b></td>
      <td class="${{(c1||0)>0?'pos':(c1||0)<0?'neg':'sub'}}">${{c1===null||c1===undefined?'-':(c1>=0?'+':'')+c1+' 名'}}</td>
      <td class="${{(c2||0)>0?'pos':(c2||0)<0?'neg':'sub'}}">${{c2===null||c2===undefined?'-':(c2>=0?'+':'')+c2+' 名'}}</td>
      <td class="${{(r.climber_rate||0)>=0.55?'pos':(r.climber_rate||0)<=0.40?'neg':''}}"><b>${{pct(r.climber_rate)}}</b> (${{r.climber_count}}升/${{r.faller_count}}降)</td>
      <td>${{r.avg_score_gain!==null&&r.avg_score_gain!==undefined?(r.avg_score_gain>=0?'+':'')+r.avg_score_gain+'分':'-'}}</td>
      <td class="${{t30>0?'pos':t30<0?'neg':''}}">${{pct(r.first_top30_presence)}} → ${{pct(r.latest_top30_presence)}} (${{t30>=0?'+':''}}${{pct(t30)}})</td>
      <td>${{pct(r.latest_presence)}} <span class="sub">(${{r.presence_delta>=0?'+':''}}${{pct(r.presence_delta)}})</span></td>
    </tr>`;
  }}).join('') + '</tbody>';

// Tab 4: Top Climbers, Top Fallers & Member Alt-Character Switches
const renderMiniMoverTbl = (id, rows, isClimb) => {{
  document.getElementById(id).innerHTML =
    '<thead><tr><th>當下排名</th><th>戰隊名稱</th><th>跨期升降</th><th>陣容體系</th><th>副角色切換</th></tr></thead><tbody>' +
    rows.map(t => `<tr>
      <td><b>#${{t.latest_rank}}</b></td>
      <td><b>${{esc(t.team_name)}}</b></td>
      <td class="${{isClimb?'pos':'neg'}}">#${{t.first_rank}} → #${{t.latest_rank}} (${{t.net_rank_change>=0?'+':''}}${{t.net_rank_change}})</td>
      <td><span class="tag">${{esc(t.archetype_tag)}}</span></td>
      <td class="sub" style="font-size:.8rem">${{esc(t.roster_change_notes)}}</td>
    </tr>`).join('') + '</tbody>';
}};
renderMiniMoverTbl('climbersTbl', T.top_climbers || [], true);
renderMiniMoverTbl('fallersTbl', T.top_fallers || [], false);

document.getElementById('changeTbl').innerHTML =
  '<thead><tr><th>戰隊</th><th>區間</th><th>切換副角色明細</th><th>排名變化</th><th>積分變化</th><th>切換後 8 人名單</th></tr></thead><tbody>' +
  (T.roster_changes.length ? T.roster_changes.map(c => `<tr><td><b>${{esc(c.team_name)}}</b></td><td>${{esc(c.from_period)}}→${{esc(c.to_period)}}</td><td><code>${{esc(c.diff_summary)}}</code></td><td class="${{c.rank_delta>0?'pos':c.rank_delta<0?'neg':''}}">#${{c.rank_before}} → #${{c.rank_after}} (${{c.rank_delta>=0?'+':''}}${{c.rank_delta}})</td><td>${{c.score_delta!==null&&c.score_delta!==undefined?(c.score_delta>=0?'+':'')+c.score_delta+'分':'-'}}</td><td class="sub">${{esc(c.roster_after)}}</td></tr>`).join('') : '<tr><td colspan="6" class="sub">本期無戰隊切換副角色（全數以固定陣容爬分）</td></tr>') + '</tbody>';
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
