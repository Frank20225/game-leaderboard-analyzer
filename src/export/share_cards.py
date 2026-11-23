"""Pro Tournament v2 PNG Share Cards (4 charts for roster building & community sharing).

1. 01_meta_quadrant.png: Meta 4-Quadrant Strategic Map (Presence Rate vs Avg Rank + Icons)
2. 02_copy_count_impact.png: 0 vs 1 vs 2 Copies Marginal Rank Impact (Double-Pick ROI)
3. 03_tier_heatmap_and_doubles.png: Non-overlapping Rank Tier Heatmap + Double-Pick Structure
4. 04_synergy_matrix.png: Occupation Synergy & Substitution Matrix (Pairwise Lift)
"""

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


def _load_icon_rgba(path: str | Path, size: int = 32) -> np.ndarray | None:
    if not path or not Path(path).is_file():
        return None
    buf = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR) if buf.size else None
    if img is None:
        return None
    rgb = cv2.cvtColor(cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    yy, xx = np.ogrid[:size, :size]
    c = (size - 1) / 2.0
    alpha = (((xx - c) ** 2 + (yy - c) ** 2) <= (size * 0.46) ** 2).astype(np.uint8) * 255
    return np.dstack([rgb, alpha])


def generate_share_cards(
    analytics: dict[str, Any],
    icon_paths_by_name: dict[str, str],
    cards_dir: str | Path,
) -> list[str]:
    """Generate 4 pro-tournament PNG visual cards tailored for roster strategy."""
    out_dir = Path(cards_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale legacy cards if any
    for old_name in ("01_occupation_frequency.png", "02_ranking_tier_comparison.png", "03_top_combinations.png"):
        old_p = out_dir / old_name
        if old_p.is_file():
            old_p.unlink()

    created: list[str] = []
    ov = analytics["overview"]
    title = analytics.get("report_title", "排位賽戰隊排陣分析")
    subtitle = f"樣本：{ov['total_teams']} 隊（#{ov['min_rank']}～#{ov['max_rank']}）｜8人名單同職上限2｜統一範本 BO5"
    occ_list = analytics.get("occupation_frequency", [])

    if not occ_list:
        return created

    # ------------------------------------------------------------------
    # Card 1: Meta 4-Quadrant Strategic Map (Presence Rate vs Avg Rank)
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(11.5, 7.6), facecolor="#0f172a")
    ax.set_facecolor("#162033")

    avg_r = float(ov.get("overall_avg_rank", 15.5))
    xs = [r["team_presence_rate"] * 100 for r in occ_list]
    ys = [r["avg_rank"] for r in occ_list]

    y_min = max(1.0, min(ys) - max(3.0, (max(ys) - min(ys)) * 0.25))
    y_max = max(ys) + max(2.8, (max(ys) - min(ys)) * 0.24)
    x_mid = 50.0

    # Subtle quadrant background shading
    ax.axvspan(x_mid, 108, ymin=0, ymax=1, color="#0ea5e9", alpha=0.05)
    ax.axvline(x_mid, color="#64748b", linestyle="--", linewidth=1.2)
    ax.axhline(avg_r, color="#64748b", linestyle="--", linewidth=1.2)

    # Invert Y so BETTER (smaller) rank is at the TOP!
    ax.set_xlim(-5, 108)
    ax.set_ylim(y_max, y_min)

    # Quadrant corner labels (pure JhengHei-safe glyphs, zero missing emoji warnings!)
    ax.text(105, y_min + (y_max - y_min) * 0.03, "★ T0 版本核心\n(高出場率 × 高排名)", color="#38bdf8", ha="right", va="top", fontsize=11, fontweight="bold")
    ax.text(-2, y_min + (y_max - y_min) * 0.03, "▲ 高端奇兵 / 黑馬\n(低出場率 × 高排名)", color="#4ade80", ha="left", va="top", fontsize=11, fontweight="bold")
    ax.text(105, y_max - (y_max - y_min) * 0.03, "● 普及標配 / 均勢\n(高出場率 × 一般排名)", color="#fbbf24", ha="right", va="bottom", fontsize=10.5, fontweight="bold")
    ax.text(-2, y_max - (y_max - y_min) * 0.03, "▼ 冷門職\n(低出場率 × 偏後排名)", color="#94a3b8", ha="left", va="bottom", fontsize=10.5, fontweight="bold")

    # Smart non-overlapping label placement using candidate offsets (top/bottom/left/right)
    placed_boxes: list[tuple[float, float]] = []
    y_span = max(1.0, y_max - y_min)
    for r in occ_list:
        x_val = r["team_presence_rate"] * 100
        y_val = r["avg_rank"]

        # Candidate (dx_pts, dy_pts) offsets; prefer below if near top edge
        candidates = (
            [(0, -26), (0, 25), (36, -16), (-36, -16), (36, 18), (-36, 18)]
            if (y_val - y_min) / y_span < 0.16
            else [(0, 24), (0, -25), (42, 14), (-42, 14), (42, -16), (-42, -16)]
        )
        best_dx, best_dy = candidates[0]
        best_score = -1e9
        for dx, dy in candidates:
            # Approximate label anchor in data coordinates
            lx = x_val + dx * 0.14
            ly = y_val - dy * (y_span / 460.0)
            min_d = min(
                (abs(lx - bx) / 14.0) ** 2 + (abs(ly - by) / (y_span * 0.08)) ** 2
                for bx, by in placed_boxes
            ) if placed_boxes else 999.0
            # Penalize drifting outside plot bounds
            bound_pen = 0.0 if (2 <= lx <= 102 and y_min + y_span * 0.08 <= ly <= y_max - y_span * 0.08) else -50.0
            sc = min(min_d, 4.0) + bound_pen
            if sc > best_score:
                best_score = sc
                best_dx, best_dy = dx, dy
        placed_boxes.append((x_val + best_dx * 0.14, y_val - best_dy * (y_span / 460.0)))

        rgba = _load_icon_rgba(icon_paths_by_name.get(r["occupation"], ""), size=34)
        if rgba is not None:
            ab = AnnotationBbox(OffsetImage(rgba, zoom=0.92), (x_val, y_val), frameon=False, zorder=5)
            ax.add_artist(ab)
        else:
            ax.scatter([x_val], [y_val], s=140, color="#38bdf8", zorder=5)

        if r.get("low_sample"):
            ax.scatter([x_val], [y_val], s=620, facecolors="none", edgecolors="#f59e0b", linewidths=1.5, linestyle="--", zorder=4)

        dp_txt = f" 雙職{r['double_pick_rate']*100:.0f}%" if r["double_pick_teams"] > 0 else ""
        low_txt = " (n<5)" if r.get("low_sample") else ""
        ax.annotate(
            f"{r['occupation']} #{y_val:.1f}{dp_txt}{low_txt}",
            xy=(x_val, y_val),
            xytext=(best_dx, best_dy),
            textcoords="offset points",
            ha="center",
            va="center",
            color="#f8fafc" if not r.get("low_sample") else "#fcd34d",
            fontsize=8.8,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.22", fc="#0f172a", ec="#334155", alpha=0.88),
            zorder=6,
        )

    ax.set_xlabel("隊伍出場率 (%)", color="#e2e8f0", fontsize=11.5, fontweight="bold")
    ax.set_ylabel(
        "↑\n排\n名\n越\n高\n\n平\n均\n排\n名",
        color="#e2e8f0",
        fontsize=11,
        fontweight="bold",
        rotation=0,
        ha="center",
        va="center",
        labelpad=22,
    )
    ax.tick_params(colors="#cbd5e1")
    ax.grid(True, color="#334155", linestyle=":", alpha=0.55)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.set_title(f"{title}｜Meta 四象限戰略圖\n{subtitle}（虛線橘圈＝低樣本 n<5）", color="#ffffff", fontsize=14, fontweight="bold", pad=14)
    fig.tight_layout()
    p1 = out_dir / "01_meta_quadrant.png"
    fig.savefig(str(p1), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    created.append(str(p1))

    # ------------------------------------------------------------------
    # Card 2: 0 vs 1 vs 2 Copies Marginal Rank Impact (Double-Pick ROI)
    # ------------------------------------------------------------------
    top_dp = [r for r in occ_list if r["team_count"] >= 1][::-1]
    fig, ax = plt.subplots(figsize=(12.0, max(6.8, len(top_dp) * 0.62)), facecolor="#0f172a")
    ax.set_facecolor("#162033")

    y_pos = np.arange(len(top_dp))
    ax.axvline(avg_r, color="#64748b", linestyle="--", linewidth=1.2, label=f"全體平均排名 (#{avg_r:.1f})")

    # Compute x span to detect close labels between copy_0 and copy_1
    all_pts = [
        r[k]["avg_rank"]
        for r in top_dp
        for k in ("copy_0", "copy_1", "copy_2")
        if r[k]["teams"] > 0 and r[k]["avg_rank"] is not None
    ]
    x_span = max(10.0, (max(all_pts) - min(all_pts)) if all_pts else 30.0)

    for idx, r in enumerate(top_dp):
        pts = []
        r0 = r["copy_0"]["avg_rank"] if r["copy_0"]["teams"] > 0 else None
        r1 = r["copy_1"]["avg_rank"] if r["copy_1"]["teams"] > 0 else None
        close_01 = (r0 is not None and r1 is not None and abs(r0 - r1) < x_span * 0.11)

        for c_key, color, marker, sz, dy_off, va_align in [
            ("copy_0", "#94a3b8", "o", 72, 0.25 if not close_01 else -0.27, "bottom" if not close_01 else "top"),
            ("copy_1", "#38bdf8", "s", 95, 0.25, "bottom"),
            ("copy_2", "#f43f5e", "D", 112, -0.27, "top"),
        ]:
            st = r[c_key]
            if st["teams"] > 0 and st["avg_rank"] is not None:
                pts.append(st["avg_rank"])
                ax.scatter([st["avg_rank"]], [idx], color=color, marker=marker, s=sz, zorder=5, edgecolors="#0f172a", linewidths=0.8)
                ax.text(
                    st["avg_rank"],
                    idx + dy_off,
                    f"#{st['avg_rank']:.1f} ({st['teams']}隊)",
                    color=color,
                    ha="center",
                    va=va_align,
                    fontsize=8.2,
                    fontweight="bold" if c_key == "copy_2" else "normal",
                )
        if len(pts) >= 2:
            ax.plot([min(pts), max(pts)], [idx, idx], color="#475569", linewidth=2.0, zorder=3)

        rgba = _load_icon_rgba(icon_paths_by_name.get(r["occupation"], ""), size=26)
        if rgba is not None:
            ab_l = AnnotationBbox(OffsetImage(rgba, zoom=0.85), (0.0, idx), xycoords=("axes fraction", "data"), xybox=(-18, 0), boxcoords="offset points", frameon=False, clip_on=False)
            ax.add_artist(ab_l)

    ax.scatter([], [], color="#94a3b8", marker="o", s=72, label="帶 0 隻（不帶）")
    ax.scatter([], [], color="#38bdf8", marker="s", s=95, label="帶 1 隻（單職業）")
    ax.scatter([], [], color="#f43f5e", marker="D", s=112, label="帶 2 隻（雙職業）")

    ax.set_yticks(y_pos)
    ax.set_yticklabels([r["occupation"] for r in top_dp], color="#f8fafc", fontsize=11, fontweight="bold")
    ax.tick_params(axis="y", pad=34)
    ax.tick_params(axis="x", colors="#cbd5e1")
    ax.set_ylim(-0.75, len(top_dp) - 0.25)
    ax.invert_xaxis()
    ax.set_xlabel("平均排名（越靠右側代表排名越高 →）", color="#e2e8f0", fontsize=11, fontweight="bold")
    ax.grid(axis="x", color="#334155", linestyle=":", alpha=0.6)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    # Place legend cleanly above the plot so it NEVER overlaps bottom-left rows!
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.06),
        ncol=4,
        facecolor="#0f172a",
        edgecolor="#475569",
        labelcolor="#f8fafc",
        fontsize=9.5,
    )
    ax.set_title(f"{title}｜0 隻 vs 1 隻（單職業）vs 2 隻（雙職業）平均排名影響\n{subtitle}", color="#ffffff", fontsize=13.5, fontweight="bold", pad=34)
    fig.tight_layout()
    p2 = out_dir / "02_copy_count_impact.png"
    fig.savefig(str(p2), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    created.append(str(p2))

    # ------------------------------------------------------------------
    # Card 3: Non-Overlapping Rank Tier Heatmap + Double-Pick Structure
    # ------------------------------------------------------------------
    tiers = [t["tier"] for t in analytics["ranking_analysis"]["tiers"]]
    tier_counts = {t["tier"]: t["team_count"] for t in analytics["ranking_analysis"]["tiers"]}
    heat_occs = occ_list[:14]
    heat_mat = np.array(
        [[r["tier_rates"].get(t, 0.0) * 100 for t in tiers] for r in heat_occs],
        dtype=np.float32,
    )

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(13.0, max(6.0, len(heat_occs) * 0.45)), gridspec_kw={"width_ratios": [1.35, 1.0]}, facecolor="#0f172a"
    )
    fig.suptitle(f"{title}｜各名次區間職業出場率 ＆ 雙職業組隊結構\n{subtitle}（左邊越高＝強隊越愛帶）", color="#ffffff", fontsize=14, fontweight="bold", y=0.97)

    # Left: Rank Bracket Popularity Table
    ax1.set_facecolor("#162033")
    im = ax1.imshow(heat_mat, cmap="YlGnBu", aspect="auto", vmin=0, vmax=100)
    ax1.set_xticks(np.arange(len(tiers)))
    ax1.set_xticklabels([f"{t} 名\n({tier_counts[t]}隊)" for t in tiers], color="#f8fafc", fontsize=10, fontweight="bold")
    ax1.set_yticks(np.arange(len(heat_occs)))
    ax1.set_yticklabels([r["occupation"] for r in heat_occs], color="#f8fafc", fontsize=10.5, fontweight="bold")
    for i in range(len(heat_occs)):
        for j in range(len(tiers)):
            val = heat_mat[i, j]
            txt_col = "#ffffff" if val >= 48 else "#0f172a"
            ax1.text(j, i, f"{val:.0f}%", ha="center", va="center", color=txt_col, fontsize=9.5, fontweight="bold")
    ax1.set_title("各名次區間有幾 % 隊伍帶該職業（深色＝越熱門）", color="#e2e8f0", fontsize=11, fontweight="bold", pad=10)

    # Right: Double-pick structure bars
    ax2.set_facecolor("#162033")
    dp_rows = analytics.get("double_pick_structure", [])
    if dp_rows:
        y_dp = np.arange(len(dp_rows))[::-1]
        rates_dp = [d["team_rate"] * 100 for d in dp_rows]
        bars = ax2.barh(y_dp, rates_dp, color="#a855f7", height=0.55)
        ax2.set_yticks(y_dp)
        ax2.set_yticklabels([d["label"] for d in dp_rows], color="#f8fafc", fontsize=10, fontweight="bold")
        ax2.set_xlim(0, max(max(rates_dp) * 1.42, 35))
        for b, d in zip(bars, dp_rows):
            ax2.text(
                d["team_rate"] * 100 + 1.2,
                b.get_y() + b.get_height() / 2,
                f"{d['team_rate']*100:.1f}% ({d['team_count']}隊｜均排 #{d['avg_rank']:.1f})",
                va="center",
                color="#e2e8f0",
                fontsize=9.2,
                fontweight="bold",
            )
    ax2.set_xlabel("隊伍佔比 (%)", color="#cbd5e1", fontsize=10.5)
    ax2.tick_params(axis="x", colors="#cbd5e1")
    ax2.grid(axis="x", color="#334155", linestyle=":", alpha=0.55)
    for spine in ax2.spines.values():
        spine.set_color("#334155")
    ax2.set_title("戰隊「雙職業組數」配置與平均排名", color="#e2e8f0", fontsize=11.5, fontweight="bold", pad=10)

    fig.tight_layout(rect=[0, 0, 1, 0.91])
    p3 = out_dir / "03_tier_heatmap_and_doubles.png"
    fig.savefig(str(p3), dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    created.append(str(p3))

    # ------------------------------------------------------------------
    # Card 4: Occupation Synergy & Substitution Matrix (Pairwise Lift)
    # ------------------------------------------------------------------
    syn = analytics.get("synergy_matrix", {})
    labels = syn.get("labels", [])
    vals = np.array(syn.get("values", []), dtype=np.float32)
    if len(labels) >= 2 and vals.size > 0:
        fig, ax = plt.subplots(figsize=(10.2, 8.8), facecolor="#0f172a")
        ax.set_facecolor("#162033")
        # Diverging colormap centered at 1.0: Blue (<1 substitution) <-> White (1.0 neutral) <-> Red (>1 synergy)
        im = ax.imshow(vals, cmap="coolwarm", vmin=0.4, vmax=1.6)
        ax.set_xticks(np.arange(len(labels)))
        ax.set_yticks(np.arange(len(labels)))
        ax.set_xticklabels(labels, rotation=40, ha="right", color="#f8fafc", fontsize=10, fontweight="bold")
        ax.set_yticklabels(labels, color="#f8fafc", fontsize=10, fontweight="bold")
        for i in range(len(labels)):
            for j in range(len(labels)):
                if i == j:
                    ax.text(j, i, "—", ha="center", va="center", color="#64748b", fontsize=9)
                else:
                    v = vals[i, j]
                    col = "#0f172a" if 0.65 <= v <= 1.35 else "#ffffff"
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center", color=col, fontsize=8.2, fontweight="bold" if (v >= 1.15 or v <= 0.80) else "normal")
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("搭檔倍率（紅 >1.15 常見綁定搭檔｜藍 <0.85 二選一搶位組合）", color="#f8fafc", fontsize=10)
        cbar.ax.tick_params(colors="#cbd5e1")
        ax.set_title(f"{title}｜常見綁定搭檔 ＆ 二選一搶位矩陣（搭檔倍率）\n{subtitle}", color="#ffffff", fontsize=13.5, fontweight="bold", pad=14)
        fig.tight_layout()
        p4 = out_dir / "04_synergy_matrix.png"
        fig.savefig(str(p4), dpi=180, facecolor=fig.get_facecolor())
        plt.close(fig)
        created.append(str(p4))

    return created
