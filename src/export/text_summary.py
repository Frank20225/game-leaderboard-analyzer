"""Discord / LINE / Forum copy-paste Markdown & plain-text summary generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_text_summary(analytics: dict[str, Any], output_path: str | Path | None = None) -> str:
    """Create a concise, community-ready戰報 summary for Discord / LINE / forums."""
    ov = analytics["overview"]
    title = analytics.get("report_title", "排位賽職業環境分析")
    lines = [
        f"## 🏆 {title}",
        f"- **分析範圍**：第 #{ov['min_rank']} ～ #{ov['max_rank']} 名（共 **{ov['total_teams']} 隊**，{ov['distinct_occupations']} 種職業）",
        "",
        "### 📊 熱門職業排行（依隊伍攜帶率）",
    ]
    for idx, r in enumerate(analytics["occupation_frequency"][:8], start=1):
        lines.append(
            f"{idx}. **{r['occupation']}** — 攜帶率 **{r['team_presence_rate']*100:.1f}%** "
            f"（{r['team_count']} 隊｜總人次 {r['slot_count']} 次 / {r['slot_rate']*100:.1f}%｜均排 #{r['avg_rank']}）"
        )

    lines.extend(["", "### 👑 前段班（Top 10）偏好職業"])
    top_pref = sorted(
        analytics["occupation_frequency"],
        key=lambda r: (r["top10_rate"], -r["avg_rank"]),
        reverse=True,
    )[:5]
    for r in top_pref:
        diff = (r["top10_rate"] - r["team_presence_rate"]) * 100
        sign = "+" if diff >= 0 else ""
        lines.append(
            f"- **{r['occupation']}**：Top 10 攜帶率 **{r['top10_rate']*100:.1f}%**（對比全體 {sign}{diff:.1f}%，Lift {r['top_tier_lift']}x）"
        )

    if analytics["pair_combinations"]:
        lines.extend(["", "### 🤝 熱門雙職業核心組合"])
        for r in analytics["pair_combinations"][:5]:
            lines.append(
                f"- **{r['combination']}**：{r['team_count']} 隊（{r['team_rate']*100:.1f}%｜均排 #{r['avg_rank']}）"
            )

    if analytics["triple_combinations"]:
        lines.extend(["", "### 🔺 熱門三職業核心組合"])
        for r in analytics["triple_combinations"][:5]:
            lines.append(
                f"- **{r['combination']}**：{r['team_count']} 隊（{r['team_rate']*100:.1f}%｜均排 #{r['avg_rank']}）"
            )

    if analytics["same_class_doubles"]:
        lines.extend(["", "### ✌️ 常見同職業雙開（2隻以上）"])
        for r in analytics["same_class_doubles"][:5]:
            lines.append(f"- **{r['combination']}**：{r['team_count']} 隊（{r['team_rate']*100:.1f}%）")

    text = "\n".join(lines).strip() + "\n"
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text
