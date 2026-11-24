"""GitHub Pages static site publisher (docs/index.html + docs/reports/<slug>/).

Supports both:
- Single-period tournament environment reports (`publish_to_github_pages`)
- Multi-period League Standings & Occupation Momentum trend reports (`publish_trend_to_github_pages`)
Automatically ensures leading MMDD date prefix by default and deduplicates by report title.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import DOCS_DIR


def _ensure_leading_date(title: str) -> str:
    """Ensure report title starts with a date prefix (e.g. MMDD or YYYY-MM-DD)."""
    clean = (title or "").strip()
    if not clean:
        return datetime.now().strftime("%m%d") + "女武神戰報"
    if re.match(r"^(?:20\d{2}[-_/]?\d{2}[-_/]?\d{2}|\d{4})", clean):
        return clean
    return f"{datetime.now().strftime('%m%d')}{clean}"


_ASCII_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_ZH_SLUG_HINTS: list[tuple[str, str]] = [
    ("女武神", "valkyrie"),
    ("總決賽", "finals"),
    ("決賽", "finals"),
    ("預賽", "qualifiers"),
    ("初賽", "qualifiers"),
    ("季後賽", "playoffs"),
    ("測試", "test"),
    ("練習", "practice"),
]


def _slugify(text: str) -> str:
    """Strict ASCII-only lowercase URL slug (a-z, 0-9, hyphen)."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def _make_english_slug(title: str, report_type: str = "single") -> str:
    """Generate a clean ASCII English URL slug from a (possibly Chinese) report title."""
    clean = (title or "").strip()
    now = datetime.now()

    rest = clean
    m_ymd = re.match(r"^(20\d{2})[-_/]?(\d{2})[-_/]?(\d{2})(.*)$", clean)
    if m_ymd:
        date_part = f"{m_ymd.group(1)}-{m_ymd.group(2)}-{m_ymd.group(3)}"
        rest = m_ymd.group(4)
    else:
        m_md = re.match(r"^(\d{2})(\d{2})(.*)$", clean)
        if m_md and 1 <= int(m_md.group(1)) <= 12 and 1 <= int(m_md.group(2)) <= 31:
            date_part = f"{now.year}-{m_md.group(1)}-{m_md.group(2)}"
            rest = m_md.group(3)
        else:
            date_part = now.strftime("%Y-%m-%d")

    tokens: list[str] = []
    for zh_kw, en_kw in _ZH_SLUG_HINTS:
        if zh_kw in rest and en_kw not in tokens:
            tokens.append(en_kw)

    for w in re.findall(r"[a-zA-Z0-9]+", rest.lower()):
        if w not in tokens:
            tokens.append(w)

    if not tokens:
        tokens.append("valkyrie")

    suffix = "trend" if report_type == "trend" else "meta"
    if suffix not in tokens:
        tokens.append(suffix)

    slug = _slugify(f"{date_part}-" + "-".join(tokens))[:64].strip("-")
    return slug or f"{date_part}-{suffix}"


def _resolve_dedup_slug_and_clean(
    reports_root: Path,
    title: str,
    explicit_slug: str | None,
    report_type: str = "single",
) -> Path:
    """Resolve a strictly ASCII English slug, reusing an existing ASCII slug for the same title
    and removing any duplicate or legacy non-ASCII folders with that title."""
    existing_same_title_dirs: list[Path] = []
    other_title_slugs: set[str] = set()
    for sub in sorted(reports_root.iterdir()):
        mp = sub / "meta.json"
        if sub.is_dir() and mp.is_file():
            try:
                m_old = json.loads(mp.read_text(encoding="utf-8"))
                if m_old.get("title") == title:
                    existing_same_title_dirs.append(sub)
                else:
                    other_title_slugs.add(sub.name)
            except Exception:
                continue

    if explicit_slug:
        if explicit_slug.isascii():
            slug = _slugify(explicit_slug) or _make_english_slug(title, report_type)
        else:
            slug = _make_english_slug(explicit_slug, report_type)
    else:
        ascii_existing = [d.name for d in existing_same_title_dirs if _ASCII_SLUG_RE.match(d.name)]
        if ascii_existing:
            slug = ascii_existing[0]
        else:
            slug = _make_english_slug(title, report_type)

    if slug in other_title_slugs:
        base = slug
        idx = 2
        while f"{base}-{idx}" in other_title_slugs:
            idx += 1
        slug = f"{base}-{idx}"

    dest = reports_root / slug
    dest.mkdir(parents=True, exist_ok=True)

    for dup_dir in existing_same_title_dirs:
        if dup_dir.resolve() != dest.resolve() and dup_dir.is_dir():
            shutil.rmtree(dup_dir, ignore_errors=True)

    return dest


def _inject_cross_report_nav(reports_root: Path, all_metas: list[dict[str, Any]]) -> None:
    """Inject or update a top navigation bar in every published docs/reports/<slug>/index.html
    so users can jump back to docs/index.html or switch directly between any published reports."""
    for m in all_metas:
        cur_slug = m.get("slug", "")
        rpt_html_p = reports_root / cur_slug / "index.html"
        if not rpt_html_p.is_file():
            continue
        raw = rpt_html_p.read_text(encoding="utf-8")

        links_html = []
        for other in all_metas:
            o_slug = other.get("slug", "")
            o_title = html.escape(str(other.get("title", o_slug)))
            is_cur = o_slug == cur_slug
            icon = "📈" if other.get("report_type") == "trend" else "📊"
            style = (
                "background:#38bdf8;color:#0b1120;border-color:#38bdf8;font-weight:700;"
                if is_cur
                else "background:#0f172a;color:#cbd5e1;border-color:#273552;"
            )
            links_html.append(
                f'<a href="../{html.escape(o_slug)}/index.html" class="gla-nav-pill" style="text-decoration:none;padding:4px 10px;border-radius:999px;border:1px solid;font-size:0.8rem;display:inline-flex;align-items:center;gap:4px;white-space:nowrap;flex-shrink:0;{style}">{icon} {o_title}</a>'
            )

        nav_block = (
            '<!-- GLA_NAV_START -->'
            '<div class="gla-nav-bar" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;background:#131c31;border:1px solid #273552;border-radius:12px;padding:8px 12px;margin-bottom:14px">'
            '<a href="../../index.html" style="text-decoration:none;background:#1c2842;color:#38bdf8;border:1px solid #38bdf8;padding:5px 11px;border-radius:8px;font-weight:700;font-size:0.82rem;display:inline-flex;align-items:center;gap:5px;white-space:nowrap">🏠 戰報總覽</a>'
            f'<div style="display:flex;align-items:center;gap:6px;overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch;padding-bottom:1px"><span style="color:#94a3b8;font-size:0.78rem;white-space:nowrap">⇄ 切換：</span>{"".join(links_html)}</div>'
            '</div>'
            '<!-- GLA_NAV_END -->'
        )

        if "<!-- GLA_NAV_START -->" in raw and "<!-- GLA_NAV_END -->" in raw:
            updated = re.sub(
                r"<!-- GLA_NAV_START -->.*?<!-- GLA_NAV_END -->",
                lambda _: nav_block,
                raw,
                flags=re.DOTALL,
            )
        elif '<div class="wrap">' in raw:
            updated = raw.replace('<div class="wrap">', f'<div class="wrap">\n  {nav_block}', 1)
        else:
            updated = raw

        if updated != raw:
            rpt_html_p.write_text(updated, encoding="utf-8")


def rebuild_docs_index(target_docs: Path = DOCS_DIR) -> Path:
    """Rebuild docs/index.html listing all published single-period and multi-period trend reports."""
    reports_root = target_docs / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)

    all_metas: list[dict[str, Any]] = []
    for sub in sorted(reports_root.iterdir(), reverse=True):
        mp = sub / "meta.json"
        if sub.is_dir() and mp.is_file():
            try:
                all_metas.append(json.loads(mp.read_text(encoding="utf-8")))
            except Exception:
                continue
    all_metas.sort(key=lambda m: m.get("published_at", ""), reverse=True)

    cards_list: list[str] = []
    for m in all_metas:
        is_trend = m.get("report_type") == "trend"
        badge = (
            '<span class="badge trend">📈 跨期聯賽積分榜＆職業趨勢</span>'
            if is_trend
            else '<span class="badge single">📊 單期環境＆教練備戰報告</span>'
        )
        sub_line = (
            f"對比期數：{html.escape(str(m.get('periods', '-')))} ｜ 強勢上分職業：{html.escape(str(m.get('top_occupation', '-')))}"
            if is_trend
            else f"辨識職業：{m.get('distinct_occupations', 14)} 種 ｜ 熱門第一：{html.escape(str(m.get('top_occupation', '-')))}"
        )
        cards_list.append(
            f"""<a class="card {'trend-card' if is_trend else ''}" href="./reports/{html.escape(m['slug'])}/index.html">
          <div class="title-row"><div class="title">{html.escape(m['title'])}</div>{badge}</div>
          <div class="meta">發佈時間：{html.escape(m['published_at'])} ｜ 涵蓋 {m['total_teams']} 隊（{html.escape(m['rank_range'])}）</div>
          <div class="meta">{sub_line}</div>
        </a>"""
        )

    cards_html = "\n".join(cards_list)
    index_html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Game Leaderboard Analyzer — 歷次排位賽戰報與跨期聯賽趨勢</title>
<style>
  body {{ margin:0; font-family:"Microsoft JhengHei","Segoe UI",sans-serif; background:#0f172a; color:#f8fafc; }}
  .wrap {{ max-width:920px; margin:0 auto; padding:36px 18px; }}
  h1 {{ margin:0 0 8px; }}
  .sub {{ color:#94a3b8; margin-bottom:26px; }}
  .card {{ display:block; text-decoration:none; color:inherit; background:#1e293b; border:1px solid #334155; border-radius:14px; padding:18px 20px; margin-bottom:14px; transition:.15s; }}
  .card:hover {{ border-color:#38bdf8; transform:translateY(-2px); }}
  .card.trend-card {{ border-color:rgba(74,222,128,.45); background:linear-gradient(135deg,#1e293b 0%,#132a2e 100%); }}
  .card.trend-card:hover {{ border-color:#4ade80; }}
  .title-row {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px; }}
  .title {{ font-size:1.2rem; font-weight:700; color:#38bdf8; }}
  .card.trend-card .title {{ color:#4ade80; }}
  .badge {{ font-size:.78rem; font-weight:700; padding:3px 10px; border-radius:999px; }}
  .badge.single {{ background:rgba(56,189,248,.18); color:#7dd3fc; }}
  .badge.trend {{ background:rgba(74,222,128,.2); color:#86efac; }}
  .meta {{ color:#cbd5e1; font-size:.9rem; margin-top:3px; line-height:1.5; }}
  @media (max-width: 640px) {{
    .wrap {{ padding: 18px 12px 36px; }}
    h1 {{ font-size: 1.32rem; }}
    .sub {{ font-size: .86rem; margin-bottom: 18px; }}
    .card {{ padding: 14px 14px; border-radius: 12px; }}
    .title {{ font-size: 1.06rem; }}
    .meta {{ font-size: .82rem; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🏆 遊戲排位賽環境分析戰報總覽</h1>
  <div class="sub">點擊任一場次即可檢視互動圖表、線上截圖秒查對手、同分圈假想敵分析與跨期聯賽積分榜。</div>
  {cards_html or '<div class="sub">尚未發佈任何分析戰報。</div>'}
</div>
</body>
</html>
"""
    index_path = target_docs / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    _inject_cross_report_nav(reports_root, all_metas)
    return index_path


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

    title = _ensure_leading_date(analytics.get("report_title", "女武神職業環境分析報告"))
    dest = _resolve_dedup_slug_and_clean(reports_root, title, report_slug, report_type="single")
    slug = dest.name

    html_src = src_share / "report.html"
    if html_src.is_file():
        shutil.copy2(html_src, dest / "index.html")

    cards_src = src_share / "cards"
    if cards_src.is_dir():
        dest_cards = dest / "cards"
        if dest_cards.exists():
            shutil.rmtree(dest_cards)
        shutil.copytree(cards_src, dest_cards)
    if (src_share / "summary.md").is_file():
        shutil.copy2(src_share / "summary.md", dest / "summary.md")

    ov = analytics["overview"]
    meta = {
        "report_type": "single",
        "slug": slug,
        "title": title,
        "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_teams": ov["total_teams"],
        "rank_range": f"#{ov['min_rank']} ~ #{ov['max_rank']}",
        "distinct_occupations": ov["distinct_occupations"],
        "top_occupation": analytics["occupation_frequency"][0]["occupation"] if analytics["occupation_frequency"] else "-",
    }
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    index_path = rebuild_docs_index(target_docs)
    return {
        "slug": slug,
        "report_html_path": str(dest / "index.html"),
        "docs_index_path": str(index_path),
    }


def publish_trend_to_github_pages(
    trend_dir: str | Path,
    trend: dict[str, Any],
    report_slug: str | None = None,
    docs_dir: str | Path = DOCS_DIR,
) -> dict[str, str]:
    """Copy a Phase 6 multi-period League Standings & Trend package into docs/reports/<slug>/ and rebuild docs/index.html."""
    src_dir = Path(trend_dir)
    target_docs = Path(docs_dir)
    reports_root = target_docs / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    (target_docs / ".nojekyll").touch(exist_ok=True)

    title = _ensure_leading_date(trend.get("trend_title", "女武神聯賽跨期積分榜與趨勢"))
    dest = _resolve_dedup_slug_and_clean(reports_root, title, report_slug, report_type="trend")
    slug = dest.name

    html_src = src_dir / "trend_report.html"
    if html_src.is_file():
        shutil.copy2(html_src, dest / "index.html")

    cards_src = src_dir / "cards"
    if cards_src.is_dir():
        dest_cards = dest / "cards"
        if dest_cards.exists():
            shutil.rmtree(dest_cards)
        shutil.copytree(cards_src, dest_cards)
    if (src_dir / "summary.md").is_file():
        shutil.copy2(src_dir / "summary.md", dest / "summary.md")

    sc = trend.get("summary_counts", {})
    occ_trends = trend.get("occupation_trends") or []
    reg_occs = [r for r in occ_trends if not r.get("low_sample")]
    best_occ = reg_occs[0] if reg_occs else (occ_trends[0] if occ_trends else None)
    if best_occ:
        g = best_occ.get("avg_rank_gain")
        g_txt = f" ({g:+.1f}名)" if g is not None else ""
        top_occ_lbl = f"{best_occ['occupation']}{g_txt}"
    else:
        top_occ_lbl = "-"

    meta = {
        "report_type": "trend",
        "slug": slug,
        "title": title,
        "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_teams": sc.get("active_league_teams") or sc.get("tracked_teams", 200),
        "rank_range": f"跨 {sc.get('snapshot_count', 2)} 期聯賽追蹤",
        "periods": " → ".join(trend.get("labels", [])),
        "distinct_occupations": len(occ_trends) or 14,
        "top_occupation": top_occ_lbl,
    }
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    index_path = rebuild_docs_index(target_docs)
    return {
        "slug": slug,
        "report_html_path": str(dest / "index.html"),
        "docs_index_path": str(index_path),
    }
