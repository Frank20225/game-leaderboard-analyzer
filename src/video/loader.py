"""Read-only video loader and metadata extraction.

Original MP4 files are strictly opened read-only and never modified.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoMetadata:
    """Basic properties of an input leaderboard recording."""

    path: str
    filename: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_sec: float

    def to_dict(self) -> dict:
        return asdict(self)


def load_video_metadata(video_path: str | Path) -> VideoMetadata:
    """Inspect video metadata without mutating the source file."""
    path = Path(video_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"找不到影片檔案: {path}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"OpenCV 無法開啟影片（格式損毀或缺少解碼器）: {path}")

    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0.0:
            fps = 30.0
        duration_sec = round(frame_count / fps, 3) if frame_count > 0 else 0.0
    finally:
        cap.release()

    if width <= 0 or height <= 0 or frame_count <= 0:
        raise ValueError(f"影片中繼資料異常: {width}x{height}, frames={frame_count}")

    return VideoMetadata(
        path=str(path),
        filename=path.name,
        width=width,
        height=height,
        fps=round(fps, 3),
        frame_count=frame_count,
        duration_sec=duration_sec,
    )


def sample_frames_uniform(
    video_path: str | Path, num_samples: int = 16
) -> list[tuple[int, np.ndarray]]:
    """Sample frames evenly across the video for layout & static-region detection."""
    meta = load_video_metadata(video_path)
    indices = np.linspace(0, max(0, meta.frame_count - 1), num=min(num_samples, meta.frame_count), dtype=int)
    unique_indices = sorted({int(i) for i in indices})

    cap = cv2.VideoCapture(str(meta.path))
    if not cap.isOpened():
        raise ValueError(f"無法開啟影片進行取樣: {meta.path}")

    frames: list[tuple[int, np.ndarray]] = []
    try:
        for idx in unique_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append((idx, frame))
    finally:
        cap.release()

    if not frames:
        raise ValueError(f"無法從影片讀取任何影格: {meta.path}")
    return frames


def read_frame_at(cap: cv2.VideoCapture, frame_idx: int) -> np.ndarray | None:
    """Seek and read a single frame by index."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame = cap.read()
    return frame if ok and frame is not None else None
