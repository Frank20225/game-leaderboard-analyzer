"""Discord / LINE / Forum v2 Tournament Roster Strategy Summary Generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_text_summary(analytics: dict[str, Any], output_path: str | Path | None = None) -> str:
    """Create a strategic tournament roster summary for Discord / LINE / forums."""
    ov = analytics["overview"]
    title = analytics.get("report_title", "排位賽戰隊排陣分析")
    lines = [
        f"## 🏆 {title}",
        f"- **分析範圍**：第 #{ov['min_rank']}～#{ov['max_rank']} 名（共 **{ov['total_teams']} 隊**｜統一範本・8人名單同職上限2）",
        "",
        "### ⭐ Meta 四象限分類",
    ]
    for q_label in ("T0 版本核心", "高端奇兵 / 黑馬", "普及標配 / 均勢", "低樣本觀察 (n<5)"):
        members = [r for r in analytics["occupation_frequency"] if r["quadrant"] == q_label]
        if members:
            desc = "、".join(f"**{r['occupation']}**({r['team_presence_rate']*100:.0f}%, 均#{r['avg_rank']})" for r in members[:6])
            lines.append(f"- **{q_label}**：{desc}")

    # Double-pick ROI highlights
    dp_worthy = [
        r for r in analytics["occupation_frequency"]
        if r["copy_2"]["teams"] >= 2 and r["double_rank_gain"] is not None
    ]
    dp_worthy.sort(key=lambda r: -r["double_rank_gain"])
    if dp_worthy:
        lines.extend(["", "### ✌️ 雙開（帶 2 隻）名次效益排行（1隻 → 2隻）"])
        for r in dp_worthy[:5]:
            g = r["double_rank_gain"]
            sign = "+" if g >= 0 else ""
            lines.append(
                f"- **{r['occupation']}**：單帶均 #{r['copy_1']['avg_rank']} → 雙開均 **#{r['copy_2']['avg_rank']}**（{sign}{g} 名｜雙開 {r['copy_2']['teams']} 隊）"
            )

    if analytics.get("double_pick_structure"):
        lines.extend(["", "### 🧩 戰隊「雙開組數」結構"])
        for d in analytics["double_pick_structure"]:
            lines.append(f"- **{d['label']}**：{d['team_count']} 隊（{d['team_rate']*100:.1f}%｜均排 **#{d['avg_rank']}**｜Top10 佔 {d['top10_count']} 隊）")

    if analytics.get("synergy_pairs"):
        lines.extend(["", "### 🔥 真正高協同搭檔（Synergy Lift ≥ 1.15）"])
        for r in analytics["synergy_pairs"][:5]:
            lines.append(f"- **{r['combination']}**：協同 **{r['synergy_lift']}x**（{r['team_count']} 隊｜均排 #{r['avg_rank']}）")

    if analytics.get("substitution_pairs"):
        lines.extend(["", "### ⚔️ 同位互斥替代（Synergy Lift ≤ 0.85）"])
        for r in analytics["substitution_pairs"][:5]:
            lines.append(f"- **{r['combination']}**：協同 **{r['synergy_lift']}x**（同隊僅 {r['team_count']} 隊，預期 {r['expected_rate']*100:.0f}%）")

    if analytics.get("roster_archetypes"):
        lines.extend(["", "### 📋 主流建隊流派骨架"])
        for a in analytics["roster_archetypes"][:4]:
            lines.append(f"- **{a['archetype_id']} {a['archetype_name']}**（{a['team_count']} 隊｜均排 #{a['avg_rank']}）：核心 `{a['core_classes']}`")

    text = "\n".join(lines).strip() + "\n"
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text
