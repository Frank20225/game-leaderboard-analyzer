"""Standalone Phase 3 runner: icon clustering, debug visuals & database persistence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.config import ICON_DB_DIR
from src.icons.clusterer import EMPTY_LABEL, IconCluster, IconInstance, cluster_team_icons
from src.icons.database import IconDatabase


def _load_font(size: int = 16) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for fp in (r"C:\Windows\Fonts\msjh.ttc", r"C:\Windows\Fonts\tahoma.ttf"):
        if Path(fp).is_file():
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_clusters_contact_sheet(
    clusters: list[IconCluster], instances_by_id: dict[str, IconInstance], output_path: Path
) -> None:
    """Render a clean gallery card sheet of all icon clusters for instant visual purity check."""
    if not clusters:
        return

    row_h = 72
    icon_sz = 46
    max_samples = 12
    left_col_w = 270
    total_w = left_col_w + max_samples * (icon_sz + 8) + 24
    header_h = 44
    canvas = Image.new("RGB", (total_w, header_h + len(clusters) * row_h), (248, 250, 252))
    draw = ImageDraw.Draw(canvas)
    font = _load_font(16)
    font_sm = _load_font(13)

    draw.rectangle([(0, 0), (total_w, header_h)], fill=(15, 23, 42))
    draw.text(
        (14, 12),
        f"Phase 3 Icon Clusters ({len(clusters)} groups) - Medoid & Sample Thumbnails",
        fill=(255, 255, 255),
        font=font,
    )

    for idx, cl in enumerate(clusters):
        y0 = header_h + idx * row_h
        bg = (255, 255, 255) if idx % 2 == 0 else (241, 245, 249)
        if cl.cluster_id == "EMPTY":
            bg = (254, 249, 195)
        draw.rectangle([(0, y0), (total_w, y0 + row_h)], fill=bg)
        draw.line([(0, y0 + row_h - 1), (total_w, y0 + row_h - 1)], fill=(203, 213, 225), width=1)

        # Representative icon
        rep_bgr = cv2.imread(cl.representative_norm_path)
        if rep_bgr is not None:
            rep_pil = Image.fromarray(cv2.cvtColor(rep_bgr, cv2.COLOR_BGR2RGB)).resize((icon_sz, icon_sz))
            canvas.paste(rep_pil, (12, y0 + (row_h - icon_sz) // 2))
            draw.rectangle(
                [(11, y0 + (row_h - icon_sz) // 2 - 1), (12 + icon_sz, y0 + (row_h + icon_sz) // 2)],
                outline=(37, 99, 235),
                width=2,
            )

        title = f"{cl.cluster_id} ({cl.confirmed_name or cl.suggested_name})"
        meta_txt = f"n={cl.count} | avg={cl.avg_internal_sim:.2f} | min={cl.min_internal_sim:.2f}"
        draw.text((70, y0 + 12), title, fill=(15, 23, 42), font=font)
        draw.text((70, y0 + 38), meta_txt, fill=(71, 85, 105), font=font_sm)

        # Up to 12 member thumbnails
        for s_idx, inst_id in enumerate(cl.sample_instance_ids[:max_samples]):
            inst = instances_by_id.get(inst_id)
            if not inst:
                continue
            ibgr = cv2.imread(inst.norm_path)
            if ibgr is None:
                continue
            ipil = Image.fromarray(cv2.cvtColor(ibgr, cv2.COLOR_BGR2RGB)).resize((icon_sz, icon_sz))
            x_pos = left_col_w + s_idx * (icon_sz + 8)
            canvas.paste(ipil, (x_pos, y0 + (row_h - icon_sz) // 2))

    canvas.save(str(output_path))


def render_similarity_heatmap(sim_matrix: np.ndarray, output_path: Path) -> None:
    """Save a block-diagonal sorted similarity matrix heatmap (ideal for learning & purity audit)."""
    if sim_matrix.size == 0:
        return
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    im = ax.imshow(sim_matrix, cmap="viridis", vmin=0.2, vmax=1.0)
    ax.set_title("Phase 3: Sorted Icon Pairwise Similarity Matrix\n(Crisp bright diagonal blocks = pure occupation clusters)", fontsize=11)
    ax.set_xlabel("Icons (sorted by cluster)")
    ax.set_ylabel("Icons (sorted by cluster)")
    fig.colorbar(im, ax=ax, label="Combined Similarity (Cosine + NCC)")
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=150)
    plt.close(fig)


def apply_labels_to_teams(
    teams: list[dict],
    instances: list[IconInstance],
    cluster_name_map: dict[str, str],
    instance_overrides: dict[str, str] | None = None,
) -> list[dict]:
    """Write confirmed occupation names back into each team's 8-slot list."""
    overrides = instance_overrides or {}
    by_rank_slot: dict[tuple[int, int], tuple[str, float]] = {}

    for inst in instances:
        if inst.is_empty:
            name = EMPTY_LABEL
            conf = 1.0
        elif inst.instance_id in overrides and overrides[inst.instance_id].strip():
            name = overrides[inst.instance_id].strip()
            conf = 1.0
        else:
            name = cluster_name_map.get(inst.cluster_id, inst.assigned_name or inst.cluster_id).strip()
            conf = inst.confidence
        inst.assigned_name = name
        by_rank_slot[(inst.rank, inst.slot)] = (name, conf)

    updated = []
    for t in teams:
        t_copy = dict(t)
        rank = int(t["rank"])
        occs = []
        confs = []
        for s in range(8):
            nm, cf = by_rank_slot.get((rank, s), ("", 0.0))
            occs.append(nm)
            confs.append(round(cf, 4))
        t_copy["occupations"] = occs
        t_copy["occupation_confs"] = confs
        updated.append(t_copy)
    return updated


def run_phase3(
    run_dir: str | Path,
    db_dir: str | Path = ICON_DB_DIR,
    db_match_threshold: float = 0.84,
    cluster_distance_threshold: float = 0.22,
) -> dict:
    """Execute Phase 3 icon clustering on a Phase 2 run_dir."""
    run_path = Path(run_dir)
    p2_teams_path = run_path / "phase2_extracted" / "teams_raw.json"
    if not p2_teams_path.is_file():
        raise FileNotFoundError(f"找不到 Phase 2 隊伍資料: {p2_teams_path}")

    teams = json.loads(p2_teams_path.read_text(encoding="utf-8"))
    phase3_dir = run_path / "phase3_icons"
    phase3_dir.mkdir(parents=True, exist_ok=True)

    icon_db = IconDatabase(db_dir=db_dir)
    instances, clusters, sim_mat, _ = cluster_team_icons(
        teams=teams,
        output_dir=phase3_dir,
        icon_db=icon_db,
        db_match_threshold=db_match_threshold,
        cluster_distance_threshold=cluster_distance_threshold,
    )

    # Apply initial cluster names (DB names or temporary 職業_01..NN) to teams
    init_map = {c.cluster_id: (c.confirmed_name or c.suggested_name) for c in clusters}
    teams_with_icons = apply_labels_to_teams(teams, instances, init_map)

    inst_by_id = {i.instance_id: i for i in instances}
    sheet_path = phase3_dir / "debug_clusters_sheet.png"
    heatmap_path = phase3_dir / "debug_similarity_matrix.png"
    render_clusters_contact_sheet(clusters, inst_by_id, sheet_path)
    render_similarity_heatmap(sim_mat, heatmap_path)

    payload = {
        "total_icons": len(instances),
        "empty_slot_count": sum(1 for i in instances if i.is_empty),
        "db_matched_count": sum(1 for i in instances if i.matched_from_db),
        "cluster_count": sum(1 for c in clusters if c.cluster_id != "EMPTY"),
        "clusters": [c.to_dict() for c in clusters],
        "instances": [i.to_dict() for i in instances],
        "clusters_sheet_path": str(sheet_path),
        "similarity_heatmap_path": str(heatmap_path),
    }
    (phase3_dir / "clusters.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (phase3_dir / "teams_with_icons.json").write_text(
        json.dumps(teams_with_icons, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def confirm_clusters_and_save_db(
    run_dir: str | Path,
    cluster_name_map: dict[str, str],
    instance_overrides: dict[str, str] | None = None,
    save_to_db: bool = True,
    db_dir: str | Path = ICON_DB_DIR,
) -> dict:
    """Persist human-confirmed cluster labels back to run_dir AND reusable IconDatabase.

    Handles renaming/merging cleanly:
    - If a DB-matched cluster (`DB_<old>`) is renamed to `<new>`, removes `<old>` from
      the persistent DB and merges its templates into `<new>` (no zombie duplicates!).
    - Merges clusters that were given the same confirmed name into a single cluster card.
    - Preserves any manual team_name / score edits previously saved in Step 4.
    """
    run_path = Path(run_dir)
    phase3_dir = run_path / "phase3_icons"
    clusters_path = phase3_dir / "clusters.json"
    p3_teams_path = phase3_dir / "teams_with_icons.json"
    p2_teams_path = run_path / "phase2_extracted" / "teams_raw.json"

    p3 = json.loads(clusters_path.read_text(encoding="utf-8"))
    # Prefer teams_with_icons.json if present so prior Step 4 team_name/score edits are preserved
    base_teams_path = p3_teams_path if p3_teams_path.is_file() else p2_teams_path
    teams = json.loads(base_teams_path.read_text(encoding="utf-8"))
    instances = [IconInstance(**i) for i in p3["instances"]]
    clusters = [IconCluster(**c) for c in p3["clusters"]]

    updated_teams = apply_labels_to_teams(teams, instances, cluster_name_map, instance_overrides)

    inst_by_id = {i.instance_id: i for i in instances}
    icon_db = IconDatabase(db_dir=db_dir) if save_to_db else None

    # 1. Update persistent DB (rename/merge old DB keys first so zombie entries are removed)
    merged_groups: dict[str, list[IconCluster]] = {}
    empty_clusters: list[IconCluster] = []

    for c in clusters:
        if c.cluster_id == "EMPTY":
            empty_clusters.append(c)
            continue

        old_db_name = c.cluster_id[3:] if c.cluster_id.startswith("DB_") else ""
        new_name = cluster_name_map.get(c.cluster_id, c.confirmed_name or c.suggested_name).strip()
        c.confirmed_name = new_name
        c.needs_review = False

        if icon_db is not None and new_name and new_name != EMPTY_LABEL:
            if old_db_name and old_db_name != new_name:
                icon_db.rename_occupation(old_db_name, new_name)
            sample_imgs = []
            for iid in c.sample_instance_ids[:5]:
                inst = inst_by_id.get(iid)
                if inst and not inst.is_empty:
                    img = cv2.imread(inst.crop_path)
                    if img is not None:
                        sample_imgs.append(img)
            if sample_imgs:
                icon_db.upsert_occupation(new_name, sample_imgs)

        merged_groups.setdefault(new_name or c.cluster_id, []).append(c)

    # 2. Merge clusters that now share the same confirmed name into unified cluster cards
    unified_clusters: list[IconCluster] = []
    for name_key, grp in merged_groups.items():
        primary = max(grp, key=lambda x: x.count)
        new_cid = f"DB_{name_key}" if save_to_db and name_key and name_key != EMPTY_LABEL else primary.cluster_id
        all_ids: list[str] = []
        sample_ids: list[str] = []
        for g in grp:
            for iid in g.all_instance_ids:
                if iid not in all_ids:
                    all_ids.append(iid)
                if iid in inst_by_id:
                    inst_by_id[iid].cluster_id = new_cid
                    inst_by_id[iid].assigned_name = name_key
            for sid in g.sample_instance_ids:
                if sid not in sample_ids:
                    sample_ids.append(sid)

        total_n = sum(g.count for g in grp)
        avg_sim = sum(g.avg_internal_sim * g.count for g in grp) / max(1, total_n)
        min_sim = min(g.min_internal_sim for g in grp)
        unified_clusters.append(
            IconCluster(
                cluster_id=new_cid,
                suggested_name=name_key,
                confirmed_name=name_key,
                matched_from_db=bool(save_to_db) or any(g.matched_from_db for g in grp),
                count=len(all_ids),
                avg_internal_sim=round(avg_sim, 4),
                min_internal_sim=round(min_sim, 4),
                representative_norm_path=primary.representative_norm_path,
                sample_instance_ids=sample_ids[:12],
                all_instance_ids=all_ids,
                needs_review=False,
            )
        )

    unified_clusters.sort(key=lambda c: (-c.count, c.confirmed_name))
    unified_clusters.extend(empty_clusters)

    p3["cluster_count"] = sum(1 for c in unified_clusters if c.cluster_id != "EMPTY")
    p3["clusters"] = [c.to_dict() for c in unified_clusters]
    p3["instances"] = [i.to_dict() for i in instances]
    clusters_path.write_text(json.dumps(p3, ensure_ascii=False, indent=2), encoding="utf-8")
    p3_teams_path.write_text(
        json.dumps(updated_teams, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    render_clusters_contact_sheet(unified_clusters, inst_by_id, phase3_dir / "debug_clusters_sheet.png")
    return {"clusters": p3["clusters"], "teams": updated_teams}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m src.pipeline_phase3 <existing_run_dir>")
        sys.exit(1)
    res = run_phase3(sys.argv[1])
    summary = {k: v for k, v in res.items() if k != "instances"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
