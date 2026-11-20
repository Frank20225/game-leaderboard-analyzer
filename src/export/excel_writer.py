"""OpenPyXL 7-worksheet Excel report generator with native charts & optional public edition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_HEADER_FILL = PatternFill("solid", fgColor="1E293B")
_SUBHEADER_FILL = PatternFill("solid", fgColor="334155")
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
    """Write a styled table starting at `start_row` and return the last written row index."""
    pct_cols = pct_cols or set()
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=col_idx, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN_BORDER
    ws.row_dimensions[start_row].height = 26

    for r_offset, row_vals in enumerate(rows, start=1):
        r_idx = start_row + r_offset
        is_flagged = False
        if highlight_col_idx is not None and highlight_col_idx < len(row_vals):
            v = str(row_vals[highlight_col_idx]).lower()
            is_flagged = v in ("flagged", "error", "warning")

        for c_idx, val in enumerate(row_vals, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.font = _BODY_FONT
            cell.border = _THIN_BORDER
            if is_flagged:
                cell.fill = _ERR_FILL if str(row_vals[highlight_col_idx]).lower() == "error" else _FLAG_FILL
            elif r_offset % 2 == 0:
                cell.fill = _ALT_FILL
            if c_idx in pct_cols and isinstance(val, (int, float)):
                cell.number_format = "0.0%"
            cell.alignment = Alignment(
                horizontal="center" if isinstance(val, (int, float)) else "left",
                vertical="center",
            )
        ws.row_dimensions[r_idx].height = 21

    return start_row + len(rows)


def _autofit_columns(ws, min_w: int = 10, max_w: int = 44) -> None:
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
    """Create the formatted 7-sheet (or 6-sheet public) Excel workbook with native charts."""
    wb = Workbook()

    # 1. Raw Data
    ws_raw = wb.active
    ws_raw.title = "Raw Data"
    raw_headers = [
        "排名",
        "戰隊名稱",
        "積分",
        "職業1",
        "職業2",
        "職業3",
        "職業4",
        "職業5",
        "職業6",
        "職業7",
        "職業8",
        "完整八職業陣容",
        "來源影格",
        "觀測次數",
        "名稱信心度",
        "狀態",
        "標記",
    ]
    raw_rows = [
        [
            r["rank"],
            r["team_name"],
            r["score"],
            *r["occupations"],
            r["full_team_signature"],
            r["representative_keyframe_id"],
            r["observation_count"],
            r["name_conf"],
            r["status"],
            r["flags"],
        ]
        for r in analytics["raw_data"]
    ]
    _style_table(ws_raw, raw_headers, raw_rows, start_row=1, pct_cols={15}, highlight_col_idx=15)
    ws_raw.freeze_panes = "A2"
    _autofit_columns(ws_raw)

    # 2. Occupation Frequency
    ws_occ = wb.create_sheet("Occupation Frequency")
    occ_headers = [
        "職業名稱",
        "總出現人次",
        "總人次佔比",
        "攜帶隊伍數",
        "隊伍攜帶率",
        "攜帶隊平均數",
        "同職業多開隊數",
        "平均排名",
        "中位排名",
        "最高排名",
        "Top 10 攜帶率",
        "Top 50 攜帶率",
        "Top 100 攜帶率",
        "高排優勢比(Lift)",
        "排名Spearman相關",
    ]
    occ_rows = [
        [
            r["occupation"],
            r["slot_count"],
            r["slot_rate"],
            r["team_count"],
            r["team_presence_rate"],
            r["avg_per_carrying_team"],
            r["multi_copy_teams"],
            r["avg_rank"],
            r["median_rank"],
            r["best_rank"],
            r["top10_rate"],
            r["top50_rate"],
            r["top100_rate"],
            r["top_tier_lift"],
            r["spearman_r"],
        ]
        for r in analytics["occupation_frequency"]
    ]
    last_occ_row = _style_table(
        ws_occ, occ_headers, occ_rows, start_row=1, pct_cols={3, 5, 11, 12, 13}
    )
    ws_occ.freeze_panes = "A2"
    _autofit_columns(ws_occ)

    if len(occ_rows) >= 2:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "職業隊伍攜帶率 vs 總人次佔比"
        chart.x_axis.title = "比例"
        chart.y_axis.title = "職業"
        data_ref_team = Reference(ws_occ, min_col=5, min_row=1, max_row=last_occ_row)
        data_ref_slot = Reference(ws_occ, min_col=3, min_row=1, max_row=last_occ_row)
        cats = Reference(ws_occ, min_col=1, min_row=2, max_row=last_occ_row)
        chart.add_data(data_ref_team, titles_from_data=True)
        chart.add_data(data_ref_slot, titles_from_data=True)
        chart.set_categories(cats)
        chart.height = max(10, min(18, len(occ_rows) * 0.9))
        chart.width = 18
        ws_occ.add_chart(chart, f"A{last_occ_row + 3}")

    # 3. Pair Combinations
    ws_pair = wb.create_sheet("Pair Combinations")
    combo_headers = [
        "職業組合",
        "出現隊數",
        "隊伍佔比",
        "平均排名",
        "最高排名",
        "Top 10 隊數",
        "Top 10 佔比",
        "Top 50 佔比",
        "Top 100 佔比",
        "代表戰隊",
    ]
    pair_rows = [
        [
            r["combination"],
            r["team_count"],
            r["team_rate"],
            r["avg_rank"],
            r["best_rank"],
            r["top10_count"],
            r["top10_rate"],
            r["top50_rate"],
            r["top100_rate"],
            r["sample_teams"],
        ]
        for r in analytics["pair_combinations"]
    ]
    last_pair = _style_table(ws_pair, combo_headers, pair_rows, start_row=1, pct_cols={3, 7, 8, 9})

    # Same-class doubles section below
    sec_row = last_pair + 3
    ws_pair.cell(row=sec_row, column=1, value="【附表】同職業雙開（同隊攜帶 2 隻以上相同職業）").font = _TITLE_FONT
    double_rows = [
        [
            r["combination"],
            r["team_count"],
            r["team_rate"],
            r["avg_rank"],
            r["best_rank"],
            r["top10_count"],
            r["top10_rate"],
            r["top50_rate"],
            r["top100_rate"],
            r["sample_teams"],
        ]
        for r in analytics["same_class_doubles"]
    ]
    _style_table(ws_pair, combo_headers, double_rows, start_row=sec_row + 1, pct_cols={3, 7, 8, 9})
    ws_pair.freeze_panes = "A2"
    _autofit_columns(ws_pair)

    # 4. Triple Combinations
    ws_tri = wb.create_sheet("Triple Combinations")
    tri_rows = [
        [
            r["combination"],
            r["team_count"],
            r["team_rate"],
            r["avg_rank"],
            r["best_rank"],
            r["top10_count"],
            r["top10_rate"],
            r["top50_rate"],
            r["top100_rate"],
            r["sample_teams"],
        ]
        for r in analytics["triple_combinations"]
    ]
    last_tri = _style_table(ws_tri, combo_headers, tri_rows, start_row=1, pct_cols={3, 7, 8, 9})

    sec_row_t = last_tri + 3
    ws_tri.cell(row=sec_row_t, column=1, value="【附表】同職業三開（同隊攜帶 3 隻以上相同職業）").font = _TITLE_FONT
    same_tri_rows = [
        [
            r["combination"],
            r["team_count"],
            r["team_rate"],
            r["avg_rank"],
            r["best_rank"],
            r["top10_count"],
            r["top10_rate"],
            r["top50_rate"],
            r["top100_rate"],
            r["sample_teams"],
        ]
        for r in analytics["same_class_triples"]
    ]
    _style_table(ws_tri, combo_headers, same_tri_rows, start_row=sec_row_t + 1, pct_cols={3, 7, 8, 9})
    ws_tri.freeze_panes = "A2"
    _autofit_columns(ws_tri)

    # 5. Full Team Combinations
    ws_full = wb.create_sheet("Full Team Combinations")
    full_rows = [
        [
            r["combination"],
            r["team_count"],
            r["team_rate"],
            r["avg_rank"],
            r["best_rank"],
            r["top10_count"],
            r["top10_rate"],
            r["top50_rate"],
            r["top100_rate"],
            r["sample_teams"],
        ]
        for r in analytics["full_team_combinations"]
    ]
    _style_table(ws_full, combo_headers, full_rows, start_row=1, pct_cols={3, 7, 8, 9})
    ws_full.freeze_panes = "A2"
    _autofit_columns(ws_full, max_w=60)

    # 6. Ranking Analysis
    ws_rank = wb.create_sheet("Ranking Analysis")
    ov = analytics["overview"]
    ws_rank.cell(row=1, column=1, value=f"{analytics['report_title']} — 排名區間與職業關聯分析").font = _TITLE_FONT
    ws_rank.cell(
        row=2,
        column=1,
        value=f"實際涵蓋隊伍：{ov['total_teams']} 隊（排名 {ov['min_rank']}～{ov['max_rank']}），共 {ov['distinct_occupations']} 種職業；Spearman 負值代表該職業越常出現在高排名（名次數字越小）。",
    ).font = _BODY_FONT

    tier_headers = [
        "職業名稱",
        "整體攜帶率",
        "Top 10 攜帶率",
        "Top 50 攜帶率",
        "Top 100 攜帶率",
        "101+ 攜帶率",
        "Top 10 vs 整體差值",
        "高排優勢比(Lift)",
        "平均排名",
        "Spearman 相關係數",
        "p-value",
    ]
    tier_rows = [
        [
            r["occupation"],
            r["team_presence_rate"],
            r["top10_rate"],
            r["top50_rate"],
            r["top100_rate"],
            r["rank101_plus_rate"],
            round(r["top10_rate"] - r["team_presence_rate"], 4),
            r["top_tier_lift"],
            r["avg_rank"],
            r["spearman_r"],
            r["spearman_p"],
        ]
        for r in analytics["ranking_analysis"]["occupation_tier_comparison"]
    ]
    last_tier_row = _style_table(
        ws_rank, tier_headers, tier_rows, start_row=4, pct_cols={2, 3, 4, 5, 6, 7}
    )
    ws_rank.freeze_panes = "A5"
    _autofit_columns(ws_rank)

    if len(tier_rows) >= 2:
        tchart = BarChart()
        tchart.type = "col"
        tchart.grouping = "clustered"
        tchart.style = 11
        tchart.title = "各職業在 Top 10 / Top 50 / 整體 的隊伍攜帶率對比"
        tchart.y_axis.title = "隊伍攜帶率"
        tchart.add_data(Reference(ws_rank, min_col=2, max_col=4, min_row=4, max_row=last_tier_row), titles_from_data=True)
        tchart.set_categories(Reference(ws_rank, min_col=1, min_row=5, max_row=last_tier_row))
        tchart.height = 12
        tchart.width = 22
        ws_rank.add_chart(tchart, f"A{last_tier_row + 3}")

    # 7. Recognition Errors (included in full report, omitted in public share report)
    if include_errors_sheet:
        ws_err = wb.create_sheet("Recognition Errors")
        err_headers = ["嚴重度", "問題類型", "排名", "欄位", "辨識值", "信心度", "來源影格", "說明", "原圖路徑"]
        err_rows = [
            [
                e.get("severity", "warning"),
                e.get("issue_type", ""),
                e.get("rank"),
                e.get("field", ""),
                e.get("detected_value", ""),
                e.get("confidence", 0.0),
                e.get("keyframe_id"),
                e.get("message", ""),
                e.get("crop_path", ""),
            ]
            for e in analytics["recognition_errors"]
        ]
        if not err_rows:
            err_rows = [["ok", "none", None, "", "", 1.0, None, "本次分析未偵測到任何辨識異常或缺漏項目。", ""]]
        _style_table(ws_err, err_headers, err_rows, start_row=1, pct_cols={6}, highlight_col_idx=0)
        ws_err.freeze_panes = "A2"
        _autofit_columns(ws_err, max_w=55)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out
