"""Integration tests for Stage 3 (Occupation Icon Clustering & Reusable Template Database)."""

from pathlib import Path

import pytest

from src.pipeline_phase3 import confirm_clusters_and_save_db, run_phase3

VERIFY_RUN_DIR = Path(r"C:\Users\f1991\source\repos\game-leaderboard-analyzer\outputs\stage1_verify")


@pytest.mark.skipif(
    not (VERIFY_RUN_DIR / "phase2_extracted" / "teams_raw.json").is_file(),
    reason="Phase 2 verified run directory not present",
)
def test_phase3_clustering_and_db_reuse(tmp_path: Path) -> None:
    # Use an isolated temporary DB so the real data/icon_db stays pristine during automated tests
    test_db_dir = tmp_path / "icon_db"

    res1 = run_phase3(VERIFY_RUN_DIR, db_dir=test_db_dir)
    assert res1["total_icons"] == 240  # 30 teams x 8 slots
    # Rank 10 slot 7 and Rank 21 slot 7 are known empty slots in the sample video!
    assert res1["empty_slot_count"] == 2
    # Expect clean grouping into ~10-25 distinct occupations
    assert 8 <= res1["cluster_count"] <= 24
    assert Path(res1["clusters_sheet_path"]).is_file()
    assert Path(res1["similarity_heatmap_path"]).is_file()

    # Simulate human confirming cluster names & saving to reusable DB
    name_map = {
        c["cluster_id"]: f"Class_{idx:02d}"
        for idx, c in enumerate(res1["clusters"], start=1)
        if c["cluster_id"] != "EMPTY"
    }
    confirm_clusters_and_save_db(VERIFY_RUN_DIR, name_map, save_to_db=True, db_dir=test_db_dir)

    # Re-run Phase 3 against the now-populated DB: nearly all non-empty icons should auto-match!
    res2 = run_phase3(VERIFY_RUN_DIR, db_dir=test_db_dir)
    non_empty = res2["total_icons"] - res2["empty_slot_count"]
    match_rate = res2["db_matched_count"] / max(1, non_empty)
    assert match_rate >= 0.95, f"Expected >=95% DB auto-match rate, got {match_rate:.2%}"

    # Restore clean non-test Phase 3 run against the real (empty) DB
    run_phase3(VERIFY_RUN_DIR)
