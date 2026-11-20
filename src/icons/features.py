"""Icon normalization, empty-slot detection, and multi-cue visual feature extraction.

Combines circular masking, centroid alignment, ring/core HSV histograms, Lab spatial
color maps, and normalized inner emblem structure so same-color classes with different
white emblems are cleanly separated without training a neural network.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

NORM_SIZE = 40
OUTER_RADIUS = 17
INNER_RADIUS = 11
EMBLEM_RADIUS = 14


@dataclass(frozen=True)
class IconAnalysis:
    """Normalized icon image, empty-slot flag, and L2-normalized feature vector."""

    is_empty: bool
    normalized_bgr: np.ndarray  # 40x40 centered BGR image
    feature_vec: np.ndarray     # 1D float32 unit vector
    sat_mean: float
    edge_energy: float


def _build_circle_mask(size: int, radius: int, inner_exclude: int = 0) -> np.ndarray:
    yy, xx = np.ogrid[:size, :size]
    c = (size - 1) / 2.0
    dist2 = (xx - c) ** 2 + (yy - c) ** 2
    mask = dist2 <= radius ** 2
    if inner_exclude > 0:
        mask &= dist2 > inner_exclude ** 2
    return mask


_MASK_FULL = _build_circle_mask(NORM_SIZE, OUTER_RADIUS)
_MASK_RING = _build_circle_mask(NORM_SIZE, OUTER_RADIUS, inner_exclude=INNER_RADIUS)
_MASK_CORE = _build_circle_mask(NORM_SIZE, INNER_RADIUS)
_MASK_EMBLEM = _build_circle_mask(NORM_SIZE, EMBLEM_RADIUS)


def center_and_normalize_icon(icon_img: np.ndarray, size: int = NORM_SIZE) -> np.ndarray:
    """Recenter the circular badge using non-white pixel centroid and resize to size x size."""
    h, w = icon_img.shape[:2]
    hsv = cv2.cvtColor(icon_img, cv2.COLOR_BGR2HSV)
    # Foreground badge pixels: either colorful (S > 32) or darker than the white cell background
    fg = ((hsv[:, :, 1] > 32) | (hsv[:, :, 2] < 218)).astype(np.uint8)
    # Restrict to inner 88% to avoid stray row border lines
    m = max(1, int(min(h, w) * 0.06))
    fg[:m, :] = 0
    fg[h - m :, :] = 0
    fg[:, :m] = 0
    fg[:, w - m :] = 0

    ys, xs = np.where(fg > 0)
    if len(xs) >= 40:
        cx = float(xs.mean())
        cy = float(ys.mean())
        # Clamp shift so a noisy edge cannot pull the icon far off-center
        dx = float(np.clip(cx - w / 2.0, -5.0, 5.0))
        dy = float(np.clip(cy - h / 2.0, -5.0, 5.0))
        # Estimate radius from bounding box of foreground pixels
        span = max(float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1))
        half = max(12.0, min(min(h, w) / 2.0, span * 0.54))
        x1 = int(round(w / 2.0 + dx - half))
        y1 = int(round(h / 2.0 + dy - half))
        x2 = int(round(w / 2.0 + dx + half))
        y2 = int(round(h / 2.0 + dy + half))
        # Pad if crop extends slightly outside source bounds
        pad_l, pad_t = max(0, -x1), max(0, -y1)
        pad_r, pad_b = max(0, x2 - w), max(0, y2 - h)
        if any((pad_l, pad_t, pad_r, pad_b)):
            src = cv2.copyMakeBorder(
                icon_img, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE
            )
            crop = src[y1 + pad_t : y2 + pad_t, x1 + pad_l : x2 + pad_l]
        else:
            crop = icon_img[y1:y2, x1:x2]
    else:
        crop = icon_img

    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)


def analyze_icon(icon_img: np.ndarray) -> IconAnalysis:
    """Detect empty slot and compute multi-cue L2-normalized feature vector."""
    norm_bgr = center_and_normalize_icon(icon_img, size=NORM_SIZE)
    hsv = cv2.cvtColor(norm_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(norm_bgr, cv2.COLOR_BGR2GRAY)

    # Empty-slot check: real occupation icons have vibrant color ring & crisp inner emblem.
    # Empty circular placeholders (e.g. 7-player teams) are flat pale beige/grey.
    sat_in = hsv[:, :, 1][_MASK_FULL]
    sat_mean = float(sat_in.mean())
    vivid_frac = float((sat_in > 55).mean())

    lap = cv2.Laplacian(gray, cv2.CV_64F)
    edge_energy = float(lap[_MASK_EMBLEM].var())

    is_empty = (sat_mean < 28.0 and vivid_frac < 0.08) or (vivid_frac < 0.04 and edge_energy < 160.0)
    if is_empty:
        return IconAnalysis(
            is_empty=True,
            normalized_bgr=norm_bgr,
            feature_vec=np.zeros(1, dtype=np.float32),
            sat_mean=round(sat_mean, 2),
            edge_energy=round(edge_energy, 2),
        )

    # Cue 1: Ring & Core HSV Histograms (captures main class color family & white emblem area)
    def _hsv_hist(mask_bool: np.ndarray) -> np.ndarray:
        mask_u8 = (mask_bool.astype(np.uint8)) * 255
        h_hist = cv2.calcHist([hsv], [0], mask_u8, [18], [0, 180]).flatten()
        s_hist = cv2.calcHist([hsv], [1], mask_u8, [6], [0, 256]).flatten()
        v_hist = cv2.calcHist([hsv], [2], mask_u8, [6], [0, 256]).flatten()
        vec = np.concatenate([h_hist * 1.4, s_hist * 0.7, v_hist * 0.6]).astype(np.float32)
        return vec / (float(np.linalg.norm(vec)) + 1e-6)

    ring_hist = _hsv_hist(_MASK_RING)
    core_hist = _hsv_hist(_MASK_CORE)

    # Cue 2: Downsampled Lab (a, b) spatial color map (16x16) inside circular mask
    lab16 = cv2.cvtColor(cv2.resize(norm_bgr, (16, 16), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).astype(
        np.float32
    )
    mask16 = _build_circle_mask(16, 7)
    ab_vec = np.concatenate([(lab16[:, :, 1][mask16] - 128.0), (lab16[:, :, 2][mask16] - 128.0)])
    ab_vec = ab_vec / (float(np.linalg.norm(ab_vec)) + 1e-6)

    # Cue 3: Normalized Inner Grayscale Emblem Patch (20x20) + Gradient Magnitude (emblem shape!)
    gray20 = cv2.resize(gray, (20, 20), interpolation=cv2.INTER_AREA).astype(np.float32)
    mask20 = _build_circle_mask(20, 7)
    g_vals = gray20[mask20]
    g_vals = g_vals - float(g_vals.mean())
    g_vals = g_vals / (float(np.linalg.norm(g_vals)) + 1e-6)

    gx = cv2.Sobel(gray20, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray20, cv2.CV_32F, 0, 1, ksize=3)
    gmag = np.sqrt(gx * gx + gy * gy)[mask20]
    gmag = gmag / (float(np.linalg.norm(gmag)) + 1e-6)

    # Weighted fusion: strong emblem shape + crisp color separation
    combined = np.concatenate(
        [
            ring_hist * 1.0,
            core_hist * 0.6,
            ab_vec * 1.1,
            g_vals * 1.35,
            gmag * 0.95,
        ]
    ).astype(np.float32)
    combined /= float(np.linalg.norm(combined)) + 1e-8

    return IconAnalysis(
        is_empty=False,
        normalized_bgr=norm_bgr,
        feature_vec=combined,
        sat_mean=round(sat_mean, 2),
        edge_energy=round(edge_energy, 2),
    )


def compute_ncc_similarity(norm_a: np.ndarray, norm_b: np.ndarray) -> float:
    """Direct masked Normalized Cross-Correlation on 40x40 normalized BGR icons."""
    va = norm_a[_MASK_FULL].astype(np.float32).flatten()
    vb = norm_b[_MASK_FULL].astype(np.float32).flatten()
    va -= va.mean()
    vb -= vb.mean()
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-8
    return float(np.dot(va, vb) / denom)
