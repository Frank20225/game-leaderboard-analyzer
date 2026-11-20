"""Integration tests for Stage 3 (Occupation Icon Clustering & Reusable Template Database)."""

import shutil
from pathlib import Path

import pytest

from src.pipeline_phase3 import confirm_clusters_and_save_db, run_phase3

VERIFY_RUN_DIR = Path(r"C:\Users\f1991\source\repos\game-leaderboard-analyzer\outputs\stage1_verify")


@pytest.mark.skipif(
    not (VERIFY_RUN_DIR / "phase2_extracted" / "teams_raw.json").is_file(),
    reason="Phase 2 verified run directory not present",
)
def test_phase3_clustering_and_db_reuse(tmp_path: Path) -> None:
    # Run inside an isolated tmp_path copy so tests never overwrite real user outputs or data/icon_db
    test_run_dir = tmp_path / "run_p3"
    (test_run_dir / "phase2_extracted").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        VERIFY_RUN_DIR / "phase2_extracted" / "teams_raw.json",
        test_run_dir / "phase2_extracted" / "teams_raw.json",
    )
    test_db_dir = tmp_path / "icon_db"

    res1 = run_phase3(test_run_dir, db_dir=test_db_dir)
    assert res1["total_icons"] == 240  # 30 teams x 8 slots
    # Rank 10 slot 7 and Rank 21 slot 7 are known empty slots in the sample video!
    assert res1["empty_slot_count"] == 2
    # Expect clean grouping into ~10-25 distinct occupations
    assert 8 <= res1["cluster_count"] <= 24
    assert Path(res1["clusters_sheet_path"]).is_file()
    assert Path(res1["similarity_heatmap_path"]).is_file()

    # Simulate human confirming Traditional Chinese cluster names & saving to reusable DB
    # (Regression test for Windows OpenCV non-ASCII filename bug!)
    cjk_names = ["法師", "補師", "詩人", "賢者", "流氓", "騎士", "德魯伊", "煉金", "舞孃", "武僧", "刺客", "鐵匠", "十字"]
    name_map = {
        c["cluster_id"]: cjk_names[idx - 1] if idx <= len(cjk_names) else f"職業_{idx:02d}"
        for idx, c in enumerate(res1["clusters"], start=1)
        if c["cluster_id"] != "EMPTY"
    }
    confirm_clusters_and_save_db(test_run_dir, name_map, save_to_db=True, db_dir=test_db_dir)

    # Re-run Phase 3 against the now-populated DB: nearly all non-empty icons should auto-match!
    res2 = run_phase3(test_run_dir, db_dir=test_db_dir)
    non_empty = res2["total_icons"] - res2["empty_slot_count"]
    match_rate = res2["db_matched_count"] / max(1, non_empty)
    assert match_rate >= 0.95, f"Expected >=95% DB auto-match rate, got {match_rate:.2%}"

    # Verify Chinese occupation names were actually restored from DB
    matched_names = {c["confirmed_name"] for c in res2["clusters"] if c["matched_from_db"]}
    assert "法師" in matched_names and "補師" in matched_names

    # Regression test: renaming/merging a DB cluster removes old zombie name from DB & merges cards
    merge_map = {
        c["cluster_id"]: ("騎士" if c["confirmed_name"] == "十字" else c["confirmed_name"])
        for c in res2["clusters"]
        if c["cluster_id"] != "EMPTY"
    }
    merged = confirm_clusters_and_save_db(test_run_dir, merge_map, save_to_db=True, db_dir=test_db_dir)
    merged_names = [c["confirmed_name"] for c in merged["clusters"] if c["cluster_id"] != "EMPTY"]
    assert "十字" not in merged_names
    assert merged_names.count("騎士") == 1
    assert all("十字" not in t["occupations"] for t in merged["teams"])
