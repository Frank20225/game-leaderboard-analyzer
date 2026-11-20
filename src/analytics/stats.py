"""Phase 4 statistical engine: dual-metric occupation frequency, pair/triple/full-team
combinations, Top 10/50/100 tier comparisons, Lift, and Spearman rank correlation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from src.icons.clusterer import EMPTY_LABEL


def _clean_team_occs(team: dict) -> list[str]:
    """Return valid non-empty occupation labels for a team."""
    return [o.strip() for o in team.get("occupations", []) if o and o.strip() and o.strip() != EMPTY_LABEL]


def format_full_team_signature(occs: list[str]) -> str:
    """Canonical multiset signature sorted by multiplicity desc then name asc (order-invariant)."""
    if not occs:
        return "(無資料)"
    counts = Counter(occs)
    parts = []
    for name, cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        parts.append(f"{name}×{cnt}" if cnt > 1 else name)
    return " + ".join(parts)


def compute_leaderboard_analytics(
    teams: list[dict],
    issues: list[dict] | None = None,
    report_title: str = "排位賽職業環境分析報告",
) -> dict[str, Any]:
    """Compute complete Phase 4 analytics bundle from deduplicated teams with occupation labels."""
    sorted_teams = sorted(teams, key=lambda t: int(t["rank"]))
    total_teams = len(sorted_teams)
    all_issues = issues or []

    ranks = [int(t["rank"]) for t in sorted_teams]
    min_rank = min(ranks) if ranks else None
    max_rank = max(ranks) if ranks else None

    team_occs_list = [_clean_team_occs(t) for t in sorted_teams]
    total_non_empty_slots = sum(len(o) for o in team_occs_list)
    total_empty_slots = sum(
        sum(1 for raw in t.get("occupations", []) if not raw or raw.strip() == EMPTY_LABEL)
        for t in sorted_teams
    )

    # Tier definitions
    tiers = [
        ("Top 10", 1, 10),
        ("Top 50", 1, 50),
        ("Top 100", 1, 100),
        ("101+", 101, 9999),
    ]
    tier_team_indices: dict[str, list[int]] = {}
    tier_meta: list[dict] = []
    for label, r_lo, r_hi in tiers:
        idxs = [i for i, t in enumerate(sorted_teams) if r_lo <= int(t["rank"]) <= r_hi]
        tier_team_indices[label] = idxs
        tier_meta.append(
            {
                "tier": label,
                "rank_min": r_lo,
                "rank_max": r_hi if r_hi < 9999 else (max_rank or 0),
                "team_count": len(idxs),
                "is_full_coverage": (
                    len(idxs) == (r_hi - r_lo + 1) if r_hi < 9999 else len(idxs) > 0
                ),
            }
        )

    # 1. Occupation Frequency (dual metrics: slot share + team presence rate)
    all_occ_names = sorted({o for occs in team_occs_list for o in occs})
    occ_freq_rows: list[dict[str, Any]] = []

    ranks_arr = np.array(ranks, dtype=np.float64) if ranks else np.array([])

    for occ in all_occ_names:
        per_team_counts = [occs.count(occ) for occs in team_occs_list]
        slot_count = sum(per_team_counts)
        carrying_indices = [i for i, c in enumerate(per_team_counts) if c > 0]
        team_count = len(carrying_indices)
        multi_copy_teams = sum(1 for c in per_team_counts if c >= 2)
        carrying_ranks = [ranks[i] for i in carrying_indices]

        slot_rate = slot_count / max(1, total_non_empty_slots)
        team_rate = team_count / max(1, total_teams)
        avg_per_carrying = slot_count / max(1, team_count)

        # Tier presence rates
        tier_rates: dict[str, float] = {}
        for label, _, _ in tiers:
            t_idxs = tier_team_indices[label]
            if t_idxs:
                t_carry = sum(1 for i in t_idxs if per_team_counts[i] > 0)
                tier_rates[label] = round(t_carry / len(t_idxs), 4)
            else:
                tier_rates[label] = 0.0

        # Lift: compare Top 50 (if >=50 teams) or Top 10 against overall presence rate
        ref_tier = "Top 50" if len(tier_team_indices["Top 50"]) >= 50 else "Top 10"
        ref_rate = tier_rates[ref_tier]
        lift = round(ref_rate / team_rate, 3) if team_rate > 0 else 0.0

        # Spearman rank correlation between per-team copy count and numeric rank
        # Negative correlation = more copies -> smaller rank number -> HIGHER ranking!
        if total_teams >= 5 and len(set(per_team_counts)) > 1:
            rho, pval = spearmanr(per_team_counts, ranks_arr)
            rho_val = 0.0 if np.isnan(rho) else round(float(rho), 4)
            pval_val = 1.0 if np.isnan(pval) else round(float(pval), 4)
        else:
            rho_val, pval_val = 0.0, 1.0

        occ_freq_rows.append(
            {
                "occupation": occ,
                "slot_count": slot_count,
                "slot_rate": round(slot_rate, 4),
                "team_count": team_count,
                "team_presence_rate": round(team_rate, 4),
                "avg_per_carrying_team": round(avg_per_carrying, 2),
                "multi_copy_teams": multi_copy_teams,
                "avg_rank": round(float(np.mean(carrying_ranks)), 2) if carrying_ranks else 0.0,
                "median_rank": round(float(np.median(carrying_ranks)), 1) if carrying_ranks else 0.0,
                "best_rank": min(carrying_ranks) if carrying_ranks else 0,
                "top10_rate": tier_rates["Top 10"],
                "top50_rate": tier_rates["Top 50"],
                "top100_rate": tier_rates["Top 100"],
                "rank101_plus_rate": tier_rates["101+"],
                "lift_ref_tier": ref_tier,
                "top_tier_lift": lift,
                "spearman_r": rho_val,
                "spearman_p": pval_val,
            }
        )

    occ_freq_rows.sort(key=lambda r: (-r["slot_count"], -r["team_count"], r["occupation"]))

    # Helper to compute combination stats (unique k-combos & same-class k-duplicates)
    def _build_combo_table(
        combo_extractor,
        min_count: int = 1,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
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
            t10 = len(idx_set.intersection(tier_team_indices["Top 10"]))
            t50 = len(idx_set.intersection(tier_team_indices["Top 50"]))
            t100 = len(idx_set.intersection(tier_team_indices["Top 100"]))
            rows.append(
                {
                    "combination": combo_name,
                    "team_count": cnt,
                    "team_rate": round(cnt / max(1, total_teams), 4),
                    "avg_rank": round(float(np.mean(c_ranks)), 2),
                    "best_rank": min(c_ranks),
                    "top10_count": t10,
                    "top10_rate": round(t10 / max(1, len(tier_team_indices["Top 10"])), 4) if tier_team_indices["Top 10"] else 0.0,
                    "top50_count": t50,
                    "top50_rate": round(t50 / max(1, len(tier_team_indices["Top 50"])), 4) if tier_team_indices["Top 50"] else 0.0,
                    "top100_count": t100,
                    "top100_rate": round(t100 / max(1, len(tier_team_indices["Top 100"])), 4) if tier_team_indices["Top 100"] else 0.0,
                    "sample_teams": ", ".join(
                        f"#{sorted_teams[i]['rank']} {sorted_teams[i]['team_name']}" for i in idxs[:4]
                    ),
                }
            )
        rows.sort(key=lambda r: (-r["team_count"], r["avg_rank"], r["combination"]))
        return rows[:limit]

    # 2. Pair Combinations (deduplicated per team) + Same-Class Doubles (A x 2+)
    unique_pairs = _build_combo_table(
        lambda occs: [" + ".join(c) for c in combinations(sorted(set(occs)), 2)],
        min_count=2 if total_teams >= 20 else 1,
        limit=100,
    )
    same_class_doubles = _build_combo_table(
        lambda occs: [f"{o} × 2+" for o, cnt in Counter(occs).items() if cnt >= 2],
        min_count=1,
        limit=50,
    )

    # 3. Triple Combinations (deduplicated per team) + Same-Class Triples (A x 3+)
    unique_triples = _build_combo_table(
        lambda occs: [" + ".join(c) for c in combinations(sorted(set(occs)), 3)],
        min_count=2 if total_teams >= 20 else 1,
        limit=100,
    )
    same_class_triples = _build_combo_table(
        lambda occs: [f"{o} × 3+" for o, cnt in Counter(occs).items() if cnt >= 3],
        min_count=1,
        limit=50,
    )

    # 4. Full 8-Occupation Team Combinations (canonical multiset)
    full_team_combos = _build_combo_table(
        lambda occs: [format_full_team_signature(occs)],
        min_count=1,
        limit=200,
    )

    # 5. Ranking Tier Analysis & Highlights
    # Sort occupations by preference in Top 10 vs Overall
    top_tier_highlights = sorted(
        occ_freq_rows,
        key=lambda r: (r["top10_rate"] - r["team_presence_rate"], -r["avg_rank"]),
        reverse=True,
    )

    # Enrich raw data rows with canonical full team string
    raw_rows = []
    for t, occs in zip(sorted_teams, team_occs_list):
        padded = list(t.get("occupations", []))
        while len(padded) < 8:
            padded.append("")
        raw_rows.append(
            {
                "rank": int(t["rank"]),
                "team_name": t.get("team_name", ""),
                "score": t.get("score"),
                "occupations": padded[:8],
                "full_team_signature": format_full_team_signature(occs),
                "representative_keyframe_id": t.get("representative_keyframe_id"),
                "observation_count": t.get("observation_count", 1),
                "name_conf": t.get("name_conf", 0.0),
                "score_conf": t.get("score_conf", 0.0),
                "status": t.get("status", "verified"),
                "flags": ", ".join(t.get("flags", [])),
            }
        )

    return {
        "report_title": report_title,
        "overview": {
            "total_teams": total_teams,
            "min_rank": min_rank,
            "max_rank": max_rank,
            "total_non_empty_slots": total_non_empty_slots,
            "total_empty_slots": total_empty_slots,
            "distinct_occupations": len(all_occ_names),
            "flagged_teams": sum(1 for t in sorted_teams if t.get("status") == "flagged"),
            "issue_count": len(all_issues),
            "tiers": tier_meta,
        },
        "raw_data": raw_rows,
        "occupation_frequency": occ_freq_rows,
        "pair_combinations": unique_pairs,
        "same_class_doubles": same_class_doubles,
        "triple_combinations": unique_triples,
        "same_class_triples": same_class_triples,
        "full_team_combinations": full_team_combos,
        "ranking_analysis": {
            "tiers": tier_meta,
            "occupation_tier_comparison": top_tier_highlights,
            "top_pairs_in_top10": [p for p in unique_pairs if p["top10_count"] > 0][:15],
            "top_triples_in_top10": [p for p in unique_triples if p["top10_count"] > 0][:15],
        },
        "recognition_errors": all_issues,
    }
