"""Standalone Phase 1 runner: video analysis, ROI detection & keyframe extraction."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import cv2

from src.config import OUTPUTS_DIR, ensure_base_dirs
from src.layout.detector import LayoutConfig, detect_leaderboard_layout, render_roi_debug_overlay
from src.video.keyframes import Phase1Result, extract_representative_keyframes
from src.video.loader import load_video_metadata, sample_frames_uniform


def run_phase1(
    video_path: str | Path,
    run_dir: str | Path | None = None,
    layout_override: LayoutConfig | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> Phase1Result:
    """Execute Phase 1 end-to-end and write all verifiable debug artifacts."""
    ensure_base_dirs()
    if progress_cb:
        progress_cb(3.0, "讀取影片中繼資料與抽樣影格...")
    meta = load_video_metadata(video_path)

    if run_dir is None:
        stem = Path(meta.filename).stem.replace(" ", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_path = OUTPUTS_DIR / f"{stem}_{ts}"
    else:
        run_path = Path(run_dir)

    phase1_dir = run_path / "phase1_frames"
    phase1_dir.mkdir(parents=True, exist_ok=True)

    sampled_pairs = sample_frames_uniform(meta.path, num_samples=16)
    sampled_frames = [f for _, f in sampled_pairs]

    if progress_cb:
        progress_cb(12.0, "自動偵測排行榜外框、8 職業位置與個人列排除...")
    layout = layout_override if layout_override is not None else detect_leaderboard_layout(sampled_frames)
    layout.save(phase1_dir / "layout.json")

    roi_overlay = render_roi_debug_overlay(sampled_frames[0], layout)
    roi_debug_path = phase1_dir / "debug_roi_overlay.png"
    cv2.imwrite(str(roi_debug_path), roi_overlay)

    keyframes, samples, stable_count, timeline_plot_path = extract_representative_keyframes(
        video_path=meta.path,
        layout=layout,
        output_dir=phase1_dir,
        progress_cb=progress_cb,
    )

    if progress_cb:
        progress_cb(96.0, "儲存 Phase 1 分析摘要與時間軸圖...")

    summary_json_path = phase1_dir / "phase1_summary.json"
    result = Phase1Result(
        metadata=meta,
        layout=layout,
        keyframes=keyframes,
        total_samples=len(samples),
        stable_segments_count=stable_count,
        roi_debug_path=str(roi_debug_path),
        timeline_plot_path=str(timeline_plot_path),
        summary_json_path=str(summary_json_path),
    )
    summary_json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.pipeline_phase1 <video_path> [output_run_dir]")
        sys.exit(1)
    video = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) >= 3 else None
    res = run_phase1(video, out)
    print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
