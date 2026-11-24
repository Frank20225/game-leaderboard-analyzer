"""Exporters for multi-snapshot longitudinal trend analysis (Coach & Mobile-First Edition):
- 5-sheet Excel (League Standings, Meta Shift, Double-Pick Shift, Score Cutoffs & Swap Flow, Roster Changes)
- 2 PNG trend charts (01_meta_trend_lines.png = Occupation Avg Rank Dumbbell, 02_meta_movers_delta.png = Occupation Strength Momentum with <5% low-sample separation)
- Self-contained mobile-first 3-tab interactive HTML report with embedded occupation icons & shared C3 My-Team Lock (trend_report.html)
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
        "雙職業組數",
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
            t.get("double_pick_count", 0),
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

    # 2. Meta Shift (Occupation Strength Momentum + Copy-1/Copy-2 Rank Shift + <5% Note)
    ws1 = wb.create_sheet("Meta Shift")
    h1 = [
        "職業",
        "樣本註記",
        "強度趨勢",
        *[f"{l} 均排" for l in labels],
        "均排爬升(正=變強)",
        "單職業(1隻)均排爬升",
        "雙職業(2隻)均排爬升",
        "持有戰隊爬升率",
        "平均積分成長(ΔScore)",
        "Top30出場率變化",
        *[f"{l} 出場率" for l in labels],
        "出場率變化(首→末)",
        *[f"{l} 雙職業率" for l in labels],
        "雙職業率變化(首→末)",
    ]
    rows1 = [
        [
            r["occupation"],
            "樣本偏小 (<5%)" if r.get("low_sample") else "正規樣本",
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
    base_c = 3 + n
    pct_cols1 = (
        {base_c + 4, base_c + 6}
        | set(range(base_c + 7, base_c + 7 + n + 1))
        | set(range(base_c + 7 + n + 1, base_c + 7 + 2 * n + 2))
    )
    _style_table(ws1, h1, rows1, start_row=1, pct_cols=pct_cols1)
    ws1.freeze_panes = "A2"
    _autofit_columns(ws1)

    # 3. Double-Pick Shift
    ws2 = wb.create_sheet("Double-Pick Shift")
    h2 = [
        "雙職業配置",
        "樣本註記",
        *[f"{l} 佔比" for l in labels],
        "佔比變化(首→末)",
        *[f"{l} 平均排名" for l in labels],
        "均排爬升(正=變強)",
    ]
    rows2 = [
        [
            d["label"],
            "樣本偏小 (<5%)" if d.get("low_sample") else "正規樣本",
            *d["rate_series"],
            d["rate_delta"],
            *[v if v is not None else "-" for v in d.get("avg_rank_series", [])],
            d.get("avg_rank_gain") if d.get("avg_rank_gain") is not None else "-",
        ]
        for d in trend["double_pick_trends"]
    ]
    _style_table(ws2, h2, rows2, start_row=1, pct_cols=set(range(3, 3 + n + 1)))
    ws2.freeze_panes = "A2"
    _autofit_columns(ws2)

    # 4. Score Cutoffs & Alt-Character Swap Flow
    ws3 = wb.create_sheet("Cutoffs & Swap Flow")
    h3 = [
        "排名門檻",
        *[f"{l} 門檻分" for l in labels],
        "門檻漲幅(Δ分)",
        "最新期同分擠壓隊數",
    ]
    rows3 = [
        [
            c["label"],
            *[s if s is not None else "-" for s in c["score_series"]],
            c["score_delta"] if c["score_delta"] is not None else "-",
            c["latest_tied_count"],
        ]
        for c in trend.get("score_cutoff_trends", [])
    ]
    if rows3:
        _style_table(ws3, h3, rows3, start_row=1)
    flow_start = len(rows3) + 4
    h_flow = ["副角色切換流向（職業）", "換入次數 (+)", "換出次數 (-)", "淨流入 (換入-換出)"]
    rows_flow = [
        [f["occupation"], f["added_count"], f["removed_count"], f["net_flow"]]
        for f in trend.get("swap_occ_flow", [])
    ]
    if rows_flow:
        _style_table(ws3, h_flow, rows_flow, start_row=flow_start)
    ws3.freeze_panes = "A2"
    _autofit_columns(ws3)

    # 5. Roster Changes (Member 2nd-Character Switches)
    ws4 = wb.create_sheet("Roster Changes")
    h4 = [
        "戰隊名稱",
        "前期",
        "後期",
        "前期排名",
        "後期排名",
        "名次變化(正=升)",
        "積分成長(ΔScore)",
        "切換副角色明細",
        "切換前陣容",
        "切換後陣容",
    ]
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
    title = trend.get("trend_title", "女武神聯賽跨期積分榜與趨勢")
    occ_trends = trend.get("occupation_trends", [])
    if not occ_trends:
        return created

    short_l0 = labels[0][:10]
    short_l1 = labels[-1][:10]

    # Card 1: Regular-Sample Occupation Avg Rank Evolution (Dumbbell Chart: Period 1 -> Latest)
    reg_occs = [
        r for r in occ_trends
        if not r.get("low_sample")
        and r.get("first_avg_rank") is not None
        and r.get("latest_avg_rank") is not None
    ]
    reg_sorted = sorted(reg_occs, key=lambda r: float(r["latest_avg_rank"]))
    items = list(reversed(reg_sorted))

    fig, ax = plt.subplots(figsize=(11.5, max(5.8, len(items) * 0.52)), facecolor="#0f172a")
    ax.set_facecolor("#162033")
    if items:
        y = np.arange(len(items))
        r_first = [float(r["first_avg_rank"]) for r in items]
        r_last = [float(r["latest_avg_rank"]) for r in items]

        ax.axvline(100.5, color="#475569", linestyle="--", linewidth=1.2, label="全場平均線 (#100.5)")
        for idx, r in enumerate(items):
            f_val = r_first[idx]
            l_val = r_last[idx]
            gain = float(r["avg_rank_gain"] or 0.0)
            col = "#4ade80" if gain >= 1.0 else "#f87171" if gain <= -1.0 else "#38bdf8"
            ax.plot([f_val, l_val], [idx, idx], color=col, linewidth=3.0, zorder=2)
            ax.scatter(
                [f_val],
                [idx],
                color="#64748b",
                s=72,
                zorder=3,
                label=f"{short_l0} 均排" if idx == len(items) - 1 else "",
            )
            ax.scatter(
                [l_val],
                [idx],
                color=col,
                s=115,
                marker="D",
                zorder=4,
                label=f"{short_l1} 均排" if idx == len(items) - 1 else "",
            )
            txt = f"#{f_val:.1f} → #{l_val:.1f} ({gain:+.1f}名｜Top30 {r['latest_top30_presence']*100:.0f}%)"
            offset = -1.6 if l_val <= f_val else 1.6
            ha = "left" if l_val <= f_val else "right"
            ax.text(l_val + offset, idx + 0.16, txt, color="#f8fafc", fontsize=9.0, fontweight="bold", ha=ha, va="bottom")

        ax.set_yticks(y)
        ax.set_yticklabels(
            [f"{r['occupation']} ({r['team_count_series'][-1]}隊)" for r in items],
            color="#f8fafc",
            fontsize=10.3,
            fontweight="bold",
        )
        all_v = r_first + r_last
        ax.set_xlim(max(all_v) + 18, max(1, min(all_v) - 24))  # Right side = higher rank (#1)
        ax.set_xlabel("持有該職業戰隊之平均排名（越靠右側代表平均排名越高 →）", color="#e2e8f0", fontsize=10.8)
        ax.tick_params(axis="x", colors="#cbd5e1")
        ax.grid(True, color="#334155", linestyle=":", alpha=0.6)
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.legend(loc="lower left", facecolor="#0f172a", edgecolor="#475569", labelcolor="#f8fafc", fontsize=9.5)
        ax.set_title(
            f"{title}｜正規樣本職業 (>=5%) 跨期平均排名演變（{short_l0} → {short_l1}）",
            color="#ffffff",
            fontsize=13.0,
            fontweight="bold",
            pad=14,
        )
    fig.tight_layout()
    p1 = out_dir / "01_meta_trend_lines.png"
    fig.savefig(str(p1), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    created.append(str(p1))

    # Card 2: Occupation Strength Momentum (Regular-Sample on Top, Low-Sample <5% Separated at Bottom in Muted Gray)
    reg_m = sorted(
        [r for r in occ_trends if not r.get("low_sample")],
        key=lambda r: float(r["avg_rank_gain"] or 0.0),
    )
    low_m = sorted(
        [r for r in occ_trends if r.get("low_sample")],
        key=lambda r: float(r["avg_rank_gain"] or 0.0),
    )
    # In horizontal bar chart, y=0 is bottom -> put low_m first (bottom), then reg_m (top, highest gain at very top)
    movers = low_m + reg_m
    y = np.arange(len(movers))
    gains = [float(r["avg_rank_gain"] or 0.0) for r in movers]
    colors = [
        "#64748b"
        if r.get("low_sample")
        else ("#4ade80" if float(r["avg_rank_gain"] or 0.0) >= 1.0 else "#f87171" if float(r["avg_rank_gain"] or 0.0) <= -1.0 else "#38bdf8")
        for r in movers
    ]

    fig, ax = plt.subplots(figsize=(11.2, max(6.0, len(movers) * 0.46)), facecolor="#0f172a")
    ax.set_facecolor("#162033")
    ax.axvline(0, color="#94a3b8", linewidth=1.2)
    bars = ax.barh(y, gains, color=colors, height=0.62)

    if low_m and reg_m:
        sep_y = len(low_m) - 0.5
        ax.axhline(sep_y, color="#f59e0b", linestyle="--", linewidth=1.1, alpha=0.75)
        ax.text(
            0.01,
            sep_y - 0.08,
            "▼ 以下為樣本偏小 (<5%) 職業，波動幅度僅供參考",
            transform=ax.get_yaxis_transform(),
            color="#fbbf24",
            fontsize=8.6,
            fontweight="bold",
            va="top",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(
        [
            f"{r['occupation']} (樣本小 n={r['team_count_series'][-1]})" if r.get("low_sample") else r["occupation"]
            for r in movers
        ],
        color="#f8fafc",
        fontsize=10.2,
        fontweight="bold",
    )
    max_abs = max(max(abs(g) for g in gains), 5.0)
    ax.set_xlim(-max_abs * 1.55, max_abs * 1.55)
    for b, r in zip(bars, movers):
        g = float(r["avg_rank_gain"] or 0.0)
        ha = "left" if g >= 0 else "right"
        pad = max_abs * 0.03 if g >= 0 else -max_abs * 0.03
        t30_d = r.get("top30_presence_delta", 0.0) * 100
        f_r = f"#{r['first_avg_rank']}" if r.get("first_avg_rank") is not None else "-"
        l_r = f"#{r['latest_avg_rank']}" if r.get("latest_avg_rank") is not None else "-"
        lbl_txt = (
            f"{g:+.1f}名 ({f_r}→{l_r}｜樣本偏小 n={r['team_count_series'][0]}→{r['team_count_series'][-1]})"
            if r.get("low_sample")
            else f"{g:+.1f}名 ({f_r}→{l_r}｜爬升率{r.get('climber_rate',0)*100:.0f}%｜Top30 {t30_d:+.1f}%)"
        )
        ax.text(
            g + pad,
            b.get_y() + b.get_height() / 2,
            lbl_txt,
            va="center",
            ha=ha,
            color="#cbd5e1" if r.get("low_sample") else "#f8fafc",
            fontsize=8.6,
            fontweight="bold",
        )
    ax.set_xlabel(f"持有該職業戰隊之平均排名爬升量：{short_l0} → {short_l1}（正值＝整體名次上升）", color="#e2e8f0", fontsize=10.5)
    ax.tick_params(axis="x", colors="#cbd5e1")
    ax.grid(axis="x", color="#334155", linestyle=":", alpha=0.6)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.set_title(
        f"{title}｜各職業實戰強度動能榜（平均名次爬升 ＆ Top 30 滲透率）",
        color="#ffffff",
        fontsize=13.0,
        fontweight="bold",
        pad=14,
    )
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
        f"## 🏆 {trend['trend_title']}",
        f"- **賽制背景**：成員鎖定、每人最多創建 2 隻角色｜**對比期數**：{' → '.join(labels)}（追蹤 {sc['tracked_teams']} 隊｜固定陣容 {sc.get('locked_roster_teams', 0)} 隊｜切換副角 {sc.get('swapped_roster_teams', sc['roster_change_events'])} 隊｜新進榜 {sc.get('new_entries', 0)} 隊）",
        "",
        f"### 👑 聯賽當下 Top 10 即時積分排行榜（以 {labels[-1]} 最新排名為主軸）",
    ]
    for t in trend.get("league_standings", [])[:10]:
        sc_txt = f"{t['latest_score']}分" if t["latest_score"] is not None else "-"
        if t.get("recent_score_delta") is not None:
            sc_txt += f" ({t['recent_score_delta']:+d})"
        lines.append(
            f"- **#{t['latest_rank']} {t['team_name']}**（`{t['status']}`｜前期 #{t['prev_rank'] or '-'}｜積分 **{sc_txt}**）：`{t['latest_roster']}`"
        )

    cutoffs = trend.get("score_cutoff_trends", [])
    if cutoffs:
        lines.extend(["", "### 🎯 關鍵排名積分門檻線跨期演變"])
        for c in cutoffs:
            d_txt = f" ({c['score_delta']:+d}分)" if c["score_delta"] is not None else ""
            f_sc = c["first_score"] if c["first_score"] is not None else "-"
            l_sc = c["latest_score"] if c["latest_score"] is not None else "-"
            lines.append(
                f"- **{c['label']} 門檻**：`{f_sc}` → **{l_sc} 分**{d_txt}（最新期同分擠壓 {c['latest_tied_count']} 隊）"
            )

    reg_occs = [r for r in trend["occupation_trends"] if not r.get("low_sample")]
    lines.extend(["", "### 📊 單一職業實戰強度動能 Top 5（已排除 <5% 低樣本干擾）"])
    for r in reg_occs[:5]:
        g = r["avg_rank_gain"] or 0.0
        c2_txt = (
            f"｜雙職業均排變化 {r['copy2_rank_gain']:+.1f}名"
            if r.get("copy2_rank_gain") is not None and not r.get("copy2_low_sample")
            else ""
        )
        lines.append(
            f"- **{r['occupation']}**（{r['trend_tag']}）：持有戰隊均排 **#{r['first_avg_rank']} → #{r['latest_avg_rank']} ({g:+.1f}名)**｜爬升比例 **{r.get('climber_rate',0)*100:.0f}%**｜Top30 佔比 `{r.get('first_top30_presence',0)*100:.1f}%→{r.get('latest_top30_presence',0)*100:.1f}%`{c2_txt}"
        )

    flow = trend.get("swap_occ_flow", [])
    if flow:
        top_in = [f for f in flow if f["net_flow"] > 0][:4]
        top_out = sorted([f for f in flow if f["net_flow"] < 0], key=lambda x: x["net_flow"])[:4]
        svl = trend.get("swap_vs_locked", {})
        lk = svl.get("locked", {})
        sw = svl.get("swapped", {})
        lines.extend(["", "### 🔄 成員副角色（二號角）切換流向與實戰效益"])
        lines.append(
            f"- **固定陣容 ({lk.get('count', 0)}隊)** 平均淨變化 `{lk.get('avg_rank_change', 0):+.1f}名`（爬升率 {lk.get('climber_rate', 0)*100:.0f}%） vs **切換副角 ({sw.get('count', 0)}隊)** 平均淨變化 `{sw.get('avg_rank_change', 0):+.1f}名`（爬升率 {sw.get('climber_rate', 0)*100:.0f}%）"
        )
        if top_in:
            lines.append("- **最多隊伍換入**：" + "、".join(f"**{x['occupation']}** (+{x['added_count']}/-{x['removed_count']}，淨 +{x['net_flow']})" for x in top_in))
        if top_out:
            lines.append("- **最多隊伍換出**：" + "、".join(f"**{x['occupation']}** (+{x['added_count']}/-{x['removed_count']}，淨 {x['net_flow']})" for x in top_out))

    climbers = trend.get("top_climbers", [])[:5]
    if climbers:
        lines.extend(["", "### 🚀 本期最強爬升黑馬戰隊 Top 5"])
        for t in climbers:
            mode = f"切換副角色 `{t['roster_change_notes']}`" if t["roster_changed"] else "🔒 原陣容未換角直衝"
            sc_d = f"｜+{t['net_score_delta']}分" if t.get("net_score_delta") is not None else ""
            lines.append(
                f"- **#{t['latest_rank']} {t['team_name']}**（**#{t['first_rank']} → #{t['latest_rank']}，狂升 +{t['net_rank_change']} 名**{sc_d}｜{mode}）"
            )

    text = "\n".join(lines).strip() + "\n"
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text


def _encode_png_b64(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def generate_trend_html(
    trend: dict[str, Any],
    output_path: str | Path,
    cards_dir: str | Path | None = None,
) -> Path:
    icons_b64 = _load_icon_db_b64()
    embedded_cards: dict[str, str] = {}
    if cards_dir is not None:
        cdir = Path(cards_dir)
        for key, fname in [
            ("occ_dumbbell", "01_meta_trend_lines.png"),
            ("class_momentum", "02_meta_movers_delta.png"),
        ]:
            fp = cdir / fname
            if fp.is_file():
                embedded_cards[key] = _encode_png_b64(fp)

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "trend": trend,
        "icons": icons_b64,
        "cards": embedded_cards,
    }
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    safe_title = html.escape(trend.get("trend_title", "女武神聯賽跨期積分榜與趨勢"))
    doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_title}</title>
<style>
  :root {{ --bg:#0b1120; --card:#131c31; --card2:#1c2842; --text:#f8fafc; --muted:#94a3b8; --accent:#38bdf8; --accent2:#f59e0b; --green:#4ade80; --red:#f87171; --border:#273552; }}
  * {{ box-sizing:border-box; }}
  html, body {{ overflow-x:hidden; }}
  body {{ margin:0; font-family:"Microsoft JhengHei","Segoe UI",sans-serif; background:var(--bg); color:var(--text); line-height:1.5; }}
  .wrap {{ max-width:1260px; margin:0 auto; padding:24px 16px 60px; }}
  h1 {{ margin:0 0 6px; font-size:1.55rem; }}
  .sub {{ color:var(--muted); font-size:.9rem; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr)); gap:12px; margin:16px 0; }}
  .kpi {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:13px 16px; min-width:0; }}
  .kpi .lbl {{ color:var(--muted); font-size:.82rem; }}
  .kpi .val {{ font-size:1.2rem; font-weight:700; color:var(--accent); margin-top:4px; }}
  .tabs {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
  .tab {{ background:var(--card); color:var(--muted); border:1px solid var(--border); padding:9px 15px; border-radius:999px; cursor:pointer; font-weight:600; font-size:.9rem; }}
  .tab.active {{ background:var(--accent); color:#0b1120; border-color:var(--accent); }}
  .panel {{ display:none; }}
  .panel.active {{ display:block; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px; margin:16px 0; }}
  .card h2 {{ margin:0 0 10px; font-size:1.12rem; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:.87rem; }}
  th,td {{ padding:8px 10px; border-bottom:1px solid var(--border); text-align:left; }}
  th {{ background:#0f172a; color:#cbd5e1; position:sticky; top:0; z-index:2; }}
  tr.team-row {{ cursor:pointer; }}
  tr.team-row:hover td {{ background:rgba(56,189,248,.09); }}
  tr.team-row.is-my-team td {{ background:rgba(74,222,128,.11); }}
  tr.low-sample-row td {{ opacity:.72; }}
  .table-wrap {{ overflow-x:auto; max-height:660px; -webkit-overflow-scrolling:touch; }}
  .mobile-swipe-hint {{ display:none; font-size:.78rem; color:var(--accent); margin:4px 0 6px; text-align:right; }}
  .desktop-only-hint {{ display:inline; }}
  .pos {{ color:var(--green); font-weight:700; }}
  .neg {{ color:var(--red); font-weight:700; }}
  .ico {{ width:24px; height:24px; border-radius:50%; object-fit:cover; vertical-align:middle; border:1px solid rgba(255,255,255,.15); }}
  .pill {{ display:inline-flex; align-items:center; gap:4px; background:var(--card2); padding:2px 8px; border-radius:999px; font-size:.79rem; margin:2px; }}
  .pill.dp {{ border:1px solid rgba(245,158,11,.6); background:rgba(245,158,11,.15); }}
  .tag {{ padding:2px 8px; border-radius:999px; font-size:.78rem; font-weight:700; display:inline-block; background:var(--card2); }}
  .tag-warn {{ background:rgba(148,163,184,.18); color:#cbd5e1; border:1px solid rgba(148,163,184,.35); }}
  .filter-bar {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; align-items:center; }}
  .controls {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:10px; align-items:center; }}
  .search-inp {{ flex:1 1 260px; min-width:0; }}
  .chip-btn {{ background:#0f172a; color:var(--muted); border:1px solid var(--border); border-radius:999px; padding:5px 12px; font-size:.82rem; cursor:pointer; font-weight:600; }}
  .chip-btn.active {{ background:rgba(56,189,248,.2); color:#7dd3fc; border-color:var(--accent); }}
  .preset-btn {{ background:var(--card2); color:var(--text); border:1px solid var(--accent); border-radius:8px; padding:6px 12px; cursor:pointer; font-weight:600; font-size:.83rem; }}
  .preset-btn:hover {{ background:rgba(56,189,248,.2); }}
  input, select {{ background:#0b1120; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 12px; font-size:.9rem; }}
  .grid-2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr)); gap:14px; }}
  .my-team-bar {{ background:rgba(16,185,129,.08); border:1px solid rgba(74,222,128,.45); border-radius:12px; padding:11px 14px; margin-bottom:12px; }}
  .scout-box {{ background:#0f172a; border:1px solid var(--accent); border-radius:12px; padding:14px 16px; margin:4px 0; }}
  .scout-cols {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr)); gap:12px; margin-top:10px; }}
  .scout-col {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:11px 13px; font-size:.86rem; line-height:1.65; min-width:0; }}
  .scout-col.threat {{ border-left:3px solid var(--accent2); }}
  .scout-col.gap {{ border-left:3px solid var(--green); }}
  .scout-col h4 {{ margin:0 0 6px; font-size:.9rem; }}
  .h2h-box {{ background:linear-gradient(135deg,rgba(56,189,248,.11),rgba(74,222,128,.08)); border:1px solid rgba(56,189,248,.55); border-radius:10px; padding:11px 14px; margin:10px 0 8px; }}
  .h2h-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,185px),1fr)); gap:8px; margin-top:8px; }}
  .h2h-item {{ background:#0b1120; border:1px solid var(--border); border-radius:8px; padding:7px 10px; font-size:.82rem; min-width:0; }}
  .h2h-item .h-lbl {{ color:var(--muted); font-size:.75rem; margin-bottom:2px; }}
  .h2h-adv {{ border-color:rgba(74,222,128,.55); }}
  .h2h-warn {{ border-color:rgba(248,113,113,.55); }}
  .cutoff-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,175px),1fr)); gap:10px; margin:12px 0; }}
  .cutoff-pill {{ background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:11px 13px; min-width:0; }}
  .cutoff-pill .c-rank {{ color:var(--muted); font-size:.8rem; font-weight:600; }}
  .cutoff-pill .c-score {{ font-size:1.18rem; font-weight:800; color:var(--accent2); margin:3px 0; }}
  .cutoff-pill .c-tie {{ font-size:.78rem; color:#cbd5e1; }}
  .flow-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr)); gap:8px; margin-top:10px; }}
  .flow-item {{ background:#0f172a; border:1px solid var(--border); border-radius:9px; padding:9px 11px; font-size:.84rem; min-width:0; }}
  .zoomable-img {{ cursor:zoom-in; transition:transform .15s,box-shadow .15s; border-radius:12px; border:1px solid var(--border); }}
  .zoomable-img:hover {{ box-shadow:0 0 0 2px var(--accent); }}
  .zoom-modal {{ position:fixed; inset:0; background:rgba(5,10,20,.94); z-index:9999; display:none; flex-direction:column; user-select:none; }}
  .zoom-modal.open {{ display:flex; }}
  .zoom-toolbar {{ display:flex; justify-content:space-between; align-items:center; padding:10px 16px; background:#0f172a; border-bottom:1px solid var(--border); flex-wrap:wrap; gap:8px; }}
  .zoom-stage {{ flex:1; overflow:hidden; position:relative; display:flex; align-items:center; justify-content:center; cursor:grab; touch-action:none; }}
  .zoom-stage.dragging {{ cursor:grabbing; }}
  .zoom-stage img {{ max-width:94vw; max-height:86vh; transform-origin:center center; transition:transform .04s linear; pointer-events:none; border-radius:8px; }}

  /* ================= Mobile-Friendly Responsive Layout (<= 768px) ================= */
  @media (max-width: 768px) {{
    .wrap {{ padding:10px 10px 44px; }}
    h1 {{ font-size:1.22rem; }}
    .sub {{ font-size:.82rem; }}
    .kpis {{ grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin:12px 0; }}
    .kpi {{ padding:10px 11px; border-radius:10px; }}
    .kpi .lbl {{ font-size:.74rem; }}
    .kpi .val {{ font-size:.96rem; line-height:1.3; }}

    .tabs {{
      position:sticky; top:0; z-index:30;
      background:rgba(11,17,32,.95); backdrop-filter:blur(8px);
      margin:0 -10px 12px; padding:8px 10px;
      border-bottom:1px solid var(--border);
      flex-wrap:nowrap; overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:none;
    }}
    .tabs::-webkit-scrollbar {{ display:none; }}
    .tab {{ white-space:nowrap; flex-shrink:0; padding:8px 12px; font-size:.83rem; }}

    .card {{ padding:13px 11px; border-radius:12px; margin:12px 0; }}
    .card h2 {{ font-size:1rem; margin-bottom:8px; }}
    .desktop-only-hint {{ display:none !important; }}
    .mobile-swipe-hint {{ display:block; }}

    .filter-bar {{
      flex-wrap:nowrap; overflow-x:auto; -webkit-overflow-scrolling:touch;
      scrollbar-width:none; padding-bottom:2px; margin-bottom:8px;
    }}
    .filter-bar::-webkit-scrollbar {{ display:none; }}
    .filter-bar > * {{ flex-shrink:0; white-space:nowrap; }}
    .chip-btn {{ padding:6px 11px; font-size:.8rem; min-height:34px; }}

    .controls {{ gap:7px; }}
    .search-inp {{ flex:1 0 100%; width:100%; font-size:.92rem; padding:9px 11px; }}
    .controls select {{ flex:1 1 46%; min-width:0; font-size:.84rem; padding:8px 9px; }}
    #standingsCount {{ flex:1 0 100%; font-size:.78rem; }}
    #myTeamTrendSelect {{ width:100%; max-width:none !important; }}

    /* Transform 200-team Standings Table into Zero-Horizontal-Scroll Mobile Cards! */
    .raw-table-wrap {{ max-height:none; overflow-x:visible; }}
    #standingsTbl, #standingsTbl tbody {{ display:block; width:100%; }}
    #standingsTbl thead {{ display:none; }}
    #standingsTbl tr.team-row {{
      display:flex; flex-wrap:wrap; align-items:center; gap:4px 7px;
      background:#0f172a; border:1px solid var(--border); border-radius:11px;
      padding:10px 11px; margin-bottom:8px;
    }}
    #standingsTbl tr.team-row.is-my-team {{
      background:rgba(74,222,128,.12); border-color:rgba(74,222,128,.55);
    }}
    #standingsTbl tr.team-row td {{ display:block; border:0; padding:0; background:transparent !important; white-space:normal; }}
    #standingsTbl tr.team-row td.col-rank {{ order:1; font-size:.94rem; color:var(--accent); min-width:34px; }}
    #standingsTbl tr.team-row td.col-status {{
      order:2; font-size:.75rem; background:var(--card2) !important; padding:2px 7px; border-radius:999px;
    }}
    #standingsTbl tr.team-row td.col-score {{
      order:3; margin-left:auto; font-size:.78rem; font-weight:700; color:var(--accent2);
      background:rgba(245,158,11,.14) !important; border:1px solid rgba(245,158,11,.35);
      padding:2px 7px; border-radius:999px;
    }}
    #standingsTbl tr.team-row td.col-name {{ order:4; flex:1 0 100%; font-size:.94rem; word-break:break-word; margin-top:2px; }}
    #standingsTbl tr.team-row td.col-prev {{ order:5; font-size:.76rem; color:var(--muted); }}
    #standingsTbl tr.team-row td.col-swap {{ order:6; font-size:.76rem; }}
    #standingsTbl tr.team-row td.col-occs {{
      order:7; flex:1 0 100%; margin-top:4px; padding-top:6px;
      border-top:1px dashed rgba(148,163,184,.22);
      display:flex; flex-wrap:wrap; gap:4px;
    }}
    #standingsTbl tr.scout-detail-row {{ display:block; margin:-4px 0 10px; }}
    #standingsTbl tr.scout-detail-row > td {{ display:block; padding:0 !important; border:0; background:transparent !important; }}
    .pill {{ padding:2px 6px; font-size:.74rem; gap:3px; margin:1px; }}
    .ico {{ width:20px; height:20px; }}

    .scout-box {{ padding:11px; border-radius:10px; }}
    .scout-cols {{ grid-template-columns:1fr; gap:8px; }}
    .scout-col {{ padding:10px 11px; font-size:.83rem; line-height:1.6; }}
    .h2h-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px; }}
    .h2h-item {{ padding:6px 8px; font-size:.78rem; }}

    /* Statistical tables: sticky first col + crisp nowrap */
    .stat-table-wrap {{ max-height:520px; }}
    .stat-table-wrap table {{ font-size:.79rem; }}
    .stat-table-wrap th, .stat-table-wrap td {{ padding:7px 7px; white-space:nowrap; }}
    .stat-table-wrap th:first-child, .stat-table-wrap td:first-child {{
      position:sticky; left:0; z-index:2; background:var(--card);
      box-shadow:2px 0 6px rgba(0,0,0,.38);
    }}
    .stat-table-wrap th:first-child {{ z-index:4; background:#0f172a; }}

    .cutoff-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }}
    .cutoff-pill {{ padding:9px 10px; }}
    .cutoff-pill .c-score {{ font-size:1.02rem; }}
    .flow-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px; }}

    .zoom-toolbar {{ padding:8px 10px; gap:6px; }}
    #zoomModalTitle {{ font-size:.84rem; }}
    .zoom-toolbar .chip-btn, .zoom-toolbar .preset-btn {{ padding:5px 9px; font-size:.78rem; }}
    .zoom-stage img {{ max-width:98vw; max-height:82vh; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <!-- GLA_NAV_START --><!-- GLA_NAV_END -->
  <h1>🏆 {safe_title}</h1>
  <div class="sub" id="sub"></div>
  <section class="kpis" id="kpiRow"></section>

  <nav class="tabs">
    <button class="tab active" data-tab="standings">🏆 1. 聯賽積分榜＆對手追蹤</button>
    <button class="tab" data-tab="classes">📊 2. 職業強度動能＆雙職業趨勢</button>
    <button class="tab" data-tab="cutoffs">📈 3. 積分門檻線＆升降換角榜</button>
  </nav>

  <!-- TAB 1: LEAGUE STANDINGS & SCOUT -->
  <section id="tab-standings" class="panel active">
    <div class="my-team-bar" id="myTeamTrendBar">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <div id="myTeamTrendStatus" style="font-size:.88rem"></div>
        <div style="display:flex;flex-wrap:wrap;gap:7px;align-items:center">
          <select id="myTeamTrendSelect" style="font-size:.82rem;padding:6px 10px;max-width:250px"></select>
          <button class="chip-btn" id="btnJumpMyTeam" type="button" style="display:none">📍 定位我方戰隊</button>
          <button class="chip-btn" id="btnClearMyTeamTrend" type="button" style="display:none;border-color:rgba(248,113,113,.55);color:#fca5a5">✖ 解除鎖定</button>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>🏆 聯賽即時積分排行榜（依最新一期 #1 ～ #200 排序）<span class="sub desktop-only-hint" style="font-size:.82rem">💡 點擊任一隊伍列展開歷期走勢、對位比較與破綻分析</span></h2>
      <div class="filter-bar" id="standingsFilterBar">
        <button class="chip-btn active" data-f="all">🌐 全部當下排名</button>
        <button class="chip-btn" data-f="top30">👑 Top 30 頂尖強隊</button>
        <button class="chip-btn" data-f="climb">🚀 本期大爬升 (▲+5以上)</button>
        <button class="chip-btn" data-f="fall">🔻 本期下滑 (▼-5以下)</button>
        <button class="chip-btn" data-f="new">🆕 本期新進榜</button>
        <button class="chip-btn" data-f="swapped">🔄 有切換副角色</button>
        <button class="chip-btn" data-f="locked">🔒 原陣容未換角</button>
      </div>
      <div class="controls">
        <input id="qStandings" class="search-inp" type="search" placeholder="搜尋戰隊名稱、排名或職業...">
        <select id="occFilter"><option value="">篩選含指定職業（全部）</option></select>
        <span class="sub" id="standingsCount"></span>
      </div>
      <div class="table-wrap raw-table-wrap"><table id="standingsTbl"></table></div>
    </div>
  </section>

  <!-- TAB 2: OCCUPATION MOMENTUM & DOUBLE-PICK TRENDS -->
  <section id="tab-classes" class="panel">
    <div class="card">
      <h2>📊 正規樣本職業（≥5%）跨期平均排名演變 <span class="sub desktop-only-hint" style="font-size:.82rem">💡 點擊圖卡可放大縮放</span></h2>
      <div id="dumbbellCardWrap" style="margin-bottom:12px"></div>
      <div class="sub" style="background:#0f172a;border:1px solid var(--border);border-radius:10px;padding:10px 14px;line-height:1.65">
        💡 <b>統計閱讀原則：</b>鎖定成員賽制下，全服職業出場率變動較小，重點應看<b>「持有該職業戰隊的均排爬升（Δ均排）」</b>與<b>「Top 30 高端滲透率變化」</b>。<br>
        出場率 <b>&lt; 5%</b>（如 5 隊以下）的冷門職業因樣本數極少，單一隊伍勝負就會劇烈拉扯平均值，已自動標記 <code>⚠️ 樣本偏小</code> 並於圖表底部隔離顯示，避免誤導判斷。
      </div>
    </div>

    <div class="card">
      <h2>🔥 職業實戰強度動能 ＆ 單/雙職業跨期明細表 <span class="sub desktop-only-hint" style="font-size:.82rem">💡 點擊圖卡可放大縮放</span></h2>
      <div id="classCardWrap" style="margin-bottom:12px"></div>
      <div class="mobile-swipe-hint">← 左右滑動表格查看完整數據 →</div>
      <div class="table-wrap stat-table-wrap"><table id="metaTbl"></table></div>
    </div>

    <div class="card">
      <h2>✌️ 戰隊「雙職業組數」結構跨期演變（0 / 1 / 2 / 3 組雙職業）</h2>
      <div class="mobile-swipe-hint">← 左右滑動表格查看完整數據 →</div>
      <div class="table-wrap stat-table-wrap"><table id="dpTbl"></table></div>
    </div>
  </section>

  <!-- TAB 3: SCORE CUTOFFS SHIFT & CLIMBERS / ALT-CHAR SWAPS -->
  <section id="tab-cutoffs" class="panel">
    <div class="card">
      <h2>🎯 關鍵排名積分門檻線跨期演變（教練週目標參考）</h2>
      <div class="sub" id="scoreVelocitySub"></div>
      <div class="cutoff-grid" id="cutoffShiftGrid"></div>
    </div>

    <div class="card">
      <h2>🔄 成員副角色（二號角）切換流向 ＆ 實戰效益</h2>
      <div id="swapCompareBox" class="kpis" style="margin:10px 0 12px"></div>
      <div class="sub" style="margin-bottom:6px"><b>各職業副角切換淨流向（綠色＝最多隊伍換入、紅色＝最多隊伍換出）：</b></div>
      <div class="flow-grid" id="swapFlowGrid"></div>
    </div>

    <div class="grid-2">
      <div class="card">
        <h2>🚀 本期最強爬升黑馬榜 Top 15</h2>
        <div class="mobile-swipe-hint">← 左右滑動查看完整資訊 →</div>
        <div class="table-wrap stat-table-wrap"><table id="climbersTbl"></table></div>
      </div>
      <div class="card">
        <h2>🔻 本期排名退化警報榜 Top 15</h2>
        <div class="mobile-swipe-hint">← 左右滑動查看完整資訊 →</div>
        <div class="table-wrap stat-table-wrap"><table id="fallersTbl"></table></div>
      </div>
    </div>

    <div class="card">
      <h2>📋 成員副角色（二號角）切換完整明細</h2>
      <div class="sub" style="margin-bottom:10px">在鎖定成員前提下，名單職業變動代表隊員切換了預先練好的第 2 隻角色上場。此表追蹤各隊切換副角後的名次與積分效益：</div>
      <div class="mobile-swipe-hint">← 左右滑動表格查看完整數據 →</div>
      <div class="table-wrap stat-table-wrap"><table id="changeTbl"></table></div>
    </div>
  </section>
</div>

<div class="zoom-modal" id="imgZoomModal">
  <div class="zoom-toolbar">
    <div>
      <b id="zoomModalTitle" style="color:var(--accent)">圖表放大檢視</b>
      <span class="sub desktop-only-hint" style="margin-left:10px">💡 滾輪：自由縮放 ｜ 按住滑鼠左鍵：拖曳平移 ｜ 雙擊圖片：切換 100% / 220%</span>
    </div>
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <button class="chip-btn" id="btnZoomOut">➖</button>
      <span id="zoomPctLabel" style="min-width:44px;text-align:center;font-weight:700;font-size:.84rem">100%</span>
      <button class="chip-btn" id="btnZoomIn">➕</button>
      <button class="chip-btn" id="btnZoomReset">🔄 100%</button>
      <a class="preset-btn" id="btnZoomDownload" download="trend_chart.png" style="text-decoration:none;padding:5px 10px">💾 <span class="desktop-only-hint">下載圖卡</span></a>
      <button class="preset-btn" id="btnZoomClose" style="background:rgba(248,113,113,.2);border-color:var(--red)">✖ 關閉</button>
    </div>
  </div>
  <div class="zoom-stage" id="zoomStage">
    <img id="zoomModalImg" src="" alt="Zoomed Chart">
  </div>
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

// Top KPIs (strictly excluding <5% low-sample classes from "最強動能職業")
const regOccs = (T.occupation_trends || []).filter(r => !r.low_sample);
const bestOcc = regOccs[0] || (T.occupation_trends || [])[0];
const topTeam = (T.league_standings || [])[0];
const top10Cut = (T.score_cutoff_trends || []).find(c => c.rank_milestone === 10);
const scCnt = T.summary_counts || {{}};
document.getElementById('kpiRow').innerHTML = [
  ['當下聯賽榜首', topTeam ? `#1 ${{topTeam.team_name}} (${{topTeam.latest_score ?? '-'}}分)` : '-'],
  ['正規樣本最強動能職業', bestOcc ? `${{bestOcc.occupation}} (均排${{bestOcc.avg_rank_gain >= 0 ? '+' : ''}}${{bestOcc.avg_rank_gain}}名)` : '-'],
  ['Top 10 門檻線變化', top10Cut ? `${{top10Cut.first_score ?? '-'}} → ${{top10Cut.latest_score ?? '-'}}分 (${{top10Cut.score_delta >= 0 ? '+' : ''}}${{top10Cut.score_delta ?? 0}})` : '-'],
  ['固定陣容 / 切換副角', `${{scCnt.locked_roster_teams || 0}} 隊 / ${{scCnt.swapped_roster_teams || scCnt.roster_change_events || 0}} 隊`],
].map(([l,v]) => `<div class="kpi"><div class="lbl">${{l}}</div><div class="val">${{esc(v)}}</div></div>`).join('');

// Shared C3 My-Team Lock (syncs seamlessly with single-period report via localStorage['gla_my_team_v1'])
const MY_TEAM_KEY = 'gla_my_team_v1';
const G2_DUELISTS = ['賢者', '流氓', '騎士', '武僧'];
const FRONTLINES = ['騎士', '十字'];
const standings = T.league_standings || [];
let myTeam = null;

function loadMyTeam() {{
  try {{
    const raw = localStorage.getItem(MY_TEAM_KEY);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (obj && Array.isArray(obj.occupations) && obj.occupations.length) return obj;
  }} catch (e) {{}}
  return null;
}}
function saveMyTeam(obj) {{
  myTeam = obj;
  try {{
    if (obj) localStorage.setItem(MY_TEAM_KEY, JSON.stringify(obj));
    else localStorage.removeItem(MY_TEAM_KEY);
  }} catch (e) {{}}
  renderMyTeamTrendBar();
  renderStandings();
}}
function findTeamInStandings(mt) {{
  if (!mt || !mt.team_name) return null;
  const k = mt.team_name.trim().toLowerCase();
  return standings.find(t => (t.team_name || '').trim().toLowerCase() === k) || null;
}}
function setMyTeamByRank(rank) {{
  const t = standings.find(x => x.latest_rank === rank);
  if (!t) return;
  saveMyTeam({{
    mode: 'team',
    team_name: t.team_name,
    rank: t.latest_rank,
    score: t.latest_score,
    occupations: (t.latest_occs || []).filter(Boolean),
  }});
}}
window.setMyTeamByRank = setMyTeamByRank;

function renderMyTeamTrendBar() {{
  const st = document.getElementById('myTeamTrendStatus');
  const sel = document.getElementById('myTeamTrendSelect');
  const clrBtn = document.getElementById('btnClearMyTeamTrend');
  const jmpBtn = document.getElementById('btnJumpMyTeam');
  if (!sel.options.length) {{
    sel.innerHTML = '<option value="">🛡️ 鎖定我方戰隊（跨戰報同步）...</option>' +
      standings.map(t => `<option value="${{t.latest_rank}}">#${{t.latest_rank}} ${{esc(t.team_name)}} (${{t.latest_score ?? '-'}}分)</option>`).join('');
  }}
  if (!myTeam) {{
    st.innerHTML = `🛡️ <b>教練對位追蹤（未鎖定我方隊伍）</b>：<span class="sub">選擇我方戰隊（或與單期戰報自動同步），即可即時追蹤我方名次變化並在展開對手時開啟 10 秒對位比較。</span>`;
    clrBtn.style.display = 'none';
    jmpBtn.style.display = 'none';
    sel.value = '';
    return;
  }}
  const matched = findTeamInStandings(myTeam);
  clrBtn.style.display = 'inline-block';
  jmpBtn.style.display = matched ? 'inline-block' : 'none';
  sel.value = matched ? String(matched.latest_rank) : '';
  const activeOccs = matched ? matched.latest_occs : myTeam.occupations;
  const trajHtml = matched
    ? `<span style="margin-left:6px">當下 <b style="color:var(--accent)">#${{matched.latest_rank}}</b>（<b class="${{matched.recent_rank_change>0?'pos':matched.recent_rank_change<0?'neg':'sub'}}">${{esc(matched.status)}}</b>｜積分 <b>${{matched.latest_score ?? '-'}}</b>${{matched.recent_score_delta!==null && matched.recent_score_delta!==undefined ? ` <span class="${{matched.recent_score_delta>=0?'pos':'neg'}}">(${{matched.recent_score_delta>=0?'+':''}}${{matched.recent_score_delta}})</span>` : ''}}）</span>`
    : `<span class="sub" style="margin-left:6px">（未在最新 Top 200 榜內，仍可展開對手進行 10 秒陣容對位）</span>`;
  st.innerHTML = `🛡️ <b style="color:var(--green)">我方戰隊：${{esc(myTeam.team_name)}}</b>${{trajHtml}}<div style="margin-top:4px">${{activeOccs.map(o => `<span class="pill" style="padding:2px 6px;font-size:.74rem">${{ico(o)}}${{esc(o)}}</span>`).join('')}}</div>`;
}}

document.getElementById('myTeamTrendSelect').onchange = e => {{
  const r = Number(e.target.value);
  if (r) setMyTeamByRank(r);
}};
document.getElementById('btnClearMyTeamTrend').onclick = () => saveMyTeam(null);
document.getElementById('btnJumpMyTeam').onclick = () => {{
  const m = findTeamInStandings(myTeam);
  if (!m) return;
  activeStandFilter = 'all';
  document.querySelectorAll('#standingsFilterBar .chip-btn').forEach(b => b.classList.toggle('active', b.dataset.f === 'all'));
  document.getElementById('qStandings').value = m.team_name;
  document.getElementById('occFilter').value = '';
  renderStandings();
}};

function analyzeRoster(occs) {{
  const clean = (occs || []).filter(Boolean);
  const cnt = {{}};
  clean.forEach(o => cnt[o] = (cnt[o] || 0) + 1);
  const dbl = Object.entries(cnt).filter(([,v]) => v >= 2).map(([k]) => k);
  const duelistNames = G2_DUELISTS.filter(k => (cnt[k] || 0) >= 1);
  const duelistSlots = G2_DUELISTS.reduce((s, k) => s + (cnt[k] || 0), 0);
  const frontSlots = FRONTLINES.reduce((s, k) => s + (cnt[k] || 0), 0);
  return {{
    clean, cnt, dbl,
    healers: cnt['補師'] || 0,
    alch: cnt['煉金'] || 0,
    druid: cnt['德魯伊'] || 0,
    monk: cnt['武僧'] || 0,
    duelistNames, duelistSlots, frontSlots,
  }};
}}

function buildH2hStripHtml(oppTeam) {{
  if (!myTeam) return '';
  const matchedMy = findTeamInStandings(myTeam);
  const myOccs = matchedMy ? matchedMy.latest_occs : myTeam.occupations;
  const me = analyzeRoster(myOccs);
  const op = analyzeRoster(oppTeam.latest_occs || []);
  const items = [];
  let healCls = '', healMsg = `我方 補師×${{me.healers}} vs 對手 補師×${{op.healers}}`;
  if (me.healers >= 2 && op.healers <= 1) {{ healCls = 'h2h-adv'; healMsg += ' → 🟢 G4 禁補優勢（可禁對手單補）'; }}
  else if (me.healers <= 1 && op.healers >= 2) {{ healCls = 'h2h-warn'; healMsg += ' → 🔴 對手雙補保底，我方防 G4 斷補'; }}
  items.push({{ lbl: '💉 補師 / G4 禁選位', txt: healMsg, cls: healCls }});
  let alchCls = '', alchMsg = `我方 ${{me.alch ? '有煉金×'+me.alch : '無煉金'}} vs 對手 ${{op.alch ? '有煉金×'+op.alch : '無煉金'}}`;
  if (me.alch > 0 && op.alch === 0) {{ alchCls = 'h2h-adv'; alchMsg += ' → 🟢 我方具護貝＋拆裝壓制'; }}
  else if (me.alch === 0 && op.alch > 0) {{ alchCls = 'h2h-warn'; alchMsg += ' → 🔴 我方無護貝防拆裝'; }}
  items.push({{ lbl: '⚗️ 煉金護貝對位', txt: alchMsg, cls: alchCls }});
  let drCls = '', drMsg = `我方 ${{me.druid ? '有德魯伊×'+me.druid : '無'}} vs 對手 ${{op.druid ? '有德魯伊×'+op.druid : '無'}}`;
  if (me.druid > 0 && op.druid === 0) {{ drCls = 'h2h-adv'; drMsg += ' → 🟢 5v5 團戰範圍壓制優勢'; }}
  else if (me.druid === 0 && op.druid > 0) {{ drCls = 'h2h-warn'; drMsg += ' → 🔴 須優先針對對方德魯伊'; }}
  items.push({{ lbl: '🌿 德魯伊 5v5 AOE', txt: drMsg, cls: drCls }});
  const dDiff = me.duelistSlots - op.duelistSlots;
  items.push({{
    lbl: '⚔️ G2 單挑主力池',
    txt: `我方 ${{me.duelistSlots}} 人 vs 對手 ${{op.duelistSlots}} 人${{dDiff > 0 ? ' → 🟢 人選較寬' : dDiff < 0 ? ' → 🔴 對手選擇較多' : ''}}`,
    cls: dDiff > 0 ? 'h2h-adv' : dDiff < 0 ? 'h2h-warn' : ''
  }});
  return `<div class="h2h-box">
    <div style="font-size:.86rem;font-weight:700;color:var(--accent)">⚔️ 我方 (${{esc(myTeam.team_name)}}) vs 對手 (#${{oppTeam.latest_rank}} ${{esc(oppTeam.team_name)}}) — 10 秒客觀對位</div>
    <div class="h2h-grid">${{items.map(it => `<div class="h2h-item ${{it.cls}}"><div class="h-lbl">${{it.lbl}}</div><div>${{it.txt}}</div></div>`).join('')}}</div>
  </div>`;
}}

function buildTrendScoutHtml(t) {{
  const st = analyzeRoster(t.latest_occs || []);
  const threats = [];
  const gaps = [];
  if (st.healers >= 2) threats.push('💉 <b>雙補師配置</b>：G3 即使被禁 1 補，G4 (2v2) 仍保底有補師。');
  if (st.druid >= 1) threats.push(`🌿 <b>含德魯伊${{st.druid>=2?' ×2':''}}</b>：5v5 最強範圍與控場壓力。`);
  if (st.monk >= 1) threats.push(`👊 <b>含武僧${{st.monk>=2?' ×2':''}}</b>：具備阿修羅霸凰拳單點秒殺威脅。`);
  if (st.alch >= 1) threats.push(`⚗️ <b>含煉金${{st.alch>=2?' ×2':''}}</b>：具化學保護與拆裝能力。`);
  if (st.dbl.length) threats.push(`✌️ <b>雙職業跨局輪轉</b>：<code>${{st.dbl.map(x=>x+'×2').join('、')}}</code>。`);
  if (!threats.length) threats.push('⚖️ 8 異職均衡配置，各局調度彈性平均。');

  if (st.healers === 0) gaps.push('🚨 <b>無補師陣容</b>：續航與保人能力明顯缺口。');
  else if (st.healers === 1) gaps.push('🎯 <b>僅 1 名補師（G4 禁選突破口）</b>：若 G3 出場且我方在 G4 禁補，對手 G4 將無補師。');
  if (st.alch === 0) gaps.push('🔓 <b>無煉金（無化學保護）</b>：缺乏防拆裝手段。');
  if (st.druid === 0) gaps.push('🌿 <b>無德魯伊</b>：5v5 團戰大型 AOE 與控場上限較低。');
  if (st.duelistSlots === 0) gaps.push('⚔️ <b>無常規 G2 單挑主力</b>：名單內無賢者/流氓/騎士/武僧。');
  else if (st.duelistSlots === 1) gaps.push(`⚔️ <b>G2 單挑人選單一（僅 ${{st.duelistNames[0]}}）</b>：單挑局容易預判。`);
  if (st.frontSlots === 0) gaps.push('🛡️ <b>無重裝前排（無騎士/十字）</b>：前排坦度偏軟。');
  if (st.clean.length < 8) gaps.push(`⚠️ <b>名單不足 8 人（僅 ${{st.clean.length}} 人）</b>：BO5 輪換空間受限。`);
  if (!gaps.length) gaps.push('✅ 無明顯結構性缺口，建議回歸對位與操作執行。');

  const histChips = T.labels.map((lbl, i) => {{
    const rk = (t.rank_series || [])[i];
    const sc = (t.score_series || [])[i];
    return `<span class="pill"><b>${{esc(lbl.slice(0,10))}}</b>: ${{rk===null||rk===undefined?'未進榜':'#'+rk}}${{sc!==null&&sc!==undefined?' ('+sc+'分)':''}}</span>`;
  }}).join(' → ');

  const isMine = myTeam && (myTeam.team_name || '').trim().toLowerCase() === (t.team_name || '').trim().toLowerCase();
  return `<div class="scout-box">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <div><b>🔎 #${{t.latest_rank}} ${{esc(t.team_name)}} — 跨期走勢與對手破綻速覽</b></div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button class="chip-btn ${{isMine?'active':''}}" type="button" onclick="event.stopPropagation();setMyTeamByRank(${{t.latest_rank}})">${{isMine ? '🛡️ 已鎖定為我方' : '🛡️ 設為我方戰隊'}}</button>
      </div>
    </div>
    <div style="margin-top:8px;font-size:.83rem"><b>📈 歷期軌跡：</b>${{histChips}} ${{t.roster_changed ? `<span class="tag" style="color:var(--green);margin-left:4px">🔄 ${{esc(t.roster_change_notes)}}</span>` : '<span class="sub" style="margin-left:4px">🔒 固定陣容</span>'}}</div>
    ${{buildH2hStripHtml(t)}}
    <div class="scout-cols">
      <div class="scout-col threat">
        <h4 style="color:var(--accent2)">⚠️ 對方關鍵威脅 ＆ 輪轉優勢</h4>
        ${{threats.map(x => `<div style="margin-bottom:4px">• ${{x}}</div>`).join('')}}
      </div>
      <div class="scout-col gap">
        <h4 style="color:var(--green)">🎯 對方陣容缺口（可針對破綻）</h4>
        ${{gaps.map(x => `<div style="margin-bottom:4px">• ${{x}}</div>`).join('')}}
      </div>
    </div>
  </div>`;
}}

// Tab 1: League Standings
const occSel = document.getElementById('occFilter');
(T.occupation_trends || []).forEach(r => {{
  const o = document.createElement('option');
  o.value = r.occupation;
  o.textContent = `含 ${{r.occupation}} (${{r.team_count_series[r.team_count_series.length-1]}}隊)`;
  occSel.appendChild(o);
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
  const occF = occSel.value;
  const rows = standings.filter(t => {{
    if (activeStandFilter === 'top30' && t.latest_rank > 30) return false;
    if (activeStandFilter === 'climb' && (t.recent_rank_change || 0) < 5) return false;
    if (activeStandFilter === 'fall' && (t.recent_rank_change || 0) > -5) return false;
    if (activeStandFilter === 'new' && t.appearances > 1) return false;
    if (activeStandFilter === 'locked' && (t.roster_changed || t.appearances <= 1)) return false;
    if (activeStandFilter === 'swapped' && !t.roster_changed) return false;
    if (occF && !(t.latest_occs || []).includes(occF)) return false;
    if (kw && !(String(t.latest_rank).includes(kw) || t.team_name.toLowerCase().includes(kw) || (t.latest_roster || '').toLowerCase().includes(kw))) return false;
    return true;
  }});

  document.getElementById('standingsCount').textContent = `顯示 ${{rows.length}} / ${{standings.length}} 隊（點任一列展開詳情）`;
  const prevLabels = T.labels.slice(0, -1);
  const myNameLower = myTeam && myTeam.team_name ? myTeam.team_name.trim().toLowerCase() : '';
  document.getElementById('standingsTbl').innerHTML =
    `<thead><tr><th>當下排名</th><th>本期升降</th><th>戰隊名稱</th><th>當下積分 (本期Δ)</th><th>前期排名</th><th>當下 8 人名單（金框＝雙職業）</th><th>副角色切換</th></tr></thead><tbody>` +
    rows.map(t => {{
      const rc = t.recent_rank_change || 0;
      const rcCls = rc > 0 ? 'pos' : rc < 0 ? 'neg' : 'sub';
      const scDelta = t.recent_score_delta !== null && t.recent_score_delta !== undefined
        ? `<span class="${{t.recent_score_delta>=0?'pos':'neg'}}" style="font-size:.8rem">(${{t.recent_score_delta>=0?'+':''}}${{t.recent_score_delta}})</span>`
        : '';
      const cnts = {{}};
      (t.latest_occs || []).forEach(o => cnts[o] = (cnts[o]||0)+1);
      const pills = (t.latest_occs && t.latest_occs.length)
        ? t.latest_occs.map(o => `<span class="pill ${{cnts[o]>=2?'dp':''}}">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')
        : `<span class="sub">${{esc(t.latest_roster)}}</span>`;
      const prevStr = prevLabels.map((l, idx) => {{
        const rv = (t.rank_series || [])[idx];
        return rv === null || rv === undefined ? '-' : '#' + rv;
      }}).join('→');
      const isMine = myNameLower && (t.team_name || '').trim().toLowerCase() === myNameLower;
      return `<tr class="team-row ${{isMine?'is-my-team':''}}" data-rank="${{t.latest_rank}}">
        <td class="col-rank"><b>#${{t.latest_rank}}</b></td>
        <td class="col-status ${{rcCls}}">${{esc(t.status)}}</td>
        <td class="col-name"><b>${{esc(t.team_name)}}</b>${{isMine ? ' <span class="tag" style="background:rgba(74,222,128,.22);color:#86efac;margin-left:4px">🛡️ 我方</span>' : ''}}</td>
        <td class="col-score"><b>${{t.latest_score ?? '-'}}分</b> ${{scDelta}}</td>
        <td class="col-prev sub">前期 ${{prevStr}}</td>
        <td class="col-occs">${{pills}}</td>
        <td class="col-swap sub" style="font-size:.8rem">${{t.roster_changed ? `<span class="pos">🔄 ${{esc(t.roster_change_notes)}}</span>` : (t.appearances<=1 ? '🆕 新進榜' : '🔒 固定')}}</td>
      </tr>`;
    }}).join('') + '</tbody>';

  document.querySelectorAll('#standingsTbl tr.team-row').forEach(tr => {{
    tr.onclick = () => {{
      const next = tr.nextElementSibling;
      if (next && next.classList.contains('scout-detail-row')) {{ next.remove(); return; }}
      const rk = Number(tr.dataset.rank);
      const team = standings.find(x => x.latest_rank === rk);
      if (!team) return;
      const detail = document.createElement('tr');
      detail.className = 'scout-detail-row';
      detail.innerHTML = `<td colspan="7" style="padding:8px 10px;background:#0b1120">${{buildTrendScoutHtml(team)}}</td>`;
      tr.after(detail);
    }};
  }});
}}
document.getElementById('qStandings').oninput = renderStandings;
occSel.onchange = renderStandings;
myTeam = loadMyTeam();
renderMyTeamTrendBar();
renderStandings();

// Tab 2: Occupation Strength Momentum & Double-Pick Trends
const TCARDS = D.cards || {{}};
if (TCARDS.occ_dumbbell && document.getElementById('dumbbellCardWrap')) {{
  document.getElementById('dumbbellCardWrap').innerHTML = `<img class="zoomable-img" src="${{TCARDS.occ_dumbbell}}" alt="正規樣本職業跨期平均排名演變" data-zoom-title="正規樣本職業（≥5%）跨期平均排名演變" style="width:100%;max-width:1100px;display:block;margin:0 auto">`;
}}
if (TCARDS.class_momentum && document.getElementById('classCardWrap')) {{
  document.getElementById('classCardWrap').innerHTML = `<img class="zoomable-img" src="${{TCARDS.class_momentum}}" alt="各職業實戰強度動能榜" data-zoom-title="各職業實戰強度動能榜" style="width:100%;max-width:1100px;display:block;margin:0 auto">`;
}}

document.getElementById('metaTbl').innerHTML =
  `<thead><tr><th>職業</th><th>強度動能</th>${{T.labels.map(l=>`<th>${{esc(l.slice(0,10))}} 均排</th>`).join('')}}<th>持有戰隊均排爬升</th><th>單職業(1隻)變化</th><th>雙職業(2隻)變化</th><th>持有戰隊爬升率</th><th>平均Δ積分</th><th>Top30出場率變化</th><th>全場出場率(隊數)</th></tr></thead><tbody>` +
  (T.occupation_trends || []).map(r => {{
    const isLow = !!r.low_sample;
    const g = r.avg_rank_gain;
    const c1 = r.copy1_rank_gain;
    const c2 = r.copy2_rank_gain;
    const t30 = r.top30_presence_delta || 0;
    const fmtCopy = (val, lowFlg) => {{
      if (val === null || val === undefined) return '<span class="sub">-</span>';
      if (lowFlg) return `<span class="sub">${{val>=0?'+':''}}${{val}}名 (樣本小)</span>`;
      return `<span class="${{val>0?'pos':val<0?'neg':'sub'}}">${{val>=0?'+':''}}${{val}}名</span>`;
    }};
    return `<tr class="${{isLow?'low-sample-row':''}}">
      <td><span style="display:inline-flex;align-items:center;gap:6px;font-weight:700">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td>
      <td><span class="tag ${{isLow?'tag-warn':''}}">${{esc(r.trend_tag)}}</span></td>
      ${{r.avg_rank_series.map(v=>`<td><b>${{v===null?'-':'#'+v}}</b></td>`).join('')}}
      <td class="${{isLow?'sub':((g||0)>0?'pos':(g||0)<0?'neg':'')}}"><b>${{g===null||g===undefined?'-':(g>=0?'+':'')+g+' 名'}}</b></td>
      <td>${{fmtCopy(c1, r.copy1_low_sample)}}</td>
      <td>${{fmtCopy(c2, r.copy2_low_sample)}}</td>
      <td class="${{isLow?'sub':((r.climber_rate||0)>=0.55?'pos':(r.climber_rate||0)<=0.40?'neg':'')}}"><b>${{pct(r.climber_rate)}}</b> (${{r.climber_count}}升/${{r.faller_count}}降)</td>
      <td>${{r.avg_score_gain!==null&&r.avg_score_gain!==undefined?(r.avg_score_gain>=0?'+':'')+r.avg_score_gain+'分':'-'}}</td>
      <td class="${{isLow?'sub':(t30>0?'pos':t30<0?'neg':'')}}">${{pct(r.first_top30_presence)}} → ${{pct(r.latest_top30_presence)}} (${{t30>=0?'+':''}}${{pct(t30)}})</td>
      <td>${{pct(r.latest_presence)}} <span class="sub">(${{r.team_count_series[r.team_count_series.length-1]}}隊｜${{r.presence_delta>=0?'+':''}}${{pct(r.presence_delta)}})</span></td>
    </tr>`;
  }}).join('') + '</tbody>';

document.getElementById('dpTbl').innerHTML =
  `<thead><tr><th>雙職業配置</th>${{T.labels.map(l=>`<th>${{esc(l.slice(0,10))}} 佔比</th>`).join('')}}<th>佔比變化</th>${{T.labels.map(l=>`<th>${{esc(l.slice(0,10))}} 均排</th>`).join('')}}<th>均排爬升(正=變強)</th></tr></thead><tbody>` +
  (T.double_pick_trends || []).map(d => {{
    const rg = d.avg_rank_gain;
    const isLow = !!d.low_sample;
    return `<tr class="${{isLow?'low-sample-row':''}}">
      <td><b>${{esc(d.label)}}</b>${{isLow?' <span class="tag tag-warn">樣本小</span>':''}}</td>
      ${{d.rate_series.map(v=>`<td>${{pct(v)}}</td>`).join('')}}
      <td class="${{d.rate_delta>0?'pos':d.rate_delta<0?'neg':''}}">${{d.rate_delta>=0?'+':''}}${{pct(d.rate_delta)}}</td>
      ${{(d.avg_rank_series||[]).map(v=>`<td><b>${{v===null?'-':'#'+v}}</b></td>`).join('')}}
      <td class="${{isLow?'sub':((rg||0)>0?'pos':(rg||0)<0?'neg':'')}}">${{rg===null||rg===undefined?'-':(rg>=0?'+':'')+rg+' 名'}}</td>
    </tr>`;
  }}).join('') + '</tbody>';

// Tab 3: Score Cutoffs Shift, Swap Flow & Climbers/Fallers
const svl = T.swap_vs_locked || {{}};
document.getElementById('scoreVelocitySub').innerHTML = svl.avg_score_gain_all !== null && svl.avg_score_gain_all !== undefined
  ? `全聯盟跨期追蹤戰隊平均進帳 <b style="color:var(--accent)">+${{svl.avg_score_gain_all}} 分</b>（中位數 +${{svl.median_score_gain_all}} 分）｜下方顯示各關鍵名次門檻線本期上漲幅度：`
  : '下方顯示各關鍵排名門檻線跨期變化：';

document.getElementById('cutoffShiftGrid').innerHTML = (T.score_cutoff_trends || []).map(c => {{
  const dTxt = c.score_delta !== null && c.score_delta !== undefined
    ? `<span class="${{c.score_delta>=0?'pos':'neg'}}">(${{c.score_delta>=0?'+':''}}${{c.score_delta}}分)</span>`
    : '';
  return `<div class="cutoff-pill">
    <div class="c-rank">${{esc(c.label)}} 門檻線</div>
    <div class="c-score">${{c.first_score ?? '-'}} → ${{c.latest_score ?? '-'}} 分</div>
    <div class="c-tie">${{dTxt}} ｜ 最新期同分擠壓 ${{c.latest_tied_count}} 隊</div>
  </div>`;
}}).join('') || '<div class="sub">無積分資料</div>';

const lk = svl.locked || {{}};
const sw = svl.swapped || {{}};
document.getElementById('swapCompareBox').innerHTML = [
  ['🔒 原陣容固定直衝', `${{lk.count || 0}} 隊｜均名次 ${{lk.avg_rank_change>=0?'+':''}}${{lk.avg_rank_change || 0}}｜爬升率 ${{pct(lk.climber_rate)}}`],
  ['🔄 切換副角實戰隊', `${{sw.count || 0}} 隊｜均名次 ${{sw.avg_rank_change>=0?'+':''}}${{sw.avg_rank_change || 0}}｜爬升率 ${{pct(sw.climber_rate)}}`],
  ['🔒 固定陣容均進帳', lk.avg_score_gain !== null && lk.avg_score_gain !== undefined ? `+${{lk.avg_score_gain}} 分` : '-'],
  ['🔄 切換副角均進帳', sw.avg_score_gain !== null && sw.avg_score_gain !== undefined ? `+${{sw.avg_score_gain}} 分` : '-'],
].map(([l,v]) => `<div class="kpi"><div class="lbl">${{l}}</div><div class="val" style="font-size:1rem">${{esc(v)}}</div></div>`).join('');

const flow = T.swap_occ_flow || [];
document.getElementById('swapFlowGrid').innerHTML = flow.length
  ? flow.map(f => {{
      const cls = f.net_flow > 0 ? 'pos' : f.net_flow < 0 ? 'neg' : 'sub';
      return `<div class="flow-item">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px">
          <span style="display:inline-flex;align-items:center;gap:6px;font-weight:700">${{ico(f.occupation)}}${{esc(f.occupation)}}</span>
          <span class="${{cls}}">${{f.net_flow>=0?'+':''}}${{f.net_flow}} 淨流入</span>
        </div>
        <div class="sub" style="font-size:.77rem;margin-top:4px">換入 +${{f.added_count}} 次 ｜ 換出 -${{f.removed_count}} 次</div>
      </div>`;
    }}).join('')
  : '<div class="sub">本期比對無隊伍切換副角色。</div>';

const renderMiniMoverTbl = (id, rows, isClimb) => {{
  document.getElementById(id).innerHTML =
    '<thead><tr><th>當下排名</th><th>戰隊名稱</th><th>跨期升降</th><th>積分變化</th><th>副角色切換</th></tr></thead><tbody>' +
    rows.map(t => `<tr>
      <td><b>#${{t.latest_rank}}</b></td>
      <td><b>${{esc(t.team_name)}}</b></td>
      <td class="${{isClimb?'pos':'neg'}}">#${{t.first_rank}} → #${{t.latest_rank}} (${{t.net_rank_change>=0?'+':''}}${{t.net_rank_change}})</td>
      <td>${{t.net_score_delta!==null&&t.net_score_delta!==undefined?(t.net_score_delta>=0?'+':'')+t.net_score_delta+'分':'-'}}</td>
      <td class="sub" style="font-size:.8rem">${{t.roster_changed ? `<span class="pos">${{esc(t.roster_change_notes)}}</span>` : '🔒 固定'}}</td>
    </tr>`).join('') + '</tbody>';
}};
renderMiniMoverTbl('climbersTbl', T.top_climbers || [], true);
renderMiniMoverTbl('fallersTbl', T.top_fallers || [], false);

document.getElementById('changeTbl').innerHTML =
  '<thead><tr><th>戰隊</th><th>區間</th><th>切換副角色明細</th><th>排名變化</th><th>積分變化</th><th>切換後 8 人名單</th></tr></thead><tbody>' +
  (T.roster_changes.length ? T.roster_changes.map(c => `<tr><td><b>${{esc(c.team_name)}}</b></td><td>${{esc(c.from_period.slice(0,8))}}→${{esc(c.to_period.slice(0,8))}}</td><td><code>${{esc(c.diff_summary)}}</code></td><td class="${{c.rank_delta>0?'pos':c.rank_delta<0?'neg':''}}">#${{c.rank_before}} → #${{c.rank_after}} (${{c.rank_delta>=0?'+':''}}${{c.rank_delta}})</td><td>${{c.score_delta!==null&&c.score_delta!==undefined?(c.score_delta>=0?'+':'')+c.score_delta+'分':'-'}}</td><td class="sub">${{esc(c.roster_after)}}</td></tr>`).join('') : '<tr><td colspan="6" class="sub">本期無戰隊切換副角色（全數以固定陣容爬分）</td></tr>') + '</tbody>';

// Universal Click-to-Zoom, Pan & Touch Pinch-Zoom Lightbox Controller
(function initZoomLightbox() {{
  const modal = document.getElementById('imgZoomModal');
  const stage = document.getElementById('zoomStage');
  const img = document.getElementById('zoomModalImg');
  const titleEl = document.getElementById('zoomModalTitle');
  const pctEl = document.getElementById('zoomPctLabel');
  const dlBtn = document.getElementById('btnZoomDownload');
  if (!modal || !stage || !img) return;
  let scale = 1, tx = 0, ty = 0, dragging = false, startX = 0, startY = 0, downX = 0, downY = 0;
  function applyTransform() {{
    img.style.transform = `translate(${{tx}}px, ${{ty}}px) scale(${{scale}})`;
    if (pctEl) pctEl.textContent = Math.round(scale * 100) + '%';
  }}
  function openZoom(src, title) {{
    img.src = src;
    if (titleEl) titleEl.textContent = title || '統計圖卡放大檢視';
    if (dlBtn) {{ dlBtn.href = src; dlBtn.download = (title || 'trend_chart') + '.png'; }}
    scale = 1; tx = 0; ty = 0; applyTransform();
    modal.classList.add('open');
  }}
  function closeZoom() {{ modal.classList.remove('open'); }}
  document.addEventListener('click', ev => {{
    const t = ev.target.closest('.zoomable-img');
    if (t && t.src) openZoom(t.src, t.dataset.zoomTitle || t.alt);
  }});
  document.getElementById('btnZoomIn').onclick = () => {{ scale = Math.min(5, +(scale + 0.25).toFixed(2)); applyTransform(); }};
  document.getElementById('btnZoomOut').onclick = () => {{ scale = Math.max(0.5, +(scale - 0.25).toFixed(2)); applyTransform(); }};
  document.getElementById('btnZoomReset').onclick = () => {{ scale = 1; tx = 0; ty = 0; applyTransform(); }};
  document.getElementById('btnZoomClose').onclick = closeZoom;
  stage.addEventListener('wheel', ev => {{
    ev.preventDefault();
    scale = Math.max(0.5, Math.min(5, +(scale + (ev.deltaY < 0 ? 0.2 : -0.2)).toFixed(2)));
    applyTransform();
  }}, {{ passive: false }});
  stage.addEventListener('mousedown', ev => {{
    if (ev.button !== 0) return;
    dragging = true; downX = ev.clientX; downY = ev.clientY;
    startX = ev.clientX - tx; startY = ev.clientY - ty;
    stage.classList.add('dragging');
  }});
  window.addEventListener('mousemove', ev => {{
    if (!dragging) return;
    tx = ev.clientX - startX; ty = ev.clientY - startY; applyTransform();
  }});
  window.addEventListener('mouseup', ev => {{
    if (!dragging) return;
    dragging = false; stage.classList.remove('dragging');
    if (Math.hypot(ev.clientX - downX, ev.clientY - downY) < 6) {{
      const r = img.getBoundingClientRect();
      const insideImg = ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom;
      if (!insideImg) closeZoom();
    }}
  }});
  stage.addEventListener('dblclick', () => {{
    if (scale > 1.05) {{ scale = 1; tx = 0; ty = 0; }} else {{ scale = 2.2; }}
    applyTransform();
  }});
  let pinchDist = 0, pinchScale = 1, tDrag = false, tSX = 0, tSY = 0, tDX = 0, tDY = 0, tMoved = false, lastTap = 0;
  stage.addEventListener('touchstart', ev => {{
    if (ev.touches.length === 2) {{
      ev.preventDefault(); tDrag = false; tMoved = true;
      pinchDist = Math.hypot(ev.touches[0].clientX - ev.touches[1].clientX, ev.touches[0].clientY - ev.touches[1].clientY) || 1;
      pinchScale = scale;
    }} else if (ev.touches.length === 1) {{
      ev.preventDefault(); const t = ev.touches[0];
      tDrag = true; tMoved = false; tDX = t.clientX; tDY = t.clientY; tSX = t.clientX - tx; tSY = t.clientY - ty;
    }}
  }}, {{ passive: false }});
  stage.addEventListener('touchmove', ev => {{
    if (ev.touches.length === 2) {{
      ev.preventDefault();
      const d = Math.hypot(ev.touches[0].clientX - ev.touches[1].clientX, ev.touches[0].clientY - ev.touches[1].clientY);
      scale = Math.max(0.5, Math.min(5, +(pinchScale * (d / pinchDist)).toFixed(2))); applyTransform();
    }} else if (ev.touches.length === 1 && tDrag) {{
      ev.preventDefault(); const t = ev.touches[0];
      if (Math.hypot(t.clientX - tDX, t.clientY - tDY) > 6) tMoved = true;
      tx = t.clientX - tSX; ty = t.clientY - tSY; applyTransform();
    }}
  }}, {{ passive: false }});
  stage.addEventListener('touchend', ev => {{
    if (ev.touches.length === 0) {{
      if (tDrag && !tMoved && ev.changedTouches && ev.changedTouches[0]) {{
        const t = ev.changedTouches[0], r = img.getBoundingClientRect();
        if (!(t.clientX >= r.left && t.clientX <= r.right && t.clientY >= r.top && t.clientY <= r.bottom)) closeZoom();
        else {{
          const now = Date.now();
          if (now - lastTap < 300) {{ if (scale > 1.05) {{ scale = 1; tx = 0; ty = 0; }} else {{ scale = 2.2; }} applyTransform(); lastTap = 0; }}
          else lastTap = now;
        }}
      }}
      tDrag = false;
    }}
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
    out.write_text(doc, encoding="utf-8")
    return out


def export_trend_package(trend: dict[str, Any], out_dir: str | Path) -> dict[str, Any]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "trend_analytics.json").write_text(
        json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    excel_p = write_trend_excel(trend, target / "trend_report.xlsx")
    cards = generate_trend_cards(trend, target / "cards")
    html_p = generate_trend_html(trend, target / "trend_report.html", cards_dir=target / "cards")
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
