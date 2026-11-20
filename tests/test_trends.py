"""Unit & export tests for multi-snapshot longitudinal trend analysis."""

from pathlib import Path

import openpyxl

from src.analytics.trends import compare_multiple_runs
from src.export.trend_export import export_trend_package


def test_multi_run_trend_and_roster_diff(tmp_path: Path) -> None:
    day1 = [
        {"rank": 1, "team_name": "Alpha", "score": 30, "occupations": ["補師", "法師", "詩人", "賢者", "騎士", "流氓", "刺客", "煉金"]},
        {"rank": 2, "team_name": "Beta", "score": 29, "occupations": ["補師", "補師", "法師", "詩人", "賢者", "騎士", "武僧", "刺客"]},
        {"rank": 3, "team_name": "Gamma", "score": 28, "occupations": ["補師", "法師", "詩人", "賢者", "流氓", "舞孃", "刺客", "鐵匠"]},
    ]
    # Day 2: Beta swaps 刺客 -> 德魯伊 and climbs #2 -> #1; Gamma swaps 鐵匠 -> 德魯伊
    day2 = [
        {"rank": 1, "team_name": "Beta", "score": 60, "occupations": ["補師", "補師", "法師", "詩人", "賢者", "騎士", "武僧", "德魯伊"]},
        {"rank": 2, "team_name": "Alpha", "score": 58, "occupations": ["補師", "法師", "詩人", "賢者", "騎士", "流氓", "刺客", "煉金"]},
        {"rank": 3, "team_name": "Gamma", "score": 55, "occupations": ["補師", "法師", "詩人", "賢者", "流氓", "舞孃", "刺客", "德魯伊"]},
    ]

    trend = compare_multiple_runs(
        [
            {"run_id": "d1", "label": "Day 1", "teams": day1},
            {"run_id": "d2", "label": "Day 2", "teams": day2},
        ],
        trend_title="排位賽 Day1 vs Day2 趨勢",
    )

    # 德魯伊 rose from 0% -> 66.7%; 刺客 dropped from 100% -> 66.7%
    by_occ = {r["occupation"]: r for r in trend["occupation_trends"]}
    assert by_occ["德魯伊"]["presence_delta"] > 0.6
    assert by_occ["刺客"]["presence_delta"] < -0.3

    # Beta roster change detected accurately (-刺客 +德魯伊, rank #2 -> #1, delta = +1)
    beta_changes = [c for c in trend["roster_changes"] if c["team_name"] == "Beta"]
    assert len(beta_changes) == 1
    assert beta_changes[0]["removed"] == ["刺客"]
    assert beta_changes[0]["added"] == ["德魯伊"]
    assert beta_changes[0]["rank_delta"] == 1

    # Full export package check
    manifest = export_trend_package(trend, tmp_path / "trend_out")
    wb = openpyxl.load_workbook(manifest["excel_path"])
    assert wb.sheetnames == ["Meta Shift", "Double-Pick Shift", "Team Trajectory", "Roster Changes"]
    assert Path(manifest["html_path"]).is_file()
    assert len(manifest["card_paths"]) == 2
    assert all(Path(p).is_file() for p in manifest["card_paths"])
    assert "德魯伊" in manifest["summary_text"]
