"""Multi-snapshot longitudinal trend analyzer for tracking Meta shifts,
double-pick strategy evolution, team rank trajectories, and roster changes across days/rounds.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from src.analytics.stats import compute_leaderboard_analytics, format_full_team_signature
from src.icons.clusterer import EMPTY_LABEL


def _norm_team_key(name: str) -> str:
    """Normalize team name for resilient cross-day matching."""
    cleaned = re.sub(r"[\s_\-\.]+", "", str(name or "").strip().lower())
    return cleaned or str(name or "").strip()


def _roster_overlap_count(occs_a: list[str], occs_b: list[str]) -> int:
    """Count shared occupations (multiset intersection size, 0..8)."""
    ca, cb = Counter(occs_a), Counter(occs_b)
    return sum(min(ca[k], cb[k]) for k in (ca.keys() & cb.keys()))


def _fuzzy_match_team_key(
    raw_name: str,
    occs: list[str],
    known_keys: dict[str, dict[int, dict]],
    display_names: dict[str, str],
    curr_snap_idx: int,
) -> str:
    """Match a team to an existing canonical key using exact norm key OR fuzzy name + roster overlap.

    Prevents slight cross-week OCR variations (e.g. 'Encore.EXLM' vs 'Encore.EXLI' or 1 Thai
    diacritic difference) from breaking longitudinal team tracking!
    """
    norm_k = _norm_team_key(raw_name)
    if norm_k in known_keys and curr_snap_idx not in known_keys[norm_k]:
        return norm_k

    best_key = norm_k
    best_score = 0.0

    for cand_key, obs_map in known_keys.items():
        if curr_snap_idx in obs_map:
            continue  # Candidate already matched a team in this snapshot
        prev_snap = max(obs_map.keys())
        prev_occs = obs_map[prev_snap]["occs"]
        overlap = _roster_overlap_count(occs, prev_occs)

        name_sim = SequenceMatcher(None, norm_k, cand_key).ratio()
        # Match if:
        # 1. Name is very similar (>= 0.84) and roster shares at least 4/8 classes, OR
        # 2. Name is moderately similar (>= 0.72) and roster shares >= 6/8 classes!
        if (name_sim >= 0.84 and overlap >= 4) or (name_sim >= 0.72 and overlap >= 6):
            combined = name_sim * 0.65 + (overlap / 8.0) * 0.35
            if combined > best_score:
                best_score = combined
                best_key = cand_key

    return best_key


def _clean_occs(team: dict) -> list[str]:
    return [
        o.strip()
        for o in team.get("occupations", [])
        if o and o.strip() and o.strip() != EMPTY_LABEL
    ]


def _diff_rosters(prev_occs: list[str], curr_occs: list[str]) -> tuple[list[str], list[str]]:
    """Compute multiset difference (removed_list, added_list) between two 8-player rosters."""
    c_prev = Counter(prev_occs)
    c_curr = Counter(curr_occs)
    removed: list[str] = []
    added: list[str] = []
    for k in sorted(set(c_prev.keys()) | set(c_curr.keys())):
        diff = c_curr[k] - c_prev[k]
        if diff < 0:
            removed.extend([k] * (-diff))
        elif diff > 0:
            added.extend([k] * diff)
    return removed, added


def compare_multiple_runs(
    snapshots: list[dict[str, Any]],
    trend_title: str = "排位賽多期環境與戰隊趨勢對比",
) -> dict[str, Any]:
    """Compare 2+ ordered leaderboard snapshots (each having run_id, label, teams, optional analytics)."""
    if len(snapshots) < 2:
        raise ValueError("多期趨勢對比至少需要選擇 2 個分析紀錄")

    labels: list[str] = []
    snap_meta: list[dict[str, Any]] = []
    snap_analytics: list[dict[str, Any]] = []
    snap_teams: list[list[dict]] = []

    for idx, snap in enumerate(snapshots):
        lbl = str(snap.get("label") or snap.get("run_id") or f"第 {idx+1} 期")
        teams = snap.get("teams", [])
        an = snap.get("analytics") or compute_leaderboard_analytics(teams, report_title=lbl)
        labels.append(lbl)
        snap_teams.append(teams)
        snap_analytics.append(an)
        ov = an["overview"]
        snap_meta.append(
            {
                "index": idx,
                "run_id": snap.get("run_id", f"run_{idx}"),
                "label": lbl,
                "total_teams": ov["total_teams"],
                "rank_range": f"#{ov['min_rank']}～#{ov['max_rank']}",
                "distinct_occupations": ov["distinct_occupations"],
            }
        )

    # 1. Occupation Meta Shift across snapshots
    all_occs = sorted(
        {r["occupation"] for an in snap_analytics for r in an.get("occupation_frequency", [])}
    )
    occ_maps = [
        {r["occupation"]: r for r in an.get("occupation_frequency", [])}
        for an in snap_analytics
    ]

    occupation_trends: list[dict[str, Any]] = []
    for occ in all_occs:
        pres_series = [round(m[occ]["team_presence_rate"], 4) if occ in m else 0.0 for m in occ_maps]
        dp_series = [round(m[occ]["double_pick_rate"], 4) if occ in m else 0.0 for m in occ_maps]
        rank_series = [m[occ]["avg_rank"] if occ in m else None for m in occ_maps]
        cnt_series = [m[occ]["team_count"] if occ in m else 0 for m in occ_maps]

        pres_delta = round(pres_series[-1] - pres_series[0], 4)
        dp_delta = round(dp_series[-1] - dp_series[0], 4)
        rank_gain = (
            round(rank_series[0] - rank_series[-1], 2)
            if rank_series[0] is not None and rank_series[-1] is not None
            else None
        )

        if pres_delta >= 0.05:
            trend_tag = "📈 明顯崛起"
        elif pres_delta <= -0.05:
            trend_tag = "📉 明顯衰退"
        else:
            trend_tag = "➖ 穩定盤整"

        occupation_trends.append(
            {
                "occupation": occ,
                "presence_series": pres_series,
                "double_pick_series": dp_series,
                "avg_rank_series": rank_series,
                "team_count_series": cnt_series,
                "first_presence": pres_series[0],
                "latest_presence": pres_series[-1],
                "presence_delta": pres_delta,
                "first_double_rate": dp_series[0],
                "latest_double_rate": dp_series[-1],
                "double_pick_delta": dp_delta,
                "first_avg_rank": rank_series[0],
                "latest_avg_rank": rank_series[-1],
                "avg_rank_gain": rank_gain,
                "trend_tag": trend_tag,
            }
        )

    occupation_trends.sort(key=lambda r: (-r["presence_delta"], -r["latest_presence"], r["occupation"]))

    # 2. Double-Pick Strategy Shift across snapshots
    all_dp_k = sorted(
        {d["double_pick_count"] for an in snap_analytics for d in an.get("double_pick_structure", [])}
    )
    dp_maps = [
        {d["double_pick_count"]: d for d in an.get("double_pick_structure", [])}
        for an in snap_analytics
    ]
    double_pick_trends: list[dict[str, Any]] = []
    for k in all_dp_k:
        rate_s = [round(m[k]["team_rate"], 4) if k in m else 0.0 for m in dp_maps]
        rank_s = [m[k]["avg_rank"] if k in m else None for m in dp_maps]
        lbl_k = "0 雙開（全 8 異職）" if k == 0 else f"{k} 組雙開"
        double_pick_trends.append(
            {
                "double_pick_count": k,
                "label": lbl_k,
                "rate_series": rate_s,
                "avg_rank_series": rank_s,
                "rate_delta": round(rate_s[-1] - rate_s[0], 4),
            }
        )

    # 3. Team Rank Trajectory & Roster Change Detector
    team_obs: dict[str, dict[int, dict]] = defaultdict(dict)
    display_names: dict[str, str] = {}

    for s_idx, teams in enumerate(snap_teams):
        for t in teams:
            raw_name = str(t.get("team_name") or "").strip()
            if not raw_name:
                continue
            occs_clean = _clean_occs(t)
            key = _fuzzy_match_team_key(raw_name, occs_clean, team_obs, display_names, s_idx)
            # Keep the highest-rank or latest clean display name
            display_names[key] = raw_name
            team_obs[key][s_idx] = {
                "rank": int(t["rank"]),
                "score": t.get("score"),
                "occs": occs_clean,
                "signature": format_full_team_signature(occs_clean),
            }

    n_snaps = len(snapshots)
    team_trajectories: list[dict[str, Any]] = []
    roster_changes: list[dict[str, Any]] = []

    for key, obs_by_snap in team_obs.items():
        ranks_s = [obs_by_snap[s]["rank"] if s in obs_by_snap else None for s in range(n_snaps)]
        present_snaps = sorted(obs_by_snap.keys())
        first_s, last_s = present_snaps[0], present_snaps[-1]
        first_r, last_r = obs_by_snap[first_s]["rank"], obs_by_snap[last_s]["rank"]
        # Positive rank_change = climbed UP in ranking!
        net_change = (first_r - last_r) if len(present_snaps) >= 2 else 0

        change_notes: list[str] = []
        for idx_p in range(1, len(present_snaps)):
            s_prev = present_snaps[idx_p - 1]
            s_curr = present_snaps[idx_p]
            prev_o = obs_by_snap[s_prev]
            curr_o = obs_by_snap[s_curr]
            removed, added = _diff_rosters(prev_o["occs"], curr_o["occs"])
            if removed or added:
                diff_str = " ".join([*(f"-{x}" for x in removed), *(f"+{x}" for x in added)])
                r_delta = prev_o["rank"] - curr_o["rank"]
                change_notes.append(f"{labels[s_prev]}→{labels[s_curr]}: {diff_str}")
                roster_changes.append(
                    {
                        "team_name": display_names[key],
                        "from_period": labels[s_prev],
                        "to_period": labels[s_curr],
                        "rank_before": prev_o["rank"],
                        "rank_after": curr_o["rank"],
                        "rank_delta": r_delta,
                        "removed": removed,
                        "added": added,
                        "diff_summary": diff_str,
                        "roster_before": prev_o["signature"],
                        "roster_after": curr_o["signature"],
                    }
                )

        if len(present_snaps) == 1 and last_s == n_snaps - 1:
            status = "🆕 新進榜"
        elif len(present_snaps) == 1 and first_s == 0:
            status = "⬇️ 跌出榜外"
        elif net_change >= 3:
            status = f"🚀 上升 +{net_change}"
        elif net_change <= -3:
            status = f"🔻 下降 {net_change}"
        else:
            status = "➖ 持平"

        team_trajectories.append(
            {
                "team_name": display_names[key],
                "appearances": len(present_snaps),
                "rank_series": ranks_s,
                "first_rank": first_r,
                "latest_rank": last_r if (n_snaps - 1) in obs_by_snap else None,
                "best_rank": min(obs_by_snap[s]["rank"] for s in present_snaps),
                "net_rank_change": net_change,
                "status": status,
                "roster_changed": bool(change_notes),
                "roster_change_notes": "；".join(change_notes),
                "latest_roster": obs_by_snap[last_s]["signature"],
            }
        )

    team_trajectories.sort(
        key=lambda t: (
            t["latest_rank"] if t["latest_rank"] is not None else 9999,
            t["best_rank"],
        )
    )
    roster_changes.sort(key=lambda c: (-c["rank_delta"], c["rank_after"]))

    return {
        "trend_title": trend_title,
        "labels": labels,
        "snapshots": snap_meta,
        "occupation_trends": occupation_trends,
        "double_pick_trends": double_pick_trends,
        "team_trajectories": team_trajectories,
        "roster_changes": roster_changes,
        "summary_counts": {
            "snapshot_count": n_snaps,
            "tracked_teams": len(team_trajectories),
            "multi_appear_teams": sum(1 for t in team_trajectories if t["appearances"] >= 2),
            "roster_change_events": len(roster_changes),
        },
    }
