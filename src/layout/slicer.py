"""Row and column slicing inside the detected scrollable leaderboard area.

Handles both cleanly aligned 5-row frames and mid-scroll frames by detecting
actual row vertical centers using the 8 colorful occupation icons as anchors,
so partially clipped top/bottom rows are never misread as complete teams.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from src.layout.detector import Box, LayoutConfig


@dataclass
class RowSlice:
    """Cropped image components of a single visible leaderboard row."""

    row_index_in_frame: int
    y_top_in_scroll: int
    y_bottom_in_scroll: int
    row_img: np.ndarray
    rank_img: np.ndarray
    name_img: np.ndarray
    score_img: np.ndarray
    icon_imgs: list[np.ndarray]  # 8 cropped square icon images


def _detect_row_centers_y(scroll_img: np.ndarray, layout: LayoutConfig) -> list[int]:
    """Locate vertical centers of complete visible rows inside scroll_img.

    Uses the horizontal strip spanning the 8 occupation icons: each complete row
    produces a strong vertical band of high-saturation circular icons, separated
    by clean white horizontal gaps between rows.
    """
    sh, sw = scroll_img.shape[:2]
    nom_row_h = sh / max(1, layout.expected_visible_rows)

    ix1 = int(round(layout.icons_x_ratio[0] * sw))
    ix2 = int(round(layout.icons_x_ratio[1] * sw))
    icon_strip = scroll_img[:, ix1:ix2]
    hsv = cv2.cvtColor(icon_strip, cv2.COLOR_BGR2HSV)
    # Fraction of saturated pixels on each horizontal line inside the 8-icon zone
    sat_profile = (hsv[:, :, 1] > 60).mean(axis=1).astype(np.float32)
    # Smooth with a 9px window
    smooth = np.convolve(sat_profile, np.ones(9) / 9.0, mode="same")

    # Find contiguous bands where icons exist (sat fraction > 0.08)
    active = smooth > 0.08
    padded = np.concatenate([[False], active, [False]])
    diff = np.diff(padded.astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]

    min_icon_band_h = max(18, int(nom_row_h * 0.25))
    edge_margin = int(nom_row_h * 0.28)  # Reject clipped rows too close to top/bottom edge

    centers: list[int] = []
    for s, e in zip(starts, ends):
        band_h = int(e - s)
        cy = int(round((s + e) / 2.0))
        if band_h >= min_icon_band_h and edge_margin <= cy <= (sh - edge_margin):
            # Avoid double-counting if two centers are implausibly close
            if not centers or (cy - centers[-1]) >= nom_row_h * 0.65:
                centers.append(cy)

    # Fallback: if aligned clean frame didn't trigger enough bands, use uniform 5-row centers
    if not centers:
        centers = [int(round((r + 0.5) * nom_row_h)) for r in range(layout.expected_visible_rows)]
    return centers


def slice_scrollable_rows(frame: np.ndarray, layout: LayoutConfig) -> list[RowSlice]:
    """Extract all complete visible rows and their sub-fields from a frame."""
    sb = layout.scroll_box()
    scroll_img = sb.crop(frame)
    sh, sw = scroll_img.shape[:2]
    nom_row_h = sh / max(1, layout.expected_visible_rows)
    half_h = int(round(nom_row_h * 0.46))

    centers_y = _detect_row_centers_y(scroll_img, layout)
    icon_half = max(12, int(round(nom_row_h * layout.icon_size_ratio_of_row_h * 0.52)))

    rank_x1, rank_x2 = int(round(layout.rank_x_ratio[0] * sw)), int(round(layout.rank_x_ratio[1] * sw))
    name_x1, name_x2 = int(round(layout.team_name_x_ratio[0] * sw)), int(round(layout.team_name_x_ratio[1] * sw))
    score_x1, score_x2 = int(round(layout.score_x_ratio[0] * sw)), int(round(layout.score_x_ratio[1] * sw))

    slices: list[RowSlice] = []
    for idx, cy in enumerate(centers_y):
        y1 = max(0, cy - half_h)
        y2 = min(sh, cy + half_h)
        if (y2 - y1) < int(nom_row_h * 0.72):
            continue  # Skip clipped partial rows

        row_img = scroll_img[y1:y2, :].copy()
        rank_img = scroll_img[y1:y2, rank_x1:rank_x2].copy()
        name_img = scroll_img[y1:y2, name_x1:name_x2].copy()
        score_img = scroll_img[y1:y2, score_x1:score_x2].copy()

        icon_imgs: list[np.ndarray] = []
        for cx_ratio in layout.icon_centers_x_ratio:
            cx = int(round(cx_ratio * sw))
            ix1 = max(0, cx - icon_half)
            ix2 = min(sw, cx + icon_half)
            iy1 = max(0, cy - icon_half)
            iy2 = min(sh, cy + icon_half)
            icon_imgs.append(scroll_img[iy1:iy2, ix1:ix2].copy())

        slices.append(
            RowSlice(
                row_index_in_frame=idx,
                y_top_in_scroll=y1,
                y_bottom_in_scroll=y2,
                row_img=row_img,
                rank_img=rank_img,
                name_img=name_img,
                score_img=score_img,
                icon_imgs=icon_imgs,
            )
        )
    return slices
