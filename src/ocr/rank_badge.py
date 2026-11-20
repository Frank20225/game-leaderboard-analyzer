"""Special rank badge classifier for Top 1 / Top 2 / Top 3 graphical crests.

Ranks 1-3 in the leaderboard use ornate Gold, Silver-Blue, and Bronze crests
instead of plain text digits, whereas Ranks 4+ are plain dark-brown numerals.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class BadgeResult:
    """Result of checking whether a rank cell contains a Top 1-3 medal badge."""

    is_badge: bool
    rank: int | None
    confidence: float
    sat_ratio: float
    details: str


def classify_rank_badge(rank_img: np.ndarray) -> BadgeResult:
    """Detect whether rank_img holds a Top 1/2/3 badge and identify which one.

    Uses HSV color distribution + horizontal crest span on the inner crop:
    - Plain digits (Rank 4+): low saturation dark-brown ink -> sat_ratio < 0.03
    - Rank 2 (Silver/Blue wreath): distinct blue/periwinkle hue (H in [92, 138])
    - Rank 1 (Gold winged crest): bright yellow-gold hue (H in [19, 42]) & wider wings
    - Rank 3 (Bronze shield): deeper orange-bronze hue (H in [4, 21]) & narrower span
    """
    h, w = rank_img.shape[:2]
    # Focus on central 80% vertically and 85% horizontally to avoid border lines
    cy1, cy2 = int(h * 0.08), int(h * 0.92)
    cx1, cx2 = int(w * 0.08), int(w * 0.92)
    roi = rank_img[cy1:cy2, cx1:cx2]
    if roi.size == 0:
        return BadgeResult(False, None, 0.0, 0.0, "empty_roi")

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    H = hsv[:, :, 0]
    S = hsv[:, :, 1]
    V = hsv[:, :, 2]

    # Colorful badge pixels (exclude white background and low-sat dark text)
    colored = (S > 45) & (V > 95)
    sat_ratio = float(colored.mean())

    # Plain dark-brown text digits have very low saturated pixel coverage
    if sat_ratio < 0.035:
        return BadgeResult(False, None, 0.0, round(sat_ratio, 4), "plain_text_digit")

    # Inspect Hue distribution among colored pixels
    h_vals = H[colored]
    v_vals = V[colored]
    n_col = max(1, len(h_vals))

    blue_frac = float(((h_vals >= 92) & (h_vals <= 140)).sum() / n_col)
    gold_frac = float(((h_vals >= 19) & (h_vals <= 42)).sum() / n_col)
    bronze_frac = float(((h_vals >= 4) & (h_vals <= 18)).sum() / n_col)
    mean_v = float(v_vals.mean())

    # Horizontal span of colored pixels (Rank 1 winged crest is noticeably wider than Rank 3)
    col_xs = np.where(colored.any(axis=0))[0]
    span_ratio = float((col_xs[-1] - col_xs[0] + 1) / max(1, roi.shape[1])) if len(col_xs) else 0.0

    if blue_frac >= 0.30:
        conf = min(0.99, 0.75 + blue_frac * 0.30)
        return BadgeResult(
            True,
            2,
            round(conf, 3),
            round(sat_ratio, 4),
            f"silver_blue_badge(blue={blue_frac:.2f},span={span_ratio:.2f})",
        )

    # Distinguish Gold (Rank 1) vs Bronze (Rank 3)
    # Gold crest has higher yellow hue fraction (H>=19), brighter V, and wider wings
    gold_score = gold_frac * 1.15 + (0.25 if mean_v > 200 else 0.0) + (0.25 if span_ratio > 0.42 else 0.0)
    bronze_score = bronze_frac * 1.15 + (0.25 if mean_v <= 200 else 0.0) + (0.25 if span_ratio <= 0.42 else 0.0)

    if gold_score >= bronze_score:
        conf = min(0.99, 0.72 + max(0.0, gold_score - bronze_score) * 0.25)
        return BadgeResult(
            True,
            1,
            round(conf, 3),
            round(sat_ratio, 4),
            f"gold_badge(gold={gold_frac:.2f},bronze={bronze_frac:.2f},V={mean_v:.0f},span={span_ratio:.2f})",
        )

    conf = min(0.99, 0.72 + max(0.0, bronze_score - gold_score) * 0.25)
    return BadgeResult(
        True,
        3,
        round(conf, 3),
        round(sat_ratio, 4),
        f"bronze_badge(gold={gold_frac:.2f},bronze={bronze_frac:.2f},V={mean_v:.0f},span={span_ratio:.2f})",
    )
