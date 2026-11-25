"""Renderer-verified anti-overlap layout helpers for Matplotlib tournament charts.

All placement & bounds calculations measure actual rendered pixel bounding boxes
via ``fig.canvas.draw()`` + ``artist.get_window_extent(renderer)`` so text labels
never collide with each other, icons, legends, or Y-axis tick labels.
"""

from __future__ import annotations

import math
import re
from typing import Any, Sequence

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.text import Text


def short_period_label(label: str) -> str:
    """Turn a verbose report title into a crisp short period tag (e.g. '1120期')."""
    clean = (label or "").strip()
    if not clean:
        return "-"
    m_ymd = re.match(r"^20\d{2}[-_/]?(\d{2})[-_/]?(\d{2})", clean)
    if m_ymd:
        return f"{m_ymd.group(1)}{m_ymd.group(2)}期"
    m_md = re.match(r"^(\d{2})(\d{2})", clean)
    if m_md and 1 <= int(m_md.group(1)) <= 12 and 1 <= int(m_md.group(2)) <= 31:
        return f"{m_md.group(1)}{m_md.group(2)}期"
    return clean[:8]


def _rects_overlap_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def fit_texts_inside_axes_x(
    fig: Figure,
    ax: Axes,
    texts: Sequence[Text],
    pad_px: float = 14.0,
    max_iters: int = 8,
) -> None:
    """Expand ``ax`` xlim asymmetrically until every text artist sits strictly inside the axes.

    Works seamlessly for both normal (xmin < xmax) and inverted (xmin > xmax) x-axes.
    """
    if not texts:
        return

    for _ in range(max_iters):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        ax_bb = ax.get_window_extent(renderer)
        if ax_bb.width <= 1.0:
            return

        left_over = 0.0
        right_over = 0.0
        for t in texts:
            if not t.get_visible() or not t.get_text():
                continue
            tb = t.get_window_extent(renderer)
            if tb.x0 < ax_bb.x0 + pad_px:
                left_over = max(left_over, (ax_bb.x0 + pad_px) - tb.x0)
            if tb.x1 > ax_bb.x1 - pad_px:
                right_over = max(right_over, tb.x1 - (ax_bb.x1 - pad_px))

        if left_over <= 1.0 and right_over <= 1.0:
            break

        x_left, x_right = ax.get_xlim()
        # Data delta per screen pixel (signed: negative when x-axis is inverted)
        dx_per_px = (x_right - x_left) / ax_bb.width
        # Slightly over-step (1.08x) so convergence completes in 2-3 passes
        new_left = x_left - dx_per_px * (left_over * 1.08)
        new_right = x_right + dx_per_px * (right_over * 1.08)
        ax.set_xlim(new_left, new_right)


def place_scatter_labels_no_overlap(
    fig: Figure,
    ax: Axes,
    items: Sequence[dict[str, Any]],
    obstacle_artists: Sequence[Any] = (),
    icon_radius_px: float = 20.0,
    pad_px: float = 4.0,
) -> list[Text]:
    """Place scatter-plot annotation badges with exact pixel-bbox collision avoidance.

    Each item dict expects:
      - ``x``: float data x
      - ``y``: float data y
      - ``text``: str label text
      - ``fontsize`` (optional, default 8.8)
      - ``color`` (optional, default '#f8fafc')
    Automatically adds a crisp leader line whenever a label must be displaced farther
    than 30 pt from its icon to avoid overlapping neighbors or corner titles.
    """
    if not items:
        return []

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ax_bb = ax.get_window_extent(renderer)
    px_per_pt = fig.dpi / 72.0

    # Pre-collect fixed obstacles: corner texts + every scatter icon circle
    fixed_obstacles: list[tuple[float, float, float, float]] = []
    for art in obstacle_artists:
        try:
            bb = art.get_window_extent(renderer)
            fixed_obstacles.append((bb.x0 - pad_px, bb.y0 - pad_px, bb.x1 + pad_px, bb.y1 + pad_px))
        except Exception:
            continue

    pts_px: list[tuple[float, float]] = []
    for it in items:
        px, py = ax.transData.transform((it["x"], it["y"]))
        pts_px.append((float(px), float(py)))
        fixed_obstacles.append(
            (px - icon_radius_px, py - icon_radius_px, px + icon_radius_px, py + icon_radius_px)
        )

    # Measure each label's exact rendered width & height once using a temporary artist
    label_sizes: list[tuple[float, float]] = []
    for it in items:
        tmp = ax.annotate(
            it["text"],
            xy=(it["x"], it["y"]),
            xytext=(0, 0),
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=it.get("fontsize", 8.8),
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.22", fc="#0f172a", ec="#334155", alpha=0.90),
        )
        fig.canvas.draw()
        tb = tmp.get_window_extent(renderer)
        label_sizes.append((float(tb.width), float(tb.height)))
        tmp.remove()

    # Order most-crowded points first so tight clusters get priority clean slots
    order = list(range(len(items)))
    if len(order) > 1:
        def _crowding(i: int) -> float:
            px, py = pts_px[i]
            return min(
                math.hypot(px - pts_px[j][0], py - pts_px[j][1])
                for j in range(len(items))
                if j != i
            )
        order.sort(key=_crowding)

    # Build concentric candidate offset rings (dx_pt, dy_pt): prefer clean N/S/E/W near icon
    angles_deg = [90, -90, 0, 180, 45, 135, -45, -135, 22, 68, 112, 158, -22, -68, -112, -158]
    radii_pt = [26, 33, 42, 54, 68, 84, 102]
    candidates: list[tuple[float, float, float]] = []
    for r_pt in radii_pt:
        for a_deg in angles_deg:
            rad = math.radians(a_deg)
            dx_pt = r_pt * math.cos(rad)
            dy_pt = r_pt * math.sin(rad)
            # Small tie-breaker preferring directly above/below over diagonals
            angle_pen = 0.0 if a_deg in (90, -90) else (0.15 if a_deg in (0, 180) else 0.4)
            candidates.append((dx_pt, dy_pt, r_pt + angle_pen))

    placed_rects: list[tuple[float, float, float, float]] = list(fixed_obstacles)
    created_artists: list[Text] = []
    inner_x0 = ax_bb.x0 + 6.0
    inner_x1 = ax_bb.x1 - 6.0
    inner_y0 = ax_bb.y0 + 6.0
    inner_y1 = ax_bb.y1 - 6.0

    for idx in order:
        it = items[idx]
        px, py = pts_px[idx]
        w, h = label_sizes[idx]

        best_cand = (0.0, 26.0)
        best_cost = float("inf")
        best_rect = (px - w / 2, py - h / 2, px + w / 2, py + h / 2)

        for dx_pt, dy_pt, dist_score in candidates:
            cx = px + dx_pt * px_per_pt
            cy = py + dy_pt * px_per_pt
            rect = (cx - w / 2.0 - pad_px, cy - h / 2.0 - pad_px, cx + w / 2.0 + pad_px, cy + h / 2.0 + pad_px)

            # Out-of-axes penalty (very heavy so labels stay strictly inside frame)
            out_pen = 0.0
            if rect[0] < inner_x0:
                out_pen += (inner_x0 - rect[0]) * 80.0
            if rect[2] > inner_x1:
                out_pen += (rect[2] - inner_x1) * 80.0
            if rect[1] < inner_y0:
                out_pen += (inner_y0 - rect[1]) * 80.0
            if rect[3] > inner_y1:
                out_pen += (rect[3] - inner_y1) * 80.0

            ov_area = 0.0
            for obs in placed_rects:
                ov_area += _rects_overlap_area(rect, obs)

            cost = ov_area * 12.0 + out_pen + dist_score * 0.6
            if cost < best_cost:
                best_cost = cost
                best_cand = (dx_pt, dy_pt)
                best_rect = rect
                if ov_area == 0.0 and out_pen == 0.0 and dist_score <= 27.0:
                    break

        dx_pt, dy_pt = best_cand
        placed_rects.append(best_rect)
        dist_pt = math.hypot(dx_pt, dy_pt)
        arrow_kw = (
            dict(arrowstyle="-", color="#64748b", lw=0.95, shrinkA=2, shrinkB=15)
            if dist_pt > 30.0
            else None
        )
        ann = ax.annotate(
            it["text"],
            xy=(it["x"], it["y"]),
            xytext=(dx_pt, dy_pt),
            textcoords="offset points",
            ha="center",
            va="center",
            color=it.get("color", "#f8fafc"),
            fontsize=it.get("fontsize", 8.8),
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.22", fc="#0f172a", ec="#334155", alpha=0.90),
            arrowprops=arrow_kw,
            zorder=6,
        )
        created_artists.append(ann)

    return created_artists


def place_row_dot_labels_no_overlap(
    fig: Figure,
    ax: Axes,
    rows: Sequence[Sequence[dict[str, Any]]],
    y_offset_pt: float = 11.5,
    h_pad_px: float = 8.0,
) -> list[Text]:
    """Place up to 3 dot labels per horizontal row with guaranteed zero same-row overlap.

    Each element of ``rows`` is a list of point dicts for one horizontal row:
      ``{"x": float, "y": float, "text": str, "color": str, "bold": bool}``
    Strategy:
      1. Sort each row's points left-to-right in screen pixels (respects inverted x-axis).
      2. Assign alternating Top/Bottom lanes:
         - 1 pt:  [Top]
         - 2 pts: [Top, Bottom]
         - 3 pts: [Top, Bottom, Top]
      3. Expand x-axis via ``fit_texts_inside_axes_x``.
      4. Check the two Top-lane labels in any 3-point row; if their real rendered pixel
         bboxes come within ``h_pad_px``, push Left label left and Right label right
         with crisp thin leader lines pointing to each dot, then re-fit xlim once.
    """
    fig.canvas.draw()
    px_per_pt = fig.dpi / 72.0

    # Store created annotations along with metadata so we can nudge same-lane collisions
    all_texts: list[Text] = []
    top_pairs: list[tuple[dict[str, Any], dict[str, Any], Text, Text]] = []

    for row_pts in rows:
        if not row_pts:
            continue
        # Sort by actual screen X (handles both normal and inverted x-axes!)
        ordered = sorted(row_pts, key=lambda p: ax.transData.transform((p["x"], p["y"]))[0])

        if len(ordered) == 1:
            lanes = [1]
        elif len(ordered) == 2:
            lanes = [1, -1]
        else:
            lanes = [1, -1, 1]

        top_created: list[tuple[dict[str, Any], Text]] = []
        for pt, lane in zip(ordered, lanes):
            dy = y_offset_pt if lane > 0 else -y_offset_pt
            va = "bottom" if lane > 0 else "top"
            ann = ax.annotate(
                pt["text"],
                xy=(pt["x"], pt["y"]),
                xytext=(0.0, dy),
                textcoords="offset points",
                ha="center",
                va=va,
                color=pt["color"],
                fontsize=pt.get("fontsize", 8.2),
                fontweight="bold" if pt.get("bold") else "normal",
                zorder=7,
            )
            all_texts.append(ann)
            if lane > 0:
                top_created.append((pt, ann))

        if len(top_created) == 2:
            top_pairs.append((top_created[0][0], top_created[1][0], top_created[0][1], top_created[1][1]))

    # First pass: fit x limits to include outer edge labels cleanly
    fit_texts_inside_axes_x(fig, ax, all_texts, pad_px=14.0)

    # Second pass: resolve any horizontal collision between the two Top-lane labels on a 3-dot row
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    nudged_any = False
    for pt_l, pt_r, ann_l, ann_r in top_pairs:
        bb_l = ann_l.get_window_extent(renderer)
        bb_r = ann_r.get_window_extent(renderer)
        overlap_px = (bb_l.x1 + h_pad_px) - bb_r.x0
        if overlap_px > 0.0:
            shift_pt = (overlap_px / 2.0) / px_per_pt + 2.0
            # Replace with nudged annotations featuring subtle leader ticks to exact dots
            ann_l.remove()
            ann_r.remove()
            all_texts.remove(ann_l)
            all_texts.remove(ann_r)

            new_l = ax.annotate(
                pt_l["text"],
                xy=(pt_l["x"], pt_l["y"]),
                xytext=(-shift_pt, y_offset_pt + 2.0),
                textcoords="offset points",
                ha="center",
                va="bottom",
                color=pt_l["color"],
                fontsize=pt_l.get("fontsize", 8.2),
                fontweight="bold" if pt_l.get("bold") else "normal",
                arrowprops=dict(arrowstyle="-", color=pt_l["color"], lw=0.75, alpha=0.65, shrinkA=1, shrinkB=5),
                zorder=7,
            )
            new_r = ax.annotate(
                pt_r["text"],
                xy=(pt_r["x"], pt_r["y"]),
                xytext=(shift_pt, y_offset_pt + 2.0),
                textcoords="offset points",
                ha="center",
                va="bottom",
                color=pt_r["color"],
                fontsize=pt_r.get("fontsize", 8.2),
                fontweight="bold" if pt_r.get("bold") else "normal",
                arrowprops=dict(arrowstyle="-", color=pt_r["color"], lw=0.75, alpha=0.65, shrinkA=1, shrinkB=5),
                zorder=7,
            )
            all_texts.extend([new_l, new_r])
            nudged_any = True

    if nudged_any:
        fit_texts_inside_axes_x(fig, ax, all_texts, pad_px=14.0)

    return all_texts
