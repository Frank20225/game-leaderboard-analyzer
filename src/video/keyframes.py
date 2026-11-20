"""Adaptive keyframe selection using motion energy, vertical scroll tracking,
Laplacian sharpness scoring, and temporal median cursor suppression.

Does NOT rely on naive fixed-interval screenshots.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.layout.detector import LayoutConfig
from src.video.loader import VideoMetadata, load_video_metadata, read_frame_at


@dataclass
class TimelineSample:
    """Per-sample diagnostic measurements on the scrollable leaderboard area."""

    frame_idx: int
    timestamp_sec: float
    motion_mad: float
    scroll_dy_px: float
    cumulative_scroll_px: float
    sharpness: float
    is_stable: bool


@dataclass
class KeyframeInfo:
    """Metadata of a selected representative keyframe."""

    keyframe_id: int
    frame_idx: int
    timestamp_sec: float
    sharpness: float
    motion_mad: float
    cumulative_scroll_px: float
    reason: str  # "stable_segment" | "scroll_step" | "tail_frame"
    composite_frames_used: int
    image_path: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Phase1Result:
    """Complete verifiable output of Phase 1 (Video Analysis & ROI Detection)."""

    metadata: VideoMetadata
    layout: LayoutConfig
    keyframes: list[KeyframeInfo]
    total_samples: int
    stable_segments_count: int
    roi_debug_path: str
    timeline_plot_path: str
    summary_json_path: str

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "layout": self.layout.to_dict(),
            "total_samples": self.total_samples,
            "stable_segments_count": self.stable_segments_count,
            "keyframe_count": len(self.keyframes),
            "keyframes": [k.to_dict() for k in self.keyframes],
            "roi_debug_path": self.roi_debug_path,
            "timeline_plot_path": self.timeline_plot_path,
            "summary_json_path": self.summary_json_path,
        }


def _compute_sharpness(gray_crop: np.ndarray) -> float:
    """Laplacian variance: higher means crisper edges (less motion blur)."""
    return float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())


def _estimate_vertical_scroll(prev_gray: np.ndarray, curr_gray: np.ndarray, hann: np.ndarray) -> float:
    """Estimate vertical pixel shift dy via phase correlation.

    Positive dy indicates the leaderboard content moved upward (scrolling down to higher ranks).
    """
    (dx, dy), response = cv2.phaseCorrelate(
        prev_gray.astype(np.float32), curr_gray.astype(np.float32), hann
    )
    # Reject unreliable correlation peaks (e.g. huge page jumps or cursor-only jitter)
    if response < 0.08 or abs(dx) > 25.0:
        return 0.0
    return float(-dy)


def _build_clean_frame_from_segment(
    cap: cv2.VideoCapture,
    segment_indices: list[int],
    scroll_box_crop_fn,
) -> tuple[np.ndarray, int, float, int]:
    """Select cleanest frame from a stable segment; suppress moving cursor via temporal median.

    Returns (best_frame, representative_frame_idx, best_sharpness, frames_used).
    """
    if len(segment_indices) == 1:
        f = read_frame_at(cap, segment_indices[0])
        assert f is not None
        sharp = _compute_sharpness(cv2.cvtColor(scroll_box_crop_fn(f), cv2.COLOR_BGR2GRAY))
        return f, segment_indices[0], sharp, 1

    # Pick up to 5 evenly spaced frames inside this stable segment
    pick_pos = np.linspace(0, len(segment_indices) - 1, num=min(5, len(segment_indices)), dtype=int)
    chosen_indices = sorted({segment_indices[int(p)] for p in pick_pos})

    loaded: list[tuple[int, np.ndarray, float]] = []
    for idx in chosen_indices:
        f = read_frame_at(cap, idx)
        if f is not None:
            sharp = _compute_sharpness(cv2.cvtColor(scroll_box_crop_fn(f), cv2.COLOR_BGR2GRAY))
            loaded.append((idx, f, sharp))

    if not loaded:
        raise RuntimeError("無法讀取穩定段落內的任何影格")

    best_idx, best_frame, best_sharp = max(loaded, key=lambda x: x[2])

    # If we have >=3 static frames, check if median composite stays crisp (erases moving mouse cursor!)
    if len(loaded) >= 3:
        # Verify the frames are truly aligned (very small pairwise diff in scroll area)
        ref_crop = scroll_box_crop_fn(best_frame).astype(np.float32)
        aligned_frames = [
            f for _, f, _ in loaded if float(np.abs(scroll_box_crop_fn(f).astype(np.float32) - ref_crop).mean()) < 2.2
        ]
        if len(aligned_frames) >= 3:
            median_frame = np.median(np.stack(aligned_frames, axis=0), axis=0).astype(np.uint8)
            med_sharp = _compute_sharpness(cv2.cvtColor(scroll_box_crop_fn(median_frame), cv2.COLOR_BGR2GRAY))
            # Use median composite if it preserves >= 92% of the single frame's sharpness
            if med_sharp >= best_sharp * 0.92:
                return median_frame, best_idx, med_sharp, len(aligned_frames)

    return best_frame, best_idx, best_sharp, 1


def _plot_scroll_timeline(
    samples: list[TimelineSample],
    keyframes: list[KeyframeInfo],
    motion_threshold: float,
    output_path: Path,
) -> None:
    """Render a visual timeline plot showing motion energy, scroll progression & selected frames."""
    times = [s.timestamp_sec for s in samples]
    mads = [s.motion_mad for s in samples]
    cum_scroll = [s.cumulative_scroll_px for s in samples]
    sharps = [s.sharpness for s in samples]

    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    fig.suptitle("Phase 1: Video Scroll & Keyframe Analysis Timeline", fontsize=13, fontweight="bold")

    # 1. Motion Energy (MAD)
    axes[0].plot(times, mads, color="#2563eb", linewidth=1.4, label="Motion Energy (MAD)")
    axes[0].axhline(motion_threshold, color="#f59e0b", linestyle="--", linewidth=1.0, label=f"Stable Threshold ({motion_threshold:.1f})")
    axes[0].set_ylabel("MAD (px intensity)")
    axes[0].legend(loc="upper right", fontsize=9)
    axes[0].grid(True, alpha=0.25)

    # 2. Cumulative Scroll Distance
    axes[1].plot(times, cum_scroll, color="#059669", linewidth=1.5, label="Cumulative Vertical Scroll (px)")
    axes[1].set_ylabel("Scroll (px)")
    axes[1].legend(loc="upper left", fontsize=9)
    axes[1].grid(True, alpha=0.25)

    # 3. Sharpness (Laplacian Variance)
    axes[2].plot(times, sharps, color="#7c3aed", linewidth=1.3, label="Sharpness (Laplacian Var)")
    axes[2].set_ylabel("Sharpness")
    axes[2].set_xlabel("Time (seconds)")
    axes[2].legend(loc="lower right", fontsize=9)
    axes[2].grid(True, alpha=0.25)

    # Overlay selected keyframes across all 3 subplots
    for kf in keyframes:
        color = "#dc2626" if kf.reason == "stable_segment" else "#ea580c"
        for ax in axes:
            ax.axvline(kf.timestamp_sec, color=color, linestyle=":", linewidth=1.3, alpha=0.85)
        axes[0].annotate(
            f"KF{kf.keyframe_id}",
            xy=(kf.timestamp_sec, max(mads) * 0.92 if mads else 1.0),
            fontsize=8,
            color=color,
            rotation=90,
            va="top",
            ha="right",
        )

    fig.tight_layout()
    fig.savefig(str(output_path), dpi=150)
    plt.close(fig)


def extract_representative_keyframes(
    video_path: str | Path,
    layout: LayoutConfig,
    output_dir: str | Path,
    sample_fps: float = 15.0,
    stable_mad_threshold: float = 1.8,
    min_visual_diff_mad: float = 3.5,
    scroll_step_row_fraction: float = 3.0,
) -> tuple[list[KeyframeInfo], list[TimelineSample], int, Path]:
    """Analyze scroll motion and extract crisp, non-redundant keyframes.

    Strategy:
    1. Sample the scrollable ROI at ~sample_fps to compute Motion Energy (MAD),
       vertical scroll shift (phase correlation), and Laplacian sharpness.
    2. Identify stable pause segments -> extract cleanest (or median cursor-free) frame.
    3. During continuous scrolling without pauses -> trigger keyframe capture every
       `scroll_step_row_fraction` of a row height (ensuring generous overlap & zero missed teams).
    4. Deduplicate consecutive keyframes if visual difference in scroll ROI is negligible.
    """
    meta = load_video_metadata(video_path)
    out_dir = Path(output_dir)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    sb = layout.scroll_box()
    row_h = layout.estimated_row_height
    scroll_trigger_px = max(30.0, row_h * scroll_step_row_fraction)
    stride = max(1, int(round(meta.fps / max(1.0, sample_fps))))

    cap = cv2.VideoCapture(str(meta.path))
    if not cap.isOpened():
        raise ValueError(f"無法開啟影片進行關鍵影格分析: {meta.path}")

    samples: list[TimelineSample] = []
    prev_gray: np.ndarray | None = None
    hann: np.ndarray | None = None
    cumulative_scroll = 0.0

    # Pass 1: Sequential scan (much faster and more accurate than random seeking on H.264 MP4)
    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if frame_idx % stride == 0 or frame_idx == meta.frame_count - 1:
                crop = sb.crop(frame)
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                if hann is None:
                    hann = cv2.createHanningWindow((gray.shape[1], gray.shape[0]), cv2.CV_32F)

                if prev_gray is None:
                    mad = 0.0
                    dy = 0.0
                else:
                    mad = float(np.abs(gray.astype(np.float32) - prev_gray.astype(np.float32)).mean())
                    dy = _estimate_vertical_scroll(prev_gray, gray, hann) if mad >= 0.35 else 0.0
                    cumulative_scroll += dy

                sharp = _compute_sharpness(gray)
                samples.append(
                    TimelineSample(
                        frame_idx=frame_idx,
                        timestamp_sec=round(frame_idx / meta.fps, 3),
                        motion_mad=round(mad, 3),
                        scroll_dy_px=round(dy, 2),
                        cumulative_scroll_px=round(cumulative_scroll, 2),
                        sharpness=round(sharp, 2),
                        is_stable=(mad < stable_mad_threshold),
                    )
                )
                prev_gray = gray
            frame_idx += 1

        # Pass 2: Segment timeline into stable pauses and continuous-scroll candidates
        selected_candidates: list[tuple[list[int], str, TimelineSample]] = []
        stable_segments_count = 0

        i = 0
        n_samples = len(samples)
        last_captured_scroll = 0.0
        while i < n_samples:
            if samples[i].is_stable:
                j = i
                while j < n_samples and samples[j].is_stable:
                    j += 1
                seg_samples = samples[i:j]
                # Require at least 2 consecutive stable samples (or start/end of video)
                if len(seg_samples) >= 2 or i == 0 or j == n_samples:
                    stable_segments_count += 1
                    seg_indices = [s.frame_idx for s in seg_samples]
                    mid_sample = seg_samples[len(seg_samples) // 2]
                    selected_candidates.append((seg_indices, "stable_segment", mid_sample))
                    last_captured_scroll = seg_samples[-1].cumulative_scroll_px
                i = j
            else:
                # Continuous scrolling segment: capture whenever cumulative scroll advances enough
                j = i
                window: list[TimelineSample] = []
                while j < n_samples and not samples[j].is_stable:
                    window.append(samples[j])
                    if abs(samples[j].cumulative_scroll_px - last_captured_scroll) >= scroll_trigger_px:
                        # Pick sharpest frame in this scroll window
                        best_s = max(window, key=lambda s: s.sharpness)
                        selected_candidates.append(([best_s.frame_idx], "scroll_step", best_s))
                        last_captured_scroll = samples[j].cumulative_scroll_px
                        window = []
                    j += 1
                i = j

        # Ensure the very last sample is considered if significant scroll happened after last capture
        if samples and abs(samples[-1].cumulative_scroll_px - last_captured_scroll) >= row_h * 0.35:
            selected_candidates.append(([samples[-1].frame_idx], "tail_frame", samples[-1]))

        # Pass 3: Materialize clean frames and filter out visually identical consecutive frames
        keyframes: list[KeyframeInfo] = []
        prev_saved_crop: np.ndarray | None = None

        for seg_indices, reason, ref_sample in selected_candidates:
            clean_frame, rep_idx, sharp, used_count = _build_clean_frame_from_segment(
                cap, seg_indices, sb.crop
            )
            curr_crop = sb.crop(clean_frame).astype(np.float32)

            if prev_saved_crop is not None:
                diff_mad = float(np.abs(curr_crop - prev_saved_crop).mean())
                if diff_mad < min_visual_diff_mad:
                    continue  # Visually redundant pause (e.g., cursor moved without scrolling)

            kf_id = len(keyframes)
            img_path = frames_dir / f"kf_{kf_id:03d}_f{rep_idx:05d}.png"
            cv2.imwrite(str(img_path), clean_frame)

            keyframes.append(
                KeyframeInfo(
                    keyframe_id=kf_id,
                    frame_idx=rep_idx,
                    timestamp_sec=round(rep_idx / meta.fps, 3),
                    sharpness=round(sharp, 2),
                    motion_mad=ref_sample.motion_mad,
                    cumulative_scroll_px=ref_sample.cumulative_scroll_px,
                    reason=reason,
                    composite_frames_used=used_count,
                    image_path=str(img_path),
                )
            )
            prev_saved_crop = curr_crop
    finally:
        cap.release()

    timeline_plot_path = out_dir / "debug_scroll_timeline.png"
    _plot_scroll_timeline(samples, keyframes, stable_mad_threshold, timeline_plot_path)
    return keyframes, samples, stable_segments_count, timeline_plot_path
