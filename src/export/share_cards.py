"""High-DPI PNG share cards optimized for LINE / Discord community sharing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import matplotlib
import numpy as np
from matplotlib.offsetbox import AnnotationBbox, OffsetImage

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Noto Sans CJK TC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _load_icon_rgba(path: str | Path, size: int = 28) -> np.ndarray | None:
    if not path or not Path(path).is_file():
        return None
    img = cv2.imread(str(path))
    if img is None:
        return None
    rgb = cv2.cvtColor(cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    # Circular alpha mask for clean round icon thumbnail on charts
    yy, xx = np.ogrid[:size, :size]
    c = (size - 1) / 2.0
    alpha = (((xx - c) ** 2 + (yy - c) ** 2) <= (size * 0.45) ** 2).astype(np.uint8) * 255
    return np.dstack([rgb, alpha])


def generate_share_cards(
    analytics: dict[str, Any],
    icon_paths_by_name: dict[str, str],
    cards_dir: str | Path,
) -> list[str]:
    """Generate 3 crisp shareable PNG infographics for LINE / Discord."""
    out_dir = Path(cards_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    ov = analytics["overview"]
    title = analytics.get("report_title", "排位賽職業環境分析")
    subtitle = f"樣本：{ov['total_teams']} 隊（#{ov['min_rank']}～#{ov['max_rank']}）｜共 {ov['distinct_occupations']} 種職業"

    occ_list = analytics["occupation_frequency"]
    if occ_list:
        # Card 1: Occupation Frequency (Team Presence Rate + Slot Share)
        top_n = occ_list[:16]
        names = [r["occupation"] for r in top_n][::-1]
        team_rates = [r["team_presence_rate"] * 100 for r in top_n][::-1]
        slot_rates = [r["slot_rate"] * 100 for r in top_n][::-1]
        y = np.arange(len(names))

        fig, ax = plt.subplots(figsize=(10.5, max(5.8, len(names) * 0.52)), facecolor="#0f172a")
        ax.set_facecolor("#1e293b")
        h_bar = 0.36
        bars1 = ax.barh(y + h_bar / 2, team_rates, height=h_bar, color="#38bdf8", label="隊伍攜帶率（至少1隻 / 總隊數）")
        bars2 = ax.barh(y - h_bar / 2, slot_rates, height=h_bar, color="#f59e0b", label="總人次佔比（出場次數 / 總有效格數）")

        ax.set_yticks(y)
        ax.set_yticklabels(names, color="#f8fafc", fontsize=11, fontweight="bold")
        ax.tick_params(axis="y", pad=32)
        ax.set_xlabel("百分比 (%)", color="#cbd5e1", fontsize=11)
        ax.tick_params(axis="x", colors="#cbd5e1")
        ax.set_xlim(0, max(max(team_rates, default=10) * 1.24, 25))
        ax.grid(axis="x", color="#334155", linestyle="--", alpha=0.6)
        for spine in ax.spines.values():
            spine.set_color("#334155")

        for b, val in zip(bars1, team_rates):
            ax.text(val + 0.8, b.get_y() + b.get_height() / 2, f"{val:.1f}%", va="center", color="#7dd3fc", fontsize=9.5, fontweight="bold")
        for b, val in zip(bars2, slot_rates):
            ax.text(val + 0.8, b.get_y() + b.get_height() / 2, f"{val:.1f}%", va="center", color="#fcd34d", fontsize=9)

        # Embed round occupation thumbnails next to Y-axis bars
        for idx, nm in enumerate(names):
            rgba = _load_icon_rgba(icon_paths_by_name.get(nm, ""), size=26)
            if rgba is not None:
                ab = AnnotationBbox(OffsetImage(rgba, zoom=0.85), (0, idx), xybox=(-14, 0), boxcoords="offset points", frameon=False, clip_on=False)
                ax.add_artist(ab)

        ax.set_title(f"{title}｜職業出場率總覽\n{subtitle}", color="#ffffff", fontsize=14, fontweight="bold", pad=16)
        ax.legend(loc="lower right", facecolor="#0f172a", edgecolor="#475569", labelcolor="#f8fafc", fontsize=9.5)
        fig.tight_layout()
        p1 = out_dir / "01_occupation_frequency.png"
        fig.savefig(str(p1), dpi=180, facecolor=fig.get_facecolor())
        plt.close(fig)
        created.append(str(p1))

        # Card 2: Ranking Tier Comparison (Top 10 vs Top 50 vs Overall)
        top_t = occ_list[:12]
        tnames = [r["occupation"] for r in top_t]
        x = np.arange(len(tnames))
        w = 0.26
        r_all = [r["team_presence_rate"] * 100 for r in top_t]
        r_t50 = [r["top50_rate"] * 100 for r in top_t]
        r_t10 = [r["top10_rate"] * 100 for r in top_t]

        fig, ax = plt.subplots(figsize=(11.5, 6.2), facecolor="#0f172a")
        ax.set_facecolor("#1e293b")
        ax.bar(x - w, r_t10, width=w, color="#f43f5e", label="Top 10")
        ax.bar(x, r_t50, width=w, color="#a855f7", label="Top 50")
        ax.bar(x + w, r_all, width=w, color="#38bdf8", label=f"全體 ({ov['total_teams']}隊)")

        ax.set_xticks(x)
        ax.set_xticklabels(tnames, rotation=28, ha="right", color="#f8fafc", fontsize=10.5, fontweight="bold")
        ax.set_ylabel("隊伍攜帶率 (%)", color="#cbd5e1", fontsize=11)
        ax.tick_params(axis="y", colors="#cbd5e1")
        ax.set_ylim(0, 112)
        ax.grid(axis="y", color="#334155", linestyle="--", alpha=0.6)
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.set_title(f"{title}｜Top 10 vs Top 50 vs 全體 職業趨勢對比\n{subtitle}", color="#ffffff", fontsize=14, fontweight="bold", pad=14)
        ax.legend(loc="upper right", facecolor="#0f172a", edgecolor="#475569", labelcolor="#f8fafc", fontsize=10)
        fig.tight_layout()
        p2 = out_dir / "02_ranking_tier_comparison.png"
        fig.savefig(str(p2), dpi=180, facecolor=fig.get_facecolor())
        plt.close(fig)
        created.append(str(p2))

    # Card 3: Top Pair, Triple & Full-Team Combinations Summary Card
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 6.2), facecolor="#0f172a")
    fig.suptitle(f"{title}｜熱門雙職業與三職業核心組合\n{subtitle}", color="#ffffff", fontsize=14, fontweight="bold", y=0.97)

    for ax, key, heading, color in [
        (axes[0], "pair_combinations", "Top 10 熱門雙職業組合（每隊去重）", "#22c55e"),
        (axes[1], "triple_combinations", "Top 10 熱門三職業組合（每隊去重）", "#eab308"),
    ]:
        ax.set_facecolor("#1e293b")
        rows = analytics.get(key, [])[:10][::-1]
        if rows:
            labels = [r["combination"] for r in rows]
            vals = [r["team_rate"] * 100 for r in rows]
            y_pos = np.arange(len(labels))
            bars = ax.barh(y_pos, vals, color=color, height=0.6)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, color="#f8fafc", fontsize=9.5)
            ax.set_xlim(0, max(max(vals) * 1.28, 25))
            for b, r in zip(bars, rows):
                ax.text(
                    r["team_rate"] * 100 + 0.8,
                    b.get_y() + b.get_height() / 2,
                    f"{r['team_rate']*100:.1f}% ({r['team_count']}隊, 均#{r['avg_rank']:.1f})",
                    va="center",
                    color="#e2e8f0",
                    fontsize=8.5,
                )
        ax.set_title(heading, color="#f8fafc", fontsize=11.5, fontweight="bold", pad=10)
        ax.set_xlabel("隊伍佔比 (%)", color="#cbd5e1", fontsize=10)
        ax.tick_params(axis="x", colors="#cbd5e1")
        ax.grid(axis="x", color="#334155", linestyle="--", alpha=0.5)
        for spine in ax.spines.values():
            spine.set_color("#334155")

    fig.tight_layout(rect=[0, 0, 1, 0.90])
    p3 = out_dir / "03_top_combinations.png"
    fig.savefig(str(p3), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    created.append(str(p3))

    return created
