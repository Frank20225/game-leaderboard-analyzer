"""Standalone Phase 2 runner: multilingual OCR, cross-frame deduplication & audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.layout.detector import LayoutConfig
from src.layout.slicer import slice_scrollable_rows
from src.ocr.deduplicator import (
    AuditSummary,
    RecognitionIssue,
    RowObservation,
    TeamRecord,
    compute_icon_strip_signature,
    fuse_observations_and_audit,
)
from src.ocr.text_ocr import MultilingualOcrEngine, preprocess_for_digits
from src.pipeline_phase1 import run_phase1


def _load_font(candidates: list[str], size: int = 20) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for fp in candidates:
        if Path(fp).is_file():
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_ocr_debug_sheet(teams: list[TeamRecord], output_path: Path, max_rows: int = 35) -> None:
    """Create a side-by-side visual verification contact sheet: original row crop vs OCR output."""
    subset = teams[:max_rows]
    if not subset:
        return

    row_h = 68
    crop_w = 760
    info_w = 560
    total_w = crop_w + info_w
    header_h = 44
    canvas = Image.new("RGB", (total_w, header_h + len(subset) * row_h), (250, 250, 252))
    draw = ImageDraw.Draw(canvas)
    font_cjk = _load_font([r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\mingliu.ttc"], 18)
    font_th = _load_font([r"C:\Windows\Fonts\leelawui.ttf", r"C:\Windows\Fonts\leelawad.ttf", r"C:\Windows\Fonts\tahoma.ttf"], 18)
    font_small = _load_font([r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\tahoma.ttf"], 14)

    draw.rectangle([(0, 0), (total_w, header_h)], fill=(30, 41, 59))
    draw.text((14, 11), "Original Cropped Row (from Best Keyframe)", fill=(255, 255, 255), font=font_cjk)
    draw.text((crop_w + 14, 11), "OCR Result (Rank | Team Name | Score | Conf)", fill=(255, 255, 255), font=font_cjk)

    for idx, t in enumerate(subset):
        y0 = header_h + idx * row_h
        bg = (255, 245, 245) if t.status == "flagged" else ((255, 255, 255) if idx % 2 == 0 else (245, 247, 250))
        draw.rectangle([(0, y0), (total_w, y0 + row_h)], fill=bg)
        draw.line([(0, y0 + row_h - 1), (total_w, y0 + row_h - 1)], fill=(220, 224, 230), width=1)

        img_bgr = cv2.imread(t.row_crop_path)
        if img_bgr is not None:
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil_crop = Image.fromarray(rgb)
            pil_crop.thumbnail((crop_w - 16, row_h - 10))
            canvas.paste(pil_crop, (8, y0 + (row_h - pil_crop.height) // 2))

        badge_color = (22, 163, 74) if t.status == "verified" else (217, 119, 6)
        draw.rectangle([(crop_w + 8, y0 + 10), (crop_w + 16, y0 + row_h - 10)], fill=badge_color)
        line1 = f"#{t.rank:<3d} | {t.team_name}  |  Score: {t.score}"
        line2 = f"src={t.name_source}  name_conf={t.name_conf:.2f}  score_conf={t.score_conf:.2f}  obs={t.observation_count}  flags={t.flags or 'OK'}"
        use_font = font_th if t.name_source == "th_en" else font_cjk
        draw.text((crop_w + 26, y0 + 10), line1, fill=(15, 23, 42), font=use_font)
        draw.text((crop_w + 26, y0 + 38), line2, fill=(100, 116, 139), font=font_small)

    canvas.save(str(output_path))


def render_ocr_preprocessing_demo(sample_rank_img: np.ndarray, output_path: Path) -> None:
    """Save a before-vs-after preprocessing comparison image for learning/debug view."""
    proc = preprocess_for_digits(sample_rank_img, scale=2.6)
    proc_bgr = cv2.cvtColor(proc, cv2.COLOR_GRAY2BGR)
    # Match heights side-by-side
    target_h = proc_bgr.shape[0]
    scale = target_h / max(1, sample_rank_img.shape[0])
    orig_resized = cv2.resize(
        sample_rank_img,
        (int(round(sample_rank_img.shape[1] * scale)), target_h),
        interpolation=cv2.INTER_NEAREST,
    )
    sep = np.full((target_h, 16, 3), 200, dtype=np.uint8)
    combined = np.hstack([orig_resized, sep, proc_bgr])
    cv2.putText(combined, "RAW CROP", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
    cv2.putText(
        combined,
        "UPSCALED + NORM + PADDED",
        (orig_resized.shape[1] + 24, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 140, 0),
        2,
    )
    cv2.imwrite(str(output_path), combined)


def run_phase2(
    run_dir: str | Path,
    ocr_engine: MultilingualOcrEngine | None = None,
) -> tuple[list[TeamRecord], list[RecognitionIssue], AuditSummary]:
    """Run Phase 2 OCR extraction & cross-frame deduplication on an existing Phase 1 run_dir."""
    run_path = Path(run_dir)
    phase1_dir = run_path / "phase1_frames"
    summary_path = phase1_dir / "phase1_summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"找不到 Phase 1 輸出摘要: {summary_path}")

    p1 = json.loads(summary_path.read_text(encoding="utf-8"))
    layout = LayoutConfig(**p1["layout"])
    keyframes = p1["keyframes"]

    phase2_dir = run_path / "phase2_extracted"
    crops_dir = phase2_dir / "crops"
    phase2_dir.mkdir(parents=True, exist_ok=True)
    crops_dir.mkdir(parents=True, exist_ok=True)

    engine = ocr_engine or MultilingualOcrEngine(gpu=False)
    all_obs: list[RowObservation] = []
    demo_saved = False

    for kf in keyframes:
        frame = cv2.imread(kf["image_path"])
        if frame is None:
            continue
        rows = slice_scrollable_rows(frame, layout)
        for row in rows:
            rank_val, rank_conf, rank_src = engine.read_rank(row.rank_img)
            score_val, score_conf, _ = engine.read_score(row.score_img)
            name_res = engine.read_team_name(row.name_img)
            sig = compute_icon_strip_signature(row.icon_imgs)

            if not demo_saved and rank_val is not None and rank_val >= 4:
                render_ocr_preprocessing_demo(row.rank_img, phase2_dir / "debug_digit_preprocess.png")
                demo_saved = True

            all_obs.append(
                RowObservation(
                    keyframe_id=int(kf["keyframe_id"]),
                    frame_idx=int(kf["frame_idx"]),
                    timestamp_sec=float(kf["timestamp_sec"]),
                    keyframe_reason=str(kf["reason"]),
                    keyframe_sharpness=float(kf["sharpness"]),
                    composite_frames_used=int(kf["composite_frames_used"]),
                    row_index_in_frame=row.row_index_in_frame,
                    rank=rank_val,
                    rank_conf=rank_conf,
                    rank_source=rank_src,
                    rank_inferred=False,
                    team_name=name_res.text,
                    name_conf=name_res.confidence,
                    name_source=name_res.source,
                    score=score_val,
                    score_conf=score_conf,
                    icon_signature=sig,
                    row_img=row.row_img,
                    name_img=row.name_img,
                    icon_imgs=row.icon_imgs,
                )
            )

    teams, issues, audit = fuse_observations_and_audit(all_obs, crops_dir=crops_dir)

    (phase2_dir / "teams_raw.json").write_text(
        json.dumps([t.to_dict() for t in teams], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (phase2_dir / "issues.json").write_text(
        json.dumps([i.to_dict() for i in issues], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (phase2_dir / "audit_report.json").write_text(
        json.dumps(audit.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    render_ocr_debug_sheet(teams, phase2_dir / "debug_ocr_grid.png")
    return teams, issues, audit


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.pipeline_phase2 <existing_run_dir_or_video_path>")
        sys.exit(1)
    arg = Path(sys.argv[1])
    if arg.is_file():
        p1 = run_phase1(arg)
        run_dir = Path(p1.summary_json_path).parent.parent
    else:
        run_dir = arg
    teams, issues, audit = run_phase2(run_dir)
    print(json.dumps({"audit": audit.to_dict(), "sample_teams": [t.to_dict() for t in teams[:10]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
