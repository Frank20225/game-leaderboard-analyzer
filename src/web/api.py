"""FastAPI backend for Game Leaderboard Analyzer local Web UI.

Provides REST endpoints for:
- Native Windows read-only MP4 file picker (no large file upload/copy needed)
- Phase 1 (Video Analysis & ROI fine-tuning), Phase 2 (Async OCR + Audit),
  Phase 3 (Icon Clustering + Naming/Merging + DB persistence),
  Human Error Correction, Phase 4 & 5 (Excel + HTML + PNG + Summary Export),
  GitHub Pages publishing, and Behind-the-Scenes Learning Inspector.
"""

from __future__ import annotations

import base64
from difflib import SequenceMatcher
import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.analytics.trends import compare_multiple_runs
from src.config import DOCS_DIR, ICON_DB_DIR, OUTPUTS_DIR, ensure_base_dirs
from src.export.pages_publisher import publish_to_github_pages, publish_trend_to_github_pages
from src.export.trend_export import export_trend_package
from src.icons.database import IconDatabase
from src.layout.detector import LayoutConfig, render_roi_debug_overlay
from src.ocr.text_ocr import MultilingualOcrEngine
from src.pipeline_phase1 import run_phase1
from src.pipeline_phase2 import run_phase2
from src.pipeline_phase3 import confirm_clusters_and_save_db, run_phase3
from src.pipeline_phase4_5 import run_phase4_5

TRENDS_DIR = OUTPUTS_DIR / "_trends"
_SCOUT_OCR_ENGINE: MultilingualOcrEngine | None = None
_SCOUT_OCR_LOCK = threading.Lock()

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
    """Start a background worker thread with live percent, message, elapsed & ETA tracking."""
    job_id = uuid.uuid4().hex[:10]
    started_at = time.monotonic()
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "type": job_type,
            "status": "running",
            "percent": 0.0,
            "message": "正在準備任務...",
            "elapsed_sec": 0.0,
            "eta_sec": None,
            "result": None,
            "error": None,
        }

    def report_progress(percent: float, message: str) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - started_at)
        pct = max(0.0, min(100.0, float(percent)))
        eta = round(elapsed * (100.0 - pct) / pct, 1) if pct >= 5.0 and pct < 100.0 else None
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job and job["status"] == "running":
                job["percent"] = round(pct, 1)
                job["message"] = message
                job["elapsed_sec"] = round(elapsed, 1)
                job["eta_sec"] = eta

    def _runner():
        try:
            res = target_fn(report_progress)
            elapsed = round(max(0.0, time.monotonic() - started_at), 1)
            with _JOBS_LOCK:
                _JOBS[job_id]["status"] = "completed"
                _JOBS[job_id]["percent"] = 100.0
                _JOBS[job_id]["message"] = "處理完成！"
                _JOBS[job_id]["elapsed_sec"] = elapsed
                _JOBS[job_id]["eta_sec"] = 0.0
                _JOBS[job_id]["result"] = res
        except Exception as exc:
            elapsed = round(max(0.0, time.monotonic() - started_at), 1)
            with _JOBS_LOCK:
                _JOBS[job_id]["status"] = "failed"
                _JOBS[job_id]["elapsed_sec"] = elapsed
                _JOBS[job_id]["eta_sec"] = None
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
    report_title: str = ""


class PublishPagesRequest(BaseModel):
    report_slug: str | None = None


class TrendSnapshotInput(BaseModel):
    run_id: str
    label: str = ""


class TrendCompareRequest(BaseModel):
    trend_title: str = "排位賽多期環境與戰隊趨勢對比"
    snapshots: list[TrendSnapshotInput]


class ScoutImageRequest(BaseModel):
    image_base64: str
    use_ocr: bool = True


def _extract_text_silhouette_vec(bgr: np.ndarray) -> np.ndarray | None:
    """Extract a scale-invariant 160x32 binary/grayscale silhouette vector of bright text."""
    if bgr is None or bgr.size == 0:
        return None
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    # Enhance contrast and isolate bright text strokes on dark game UI background
    norm = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    _, mask = cv2.threshold(norm, 145, 255, cv2.THRESH_BINARY)
    ys, xs = np.where(mask > 0)
    if len(xs) < 12 or len(ys) < 6:
        resized = cv2.resize(norm, (160, 32), interpolation=cv2.INTER_AREA)
    else:
        x1, x2 = max(0, int(np.percentile(xs, 2)) - 2), min(norm.shape[1], int(np.percentile(xs, 98)) + 3)
        y1, y2 = max(0, int(np.percentile(ys, 4)) - 2), min(norm.shape[0], int(np.percentile(ys, 96)) + 3)
        crop = norm[y1:y2, x1:x2] if (x2 > x1 + 4 and y2 > y1 + 4) else norm
        resized = cv2.resize(crop, (160, 32), interpolation=cv2.INTER_AREA)
    vec = resized.astype(np.float32).ravel()
    vec -= float(np.mean(vec))
    denom = float(np.linalg.norm(vec))
    return vec / denom if denom > 1e-6 else None


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


def _compute_period_sort_key(run_id: str, report_title: str, video_name: str) -> str:
    """Compute a chronological sort key (earliest -> latest) independent of filesystem mtime."""
    import re

    m_title = re.match(r"^(\d{2})(\d{2})", (report_title or "").strip())
    if m_title:
        return f"2026-{m_title.group(1)}-{m_title.group(2)}_{run_id}"
    if "next_week" in run_id.lower() or "week2" in run_id.lower():
        return f"2026-11-27_{run_id}"
    m_run = re.match(r"^(\d{4}-\d{2}-\d{2})", run_id)
    if m_run:
        return f"{m_run.group(1)}_{run_id}"
    m_vid = re.match(r"^(\d{4}-\d{2}-\d{2})", video_name or "")
    if m_vid:
        return f"{m_vid.group(1)}_{run_id}"
    return f"0000-00-00_{run_id}"


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    ensure_base_dirs()
    runs: list[dict[str, Any]] = []
    for d in sorted(OUTPUTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        p1_file = d / "phase1_frames" / "phase1_summary.json"
        p2_audit = d / "phase2_extracted" / "audit_report.json"
        p3_file = d / "phase3_icons" / "clusters.json"
        share_manifest = d / "share" / "manifest.json"
        video_name = (
            json.loads(p1_file.read_text(encoding="utf-8")).get("metadata", {}).get("filename", "")
            if p1_file.is_file()
            else ""
        )
        report_title = ""
        team_count = 0
        if share_manifest.is_file():
            try:
                mf = json.loads(share_manifest.read_text(encoding="utf-8"))
                report_title = mf.get("report_title", "")
                team_count = mf.get("overview", {}).get("total_teams", 0)
            except Exception:
                pass
        runs.append(
            {
                "run_id": d.name,
                "has_phase1": p1_file.is_file(),
                "has_phase2": p2_audit.is_file(),
                "has_phase3": p3_file.is_file(),
                "has_export": share_manifest.is_file(),
                "video_name": video_name,
                "report_title": report_title,
                "team_count": team_count,
                "period_sort_key": _compute_period_sort_key(d.name, report_title, video_name),
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

    def _work(report_progress):
        res = run_phase1(video_p, run_dir=run_dir, progress_cb=report_progress)
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

    def _work(report_progress):
        teams, issues, audit = run_phase2(run_path, progress_cb=report_progress)
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


def _resolve_trend_dir(trend_id: str) -> Path:
    if "/" in trend_id or "\\" in trend_id or ".." in trend_id:
        raise HTTPException(status_code=400, detail="無效的 trend_id")
    t_path = (TRENDS_DIR / trend_id).resolve()
    if not str(t_path).startswith(str(TRENDS_DIR.resolve())) or not t_path.is_dir():
        raise HTTPException(status_code=404, detail=f"找不到趨勢報告: {trend_id}")
    return t_path


@app.get("/api/trends")
def list_trends() -> list[dict[str, Any]]:
    TRENDS_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for d in sorted(TRENDS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        mp = d / "manifest.json"
        if d.is_dir() and mp.is_file():
            try:
                items.append(json.loads(mp.read_text(encoding="utf-8")))
            except Exception:
                continue
    return items


@app.post("/api/trends/compare")
def run_trend_comparison(req: TrendCompareRequest) -> dict[str, Any]:
    if len(req.snapshots) < 2:
        raise HTTPException(status_code=400, detail="請至少勾選 2 個已完成 Phase 3 的分析紀錄")

    loaded_snaps: list[dict[str, Any]] = []
    for item in req.snapshots:
        rp = _resolve_run_dir(item.run_id)
        teams_p = rp / "phase3_icons" / "teams_with_icons.json"
        if not teams_p.is_file():
            raise HTTPException(status_code=400, detail=f"紀錄 {item.run_id} 尚未完成 Phase 3 職業辨識")
        teams = json.loads(teams_p.read_text(encoding="utf-8"))
        loaded_snaps.append(
            {
                "run_id": item.run_id,
                "label": item.label.strip() or item.run_id,
                "teams": teams,
            }
        )

    trend = compare_multiple_runs(loaded_snaps, trend_title=req.trend_title)
    trend_id = f"trend_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    manifest = export_trend_package(trend, TRENDS_DIR / trend_id)
    return {"manifest": manifest, "trend": trend}


@app.get("/api/trends/{trend_id}/files/{rel_path:path}")
def serve_trend_file(trend_id: str, rel_path: str) -> FileResponse:
    t_path = _resolve_trend_dir(trend_id)
    target = (t_path / rel_path).resolve()
    if not str(target).startswith(str(t_path)) or not target.is_file():
        raise HTTPException(status_code=404, detail=f"找不到趨勢檔案: {rel_path}")
    return FileResponse(str(target))


@app.post("/api/trends/{trend_id}/publish-pages")
def publish_trend_pages(trend_id: str, req: PublishPagesRequest) -> dict[str, Any]:
    t_path = _resolve_trend_dir(trend_id)
    an_path = t_path / "trend_analytics.json"
    if not an_path.is_file():
        raise HTTPException(status_code=400, detail="找不到跨期趨勢資料檔")
    trend = json.loads(an_path.read_text(encoding="utf-8"))
    return publish_trend_to_github_pages(
        trend_dir=t_path,
        trend=trend,
        report_slug=req.report_slug,
        docs_dir=DOCS_DIR,
    )


@app.post("/api/runs/{run_id}/scout-image")
def scout_opponent_by_image(run_id: str, req: ScoutImageRequest) -> dict[str, Any]:
    """Match a pasted in-game opponent name screenshot against the run's 200 teams via OCR + visual silhouette."""
    global _SCOUT_OCR_ENGINE
    run_path = _resolve_run_dir(run_id)
    p3_teams = run_path / "phase3_icons" / "teams_with_icons.json"
    p2_teams = run_path / "phase2_extracted" / "teams_raw.json"
    target_path = p3_teams if p3_teams.is_file() else p2_teams
    if not target_path.is_file():
        raise HTTPException(status_code=400, detail="此分析紀錄尚未產生隊伍清單")

    raw_b64 = req.image_base64.strip()
    if "," in raw_b64 and raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[1]
    try:
        img_bytes = base64.b64decode(raw_b64)
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        query_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"無法解析貼上的圖片: {exc}") from exc

    if query_img is None or query_img.size == 0:
        raise HTTPException(status_code=400, detail="貼上的圖片內容為空")

    ocr_text = ""
    if req.use_ocr:
        try:
            with _SCOUT_OCR_LOCK:
                if _SCOUT_OCR_ENGINE is None:
                    _SCOUT_OCR_ENGINE = MultilingualOcrEngine()
                ocr_res = _SCOUT_OCR_ENGINE.read_team_name(query_img)
                ocr_text = (ocr_res.text or "").strip()
        except Exception:
            ocr_text = ""

    q_vec = _extract_text_silhouette_vec(query_img)
    teams = json.loads(target_path.read_text(encoding="utf-8"))
    crops_dir = run_path / "phase2_extracted" / "crops"

    scored: list[dict[str, Any]] = []
    q_norm = "".join(ocr_text.lower().split())

    for t in teams:
        rank = int(t["rank"])
        t_name = str(t.get("team_name") or "").strip()
        t_norm = "".join(t_name.lower().split())

        text_sim = 0.0
        if q_norm and t_norm:
            if q_norm in t_norm or t_norm in q_norm:
                text_sim = max(0.88, SequenceMatcher(None, q_norm, t_norm).ratio())
            else:
                text_sim = SequenceMatcher(None, q_norm, t_norm).ratio()

        vis_sim = 0.0
        crop_file = crops_dir / f"rank_{rank:03d}_name.png"
        if q_vec is not None and crop_file.is_file():
            try:
                c_arr = np.fromfile(str(crop_file), dtype=np.uint8)
                c_img = cv2.imdecode(c_arr, cv2.IMREAD_COLOR)
                c_vec = _extract_text_silhouette_vec(c_img) if c_img is not None else None
                if c_vec is not None:
                    vis_sim = float(max(0.0, np.dot(q_vec, c_vec)))
            except Exception:
                vis_sim = 0.0

        combined = max(text_sim, vis_sim * 0.92, (text_sim * 0.65 + vis_sim * 0.35) if q_norm else vis_sim)
        reason_parts = []
        if text_sim >= 0.45:
            reason_parts.append(f"文字吻合 {int(round(text_sim * 100))}%")
        if vis_sim >= 0.40:
            reason_parts.append(f"字形輪廓吻合 {int(round(vis_sim * 100))}%")
        scored.append(
            {
                "rank": rank,
                "team_name": t_name,
                "score": t.get("score"),
                "occupations": [o for o in (t.get("occupations") or []) if o],
                "confidence": round(combined, 3),
                "text_sim": round(text_sim, 3),
                "visual_sim": round(vis_sim, 3),
                "match_reason": " ＋ ".join(reason_parts) or f"綜合相似度 {int(round(combined * 100))}%",
                "name_crop_rel": f"phase2_extracted/crops/rank_{rank:03d}_name.png" if crop_file.is_file() else "",
            }
        )

    scored.sort(key=lambda x: (-x["confidence"], x["rank"]))
    return {
        "run_id": run_id,
        "ocr_text": ocr_text,
        "matches": scored[:5],
    }
