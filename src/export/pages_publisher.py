"""GitHub Pages static site publisher (docs/index.html + docs/reports/<slug>/)."""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import DOCS_DIR, DOCS_REPORTS_DIR


def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", text.strip().lower()).strip("-")
    return s or datetime.now().strftime("report-%Y%m%d-%H%M%S")


def publish_to_github_pages(
    share_dir: str | Path,
    analytics: dict[str, Any],
    report_slug: str | None = None,
    docs_dir: str | Path = DOCS_DIR,
) -> dict[str, str]:
    """Copy a run's share/ report & cards into docs/reports/<slug>/ and rebuild docs/index.html."""
    src_share = Path(share_dir)
    target_docs = Path(docs_dir)
    reports_root = target_docs / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    (target_docs / ".nojekyll").touch(exist_ok=True)

    title = analytics.get("report_title", "排位賽職業環境分析報告")

    # Find existing report folder(s) with the exact same title to prevent duplicate cards on docs/index.html
    existing_same_title_dirs: list[Path] = []
    for sub in sorted(reports_root.iterdir()):
        mp = sub / "meta.json"
        if sub.is_dir() and mp.is_file():
            try:
                m_old = json.loads(mp.read_text(encoding="utf-8"))
                if m_old.get("title") == title:
                    existing_same_title_dirs.append(sub)
            except Exception:
                continue

    if report_slug:
        slug = _slugify(report_slug)
    elif existing_same_title_dirs:
        # Reuse existing folder slug so re-publishing from Web UI updates in place
        slug = existing_same_title_dirs[0].name
    else:
        slug = _slugify(title[:32])

    dest = reports_root / slug
    dest.mkdir(parents=True, exist_ok=True)

    # Remove any other duplicate folders that had the exact same report title
    for dup_dir in existing_same_title_dirs:
        if dup_dir.resolve() != dest.resolve() and dup_dir.is_dir():
            shutil.rmtree(dup_dir, ignore_errors=True)

    # Copy interactive single-file HTML report as index.html inside this report folder
    html_src = src_share / "report.html"
    if html_src.is_file():
        shutil.copy2(html_src, dest / "index.html")

    # Copy share cards & text summary
    cards_src = src_share / "cards"
    if cards_src.is_dir():
        dest_cards = dest / "cards"
        if dest_cards.exists():
            shutil.rmtree(dest_cards)
        shutil.copytree(cards_src, dest_cards)
    if (src_share / "summary.md").is_file():
        shutil.copy2(src_share / "summary.md", dest / "summary.md")

    # Write per-report metadata for index generation
    ov = analytics["overview"]
    meta = {
        "slug": slug,
        "title": title,
        "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_teams": ov["total_teams"],
        "rank_range": f"#{ov['min_rank']} ~ #{ov['max_rank']}",
        "distinct_occupations": ov["distinct_occupations"],
        "top_occupation": analytics["occupation_frequency"][0]["occupation"] if analytics["occupation_frequency"] else "-",
    }
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Rebuild docs/index.html archive page
    all_metas: list[dict] = []
    for sub in sorted(reports_root.iterdir(), reverse=True):
        mp = sub / "meta.json"
        if sub.is_dir() and mp.is_file():
            try:
                all_metas.append(json.loads(mp.read_text(encoding="utf-8")))
            except Exception:
                continue
    all_metas.sort(key=lambda m: m.get("published_at", ""), reverse=True)

    cards_html = "\n".join(
        f"""<a class="card" href="./reports/{html.escape(m['slug'])}/index.html">
          <div class="title">{html.escape(m['title'])}</div>
          <div class="meta">發佈時間：{html.escape(m['published_at'])} ｜ 涵蓋 {m['total_teams']} 隊（{html.escape(m['rank_range'])}）</div>
          <div class="meta">辨識職業：{m['distinct_occupations']} 種 ｜ 熱門第一：{html.escape(m['top_occupation'])}</div>
        </a>"""
        for m in all_metas
    )
    index_html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Game Leaderboard Analyzer — 歷次排位賽戰報</title>
<style>
  body {{ margin:0; font-family:"Microsoft JhengHei","Segoe UI",sans-serif; background:#0f172a; color:#f8fafc; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:36px 18px; }}
  h1 {{ margin:0 0 8px; }}
  .sub {{ color:#94a3b8; margin-bottom:26px; }}
  .card {{ display:block; text-decoration:none; color:inherit; background:#1e293b; border:1px solid #334155; border-radius:14px; padding:18px 20px; margin-bottom:14px; transition:.15s; }}
  .card:hover {{ border-color:#38bdf8; transform:translateY(-2px); }}
  .title {{ font-size:1.2rem; font-weight:700; color:#38bdf8; margin-bottom:6px; }}
  .meta {{ color:#cbd5e1; font-size:.9rem; margin-top:3px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🏆 遊戲排位賽環境分析戰報總覽</h1>
  <div class="sub">點擊任一場次即可檢視互動圖表、職業出場率與完整陣容查詢。</div>
  {cards_html or '<div class="sub">尚未發佈任何分析戰報。</div>'}
</div>
</body>
</html>
"""
    index_path = target_docs / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    return {
        "slug": slug,
        "report_html_path": str(dest / "index.html"),
        "docs_index_path": str(index_path),
    }
