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
  html, body {{ overflow-x: hidden; }}
  body {{ margin: 0; font-family: "Microsoft JhengHei", "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; -webkit-text-size-adjust: 100%; }}
  .wrap {{ max-width: 1240px; margin: 0 auto; padding: 24px 16px 60px; }}
  header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 12px; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; }}
  h1 {{ margin: 0; font-size: 1.6rem; line-height: 1.3; }}
  .sub {{ color: var(--muted); font-size: 0.9rem; margin-top: 4px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; min-width: 0; }}
  .kpi .lbl {{ color: var(--muted); font-size: 0.82rem; }}
  .kpi .val {{ font-size: 1.25rem; font-weight: 700; margin-top: 4px; color: var(--accent); word-break: break-word; }}
  .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }}
  .tab {{ background: var(--card); color: var(--muted); border: 1px solid var(--border); padding: 9px 15px; border-radius: 999px; cursor: pointer; font-weight: 600; font-size: 0.9rem; }}
  .tab.active {{ background: var(--accent); color: #0b1120; border-color: var(--accent); }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 18px; }}
  .card h2 {{ margin: 0 0 10px; font-size: 1.12rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; line-height: 1.35; }}
  .ico {{ width: 26px; height: 26px; border-radius: 50%; object-fit: cover; flex-shrink: 0; border: 1px solid rgba(255,255,255,.15); }}
  .lbl-flex {{ display: inline-flex; align-items: center; gap: 7px; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.87rem; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
  th {{ background: #0f172a; color: #cbd5e1; position: sticky; top: 0; z-index: 2; }}
  tr.team-row {{ cursor: pointer; transition: background 0.12s; }}
  tr.team-row:hover td {{ background: rgba(56,189,248,.09); }}
  .table-wrap {{ overflow-x: auto; max-height: 680px; -webkit-overflow-scrolling: touch; }}
  .mobile-swipe-hint {{ display: none; font-size: 0.78rem; color: var(--accent); margin: 4px 0 6px; text-align: right; }}
  .search-inp {{ flex: 1 1 280px; min-width: 0; }}
  .ocr-details > summary {{ list-style: none; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 8px; font-weight: 700; }}
  .ocr-details > summary::-webkit-details-marker {{ display: none; }}
  .ocr-summary-tag {{ font-size: 0.78rem; color: var(--accent); font-weight: 600; white-space: nowrap; }}
  .desktop-only-hint {{ display: inline; }}
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
  .scout-cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 12px; margin-top: 10px; }}
  .scout-col {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; font-size: 0.86rem; line-height: 1.68; min-width: 0; }}
  .scout-col.threat {{ border-left: 3px solid var(--accent2); }}
  .scout-col.gap {{ border-left: 3px solid var(--green); }}
  .scout-col h4 {{ margin: 0 0 6px; font-size: 0.9rem; }}
  .my-team-bar {{ background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(74, 222, 128, 0.45); border-radius: 12px; padding: 12px 15px; margin-bottom: 12px; }}
  .my-team-custom {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); display: none; }}
  .my-team-custom.open {{ display: block; }}
  .custom-slots {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(125px, 1fr)); gap: 8px; margin: 8px 0; }}
  .custom-slots select {{ padding: 6px 8px; font-size: 0.84rem; width: 100%; }}
  tr.team-row.is-my-team td {{ background: rgba(74, 222, 128, 0.11); }}
  .h2h-box {{ background: linear-gradient(135deg, rgba(56,189,248,.11), rgba(74,222,128,.08)); border: 1px solid rgba(56,189,248,.55); border-radius: 10px; padding: 11px 14px; margin: 10px 0 8px; }}
  .h2h-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 8px; margin-top: 8px; }}
  .h2h-item {{ background: #0b1120; border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-size: 0.83rem; min-width: 0; }}
  .h2h-item .h-lbl {{ color: var(--muted); font-size: 0.76rem; margin-bottom: 2px; }}
  .h2h-adv {{ border-color: rgba(74,222,128,.55); }}
  .h2h-warn {{ border-color: rgba(248,113,113,.55); }}
  .cutoff-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 175px), 1fr)); gap: 10px; margin: 12px 0 16px; }}
  .cutoff-pill {{ background: #0f172a; border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; min-width: 0; }}
  .cutoff-pill .c-rank {{ color: var(--muted); font-size: 0.8rem; font-weight: 600; }}
  .cutoff-pill .c-score {{ font-size: 1.25rem; font-weight: 800; color: var(--accent2); margin: 2px 0; }}
  .cutoff-pill .c-tie {{ font-size: 0.78rem; color: #cbd5e1; }}
  .density-bar-wrap {{ width: 100%; background: #0b1120; border-radius: 999px; height: 14px; overflow: hidden; border: 1px solid var(--border); }}
  .density-bar {{ height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); border-radius: 999px; }}
  .bracket-kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 10px; margin: 12px 0; }}
  .bracket-kpi {{ background: #0f172a; border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; min-width: 0; }}
  .bracket-kpi .b-lbl {{ color: var(--muted); font-size: 0.8rem; }}
  .bracket-kpi .b-val {{ font-size: 1.2rem; font-weight: 700; color: var(--text); margin: 3px 0; }}
  .bracket-kpi .b-sub {{ font-size: 0.78rem; color: var(--muted); }}
  .bracket-occ-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 8px; margin-top: 10px; }}
  .bracket-occ-row {{ background: #0f172a; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 0.83rem; min-width: 0; }}
  .score-filter-banner {{ display: none; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; background: rgba(245,158,11,.13); border: 1px solid rgba(245,158,11,.55); border-radius: 10px; padding: 8px 12px; margin-bottom: 10px; font-size: 0.86rem; }}
  .score-filter-banner.open {{ display: flex; }}
  .scout-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 10px; margin-top: 10px; }}
  .bo5-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }}
  .bo5-card h4 {{ margin: 0 0 6px; font-size: 0.88rem; color: var(--accent); }}
  .builder-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); gap: 10px; margin: 14px 0; }}
  .slot-box {{ background: #0f172a; border: 1px solid var(--border); border-radius: 10px; padding: 10px; text-align: center; }}
  .slot-box select {{ width: 100%; margin-top: 6px; }}
  .preset-btn {{ background: var(--card2); color: var(--text); border: 1px solid var(--accent); border-radius: 8px; padding: 7px 13px; cursor: pointer; font-weight: 600; font-size: 0.84rem; }}
  .preset-btn:hover {{ background: rgba(56,189,248,.2); }}
  .zoomable-img {{ cursor: zoom-in; transition: transform 0.15s, box-shadow 0.15s; border-radius: 12px; border: 1px solid var(--border); }}
  .zoomable-img:hover {{ box-shadow: 0 0 0 2px var(--accent); }}
  .cards-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); gap: 16px; }}
  .zoom-modal {{ position: fixed; inset: 0; background: rgba(5, 10, 20, 0.94); z-index: 9999; display: none; flex-direction: column; user-select: none; }}
  .zoom-modal.open {{ display: flex; }}
  .zoom-toolbar {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; background: #0f172a; border-bottom: 1px solid var(--border); flex-wrap: wrap; gap: 8px; }}
  .zoom-stage {{ flex: 1; overflow: hidden; position: relative; display: flex; align-items: center; justify-content: center; cursor: grab; touch-action: none; }}
  .zoom-stage.dragging {{ cursor: grabbing; }}
  .zoom-stage img {{ max-width: 94vw; max-height: 86vh; transform-origin: center center; transition: transform 0.04s linear; pointer-events: none; border-radius: 8px; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.82rem; margin-top: 28px; }}

  /* ================= Mobile-Friendly Responsive Layout (<= 768px) ================= */
  @media (max-width: 768px) {{
    .wrap {{ padding: 10px 10px 44px; }}
    header {{ padding-bottom: 10px; margin-bottom: 12px; gap: 4px; }}
    h1 {{ font-size: 1.24rem; }}
    .sub {{ font-size: 0.82rem; }}
    .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }}
    .kpi {{ padding: 10px 11px; border-radius: 10px; }}
    .kpi .lbl {{ font-size: 0.74rem; }}
    .kpi .val {{ font-size: 0.96rem; line-height: 1.3; }}

    /* Sticky single-row swipeable tabs */
    .tabs {{
      position: sticky; top: 0; z-index: 30;
      background: rgba(11, 17, 32, 0.95); backdrop-filter: blur(8px);
      margin: 0 -10px 12px; padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none;
    }}
    .tabs::-webkit-scrollbar {{ display: none; }}
    .tab {{ white-space: nowrap; flex-shrink: 0; padding: 8px 13px; font-size: 0.84rem; }}

    .card {{ padding: 13px 11px; border-radius: 12px; margin-bottom: 12px; }}
    .card h2 {{ font-size: 1.0rem; margin-bottom: 8px; }}
    .desktop-only-hint {{ display: none !important; }}
    .mobile-swipe-hint {{ display: block; }}

    /* Horizontal swipeable chip rows so filters stay compact */
    .filter-bar {{
      flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch;
      scrollbar-width: none; padding-bottom: 2px; margin-bottom: 8px;
    }}
    .filter-bar::-webkit-scrollbar {{ display: none; }}
    .filter-bar > * {{ flex-shrink: 0; white-space: nowrap; }}
    .chip-btn {{ padding: 6px 11px; font-size: 0.8rem; min-height: 34px; }}

    /* Search & filter inputs full-width / 2-column */
    .controls {{ gap: 7px; }}
    .search-inp {{ flex: 1 0 100%; width: 100%; font-size: 0.92rem; padding: 9px 11px; }}
    .controls select {{ flex: 1 1 46%; min-width: 0; font-size: 0.84rem; padding: 8px 9px; }}
    #rawCount {{ flex: 1 0 100%; font-size: 0.78rem; }}

    /* Transform 200-team Leaderboard Table into Clean Zero-Scroll Mobile Cards! */
    .raw-table-wrap {{ max-height: none; overflow-x: visible; }}
    #rawTable, #rawTable tbody {{ display: block; width: 100%; }}
    #rawTable thead {{ display: none; }}
    #rawTable tr.team-row {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 4px 7px;
      background: #0f172a; border: 1px solid var(--border); border-radius: 11px;
      padding: 10px 11px; margin-bottom: 8px;
    }}
    #rawTable tr.team-row.is-my-team {{
      background: rgba(74, 222, 128, 0.12); border-color: rgba(74, 222, 128, 0.55);
    }}
    #rawTable tr.team-row td {{ display: block; border: 0; padding: 0; background: transparent !important; }}
    #rawTable tr.team-row td.col-rank {{ order: 1; font-size: 0.92rem; color: var(--accent); min-width: 34px; }}
    #rawTable tr.team-row td.col-name {{ order: 2; flex: 1 1 52%; min-width: 0; word-break: break-word; font-size: 0.92rem; }}
    #rawTable tr.team-row td.col-score {{
      order: 3; font-size: 0.78rem; font-weight: 700; color: var(--accent2);
      background: rgba(245, 158, 11, 0.14) !important; border: 1px solid rgba(245, 158, 11, 0.35);
      padding: 2px 7px; border-radius: 999px;
    }}
    #rawTable tr.team-row td.col-dp {{
      order: 4; font-size: 0.75rem; color: #cbd5e1;
      background: var(--card2) !important; padding: 2px 7px; border-radius: 999px;
    }}
    #rawTable tr.team-row td.col-occs {{
      order: 5; flex: 1 0 100%; margin-top: 5px; padding-top: 6px;
      border-top: 1px dashed rgba(148, 163, 184, 0.22);
      display: flex; flex-wrap: wrap; gap: 4px;
    }}
    #rawTable tr.scout-detail-row {{ display: block; margin: -4px 0 10px; }}
    #rawTable tr.scout-detail-row > td {{ display: block; padding: 0 !important; border: 0; background: transparent !important; }}
    .pill {{ padding: 2px 6px; font-size: 0.74rem; gap: 3px; margin: 1px; }}
    .ico {{ width: 20px; height: 20px; }}

    /* Scout & H2H cards tight on mobile */
    .scout-box {{ padding: 11px 11px; border-radius: 10px; }}
    .scout-cols {{ grid-template-columns: 1fr; gap: 8px; }}
    .scout-col {{ padding: 10px 11px; font-size: 0.83rem; line-height: 1.6; }}
    .h2h-box {{ padding: 10px 10px; }}
    .h2h-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }}
    .h2h-item {{ padding: 6px 8px; font-size: 0.78rem; }}

    /* Tab 2 & Tab 3 statistical tables: sticky first col + crisp nowrap numbers */
    .stat-table-wrap {{ max-height: 520px; }}
    .stat-table-wrap table {{ font-size: 0.79rem; }}
    .stat-table-wrap th, .stat-table-wrap td {{ padding: 7px 7px; white-space: nowrap; }}
    .stat-table-wrap th:first-child, .stat-table-wrap td:first-child {{
      position: sticky; left: 0; z-index: 2; background: var(--card);
      box-shadow: 2px 0 6px rgba(0, 0, 0, 0.38);
    }}
    .stat-table-wrap th:first-child {{ z-index: 4; background: #0f172a; }}

    /* Tab 3 grids compact 2-column */
    .my-team-bar {{ padding: 11px; }}
    #myTeamSelect {{ width: 100%; max-width: none !important; }}
    .custom-slots {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .cutoff-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
    .cutoff-pill {{ padding: 9px 10px; }}
    .cutoff-pill .c-score {{ font-size: 1.05rem; }}
    .cutoff-pill .c-tie {{ font-size: 0.74rem; }}
    .bracket-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
    .bracket-kpi {{ padding: 9px 10px; }}
    .bracket-kpi .b-val {{ font-size: 1.02rem; }}
    .bracket-occ-grid {{ grid-template-columns: 1fr; gap: 6px; }}

    /* Lightbox compact mobile toolbar */
    .zoom-toolbar {{ padding: 8px 10px; gap: 6px; }}
    #zoomModalTitle {{ font-size: 0.84rem; }}
    .zoom-toolbar .chip-btn, .zoom-toolbar .preset-btn {{ padding: 5px 9px; font-size: 0.78rem; }}
    .zoom-stage img {{ max-width: 98vw; max-height: 82vh; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <!-- GLA_NAV_START --><!-- GLA_NAV_END -->
  <header>
    <div>
      <h1>{safe_title}</h1>
      <div class="sub" id="reportSub"></div>
    </div>
    <div class="sub" id="genTime"></div>
  </header>

  <section class="kpis" id="kpiRow"></section>

  <nav class="tabs">
    <button class="tab active" data-tab="raw">🔍 1. 排行榜與對手秒查</button>
    <button class="tab" data-tab="quad">📊 2. 職業出場率＆雙職業分析</button>
    <button class="tab" data-tab="bracket">🏆 3. 積分門檻線＆同分圈假想敵</button>
  </nav>

  <section id="tab-raw" class="panel active">
    <div class="card">
      <h2>完整排行榜資料查詢 ＆ 實戰對手秒查 <span class="sub desktop-only-hint" style="font-size:0.82rem">支援線上 Ctrl+V 截圖 OCR／免打泰文</span></h2>
      <details id="ocrScoutDetails" class="scout-box ocr-details" open style="margin-bottom:12px;background:#0f172a;border-color:rgba(56,189,248,.55)">
        <summary>
          <span>📷 截圖秒查對手（免開本機伺服器）</span>
          <span class="ocr-summary-tag">點擊展開 / 收合</span>
        </summary>
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-top:8px">
          <div class="sub" style="font-size:0.83rem;margin-top:0">
            <span class="desktop-only-hint">遊戲中按 <code>Win + Shift + S</code> 框選對手隊名後，直接按 <b><code>Ctrl + V</code></b> 貼上，或</span>點擊右側選取手機截圖，系統將以<b>「原圖字形指紋 ＋ 多語系 OCR (中/英/泰)」</b>鎖定對手並展開對局提醒卡。
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;width:100%">
            <select id="ocrModeSelect" style="font-size:0.82rem;padding:6px 10px;max-width:100%;flex:1 1 220px">
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
      </details>

      <div class="score-filter-banner" id="scoreFilterBanner">
        <span id="scoreFilterText"></span>
        <button class="chip-btn" id="btnClearScoreFilter" type="button">✖ 清除積分篩選（恢復顯示全部）</button>
      </div>

      <div class="sub desktop-only-hint" style="display:block;background:#0f172a;border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:12px;line-height:1.6">
        🎯 <b>不截圖也能 3 秒查泰文對手：</b>
        先點下方<b>「語系秒篩」</b>（例如點 <code>🇹🇭 泰文隊</code>）＋<b>「外觀特徵」</b>（含數字 / 字數長短），免打字即可縮小範圍！<b>點擊表格任一戰隊列</b>可展開<b>【🎯 對手陣容特徵 ＆ 實戰對局提醒卡】</b>。
      </div>
      <div class="filter-bar" id="scriptFilterBar">
        <span class="sub" style="margin-right:4px">語系：</span>
        <button class="chip-btn active" data-script="all">🌐 全部</button>
        <button class="chip-btn" data-script="th">🇹🇭 泰文隊</button>
        <button class="chip-btn" data-script="zh">🇹🇼 中文隊</button>
        <button class="chip-btn" data-script="en">🔤 純英數</button>
      </div>
      <div class="filter-bar" id="featFilterBar">
        <span class="sub" style="margin-right:4px">特徵：</span>
        <button class="chip-btn active" data-feat="all">📏 全部長度</button>
        <button class="chip-btn" data-feat="num">🔢 含數字</button>
        <button class="chip-btn" data-feat="sym">✨ 含符號</button>
        <button class="chip-btn" data-feat="short">短名 ≤5字</button>
        <button class="chip-btn" data-feat="mid">中名 6~9字</button>
        <button class="chip-btn" data-feat="long">長名 ≥10字</button>
      </div>
      <div class="controls">
        <input id="searchInput" class="search-inp" type="search" placeholder="搜尋隊名、跳字縮寫或排名 (如 #12, enc, 88)...">
        <select id="occFilter"><option value="">篩選職業（全部）</option></select>
        <select id="dpFilter">
          <option value="">篩選雙職業（全部）</option>
          <option value="0">0 組雙職業（8異職）</option>
          <option value="1">1 組雙職業</option>
          <option value="2">2 組雙職業</option>
          <option value="3">3+ 組雙職業</option>
        </select>
        <span class="sub" id="rawCount"></span>
      </div>
      <div class="table-wrap raw-table-wrap"><table id="rawTable"></table></div>
    </div>
  </section>

  <section id="tab-quad" class="panel">
    <div class="card">
      <h2>14 職業環境總表 ＆ Meta 四象限戰略圖 <span class="sub" style="font-size:0.82rem">💡 點擊圖卡可全螢幕放大縮放</span></h2>
      <div id="quadCardWrap" style="margin-bottom:14px"></div>
      <div class="sub" style="background:#0f172a;border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:12px;line-height:1.65">
        💡 <b>指標白話說明：</b><br>
        • <b>前段班偏好倍率</b>＝前段班（Top 50 / Top 10）出場率 ÷ 全場出場率。<b>&gt; 1.0x</b> 代表前段班強隊更愛帶；<b>≈ 1.0x</b> 代表各分段普及度相近；<b>&lt; 1.0x</b> 代表偏中後段帶得多。<br>
        • <b>名次相關性（-1 ～ +1）</b>＝衡量「帶越多隻該職業，名次是否越靠前」。<b>負值（綠色，如 -0.21 帶越多名次越前）代表強勢職業</b>；接近 0 代表無明顯關聯；<b>正值（紅色）代表偏中後段</b>。
      </div>
      <div class="mobile-swipe-hint">← 左右滑動表格查看完整數據 →</div>
      <div class="table-wrap stat-table-wrap"><table id="occTable"></table></div>
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
        <div class="mobile-swipe-hint">← 左右滑動表格查看完整數據 →</div>
        <div class="table-wrap stat-table-wrap" style="margin-top:10px"><table id="copyTable"></table></div>
      </details>
    </div>

    <div class="card">
      <h2>各名次區間職業出場率 ＆ 雙職業組數結構 <span class="sub" style="font-size:0.82rem">💡 點圖可放大縮放</span></h2>
      <div id="tierCardWrap" style="margin-bottom:12px"></div>
      <details style="margin-top:10px">
        <summary style="cursor:pointer;color:var(--accent);font-weight:600">📋 展開查看「各名次區間出場率明細表」與「雙職業組數結構表」</summary>
        <p class="sub" style="margin:10px 0 6px">💡 橫著從左往右看（左邊是前 10 名、右邊是後段班）：越左邊數字越高＝頂尖強隊越愛用。</p>
        <div class="mobile-swipe-hint">← 左右滑動表格查看完整數據 →</div>
        <div class="table-wrap stat-table-wrap" style="margin-bottom:14px"><table id="tierHeatTable"></table></div>
        <h3 style="font-size:0.98rem;margin:10px 0 6px">戰隊「雙職業組數」策略結構（8 異職 vs 1 / 2 / 3 組雙職業）</h3>
        <div class="mobile-swipe-hint">← 左右滑動表格查看完整數據 →</div>
        <div class="table-wrap stat-table-wrap"><table id="dpStructTable"></table></div>
      </details>
    </div>
  </section>

  <section id="tab-bracket" class="panel">
    <div class="my-team-bar" id="myTeamBar">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <div id="myTeamStatus" style="font-size:0.88rem"></div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <select id="myTeamSelect" style="font-size:0.82rem;padding:6px 10px;max-width:250px"></select>
          <button class="chip-btn" id="btnToggleCustomMyTeam" type="button">✏️ 自選 8 職業（榜外隊適用）</button>
          <button class="chip-btn" id="btnClearMyTeam" type="button" style="display:none;border-color:rgba(248,113,113,.55);color:#fca5a5">✖ 解除鎖定</button>
        </div>
      </div>
      <div class="my-team-custom" id="myTeamCustomBox">
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:6px">
          <span class="sub" style="font-size:0.82rem">我方隊名（選填）：</span>
          <input id="customMyTeamName" type="text" placeholder="例如：我方戰隊" style="padding:5px 9px;font-size:0.83rem;width:180px">
          <span class="sub" style="font-size:0.8rem">※ 格 1～5 為預設先發、格 6～8 為替補（同職業上限 2 隻）</span>
        </div>
        <div class="custom-slots" id="customMyTeamSlots"></div>
        <div style="display:flex;gap:8px;align-items:center;margin-top:6px">
          <button class="preset-btn" id="btnSaveCustomMyTeam" type="button" style="padding:5px 12px;font-size:0.82rem">💾 儲存並鎖定我方陣容</button>
          <span class="sub" id="customMyTeamWarn" style="color:var(--red);font-size:0.82rem"></span>
        </div>
      </div>
    </div>

    <div id="scoreBracketCard">
      <div class="card">
        <h2>🎯 同分圈假想敵環境（教練備戰專區）<button class="preset-btn" id="btnJumpBracketToRaw" type="button" style="padding:6px 12px;font-size:0.82rem">🔍 在排行榜查看此同分圈對手</button></h2>
        <p class="sub" style="margin-top:0">點選目標分數段或自訂區間，立即對比「接下來會撞到的對手」與「全服平均」的職業差異，決定本週團練與針對重點。</p>
        <div class="filter-bar" id="bracketPresetBar"></div>
        <div class="controls" style="margin-bottom:10px">
          <span class="sub" style="font-size:0.84rem">自訂積分區間：</span>
          <select id="bracketMinScore" style="padding:6px 10px;font-size:0.85rem"></select>
          <span class="sub">～</span>
          <select id="bracketMaxScore" style="padding:6px 10px;font-size:0.85rem"></select>
          <span class="sub" id="bracketMetaText" style="font-weight:600;color:var(--accent)"></span>
        </div>
        <div class="bracket-kpis" id="bracketKpiGrid"></div>
        <div style="margin-top:12px">
          <div class="sub" style="font-size:0.84rem;margin-bottom:6px"><b>該同分圈各職業出場率（括號為相較全服平均之增減）：</b></div>
          <div class="bracket-occ-grid" id="bracketOccGrid"></div>
        </div>
      </div>

      <div class="card">
        <h2>🏆 關鍵排名積分門檻線 ＆ 各分數同分擠壓密度 <span class="sub" style="font-size:0.82rem">💡 點擊下方任一積分列可立即切換上方假想敵分析</span></h2>
        <div id="cutoffGrid" class="cutoff-grid"></div>
        <details open>
          <summary style="cursor:pointer;color:var(--accent);font-weight:600">📊 各積分同分擠壓密度表（點擊任一積分列可立即檢視該分數段）</summary>
          <div class="mobile-swipe-hint">← 左右滑動表格查看完整數據 →</div>
          <div class="table-wrap stat-table-wrap" style="margin-top:10px"><table id="scoreDensityTable"></table></div>
        </details>
      </div>
    </div>
  </section>

  <footer>Game Leaderboard Analyzer v2 — Tournament Roster Strategy Report</footer>
</div>

<div class="zoom-modal" id="imgZoomModal">
  <div class="zoom-toolbar">
    <div>
      <b id="zoomModalTitle" style="color:var(--accent)">圖表放大檢視</b>
      <span class="sub desktop-only-hint" style="margin-left:10px">💡 滾輪：自由縮放 ｜ 按住滑鼠左鍵：拖曳平移 ｜ 雙擊圖片：切換 100% / 220%</span>
    </div>
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <button class="chip-btn" id="btnZoomOut">➖</button>
      <span id="zoomPctLabel" style="min-width:44px;text-align:center;font-weight:700;font-size:0.84rem">100%</span>
      <button class="chip-btn" id="btnZoomIn">➕</button>
      <button class="chip-btn" id="btnZoomReset">🔄 100%</button>
      <a class="preset-btn" id="btnZoomDownload" download="chart.png" style="text-decoration:none;padding:5px 10px">💾 <span class="desktop-only-hint">下載高清圖卡</span></a>
      <button class="preset-btn" id="btnZoomClose" style="background:rgba(248,113,113,.2);border-color:var(--red)">✖ 關閉</button>
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

const bestDP = [...A.double_pick_structure].filter(d => !d.low_sample).sort((a,b) => a.avg_rank - b.avg_rank)[0] || A.double_pick_structure[0];
const topOcc = A.occupation_frequency[0];
const bestDoubleOcc = [...A.occupation_frequency].filter(r => !r.low_sample && r.copy_2 && !r.copy_2.low_sample && r.copy_2.avg_rank).sort((a,b) => a.copy_2.avg_rank - b.copy_2.avg_rank)[0];
document.getElementById('kpiRow').innerHTML = [
  ['分析隊伍數', ov.total_teams + ' 隊'],
  ['熱門第一職業', topOcc ? `${{topOcc.occupation}} (${{pct(topOcc.team_presence_rate)}})` : '-'],
  ['最佳雙職業效益', bestDoubleOcc ? `雙${{bestDoubleOcc.occupation}} (${{bestDoubleOcc.copy_2.teams}}隊・均#${{bestDoubleOcc.copy_2.avg_rank}})` : '-'],
  ['最強勢雙職業結構', bestDP ? `${{bestDP.label}} (均#${{bestDP.avg_rank}})` : '-'],
].map(([l, v]) => `<div class="kpi"><div class="lbl">${{l}}</div><div class="val">${{esc(v)}}</div></div>`).join('');

document.querySelectorAll('.tab').forEach(btn => btn.onclick = () => {{
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
}});

// Render crisp inline SVG Meta Quadrant (Scheme A: exclude <5% low-sample occupations so axes stay crisp)
(function renderQuad() {{
  const mainRows = A.occupation_frequency.filter(r => !r.low_sample);
  const rows = mainRows.length ? mainRows : A.occupation_frequency;
  const excl = A.occupation_frequency.filter(r => r.low_sample);
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
    items += `${{imgTag}}<text x="${{cx}}" y="${{cy+27}}" text-anchor="middle" fill="#f8fafc" font-size="11" font-weight="700">${{esc(r.occupation)}} #${{r.avg_rank}}</text>`;
  }});

  const exclHtml = excl.length
    ? `<div class="sub" style="margin-top:6px;text-align:center;font-size:0.82rem">ⓘ 已排除出場率 &lt;5% 極低樣本職業以免拉歪座標軸：${{excl.map(r => `${{esc(r.occupation)}} (${{r.team_count}}隊)`).join('、')}}</div>`
    : '';
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
  </svg>${{exclHtml}}`;
}})();

const fmtRho = (r, lowSample) => {{
  if (lowSample) return `<span class="sub">${{Number(r || 0)}} (樣本不足)</span>`;
  const v = Number(r || 0);
  if (v <= -0.15) return `<span class="pos">${{v}} (🔥帶越多名次越前)</span>`;
  if (v <= -0.07) return `<span class="pos">${{v}} (↗偏前段)</span>`;
  if (v >= 0.15) return `<span class="neg">${{v}} (⚠️偏中後段)</span>`;
  if (v >= 0.07) return `<span class="neg">${{v}} (↘稍偏後段)</span>`;
  return `<span class="sub">${{v}} (➖無明顯關聯)</span>`;
}};

document.getElementById('occTable').innerHTML =
  '<thead><tr><th>職業</th><th>Meta 象限</th><th>隊伍出場率(隊數)</th><th>總席次佔比</th><th>雙職業率(帶2隻隊數)</th><th>平均排名</th><th title="前段班出場率 ÷ 全體出場率，>1.0x 代表前段班強隊更偏愛">前段班偏好倍率 ⓘ</th><th title="負值代表帶越多隻名次越靠前，正值代表偏向中後段班">名次相關性 ⓘ</th></tr></thead><tbody>' +
  A.occupation_frequency.map(r => {{
    const lowTag = r.low_sample ? ' <span class="sub" style="font-size:0.75rem">(低樣本參考)</span>' : '';
    const rowStyle = r.low_sample ? ' style="opacity:0.68"' : '';
    return `<tr${{rowStyle}}><td><span class="lbl-flex">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td><td><span class="q-tag ${{qCls(r.quadrant)}}">${{esc(r.quadrant)}}</span></td><td><b>${{pct(r.team_presence_rate)}}</b> (${{r.team_count}}隊)</td><td>${{pct(r.slot_rate)}} (${{r.slot_count}})</td><td>${{pct(r.double_pick_rate)}} (${{r.double_pick_teams}}隊)</td><td><b>#${{r.avg_rank}}</b>${{lowTag}}</td><td><b>${{r.top_tier_lift}}x</b>${{lowTag}}</td><td>${{fmtRho(r.spearman_r, r.low_sample)}}</td></tr>`;
  }}).join('') +
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

const fmtB = b => b && b.teams ? `<b>#${{b.avg_rank}}</b> <span class="sub">(${{b.teams}}隊${{b.low_sample?', 低樣本':''}})</span>` : '<span class="sub">-</span>';
document.getElementById('copyTable').innerHTML =
  '<thead><tr><th>職業</th><th>帶 0 隻（不帶）</th><th>帶 1 隻（單職業）</th><th>帶 2 隻（雙職業）</th><th>雙職業名次提升 (1隻→2隻)</th></tr></thead><tbody>' +
  A.occupation_frequency.map(r => {{
    const g = r.double_rank_gain;
    const gHtml = g === null || g === undefined ? '-' : `<span class="${{g>=0?'pos':'neg'}}">${{g>=0?'+':''}}${{g}} 名</span>`;
    const rowStyle = r.low_sample ? ' style="opacity:0.68"' : '';
    return `<tr${{rowStyle}}><td><span class="lbl-flex">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td><td>${{fmtB(r.copy_0)}}</td><td>${{fmtB(r.copy_1)}}</td><td>${{fmtB(r.copy_2)}}</td><td>${{gHtml}}</td></tr>`;
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
    const trendTxt = r.low_sample ? '— 低樣本觀察' : diff >= 0.08 ? `↑ 前段愛帶 (+${{pct(diff)}})` : diff <= -0.08 ? `↓ 後段較多 (${{pct(diff)}})` : `— 差不多 (${{diff>=0?'+':''}}${{pct(diff)}})`;
    const trendCls = r.low_sample ? 'sub' : diff >= 0.08 ? 'pos' : diff <= -0.08 ? 'neg' : 'sub';
    const rowStyle = r.low_sample ? ' style="opacity:0.68"' : '';
    return `<tr${{rowStyle}}><td><span class="lbl-flex">${{ico(r.occupation)}}${{esc(r.occupation)}}</span></td><td>${{pct(r.team_presence_rate)}}</td>${{tiers.map(t => {{
      const v = r.tier_rates[t.tier] || 0;
      const alpha = (0.08 + v * 0.65).toFixed(2);
      return `<td class="heat-cell" style="background:rgba(56,189,248,${{alpha}})">${{pct(v)}}</td>`;
    }}).join('')}}<td class="${{trendCls}}">${{trendTxt}}</td><td><b>#${{r.avg_rank}}</b></td></tr>`;
  }}).join('') + '</tbody>';

document.getElementById('dpStructTable').innerHTML =
  '<thead><tr><th>雙職業組數配置</th><th>隊伍數</th><th>佔比</th><th>平均排名</th><th>中位排名</th><th>最高排名</th><th>Top 10 隊數</th></tr></thead><tbody>' +
  A.double_pick_structure.map(d => `<tr><td><b>${{esc(d.label)}}</b></td><td>${{d.team_count}}</td><td>${{pct(d.team_rate)}}</td><td><b>#${{d.avg_rank}}</b></td><td>#${{d.median_rank}}</td><td>#${{d.best_rank}}</td><td>${{d.top10_count}}</td></tr>`).join('') + '</tbody>';

// ============================================================
// C3: Coach My-Team Lock & 10-Second Objective Head-to-Head
// ============================================================
const MY_TEAM_KEY = 'gla_my_team_v1';
const DUEL_CLASSES = ['賢者', '流氓', '騎士', '武僧'];
const ALL_OCC_NAMES = A.occupation_frequency.map(r => r.occupation);
let myTeam = null;
let activeScoreRange = null; // { min, max } when jumping from Tab 2 C5 bracket

function loadMyTeam() {{
  try {{
    const raw = localStorage.getItem(MY_TEAM_KEY);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (!obj) return null;
    if (obj.mode === 'rank' && obj.rank) {{
      const found = A.raw_data.find(t => t.rank === Number(obj.rank) && (!obj.team_name || t.team_name === obj.team_name))
        || A.raw_data.find(t => t.team_name === obj.team_name);
      if (found) {{
        return {{
          mode: 'rank',
          rank: found.rank,
          team_name: found.team_name,
          score: found.score,
          occupations: (found.occupations || []).filter(Boolean),
        }};
      }}
    }}
    if (Array.isArray(obj.occupations) && obj.occupations.length) {{
      return {{
        mode: 'custom',
        rank: null,
        team_name: obj.team_name || '我方自選陣容',
        score: null,
        occupations: obj.occupations.filter(Boolean),
      }};
    }}
  }} catch (e) {{}}
  return null;
}}

function saveMyTeam(obj) {{
  myTeam = obj;
  try {{
    if (obj) localStorage.setItem(MY_TEAM_KEY, JSON.stringify(obj));
    else localStorage.removeItem(MY_TEAM_KEY);
  }} catch (e) {{}}
  renderMyTeamBar();
  renderRaw();
  if (typeof renderBracketPresets === 'function') renderBracketPresets();
}}

window.setMyTeamByRank = function(rank, ev) {{
  if (ev) ev.stopPropagation();
  const found = A.raw_data.find(t => t.rank === Number(rank));
  if (!found) return;
  saveMyTeam({{
    mode: 'rank',
    rank: found.rank,
    team_name: found.team_name,
    score: found.score,
    occupations: (found.occupations || []).filter(Boolean),
  }});
}};

function countOccs(occs) {{
  const m = {{}};
  (occs || []).filter(Boolean).forEach(o => m[o] = (m[o] || 0) + 1);
  return m;
}}

function renderMyTeamBar() {{
  const statusEl = document.getElementById('myTeamStatus');
  const selEl = document.getElementById('myTeamSelect');
  const clrBtn = document.getElementById('btnClearMyTeam');
  if (!statusEl || !selEl) return;

  if (myTeam) {{
    const cnts = countOccs(myTeam.occupations);
    const doubles = Object.keys(cnts).filter(o => cnts[o] >= 2);
    const rankTag = myTeam.rank ? `#${{myTeam.rank}} ` : '自選 ';
    const scoreTag = myTeam.score !== null && myTeam.score !== undefined ? `（${{myTeam.score}}分）` : '';
    statusEl.innerHTML = `🛡️ <b style="color:var(--green)">已鎖定我方戰隊：${{rankTag}}${{esc(myTeam.team_name)}}${{scoreTag}}</b>
      <span class="sub" style="margin-left:6px">雙職業：${{doubles.length ? doubles.map(d => `${{d}}×2`).join('、') : '無'}}</span>
      <div style="margin-top:5px">${{myTeam.occupations.map(o => `<span class="pill ${{cnts[o]>=2?'dp':''}}">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')}}</div>`;
    selEl.value = myTeam.mode === 'rank' && myTeam.rank ? String(myTeam.rank) : '';
    if (clrBtn) clrBtn.style.display = 'inline-block';
  }} else {{
    statusEl.innerHTML = `🛡️ <b>教練對位模式（未鎖定我方隊伍）</b> <span class="sub">— 鎖定我方戰隊或自選 8 職業後，此頁將自動解鎖「我方同分圈 (±1分)」，且在分頁 1 查對手時自動展開「10 秒客觀對位對照」</span>`;
    selEl.value = '';
    if (clrBtn) clrBtn.style.display = 'none';
  }}
}}

function initMyTeamControls() {{
  const selEl = document.getElementById('myTeamSelect');
  const customBox = document.getElementById('myTeamCustomBox');
  const slotsEl = document.getElementById('customMyTeamSlots');
  const nameInp = document.getElementById('customMyTeamName');
  const warnEl = document.getElementById('customMyTeamWarn');
  if (!selEl) return;

  selEl.innerHTML = '<option value="">-- 從排行榜鎖定我方戰隊 --</option>' +
    A.raw_data.map(t => `<option value="${{t.rank}}">#${{t.rank}} ${{esc(t.team_name)}} (${{t.score ?? '-'}}分)</option>`).join('');
  selEl.onchange = () => {{
    if (!selEl.value) return;
    window.setMyTeamByRank(Number(selEl.value));
    if (customBox) customBox.classList.remove('open');
  }};

  if (slotsEl) {{
    const opts = '<option value="">(空位)</option>' + ALL_OCC_NAMES.map(o => `<option value="${{esc(o)}}">${{esc(o)}}</option>`).join('');
    slotsEl.innerHTML = Array.from({{ length: 8 }}, (_, i) => `
      <div>
        <div class="sub" style="font-size:0.75rem;margin-bottom:2px">${{i < 5 ? `先發格 ${{i + 1}}` : `替補格 ${{i + 1}}`}}</div>
        <select class="custom-occ-sel">${{opts}}</select>
      </div>`).join('');
  }}

  const btnToggle = document.getElementById('btnToggleCustomMyTeam');
  if (btnToggle && customBox) {{
    btnToggle.onclick = () => {{
      customBox.classList.toggle('open');
      if (customBox.classList.contains('open') && myTeam) {{
        if (nameInp) nameInp.value = myTeam.team_name || '';
        const sels = slotsEl.querySelectorAll('.custom-occ-sel');
        sels.forEach((s, i) => s.value = (myTeam.occupations && myTeam.occupations[i]) || '');
      }}
    }};
  }}

  const btnSave = document.getElementById('btnSaveCustomMyTeam');
  if (btnSave) {{
    btnSave.onclick = () => {{
      const picked = [...slotsEl.querySelectorAll('.custom-occ-sel')].map(s => s.value).filter(Boolean);
      if (picked.length < 5) {{
        warnEl.textContent = '請至少選擇 5 名先發職業。';
        return;
      }}
      const c = countOccs(picked);
      const over = Object.keys(c).filter(k => c[k] > 2);
      if (over.length) {{
        warnEl.textContent = `違反賽制上限：${{over.join('、')}} 超過 2 隻！`;
        return;
      }}
      warnEl.textContent = '';
      customBox.classList.remove('open');
      saveMyTeam({{
        mode: 'custom',
        rank: null,
        team_name: (nameInp && nameInp.value.trim()) || '我方自選陣容',
        score: null,
        occupations: picked,
      }});
    }};
  }}

  const btnClr = document.getElementById('btnClearMyTeam');
  if (btnClr) btnClr.onclick = () => saveMyTeam(null);

  myTeam = loadMyTeam();
  renderMyTeamBar();
}}

function buildHeadToHeadHtml(team) {{
  if (!myTeam) return '';
  if (myTeam.mode === 'rank' && myTeam.rank === team.rank) {{
    return `<div class="h2h-box" style="border-color:rgba(74,222,128,.55)">🛡️ <b>此隊伍為目前已鎖定的我方戰隊</b>（點選其他對手列即可自動顯示雙方 10 秒客觀對位對照）。</div>`;
  }}
  const myOccs = (myTeam.occupations || []).filter(Boolean);
  const oppOccs = (team.occupations || []).filter(Boolean);
  const mc = countOccs(myOccs);
  const oc = countOccs(oppOccs);

  const myH = mc['補師'] || 0, oppH = oc['補師'] || 0;
  let healerNote = '雙方同為單補（互拚 G4 禁補）', healerCls = '';
  if (myH >= 2 && oppH <= 1) {{ healerNote = '✅ 我方 G4 禁補佔優'; healerCls = 'h2h-adv'; }}
  else if (myH <= 1 && oppH >= 2) {{ healerNote = '⚠️ 敵方雙補・我方單補需防 G4 禁補'; healerCls = 'h2h-warn'; }}
  else if (myH >= 2 && oppH >= 2) {{ healerNote = '⚖️ 雙方同為雙補配置'; }}
  else if (oppH === 0 && myH >= 1) {{ healerNote = '✅ 敵方無補・我方續航壓制'; healerCls = 'h2h-adv'; }}

  const myAlc = !!mc['煉金'], oppAlc = !!oc['煉金'];
  const alcNote = myAlc && !oppAlc ? '✅ 我方獨有護貝/毀裝' : !myAlc && oppAlc ? '⚠️ 敵方獨有護貝/毀裝' : myAlc && oppAlc ? '⚖️ 雙方皆有煉金' : '➖ 雙方皆無煉金';
  const alcCls = myAlc && !oppAlc ? 'h2h-adv' : !myAlc && oppAlc ? 'h2h-warn' : '';

  const myDru = !!mc['德魯伊'], oppDru = !!oc['德魯伊'];
  const druNote = myDru && !oppDru ? '✅ 我方獨有德魯伊 AOE' : !myDru && oppDru ? '⚠️ 敵方獨有德魯伊 AOE' : myDru && oppDru ? '⚖️ 雙方皆有德魯伊' : '➖ 雙方皆無德魯伊';
  const druCls = myDru && !oppDru ? 'h2h-adv' : !myDru && oppDru ? 'h2h-warn' : '';

  const myMonk = !!mc['武僧'], oppMonk = !!oc['武僧'];
  const monkNote = myMonk && !oppMonk ? '✅ 我方獨有阿修羅威脅' : !myMonk && oppMonk ? '⚠️ 敵方有武僧・需防減員' : myMonk && oppMonk ? '⚖️ 雙方皆有武僧' : '➖ 雙方皆無武僧';
  const monkCls = !myMonk && oppMonk ? 'h2h-warn' : '';

  const myDuels = DUEL_CLASSES.filter(k => mc[k]);
  const oppDuels = DUEL_CLASSES.filter(k => oc[k]);
  const myDbl = Object.keys(mc).filter(k => mc[k] >= 2);
  const oppDbl = Object.keys(oc).filter(k => oc[k] >= 2);

  const scoreDiffHtml = (myTeam.score !== null && myTeam.score !== undefined && team.score !== null && team.score !== undefined)
    ? `<span class="sub" style="font-size:0.82rem">積分對照：我方 <b>${{myTeam.score}}分</b> (#${{myTeam.rank}}) vs 敵方 <b>${{team.score}}分</b> (#${{team.rank}})</span>`
    : `<span class="sub" style="font-size:0.82rem">我方：<b>${{esc(myTeam.team_name)}}</b> vs 敵方：<b>#${{team.rank}} ${{esc(team.team_name)}}</b></span>`;

  return `
  <div class="h2h-box">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">
      <b style="color:var(--accent);font-size:0.9rem">⚔️ 我方 vs 對手 — 10 秒客觀對位對照</b>
      ${{scoreDiffHtml}}
    </div>
    <div class="h2h-grid">
      <div class="h2h-item ${{healerCls}}"><div class="h-lbl">補師資源（G4 禁補關鍵）</div><b>我 ×${{myH}} vs 敵 ×${{oppH}}</b><div style="font-size:0.78rem;margin-top:2px">${{healerNote}}</div></div>
      <div class="h2h-item ${{alcCls}}"><div class="h-lbl">煉金護貝 ＆ 毀裝</div><b>我 ${{myAlc?'✅':'❌'}} / 敵 ${{oppAlc?'✅':'❌'}}</b><div style="font-size:0.78rem;margin-top:2px">${{alcNote}}</div></div>
      <div class="h2h-item ${{druCls}}"><div class="h-lbl">德魯伊 5v5 範圍壓制</div><b>我 ${{myDru?'✅':'❌'}} / 敵 ${{oppDru?'✅':'❌'}}</b><div style="font-size:0.78rem;margin-top:2px">${{druNote}}</div></div>
      <div class="h2h-item ${{monkCls}}"><div class="h-lbl">武僧阿修羅秒殺點</div><b>我 ${{myMonk?'✅':'❌'}} / 敵 ${{oppMonk?'✅':'❌'}}</b><div style="font-size:0.78rem;margin-top:2px">${{monkNote}}</div></div>
      <div class="h2h-item"><div class="h-lbl">G2 單挑強點（賢/流/騎/僧）</div><b>我 ${{myDuels.length}} 種 vs 敵 ${{oppDuels.length}} 種</b><div class="sub" style="font-size:0.76rem;margin-top:2px">敵：${{oppDuels.join('、') || '無'}}</div></div>
      <div class="h2h-item"><div class="h-lbl">雙職業輪轉資源</div><b>我 ${{myDbl.length}} 組 vs 敵 ${{oppDbl.length}} 組</b><div class="sub" style="font-size:0.76rem;margin-top:2px">敵：${{oppDbl.length ? oppDbl.map(d=>d+'×2').join('、') : '無'}}</div></div>
    </div>
    <div style="margin-top:8px;font-size:0.81rem;display:flex;flex-wrap:wrap;gap:12px;align-items:center">
      <span><b>我方預設前5：</b>${{myOccs.slice(0,5).map(o => `<span class="pill" style="padding:2px 6px">${{ico(o)}}${{esc(o)}}</span>`).join('')}}</span>
      <span><b>對手預設前5：</b>${{oppOccs.slice(0,5).map(o => `<span class="pill" style="padding:2px 6px">${{ico(o)}}${{esc(o)}}</span>`).join('')}}</span>
    </div>
  </div>`;
}}

// ============================================================
// C1: Opponent Roster Features, Threats & Objective Gaps Card
// ============================================================
function buildScoutCardHtml(team) {{
  const rawOccs = (team.occupations || []).filter(Boolean);
  const counts = countOccs(rawOccs);
  const doubles = Object.keys(counts).filter(o => counts[o] >= 2);
  const isSelf = myTeam && myTeam.mode === 'rank' && myTeam.rank === team.rank;

  const threats = [];
  const gaps = [];

  if ((counts['補師'] || 0) >= 2) {{
    threats.push('💉 <b>雙補師配置 (補師×2)</b>：可分攤 5v5 與 3v3 出戰紀錄，即使 G4 (2v2) 禁選掉其 G3 補師，對手 G4 席次 1 仍可保底有補師登場。');
  }} else if ((counts['補師'] || 0) === 1) {{
    gaps.push('🚫 <b>單補師配置 (補師×1)</b>：若對手在 G1 (5v5) 與 G3 (3v3) 皆出動補師，進入 G4 (2v2) 時<b>可優先禁選其 G3 補師</b>，迫使對手打無補師局。');
  }} else {{
    gaps.push('⚠️ <b>無正統補師名單</b>：對手 8 人名單未攜帶補師，續航與復活容錯極低，可全力強壓換血。');
  }}

  if ((counts['法師'] || 0) >= 2) {{
    threats.push('❄️ <b>雙法師配置 (法師×2)</b>：可跨局分攤 G1/G3/G4 控場，使各局皆有法師控場不斷檔。');
  }}
  if ((counts['詩人'] || 0) >= 2) {{
    threats.push('🎵 <b>雙詩人配置 (詩人×2)</b>：可跨局分攤 3v3/2v2 輔助位，或於賽前切換「1 輔助流 ＋ 1 輸出流」。');
  }}
  if (counts['德魯伊']) {{
    threats.push('🌿 <b>德魯伊團戰範圍壓制</b>：大範圍 AOE 傷害與控場在 5v5 團戰威脅極高，需注意分散站位。');
  }} else {{
    gaps.push('🌿 <b>缺德魯伊</b>：5v5 團戰缺少最強大範圍 AOE 壓制核心，我方團戰陣型站位壓力較低。');
  }}

  if (counts['武僧']) {{
    threats.push('🥊 <b>武僧阿修羅減員威脅</b>：核心戰術為阿修羅一拳秒殺製造人數差，需特別注意關鍵目標保護。');
  }}

  if (counts['煉金']) {{
    threats.push('⚗️ <b>煉金護貝＆毀裝干擾</b>：具備護貝（保護隊友免於裝備破壞）與單體攻擊破壞我方裝備的能力。');
  }} else {{
    gaps.push('🧪 <b>缺煉金（無護貝保護）</b>：對手名單未帶煉金防毀裝，我方若有毀裝手段或針對前排破甲時收益大增。');
  }}

  if (counts['刺客'] || counts['流氓']) {{
    const burstNames = ['流氓', '刺客'].filter(c => counts[c]).join('、');
    threats.push(`🗡️ <b>高機動手長單體爆發（${{burstNames}}）</b>：機動性佳、手長且單體 DPS 爆發高，但本體偏軟，可透過控場鎖定後集火反殺。`);
  }}

  // G2 (1v1) Duelist Pool Analysis (賢者 / 流氓 / 騎士 / 武僧)
  const duelists = DUEL_CLASSES.filter(c => counts[c]);
  if (!counts['賢者'] && duelists.length === 0) {{
    gaps.push('🤺 <b>極度缺乏 1v1 單挑強點</b>：名單無賢者／流氓／騎士／武僧，G2 單挑局對位壓力明顯較小。');
  }} else if (!counts['賢者'] && duelists.length === 1) {{
    gaps.push(`🤺 <b>缺賢者且 1v1 牌池極窄</b>：僅有「<b>${{duelists[0]}}</b>」為常見 1v1 強點，G2 賽前極易預判其單挑人選。`);
  }} else if (!counts['賢者']) {{
    gaps.push(`🤺 <b>缺賢者（無第一梯隊 1v1 核心）</b>：對手 G2 單挑主力將聚焦於「<b>${{duelists.join('、')}}</b>」。`);
  }} else if (duelists.length === 1) {{
    gaps.push('🤺 <b>1v1 核心單一（僅賢者）</b>：除賢者外無流氓／騎士／武僧，G2 高機率圍繞賢者出牌。');
  }}

  if (!counts['騎士'] && !counts['十字']) {{
    gaps.push('🛡️ <b>缺正統前排（無騎士／無十字）</b>：正面承傷與強開坦度偏薄。');
  }}
  if (rawOccs.length < 8) {{
    gaps.push(`👥 <b>名單未滿編（僅 ${{rawOccs.length}} 人）</b>：跨局輪換與針對性替補彈性受限。`);
  }}

  if (!threats.length) {{
    threats.push('⚖️ 無雙職業爆發點或極端減員威脅，屬偏常規之均衡陣容。');
  }}
  if (!gaps.length) {{
    gaps.push('✅ <b>名單無明顯職業缺口</b>（雙補＋煉金＋德魯伊＋多單挑點＋前排＋滿編皆齊全），屬高完整度強隊，建議回歸對位細節與機體應對。');
  }}

  const default5Str = rawOccs.slice(0, 5).join(' / ');
  const bench3Str = rawOccs.slice(5, 8).join(' / ');

  return `
  <div class="scout-box">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <div><b>🎯 #${{team.rank}} ${{esc(team.team_name)}} — 對手陣容特徵 ＆ 實戰對局提醒</b></div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <span class="sub">雙職業配置：${{doubles.length ? doubles.map(d => `<b>${{d}}×2</b>`).join('、') : '無（全 8 異職）'}}</span>
        <button class="chip-btn ${{isSelf ? 'active' : ''}}" type="button" onclick="setMyTeamByRank(${{team.rank}}, event)">${{isSelf ? '✅ 已鎖定為我方戰隊' : '🛡️ 設為我方戰隊'}}</button>
      </div>
    </div>
    ${{buildHeadToHeadHtml(team)}}
    <div class="sub" style="margin-top:8px;font-size:0.84rem;background:#0b1120;border:1px solid var(--border);border-radius:8px;padding:7px 11px">
      📋 <b>遊戲內預設席次</b>：前 5 格預設先發【<b style="color:var(--text)">${{esc(default5Str)}}</b>】｜後 3 格替補【<b style="color:var(--text)">${{esc(bench3Str || '無')}}</b>】（開賽前仍可替換）
    </div>
    <div class="scout-cols">
      <div class="scout-col threat">
        <h4 style="color:var(--accent2)">⚠️ 對方關鍵威脅 ＆ 輪轉優勢</h4>
        ${{threats.map(t => `<div>• ${{t}}</div>`).join('')}}
      </div>
      <div class="scout-col gap">
        <h4 style="color:var(--green)">🎯 對方陣容缺口（可針對破綻）</h4>
        ${{gaps.map(g => `<div>• ${{g}}</div>`).join('')}}
      </div>
    </div>
  </div>`;
}}

// Tab 1 Filtering (Script + Visual Feature + Score Bracket + Fuzzy Search + Click-to-Scout)
const occSel = document.getElementById('occFilter');
A.occupation_frequency.forEach(r => {{ const o = document.createElement('option'); o.value = r.occupation; o.textContent = r.occupation; occSel.appendChild(o); }});
const dpSel = document.getElementById('dpFilter');
let activeScript = 'all';
let activeFeat = 'all';
let expandedRanks = new Set();

function applyScoreFilter(minSc, maxSc) {{
  activeScoreRange = {{ min: Number(minSc), max: Number(maxSc) }};
  const banner = document.getElementById('scoreFilterBanner');
  const txt = document.getElementById('scoreFilterText');
  if (banner && txt) {{
    txt.innerHTML = `🎯 <b>目前僅顯示同分圈對手：積分 ${{activeScoreRange.min}} ～ ${{activeScoreRange.max}} 分</b>`;
    banner.classList.add('open');
  }}
  renderRaw();
}}

function clearScoreFilter() {{
  activeScoreRange = null;
  const banner = document.getElementById('scoreFilterBanner');
  if (banner) banner.classList.remove('open');
  renderRaw();
}}
const btnClrSc = document.getElementById('btnClearScoreFilter');
if (btnClrSc) btnClrSc.onclick = clearScoreFilter;

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
    if (activeScoreRange && (r.score === null || r.score === undefined || r.score < activeScoreRange.min || r.score > activeScoreRange.max)) return false;
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
    const isMy = myTeam && myTeam.mode === 'rank' && myTeam.rank === r.rank;
    const myTag = isMy ? '<span class="q-tag q-dark" style="margin-right:6px">🛡️ 我方</span>' : '';
    rowsHtml += `<tr class="team-row ${{isMy ? 'is-my-team' : ''}}" onclick="toggleScoutRow(${{r.rank}})">
      <td class="col-rank"><b>#${{r.rank}}</b></td>
      <td class="col-name">${{myTag}}${{scriptBadge(detectScript(r.team_name))}}<b>${{esc(r.team_name)}}</b> <span class="sub" style="font-size:0.75rem">${{isExp ? '▲ 收合' : '▼ 提醒'}}</span></td>
      <td class="col-score">${{r.score ?? '-'}}分</td>
      <td class="col-dp">${{r.double_pick_count}} 組雙職</td>
      <td class="col-occs">${{r.occupations.map(o => `<span class="pill ${{counts[o]>=2?'dp':''}}">${{ico(o)}}<span>${{esc(o)}}</span></span>`).join('')}}</td>
    </tr>`;
    if (isExp) {{
      rowsHtml += `<tr class="scout-detail-row"><td colspan="5" style="padding:4px 10px 14px;background:#090e1a">${{buildScoutCardHtml(r)}}</td></tr>`;
    }}
  }});

  document.getElementById('rawTable').innerHTML =
    '<thead><tr><th>排名</th><th>戰隊名稱（點擊展開對局提醒卡）</th><th>積分</th><th>雙職業</th><th>8 人名單配置（金色外框＝雙職業）</th></tr></thead><tbody>' +
    rowsHtml + '</tbody>';
}}
document.getElementById('searchInput').oninput = renderRaw;
occSel.onchange = renderRaw;
dpSel.onchange = renderRaw;
initMyTeamControls();
renderRaw();

// ============================================================
// C5: Score Cutoffs & Target Bracket Opponent Environment
// ============================================================
let renderBracketPresets = null;
(function initScoreBracketPanel() {{
  const card = document.getElementById('scoreBracketCard');
  const cutGrid = document.getElementById('cutoffGrid');
  const densTbl = document.getElementById('scoreDensityTable');
  const presetBar = document.getElementById('bracketPresetBar');
  const minSel = document.getElementById('bracketMinScore');
  const maxSel = document.getElementById('bracketMaxScore');
  const metaTxt = document.getElementById('bracketMetaText');
  const kpiGrid = document.getElementById('bracketKpiGrid');
  const occGrid = document.getElementById('bracketOccGrid');
  const jumpBtn = document.getElementById('btnJumpBracketToRaw');

  const scoreTiers = A.score_tiers || [];
  const scoreCutoffs = A.score_cutoffs || [];
  const teamsWithScore = A.raw_data.filter(t => t.score !== null && t.score !== undefined);
  if (!card || !teamsWithScore.length || !scoreTiers.length) {{
    const tabBtn = document.querySelector('.tab[data-tab="bracket"]');
    if (tabBtn) tabBtn.style.display = 'none';
    if (card) card.style.display = 'none';
    return;
  }}

  // 1. Render Milestone Cutoffs
  if (cutGrid) {{
    cutGrid.innerHTML = scoreCutoffs.map(c => `
      <div class="cutoff-pill">
        <div class="c-rank">${{esc(c.label)}} 門檻線</div>
        <div class="c-score">${{c.cutoff_score}} 分 <span class="sub" style="font-size:0.78rem;font-weight:500">（穩進 ${{c.safe_score}}+ 分）</span></div>
        <div class="c-tie">同分擠壓：<b>${{c.tied_teams}} 隊</b>同為 ${{c.cutoff_score}} 分（${{esc(c.tied_rank_range)}}）</div>
      </div>`).join('');
  }}

  // 2. Render Ladder Score Density Table
  const maxTierCnt = Math.max(...scoreTiers.map(s => s.team_count), 1);
  if (densTbl) {{
    densTbl.innerHTML = '<thead><tr><th>積分</th><th>隊伍數（擠壓密度）</th><th>排名區間</th><th>雙補師率</th><th>德魯伊率</th><th>武僧率</th><th>平均雙職業</th></tr></thead><tbody>' +
      scoreTiers.map(s => {{
        const wPct = Math.max(4, Math.round((s.team_count / maxTierCnt) * 100));
        return `<tr class="team-row" onclick="selectScoreBracket(${{s.score}}, ${{s.score}})">
          <td><b>${{s.score}} 分</b></td>
          <td style="min-width:190px">
            <div style="display:flex;align-items:center;gap:8px">
              <div class="density-bar-wrap" style="flex:1"><div class="density-bar" style="width:${{wPct}}%"></div></div>
              <span style="min-width:54px;text-align:right"><b>${{s.team_count}} 隊</b></span>
            </div>
          </td>
          <td>${{esc(s.rank_range)}}</td>
          <td>${{pct(s.double_healer_rate)}}</td>
          <td>${{pct(s.druid_rate)}}</td>
          <td>${{pct(s.monk_rate)}}</td>
          <td>${{s.avg_doubles}} 組</td>
        </tr>`;
      }}).join('') + '</tbody>';
  }}

  // Overall baseline rates for delta comparison
  const totalN = teamsWithScore.length;
  const overallOccRate = {{}};
  A.occupation_frequency.forEach(r => overallOccRate[r.occupation] = r.team_presence_rate);
  const overallDblHealer = teamsWithScore.filter(t => countOccs(t.occupations)['補師'] >= 2).length / totalN;
  const overallDruid = teamsWithScore.filter(t => countOccs(t.occupations)['德魯伊'] >= 1).length / totalN;
  const overallMonk = teamsWithScore.filter(t => countOccs(t.occupations)['武僧'] >= 1).length / totalN;
  const overallAlc = teamsWithScore.filter(t => countOccs(t.occupations)['煉金'] >= 1).length / totalN;
  const overallAvgDp = teamsWithScore.reduce((s, t) => s + (t.double_pick_count || 0), 0) / totalN;

  const allScoresDesc = scoreTiers.map(s => s.score);
  const maxSc = allScoresDesc[0];
  const minSc = allScoresDesc[allScoresDesc.length - 1];

  const scOpts = allScoresDesc.map(sc => `<option value="${{sc}}">${{sc}} 分</option>`).join('');
  minSel.innerHTML = scOpts;
  maxSel.innerHTML = scOpts;

  function fmtDelta(val, base) {{
    const diff = (val - base) * 100;
    if (Math.abs(diff) < 0.8) return '<span class="sub">（與全服相近）</span>';
    const cls = diff > 0 ? 'pos' : 'neg';
    return `<span class="${{cls}}">（較全服 ${{diff > 0 ? '+' : ''}}${{diff.toFixed(1)}}%）</span>`;
  }}

  function renderBracket(lo, hi) {{
    const loN = Math.min(Number(lo), Number(hi));
    const hiN = Math.max(Number(lo), Number(hi));
    minSel.value = String(loN);
    maxSel.value = String(hiN);

    const sub = teamsWithScore.filter(t => t.score >= loN && t.score <= hiN);
    if (!sub.length) {{
      metaTxt.textContent = '此區間無隊伍資料';
      kpiGrid.innerHTML = '';
      occGrid.innerHTML = '';
      return;
    }}
    const rMin = Math.min(...sub.map(t => t.rank));
    const rMax = Math.max(...sub.map(t => t.rank));
    metaTxt.textContent = `共 ${{sub.length}} 支假想敵｜涵蓋排名 #${{rMin}} ～ #${{rMax}}`;
    if (jumpBtn) {{
      jumpBtn.textContent = `🔍 在排行榜查看這 ${{sub.length}} 支同分圈對手 (${{loN}}~${{hiN}}分)`;
      jumpBtn.onclick = () => {{
        document.querySelector('.tab[data-tab="raw"]').click();
        applyScoreFilter(loN, hiN);
        document.getElementById('rawTable').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }};
    }}

    const n = sub.length;
    const cntDblH = sub.filter(t => (countOccs(t.occupations)['補師'] || 0) >= 2).length;
    const cntSglH = sub.filter(t => (countOccs(t.occupations)['補師'] || 0) === 1).length;
    const cntDru = sub.filter(t => countOccs(t.occupations)['德魯伊']).length;
    const cntMonk = sub.filter(t => countOccs(t.occupations)['武僧']).length;
    const cntAlc = sub.filter(t => countOccs(t.occupations)['煉金']).length;
    const avgDp = sub.reduce((s, t) => s + (t.double_pick_count || 0), 0) / n;

    // Top 2 double-pick classes in this bracket
    const dpMap = {{}};
    sub.forEach(t => {{
      const c = countOccs(t.occupations);
      Object.keys(c).forEach(k => {{ if (c[k] >= 2) dpMap[k] = (dpMap[k] || 0) + 1; }});
    }});
    const topDps = Object.entries(dpMap).sort((a, b) => b[1] - a[1]).slice(0, 2)
      .map(([k, v]) => `${{k}}×2 (${{Math.round(v / n * 100)}}%)`).join('、') || '無';

    kpiGrid.innerHTML = [
      ['💉 雙補師比例（補×2）', `${{pct(cntDblH / n)}} <span class="sub" style="font-size:0.84rem">(${{cntDblH}}隊)</span>`, `${{fmtDelta(cntDblH / n, overallDblHealer)}}<br>單補 G4 可禁對象：<b>${{cntSglH}} 隊</b> (${{pct(cntSglH / n)}})`],
      ['🌿 德魯伊出場率（5v5 AOE）', `${{pct(cntDru / n)}} <span class="sub" style="font-size:0.84rem">(${{cntDru}}隊)</span>`, `${{fmtDelta(cntDru / n, overallDruid)}}<br>缺德魯伊隊數：${{n - cntDru}} 隊`],
      ['🥊 武僧出場率（阿修羅）', `${{pct(cntMonk / n)}} <span class="sub" style="font-size:0.84rem">(${{cntMonk}}隊)</span>`, `${{fmtDelta(cntMonk / n, overallMonk)}}<br>需防一拳減員頻率`],
      ['⚗️ 煉金覆蓋率（護貝）', `${{pct(cntAlc / n)}} <span class="sub" style="font-size:0.84rem">(${{cntAlc}}隊)</span>`, `${{fmtDelta(cntAlc / n, overallAlc)}}<br>無煉金（無護貝）：<b>${{n - cntAlc}} 隊</b>`],
      ['⚔️ 平均雙職業組數', `${{avgDp.toFixed(2)}} 組`, `全服平均 ${{overallAvgDp.toFixed(2)}} 組<br>最常見：${{topDps}}`],
    ].map(([l, v, s]) => `<div class="bracket-kpi"><div class="b-lbl">${{l}}</div><div class="b-val">${{v}}</div><div class="b-sub">${{s}}</div></div>`).join('');

    // Per-occupation breakdown sorted by presence in this bracket
    const occRows = A.occupation_frequency.map(r => {{
      const o = r.occupation;
      const c = sub.filter(t => (t.occupations || []).includes(o)).length;
      const rate = c / n;
      const diff = (rate - (overallOccRate[o] || 0)) * 100;
      return {{ o, c, rate, diff, low_sample: r.low_sample }};
    }}).sort((a, b) => b.rate - a.rate || b.diff - a.diff);

    occGrid.innerHTML = occRows.map(x => {{
      const w = Math.max(2, Math.round(x.rate * 100));
      const dTxt = Math.abs(x.diff) < 0.8
        ? '<span class="sub">±0%</span>'
        : `<span class="${{x.diff > 0 ? 'pos' : 'neg'}}">${{x.diff > 0 ? '+' : ''}}${{x.diff.toFixed(1)}}%</span>`;
      const dim = x.low_sample ? ' style="opacity:0.68"' : '';
      return `<div class="bracket-occ-row"${{dim}}>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span class="lbl-flex">${{ico(x.o)}}${{esc(x.o)}}</span>
          <span><b>${{pct(x.rate)}}</b> (${{x.c}}隊) ${{dTxt}}</span>
        </div>
        <div class="density-bar-wrap" style="height:8px"><div class="density-bar" style="width:${{w}}%;background:${{x.diff >= 5 ? '#4ade80' : x.diff <= -5 ? '#f87171' : '#38bdf8'}}"></div></div>
      </div>`;
    }}).join('');
  }}

  window.selectScoreBracket = function(lo, hi) {{
    document.querySelectorAll('#bracketPresetBar .chip-btn').forEach(b => b.classList.remove('active'));
    renderBracket(lo, hi);
    card.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }};

  // Build smart score presets based on actual cutoffs + C3 myTeam score!
  const c16 = scoreCutoffs.find(c => c.rank_cutoff === 16) || scoreCutoffs[0];
  const c32 = scoreCutoffs.find(c => c.rank_cutoff === 32);
  const c100 = scoreCutoffs.find(c => c.rank_cutoff === 100);

  renderBracketPresets = function() {{
    const presets = [];
    if (myTeam && myTeam.score !== null && myTeam.score !== undefined) {{
      const ms = Number(myTeam.score);
      presets.push({{
        label: `🎯 我方同分圈 (${{Math.max(minSc, ms - 1)}}~${{Math.min(maxSc, ms + 1)}}分)`,
        lo: Math.max(minSc, ms - 1),
        hi: Math.min(maxSc, ms + 1),
        highlight: true,
      }});
    }}
    if (c16) {{
      presets.push({{ label: `🏆 爭冠頂端 (${{c16.cutoff_score}}~${{maxSc}}分)`, lo: c16.cutoff_score, hi: maxSc }});
    }}
    if (c32 && c16) {{
      const lo32 = Math.max(minSc, c32.cutoff_score - 1);
      presets.push({{ label: `🔥 前32卡位圈 (${{lo32}}~${{c16.cutoff_score}}分)`, lo: lo32, hi: c16.cutoff_score }});
    }}
    if (c100 && c32) {{
      presets.push({{ label: `⚔️ 中段混戰圈 (${{c100.cutoff_score}}~${{Math.max(c100.cutoff_score, c32.cutoff_score - 1)}}分)`, lo: c100.cutoff_score, hi: Math.max(c100.cutoff_score, c32.cutoff_score - 1) }});
    }}
    if (c100 && c100.cutoff_score > minSc) {{
      presets.push({{ label: `🛡️ 百名後段 (${{minSc}}~${{c100.cutoff_score - 1}}分)`, lo: minSc, hi: c100.cutoff_score - 1 }});
    }}
    presets.push({{ label: `🌐 全服 (${{minSc}}~${{maxSc}}分)`, lo: minSc, hi: maxSc }});

    presetBar.innerHTML = '<span class="sub" style="margin-right:4px">快速分段：</span>' +
      presets.map((p, idx) => `<button class="chip-btn ${{idx === 0 ? 'active' : ''}}" type="button" data-lo="${{p.lo}}" data-hi="${{p.hi}}" style="${{p.highlight ? 'border-color:var(--green);color:#86efac' : ''}}">${{esc(p.label)}}</button>`).join('');

    presetBar.querySelectorAll('.chip-btn').forEach(btn => {{
      btn.onclick = () => {{
        presetBar.querySelectorAll('.chip-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderBracket(Number(btn.dataset.lo), Number(btn.dataset.hi));
      }};
    }});
    if (presets.length) renderBracket(presets[0].lo, presets[0].hi);
  }};

  minSel.onchange = () => {{
    presetBar.querySelectorAll('.chip-btn').forEach(b => b.classList.remove('active'));
    renderBracket(Number(minSel.value), Number(maxSel.value));
  }};
  maxSel.onchange = () => {{
    presetBar.querySelectorAll('.chip-btn').forEach(b => b.classList.remove('active'));
    renderBracket(Number(minSel.value), Number(maxSel.value));
  }};

  renderBracketPresets();
}})();

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
    activeScoreRange = null;
    const scBan = document.getElementById('scoreFilterBanner');
    if (scBan) scBan.classList.remove('open');
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

  // Collapse desktop-centric screenshot OCR box by default on narrow mobile screens so search & leaderboard start above the fold
  const ocrDet = document.getElementById('ocrScoutDetails');
  if (ocrDet && window.innerWidth <= 768) ocrDet.removeAttribute('open');

  function handleScreenshotDataUrl(rawDataUrl) {{
    // Switch to Tab 1 and expand OCR box if user pasted while viewing another tab
    document.querySelector('.tab[data-tab="raw"]').click();
    if (ocrDet) ocrDet.setAttribute('open', '');
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

// Universal Click-to-Zoom & Pan Lightbox Controller
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
    downX = ev.clientX;
    downY = ev.clientY;
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
  window.addEventListener('mouseup', ev => {{
    if (!dragging) return;
    dragging = false;
    stage.classList.remove('dragging');
    // If user clicked without dragging and pointer is outside the rendered image bounds, close modal!
    if (Math.hypot(ev.clientX - downX, ev.clientY - downY) < 6) {{
      const r = img.getBoundingClientRect();
      const insideImg = ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom;
      if (!insideImg) closeZoom();
    }}
  }});
  stage.addEventListener('dblclick', () => {{
    if (scale > 1.05) {{ scale = 1; tx = 0; ty = 0; }}
    else {{ scale = 2.2; }}
    applyTransform();
  }});

  // Mobile Touch Support: 2-finger pinch-to-zoom, 1-finger pan, double-tap zoom, tap-outside to close
  let pinchStartDist = 0, pinchStartScale = 1, touchDragging = false;
  let touchStartX = 0, touchStartY = 0, touchDownX = 0, touchDownY = 0, touchMoved = false, lastTapTime = 0;

  stage.addEventListener('touchstart', ev => {{
    if (ev.touches.length === 2) {{
      ev.preventDefault();
      touchDragging = false;
      touchMoved = true;
      pinchStartDist = Math.hypot(
        ev.touches[0].clientX - ev.touches[1].clientX,
        ev.touches[0].clientY - ev.touches[1].clientY
      ) || 1;
      pinchStartScale = scale;
    }} else if (ev.touches.length === 1) {{
      ev.preventDefault();
      const t = ev.touches[0];
      touchDragging = true;
      touchMoved = false;
      touchDownX = t.clientX;
      touchDownY = t.clientY;
      touchStartX = t.clientX - tx;
      touchStartY = t.clientY - ty;
    }}
  }}, {{ passive: false }});

  stage.addEventListener('touchmove', ev => {{
    if (ev.touches.length === 2) {{
      ev.preventDefault();
      const dist = Math.hypot(
        ev.touches[0].clientX - ev.touches[1].clientX,
        ev.touches[0].clientY - ev.touches[1].clientY
      );
      scale = Math.max(0.5, Math.min(5, +(pinchStartScale * (dist / pinchStartDist)).toFixed(2)));
      applyTransform();
    }} else if (ev.touches.length === 1 && touchDragging) {{
      ev.preventDefault();
      const t = ev.touches[0];
      if (Math.hypot(t.clientX - touchDownX, t.clientY - touchDownY) > 6) touchMoved = true;
      tx = t.clientX - touchStartX;
      ty = t.clientY - touchStartY;
      applyTransform();
    }}
  }}, {{ passive: false }});

  stage.addEventListener('touchend', ev => {{
    if (ev.touches.length === 0) {{
      if (touchDragging && !touchMoved && ev.changedTouches && ev.changedTouches[0]) {{
        const t = ev.changedTouches[0];
        const r = img.getBoundingClientRect();
        const insideImg = t.clientX >= r.left && t.clientX <= r.right && t.clientY >= r.top && t.clientY <= r.bottom;
        if (!insideImg) {{
          closeZoom();
        }} else {{
          const now = Date.now();
          if (now - lastTapTime < 300) {{
            if (scale > 1.05) {{ scale = 1; tx = 0; ty = 0; }}
            else {{ scale = 2.2; }}
            applyTransform();
            lastTapTime = 0;
          }} else {{
            lastTapTime = now;
          }}
        }}
      }}
      touchDragging = false;
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
    out.write_text(html_doc, encoding="utf-8")
    return out
