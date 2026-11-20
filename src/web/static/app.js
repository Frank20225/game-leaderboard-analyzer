/* Frontend controller for Game Leaderboard Analyzer Local Web UI */

let currentRunId = null;
let currentState = null;

const $ = (id) => document.getElementById(id);

function showNotice(msg, kind = "") {
  const el = $("globalNotice");
  el.textContent = msg;
  el.className = "status-banner " + kind;
  el.style.display = "block";
}

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

async function pollJob(jobId, label) {
  showNotice(`⏳ 正在執行 ${label}，請稍候...`, "warn");
  while (true) {
    await new Promise((r) => setTimeout(r, 1200));
    const job = await api(`/api/jobs/${jobId}`);
    if (job.status === "completed") return job.result;
    if (job.status === "failed") throw new Error(job.error || "背景任務失敗");
  }
}

// Navigation tabs
document.querySelectorAll(".step-btn").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".step-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
    btn.classList.add("active");
    $("step-" + btn.dataset.step).classList.add("active");
  };
});

async function refreshRuns(selectRunId = null) {
  const runs = await api("/api/runs");
  const sel = $("runSelect");
  sel.innerHTML = '<option value="">-- 選擇既有分析紀錄 --</option>';
  runs.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.run_id;
    const tags = [
      r.has_phase1 ? "P1" : "",
      r.has_phase2 ? "P2" : "",
      r.has_phase3 ? "P3" : "",
      r.has_export ? "Export" : "",
    ].filter(Boolean).join("/");
    opt.textContent = `${r.run_id} (${tags || "空"})`;
    sel.appendChild(opt);
  });

  const target = selectRunId || (runs.length ? runs[0].run_id : "");
  if (target) {
    sel.value = target;
    await loadRun(target);
  }
}

function fileUrl(relPath) {
  return `/api/runs/${encodeURIComponent(currentRunId)}/files/${relPath}?t=${Date.now()}`;
}

async function loadRun(runId) {
  if (!runId) {
    currentRunId = null;
    currentState = null;
    $("btnOpenFolder").disabled = true;
    return;
  }
  currentRunId = runId;
  $("btnOpenFolder").disabled = false;
  currentState = await api(`/api/runs/${encodeURIComponent(runId)}`);
  renderAllSections();
}

function renderAllSections() {
  if (!currentState) return;
  const s = currentState;

  // Phase 1
  if (s.phase1) {
    $("phase1ResultCard").style.display = "block";
    const m = s.phase1.metadata;
    $("phase1Meta").innerHTML =
      `影片：<b>${m.filename}</b>（${m.width}×${m.height}，${m.fps} FPS，${m.duration_sec} 秒）｜` +
      `已篩選 <b>${s.phase1.keyframe_count}</b> 張清晰代表影格（${s.phase1.stable_segments_count} 個停頓段）。<br>` +
      `<span class="muted">${(s.phase1.layout.detection_notes || []).join(" ｜ ")}</span>`;
    $("imgRoiOverlay").src = fileUrl("phase1_frames/debug_roi_overlay.png");
    $("imgTimeline").src = fileUrl("phase1_frames/debug_scroll_timeline.png");
    renderRoiEditor(s.phase1.layout);
  } else {
    $("phase1ResultCard").style.display = "none";
  }

  // Phase 2
  if (s.phase2_audit) {
    $("phase2ResultCard").style.display = "block";
    const a = s.phase2_audit;
    const box = $("phase2AuditBox");
    box.className = "status-banner " + (a.missing_ranks.length ? "err" : a.flagged_team_count ? "warn" : "ok");
    box.innerHTML =
      `<b>${a.completeness_note}</b><br>` +
      `實際擷取隊數：${a.extracted_team_count}｜缺漏排名：${a.missing_ranks.length ? a.missing_ranks.join(", ") : "無"}｜` +
      `衝突數：${a.duplicate_or_conflict_count}｜待人工確認列數：${a.flagged_team_count}`;
    $("imgOcrGrid").src = fileUrl("phase2_extracted/debug_ocr_grid.png");
  } else {
    $("phase2ResultCard").style.display = "none";
  }

  // Phase 3
  if (s.phase3) {
    $("btnConfirmClusters").style.display = "inline-block";
    $("clusterSummary").style.display = "block";
    $("clusterSummary").innerHTML =
      `總計分析 <b>${s.phase3.total_icons}</b> 個職業槽位｜資料庫自動命中：<b>${s.phase3.db_matched_count}</b>｜` +
      `分群數：<b>${s.phase3.cluster_count}</b>｜偵測到空位：<b>${s.phase3.empty_slot_count}</b>`;
    renderClusters(s.phase3);
  } else {
    $("btnConfirmClusters").style.display = "none";
    $("clusterSummary").style.display = "none";
    $("clustersContainer").innerHTML = "";
  }

  // Step 4: Editable Teams
  renderEditableTeams();

  // Step 5: Export & Share
  if (s.export) {
    renderExportPanel(s.export);
  } else {
    $("exportActions").style.display = "none";
  }

  // Learning / Behind-the-Scenes Inspector
  renderLearningTab();
}

function renderRoiEditor(layout) {
  const fields = [
    ["panel_box", "主面板像素 [x, y, w, h]", JSON.stringify(layout.panel_box)],
    ["scroll_area_ratio", "捲動區比例 [x1, y1, x2, y2]", JSON.stringify(layout.scroll_area_ratio)],
    ["personal_row_ratio", "個人列排除區比例 [x1, y1, x2, y2]", JSON.stringify(layout.personal_row_ratio)],
    ["rank_x_ratio", "排名欄 X 比例 [x1, x2]", JSON.stringify(layout.rank_x_ratio)],
    ["team_name_x_ratio", "戰隊名欄 X 比例 [x1, x2]", JSON.stringify(layout.team_name_x_ratio)],
    ["icons_x_ratio", "職業區 X 比例 [x1, x2]", JSON.stringify(layout.icons_x_ratio)],
    ["score_x_ratio", "積分欄 X 比例 [x1, x2]", JSON.stringify(layout.score_x_ratio)],
    ["icon_centers_x_ratio", "8 職業中心 X 比例", JSON.stringify(layout.icon_centers_x_ratio)],
  ];
  $("roiEditor").innerHTML = fields
    .map(
      ([k, label, val]) =>
        `<div class="roi-field"><label>${label}</label><input type="text" data-roi-key="${k}" value='${val}'></div>`
    )
    .join("");
}

function renderClusters(p3) {
  const instMap = {};
  (p3.instances || []).forEach((i) => (instMap[i.instance_id] = i));
  $("clustersContainer").innerHTML = (p3.clusters || [])
    .map((cl) => {
      const repFile = cl.representative_norm_path.split("phase3_icons").pop().replace(/^[\\/]/, "").replace(/\\/g, "/");
      const thumbs = (cl.sample_instance_ids || [])
        .map((iid) => {
          const inst = instMap[iid];
          if (!inst) return "";
          const rel = inst.norm_path.split("phase3_icons").pop().replace(/^[\\/]/, "").replace(/\\/g, "/");
          return `<img src="${fileUrl("phase3_icons/" + rel)}" title="${iid} (conf=${inst.confidence})">`;
        })
        .join("");
      const isEmpty = cl.cluster_id === "EMPTY";
      const val = cl.confirmed_name || cl.suggested_name;
      return `
        <div class="cluster-card">
          <div class="cluster-head">
            <img class="cluster-rep" src="${fileUrl("phase3_icons/" + repFile)}" alt="${cl.cluster_id}">
            <div>
              <div><b>${cl.cluster_id}</b> ${cl.matched_from_db ? '<span class="badge ok">資料庫命中</span>' : ""}</div>
              <div class="muted">數量：${cl.count} ｜ 平均相似度：${cl.avg_internal_sim} ｜ 最低相似度：${cl.min_internal_sim}</div>
            </div>
            ${
              isEmpty
                ? '<span class="badge flagged">自動排除空位</span>'
                : `<input type="text" data-cluster-id="${cl.cluster_id}" value="${val.replace(/"/g, "&quot;")}" placeholder="輸入職業名稱（同名自動合併）">`
            }
          </div>
          <div class="thumbs">${thumbs}</div>
        </div>`;
    })
    .join("");
}

function renderEditableTeams() {
  const teams = (currentState && currentState.teams) || [];
  const onlyFlagged = $("chkOnlyFlagged").checked;
  const shown = onlyFlagged ? teams.filter((t) => t.status === "flagged") : teams;
  $("editCountInfo").textContent = `顯示 ${shown.length} / ${teams.length} 隊`;

  const header = `<thead><tr><th>排名</th><th>原圖對照</th><th>戰隊名稱</th><th>積分</th><th>8 職業（逗號分隔）</th><th>狀態</th></tr></thead>`;
  const body = shown
    .map((t) => {
      const rel = (t.row_crop_path || "").split("phase2_extracted").pop().replace(/^[\\/]/, "").replace(/\\/g, "/");
      const occStr = (t.occupations || []).join(", ");
      const badgeCls = t.status === "flagged" ? "flagged" : t.status === "edited" ? "edited" : "ok";
      return `
        <tr data-rank="${t.rank}">
          <td><b>#${t.rank}</b></td>
          <td>${rel ? `<img class="row-crop-img" src="${fileUrl("phase2_extracted/" + rel)}" alt="rank ${t.rank}">` : "-"}</td>
          <td><input type="text" class="ed-name" value="${(t.team_name || "").replace(/"/g, "&quot;")}" style="width:170px"></td>
          <td><input type="number" class="ed-score" value="${t.score ?? ""}" style="width:76px"></td>
          <td><input type="text" class="ed-occs" value="${occStr.replace(/"/g, "&quot;")}" style="width:360px"></td>
          <td><span class="badge ${badgeCls}">${t.status}</span><div class="muted">${(t.flags || []).join(", ")}</div></td>
        </tr>`;
    })
    .join("");
  $("editTeamsTable").innerHTML = header + "<tbody>" + body + "</tbody>";
}

function renderExportPanel(exp) {
  $("exportActions").style.display = "block";
  $("dlExcelFull").href = fileUrl("report.xlsx");
  $("dlExcelPublic").href = fileUrl("share/report_public.xlsx");
  $("dlHtmlReport").href = fileUrl("share/report.html");
  $("summaryTextarea").value = exp.summary_text || "";
  const cards = ["01_occupation_frequency.png", "02_ranking_tier_comparison.png", "03_top_combinations.png"];
  $("shareCardsPreview").innerHTML = cards
    .map((c) => `<div><img class="preview" src="${fileUrl("share/cards/" + c)}" alt="${c}"></div>`)
    .join("");
}

function renderLearningTab() {
  if (!currentState || !currentState.phase1) {
    $("learnEmptyHint").style.display = "block";
    $("learnContent").style.display = "none";
    return;
  }
  $("learnEmptyHint").style.display = "none";
  $("learnContent").style.display = "block";
  $("learnStage1Notes").textContent = (currentState.phase1.layout.detection_notes || []).join(" ｜ ");
  $("learnRoiImg").src = fileUrl("phase1_frames/debug_roi_overlay.png");
  $("learnTimelineImg").src = fileUrl("phase1_frames/debug_scroll_timeline.png");
  if (currentState.phase2_audit) {
    $("learnPreprocImg").src = fileUrl("phase2_extracted/debug_digit_preprocess.png");
    $("learnOcrGridImg").src = fileUrl("phase2_extracted/debug_ocr_grid.png");
  }
  if (currentState.phase3) {
    $("learnClustersImg").src = fileUrl("phase3_icons/debug_clusters_sheet.png");
    $("learnHeatmapImg").src = fileUrl("phase3_icons/debug_similarity_matrix.png");
  }
}

// Event bindings
$("btnRefreshRuns").onclick = () => refreshRuns(currentRunId);
$("runSelect").onchange = (e) => loadRun(e.target.value);
$("chkOnlyFlagged").onchange = renderEditableTeams;

$("btnOpenFolder").onclick = async () => {
  if (!currentRunId) return;
  await api(`/api/runs/${encodeURIComponent(currentRunId)}/open-folder`, { method: "POST" });
};

$("btnPickVideo").onclick = async () => {
  try {
    const res = await api("/api/pick-video", { method: "POST" });
    if (res.video_path) $("videoPathInput").value = res.video_path;
  } catch (e) {
    showNotice("選檔視窗開啟失敗：" + e.message, "err");
  }
};

$("btnRunPhase1").onclick = async () => {
  const vp = $("videoPathInput").value.trim();
  if (!vp) return showNotice("請先選擇或輸入本機 MP4 影片路徑", "warn");
  try {
    const { job_id } = await api("/api/phase1", { method: "POST", body: JSON.stringify({ video_path: vp }) });
    const res = await pollJob(job_id, "Phase 1 影片分析與 ROI 定位");
    showNotice(`✅ Phase 1 完成！共選出 ${res.phase1.keyframe_count} 張清晰影格`, "ok");
    await refreshRuns(res.run_id);
  } catch (e) {
    showNotice("Phase 1 失敗：" + e.message, "err");
  }
};

$("btnSaveLayout").onclick = async () => {
  if (!currentRunId) return;
  try {
    const payload = {};
    document.querySelectorAll("[data-roi-key]").forEach((inp) => {
      payload[inp.dataset.roiKey] = JSON.parse(inp.value);
    });
    await api(`/api/runs/${encodeURIComponent(currentRunId)}/layout`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showNotice("✅ ROI 座標已更新並重繪預覽圖", "ok");
    await loadRun(currentRunId);
  } catch (e) {
    showNotice("ROI 格式錯誤或儲存失敗：" + e.message, "err");
  }
};

$("btnRunPhase2").onclick = async () => {
  if (!currentRunId) return showNotice("請先選擇或建立 Phase 1 分析紀錄", "warn");
  try {
    const { job_id } = await api(`/api/runs/${encodeURIComponent(currentRunId)}/phase2`, { method: "POST" });
    const res = await pollJob(job_id, "Phase 2 多語系 OCR 與跨影格去重（CPU 執行需約數十秒至數分鐘）");
    showNotice(`✅ Phase 2 完成！${res.audit.completeness_note}`, "ok");
    await loadRun(currentRunId);
  } catch (e) {
    showNotice("Phase 2 失敗：" + e.message, "err");
  }
};

$("btnRunPhase3").onclick = async () => {
  if (!currentRunId) return showNotice("請先完成 Phase 2", "warn");
  try {
    showNotice("⏳ 正在進行職業圖示分群...", "warn");
    const res = await api(`/api/runs/${encodeURIComponent(currentRunId)}/phase3`, { method: "POST" });
    showNotice(`✅ Phase 3 完成！共分出 ${res.cluster_count} 個職業群組（空位 ${res.empty_slot_count} 個）`, "ok");
    await loadRun(currentRunId);
  } catch (e) {
    showNotice("Phase 3 失敗：" + e.message, "err");
  }
};

$("btnConfirmClusters").onclick = async () => {
  if (!currentRunId) return;
  const cluster_name_map = {};
  document.querySelectorAll("[data-cluster-id]").forEach((inp) => {
    cluster_name_map[inp.dataset.clusterId] = inp.value.trim();
  });
  try {
    await api(`/api/runs/${encodeURIComponent(currentRunId)}/icons/confirm`, {
      method: "POST",
      body: JSON.stringify({ cluster_name_map, save_to_db: true }),
    });
    showNotice("✅ 職業名稱已套用到全部隊伍並寫入 data/icon_db/ 供未來複用！", "ok");
    await loadRun(currentRunId);
  } catch (e) {
    showNotice("儲存職業名稱失敗：" + e.message, "err");
  }
};

$("btnSaveEdits").onclick = async () => {
  if (!currentRunId) return;
  const updates = [];
  document.querySelectorAll("#editTeamsTable tbody tr").forEach((tr) => {
    const rank = parseInt(tr.dataset.rank, 10);
    const team_name = tr.querySelector(".ed-name").value;
    const scoreRaw = tr.querySelector(".ed-score").value;
    const score = scoreRaw === "" ? null : parseInt(scoreRaw, 10);
    const occupations = tr.querySelector(".ed-occs").value.split(",").map((s) => s.trim());
    updates.push({ rank, team_name, score, occupations, status: "edited" });
  });
  try {
    const res = await api(`/api/runs/${encodeURIComponent(currentRunId)}/teams/update`, {
      method: "POST",
      body: JSON.stringify({ updates }),
    });
    showNotice(`✅ 已儲存 ${res.updated_count} 筆人工校對資料！可前往 Step 5 重新匯出報告。`, "ok");
    await loadRun(currentRunId);
  } catch (e) {
    showNotice("儲存失敗：" + e.message, "err");
  }
};

$("btnRunExport").onclick = async () => {
  if (!currentRunId) return showNotice("請先完成 Phase 3", "warn");
  try {
    showNotice("⏳ 正在產生 7 頁 Excel、單檔互動報告與 PNG 圖卡...", "warn");
    const title = $("reportTitleInput").value.trim() || "排位賽職業環境分析報告";
    await api(`/api/runs/${encodeURIComponent(currentRunId)}/export`, {
      method: "POST",
      body: JSON.stringify({ report_title: title }),
    });
    showNotice("✅ 7 頁 Excel 與全配分享包已產出完成！", "ok");
    await loadRun(currentRunId);
  } catch (e) {
    showNotice("匯出失敗：" + e.message, "err");
  }
};

$("btnCopySummary").onclick = async () => {
  await navigator.clipboard.writeText($("summaryTextarea").value);
  showNotice("📋 戰報摘要已複製到剪貼簿，可直接貼到 Discord / LINE！", "ok");
};

$("btnPublishPages").onclick = async () => {
  if (!currentRunId) return;
  try {
    const res = await api(`/api/runs/${encodeURIComponent(currentRunId)}/publish-pages`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    const box = $("pagesResultBox");
    box.style.display = "block";
    box.innerHTML =
      `✅ 已發佈至 <code>docs/reports/${res.slug}/index.html</code> 並更新 <code>docs/index.html</code>！<br>` +
      `執行 <code>git add docs && git commit && git push</code> 後，即可透過 GitHub Pages 公開分享連結。`;
  } catch (e) {
    showNotice("發佈至 docs/ 失敗：" + e.message, "err");
  }
};

refreshRuns();
