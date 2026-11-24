"""Multi-snapshot longitudinal trend analyzer for locked-roster tournaments
(no member changes, max 2 characters per member):
- League Standings anchored on current/latest rank (#1..#200) with rank delta, score velocity (ΔScore),
  8-occupation icons, and alt-character switch detection
- Occupation & Copy-Count (1-copy vs 2-copy) Performance Momentum with <5% low-sample protection
- Double-Pick Structure Shift (0/1/2/3 double-class pairs)
- Cross-Period Score Cutoffs Shift (Top 10/16/32/50/100/200) & Swap-vs-Locked Coach Insights
- Top Climbers / Fallers & Member Alt-Character (2nd character) Switch Flow
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
import re
from typing import Any

import numpy as np

from src.analytics.stats import compute_leaderboard_analytics, format_full_team_signature
from src.icons.clusterer import EMPTY_LABEL

LOW_SAMPLE_RATE = 0.05
LOW_SAMPLE_MIN_COUNT = 5
CUTOFF_MILESTONES = [10, 16, 32, 50, 100, 200]


def default_trend_title() -> str:
    """Return today's MMDD + 女武神聯賽跨期積分榜與趨勢."""
    return f"{datetime.now().strftime('%m%d')}女武神聯賽跨期積分榜與趨勢"


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
    """Match a team to an existing canonical key using exact norm key OR fuzzy name + roster overlap."""
    norm_k = _norm_team_key(raw_name)
    if norm_k in known_keys and curr_snap_idx not in known_keys[norm_k]:
        return norm_k

    best_key = norm_k
    best_score = 0.0

    for cand_key, obs_map in known_keys.items():
        if curr_snap_idx in obs_map:
            continue
        prev_snap = max(obs_map.keys())
        prev_occs = obs_map[prev_snap]["occs"]
        overlap = _roster_overlap_count(occs, prev_occs)

        name_sim = SequenceMatcher(None, norm_k, cand_key).ratio()
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
    trend_title: str = "",
) -> dict[str, Any]:
    """Compare 2+ ordered leaderboard snapshots with Coach-Grade League Standings & Momentum."""
    if len(snapshots) < 2:
        raise ValueError("多期趨勢對比至少需要選擇 2 個分析紀錄")

    clean_title = (trend_title or "").strip()
    if not clean_title or clean_title in (
        "女武神聯賽跨期積分榜與陣容強度趨勢",
        "排位賽多期環境與戰隊趨勢對比",
        "排位賽多期環境與戰隊強度趨勢對比",
    ):
        clean_title = default_trend_title()

    labels: list[str] = []
    snap_meta: list[dict[str, Any]] = []
    snap_analytics: list[dict[str, Any]] = []
    snap_teams: list[list[dict]] = []

    for idx, snap in enumerate(snapshots):
        lbl = str(snap.get("label") or snap.get("run_id") or f"第 {idx+1} 期")
        teams = sorted(snap.get("teams", []), key=lambda t: int(t["rank"]))
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

    n_snaps = len(snapshots)

    # 1. Track every team across snapshots
    team_obs: dict[str, dict[int, dict]] = defaultdict(dict)
    display_names: dict[str, str] = {}

    for s_idx, teams in enumerate(snap_teams):
        for t in teams:
            raw_name = str(t.get("team_name") or "").strip()
            if not raw_name:
                continue
            occs_clean = _clean_occs(t)
            key = _fuzzy_match_team_key(raw_name, occs_clean, team_obs, display_names, s_idx)
            display_names[key] = raw_name
            cnts = Counter(occs_clean)
            team_obs[key][s_idx] = {
                "rank": int(t["rank"]),
                "score": t.get("score"),
                "occs": occs_clean,
                "counts": cnts,
                "double_picks": sorted([k for k, v in cnts.items() if v >= 2]),
                "double_pick_count": sum(1 for v in cnts.values() if v >= 2),
                "signature": format_full_team_signature(occs_clean),
            }

    # Build Team Trajectories & League Standings (anchored on latest rank #1..#N)
    team_trajectories: list[dict[str, Any]] = []
    roster_changes: list[dict[str, Any]] = []
    swap_added_counter: Counter[str] = Counter()
    swap_removed_counter: Counter[str] = Counter()

    for key, obs_by_snap in team_obs.items():
        ranks_s = [obs_by_snap[s]["rank"] if s in obs_by_snap else None for s in range(n_snaps)]
        scores_s = [obs_by_snap[s]["score"] if s in obs_by_snap else None for s in range(n_snaps)]
        present_snaps = sorted(obs_by_snap.keys())
        first_s, last_s = present_snaps[0], present_snaps[-1]
        first_r, last_r = obs_by_snap[first_s]["rank"], obs_by_snap[last_s]["rank"]
        prev_s = present_snaps[-2] if len(present_snaps) >= 2 else first_s
        prev_r = obs_by_snap[prev_s]["rank"]

        net_change = (first_r - last_r) if len(present_snaps) >= 2 else 0
        recent_change = (prev_r - last_r) if len(present_snaps) >= 2 else 0

        first_sc = obs_by_snap[first_s]["score"]
        prev_sc = obs_by_snap[prev_s]["score"]
        last_sc = obs_by_snap[last_s]["score"]
        net_score_delta = (
            int(last_sc) - int(first_sc)
            if (last_sc is not None and first_sc is not None and len(present_snaps) >= 2)
            else None
        )
        recent_score_delta = (
            int(last_sc) - int(prev_sc)
            if (last_sc is not None and prev_sc is not None and len(present_snaps) >= 2)
            else None
        )

        change_notes: list[str] = []
        for idx_p in range(1, len(present_snaps)):
            s_prev = present_snaps[idx_p - 1]
            s_curr = present_snaps[idx_p]
            prev_o = obs_by_snap[s_prev]
            curr_o = obs_by_snap[s_curr]
            removed, added = _diff_rosters(prev_o["occs"], curr_o["occs"])
            if removed or added:
                for x in removed:
                    swap_removed_counter[x] += 1
                for x in added:
                    swap_added_counter[x] += 1
                diff_str = " ".join([*(f"-{x}" for x in removed), *(f"+{x}" for x in added)])
                r_delta = prev_o["rank"] - curr_o["rank"]
                sc_delta = (
                    int(curr_o["score"]) - int(prev_o["score"])
                    if curr_o["score"] is not None and prev_o["score"] is not None
                    else None
                )
                short_prev = labels[s_prev][:6]
                short_curr = labels[s_curr][:6]
                change_notes.append(f"{short_prev}→{short_curr}: {diff_str}")
                roster_changes.append(
                    {
                        "team_name": display_names[key],
                        "from_period": labels[s_prev],
                        "to_period": labels[s_curr],
                        "rank_before": prev_o["rank"],
                        "rank_after": curr_o["rank"],
                        "rank_delta": r_delta,
                        "score_before": prev_o["score"],
                        "score_after": curr_o["score"],
                        "score_delta": sc_delta,
                        "swap_slot_count": max(len(removed), len(added)),
                        "removed": removed,
                        "added": added,
                        "diff_summary": diff_str,
                        "roster_before": prev_o["signature"],
                        "roster_after": curr_o["signature"],
                    }
                )

        if len(present_snaps) == 1 and last_s == n_snaps - 1:
            status = "🆕 新進榜"
        elif (n_snaps - 1) not in obs_by_snap:
            status = "⬇️ 跌出榜外"
        elif recent_change >= 3:
            status = f"▲ +{recent_change}"
        elif recent_change <= -3:
            status = f"▼ {recent_change}"
        elif recent_change > 0:
            status = f"△ +{recent_change}"
        elif recent_change < 0:
            status = f"▽ {recent_change}"
        else:
            status = "➖ 持平"

        latest_obs = obs_by_snap[last_s]
        team_trajectories.append(
            {
                "team_key": key,
                "team_name": display_names[key],
                "appearances": len(present_snaps),
                "rank_series": ranks_s,
                "score_series": scores_s,
                "first_rank": first_r,
                "prev_rank": prev_r if len(present_snaps) >= 2 else None,
                "latest_rank": last_r if (n_snaps - 1) in obs_by_snap else None,
                "best_rank": min(obs_by_snap[s]["rank"] for s in present_snaps),
                "recent_rank_change": recent_change,
                "net_rank_change": net_change,
                "latest_score": last_sc if (n_snaps - 1) in obs_by_snap else None,
                "recent_score_delta": recent_score_delta,
                "net_score_delta": net_score_delta,
                "status": status,
                "double_picks": latest_obs["double_picks"],
                "double_pick_count": latest_obs["double_pick_count"],
                "roster_changed": bool(change_notes),
                "roster_change_notes": "；".join(change_notes) if change_notes else "固定陣容",
                "latest_occs": latest_obs["occs"],
                "latest_roster": latest_obs["signature"],
            }
        )

    team_trajectories.sort(
        key=lambda t: (
            t["latest_rank"] if t["latest_rank"] is not None else 9999,
            t["best_rank"],
        )
    )
    roster_changes.sort(key=lambda c: (-c["rank_delta"], c["rank_after"]))

    league_standings = [t for t in team_trajectories if t["latest_rank"] is not None]
    multi_teams = [t for t in league_standings if t["appearances"] >= 2]
    new_entries_count = sum(1 for t in league_standings if t["appearances"] == 1)
    top_climbers = sorted(multi_teams, key=lambda t: (-t["net_rank_change"], t["latest_rank"]))[:15]
    top_fallers = sorted(multi_teams, key=lambda t: (t["net_rank_change"], -t["latest_rank"]))[:15]

    # 2. Occupation Performance & Strength Momentum across snapshots (with <5% low-sample protection)
    all_occs = sorted(
        {r["occupation"] for an in snap_analytics for r in an.get("occupation_frequency", [])}
    )
    occ_maps = [
        {r["occupation"]: r for r in an.get("occupation_frequency", [])}
        for an in snap_analytics
    ]

    top30_rates_by_snap: list[dict[str, float]] = []
    for teams in snap_teams:
        top30 = [t for t in teams if int(t["rank"]) <= 30]
        denom = max(1, len(top30))
        c30: Counter[str] = Counter()
        for t in top30:
            for o in set(_clean_occs(t)):
                c30[o] += 1
        top30_rates_by_snap.append({occ: round(c30[occ] / denom, 4) for occ in all_occs})

    occupation_trends: list[dict[str, Any]] = []
    for occ in all_occs:
        pres_series = [round(m[occ]["team_presence_rate"], 4) if occ in m else 0.0 for m in occ_maps]
        dp_series = [round(m[occ]["double_pick_rate"], 4) if occ in m else 0.0 for m in occ_maps]
        rank_series = [m[occ]["avg_rank"] if occ in m else None for m in occ_maps]
        cnt_series = [m[occ]["team_count"] if occ in m else 0 for m in occ_maps]
        top30_series = [top30_rates_by_snap[s].get(occ, 0.0) for s in range(n_snaps)]

        c1_teams_series = [
            int(m[occ].get("copy_1", {}).get("teams", 0)) if occ in m else 0
            for m in occ_maps
        ]
        c2_teams_series = [
            int(m[occ].get("copy_2", {}).get("teams", 0)) if occ in m else 0
            for m in occ_maps
        ]
        c1_rank_series = [
            m[occ]["copy_1"]["avg_rank"] if (occ in m and c1_teams_series[i] > 0) else None
            for i, m in enumerate(occ_maps)
        ]
        c2_rank_series = [
            m[occ]["copy_2"]["avg_rank"] if (occ in m and c2_teams_series[i] > 0) else None
            for i, m in enumerate(occ_maps)
        ]

        pres_delta = round(pres_series[-1] - pres_series[0], 4)
        dp_delta = round(dp_series[-1] - dp_series[0], 4)
        top30_delta = round(top30_series[-1] - top30_series[0], 4)
        rank_gain = (
            round(rank_series[0] - rank_series[-1], 2)
            if rank_series[0] is not None and rank_series[-1] is not None
            else None
        )
        c1_gain = (
            round(c1_rank_series[0] - c1_rank_series[-1], 2)
            if c1_rank_series[0] is not None and c1_rank_series[-1] is not None
            else None
        )
        c2_gain = (
            round(c2_rank_series[0] - c2_rank_series[-1], 2)
            if c2_rank_series[0] is not None and c2_rank_series[-1] is not None
            else None
        )

        # Low-sample protection aligned with single-period stats (< 5% presence or < 5 teams in either endpoint)
        is_low_sample = (
            pres_series[-1] < LOW_SAMPLE_RATE
            or pres_series[0] < LOW_SAMPLE_RATE
            or cnt_series[-1] < LOW_SAMPLE_MIN_COUNT
            or cnt_series[0] < LOW_SAMPLE_MIN_COUNT
        )
        c1_low_sample = (c1_teams_series[0] < LOW_SAMPLE_MIN_COUNT) or (c1_teams_series[-1] < LOW_SAMPLE_MIN_COUNT)
        c2_low_sample = (c2_teams_series[0] < LOW_SAMPLE_MIN_COUNT) or (c2_teams_series[-1] < LOW_SAMPLE_MIN_COUNT)

        holders = [t for t in multi_teams if occ in t["latest_occs"]]
        climbers_cnt = sum(1 for t in holders if t["net_rank_change"] > 0)
        fallers_cnt = sum(1 for t in holders if t["net_rank_change"] < 0)
        climber_rate = round(climbers_cnt / len(holders), 4) if holders else 0.0
        sc_deltas = [t["net_score_delta"] for t in holders if t["net_score_delta"] is not None]
        avg_sc_gain = round(float(np.mean(sc_deltas)), 1) if sc_deltas else None

        rg_val = rank_gain if rank_gain is not None else 0.0
        if is_low_sample:
            trend_tag = "⚠️ 樣本偏小 (<5%)"
        elif rg_val >= 2.5 or (rg_val >= 0.5 and top30_delta >= 0.05):
            trend_tag = "🔥 強勢上分"
        elif rg_val <= -2.5 or (rg_val <= -0.5 and top30_delta <= -0.05):
            trend_tag = "🧊 均排下滑"
        else:
            trend_tag = "⚖️ 穩定盤整"

        occupation_trends.append(
            {
                "occupation": occ,
                "low_sample": is_low_sample,
                "copy1_low_sample": c1_low_sample,
                "copy2_low_sample": c2_low_sample,
                "presence_series": pres_series,
                "double_pick_series": dp_series,
                "avg_rank_series": rank_series,
                "team_count_series": cnt_series,
                "top30_presence_series": top30_series,
                "copy1_avg_rank_series": c1_rank_series,
                "copy2_avg_rank_series": c2_rank_series,
                "copy1_teams_series": c1_teams_series,
                "copy2_teams_series": c2_teams_series,
                "first_presence": pres_series[0],
                "latest_presence": pres_series[-1],
                "presence_delta": pres_delta,
                "first_double_rate": dp_series[0],
                "latest_double_rate": dp_series[-1],
                "double_pick_delta": dp_delta,
                "first_top30_presence": top30_series[0],
                "latest_top30_presence": top30_series[-1],
                "top30_presence_delta": top30_delta,
                "first_avg_rank": rank_series[0],
                "latest_avg_rank": rank_series[-1],
                "avg_rank_gain": rank_gain,
                "copy1_rank_gain": c1_gain,
                "copy2_rank_gain": c2_gain,
                "holder_count": len(holders),
                "climber_count": climbers_cnt,
                "faller_count": fallers_cnt,
                "climber_rate": climber_rate,
                "avg_score_gain": avg_sc_gain,
                "trend_tag": trend_tag,
            }
        )

    # Regular-sample classes first (by avg_rank_gain desc, then Top30 delta desc), low-sample classes at bottom
    occupation_trends.sort(
        key=lambda r: (
            1 if r["low_sample"] else 0,
            -(r["avg_rank_gain"] if r["avg_rank_gain"] is not None else -999.0),
            -(r["top30_presence_delta"] or 0.0),
            r["latest_avg_rank"] or 999.0,
        )
    )

    # 3. Double-Pick Structure Shift (0 / 1 / 2 / 3 double-class pairs)
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
        cnt_s = [int(m[k]["team_count"]) if k in m else 0 for m in dp_maps]
        rank_s = [m[k]["avg_rank"] if k in m else None for m in dp_maps]
        r_gain = (
            round(rank_s[0] - rank_s[-1], 2)
            if rank_s[0] is not None and rank_s[-1] is not None
            else None
        )
        dp_low = (rate_s[-1] < LOW_SAMPLE_RATE) or (cnt_s[-1] < LOW_SAMPLE_MIN_COUNT)
        lbl_k = "0 組雙職業（全 8 異職）" if k == 0 else f"{k} 組雙職業"
        double_pick_trends.append(
            {
                "double_pick_count": k,
                "label": lbl_k,
                "low_sample": dp_low,
                "team_count_series": cnt_s,
                "rate_series": rate_s,
                "avg_rank_series": rank_s,
                "rate_delta": round(rate_s[-1] - rate_s[0], 4),
                "avg_rank_gain": r_gain,
            }
        )

    # 4. Cross-Period Score Cutoffs Shift (Top 10 / 16 / 32 / 50 / 100 / 200)
    score_cutoff_trends: list[dict[str, Any]] = []
    for m_rank in CUTOFF_MILESTONES:
        sc_series: list[int | None] = []
        tied_latest = 0
        for s_idx, teams in enumerate(snap_teams):
            scored = [t for t in teams if t.get("score") is not None]
            if len(scored) >= m_rank:
                cut_sc = int(scored[m_rank - 1]["score"])
                sc_series.append(cut_sc)
                if s_idx == n_snaps - 1:
                    tied_latest = sum(1 for t in scored if int(t["score"]) == cut_sc)
            else:
                sc_series.append(None)
        if any(v is not None for v in sc_series):
            sc_delta = (
                int(sc_series[-1]) - int(sc_series[0])
                if sc_series[0] is not None and sc_series[-1] is not None
                else None
            )
            score_cutoff_trends.append(
                {
                    "rank_milestone": m_rank,
                    "label": f"Top {m_rank}",
                    "score_series": sc_series,
                    "first_score": sc_series[0],
                    "latest_score": sc_series[-1],
                    "score_delta": sc_delta,
                    "latest_tied_count": tied_latest,
                }
            )

    # 5. Swap vs Locked Performance Comparison & Alt-Character Swap Flow
    def _group_perf(group: list[dict[str, Any]]) -> dict[str, Any]:
        if not group:
            return {
                "count": 0,
                "avg_rank_change": 0.0,
                "avg_score_gain": None,
                "climber_count": 0,
                "climber_rate": 0.0,
            }
        rc_vals = [t["net_rank_change"] for t in group]
        sc_vals = [t["net_score_delta"] for t in group if t["net_score_delta"] is not None]
        climbers = sum(1 for t in group if t["net_rank_change"] > 0)
        return {
            "count": len(group),
            "avg_rank_change": round(float(np.mean(rc_vals)), 2),
            "avg_score_gain": round(float(np.mean(sc_vals)), 1) if sc_vals else None,
            "climber_count": climbers,
            "climber_rate": round(climbers / len(group), 4),
        }

    locked_group = [t for t in multi_teams if not t["roster_changed"]]
    swapped_group = [t for t in multi_teams if t["roster_changed"]]
    all_sc_deltas = [t["net_score_delta"] for t in multi_teams if t["net_score_delta"] is not None]
    swap_vs_locked = {
        "avg_score_gain_all": round(float(np.mean(all_sc_deltas)), 1) if all_sc_deltas else None,
        "median_score_gain_all": round(float(np.median(all_sc_deltas)), 1) if all_sc_deltas else None,
        "locked": _group_perf(locked_group),
        "swapped": _group_perf(swapped_group),
    }

    swap_occ_flow: list[dict[str, Any]] = []
    for occ in sorted(set(swap_added_counter.keys()) | set(swap_removed_counter.keys())):
        add_c = int(swap_added_counter[occ])
        rem_c = int(swap_removed_counter[occ])
        swap_occ_flow.append(
            {
                "occupation": occ,
                "added_count": add_c,
                "removed_count": rem_c,
                "net_flow": add_c - rem_c,
                "total_activity": add_c + rem_c,
            }
        )
    swap_occ_flow.sort(key=lambda x: (-x["net_flow"], -x["total_activity"], x["occupation"]))

    return {
        "trend_title": clean_title,
        "labels": labels,
        "snapshots": snap_meta,
        "league_standings": league_standings,
        "occupation_trends": occupation_trends,
        "double_pick_trends": double_pick_trends,
        "score_cutoff_trends": score_cutoff_trends,
        "swap_vs_locked": swap_vs_locked,
        "swap_occ_flow": swap_occ_flow,
        "top_climbers": top_climbers,
        "top_fallers": top_fallers,
        "team_trajectories": team_trajectories,
        "roster_changes": roster_changes,
        "summary_counts": {
            "snapshot_count": n_snaps,
            "tracked_teams": len(team_trajectories),
            "active_league_teams": len(league_standings),
            "multi_appear_teams": len(multi_teams),
            "new_entries": new_entries_count,
            "locked_roster_teams": len(locked_group),
            "swapped_roster_teams": len(swapped_group),
            "roster_change_events": len(roster_changes),
        },
    }
