"""Integration and accuracy tests for Stage 2 (Multilingual OCR & Cross-Frame Deduplication)."""

from pathlib import Path

import pytest

from src.pipeline_phase1 import run_phase1
from src.pipeline_phase2 import run_phase2

SAMPLE_VIDEO = Path(r"C:\Users\f1991\Videos\2026-11-21 03-18-43.mp4")
VERIFY_RUN_DIR = Path(r"C:\Users\f1991\source\repos\game-leaderboard-analyzer\outputs\stage1_verify")


@pytest.mark.skipif(not SAMPLE_VIDEO.is_file(), reason="Sample video not present")
def test_phase2_on_sample_video(tmp_path: Path) -> None:
    # Reuse stage1_verify if present for speed; otherwise run phase1 fresh
    if (VERIFY_RUN_DIR / "phase1_frames" / "phase1_summary.json").is_file():
        run_dir = VERIFY_RUN_DIR
    else:
        run_dir = tmp_path / "run_p2"
        run_phase1(SAMPLE_VIDEO, run_dir=run_dir)

    teams, issues, audit = run_phase2(run_dir)

    # Sample video covers ranks 1..30 with zero missing ranks and zero duplicates
    assert audit.extracted_team_count == 30
    assert audit.min_rank == 1
    assert audit.max_rank == 30
    assert audit.missing_ranks == []
    assert audit.is_contiguous_from_1 is True

    # Personal row (rank 72) must NEVER appear in extracted teams
    ranks = [t.rank for t in teams]
    assert 72 not in ranks
    assert ranks == list(range(1, 31))

    # Spot-check known Top 1-3 badges & English/Chinese/Thai names and scores from the sample video
    by_rank = {t.rank: t for t in teams}
    assert by_rank[1].score == 45
    assert "Encore" in by_rank[1].team_name
    assert by_rank[2].score == 45
    assert by_rank[3].score == 45
    assert by_rank[10].score == 44
    assert by_rank[30].score == 43

    # Verify non-increasing score monotonicity across all 30 teams
    scores = [t.score for t in teams]
    assert all(s is not None for s in scores)
    assert all(scores[i] <= scores[i - 1] for i in range(1, len(scores)))

    # Verify 8 icon crops saved per team
    for t in teams:
        assert len(t.icon_crop_paths) == 8
        assert Path(t.row_crop_path).is_file()
