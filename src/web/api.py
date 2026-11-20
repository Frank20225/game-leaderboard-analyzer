"""FastAPI backend for Game Leaderboard Analyzer local Web UI.

Provides REST endpoints for:
- Native Windows read-only MP4 file picker (no large file upload/copy needed)
- Phase 1 (Video Analysis & ROI fine-tuning), Phase 2 (Async OCR + Audit),
  Phase 3 (Icon Clustering + Naming/Merging + DB persistence),
  Human Error Correction, Phase 4 & 5 (Excel + HTML + PNG + Summary Export),
  GitHub Pages publishing, and Behind-the-Scenes Learning Inspector.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import DOCS_DIR, ICON_DB_DIR, OUTPUTS_DIR, ensure_base_dirs
from src.export.pages_publisher import publish_to_github_pages
from src.icons.database import IconDatabase
from src.layout.detector import LayoutConfig, render_roi_debug_overlay
from src.pipeline_phase1 import run_phase1
from src.pipeline_phase2 import run_phase2
from src.pipeline_phase3 import confirm_clusters_and_save_db, run_phase3
from src.pipeline_phase4_5 import run_phase4_5

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Game Leaderboard Analyzer", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory background job tracker for long-running Phase 1/2 tasks
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _resolve_run_dir(run_id: str) -> Path:
    """Safely resolve a run directory inside OUTPUTS_DIR (prevents path traversal)."""
    if "/" in run_id or "\\" in run_id or ".." in run_id:
        raise HTTPException(status_code=400, detail="無效的 run_id")
    run_path = (OUTPUTS_DIR / run_id).resolve()
    if not str(run_path).startswith(str(OUTPUTS_DIR.resolve())) or not run_path.is_dir():
        raise HTTPException(status_code=404, detail=f"找不到分析紀錄: {run_id}")
    return run_path


def _start_bg_job(job_type: str, target_fn) -> str:
    job_id = uuid.uuid4().hex[:10]
    with _JOBS_LOCK:
        _JOBS[job_id] = {"job_id": job_id, "type": job_type, "status": "running", "result": None, "error": None}

    def _runner():
        try:
            res = target_fn()
            with _JOBS_LOCK:
                _JOBS[job_id]["status"] = "completed"
                _JOBS[job_id]["result"] = res
        except Exception as exc:
            with _JOBS_LOCK:
                _JOBS[job_id]["status"] = "failed"
                _JOBS[job_id]["error"] = str(exc)

    threading.Thread(target=_runner, daemon=True).start()
    return job_id


class Phase1Request(BaseModel):
    video_path: str
    run_name: str | None = None


class LayoutUpdateRequest(BaseModel):
    panel_box: list[int]
    scroll_area_ratio: list[float]
    personal_row_ratio: list[float]
    rank_x_ratio: list[float]
    team_name_x_ratio: list[float]
    icons_x_ratio: list[float]
    score_x_ratio: list[float]
    icon_centers_x_ratio: list[float]


class ClusterConfirmRequest(BaseModel):
    cluster_name_map: dict[str, str]
    instance_overrides: dict[str, str] = Field(default_factory=dict)
    save_to_db: bool = True


class TeamEditItem(BaseModel):
    rank: int
    team_name: str
    score: int | None = None
    occupations: list[str]
    status: str = "edited"


class TeamsUpdateRequest(BaseModel):
    updates: list[TeamEditItem]


class ExportRequest(BaseModel):
    report_title: str = "排位賽職業環境分析報告"


class PublishPagesRequest(BaseModel):
    report_slug: str | None = None


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, str]:
    ensure_base_dirs()
    return {"status": "ok"}


@app.post("/api/pick-video")
def pick_video_file() -> dict[str, str]:
    """Open native Windows file picker dialog to select an MP4 without copying/modifying it."""
    selected = {"path": ""}

    def _open_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            p = filedialog.askopenfilename(
                title="選擇 OBS 錄製的遊戲排行榜影片（唯讀開啟，不會修改原檔）",
                filetypes=[("MP4 Videos", "*.mp4"), ("All Videos", "*.mp4;*.mkv;*.mov;*.avi"), ("All Files", "*.*")],
            )
            root.destroy()
            selected["path"] = p or ""
        except Exception:
            selected["path"] = ""

    # Run tkinter dialog in a dedicated thread to avoid blocking FastAPI event loop
    t = threading.Thread(target=_open_dialog)
    t.start()
    t.join(timeout=120)
    return {"video_path": selected["path"]}


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    ensure_base_dirs()
    runs: list[dict[str, Any]] = []
    for d in sorted(OUTPUTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        p1_file = d / "phase1_frames" / "phase1_summary.json"
        p2_audit = d / "phase2_extracted" / "audit_report.json"
        p3_file = d / "phase3_icons" / "clusters.json"
        share_manifest = d / "share" / "manifest.json"
        runs.append(
            {
                "run_id": d.name,
                "has_phase1": p1_file.is_file(),
                "has_phase2": p2_audit.is_file(),
                "has_phase3": p3_file.is_file(),
                "has_export": share_manifest.is_file(),
                "video_name": json.loads(p1_file.read_text(encoding="utf-8")).get("metadata", {}).get("filename", "")
                if p1_file.is_file()
                else "",
            }
        )
    return runs


@app.get("/api/runs/{run_id}")
def get_run_state(run_id: str) -> dict[str, Any]:
    run_path = _resolve_run_dir(run_id)
    state: dict[str, Any] = {"run_id": run_id, "run_dir": str(run_path)}

    p1 = run_path / "phase1_frames" / "phase1_summary.json"
    if p1.is_file():
        state["phase1"] = json.loads(p1.read_text(encoding="utf-8"))

    p2_audit = run_path / "phase2_extracted" / "audit_report.json"
    p2_teams = run_path / "phase2_extracted" / "teams_raw.json"
    p2_issues = run_path / "phase2_extracted" / "issues.json"
    if p2_audit.is_file():
        state["phase2_audit"] = json.loads(p2_audit.read_text(encoding="utf-8"))
        state["issues"] = json.loads(p2_issues.read_text(encoding="utf-8")) if p2_issues.is_file() else []
        state["teams"] = json.loads(p2_teams.read_text(encoding="utf-8")) if p2_teams.is_file() else []

    p3 = run_path / "phase3_icons" / "clusters.json"
    p3_teams = run_path / "phase3_icons" / "teams_with_icons.json"
    if p3.is_file():
        state["phase3"] = json.loads(p3.read_text(encoding="utf-8"))
        if p3_teams.is_file():
            state["teams"] = json.loads(p3_teams.read_text(encoding="utf-8"))

    manifest = run_path / "share" / "manifest.json"
    if manifest.is_file():
        state["export"] = json.loads(manifest.read_text(encoding="utf-8"))

    return state


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="找不到背景任務")
    return job


@app.post("/api/phase1")
def start_phase1(req: Phase1Request) -> dict[str, Any]:
    video_p = Path(req.video_path)
    if not video_p.is_file():
        raise HTTPException(status_code=400, detail=f"找不到影片檔案: {req.video_path}")

    run_dir = OUTPUTS_DIR / req.run_name if req.run_name else None

    def _work():
        res = run_phase1(video_p, run_dir=run_dir)
        out_run_id = Path(res.summary_json_path).parent.parent.name
        return {"run_id": out_run_id, "phase1": res.to_dict()}

    job_id = _start_bg_job("phase1", _work)
    return {"job_id": job_id}


@app.post("/api/runs/{run_id}/layout")
def update_layout(run_id: str, req: LayoutUpdateRequest) -> dict[str, Any]:
    """Allow manual ROI fine-tuning and re-render the debug overlay immediately."""
    run_path = _resolve_run_dir(run_id)
    p1_path = run_path / "phase1_frames" / "phase1_summary.json"
    if not p1_path.is_file():
        raise HTTPException(status_code=400, detail="請先執行 Phase 1 影片分析")

    p1 = json.loads(p1_path.read_text(encoding="utf-8"))
    layout = LayoutConfig(**p1["layout"])
    layout.panel_box = req.panel_box
    layout.scroll_area_ratio = req.scroll_area_ratio
    layout.personal_row_ratio = req.personal_row_ratio
    layout.rank_x_ratio = req.rank_x_ratio
    layout.team_name_x_ratio = req.team_name_x_ratio
    layout.icons_x_ratio = req.icons_x_ratio
    layout.score_x_ratio = req.score_x_ratio
    layout.icon_centers_x_ratio = req.icon_centers_x_ratio
    layout.save(run_path / "phase1_frames" / "layout.json")

    p1["layout"] = layout.to_dict()
    p1_path.write_text(json.dumps(p1, ensure_ascii=False, indent=2), encoding="utf-8")

    # Re-render ROI debug overlay on first keyframe
    if p1.get("keyframes"):
        first_kf = cv2.imread(p1["keyframes"][0]["image_path"])
        if first_kf is not None:
            vis = render_roi_debug_overlay(first_kf, layout)
            cv2.imwrite(str(run_path / "phase1_frames" / "debug_roi_overlay.png"), vis)

    return {"status": "updated", "layout": layout.to_dict()}


@app.post("/api/runs/{run_id}/phase2")
def start_phase2(run_id: str) -> dict[str, Any]:
    run_path = _resolve_run_dir(run_id)

    def _work():
        teams, issues, audit = run_phase2(run_path)
        return {
            "run_id": run_id,
            "audit": audit.to_dict(),
            "team_count": len(teams),
            "issue_count": len(issues),
        }

    job_id = _start_bg_job("phase2", _work)
    return {"job_id": job_id}


@app.post("/api/runs/{run_id}/phase3")
def trigger_phase3(run_id: str) -> dict[str, Any]:
    run_path = _resolve_run_dir(run_id)
    res = run_phase3(run_path)
    return {
        "run_id": run_id,
        "total_icons": res["total_icons"],
        "empty_slot_count": res["empty_slot_count"],
        "db_matched_count": res["db_matched_count"],
        "cluster_count": res["cluster_count"],
    }


@app.post("/api/runs/{run_id}/icons/confirm")
def confirm_icons(run_id: str, req: ClusterConfirmRequest) -> dict[str, Any]:
    run_path = _resolve_run_dir(run_id)
    res = confirm_clusters_and_save_db(
        run_dir=run_path,
        cluster_name_map=req.cluster_name_map,
        instance_overrides=req.instance_overrides,
        save_to_db=req.save_to_db,
        db_dir=ICON_DB_DIR,
    )
    return {"status": "saved", "cluster_count": len(res["clusters"]), "team_count": len(res["teams"])}


@app.get("/api/icon-db")
def get_icon_db() -> list[dict[str, Any]]:
    db = IconDatabase(ICON_DB_DIR)
    return db.list_occupations()


@app.post("/api/runs/{run_id}/teams/update")
def update_teams(run_id: str, req: TeamsUpdateRequest) -> dict[str, Any]:
    """Save human corrections for team names, scores, or occupations."""
    run_path = _resolve_run_dir(run_id)
    p3_teams_path = run_path / "phase3_icons" / "teams_with_icons.json"
    p2_teams_path = run_path / "phase2_extracted" / "teams_raw.json"
    target_path = p3_teams_path if p3_teams_path.is_file() else p2_teams_path
    if not target_path.is_file():
        raise HTTPException(status_code=400, detail="找不到隊伍資料檔")

    teams = json.loads(target_path.read_text(encoding="utf-8"))
    by_rank = {int(t["rank"]): t for t in teams}
    updated_count = 0

    for item in req.updates:
        if item.rank in by_rank:
            t = by_rank[item.rank]
            t["team_name"] = item.team_name.strip()
            t["score"] = item.score
            t["occupations"] = (item.occupations + [""] * 8)[:8]
            t["status"] = item.status
            t["flags"] = []
            updated_count += 1

    merged = [by_rank[r] for r in sorted(by_rank.keys())]
    target_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "updated", "updated_count": updated_count}


@app.post("/api/runs/{run_id}/export")
def export_reports(run_id: str, req: ExportRequest) -> dict[str, Any]:
    run_path = _resolve_run_dir(run_id)
    manifest = run_phase4_5(run_path, report_title=req.report_title)
    return manifest


@app.post("/api/runs/{run_id}/publish-pages")
def publish_pages(run_id: str, req: PublishPagesRequest) -> dict[str, Any]:
    run_path = _resolve_run_dir(run_id)
    analytics_path = run_path / "phase4_stats" / "analytics.json"
    if not analytics_path.is_file():
        raise HTTPException(status_code=400, detail="請先執行「產出報告與分享包」再發佈至 GitHub Pages")
    analytics = json.loads(analytics_path.read_text(encoding="utf-8"))
    res = publish_to_github_pages(
        share_dir=run_path / "share",
        analytics=analytics,
        report_slug=req.report_slug,
        docs_dir=DOCS_DIR,
    )
    return res


@app.post("/api/runs/{run_id}/open-folder")
def open_output_folder(run_id: str) -> dict[str, str]:
    run_path = _resolve_run_dir(run_id)
    if os.name == "nt":
        os.startfile(str(run_path))  # type: ignore[attr-defined]
    return {"opened": str(run_path)}


@app.get("/api/runs/{run_id}/files/{rel_path:path}")
def serve_run_file(run_id: str, rel_path: str) -> FileResponse:
    """Serve images, Excel reports, or HTML files safely from inside a specific run directory."""
    run_path = _resolve_run_dir(run_id)
    target = (run_path / rel_path).resolve()
    if not str(target).startswith(str(run_path)) or not target.is_file():
        raise HTTPException(status_code=404, detail=f"找不到檔案: {rel_path}")
    return FileResponse(str(target))
