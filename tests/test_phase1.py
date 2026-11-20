"""Unit and sample-video integration tests for Stage 1 (Video Analysis & ROI Detection)."""

from pathlib import Path

import cv2
import pytest

from src.layout.slicer import slice_scrollable_rows
from src.pipeline_phase1 import run_phase1
from src.video.loader import load_video_metadata

SAMPLE_VIDEO = Path(r"C:\Users\f1991\Videos\2026-11-21 03-18-43.mp4")


@pytest.mark.skipif(not SAMPLE_VIDEO.is_file(), reason="Sample video not present")
def test_phase1_on_sample_video(tmp_path: Path) -> None:
    meta = load_video_metadata(SAMPLE_VIDEO)
    assert meta.width == 1920
    assert meta.height == 1080
    assert meta.fps > 0
    assert meta.frame_count > 100

    res = run_phase1(SAMPLE_VIDEO, run_dir=tmp_path / "run1")

    # Verify ROI overlay & timeline plot created
    assert Path(res.roi_debug_path).is_file()
    assert Path(res.timeline_plot_path).is_file()
    assert Path(res.summary_json_path).is_file()

    # Verify 8 icon centers detected cleanly in ascending order
    assert len(res.layout.icon_centers_x_ratio) == 8
    assert res.layout.icon_centers_x_ratio == sorted(res.layout.icon_centers_x_ratio)

    # Verify personal row sits strictly below scrollable area
    sb = res.layout.scroll_box()
    pb = res.layout.personal_row_box()
    assert pb.y >= sb.y2 - 2
    assert pb.h >= 60

    # Verify reasonable number of representative keyframes selected (ranks 1..30 -> >= 6 keyframes)
    assert len(res.keyframes) >= 6

    # Verify row slicing on first and last keyframes yields complete rows with 8 icons each
    for kf in (res.keyframes[0], res.keyframes[-1]):
        img = cv2.imread(kf.image_path)
        assert img is not None
        rows = slice_scrollable_rows(img, res.layout)
        assert 4 <= len(rows) <= 5
        for row in rows:
            assert len(row.icon_imgs) == 8
            for icon in row.icon_imgs:
                assert icon.shape[0] >= 24 and icon.shape[1] >= 24
