"""Standalone Phase 4 & 5 runner: analytics, 7-sheet Excel & full shareable package."""

from __future__ import annotations

from datetime import datetime
import json
import sys
from pathlib import Path
from typing import Any

from src.analytics.stats import compute_leaderboard_analytics
from src.export.excel_writer import write_excel_report
from src.export.html_report import generate_html_report
from src.export.share_cards import generate_share_cards
from src.export.text_summary import generate_text_summary


def default_report_title() -> str:
    """Return today's MMDD + 女武神職業環境分析報告."""
    return f"{datetime.now().strftime('%m%d')}女武神職業環境分析報告"


def _collect_icon_paths(run_path: Path) -> dict[str, str]:
    """Map each confirmed/suggested occupation name to a clean representative PNG icon."""
    mapping: dict[str, str] = {}
    p3_path = run_path / "phase3_icons" / "clusters.json"
    if p3_path.is_file():
        p3 = json.loads(p3_path.read_text(encoding="utf-8"))
        for cl in p3.get("clusters", []):
            if cl.get("cluster_id") == "EMPTY":
                continue
            name = (cl.get("confirmed_name") or cl.get("suggested_name") or "").strip()
            rep = cl.get("representative_norm_path", "")
            if name and rep and Path(rep).is_file() and name not in mapping:
                mapping[name] = rep
    return mapping


def run_phase4_5(
    run_dir: str | Path,
    report_title: str | None = None,
) -> dict[str, Any]:
    """Run statistical analysis and export Excel + full shareable package."""
    if not report_title or report_title == "排位賽職業環境分析報告":
        report_title = default_report_title()
    run_path = Path(run_dir)
    teams_path = run_path / "phase3_icons" / "teams_with_icons.json"
    if not teams_path.is_file():
        raise FileNotFoundError(f"找不到 Phase 3 隊伍資料: {teams_path}")

    teams = json.loads(teams_path.read_text(encoding="utf-8"))
    issues_path = run_path / "phase2_extracted" / "issues.json"
    issues = json.loads(issues_path.read_text(encoding="utf-8")) if issues_path.is_file() else []

    analytics = compute_leaderboard_analytics(teams=teams, issues=issues, report_title=report_title)

    phase4_dir = run_path / "phase4_stats"
    phase4_dir.mkdir(parents=True, exist_ok=True)
    analytics_json_path = phase4_dir / "analytics.json"
    analytics_json_path.write_text(
        json.dumps(analytics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    share_dir = run_path / "share"
    share_dir.mkdir(parents=True, exist_ok=True)
    icon_map = _collect_icon_paths(run_path)

    excel_full_path = write_excel_report(analytics, run_path / "report.xlsx", include_errors_sheet=True)
    excel_public_path = write_excel_report(analytics, share_dir / "report_public.xlsx", include_errors_sheet=False)
    # Generate share cards FIRST so html_report can embed 02_copy_count_impact.png inline as Base64
    card_paths = generate_share_cards(analytics, icon_map, share_dir / "cards")
    html_path = generate_html_report(analytics, icon_map, share_dir / "report.html", cards_dir=share_dir / "cards")
    summary_path = share_dir / "summary.md"
    summary_text = generate_text_summary(analytics, summary_path)

    manifest = {
        "report_title": report_title,
        "analytics_json_path": str(analytics_json_path),
        "excel_full_path": str(excel_full_path),
        "excel_public_path": str(excel_public_path),
        "html_report_path": str(html_path),
        "share_card_paths": card_paths,
        "summary_md_path": str(summary_path),
        "summary_text": summary_text,
        "overview": analytics["overview"],
    }
    (share_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.pipeline_phase4_5 <existing_run_dir> [report_title]")
        sys.exit(1)
    title = sys.argv[2] if len(sys.argv) >= 3 else default_report_title()
    res = run_phase4_5(sys.argv[1], report_title=title)
    print(json.dumps({k: v for k, v in res.items() if k != "summary_text"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
