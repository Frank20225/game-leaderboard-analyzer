"""Integration tests for Stage 4 & 5 (Analytics, 7-Sheet Excel & Shareable Package)."""

import json
from pathlib import Path

import openpyxl
import pytest

from src.export.pages_publisher import publish_to_github_pages
from src.pipeline_phase4_5 import run_phase4_5

VERIFY_RUN_DIR = Path(r"C:\Users\f1991\source\repos\game-leaderboard-analyzer\outputs\stage1_verify")


@pytest.mark.skipif(
    not (VERIFY_RUN_DIR / "phase3_icons" / "teams_with_icons.json").is_file(),
    reason="Phase 3 verified run directory not present",
)
def test_phase4_5_exports_and_pages(tmp_path: Path) -> None:
    manifest = run_phase4_5(VERIFY_RUN_DIR, report_title="實測排位賽 30 隊環境分析")

    # 1. Verify full Excel has all 7 required sheets and data rows
    full_xlsx = Path(manifest["excel_full_path"])
    assert full_xlsx.is_file()
    wb = openpyxl.load_workbook(full_xlsx)
    expected_sheets = [
        "Raw Data",
        "Occupation Frequency",
        "Pair Combinations",
        "Triple Combinations",
        "Full Team Combinations",
        "Ranking Analysis",
        "Recognition Errors",
    ]
    assert wb.sheetnames == expected_sheets
    assert wb["Raw Data"].max_row == 31  # 1 header + 30 teams
    assert wb["Occupation Frequency"].max_row >= 10

    # 2. Verify public Excel omits Recognition Errors
    pub_xlsx = Path(manifest["excel_public_path"])
    assert pub_xlsx.is_file()
    wb_pub = openpyxl.load_workbook(pub_xlsx)
    assert "Recognition Errors" not in wb_pub.sheetnames
    assert len(wb_pub.sheetnames) == 6

    # 3. Verify self-contained HTML report with Base64 icons
    html_file = Path(manifest["html_report_path"])
    assert html_file.is_file()
    html_text = html_file.read_text(encoding="utf-8")
    assert "data:image/png;base64," in html_text
    assert "Encore.NT" in html_text

    # 4. Verify 3 PNG share cards & Markdown text summary
    assert len(manifest["share_card_paths"]) == 3
    for cp in manifest["share_card_paths"]:
        assert Path(cp).is_file()
        assert Path(cp).stat().st_size > 10_000
    assert Path(manifest["summary_md_path"]).is_file()

    # 5. Verify GitHub Pages publishing into temporary docs dir
    analytics = json.loads(Path(manifest["analytics_json_path"]).read_text(encoding="utf-8"))
    pub_res = publish_to_github_pages(
        VERIFY_RUN_DIR / "share", analytics, report_slug="sample-30", docs_dir=tmp_path / "docs"
    )
    assert Path(pub_res["report_html_path"]).is_file()
    assert Path(pub_res["docs_index_path"]).is_file()
    assert "實測排位賽 30 隊環境分析" in Path(pub_res["docs_index_path"]).read_text(encoding="utf-8")
