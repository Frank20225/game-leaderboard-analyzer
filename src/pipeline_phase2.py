"""Standalone Phase 2 runner: multilingual OCR, cross-frame deduplication & audit."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from collections.abc import Callable
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
    infer_missing_ranks_in_frame,
)
from src.ocr.text_ocr import MultilingualOcrEngine, get_shared_ocr_engine, preprocess_for_digits
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
    progress_cb: Callable[[float, str], None] | None = None,
) -> tuple[list[TeamRecord], list[RecognitionIssue], AuditSummary]:
    """Run Phase 2 OCR extraction & cross-frame deduplication with live progress & fast two-pass name OCR."""
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

    engine = ocr_engine or get_shared_ocr_engine()
    if progress_cb:
        progress_cb(3.0, f"載入中/英/泰 OCR 模型（硬體加速：{engine.device_label}）...")
    # Trigger lazy load of primary reader so progress reflects model load cleanly
    _ = engine.reader_cjk

    all_obs: list[RowObservation] = []
    demo_saved = False
    total_kf = max(1, len(keyframes))

    # Pass 1 (Fast 2-Anchor Rank Scan + Icon Signature):
    # Since rows in any single frame are strictly consecutive (base, base+1, ..., base+5),
    # probe 2 anchor rows (row 0 and row 3) first; if they agree on base_rank with high confidence,
    # skip redundant rank OCR on the remaining 4 rows!
    for kf_pos, kf in enumerate(keyframes):
        if progress_cb:
            pct = 8.0 + (kf_pos / total_kf) * 34.0
            progress_cb(pct, f"[1/2 快速定位影格排名 ({engine.device_label})] 影格 {kf_pos + 1} / {total_kf} (KF{kf['keyframe_id']})")
        frame = cv2.imread(kf["image_path"])
        if frame is None:
            continue
        rows = slice_scrollable_rows(frame, layout)
        if not rows:
            continue

        rank_results: dict[int, tuple[int | None, float, str]] = {}
        anchor_idxs = [0, min(3, len(rows) - 1)] if len(rows) >= 4 else list(range(len(rows)))
        for a_idx in anchor_idxs:
            rank_results[a_idx] = engine.read_rank(rows[a_idx].rank_img)

        fast_base: int | None = None
        if len(anchor_idxs) == 2 and anchor_idxs[0] != anchor_idxs[1]:
            r0, c0, s0 = rank_results[anchor_idxs[0]]
            r1, c1, s1 = rank_results[anchor_idxs[1]]
            if (
                r0 is not None
                and r1 is not None
                and (r1 - r0) == (anchor_idxs[1] - anchor_idxs[0])
                and r0 >= 1
                and (c0 >= 0.78 or s0.startswith("badge:"))
                and (c1 >= 0.78 or s1.startswith("badge:"))
            ):
                fast_base = r0 - anchor_idxs[0]

        if fast_base is None:
            for idx in range(len(rows)):
                if idx not in rank_results:
                    rank_results[idx] = engine.read_rank(rows[idx].rank_img)

        frame_obs: list[RowObservation] = []
        for idx, row in enumerate(rows):
            if fast_base is not None and idx not in rank_results:
                rank_val: int | None = fast_base + idx
                rank_conf = 0.92
                rank_src = f"anchor_verified(base={fast_base})"
                rank_inf = False
            else:
                rank_val, rank_conf, rank_src = rank_results[idx]
                rank_inf = False

            sig = compute_icon_strip_signature(row.icon_imgs)

            if not demo_saved and rank_val is not None and rank_val >= 4:
                render_ocr_preprocessing_demo(row.rank_img, phase2_dir / "debug_digit_preprocess.png")
                demo_saved = True

            frame_obs.append(
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
                    rank_inferred=rank_inf,
                    team_name="",
                    name_conf=0.0,
                    name_source="pending",
                    score=None,
                    score_conf=0.0,
                    icon_signature=sig,
                    row_img=row.row_img,
                    name_img=row.name_img,
                    icon_imgs=row.icon_imgs,
                    score_img=row.score_img,
                )
            )
        if fast_base is None:
            infer_missing_ranks_in_frame(frame_obs)
        all_obs.extend(frame_obs)

    # Pass 2 (Targeted Multilingual Team Name + Score OCR on sharpest 1-2 observations per unique rank):
    # Eliminates duplicate Score & Name OCR across overlapping keyframes while keeping consensus voting!
    by_rank_pre: dict[int, list[RowObservation]] = defaultdict(list)
    for ob in all_obs:
        if ob.rank is not None:
            by_rank_pre[ob.rank].append(ob)

    sorted_ranks = sorted(by_rank_pre.keys())
    total_ranks = max(1, len(sorted_ranks))
    for r_pos, rank in enumerate(sorted_ranks):
        if progress_cb:
            pct = 44.0 + (r_pos / total_ranks) * 48.0
            progress_cb(
                pct,
                f"[2/2 辨識隊名與積分 ({engine.device_label})] 第 #{rank} 名（{r_pos + 1} / {total_ranks} 隊）",
            )
        obs_for_rank = sorted(
            by_rank_pre[rank],
            key=lambda o: (
                1 if o.keyframe_reason == "stable_segment" else 0,
                o.composite_frames_used,
                o.keyframe_sharpness,
            ),
            reverse=True,
        )
        best_ob = obs_for_rank[0]
        res1 = engine.read_team_name(best_ob.name_img)
        best_ob.team_name = res1.text
        best_ob.name_conf = res1.confidence
        best_ob.name_source = res1.source
        if best_ob.score_img is not None:
            sc1, sc_conf1, _ = engine.read_score(best_ob.score_img)
            best_ob.score = sc1
            best_ob.score_conf = sc_conf1

        if len(obs_for_rank) >= 2:
            second_ob = obs_for_rank[1]
            if res1.confidence < 0.85:
                res2 = engine.read_team_name(second_ob.name_img)
                second_ob.team_name = res2.text
                second_ob.name_conf = res2.confidence
                second_ob.name_source = res2.source
            if (best_ob.score is None or best_ob.score_conf < 0.85) and second_ob.score_img is not None:
                sc2, sc_conf2, _ = engine.read_score(second_ob.score_img)
                second_ob.score = sc2
                second_ob.score_conf = sc_conf2

    if progress_cb:
        progress_cb(94.0, "跨影格融合去重、稽核完整性與輸出對照表...")

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
    if progress_cb:
        progress_cb(100.0, f"完成！已擷取 {len(teams)} 隊")
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
