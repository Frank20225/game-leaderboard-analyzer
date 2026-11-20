"""End-to-end HTTP server verification for Stage 5 local Web UI & API (zero extra test deps)."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import uvicorn

from src.web.api import app

VERIFY_RUN_DIR = Path(r"C:\Users\f1991\source\repos\game-leaderboard-analyzer\outputs\stage1_verify")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def live_server_url() -> str:
    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1.0) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.15)
    yield base_url
    server.should_exit = True
    thread.join(timeout=5.0)


def _get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=15.0) as resp:
        return resp.status, resp.read()


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_health_homepage_and_static_assets(live_server_url: str) -> None:
    code, body = _get(f"{live_server_url}/api/health")
    assert code == 200
    assert json.loads(body)["status"] == "ok"

    code, html_bytes = _get(f"{live_server_url}/")
    assert code == 200
    html_text = html_bytes.decode("utf-8")
    assert "Game Leaderboard Analyzer" in html_text
    assert "幕後過程 / 學習檢視" in html_text

    assert _get(f"{live_server_url}/static/app.js")[0] == 200
    assert _get(f"{live_server_url}/static/style.css")[0] == 200


@pytest.mark.skipif(not VERIFY_RUN_DIR.is_dir(), reason="Verified run directory not present")
def test_run_inspection_and_export_endpoints(live_server_url: str) -> None:
    _, runs_bytes = _get(f"{live_server_url}/api/runs")
    runs = json.loads(runs_bytes)
    assert any(r["run_id"] == "stage1_verify" for r in runs)

    _, state_bytes = _get(f"{live_server_url}/api/runs/stage1_verify")
    state = json.loads(state_bytes)
    assert state["phase1"]["keyframe_count"] >= 6
    assert state["phase2_audit"]["extracted_team_count"] == 30
    assert state["phase3"]["cluster_count"] >= 8

    # Serve debug visuals
    assert _get(f"{live_server_url}/api/runs/stage1_verify/files/phase1_frames/debug_roi_overlay.png")[0] == 200
    assert _get(f"{live_server_url}/api/runs/stage1_verify/files/phase3_icons/debug_similarity_matrix.png")[0] == 200

    # Path traversal must be rejected
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(f"{live_server_url}/api/runs/stage1_verify/files/..%2F..%2Frequirements.txt")
    assert exc.value.code in (400, 404)

    # Trigger live export via POST API
    code, exp = _post_json(
        f"{live_server_url}/api/runs/stage1_verify/export",
        {"report_title": "Web API 實測排位賽分析"},
    )
    assert code == 200
    assert exp["overview"]["total_teams"] == 30
    assert _get(f"{live_server_url}/api/runs/stage1_verify/files/report.xlsx")[0] == 200
    assert _get(f"{live_server_url}/api/runs/stage1_verify/files/share/report.html")[0] == 200
