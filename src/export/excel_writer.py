"""OpenPyXL v2 7-worksheet Excel report generator with pro tournament metrics & native charts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_HEADER_FILL = PatternFill("solid", fgColor="1E293B")
_ALT_FILL = PatternFill("solid", fgColor="F8FAFC")
_FLAG_FILL = PatternFill("solid", fgColor="FEF3C7")
_ERR_FILL = PatternFill("solid", fgColor="FEE2E2")
_HEADER_FONT = Font(name="Microsoft JhengHei", size=11, bold=True, color="FFFFFF")
_BODY_FONT = Font(name="Microsoft JhengHei", size=10, color="0F172A")
_TITLE_FONT = Font(name="Microsoft JhengHei", size=12, bold=True, color="1E293B")
_THIN_BORDER = Border(
    left=Side(style="thin", color="E2E8F0"),
    right=Side(style="thin", color="E2E8F0"),
    top=Side(style="thin", color="E2E8F0"),
    bottom=Side(style="thin", color="E2E8F0"),
)


def _display_width(val: Any) -> int:
    s = str(val or "")
    return sum(2 if ord(ch) > 127 else 1 for ch in s)


def _style_table(
    ws,
    headers: list[str],
    rows: list[list[Any]],
    start_row: int = 1,
    pct_cols: set[int] | None = None,
    highlight_col_idx: int | None = None,
) -> int:
    pct_cols = pct_cols or set()
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=col_idx, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN_BORDER
    ws.row_dimensions[start_row].height = 28

    for r_offset, row_vals in enumerate(rows, start=1):
        r_idx = start_row + r_offset
        is_flagged = False
        if highlight_col_idx is not None and highlight_col_idx < len(row_vals):
            v = str(row_vals[highlight_col_idx]).lower()
            is_flagged = v in ("flagged", "error", "warning", "false")

        for c_idx, val in enumerate(row_vals, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.font = _BODY_FONT
            cell.border = _THIN_BORDER
            if is_flagged:
                cell.fill = _ERR_FILL if str(row_vals[highlight_col_idx]).lower() in ("error", "false") else _FLAG_FILL
            elif r_offset % 2 == 0:
                cell.fill = _ALT_FILL
            if c_idx in pct_cols and isinstance(val, (int, float)):
                cell.number_format = "0.0%"
            cell.alignment = Alignment(
                horizontal="center" if isinstance(val, (int, float, bool)) else "left",
                vertical="center",
            )
        ws.row_dimensions[r_idx].height = 21
    return start_row + len(rows)


def _autofit_columns(ws, min_w: int = 10, max_w: int = 48) -> None:
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        best = min_w
        for cell in col:
            if cell.value is not None:
                best = max(best, _display_width(cell.value) + 3)
        ws.column_dimensions[col_letter].width = min(max_w, best)


def write_excel_report(
    analytics: dict[str, Any],
    output_path: str | Path,
    include_errors_sheet: bool = True,
) -> Path:
    """Create the upgraded 7-sheet (or 6-sheet public) tournament roster Excel workbook."""
    wb = Workbook()

    # 1. Raw Data
    ws_raw = wb.active
    ws_raw.title = "Raw Data"
    raw_headers = [
        "排名", "戰隊名稱", "積分",
        "職業1", "職業2", "職業3", "職業4", "職業5", "職業6", "職業7", "職業8",
        "雙開組數", "合規(同職<=2)", "完整八職業陣容", "來源影格", "狀態", "標記",
    ]
    raw_rows = [
        [
            r["rank"], r["team_name"], r["score"],
            *r["occupations"],
            r.get("double_pick_count", 0),
            "OK" if r.get("rule_compliant", True) else "ERROR",
            r["full_team_signature"],
            r["representative_keyframe_id"],
            r["status"],
            r["flags"],
        ]
        for r in analytics["raw_data"]
    ]
    _style_table(ws_raw, raw_headers, raw_rows, start_row=1, highlight_col_idx=15)
    ws_raw.freeze_panes = "A2"
    _autofit_columns(ws_raw)

    # 2. Occupation Frequency (includes 0/1/2 Copy Marginal Rank Impact & Meta Quadrant!)
    ws_occ = wb.create_sheet("Occupation Frequency")
    occ_headers = [
        "職業名稱", "Meta 象限", "總人次", "總人次佔比", "攜帶隊數", "隊伍攜帶率",
        "雙開隊數(×2)", "雙開率", "平均排名",
        "0隻均排(隊數)", "1隻均排(隊數)", "2隻均排(隊數)", "雙開名次提升(1→2)",
        "高排優勢比(Lift)", "Spearman r", "低樣本提醒",
    ]
    occ_rows = []
    for r in analytics["occupation_frequency"]:
        c0, c1, c2 = r["copy_0"], r["copy_1"], r["copy_2"]
        f_b = lambda b: f"#{b['avg_rank']} ({b['teams']}隊)" if b["teams"] else "-"
        occ_rows.append([
            r["occupation"], r["quadrant"], r["slot_count"], r["slot_rate"],
            r["team_count"], r["team_presence_rate"], r["double_pick_teams"], r["double_pick_rate"],
            r["avg_rank"], f_b(c0), f_b(c1), f_b(c2),
            r["double_rank_gain"] if r["double_rank_gain"] is not None else "-",
            r["top_tier_lift"], r["spearman_r"], "n<5 謹慎參考" if r["low_sample"] else "",
        ])
    last_occ_row = _style_table(ws_occ, occ_headers, occ_rows, start_row=1, pct_cols={4, 6, 8})
    ws_occ.freeze_panes = "A2"
    _autofit_columns(ws_occ)

    if len(occ_rows) >= 2:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "職業隊伍攜帶率 vs 雙開率"
        chart.add_data(Reference(ws_occ, min_col=6, min_row=1, max_row=last_occ_row), titles_from_data=True)
        chart.add_data(Reference(ws_occ, min_col=8, min_row=1, max_row=last_occ_row), titles_from_data=True)
        chart.set_categories(Reference(ws_occ, min_col=1, min_row=2, max_row=last_occ_row))
        chart.height = max(10, min(18, len(occ_rows) * 0.9))
        chart.width = 18
        ws_occ.add_chart(chart, f"A{last_occ_row + 3}")

    # 3. Pair Combinations (Synergy Lift + Substitution Pairs + Same-Class Doubles)
    ws_pair = wb.create_sheet("Pair Combinations")
    pair_headers = ["雙職業組合", "出現隊數", "實際佔比", "隨機預期佔比", "協同指數(Lift)", "平均排名", "最高排名", "Top 10 隊數", "代表戰隊"]
    ws_pair.cell(row=1, column=1, value="【表一】強烈綁定搭檔（Synergy Lift ≥ 1.15，排除熱門職相乘的假協同）").font = _TITLE_FONT
    syn_rows = [
        [r["combination"], r["team_count"], r["team_rate"], r["expected_rate"], r["synergy_lift"], r["avg_rank"], r["best_rank"], r["top10_count"], r["sample_teams"]]
        for r in analytics.get("synergy_pairs", [])
    ]
    r_cur = _style_table(ws_pair, pair_headers, syn_rows or [["(無明顯高協同搭檔)", 0, 0, 0, 1.0, 0, 0, 0, ""]], start_row=2, pct_cols={3, 4})

    r_cur += 2
    ws_pair.cell(row=r_cur, column=1, value="【表二】同定位互斥替代（Synergy Lift ≤ 0.85，帶 A 通常不帶 B）").font = _TITLE_FONT
    sub_rows = [
        [r["combination"], r["team_count"], r["team_rate"], r["expected_rate"], r["synergy_lift"], r["avg_rank"], r["best_rank"], r["top10_count"], r["sample_teams"]]
        for r in analytics.get("substitution_pairs", [])
    ]
    r_cur = _style_table(ws_pair, pair_headers, sub_rows or [["(無明顯互斥職業)", 0, 0, 0, 1.0, 0, 0, 0, ""]], start_row=r_cur + 1, pct_cols={3, 4})

    r_cur += 2
    ws_pair.cell(row=r_cur, column=1, value="【表三】同職業滿編雙開（×2）統計").font = _TITLE_FONT
    dbl_headers = ["同職雙開", "隊數", "隊伍佔比", "平均排名", "最高排名", "Top 10 隊數", "Top 10 佔比", "代表戰隊"]
    dbl_rows = [
        [r["combination"], r["team_count"], r["team_rate"], r["avg_rank"], r["best_rank"], r["top10_count"], r["top10_rate"], r["sample_teams"]]
        for r in analytics.get("same_class_doubles", [])
    ]
    r_cur = _style_table(ws_pair, dbl_headers, dbl_rows, start_row=r_cur + 1, pct_cols={3, 7})

    r_cur += 2
    ws_pair.cell(row=r_cur, column=1, value="【表四】完整雙職業出現次數排行（含協同指數）").font = _TITLE_FONT
    all_pair_rows = [
        [r["combination"], r["team_count"], r["team_rate"], r["expected_rate"], r["synergy_lift"], r["avg_rank"], r["best_rank"], r["top10_count"], r["sample_teams"]]
        for r in analytics.get("pair_combinations", [])[:50]
    ]
    _style_table(ws_pair, pair_headers, all_pair_rows, start_row=r_cur + 1, pct_cols={3, 4})
    ws_pair.freeze_panes = "A3"
    _autofit_columns(ws_pair)

    # 4. Triple Combinations (deduplicated per team; no illegal same-class triples!)
    ws_tri = wb.create_sheet("Triple Combinations")
    combo_headers = ["職業組合", "出現隊數", "隊伍佔比", "平均排名", "最高排名", "Top 10 隊數", "Top 10 佔比", "Top 50 佔比", "代表戰隊"]
    tri_rows = [
        [r["combination"], r["team_count"], r["team_rate"], r["avg_rank"], r["best_rank"], r["top10_count"], r["top10_rate"], r["top50_rate"], r["sample_teams"]]
        for r in analytics["triple_combinations"]
    ]
    _style_table(ws_tri, combo_headers, tri_rows, start_row=1, pct_cols={3, 7, 8})
    ws_tri.freeze_panes = "A2"
    _autofit_columns(ws_tri)

    # 5. Full Team Combinations (Roster Archetypes + Full 8-Occupation Details)
    ws_full = wb.create_sheet("Full Team Combinations")
    ws_full.cell(row=1, column=1, value="【表一】主流 8 人建隊流派骨架（Roster Archetypes — 依職業向量自動聚類）").font = _TITLE_FONT
    arch_headers = ["流派編號", "流派特徵", "隊數", "佔比", "平均排名", "最高排名", "Top 10 數", "平均雙開數", "核心必帶職(均數)", "常見彈性搖擺位", "代表戰隊"]
    arch_rows = [
        [a["archetype_id"], a["archetype_name"], a["team_count"], a["team_rate"], a["avg_rank"], a["best_rank"], a["top10_count"], a["avg_double_picks"], a["core_classes"], a["flex_classes"], a["sample_teams"]]
        for a in analytics.get("roster_archetypes", [])
    ]
    r_f = _style_table(ws_full, arch_headers, arch_rows or [["-", "樣本不足", 0, 0, 0, 0, 0, 0, "-", "-", "-"]], start_row=2, pct_cols={4})

    r_f += 2
    ws_full.cell(row=r_f, column=1, value="【表二】完整 8 職業陣容明細（順序無關標準化）").font = _TITLE_FONT
    full_rows = [
        [r["combination"], r["team_count"], r["team_rate"], r["avg_rank"], r["best_rank"], r["top10_count"], r["top10_rate"], r["top50_rate"], r["sample_teams"]]
        for r in analytics["full_team_combinations"]
    ]
    _style_table(ws_full, combo_headers, full_rows, start_row=r_f + 1, pct_cols={3, 7, 8})
    ws_full.freeze_panes = "A3"
    _autofit_columns(ws_full, max_w=62)

    # 6. Ranking Analysis (Non-overlapping Tiers + Double-Pick Structure + Score Tiers)
    ws_rank = wb.create_sheet("Ranking Analysis")
    ov = analytics["overview"]
    tiers = analytics["ranking_analysis"]["tiers"]
    tier_labels = [t["tier"] for t in tiers]

    ws_rank.cell(row=1, column=1, value=f"{analytics['report_title']} — 互斥分段趨勢 ＆ 雙開組隊結構").font = _TITLE_FONT
    ws_rank.cell(
        row=2,
        column=1,
        value=f"樣本：{ov['total_teams']} 隊（#{ov['min_rank']}～#{ov['max_rank']}，均排 #{ov['overall_avg_rank']}）；各分段完全互斥不重疊；Spearman 負值代表該職業越常出現在高排名。",
    ).font = _BODY_FONT

    tier_headers = [
        "職業名稱", "Meta 象限", "整體攜帶率",
        *[f"{t['tier']} ({t['team_count']}隊)" for t in tiers],
        "高排優勢比(Lift)", "平均排名", "Spearman r", "p-value",
    ]
    tier_rows = [
        [
            r["occupation"], r["quadrant"], r["team_presence_rate"],
            *[r["tier_rates"].get(tl, 0.0) for tl in tier_labels],
            r["top_tier_lift"], r["avg_rank"], r["spearman_r"], r["spearman_p"],
        ]
        for r in analytics["ranking_analysis"]["occupation_tier_comparison"]
    ]
    pct_set = {3, *{4 + i for i in range(len(tier_labels))}}
    r_k = _style_table(ws_rank, tier_headers, tier_rows, start_row=4, pct_cols=pct_set)

    # Double-pick structure subtable
    r_k += 2
    ws_rank.cell(row=r_k, column=1, value="【附表一】戰隊「雙開組數」策略分布（8 異職 vs 1/2/3 組雙開）").font = _TITLE_FONT
    dp_headers = ["雙開配置", "隊伍數", "佔比", "平均排名", "中位排名", "最高排名", "Top 10 數"]
    dp_rows = [
        [d["label"], d["team_count"], d["team_rate"], d["avg_rank"], d["median_rank"], d["best_rank"], d["top10_count"]]
        for d in analytics.get("double_pick_structure", [])
    ]
    r_k = _style_table(ws_rank, dp_headers, dp_rows, start_row=r_k + 1, pct_cols={3})

    # Score tiers subtable
    r_k += 2
    ws_rank.cell(row=r_k, column=1, value="【附表二】當期積分梯隊分布（參考用，跨期比較請以排名為主）").font = _TITLE_FONT
    sc_headers = ["積分", "隊伍數", "對應排名區間", "平均雙開數", "該梯隊熱門前 4 職業"]
    sc_rows = [
        [s["score"], s["team_count"], s["rank_range"], s["avg_doubles"], s["top_occupations"]]
        for s in analytics.get("score_tiers", [])
    ]
    _style_table(ws_rank, sc_headers, sc_rows, start_row=r_k + 1)
    ws_rank.freeze_panes = "A5"
    _autofit_columns(ws_rank)

    # 7. Recognition Errors
    if include_errors_sheet:
        ws_err = wb.create_sheet("Recognition Errors")
        err_headers = ["嚴重度", "問題類型", "排名", "欄位", "辨識值", "信心度", "來源影格", "說明", "原圖路徑"]
        err_rows = [
            [
                e.get("severity", "warning"), e.get("issue_type", ""), e.get("rank"),
                e.get("field", ""), e.get("detected_value", ""), e.get("confidence", 0.0),
                e.get("keyframe_id"), e.get("message", ""), e.get("crop_path", ""),
            ]
            for e in analytics["recognition_errors"]
        ]
        if not err_rows:
            err_rows = [["ok", "none", None, "", "", 1.0, None, "本次分析未偵測到任何辨識異常或賽制違規項目。", ""]]
        _style_table(ws_err, err_headers, err_rows, start_row=1, pct_cols={6}, highlight_col_idx=0)
        ws_err.freeze_panes = "A2"
        _autofit_columns(ws_err, max_w=55)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out
