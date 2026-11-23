"""Phase 4 v2 Pro Tournament Analytics Engine.

Tailored for uniform-template 8-player rosters (max 2 per occupation) in BO5
(5v5 -> 1v1 -> 3v3 -> 2v2 -> 5v5) tournaments:
- Non-overlapping rank tiers (adaptive for <50 or >=50 teams)
- Dual-metric occupation frequency + 0/1/2 copy marginal rank impact + low-sample flags
- Meta Quadrant classification (X = Team Presence Rate, Y = Avg Rank, lower is stronger)
- Double-pick roster strategy distribution (0/1/2/3/4 double-picks per team)
- True Pairwise Synergy Lift (>1.15 synergy, <0.85 substitution) + full NxN matrix
- Roster Archetype clustering (3-5 main team-building skeletons)
- Score tier breakdown + Tournament rule compliance check (max 2 per occupation)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

import numpy as np
from scipy.stats import spearmanr
from sklearn.cluster import AgglomerativeClustering

from src.icons.clusterer import EMPTY_LABEL


def _clean_team_occs(team: dict) -> list[str]:
    """Return valid non-empty occupation labels for a team."""
    return [
        o.strip()
        for o in team.get("occupations", [])
        if o and o.strip() and o.strip() != EMPTY_LABEL
    ]


def format_full_team_signature(occs: list[str]) -> str:
    """Canonical multiset signature sorted by multiplicity desc then name asc."""
    if not occs:
        return "(無資料)"
    counts = Counter(occs)
    parts = []
    for name, cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        parts.append(f"{name}×{cnt}" if cnt > 1 else name)
    return " + ".join(parts)


def _build_non_overlapping_tiers(max_rank: int) -> list[tuple[str, int, int]]:
    """Build mutually exclusive rank buckets adapted to actual video coverage."""
    if max_rank <= 15:
        return [("#1–5", 1, 5), ("#6–10", 6, 10), ("#11+", 11, max(11, max_rank))]
    if max_rank <= 45:
        mid_end = min(20, max_rank)
        tiers = [("#1–10", 1, 10), (f"#11–{mid_end}", 11, mid_end)]
        if max_rank > mid_end:
            tiers.append((f"#{mid_end + 1}–{max_rank}", mid_end + 1, max_rank))
        return tiers
    if max_rank <= 100:
        return [("#1–10", 1, 10), ("#11–50", 11, 50), (f"#51–{max_rank}", 51, max_rank)]
    return [
        ("#1–10", 1, 10),
        ("#11–50", 11, 50),
        ("#51–100", 51, 100),
        (f"#101–{max_rank}", 101, max_rank),
    ]


def _cluster_roster_archetypes(
    sorted_teams: list[dict],
    team_occs_list: list[list[str]],
    all_occ_names: list[str],
    ranks: list[int],
    top10_set: set[int],
) -> list[dict[str, Any]]:
    """Group rosters into 3-5 strategic team-building archetypes using class count vectors."""
    n = len(sorted_teams)
    if n < 6 or not all_occ_names:
        return []

    occ_to_idx = {o: idx for idx, o in enumerate(all_occ_names)}
    mat = np.zeros((n, len(all_occ_names)), dtype=np.float32)
    for i, occs in enumerate(team_occs_list):
        for o in occs:
            mat[i, occ_to_idx[o]] += 1.0

    # L2-normalize each team's 8-slot composition vector for cosine clustering
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8
    mat_norm = mat / norms

    n_archetypes = min(5, max(3, n // 15 if n >= 45 else 3))
    model = AgglomerativeClustering(n_clusters=n_archetypes, metric="cosine", linkage="average")
    labels = model.fit_predict(mat_norm)

    grouped: dict[int, list[int]] = defaultdict(list)
    for idx, lbl in enumerate(labels):
        grouped[int(lbl)].append(idx)

    archetypes: list[dict[str, Any]] = []
    for grp_idxs in sorted(grouped.values(), key=len, reverse=True):
        cnt = len(grp_idxs)
        sub_mat = mat[grp_idxs]  # (cnt, num_occs)
        presence = (sub_mat > 0).mean(axis=0)
        mean_copies = sub_mat.mean(axis=0)
        double_rate = (sub_mat >= 2).mean(axis=0)

        # Core classes: carried by >= 70% of teams in this archetype
        core = [
            (all_occ_names[j], float(presence[j]), float(mean_copies[j]), float(double_rate[j]))
            for j in range(len(all_occ_names))
            if presence[j] >= 0.70
        ]
        core.sort(key=lambda x: (-x[2], -x[1], x[0]))

        # Flex/signature classes: carried by 35%..69%
        flex = [
            (all_occ_names[j], float(presence[j]), float(mean_copies[j]))
            for j in range(len(all_occ_names))
            if 0.35 <= presence[j] < 0.70
        ]
        flex.sort(key=lambda x: (-x[1], x[0]))

        # Distinguishing classes vs overall average (for human-readable archetype label)
        overall_mean = mat.mean(axis=0)
        diffs = mean_copies - overall_mean
        top_diff_idxs = np.argsort(-diffs)[:2]
        sig_tags = [
            f"偏重{all_occ_names[j]}" if double_rate[j] < 0.45 else f"雙{all_occ_names[j]}"
            for j in top_diff_idxs
            if diffs[j] > 0.18
        ]
        if not sig_tags and core:
            sig_tags = [f"{core[0][0]}核心"]

        c_ranks = [ranks[i] for i in grp_idxs]
        t10_cnt = len(set(grp_idxs).intersection(top10_set))
        core_str = " + ".join(
            f"{name}({mc:.1f})" if mc >= 1.35 else name for name, _, mc, _ in core[:6]
        ) or "(無固定核心)"
        flex_str = " / ".join(f"{name}({pr*100:.0f}%)" for name, pr, _ in flex[:5]) or "-"

        archetypes.append(
            {
                "archetype_name": "・".join(sig_tags) + "體系",
                "team_count": cnt,
                "team_rate": round(cnt / n, 4),
                "avg_rank": round(float(np.mean(c_ranks)), 2),
                "median_rank": round(float(np.median(c_ranks)), 1),
                "best_rank": min(c_ranks),
                "top10_count": t10_cnt,
                "core_classes": core_str,
                "flex_classes": flex_str,
                "avg_double_picks": round(float((sub_mat >= 2).sum(axis=1).mean()), 2),
                "sample_teams": ", ".join(
                    f"#{sorted_teams[i]['rank']} {sorted_teams[i]['team_name']}" for i in grp_idxs[:4]
                ),
            }
        )

    archetypes.sort(key=lambda a: (a["avg_rank"], -a["team_count"]))
    for idx, a in enumerate(archetypes, start=1):
        a["archetype_id"] = f"流派 {idx}"
    return archetypes


def compute_leaderboard_analytics(
    teams: list[dict],
    issues: list[dict] | None = None,
    report_title: str = "排位賽戰隊排陣分析報告",
) -> dict[str, Any]:
    """Compute complete v2 tournament analytics bundle."""
    sorted_teams = sorted(teams, key=lambda t: int(t["rank"]))
    total_teams = len(sorted_teams)
    all_issues = [dict(i) for i in (issues or [])]

    ranks = [int(t["rank"]) for t in sorted_teams]
    scores = [t.get("score") for t in sorted_teams]
    min_rank = min(ranks) if ranks else None
    max_rank = max(ranks) if ranks else None
    overall_avg_rank = round(float(np.mean(ranks)), 2) if ranks else 0.0

    team_occs_list = [_clean_team_occs(t) for t in sorted_teams]
    total_non_empty_slots = sum(len(o) for o in team_occs_list)
    total_empty_slots = sum(
        sum(1 for raw in t.get("occupations", []) if not raw or raw.strip() == EMPTY_LABEL)
        for t in sorted_teams
    )

    # Tournament Rule Audit: max 2 copies of the same occupation per 8-player roster!
    rule_violations = 0
    for t, occs in zip(sorted_teams, team_occs_list):
        cnts = Counter(occs)
        for occ_name, c in cnts.items():
            if c > 2:
                rule_violations += 1
                all_issues.append(
                    {
                        "issue_type": "rule_violation_max2",
                        "severity": "error",
                        "rank": int(t["rank"]),
                        "field": "occupations",
                        "detected_value": f"{occ_name}×{c}",
                        "confidence": 0.0,
                        "keyframe_id": t.get("representative_keyframe_id"),
                        "crop_path": t.get("row_crop_path", ""),
                        "message": f"排名 #{t['rank']} 辨識出 {c} 名「{occ_name}」，違反賽制「同職業最多 2 名」規則，請人工檢查圖示辨識！",
                    }
                )

    # Non-overlapping rank tiers
    tier_specs = _build_non_overlapping_tiers(max_rank or 30)
    tier_indices: dict[str, list[int]] = {}
    tier_meta: list[dict[str, Any]] = []
    for label, lo, hi in tier_specs:
        idxs = [i for i, r in enumerate(ranks) if lo <= r <= hi]
        tier_indices[label] = idxs
        tier_meta.append(
            {
                "tier": label,
                "rank_min": lo,
                "rank_max": hi,
                "team_count": len(idxs),
            }
        )

    # Cumulative convenience references for Top 10 / Top 50 / Top 100
    top10_idxs = [i for i, r in enumerate(ranks) if r <= 10]
    top50_idxs = [i for i, r in enumerate(ranks) if r <= 50]
    top100_idxs = [i for i, r in enumerate(ranks) if r <= 100]
    top10_set = set(top10_idxs)

    # 1. Occupation Frequency + 0/1/2 Copy Breakdown + Meta Quadrant
    all_occ_names = sorted({o for occs in team_occs_list for o in occs})
    occ_freq_rows: list[dict[str, Any]] = []
    ranks_arr = np.array(ranks, dtype=np.float64) if ranks else np.array([])

    for occ in all_occ_names:
        per_team_counts = [occs.count(occ) for occs in team_occs_list]
        slot_count = sum(per_team_counts)

        idx_0 = [i for i, c in enumerate(per_team_counts) if c == 0]
        idx_1 = [i for i, c in enumerate(per_team_counts) if c == 1]
        idx_2 = [i for i, c in enumerate(per_team_counts) if c >= 2]
        carrying_idxs = idx_1 + idx_2
        team_count = len(carrying_idxs)
        multi_copy_teams = len(idx_2)
        carrying_ranks = [ranks[i] for i in carrying_idxs]

        slot_rate = slot_count / max(1, total_non_empty_slots)
        team_rate = team_count / max(1, total_teams)
        double_rate = multi_copy_teams / max(1, total_teams)
        avg_per_carrying = slot_count / max(1, team_count)
        avg_rank = round(float(np.mean(carrying_ranks)), 2) if carrying_ranks else overall_avg_rank

        # Non-overlapping tier presence rates
        tier_rates: dict[str, float] = {}
        for label, _, _ in tier_specs:
            t_idxs = tier_indices[label]
            tier_rates[label] = (
                round(sum(1 for i in t_idxs if per_team_counts[i] > 0) / len(t_idxs), 4)
                if t_idxs
                else 0.0
            )

        t10_rate = round(sum(1 for i in top10_idxs if per_team_counts[i] > 0) / max(1, len(top10_idxs)), 4) if top10_idxs else 0.0
        t50_rate = round(sum(1 for i in top50_idxs if per_team_counts[i] > 0) / max(1, len(top50_idxs)), 4) if top50_idxs else 0.0
        t100_rate = round(sum(1 for i in top100_idxs if per_team_counts[i] > 0) / max(1, len(top100_idxs)), 4) if top100_idxs else 0.0

        ref_tier = "Top 50" if len(top50_idxs) >= 50 else "Top 10"
        ref_rate = t50_rate if ref_tier == "Top 50" else t10_rate
        lift = round(ref_rate / team_rate, 3) if team_rate > 0 else 0.0

        if total_teams >= 5 and len(set(per_team_counts)) > 1:
            rho, pval = spearmanr(per_team_counts, ranks_arr)
            rho_val = 0.0 if np.isnan(rho) else round(float(rho), 4)
            pval_val = 1.0 if np.isnan(pval) else round(float(pval), 4)
        else:
            rho_val, pval_val = 0.0, 1.0

        low_sample_min_teams = max(5, int(round(total_teams * 0.05)))
        is_low_sample = team_count < low_sample_min_teams

        # 0 / 1 / 2 copy breakdown for roster-building decisions!
        def _bucket_stats(idxs: list[int]) -> dict[str, Any]:
            if not idxs:
                return {"teams": 0, "rate": 0.0, "avg_rank": None, "top10_teams": 0, "low_sample": True}
            b_ranks = [ranks[i] for i in idxs]
            return {
                "teams": len(idxs),
                "rate": round(len(idxs) / max(1, total_teams), 4),
                "avg_rank": round(float(np.mean(b_ranks)), 2),
                "top10_teams": len(set(idxs).intersection(top10_set)),
                "low_sample": len(idxs) < low_sample_min_teams,
            }

        c0_stat = _bucket_stats(idx_0)
        c1_stat = _bucket_stats(idx_1)
        c2_stat = _bucket_stats(idx_2)

        # Rank improvement from 1 copy -> 2 copies (positive = 2 copies ranks HIGHER!)
        double_rank_gain = None
        if c1_stat["avg_rank"] is not None and c2_stat["avg_rank"] is not None:
            double_rank_gain = round(c1_stat["avg_rank"] - c2_stat["avg_rank"], 2)

        # Meta Quadrant classification (X threshold = 50% presence, Y threshold = overall_avg_rank)
        is_popular = team_rate >= 0.50
        is_strong = avg_rank <= overall_avg_rank
        if is_low_sample:
            quadrant = f"低樣本觀察 (<{low_sample_min_teams}隊)"
        elif is_popular and is_strong:
            quadrant = "T0 版本核心"
        elif (not is_popular) and is_strong:
            quadrant = "高端奇兵 / 黑馬"
        elif is_popular and (not is_strong):
            quadrant = "普及標配 / 均勢"
        else:
            quadrant = "冷門職"

        occ_freq_rows.append(
            {
                "occupation": occ,
                "slot_count": slot_count,
                "slot_rate": round(slot_rate, 4),
                "team_count": team_count,
                "team_presence_rate": round(team_rate, 4),
                "double_pick_teams": multi_copy_teams,
                "double_pick_rate": round(double_rate, 4),
                "multi_copy_teams": multi_copy_teams,  # backwards-compatible alias
                "avg_per_carrying_team": round(avg_per_carrying, 2),
                "avg_rank": avg_rank,
                "median_rank": round(float(np.median(carrying_ranks)), 1) if carrying_ranks else 0.0,
                "best_rank": min(carrying_ranks) if carrying_ranks else 0,
                "low_sample": is_low_sample,
                "quadrant": quadrant,
                "tier_rates": tier_rates,
                "top10_rate": t10_rate,
                "top50_rate": t50_rate,
                "top100_rate": t100_rate,
                "lift_ref_tier": ref_tier,
                "top_tier_lift": lift,
                "spearman_r": rho_val,
                "spearman_p": pval_val,
                "copy_0": c0_stat,
                "copy_1": c1_stat,
                "copy_2": c2_stat,
                "double_rank_gain": double_rank_gain,
            }
        )

    occ_freq_rows.sort(key=lambda r: (-r["team_presence_rate"], r["avg_rank"], r["occupation"]))

    # 2. Double-Pick Roster Structure Distribution (0 / 1 / 2 / 3 / 4 double-picks per team)
    dp_groups: dict[int, list[int]] = defaultdict(list)
    for i, occs in enumerate(team_occs_list):
        num_doubles = sum(1 for c in Counter(occs).values() if c >= 2)
        dp_groups[num_doubles].append(i)

    double_pick_structure: list[dict[str, Any]] = []
    for k in sorted(dp_groups.keys()):
        idxs = dp_groups[k]
        g_ranks = [ranks[i] for i in idxs]
        label = "0 組雙職業（全 8 異職）" if k == 0 else f"{k} 組雙職業（{8 - k} 種職業）"
        double_pick_structure.append(
            {
                "double_pick_count": k,
                "label": label,
                "team_count": len(idxs),
                "team_rate": round(len(idxs) / max(1, total_teams), 4),
                "avg_rank": round(float(np.mean(g_ranks)), 2),
                "median_rank": round(float(np.median(g_ranks)), 1),
                "best_rank": min(g_ranks),
                "top10_count": len(set(idxs).intersection(top10_set)),
                "low_sample": len(idxs) < 5,
            }
        )

    # 3. Pairwise Synergy & Substitution Matrix (Synergy Lift = P(A∩B) / (P(A)*P(B)))
    occ_presence_map = {r["occupation"]: r["team_presence_rate"] for r in occ_freq_rows}
    occ_order = [r["occupation"] for r in occ_freq_rows]
    n_occ = len(occ_order)
    synergy_matrix = np.ones((n_occ, n_occ), dtype=np.float32)

    pair_team_indices: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, occs in enumerate(team_occs_list):
        uniq = sorted(set(occs))
        for a, b in combinations(uniq, 2):
            pair_team_indices[(a, b)].append(i)

    pair_rows: list[dict[str, Any]] = []
    synergy_pairs: list[dict[str, Any]] = []
    substitution_pairs: list[dict[str, Any]] = []

    for i_idx in range(n_occ):
        for j_idx in range(i_idx + 1, n_occ):
            a, b = occ_order[i_idx], occ_order[j_idx]
            key = (a, b) if a < b else (b, a)
            idxs = pair_team_indices.get(key, [])
            cnt = len(idxs)
            p_ab = cnt / max(1, total_teams)
            p_a = occ_presence_map[a]
            p_b = occ_presence_map[b]
            expected = p_a * p_b
            synergy = round(p_ab / expected, 3) if expected > 0 else 1.0
            synergy_matrix[i_idx, j_idx] = synergy
            synergy_matrix[j_idx, i_idx] = synergy

            if cnt > 0:
                c_ranks = [ranks[k] for k in idxs]
                idx_set = set(idxs)
                t10 = len(idx_set.intersection(top10_set))
                t50 = len(idx_set.intersection(top50_idxs))
                t100 = len(idx_set.intersection(top100_idxs))
                entry = {
                    "combination": f"{a} + {b}",
                    "occ_a": a,
                    "occ_b": b,
                    "team_count": cnt,
                    "team_rate": round(p_ab, 4),
                    "expected_rate": round(expected, 4),
                    "synergy_lift": synergy,
                    "avg_rank": round(float(np.mean(c_ranks)), 2),
                    "best_rank": min(c_ranks),
                    "top10_count": t10,
                    "top10_rate": round(t10 / max(1, len(top10_idxs)), 4) if top10_idxs else 0.0,
                    "top50_rate": round(t50 / max(1, len(top50_idxs)), 4) if top50_idxs else 0.0,
                    "top100_rate": round(t100 / max(1, len(top100_idxs)), 4) if top100_idxs else 0.0,
                    "sample_teams": ", ".join(
                        f"#{sorted_teams[k]['rank']} {sorted_teams[k]['team_name']}" for k in idxs[:4]
                    ),
                }
                pair_rows.append(entry)

                # Filter meaningful synergy/substitution (both classes have at least 4 teams)
                cnt_a = round(p_a * total_teams)
                cnt_b = round(p_b * total_teams)
                if cnt_a >= 4 and cnt_b >= 4:
                    if synergy >= 1.15 and cnt >= 3:
                        synergy_pairs.append(entry)
                    elif synergy <= 0.85:
                        substitution_pairs.append(entry)
            else:
                # Zero co-occurrence between two reasonably common classes is a STRONG substitution!
                cnt_a = round(p_a * total_teams)
                cnt_b = round(p_b * total_teams)
                if cnt_a >= 5 and cnt_b >= 5:
                    substitution_pairs.append(
                        {
                            "combination": f"{a} vs {b}",
                            "occ_a": a,
                            "occ_b": b,
                            "team_count": 0,
                            "team_rate": 0.0,
                            "expected_rate": round(expected, 4),
                            "synergy_lift": 0.0,
                            "avg_rank": 0.0,
                            "best_rank": 0,
                            "top10_count": 0,
                            "top10_rate": 0.0,
                            "top50_rate": 0.0,
                            "top100_rate": 0.0,
                            "sample_teams": "(完全不同隊)",
                        }
                    )

    pair_rows.sort(key=lambda r: (-r["team_count"], r["avg_rank"], r["combination"]))
    synergy_pairs.sort(key=lambda r: (-r["synergy_lift"], r["avg_rank"]))
    substitution_pairs.sort(key=lambda r: (r["synergy_lift"], -r["expected_rate"]))

    # Helper for same-class doubles, triples, and full teams
    def _build_combo_table(combo_extractor, min_count: int = 1, limit: int = 80) -> list[dict[str, Any]]:
        combo_team_indices: dict[str, list[int]] = defaultdict(list)
        for i, occs in enumerate(team_occs_list):
            for key in combo_extractor(occs):
                combo_team_indices[key].append(i)
        rows: list[dict[str, Any]] = []
        for combo_name, idxs in combo_team_indices.items():
            cnt = len(idxs)
            if cnt < min_count:
                continue
            c_ranks = [ranks[i] for i in idxs]
            idx_set = set(idxs)
            t10 = len(idx_set.intersection(top10_set))
            t50 = len(idx_set.intersection(top50_idxs))
            t100 = len(idx_set.intersection(top100_idxs))
            rows.append(
                {
                    "combination": combo_name,
                    "team_count": cnt,
                    "team_rate": round(cnt / max(1, total_teams), 4),
                    "avg_rank": round(float(np.mean(c_ranks)), 2),
                    "best_rank": min(c_ranks),
                    "top10_count": t10,
                    "top10_rate": round(t10 / max(1, len(top10_idxs)), 4) if top10_idxs else 0.0,
                    "top50_rate": round(t50 / max(1, len(top50_idxs)), 4) if top50_idxs else 0.0,
                    "top100_rate": round(t100 / max(1, len(top100_idxs)), 4) if top100_idxs else 0.0,
                    "sample_teams": ", ".join(
                        f"#{sorted_teams[i]['rank']} {sorted_teams[i]['team_name']}" for i in idxs[:4]
                    ),
                }
            )
        rows.sort(key=lambda r: (-r["team_count"], r["avg_rank"], r["combination"]))
        return rows[:limit]

    same_class_doubles = _build_combo_table(
        lambda occs: [f"{o} × 2" for o, cnt in Counter(occs).items() if cnt >= 2],
        min_count=1,
        limit=50,
    )
    unique_triples = _build_combo_table(
        lambda occs: [" + ".join(c) for c in combinations(sorted(set(occs)), 3)],
        min_count=2 if total_teams >= 20 else 1,
        limit=100,
    )
    full_team_combos = _build_combo_table(
        lambda occs: [format_full_team_signature(occs)],
        min_count=1,
        limit=200,
    )

    # 4. Roster Archetypes (3-5 strategic team-building skeletons)
    archetypes = _cluster_roster_archetypes(
        sorted_teams, team_occs_list, all_occ_names, ranks, top10_set
    )

    # 5. Score Tier Distribution (optional reference for current snapshot)
    score_buckets: dict[int, list[int]] = defaultdict(list)
    for i, sc in enumerate(scores):
        if sc is not None:
            score_buckets[int(sc)].append(i)
    score_tiers: list[dict[str, Any]] = []
    for sc in sorted(score_buckets.keys(), reverse=True)[:10]:
        idxs = score_buckets[sc]
        sc_ranks = [ranks[i] for i in idxs]
        top_occs_in_sc = Counter(o for i in idxs for o in set(team_occs_list[i])).most_common(4)
        score_tiers.append(
            {
                "score": sc,
                "team_count": len(idxs),
                "rank_range": f"#{min(sc_ranks)}～#{max(sc_ranks)}",
                "avg_doubles": round(
                    float(np.mean([sum(1 for c in Counter(team_occs_list[i]).values() if c >= 2) for i in idxs])),
                    2,
                ),
                "top_occupations": "、".join(
                    f"{o}({round(c/len(idxs)*100)}%)" for o, c in top_occs_in_sc
                ),
            }
        )

    # Enriched Raw Data
    raw_rows = []
    for t, occs in zip(sorted_teams, team_occs_list):
        padded = list(t.get("occupations", []))
        while len(padded) < 8:
            padded.append("")
        num_doubles = sum(1 for c in Counter(occs).values() if c >= 2)
        rule_ok = all(c <= 2 for c in Counter(occs).values())
        raw_rows.append(
            {
                "rank": int(t["rank"]),
                "team_name": t.get("team_name", ""),
                "score": t.get("score"),
                "occupations": padded[:8],
                "double_pick_count": num_doubles,
                "rule_compliant": rule_ok,
                "full_team_signature": format_full_team_signature(occs),
                "representative_keyframe_id": t.get("representative_keyframe_id"),
                "observation_count": t.get("observation_count", 1),
                "name_conf": t.get("name_conf", 0.0),
                "score_conf": t.get("score_conf", 0.0),
                "status": t.get("status", "verified"),
                "flags": ", ".join(t.get("flags", [])),
            }
        )

    top_tier_highlights = sorted(
        occ_freq_rows,
        key=lambda r: (r["avg_rank"], -r["team_presence_rate"]),
    )

    return {
        "schema_version": 2,
        "report_title": report_title,
        "overview": {
            "total_teams": total_teams,
            "min_rank": min_rank,
            "max_rank": max_rank,
            "overall_avg_rank": overall_avg_rank,
            "total_non_empty_slots": total_non_empty_slots,
            "total_empty_slots": total_empty_slots,
            "distinct_occupations": len(all_occ_names),
            "flagged_teams": sum(1 for t in sorted_teams if t.get("status") == "flagged"),
            "rule_violations_max2": rule_violations,
            "issue_count": len(all_issues),
            "tiers": tier_meta,
        },
        "raw_data": raw_rows,
        "occupation_frequency": occ_freq_rows,
        "double_pick_structure": double_pick_structure,
        "pair_combinations": pair_rows[:100],
        "synergy_pairs": synergy_pairs[:30],
        "substitution_pairs": substitution_pairs[:30],
        "synergy_matrix": {
            "labels": occ_order,
            "values": [[round(float(v), 3) for v in row] for row in synergy_matrix.tolist()],
        },
        "same_class_doubles": same_class_doubles,
        "triple_combinations": unique_triples,
        "full_team_combinations": full_team_combos,
        "roster_archetypes": archetypes,
        "score_tiers": score_tiers,
        "ranking_analysis": {
            "tiers": tier_meta,
            "occupation_tier_comparison": top_tier_highlights,
        },
        "recognition_errors": all_issues,
    }
