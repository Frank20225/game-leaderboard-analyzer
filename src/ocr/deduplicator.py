"""Cross-frame team deduplication, multi-frame consensus fusion, and completeness auditing.

Uses Rank as primary identifier, cross-checked by 8-icon visual signature and
monotone business rules (ranks continuous 1..N, scores non-increasing).
Never claims 200-team completeness without explicit audit verification.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np


@dataclass
class RowObservation:
    """Raw recognition of a single visible row inside one keyframe."""

    keyframe_id: int
    frame_idx: int
    timestamp_sec: float
    keyframe_reason: str
    keyframe_sharpness: float
    composite_frames_used: int
    row_index_in_frame: int
    rank: int | None
    rank_conf: float
    rank_source: str
    rank_inferred: bool
    team_name: str
    name_conf: float
    name_source: str
    score: int | None
    score_conf: float
    icon_signature: np.ndarray  # Lightweight HSV signature across 8 icons for conflict checking
    row_img: np.ndarray
    name_img: np.ndarray
    icon_imgs: list[np.ndarray]
    score_img: np.ndarray | None = None


@dataclass
class TeamRecord:
    """Deduplicated, consensus-fused team record across all keyframes."""

    rank: int
    team_name: str
    score: int | None
    rank_conf: float
    name_conf: float
    score_conf: float
    name_source: str
    rank_inferred: bool
    observation_count: int
    source_keyframe_ids: list[int]
    representative_keyframe_id: int
    row_crop_path: str
    name_crop_path: str
    icon_crop_paths: list[str]
    occupations: list[str] = field(default_factory=lambda: [""] * 8)
    occupation_confs: list[float] = field(default_factory=lambda: [0.0] * 8)
    status: str = "verified"  # "verified" | "flagged" | "edited"
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RecognitionIssue:
    """Explicit error or warning entry surfaced in the UI & Excel Recognition Errors sheet."""

    issue_type: str  # missing_rank | score_monotonicity | low_name_conf | low_score_conf | rank_inferred | rank_conflict | low_icon_conf
    severity: str  # "error" | "warning"
    rank: int | None
    field: str
    detected_value: str
    confidence: float
    keyframe_id: int | None
    crop_path: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditSummary:
    """Honest completeness and accuracy audit for Phase 2."""

    extracted_team_count: int
    min_rank: int | None
    max_rank: int | None
    expected_range_count: int
    missing_ranks: list[int]
    duplicate_or_conflict_count: int
    flagged_team_count: int
    issue_count: int
    is_contiguous_from_1: bool
    completeness_note: str

    def to_dict(self) -> dict:
        return asdict(self)


def compute_icon_strip_signature(icon_imgs: list[np.ndarray]) -> np.ndarray:
    """Compute a compact 8-slot HSV color histogram signature to verify team identity."""
    vecs = []
    for icon in icon_imgs:
        hsv = cv2.cvtColor(icon, cv2.COLOR_BGR2HSV)
        h_hist = cv2.calcHist([hsv], [0], None, [12], [0, 180]).flatten()
        s_hist = cv2.calcHist([hsv], [1], None, [6], [0, 256]).flatten()
        v = np.concatenate([h_hist, s_hist]).astype(np.float32)
        norm = float(np.linalg.norm(v)) + 1e-6
        vecs.append(v / norm)
    return np.concatenate(vecs)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    return float(np.dot(a, b) / denom)


def infer_missing_ranks_in_frame(frame_obs: list[RowObservation]) -> list[RowObservation]:
    """Fill missing or outlier rank within a single keyframe using sequential row order.

    In any single frame, rows are strictly consecutive integers: rank[i+1] == rank[i] + 1.
    Uses majority vote over candidate base_rank = (obs.rank - idx) to catch both missing
    and single-row misread ranks!
    """
    if len(frame_obs) < 2:
        return frame_obs

    base_votes: Counter[int] = Counter()
    for idx, ob in enumerate(frame_obs):
        if ob.rank is not None:
            base = ob.rank - idx
            if base >= 1:
                # Weight stable badge or high-confidence digit readings higher
                weight = 3 if ob.rank_source.startswith("badge:") or ob.rank_conf >= 0.85 else 1
                base_votes[base] += weight

    if not base_votes:
        return frame_obs

    best_base, best_weight = base_votes.most_common(1)[0]
    # Only enforce sequence correction if at least 2 rows agree on the base offset
    agreeing_rows = sum(1 for idx, ob in enumerate(frame_obs) if ob.rank == best_base + idx)
    if agreeing_rows < 2:
        return frame_obs

    for idx, ob in enumerate(frame_obs):
        expected_rank = best_base + idx
        if ob.rank != expected_rank:
            ob.rank = expected_rank
            ob.rank_inferred = True
            ob.rank_conf = max(0.5, ob.rank_conf * 0.6)
            ob.rank_source = f"inferred_from_neighbors(base={best_base})"
    return frame_obs


def _select_best_icon_per_slot(obs_list: list[RowObservation]) -> list[np.ndarray]:
    """Choose the cleanest, cursor-free icon crop for each of the 8 slots across observations."""
    if len(obs_list) == 1:
        return [im.copy() for im in obs_list[0].icon_imgs]

    # Prefer observations from stable_segment median composites first
    sorted_obs = sorted(
        obs_list,
        key=lambda o: (
            1 if o.keyframe_reason == "stable_segment" else 0,
            o.composite_frames_used,
            o.keyframe_sharpness,
        ),
        reverse=True,
    )
    if len(sorted_obs) == 2:
        return [im.copy() for im in sorted_obs[0].icon_imgs]

    # With >=3 observations of the same team, pick the icon closest to the pairwise median
    # per slot so a transient mouse cursor on a single frame is automatically rejected!
    best_icons: list[np.ndarray] = []
    for slot in range(8):
        candidates = [o.icon_imgs[slot] for o in sorted_obs]
        # Resize all to first candidate's shape for pixel comparison
        th, tw = candidates[0].shape[:2]
        resized = [cv2.resize(c, (tw, th)).astype(np.float32) for c in candidates]
        med = np.median(np.stack(resized, axis=0), axis=0)
        dists = [float(np.abs(r - med).mean()) for r in resized]
        best_idx = int(np.argmin(dists))
        best_icons.append(candidates[best_idx].copy())
    return best_icons


def fuse_observations_and_audit(
    all_observations: list[RowObservation],
    crops_dir: str | Path,
    name_conf_threshold: float = 0.55,
    score_conf_threshold: float = 0.65,
) -> tuple[list[TeamRecord], list[RecognitionIssue], AuditSummary]:
    """Deduplicate cross-frame observations by rank, fuse best fields, and audit quality."""
    out_crops = Path(crops_dir)
    out_crops.mkdir(parents=True, exist_ok=True)
    icons_dir = out_crops / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Group by keyframe first to run within-frame sequence inference
    by_kf: dict[int, list[RowObservation]] = defaultdict(list)
    for ob in all_observations:
        by_kf[ob.keyframe_id].append(ob)
    for kf_id in by_kf:
        by_kf[kf_id].sort(key=lambda o: o.row_index_in_frame)
        infer_missing_ranks_in_frame(by_kf[kf_id])

    # Group all valid-rank observations by rank
    by_rank: dict[int, list[RowObservation]] = defaultdict(list)
    issues: list[RecognitionIssue] = []

    for kf_id in sorted(by_kf):
        for ob in by_kf[kf_id]:
            if ob.rank is None:
                err_crop = out_crops / f"unranked_kf{kf_id:03d}_r{ob.row_index_in_frame}.png"
                cv2.imwrite(str(err_crop), ob.row_img)
                issues.append(
                    RecognitionIssue(
                        issue_type="unrecognized_rank",
                        severity="error",
                        rank=None,
                        field="rank",
                        detected_value="",
                        confidence=0.0,
                        keyframe_id=kf_id,
                        crop_path=str(err_crop),
                        message=f"影格 KF{kf_id} 第 {ob.row_index_in_frame+1} 列無法辨識排名且無法由鄰列推算",
                    )
                )
                continue
            by_rank[ob.rank].append(ob)

    teams: list[TeamRecord] = []
    conflict_count = 0

    for rank in sorted(by_rank.keys()):
        obs_list = by_rank[rank]

        # Sort observations by quality (stable median composite > stable single > scroll_step)
        obs_list.sort(
            key=lambda o: (
                1 if o.keyframe_reason == "stable_segment" else 0,
                o.composite_frames_used,
                o.keyframe_sharpness,
            ),
            reverse=True,
        )
        anchor = obs_list[0]

        # Cross-frame icon-signature consistency check (detects misread rank collisions)
        consistent_obs = [anchor]
        for ob in obs_list[1:]:
            sim = cosine_sim(anchor.icon_signature, ob.icon_signature)
            if sim >= 0.72:
                consistent_obs.append(ob)
            else:
                conflict_count += 1
                conf_path = out_crops / f"conflict_rank{rank:03d}_kf{ob.keyframe_id:03d}.png"
                cv2.imwrite(str(conf_path), ob.row_img)
                issues.append(
                    RecognitionIssue(
                        issue_type="rank_conflict",
                        severity="warning",
                        rank=rank,
                        field="rank",
                        detected_value=ob.team_name,
                        confidence=ob.rank_conf,
                        keyframe_id=ob.keyframe_id,
                        crop_path=str(conf_path),
                        message=f"排名 {rank} 在 KF{ob.keyframe_id} 的圖示簽章與主影格 KF{anchor.keyframe_id} 不一致 (sim={sim:.2f})，已保留主影格資料",
                    )
                )

        # Consensus score: confidence-weighted vote
        score_weights: dict[int, float] = defaultdict(float)
        score_max_conf: dict[int, float] = defaultdict(float)
        for ob in consistent_obs:
            if ob.score is not None:
                w = ob.score_conf + (0.3 if ob.keyframe_reason == "stable_segment" else 0.0)
                score_weights[ob.score] += w
                score_max_conf[ob.score] = max(score_max_conf[ob.score], ob.score_conf)
        if score_weights:
            best_score = max(score_weights.keys(), key=lambda s: score_weights[s])
            best_score_conf = round(score_max_conf[best_score], 4)
        else:
            best_score = None
            best_score_conf = 0.0

        # Consensus team name: vote weighted by confidence + stability bonus
        name_weights: dict[str, float] = defaultdict(float)
        name_meta: dict[str, tuple[float, str]] = {}
        for ob in consistent_obs:
            if ob.team_name:
                bonus = 0.25 if ob.keyframe_reason == "stable_segment" else 0.0
                name_weights[ob.team_name] += ob.name_conf + bonus
                prev_c = name_meta.get(ob.team_name, (0.0, ""))[0]
                if ob.name_conf >= prev_c:
                    name_meta[ob.team_name] = (ob.name_conf, ob.name_source)
        if name_weights:
            best_name = max(name_weights.keys(), key=lambda n: name_weights[n])
            best_name_conf, best_name_src = name_meta[best_name]
        else:
            best_name, best_name_conf, best_name_src = "", 0.0, "empty"

        # Save representative row, name, and 8 cursor-free icon crops
        row_crop_path = out_crops / f"rank_{rank:03d}_row.png"
        name_crop_path = out_crops / f"rank_{rank:03d}_name.png"
        cv2.imwrite(str(row_crop_path), anchor.row_img)
        cv2.imwrite(str(name_crop_path), anchor.name_img)

        best_icons = _select_best_icon_per_slot(consistent_obs)
        icon_paths: list[str] = []
        for slot_idx, icon_img in enumerate(best_icons):
            ipath = icons_dir / f"rank_{rank:03d}_slot_{slot_idx}.png"
            cv2.imwrite(str(ipath), icon_img)
            icon_paths.append(str(ipath))

        rank_inferred_all = all(ob.rank_inferred for ob in consistent_obs)
        best_rank_conf = round(max(ob.rank_conf for ob in consistent_obs), 4)

        flags: list[str] = []
        if rank_inferred_all:
            flags.append("rank_inferred")
            issues.append(
                RecognitionIssue(
                    issue_type="rank_inferred",
                    severity="warning",
                    rank=rank,
                    field="rank",
                    detected_value=str(rank),
                    confidence=best_rank_conf,
                    keyframe_id=anchor.keyframe_id,
                    crop_path=str(row_crop_path),
                    message=f"排名 {rank} 由同影格相鄰列推算而來，建議人工確認",
                )
            )
        if not best_name or best_name_conf < name_conf_threshold:
            flags.append("low_name_conf")
            issues.append(
                RecognitionIssue(
                    issue_type="low_name_conf",
                    severity="warning",
                    rank=rank,
                    field="team_name",
                    detected_value=best_name,
                    confidence=round(best_name_conf, 4),
                    keyframe_id=anchor.keyframe_id,
                    crop_path=str(name_crop_path),
                    message=f"排名 {rank} 戰隊名稱信心度偏低 ({best_name_conf:.2f})：{best_name!r}",
                )
            )
        if best_score is None or best_score_conf < score_conf_threshold:
            flags.append("low_score_conf")
            issues.append(
                RecognitionIssue(
                    issue_type="low_score_conf",
                    severity="error" if best_score is None else "warning",
                    rank=rank,
                    field="score",
                    detected_value="" if best_score is None else str(best_score),
                    confidence=best_score_conf,
                    keyframe_id=anchor.keyframe_id,
                    crop_path=str(row_crop_path),
                    message=f"排名 {rank} 積分辨識失敗或信心度偏低 ({best_score_conf:.2f})",
                )
            )

        teams.append(
            TeamRecord(
                rank=rank,
                team_name=best_name,
                score=best_score,
                rank_conf=best_rank_conf,
                name_conf=round(best_name_conf, 4),
                score_conf=best_score_conf,
                name_source=best_name_src,
                rank_inferred=rank_inferred_all,
                observation_count=len(consistent_obs),
                source_keyframe_ids=sorted({ob.keyframe_id for ob in consistent_obs}),
                representative_keyframe_id=anchor.keyframe_id,
                row_crop_path=str(row_crop_path),
                name_crop_path=str(name_crop_path),
                icon_crop_paths=icon_paths,
                status="flagged" if flags else "verified",
                flags=flags,
            )
        )

    # Business Rule Audit 1: Score non-increasing monotonicity across ranks
    prev_score: int | None = None
    prev_rank: int | None = None
    for team in teams:
        if team.score is not None and prev_score is not None and team.score > prev_score:
            if "score_monotonicity" not in team.flags:
                team.flags.append("score_monotonicity")
                team.status = "flagged"
            issues.append(
                RecognitionIssue(
                    issue_type="score_monotonicity",
                    severity="error",
                    rank=team.rank,
                    field="score",
                    detected_value=str(team.score),
                    confidence=team.score_conf,
                    keyframe_id=team.representative_keyframe_id,
                    crop_path=team.row_crop_path,
                    message=f"排名 {team.rank} 積分 ({team.score}) 高於前一名 {prev_rank} ({prev_score})，違反排行榜遞減規則",
                )
            )
        if team.score is not None:
            prev_score = team.score
            prev_rank = team.rank

    # Business Rule Audit 2: Rank contiguity & missing rank detection
    if teams:
        present = {t.rank for t in teams}
        min_r, max_r = min(present), max(present)
        missing = [r for r in range(1, max_r + 1) if r not in present]
        for mr in missing:
            issues.append(
                RecognitionIssue(
                    issue_type="missing_rank",
                    severity="error",
                    rank=mr,
                    field="rank",
                    detected_value="",
                    confidence=0.0,
                    keyframe_id=None,
                    crop_path="",
                    message=f"缺漏第 {mr} 名（在已偵測範圍 1..{max_r} 內未擷取到該隊）",
                )
            )
        is_contiguous = (min_r == 1) and (len(missing) == 0)
        flagged_cnt = sum(1 for t in teams if t.status == "flagged")
        note = (
            f"已實際擷取並去重 {len(teams)} 隊（排名 {min_r}..{max_r}），"
            + ("1..max_rank 連續無漏隊" if is_contiguous else f"缺漏 {len(missing)} 隊: {missing[:10]}")
            + f"；待人工確認/警告列數：{flagged_cnt}。"
        )
        if max_r < 200:
            note += f"（影片實際涵蓋至第 {max_r} 名，尚未達 200 隊上限）"
    else:
        min_r, max_r, missing, is_contiguous, flagged_cnt = None, None, [], False, 0
        note = "未擷取到任何有效隊伍資料。"

    audit = AuditSummary(
        extracted_team_count=len(teams),
        min_rank=min_r,
        max_rank=max_r,
        expected_range_count=max_r or 0,
        missing_ranks=missing,
        duplicate_or_conflict_count=conflict_count,
        flagged_team_count=flagged_cnt,
        issue_count=len(issues),
        is_contiguous_from_1=is_contiguous,
        completeness_note=note,
    )
    return teams, issues, audit
