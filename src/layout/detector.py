"""Automatic leaderboard ROI detection, personal-row exclusion, and visualization.

All sub-regions inside the detected leaderboard panel are stored as normalized
ratios (0.0 - 1.0) so the layout remains resilient to scaling, OBS window
borders, or minor shifts, and can be fine-tuned visually in the Web UI.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Box:
    """Axis-aligned rectangle in pixel coordinates."""

    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def crop(self, img: np.ndarray) -> np.ndarray:
        ih, iw = img.shape[:2]
        x1 = max(0, min(iw, self.x))
        y1 = max(0, min(ih, self.y))
        x2 = max(x1, min(iw, self.x2))
        y2 = max(y1, min(ih, self.y2))
        return img[y1:y2, x1:x2]


@dataclass
class LayoutConfig:
    """Serializable ROI specification relative to the detected leaderboard panel."""

    frame_width: int
    frame_height: int
    panel_box: list[int]  # [x, y, w, h] in pixels

    # Normalized ratios relative to panel_box (0.0 - 1.0)
    header_y_ratio: list[float] = field(default_factory=lambda: [0.075, 0.163])
    scroll_area_ratio: list[float] = field(default_factory=lambda: [0.025, 0.163, 0.975, 0.830])
    personal_row_ratio: list[float] = field(default_factory=lambda: [0.025, 0.830, 0.975, 0.968])

    # Normalized X ranges relative to scroll_area width (0.0 - 1.0)
    rank_x_ratio: list[float] = field(default_factory=lambda: [0.005, 0.165])
    team_name_x_ratio: list[float] = field(default_factory=lambda: [0.165, 0.435])
    icons_x_ratio: list[float] = field(default_factory=lambda: [0.440, 0.775])
    score_x_ratio: list[float] = field(default_factory=lambda: [0.815, 0.990])

    # 8 icon center X positions relative to scroll_area width, and icon diameter ratio relative to row height
    icon_centers_x_ratio: list[float] = field(
        default_factory=lambda: [0.456, 0.495, 0.534, 0.573, 0.612, 0.652, 0.691, 0.730]
    )
    icon_size_ratio_of_row_h: float = 0.44
    expected_visible_rows: int = 5
    detection_notes: list[str] = field(default_factory=list)

    def panel(self) -> Box:
        x, y, w, h = self.panel_box
        return Box(int(x), int(y), int(w), int(h))

    def header_box(self) -> Box:
        p = self.panel()
        y1 = p.y + int(round(self.header_y_ratio[0] * p.h))
        y2 = p.y + int(round(self.header_y_ratio[1] * p.h))
        x1 = p.x + int(round(self.scroll_area_ratio[0] * p.w))
        x2 = p.x + int(round(self.scroll_area_ratio[2] * p.w))
        return Box(x1, y1, max(1, x2 - x1), max(1, y2 - y1))

    def scroll_box(self) -> Box:
        p = self.panel()
        x1 = p.x + int(round(self.scroll_area_ratio[0] * p.w))
        y1 = p.y + int(round(self.scroll_area_ratio[1] * p.h))
        x2 = p.x + int(round(self.scroll_area_ratio[2] * p.w))
        y2 = p.y + int(round(self.scroll_area_ratio[3] * p.h))
        return Box(x1, y1, max(1, x2 - x1), max(1, y2 - y1))

    def personal_row_box(self) -> Box:
        p = self.panel()
        x1 = p.x + int(round(self.personal_row_ratio[0] * p.w))
        y1 = p.y + int(round(self.personal_row_ratio[1] * p.h))
        x2 = p.x + int(round(self.personal_row_ratio[2] * p.w))
        y2 = p.y + int(round(self.personal_row_ratio[3] * p.h))
        return Box(x1, y1, max(1, x2 - x1), max(1, y2 - y1))

    @property
    def estimated_row_height(self) -> float:
        return self.scroll_box().h / max(1, self.expected_visible_rows)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "LayoutConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def _detect_panel_box(frame: np.ndarray) -> tuple[Box, str]:
    """Detect the bright cream/white leaderboard container on the right/center side."""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # The inner leaderboard body is bright low-saturation cream/white (S < 28, V > 230)
    # Exclude the far-left navigation sidebar (typically x < 20% of width).
    white_mask = ((hsv[:, :, 1] < 28) & (hsv[:, :, 2] > 230)).astype(np.uint8) * 255
    left_guard = int(w * 0.18)
    white_mask[:, :left_guard] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    closed = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_box: Box | None = None
    best_area = 0.0
    min_expected_area = w * h * 0.20  # Leaderboard panel should occupy at least 20% of screen

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        aspect = cw / max(1, ch)
        if area > best_area and area >= min_expected_area and 1.1 <= aspect <= 2.6:
            best_area = area
            best_box = Box(x, y, cw, ch)

    if best_box is not None:
        return best_box, f"自動偵測到排行榜白底主框 ({best_box.x}, {best_box.y}, {best_box.w}x{best_box.h})"

    # Fallback: proportional 1920x1080 calibrated defaults
    fallback = Box(
        int(round(w * 0.235)),
        int(round(h * 0.118)),
        int(round(w * 0.714)),
        int(round(h * 0.708)),
    )
    return fallback, "未達主框輪廓門檻，改用 16:9 預設比例外框"


def _find_contiguous_runs(mask_1d: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Return inclusive-exclusive (start, end) runs where boolean 1D mask is True."""
    padded = np.concatenate([[False], mask_1d.astype(bool), [False]])
    diff = np.diff(padded.astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    return [(int(s), int(e)) for s, e in zip(starts, ends) if (e - s) >= min_len]


def _detect_vertical_bands(
    samples: list[np.ndarray], panel: Box
) -> tuple[list[float], list[float], list[float], list[str]]:
    """Locate header band, 5-row scrollable area, and fixed bottom personal row.

    Combines TWO independent signals for robustness:
    1. Temporal variance across sampled frames (scrollable rows move; header & personal row stay static).
    2. HSV color profile (scrollable rows have low saturation white background;
       personal row has warm beige/gold higher saturation background).
    """
    notes: list[str] = []
    # Crop central 85% width of panel to avoid rounded corners / left-right border frames
    x1 = panel.x + int(panel.w * 0.06)
    x2 = panel.x + int(panel.w * 0.94)
    y1, y2 = panel.y, panel.y2
    ph = max(1, y2 - y1)

    # 1. Temporal std per horizontal scanline
    stack = np.stack([f[y1:y2, x1:x2] for f in samples], axis=0).astype(np.float32)
    tstd_y = stack.std(axis=0).mean(axis=(1, 2))  # shape (ph,)
    # Smooth slightly with 7-pixel moving average to bridge thin divider lines
    smooth_tstd = np.convolve(tstd_y, np.ones(7) / 7.0, mode="same")

    # 2. HSV saturation & value profile on first frame
    hsv0 = cv2.cvtColor(samples[0][y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    sat_y = hsv0[:, :, 1].mean(axis=1)
    val_y = hsv0[:, :, 2].mean(axis=1)

    # Active scrolling band: rows with strong temporal change (tstd > 3.5)
    active_runs = _find_contiguous_runs(smooth_tstd > 3.5, min_len=int(ph * 0.35))

    if active_runs:
        # Pick the longest active vertical span -> the 5-row scrollable area
        scroll_y1, scroll_y2 = max(active_runs, key=lambda r: r[1] - r[0])
        # Refine edges inward/outward using HSV saturation jump at top (header) and bottom (personal row)
        # Look near bottom edge for the warm personal row (S jumps above 35)
        search_bot_start = max(scroll_y1 + int(ph * 0.45), scroll_y2 - 20)
        search_bot_end = min(ph, scroll_y2 + 30)
        warm_hits = np.where(sat_y[search_bot_start:search_bot_end] > 35.0)[0]
        if len(warm_hits) > 0:
            scroll_y2 = search_bot_start + int(warm_hits[0])

        # Look near top edge for header bottom (S drops below 24 entering white scroll area)
        search_top_start = max(0, scroll_y1 - 25)
        search_top_end = min(ph, scroll_y1 + 20)
        header_hits = np.where(sat_y[search_top_start:search_top_end] > 26.0)[0]
        if len(header_hits) > 0:
            scroll_y1 = search_top_start + int(header_hits[-1]) + 1

        notes.append(
            f"透過跨影格時間變異＋HSV 色彩偵測到捲動區 y=[{y1+scroll_y1}, {y1+scroll_y2}] (高 {scroll_y2-scroll_y1}px)"
        )
    else:
        # Static video or minimal scroll fallback: rely on HSV saturation bands
        scroll_y1 = int(ph * 0.163)
        scroll_y2 = int(ph * 0.830)
        notes.append("影格間位移不足，改用預設比例推算捲動區垂直範圍")

    # Header band sits directly above scroll_y1 (warm tan band ~9% of panel height)
    header_y2 = scroll_y1
    header_y1 = max(0, header_y2 - int(ph * 0.09))
    header_band_hits = np.where((sat_y[:header_y2] > 24.0) & (val_y[:header_y2] < 235.0))[0]
    if len(header_band_hits) > 10:
        header_y1 = max(0, int(header_band_hits[0]))

    # Fixed bottom personal row sits directly below scroll_y2 (higher saturation warm beige, static)
    personal_y1 = scroll_y2
    personal_y2 = min(ph, scroll_y2 + int((scroll_y2 - scroll_y1) / 5.0))
    # Verify static + warm color below scroll_y2
    if personal_y2 > personal_y1 + 10:
        p_tstd = float(smooth_tstd[personal_y1:personal_y2].mean())
        p_sat = float(sat_y[personal_y1:personal_y2].mean())
        notes.append(
            f"偵測並排除底部固定個人列 y=[{y1+personal_y1}, {y1+personal_y2}] "
            f"(時間變異={p_tstd:.2f}, 平均飽和度S={p_sat:.1f})"
        )

    header_ratio = [round(header_y1 / ph, 4), round(header_y2 / ph, 4)]
    scroll_ratio = [0.025, round(scroll_y1 / ph, 4), 0.975, round(scroll_y2 / ph, 4)]
    personal_ratio = [0.025, round(personal_y1 / ph, 4), 0.975, round(personal_y2 / ph, 4)]
    return header_ratio, scroll_ratio, personal_ratio, notes


def _detect_icon_columns(
    samples: list[np.ndarray], scroll_box: Box
) -> tuple[list[float], list[float], list[str]]:
    """Auto-detect the 8 horizontal circular occupation icon centers inside scroll_box."""
    notes: list[str] = []
    # Average colorfulness (HSV saturation > 65) across sampled frames inside scroll_box
    sat_masks = []
    for f in samples:
        crop = scroll_box.crop(f)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        sat_masks.append((hsv[:, :, 1] > 65).astype(np.float32))
    sat_x = np.mean(sat_masks, axis=0).mean(axis=0)  # shape (scroll_w,)
    sw = max(1, scroll_box.w)

    # Icons live in the middle-right half of the table (roughly 35% - 82% of scroll width)
    left_lim = int(sw * 0.35)
    right_lim = int(sw * 0.82)
    sub_mask = np.zeros_like(sat_x, dtype=bool)
    sub_mask[left_lim:right_lim] = sat_x[left_lim:right_lim] > 0.10

    runs = _find_contiguous_runs(sub_mask, min_len=max(10, int(sw * 0.012)))
    if len(runs) == 8:
        centers = [round(((s + e) / 2.0) / sw, 4) for s, e in runs]
        span_left = max(0.0, round((runs[0][0] - 10) / sw, 4))
        span_right = min(1.0, round((runs[-1][1] + 10) / sw, 4))
        avg_width = float(np.mean([e - s for s, e in runs]))
        notes.append(
            f"自動偵測到 8 個職業圖示水平位置（平均彩區寬 {avg_width:.1f}px，中心間距 {(runs[-1][0]-runs[0][0])/7.0:.1f}px）"
        )
        return centers, [span_left, span_right], notes

    # If slight merging/noise happened, fit 8 evenly spaced centers across detected overall icon span
    if len(runs) >= 4:
        first_s = runs[0][0]
        last_e = runs[-1][1]
        slot_w = (last_e - first_s) / 8.0
        centers = [round((first_s + (i + 0.5) * slot_w) / sw, 4) for i in range(8)]
        span_left = max(0.0, round((first_s - 8) / sw, 4))
        span_right = min(1.0, round((last_e + 8) / sw, 4))
        notes.append(f"由 {len(runs)} 個高飽和區段等分擬合 8 個職業圖示中心")
        return centers, [span_left, span_right], notes

    default_centers = [0.456, 0.495, 0.534, 0.573, 0.612, 0.652, 0.691, 0.730]
    notes.append("未偵測到足夠彩度峰值，沿用預設 8 職業水平比例")
    return default_centers, [0.435, 0.765], notes


def detect_leaderboard_layout(sampled_frames: list[np.ndarray]) -> LayoutConfig:
    """Detect leaderboard panel, scrollable 5-row area, personal row, and 8 icon columns."""
    if not sampled_frames:
        raise ValueError("detect_leaderboard_layout 需要至少一張影格")

    h, w = sampled_frames[0].shape[:2]
    panel, panel_note = _detect_panel_box(sampled_frames[0])
    header_ratio, scroll_ratio, personal_ratio, band_notes = _detect_vertical_bands(
        sampled_frames, panel
    )

    cfg = LayoutConfig(
        frame_width=w,
        frame_height=h,
        panel_box=[panel.x, panel.y, panel.w, panel.h],
        header_y_ratio=header_ratio,
        scroll_area_ratio=scroll_ratio,
        personal_row_ratio=personal_ratio,
        detection_notes=[panel_note, *band_notes],
    )

    centers, icons_span, icon_notes = _detect_icon_columns(sampled_frames, cfg.scroll_box())
    cfg.icon_centers_x_ratio = centers
    cfg.icons_x_ratio = icons_span
    # Align team_name right boundary cleanly before icons, and score left boundary after icons
    cfg.team_name_x_ratio = [0.165, max(0.38, round(icons_span[0] - 0.015, 4))]
    cfg.score_x_ratio = [min(0.84, round(icons_span[1] + 0.045, 4)), 0.990]
    cfg.detection_notes.extend(icon_notes)
    return cfg


def render_roi_debug_overlay(frame: np.ndarray, layout: LayoutConfig) -> np.ndarray:
    """Draw a clear visual debug image showing all detected ROIs & excluded personal row."""
    vis = frame.copy()

    # 1. Outer leaderboard panel (blue)
    p = layout.panel()
    cv2.rectangle(vis, (p.x, p.y), (p.x2, p.y2), (255, 140, 0), 3)
    cv2.putText(vis, "PANEL", (p.x + 8, max(25, p.y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 140, 0), 2)

    # 2. Header bar (cyan)
    hb = layout.header_box()
    cv2.rectangle(vis, (hb.x, hb.y), (hb.x2, hb.y2), (200, 180, 0), 2)
    cv2.putText(vis, "HEADER", (hb.x + 8, hb.y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 140, 0), 2)

    # 3. Scrollable 5-row area (green)
    sb = layout.scroll_box()
    cv2.rectangle(vis, (sb.x, sb.y), (sb.x2, sb.y2), (0, 180, 0), 3)
    cv2.putText(vis, "SCROLL AREA (5 ROWS)", (sb.x + 8, sb.y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 150, 0), 2)

    # Column guides inside scroll area
    for label, xr, color in [
        ("RANK", layout.rank_x_ratio, (200, 80, 0)),
        ("TEAM NAME", layout.team_name_x_ratio, (180, 0, 180)),
        ("ICONS x8", layout.icons_x_ratio, (0, 150, 220)),
        ("SCORE", layout.score_x_ratio, (0, 120, 0)),
    ]:
        cx1 = sb.x + int(round(xr[0] * sb.w))
        cx2 = sb.x + int(round(xr[1] * sb.w))
        cv2.line(vis, (cx1, sb.y), (cx1, sb.y2), color, 1, cv2.LINE_AA)
        cv2.line(vis, (cx2, sb.y), (cx2, sb.y2), color, 1, cv2.LINE_AA)
        cv2.putText(vis, label, (cx1 + 6, sb.y2 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # 5 nominal row lines & 8 icon circles per row
    row_h = sb.h / max(1, layout.expected_visible_rows)
    radius = max(10, int(round(row_h * layout.icon_size_ratio_of_row_h * 0.5)))
    for r in range(layout.expected_visible_rows):
        ry = sb.y + int(round(r * row_h))
        if r > 0:
            cv2.line(vis, (sb.x, ry), (sb.x2, ry), (0, 200, 0), 1)
        cy = sb.y + int(round((r + 0.5) * row_h))
        for cx_ratio in layout.icon_centers_x_ratio:
            cx = sb.x + int(round(cx_ratio * sb.w))
            cv2.circle(vis, (cx, cy), radius, (0, 165, 255), 2)

    # 4. Excluded fixed bottom personal row (semi-transparent red + X cross)
    pb = layout.personal_row_box()
    overlay = vis.copy()
    cv2.rectangle(overlay, (pb.x, pb.y), (pb.x2, pb.y2), (0, 0, 220), -1)
    cv2.addWeighted(overlay, 0.22, vis, 0.78, 0, vis)
    cv2.rectangle(vis, (pb.x, pb.y), (pb.x2, pb.y2), (0, 0, 220), 3)
    cv2.line(vis, (pb.x, pb.y), (pb.x2, pb.y2), (0, 0, 220), 2)
    cv2.line(vis, (pb.x, pb.y2), (pb.x2, pb.y), (0, 0, 220), 2)
    cv2.putText(
        vis,
        "EXCLUDED: FIXED PERSONAL ROW",
        (pb.x + 16, pb.y + int(pb.h * 0.58)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 200),
        2,
    )
    return vis
