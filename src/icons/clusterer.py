"""Icon clustering (Agglomerative Clustering on combined cosine + NCC distance)
and human-in-the-loop cluster labeling / merging / splitting helpers.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
from sklearn.cluster import AgglomerativeClustering

from src.icons.database import IconDatabase
from src.icons.features import IconAnalysis, analyze_icon, compute_ncc_similarity

EMPTY_LABEL = "(空位)"


@dataclass
class IconInstance:
    """Single cropped icon belonging to (team rank, slot 0..7)."""

    instance_id: str
    rank: int
    slot: int
    crop_path: str
    norm_path: str
    is_empty: bool
    cluster_id: str
    assigned_name: str
    confidence: float
    matched_from_db: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IconCluster:
    """Group of visually similar icons awaiting or having received human confirmation."""

    cluster_id: str
    suggested_name: str
    confirmed_name: str
    matched_from_db: bool
    count: int
    avg_internal_sim: float
    min_internal_sim: float
    representative_norm_path: str
    sample_instance_ids: list[str]
    all_instance_ids: list[str]
    needs_review: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def compute_pairwise_similarity_matrix(analyses: list[IconAnalysis]) -> np.ndarray:
    """Compute symmetric N x N combined similarity matrix (feature cosine + masked NCC)."""
    n = len(analyses)
    if n == 0:
        return np.zeros((0, 0), dtype=np.float32)

    feats = np.stack([a.feature_vec for a in analyses], axis=0)  # (N, D), already L2-normalized
    feat_sim = np.clip(feats @ feats.T, 0.0, 1.0)

    # Fast vectorized masked NCC across all N icons
    from src.icons.features import _MASK_FULL

    patches = np.stack(
        [a.normalized_bgr[_MASK_FULL].astype(np.float32).flatten() for a in analyses], axis=0
    )
    patches -= patches.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(patches, axis=1, keepdims=True) + 1e-8
    patches /= norms
    ncc_sim = np.clip(patches @ patches.T, 0.0, 1.0)

    sim = 0.55 * feat_sim + 0.45 * ncc_sim
    np.fill_diagonal(sim, 1.0)
    return sim.astype(np.float32)


def cluster_team_icons(
    teams: list[dict],
    output_dir: str | Path,
    icon_db: IconDatabase,
    db_match_threshold: float = 0.84,
    cluster_distance_threshold: float = 0.22,
) -> tuple[list[IconInstance], list[IconCluster], np.ndarray, list[int]]:
    """Analyze all icons across extracted teams: detect empty slots, match DB, cluster unknowns.

    Returns (instances, clusters, sorted_similarity_matrix, cluster_order_labels).
    """
    out_dir = Path(output_dir)
    norm_dir = out_dir / "normalized"
    norm_dir.mkdir(parents=True, exist_ok=True)

    instances: list[IconInstance] = []
    unknown_indices: list[int] = []
    unknown_analyses: list[IconAnalysis] = []
    db_groups: dict[str, list[int]] = defaultdict(list)
    db_sims: dict[int, float] = {}
    empty_indices: list[int] = []

    for team in teams:
        rank = int(team["rank"])
        for slot, crop_path in enumerate(team["icon_crop_paths"]):
            inst_id = f"r{rank:03d}_s{slot}"
            img = cv2.imread(crop_path)
            if img is None:
                continue
            analysis = analyze_icon(img)
            norm_path = norm_dir / f"{inst_id}.png"
            cv2.imwrite(str(norm_path), analysis.normalized_bgr)

            if analysis.is_empty:
                idx = len(instances)
                empty_indices.append(idx)
                instances.append(
                    IconInstance(
                        instance_id=inst_id,
                        rank=rank,
                        slot=slot,
                        crop_path=crop_path,
                        norm_path=str(norm_path),
                        is_empty=True,
                        cluster_id="EMPTY",
                        assigned_name=EMPTY_LABEL,
                        confidence=1.0,
                        matched_from_db=False,
                    )
                )
                continue

            match = icon_db.match(analysis, threshold=db_match_threshold)
            idx = len(instances)
            if match.matched:
                db_groups[match.occupation_name].append(idx)
                db_sims[idx] = match.similarity
                instances.append(
                    IconInstance(
                        instance_id=inst_id,
                        rank=rank,
                        slot=slot,
                        crop_path=crop_path,
                        norm_path=str(norm_path),
                        is_empty=False,
                        cluster_id=f"DB_{match.occupation_name}",
                        assigned_name=match.occupation_name,
                        confidence=match.similarity,
                        matched_from_db=True,
                    )
                )
            else:
                unknown_indices.append(idx)
                unknown_analyses.append(analysis)
                instances.append(
                    IconInstance(
                        instance_id=inst_id,
                        rank=rank,
                        slot=slot,
                        crop_path=crop_path,
                        norm_path=str(norm_path),
                        is_empty=False,
                        cluster_id="",
                        assigned_name="",
                        confidence=0.0,
                        matched_from_db=False,
                    )
                )

    clusters: list[IconCluster] = []

    # 1. Build clusters for DB-matched occupations
    for occ_name, idxs in sorted(db_groups.items(), key=lambda kv: len(kv[1]), reverse=True):
        sims = [db_sims[i] for i in idxs]
        best_i = max(idxs, key=lambda i: db_sims[i])
        clusters.append(
            IconCluster(
                cluster_id=f"DB_{occ_name}",
                suggested_name=occ_name,
                confirmed_name=occ_name,
                matched_from_db=True,
                count=len(idxs),
                avg_internal_sim=round(float(np.mean(sims)), 4),
                min_internal_sim=round(float(np.min(sims)), 4),
                representative_norm_path=instances[best_i].norm_path,
                sample_instance_ids=[instances[i].instance_id for i in idxs[:12]],
                all_instance_ids=[instances[i].instance_id for i in idxs],
                needs_review=float(np.min(sims)) < 0.88,
            )
        )

    # 2. Cluster unknown icons using Agglomerative Clustering on precomputed distance
    sorted_sim_matrix = np.zeros((0, 0), dtype=np.float32)
    sorted_cluster_labels: list[int] = []

    if unknown_analyses:
        sim_mat = compute_pairwise_similarity_matrix(unknown_analyses)
        dist_mat = np.clip(1.0 - sim_mat, 0.0, 1.0)

        if len(unknown_analyses) == 1:
            raw_labels = np.array([0])
        else:
            model = AgglomerativeClustering(
                n_clusters=None,
                metric="precomputed",
                linkage="average",
                distance_threshold=cluster_distance_threshold,
            )
            raw_labels = model.fit_predict(dist_mat)

        grouped: dict[int, list[int]] = defaultdict(list)
        for local_i, lbl in enumerate(raw_labels):
            grouped[int(lbl)].append(local_i)

        # Sort clusters by member count descending for convenient human naming
        ordered_groups = sorted(grouped.values(), key=len, reverse=True)

        # Build reordered similarity matrix for learning/debug visualization
        perm: list[int] = []
        for c_num, local_members in enumerate(ordered_groups, start=1):
            cid = f"C{c_num:02d}"
            default_name = f"職業_{c_num:02d}"

            sub_sim = sim_mat[np.ix_(local_members, local_members)]
            # Medoid: member with highest average similarity to all other members of its cluster
            mean_per_member = sub_sim.mean(axis=1)
            medoid_pos = int(np.argmax(mean_per_member))
            medoid_local_idx = local_members[medoid_pos]
            medoid_global_idx = unknown_indices[medoid_local_idx]

            # Order samples: medoid first, then lowest-similarity outliers so user sees edge cases immediately
            sorted_local = sorted(
                local_members,
                key=lambda li: float(sim_mat[li, medoid_local_idx]),
                reverse=True,
            )
            perm.extend(sorted_local)
            sorted_cluster_labels.extend([c_num] * len(sorted_local))

            for li in local_members:
                gi = unknown_indices[li]
                sim_to_medoid = float(sim_mat[li, medoid_local_idx])
                instances[gi].cluster_id = cid
                instances[gi].assigned_name = default_name
                instances[gi].confidence = round(sim_to_medoid, 4)

            # Sample preview: include top 8 closest + bottom 4 edge samples if cluster is large
            if len(sorted_local) <= 12:
                preview_locals = sorted_local
            else:
                preview_locals = sorted_local[:8] + sorted_local[-4:]

            clusters.append(
                IconCluster(
                    cluster_id=cid,
                    suggested_name=default_name,
                    confirmed_name="",
                    matched_from_db=False,
                    count=len(local_members),
                    avg_internal_sim=round(float(sub_sim.mean()), 4),
                    min_internal_sim=round(float(sub_sim.min()), 4),
                    representative_norm_path=instances[medoid_global_idx].norm_path,
                    sample_instance_ids=[instances[unknown_indices[li]].instance_id for li in preview_locals],
                    all_instance_ids=[instances[unknown_indices[li]].instance_id for li in sorted_local],
                    needs_review=True,
                )
            )

        sorted_sim_matrix = sim_mat[np.ix_(perm, perm)]

    # 3. Record Empty-Slot summary cluster (if any)
    if empty_indices:
        clusters.append(
            IconCluster(
                cluster_id="EMPTY",
                suggested_name=EMPTY_LABEL,
                confirmed_name=EMPTY_LABEL,
                matched_from_db=False,
                count=len(empty_indices),
                avg_internal_sim=1.0,
                min_internal_sim=1.0,
                representative_norm_path=instances[empty_indices[0]].norm_path,
                sample_instance_ids=[instances[i].instance_id for i in empty_indices[:12]],
                all_instance_ids=[instances[i].instance_id for i in empty_indices],
                needs_review=False,
            )
        )

    return instances, clusters, sorted_sim_matrix, sorted_cluster_labels
