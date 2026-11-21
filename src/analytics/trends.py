"""Multi-snapshot longitudinal trend analyzer for locked-roster tournaments
(no member changes, max 2 characters per member):
- League Standings anchored on current/latest rank (#1..#200) with rank delta, score velocity (ΔScore),
  8-occupation icons, and archetype classification
- Roster Archetype / Lineup System Strength Momentum (avg rank shift, Top 30 seat shift, score gain, climber rate)
- Occupation & Copy-Count (1-copy vs 2-copy) Performance Momentum (avg rank gain, Top 30 penetration shift, score gain)
- Top Climbers / Fallers & Member Alt-Character (2nd character) Switch Detection
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

import numpy as np

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

    Under the tournament rule (locked members, max 2 characters per member), a team's 8-player
    roster usually keeps 6~8 identical occupations across weeks. Combining name similarity with
    roster multiset overlap ensures 100% reliable tracking even with OCR jitter.
    """
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


def classify_team_lineup_tags(occs: list[str]) -> tuple[str, list[str]]:
    """Return (primary_archetype_label, all_matching_system_labels) for an 8-player roster.

    Every occupation is treated independently (never merging same-colored icons), reflecting verified
    Valkyrie Cup mechanics:
    - 法師×2: Cross-game control rotation (1 in G1->G4, 1 in G3), NOT same-game double mage
    - 詩人×2: Cross-game support rotation or 1 Support + 1 DPS build
    - 德魯伊: Top 5v5 large-AOE & control threat
    - 賢者 / 流氓 / 騎士 / 武僧: Top 4 G2 1v1 duelists & single-target burst
    - 補師×2: Guarantees a healer in G4 (2v2) despite opponent's G3 healer ban
    """
    counts = Counter(occs)
    dp_count = sum(1 for v in counts.values() if v >= 2)
    matched: list[str] = []

    if counts.get("法師", 0) >= 2:
        matched.append("🔥 雙法師跨局控場體系 (法師×2)")
    if counts.get("詩人", 0) >= 2:
        matched.append("🎵 雙詩人雙流派輪轉體系 (詩人×2)")
    if dp_count == 0 and len(occs) >= 7:
        matched.append("👑 8異職全能體系 (0雙開)")
    if counts.get("德魯伊", 0) >= 1:
        matched.append("🌿 德魯伊5v5團戰AOE體系")
    if counts.get("賢者", 0) >= 2 or counts.get("流氓", 0) >= 2:
        matched.append("⚡ 雙賢者/雙流氓單挑分攤體系")
    if counts.get("補師", 0) >= 2:
        matched.append("💉 雙補師2v2保底有補體系 (補師×2)")
    if counts.get("煉金", 0) >= 1:
        matched.append("⚗️ 煉金護貝防拆裝體系")
    if counts.get("舞孃", 0) == 1:
        matched.append("💃 單帶舞孃體系 (舞孃×1)")

    if counts.get("法師", 0) >= 2:
        primary = "🔥 雙法跨局控場陣"
    elif counts.get("詩人", 0) >= 2:
        primary = "🎵 雙詩雙流派陣"
    elif counts.get("補師", 0) >= 2:
        primary = "💉 雙補2v2保底陣"
    elif dp_count == 0 and len(occs) >= 7:
        primary = "👑 8異職全能陣"
    elif counts.get("賢者", 0) >= 2 or counts.get("流氓", 0) >= 2:
        primary = "⚡ 雙單挑主力陣"
    elif counts.get("德魯伊", 0) >= 1:
        primary = "🌿 德魯伊團戰陣"
    elif counts.get("舞孃", 0) == 1:
        primary = "💃 單舞配置陣"
    else:
        primary = f"⚖️ {dp_count}雙開輪轉陣"

    return primary, matched


LINEUP_SYSTEM_CATALOG = [
    "🔥 雙法師跨局控場體系 (法師×2)",
    "🎵 雙詩人雙流派輪轉體系 (詩人×2)",
    "👑 8異職全能體系 (0雙開)",
    "🌿 德魯伊5v5團戰AOE體系",
    "⚡ 雙賢者/雙流氓單挑分攤體系",
    "⚗️ 煉金護貝防拆裝體系",
    "💉 雙補師2v2保底有補體系 (補師×2)",
    "💃 單帶舞孃體系 (舞孃×1)",
]


def compare_multiple_runs(
    snapshots: list[dict[str, Any]],
    trend_title: str = "排位賽多期環境與戰隊強度趨勢對比",
) -> dict[str, Any]:
    """Compare 2+ ordered leaderboard snapshots with League Standings & Roster Strength Momentum."""
    if len(snapshots) < 2:
        raise ValueError("多期趨勢對比至少需要選擇 2 個分析紀錄")

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

    # 1. Track every team across snapshots first (so we can compute per-team rank & score velocity)
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
            primary_arch, system_tags = classify_team_lineup_tags(occs_clean)
            cnts = Counter(occs_clean)
            team_obs[key][s_idx] = {
                "rank": int(t["rank"]),
                "score": t.get("score"),
                "occs": occs_clean,
                "counts": cnts,
                "double_picks": sorted([k for k, v in cnts.items() if v >= 2]),
                "double_pick_count": sum(1 for v in cnts.values() if v >= 2),
                "signature": format_full_team_signature(occs_clean),
                "primary_archetype": primary_arch,
                "system_tags": system_tags,
            }

    # Build Team Trajectories & League Standings (anchored on latest rank #1..#N)
    team_trajectories: list[dict[str, Any]] = []
    roster_changes: list[dict[str, Any]] = []

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
        net_score_delta = (int(last_sc) - int(first_sc)) if (last_sc is not None and first_sc is not None and len(present_snaps) >= 2) else None
        recent_score_delta = (int(last_sc) - int(prev_sc)) if (last_sc is not None and prev_sc is not None and len(present_snaps) >= 2) else None

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
                sc_delta = (
                    int(curr_o["score"]) - int(prev_o["score"])
                    if curr_o["score"] is not None and prev_o["score"] is not None
                    else None
                )
                change_notes.append(f"{labels[s_prev]}→{labels[s_curr]}: {diff_str}")
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
                "archetype_tag": latest_obs["primary_archetype"],
                "system_tags": latest_obs["system_tags"],
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

    # League Standings: strictly the active teams in the latest snapshot (#1..#N)
    league_standings = [t for t in team_trajectories if t["latest_rank"] is not None]

    # Top Climbers & Top Fallers (among teams present in >= 2 snapshots)
    multi_teams = [t for t in league_standings if t["appearances"] >= 2]
    top_climbers = sorted(multi_teams, key=lambda t: (-t["net_rank_change"], t["latest_rank"]))[:15]
    top_fallers = sorted(multi_teams, key=lambda t: (t["net_rank_change"], -t["latest_rank"]))[:15]

    # 2. Occupation Performance & Strength Momentum across snapshots
    # Crucial for locked-roster tournaments: even when presence_delta == 0, avg_rank_gain,
    # top30_presence_delta, copy1 vs copy2 rank gain, and climber_rate reveal which classes are winning!
    all_occs = sorted(
        {r["occupation"] for an in snap_analytics for r in an.get("occupation_frequency", [])}
    )
    occ_maps = [
        {r["occupation"]: r for r in an.get("occupation_frequency", [])}
        for an in snap_analytics
    ]

    # Precompute Top 30 presence rate per occupation for each snapshot
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

        c1_rank_series = [
            m[occ]["copy_1"]["avg_rank"] if (occ in m and m[occ].get("copy_1", {}).get("teams", 0) > 0) else None
            for m in occ_maps
        ]
        c2_rank_series = [
            m[occ]["copy_2"]["avg_rank"] if (occ in m and m[occ].get("copy_2", {}).get("teams", 0) > 0) else None
            for m in occ_maps
        ]

        pres_delta = round(pres_series[-1] - pres_series[0], 4)
        dp_delta = round(dp_series[-1] - dp_series[0], 4)
        top30_delta = round(top30_series[-1] - top30_series[0], 4)
        rank_gain = (
            round(rank_series[0] - rank_series[-1], 2)
            if rank_series[0] is not None and rank_series[-1] is not None
            else 0.0
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

        # Compute actual climber rate & average score gain among teams currently carrying this occupation
        holders = [t for t in multi_teams if occ in t["latest_occs"]]
        climbers_cnt = sum(1 for t in holders if t["net_rank_change"] > 0)
        fallers_cnt = sum(1 for t in holders if t["net_rank_change"] < 0)
        climber_rate = round(climbers_cnt / len(holders), 4) if holders else 0.0
        sc_deltas = [t["net_score_delta"] for t in holders if t["net_score_delta"] is not None]
        avg_sc_gain = round(float(np.mean(sc_deltas)), 1) if sc_deltas else None

        # Strength tag combines avg_rank_gain, top30 penetration shift, and presence shift
        if rank_gain >= 2.5 or top30_delta >= 0.05 or pres_delta >= 0.04:
            trend_tag = "🔥 強勢上分"
        elif rank_gain <= -2.5 or top30_delta <= -0.05 or pres_delta <= -0.04:
            trend_tag = "🧊 排名退化"
        else:
            trend_tag = "⚖️ 穩定盤整"

        occupation_trends.append(
            {
                "occupation": occ,
                "presence_series": pres_series,
                "double_pick_series": dp_series,
                "avg_rank_series": rank_series,
                "team_count_series": cnt_series,
                "top30_presence_series": top30_series,
                "copy1_avg_rank_series": c1_rank_series,
                "copy2_avg_rank_series": c2_rank_series,
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

    # Sort occupation trends by strength momentum (avg_rank_gain + top30_delta + presence_delta)
    occupation_trends.sort(
        key=lambda r: (
            -(r["avg_rank_gain"] or 0.0) - (r["top30_presence_delta"] * 100.0) - (r["presence_delta"] * 100.0),
            r["latest_avg_rank"] or 999.0,
        )
    )

    # 3. Roster Archetype / Lineup System Strength Trends across snapshots
    # Tracks how each of the 8 major team-building systems performs over time even if nobody swaps characters!
    roster_strength_trends: list[dict[str, Any]] = []
    for sys_name in LINEUP_SYSTEM_CATALOG:
        cnt_s: list[int] = []
        avg_r_s: list[float | None] = []
        top30_s: list[int] = []
        top10_s: list[int] = []

        for s_idx in range(n_snaps):
            matched_ranks = [
                obs_by_snap[s_idx]["rank"]
                for obs_by_snap in team_obs.values()
                if s_idx in obs_by_snap and sys_name in obs_by_snap[s_idx]["system_tags"]
            ]
            cnt_s.append(len(matched_ranks))
            avg_r_s.append(round(float(np.mean(matched_ranks)), 2) if matched_ranks else None)
            top30_s.append(sum(1 for r in matched_ranks if r <= 30))
            top10_s.append(sum(1 for r in matched_ranks if r <= 10))

        if max(cnt_s, default=0) == 0:
            continue

        sys_holders = [t for t in multi_teams if sys_name in t["system_tags"]]
        sys_climbers = sum(1 for t in sys_holders if t["net_rank_change"] > 0)
        sys_climber_rate = round(sys_climbers / len(sys_holders), 4) if sys_holders else 0.0
        sys_net_changes = [t["net_rank_change"] for t in sys_holders]
        avg_net_climb = round(float(np.mean(sys_net_changes)), 2) if sys_net_changes else 0.0
        sys_sc_deltas = [t["net_score_delta"] for t in sys_holders if t["net_score_delta"] is not None]
        sys_avg_sc_gain = round(float(np.mean(sys_sc_deltas)), 1) if sys_sc_deltas else None

        r_gain = (
            round(avg_r_s[0] - avg_r_s[-1], 2)
            if avg_r_s[0] is not None and avg_r_s[-1] is not None
            else avg_net_climb
        )
        top30_delta = top30_s[-1] - top30_s[0]

        if r_gain >= 2.0 or sys_climber_rate >= 0.58 or top30_delta >= 2:
            verdict = "🚀 強勢上分體系"
        elif r_gain <= -2.0 or (sys_holders and sys_climber_rate <= 0.38) or top30_delta <= -2:
            verdict = "⚠️ 排名退化體系"
        else:
            verdict = "⚖️ 穩定中堅體系"

        best_reps = sorted(
            [t for t in league_standings if sys_name in t["system_tags"]],
            key=lambda t: t["latest_rank"],
        )[:3]

        roster_strength_trends.append(
            {
                "system_name": sys_name,
                "team_count_series": cnt_s,
                "latest_team_count": cnt_s[-1],
                "avg_rank_series": avg_r_s,
                "first_avg_rank": avg_r_s[0],
                "latest_avg_rank": avg_r_s[-1],
                "avg_rank_gain": r_gain,
                "avg_team_climb": avg_net_climb,
                "top30_series": top30_s,
                "top30_delta": top30_delta,
                "top10_series": top10_s,
                "top10_delta": top10_s[-1] - top10_s[0],
                "climber_count": sys_climbers,
                "climber_rate": sys_climber_rate,
                "avg_score_gain": sys_avg_sc_gain,
                "verdict": verdict,
                "sample_teams": ", ".join(f"#{t['latest_rank']} {t['team_name']}" for t in best_reps),
            }
        )

    roster_strength_trends.sort(
        key=lambda x: (-x["avg_rank_gain"], x["latest_avg_rank"] or 999.0)
    )

    # 4. Double-Pick Strategy Shift (with Avg Rank performance across periods!)
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
        r_gain = (
            round(rank_s[0] - rank_s[-1], 2)
            if rank_s[0] is not None and rank_s[-1] is not None
            else None
        )
        lbl_k = "0 雙開（全 8 異職）" if k == 0 else f"{k} 組雙開"
        double_pick_trends.append(
            {
                "double_pick_count": k,
                "label": lbl_k,
                "rate_series": rate_s,
                "avg_rank_series": rank_s,
                "rate_delta": round(rate_s[-1] - rate_s[0], 4),
                "avg_rank_gain": r_gain,
            }
        )

    return {
        "trend_title": trend_title,
        "labels": labels,
        "snapshots": snap_meta,
        "league_standings": league_standings,
        "roster_strength_trends": roster_strength_trends,
        "occupation_trends": occupation_trends,
        "double_pick_trends": double_pick_trends,
        "top_climbers": top_climbers,
        "top_fallers": top_fallers,
        "team_trajectories": team_trajectories,
        "roster_changes": roster_changes,
        "summary_counts": {
            "snapshot_count": n_snaps,
            "tracked_teams": len(team_trajectories),
            "active_league_teams": len(league_standings),
            "multi_appear_teams": len(multi_teams),
            "locked_roster_teams": sum(1 for t in multi_teams if not t["roster_changed"]),
            "roster_change_events": len(roster_changes),
        },
    }
