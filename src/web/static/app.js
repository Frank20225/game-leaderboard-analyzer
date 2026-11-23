/* Frontend controller for Game Leaderboard Analyzer Local Web UI */

let currentRunId = null;
let currentState = null;
let currentTrendId = null;
let trendOrderedRuns = [];

const $ = (id) => document.getElementById(id);

function getDefaultReportTitle() {
  const now = new Date();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${mm}${dd}女武神職業環境分析報告`;
}

if ($("reportTitleInput") && !$("reportTitleInput").value) {
  $("reportTitleInput").value = getDefaultReportTitle();
}

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

function fmtSec(sec) {
  if (sec === null || sec === undefined || isNaN(sec)) return "計算中...";
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m} 分 ${rem} 秒`;
}

function showProgress(title, percent, detail, elapsedSec = null, etaSec = null) {
  $("progressPanel").style.display = "block";
  $("progressTitle").textContent = "⏳ " + title;
  const p = Math.max(0, Math.min(100, Number(percent || 0)));
  $("progressFill").style.width = p.toFixed(1) + "%";
  const timeTxt =
    elapsedSec !== null
      ? ` ｜ 已耗時 ${fmtSec(elapsedSec)}` + (etaSec !== null ? ` ｜ 預估剩餘 ${fmtSec(etaSec)}` : "")
      : "";
  $("progressStats").textContent = `${p.toFixed(1)}%${timeTxt}`;
  $("progressDetail").textContent = detail || "";
}

function hideProgress() {
  $("progressPanel").style.display = "none";
}

async function pollJob(jobId, label) {
  showProgress(label, 1, "任務已啟動，準備執行中...");
  $("globalNotice").style.display = "none";
  try {
    while (true) {
      await new Promise((r) => setTimeout(r, 600));
      const job = await api(`/api/jobs/${jobId}`);
      showProgress(label, job.percent ?? 0, job.message || "", job.elapsed_sec ?? null, job.eta_sec ?? null);
      if (job.status === "completed") {
        setTimeout(hideProgress, 900);
        return job.result;
      }
      if (job.status === "failed") {
        hideProgress();
        throw new Error(job.error || "背景任務失敗");
      }
    }
  } catch (err) {
    hideProgress();
    throw err;
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
  try {
    const h = await api("/api/health");
    if ($("gpuDeviceBadge")) {
      $("gpuDeviceBadge").textContent = "⚡ OCR 引擎：" + (h.ocr_device || "CPU");
      $("gpuDeviceBadge").className = "badge " + (h.gpu_available ? "ok" : "edited");
    }
  } catch (_) {}
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
  renderTrendRunsPicker(runs);
  refreshPublishedPagesList();
  if (target) {
    sel.value = target;
    await loadRun(target);
  }
}

async function refreshPublishedPagesList() {
  const box = $("publishedPagesList");
  if (!box) return;
  try {
    const pages = await api("/api/pages");
    if (!pages.length) {
      box.innerHTML = '<div class="muted">目前 docs/reports/ 尚無已發佈的報告。</div>';
      return;
    }
    box.innerHTML = pages
      .map(
        (p) => `
      <div class="row" style="justify-content:space-between;padding:8px 12px;margin:6px 0;background:var(--panel2);border-radius:8px">
        <div>
          <span class="badge ${p.report_type === "trend" ? "ok" : "edited"}">${p.report_type === "trend" ? "📈 跨期趨勢" : "📊 單期報告"}</span>
          <b style="margin-left:6px">${p.title}</b>
          <span class="muted" style="margin-left:8px">(<code>docs/reports/${p.slug}/</code> ｜ 發佈於 ${p.published_at})</span>
        </div>
        <button class="btn secondary" style="padding:4px 10px;font-size:0.8rem;border-color:rgba(248,113,113,.5);color:#fca5a5" onclick="deletePublishedPage('${p.slug}', '${(p.title || "").replace(/'/g, "\\'")}')">🗑️ 從 GitHub Pages 移除</button>
      </div>`
      )
      .join("");
  } catch (_) {}
}

window.deletePublishedPage = async function (slug, title) {
  if (!confirm(`確定要從 GitHub Pages (docs/reports/${slug}) 移除「${title}」並同步更新線上總覽頁嗎？`)) return;
  try {
    showNotice(`⏳ 正在從 docs/ 移除 ${title} 並同步推送到 GitHub Pages...`, "warn");
    const res = await api(`/api/pages/${encodeURIComponent(slug)}`, { method: "DELETE" });
    showNotice(`✅ 已從 GitHub Pages 移除「${title}」！${res.git_message || ""}`, "ok");
    await refreshPublishedPagesList();
  } catch (e) {
    showNotice("移除已發佈報告失敗：" + e.message, "err");
  }
};

function renderTrendRunsPicker(runs) {
  const ready = runs.filter((r) => r.has_phase3);
  if (!ready.length) {
    $("trendRunsList").innerHTML = '<div class="muted">尚無已完成 Phase 3 的紀錄可做多期比較。</div>';
    return;
  }
  // Sort strictly by chronological period_sort_key ascending (earliest period on top -> latest period at bottom!)
  trendOrderedRuns = [...ready].sort((a, b) =>
    String(a.period_sort_key || a.run_id).localeCompare(String(b.period_sort_key || b.run_id))
  );
  // Default check the latest 2 full runs (so 11/20 real run is Period 1 and 11/27 demo_next_week is Period 2)
  const defaultCheckedIds = new Set(trendOrderedRuns.slice(-2).map((r) => r.run_id));
  trendOrderedRuns.forEach((r) => {
    r._checked = defaultCheckedIds.has(r.run_id);
    r._customLabel = r.report_title || r.run_id;
  });
  drawTrendRunsList();
}

function drawTrendRunsList() {
  const checkedIndices = [];
  trendOrderedRuns.forEach((r, i) => {
    if (r._checked) checkedIndices.push(i);
  });

  $("trendRunsList").innerHTML = trendOrderedRuns
    .map((r, idx) => {
      const orderPos = checkedIndices.indexOf(idx);
      const isLatest = orderPos >= 0 && orderPos === checkedIndices.length - 1 && checkedIndices.length >= 2;
      const orderBadge =
        orderPos < 0
          ? '<span class="badge edited" style="min-width:128px;text-align:center">未勾選</span>'
          : isLatest
            ? `<span class="badge ok" style="min-width:128px;text-align:center">🌟 第 ${orderPos + 1} 期 (當下最新)</span>`
            : `<span class="badge" style="min-width:128px;text-align:center;background:#1e293b">第 ${orderPos + 1} 期 (前期基準)</span>`;
      return `
      <div class="row trend-row" data-idx="${idx}" style="margin:6px 0;padding:8px 10px;background:var(--panel2);border-radius:8px;justify-content:space-between">
        <div class="row" style="flex:1">
          ${orderBadge}
          <label style="min-width:250px;cursor:pointer">
            <input type="checkbox" class="trend-chk" data-idx="${idx}" data-run-id="${r.run_id}" ${r._checked ? "checked" : ""}>
            <b>${r.run_id}</b>
          </label>
          <input type="text" class="trend-lbl" data-idx="${idx}" data-run-id="${r.run_id}" value="${(r._customLabel || "").replace(/"/g, "&quot;")}" style="width:240px" placeholder="期別名稱">
          <span class="muted">${r.team_count ? r.team_count + "隊" : ""} ${r.video_name || ""}</span>
        </div>
        <div class="row" style="gap:4px">
          <button class="btn secondary" style="padding:3px 8px;font-size:0.78rem" onclick="moveTrendRow(${idx}, -1)" ${idx === 0 ? "disabled" : ""} title="移至較早期">⬆️ 上移</button>
          <button class="btn secondary" style="padding:3px 8px;font-size:0.78rem" onclick="moveTrendRow(${idx}, 1)" ${idx === trendOrderedRuns.length - 1 ? "disabled" : ""} title="移至較晚期">⬇️ 下移</button>
        </div>
      </div>`;
    })
    .join("");

  document.querySelectorAll(".trend-chk").forEach((chk) => {
    chk.onchange = () => {
      syncTrendInputsFromDom();
      drawTrendRunsList();
    };
  });
  document.querySelectorAll(".trend-lbl").forEach((inp) => {
    inp.oninput = () => syncTrendInputsFromDom();
  });
}

function syncTrendInputsFromDom() {
  document.querySelectorAll(".trend-chk").forEach((chk) => {
    const i = parseInt(chk.dataset.idx, 10);
    if (trendOrderedRuns[i]) trendOrderedRuns[i]._checked = chk.checked;
  });
  document.querySelectorAll(".trend-lbl").forEach((inp) => {
    const i = parseInt(inp.dataset.idx, 10);
    if (trendOrderedRuns[i]) trendOrderedRuns[i]._customLabel = inp.value;
  });
}

window.moveTrendRow = function (idx, dir) {
  syncTrendInputsFromDom();
  const target = idx + dir;
  if (target < 0 || target >= trendOrderedRuns.length) return;
  const tmp = trendOrderedRuns[idx];
  trendOrderedRuns[idx] = trendOrderedRuns[target];
  trendOrderedRuns[target] = tmp;
  drawTrendRunsList();
};

function fileUrl(relPath) {
  return `/api/runs/${encodeURIComponent(currentRunId)}/files/${relPath}?t=${Date.now()}`;
}

async function loadRun(runId) {
  if (!runId) {
    currentRunId = null;
    currentState = null;
    $("btnOpenFolder").disabled = true;
    if ($("btnDeleteRun")) $("btnDeleteRun").disabled = true;
    return;
  }
  currentRunId = runId;
  $("btnOpenFolder").disabled = false;
  if ($("btnDeleteRun")) $("btnDeleteRun").disabled = false;
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
  const kw = ($("editSearchInput") ? $("editSearchInput").value : "").trim().toLowerCase();
  const shown = teams.filter((t) => {
    if (onlyFlagged && t.status !== "flagged") return false;
    if (kw) {
      const rankHit = String(t.rank) === kw.replace(/^#/, "") || ("#" + t.rank).includes(kw);
      const nameHit = (t.team_name || "").toLowerCase().includes(kw);
      const occHit = (t.occupations || []).join(",").toLowerCase().includes(kw);
      if (!rankHit && !nameHit && !occHit) return false;
    }
    return true;
  });
  const flaggedTotal = teams.filter((t) => t.status === "flagged").length;
  $("editCountInfo").textContent = `顯示 ${shown.length} / ${teams.length} 隊（待確認異常列：${flaggedTotal} 筆）`;

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
  const cards = [
    "01_meta_quadrant.png",
    "02_copy_count_impact.png",
    "03_tier_heatmap_and_doubles.png",
    "04_synergy_matrix.png",
  ];
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
if ($("editSearchInput")) $("editSearchInput").oninput = renderEditableTeams;

$("btnOpenFolder").onclick = async () => {
  if (!currentRunId) return;
  await api(`/api/runs/${encodeURIComponent(currentRunId)}/open-folder`, { method: "POST" });
};

if ($("btnDeleteRun")) {
  $("btnDeleteRun").onclick = async () => {
    if (!currentRunId) return;
    if (!confirm(`確定要永久刪除本機分析紀錄「${currentRunId}」嗎？（原始 MP4 影片不會受影響）`)) return;
    try {
      const deletedId = currentRunId;
      await api(`/api/runs/${encodeURIComponent(deletedId)}`, { method: "DELETE" });
      showNotice(`🗑️ 已刪除本機分析紀錄：${deletedId}`, "ok");
      await refreshRuns();
    } catch (e) {
      showNotice("刪除失敗：" + e.message, "err");
    }
  };
}

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

if ($("btnRunFullAuto")) {
  $("btnRunFullAuto").onclick = async () => {
    const vp = $("videoPathInput").value.trim();
    if (!vp) return showNotice("請先選擇或輸入本機 MP4 影片路徑", "warn");
    try {
      const { job_id } = await api("/api/pipeline/full", {
        method: "POST",
        body: JSON.stringify({ video_path: vp }),
      });
      const res = await pollJob(job_id, "⚡ 一鍵全自動分析（Phase 1 影格提取 → Phase 2 多語系 OCR → Phase 3 圖示自動比對＆歷史隊名校正 → Phase 4&5 報告產出）");
      await refreshRuns(res.run_id);
      const alignNote = res.aligned_name_count ? `（已自動根據歷史期數校正 ${res.aligned_name_count} 支隊名）` : "";
      if (res.flagged_team_count > 0) {
        $("chkOnlyFlagged").checked = true;
        renderEditableTeams();
        const step4Btn = document.querySelector('.step-btn[data-step="4"]');
        if (step4Btn) step4Btn.click();
        showNotice(
          `⚠️ 全自動分析與初版報告已完成${alignNote}！偵測到 ${res.flagged_team_count} 筆低信心度/待確認列，已自動為你篩選於下方 Step 4，確認修改後點「🚀 儲存修正並立即更新報告」即可！`,
          "warn"
        );
      } else {
        const step5Btn = document.querySelector('.step-btn[data-step="5"]');
        if (step5Btn) step5Btn.click();
        showNotice(
          `🎉 全自動分析完成！共擷取 ${res.team_count} 隊（0 異常列${alignNote}），已直接產出「${res.report_title}」！若想微調隊名可隨時點 Step 4。`,
          "ok"
        );
      }
    } catch (e) {
      showNotice("全自動分析失敗：" + e.message, "err");
    }
  };
}

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

async function collectAndSaveTeamEdits() {
  const updates = [];
  document.querySelectorAll("#editTeamsTable tbody tr").forEach((tr) => {
    const rank = parseInt(tr.dataset.rank, 10);
    const team_name = tr.querySelector(".ed-name").value;
    const scoreRaw = tr.querySelector(".ed-score").value;
    const score = scoreRaw === "" ? null : parseInt(scoreRaw, 10);
    const occupations = tr.querySelector(".ed-occs").value.split(",").map((s) => s.trim());
    updates.push({ rank, team_name, score, occupations, status: "edited" });
  });
  return await api(`/api/runs/${encodeURIComponent(currentRunId)}/teams/update`, {
    method: "POST",
    body: JSON.stringify({ updates }),
  });
}

$("btnSaveEdits").onclick = async () => {
  if (!currentRunId) return;
  try {
    const res = await collectAndSaveTeamEdits();
    showNotice(`✅ 已儲存 ${res.updated_count} 筆人工校對資料！`, "ok");
    await loadRun(currentRunId);
  } catch (e) {
    showNotice("儲存失敗：" + e.message, "err");
  }
};

if ($("btnSaveAndReexport")) {
  $("btnSaveAndReexport").onclick = async () => {
    if (!currentRunId) return;
    try {
      showNotice("⏳ 正在儲存人工校對並重新產出 7 頁 Excel、互動網頁與 4 張圖卡...", "warn");
      const res = await collectAndSaveTeamEdits();
      const title = $("reportTitleInput").value.trim() || getDefaultReportTitle();
      await api(`/api/runs/${encodeURIComponent(currentRunId)}/export`, {
        method: "POST",
        body: JSON.stringify({ report_title: title }),
      });
      await loadRun(currentRunId);
      const step5Btn = document.querySelector('.step-btn[data-step="5"]');
      if (step5Btn) step5Btn.click();
      showNotice(`✅ 已儲存 ${res.updated_count} 筆校對並同步更新「${title}」所有報告與圖卡！`, "ok");
    } catch (e) {
      showNotice("儲存並更新報告失敗：" + e.message, "err");
    }
  };
}

if ($("btnAutoAlignNames")) {
  $("btnAutoAlignNames").onclick = async () => {
    if (!currentRunId) return;
    try {
      const res = await api(`/api/runs/${encodeURIComponent(currentRunId)}/teams/auto-align`, { method: "POST" });
      await loadRun(currentRunId);
      showNotice(
        res.aligned_count > 0
          ? `✅ 已根據歷史期數已知隊名與 8 職業組合，自動校正了 ${res.aligned_count} 支戰隊名稱！`
          : "✨ 所有戰隊名稱皆已與歷史期數一致，無需額外校正。",
        "ok"
      );
    } catch (e) {
      showNotice("歷史隊名對齊失敗：" + e.message, "err");
    }
  };
}

$("btnRunExport").onclick = async () => {
  if (!currentRunId) return showNotice("請先完成 Phase 3", "warn");
  try {
    showNotice("⏳ 正在產生 7 頁 Excel、單檔互動報告與 PNG 圖卡...", "warn");
    const title = $("reportTitleInput").value.trim() || getDefaultReportTitle();
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
      `${res.git_message || "可透過 GitHub Pages 公開分享連結。"}`;
  } catch (e) {
    showNotice("發佈至 docs/ 失敗：" + e.message, "err");
  }
};

$("btnRunTrend").onclick = async () => {
  syncTrendInputsFromDom();
  const snaps = trendOrderedRuns
    .filter((r) => r._checked)
    .map((r) => ({ run_id: r.run_id, label: (r._customLabel || r.run_id).trim() }));
  if (snaps.length < 2) {
    return showNotice("請至少勾選 2 個分析紀錄才能進行多期趨勢對比", "warn");
  }
  try {
    showNotice("⏳ 正在比對多期排名、Meta 演變與戰隊換角紀錄...", "warn");
    const res = await api("/api/trends/compare", {
      method: "POST",
      body: JSON.stringify({
        trend_title: $("trendTitleInput").value.trim() || "排位賽多期環境與戰隊趨勢對比",
        snapshots: snaps,
      }),
    });
    const m = res.manifest;
    const t = res.trend;
    const tid = m.trend_id;
    currentTrendId = tid;
    $("trendResultCard").style.display = "block";
    if ($("trendPagesResultBox")) $("trendPagesResultBox").style.display = "none";
    $("dlTrendExcel").href = `/api/trends/${encodeURIComponent(tid)}/files/trend_report.xlsx`;
    $("dlTrendHtml").href = `/api/trends/${encodeURIComponent(tid)}/files/trend_report.html`;
    $("trendSummaryBox").value = m.summary_text || "";
    $("trendCardsPreview").innerHTML = ["01_meta_trend_lines.png", "02_meta_movers_delta.png"]
      .map((c) => `<div><img class="preview" src="/api/trends/${encodeURIComponent(tid)}/files/cards/${c}?t=${Date.now()}" alt="${c}"></div>`)
      .join("");
    const sys = t.roster_strength_trends || [];
    if ($("trendSystemsTable")) {
      $("trendSystemsTable").innerHTML =
        "<thead><tr><th>陣容體系</th><th>強度判定</th><th>當下隊數</th><th>前期→當下均排</th><th>均排爬升</th><th>爬升隊伍比例</th><th>Top30席次變化</th><th>當下代表強隊</th></tr></thead><tbody>" +
        sys
          .map(
            (s) =>
              `<tr><td><b>${s.system_name}</b></td><td><span class="badge ${s.avg_rank_gain >= 2 ? "ok" : s.avg_rank_gain <= -2 ? "flagged" : "edited"}">${s.verdict}</span></td><td>${s.latest_team_count}隊</td><td>#${s.first_avg_rank} → <b>#${s.latest_avg_rank}</b></td><td><b>${s.avg_rank_gain >= 0 ? "+" : ""}${s.avg_rank_gain} 名</b></td><td><b>${Math.round(s.climber_rate * 100)}%</b> (${s.climber_count}隊升)</td><td>${s.top30_series[0]} → ${s.top30_series[s.top30_series.length - 1]} (${s.top30_delta >= 0 ? "+" : ""}${s.top30_delta})</td><td class="muted">${s.sample_teams}</td></tr>`
          )
          .join("") +
        "</tbody>";
    }
    const st = (t.league_standings || []).slice(0, 50);
    if ($("trendStandingsTable")) {
      $("trendStandingsTable").innerHTML =
        "<thead><tr><th>當下排名</th><th>本期升降</th><th>戰隊名稱</th><th>當下積分 (本期Δ)</th><th>前期排名</th><th>陣容體系</th><th>當下 8 人名單</th><th>副角色切換</th></tr></thead><tbody>" +
        st
          .map(
            (r) =>
              `<tr><td><b>#${r.latest_rank}</b></td><td><span class="badge ${r.recent_rank_change > 0 ? "ok" : r.recent_rank_change < 0 ? "flagged" : "edited"}">${r.status}</span></td><td><b>${r.team_name}</b></td><td><b>${r.latest_score ?? "-"}</b> ${r.recent_score_delta !== null && r.recent_score_delta !== undefined ? `(${r.recent_score_delta >= 0 ? "+" : ""}${r.recent_score_delta})` : ""}</td><td class="muted">${r.prev_rank ? "#" + r.prev_rank : "-"}</td><td>${r.archetype_tag}</td><td class="muted">${r.latest_roster}</td><td class="muted">${r.roster_change_notes}</td></tr>`
          )
          .join("") +
        "</tbody>";
    }
    const ch = t.roster_changes || [];
    $("trendChangesTable").innerHTML =
      "<thead><tr><th>戰隊</th><th>區間</th><th>切換副角色明細</th><th>排名變化</th><th>換角後 8 人名單</th></tr></thead><tbody>" +
      (ch.length
        ? ch
            .map(
              (c) =>
                `<tr><td><b>${c.team_name}</b></td><td>${c.from_period}→${c.to_period}</td><td><code>${c.diff_summary}</code></td><td>#${c.rank_before} → #${c.rank_after} (${c.rank_delta >= 0 ? "+" : ""}${c.rank_delta})</td><td class="muted">${c.roster_after}</td></tr>`
            )
            .join("")
        : '<tr><td colspan="5" class="muted">本次對比全數戰隊皆維持固定陣容</td></tr>') +
      "</tbody>";
    showNotice(`✅ 聯賽趨勢分析完成！共追蹤 ${t.summary_counts.tracked_teams} 隊（原陣容直衝 ${t.summary_counts.locked_roster_teams || 0} 隊、切換副角色 ${t.summary_counts.roster_change_events} 隊）。`, "ok");
  } catch (e) {
    showNotice("多期趨勢分析失敗：" + e.message, "err");
  }
};

$("btnCopyTrendSummary").onclick = async () => {
  await navigator.clipboard.writeText($("trendSummaryBox").value);
  showNotice("📋 跨期趨勢戰報已複製到剪貼簿！", "ok");
};

if ($("btnReverseTrendOrder")) {
  $("btnReverseTrendOrder").onclick = () => {
    syncTrendInputsFromDom();
    trendOrderedRuns.reverse();
    drawTrendRunsList();
  };
}

if ($("btnPublishTrendPages")) {
  $("btnPublishTrendPages").onclick = async () => {
    if (!currentTrendId) return;
    try {
      const res = await api(`/api/trends/${encodeURIComponent(currentTrendId)}/publish-pages`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      const box = $("trendPagesResultBox");
      if (box) {
        box.style.display = "block";
        box.innerHTML =
          `✅ 跨期聯賽積分榜與趨勢報告已發佈至 <code>docs/reports/${res.slug}/index.html</code> 並更新首頁 <code>docs/index.html</code>！<br>` +
          `${res.git_message || "可透過 GitHub Pages 公開分享。"}`;
      }
    } catch (e) {
      showNotice("發佈跨期趨勢至 docs/ 失敗：" + e.message, "err");
    }
  };
}

async function runImageScoutWithDataUrl(dataUrl) {
  if (!currentRunId) {
    return showNotice("請先於右上角選擇一個已分析完成的紀錄（如 200 隊紀錄）再貼上截圖", "warn");
  }
  const box = $("scoutResultBox");
  box.style.display = "block";
  box.innerHTML = `<div class="muted">⏳ 正在透過多語系 OCR ＋ 字形輪廓比對 200 隊名單...</div>`;
  try {
    const res = await api(`/api/runs/${encodeURIComponent(currentRunId)}/scout-image`, {
      method: "POST",
      body: JSON.stringify({ image_base64: dataUrl, use_ocr: true }),
    });
    const matches = res.matches || [];
    const rowsHtml = matches
      .map(
        (m, idx) => `
        <tr style="${idx === 0 ? "background:rgba(56,189,248,.12)" : ""}">
          <td><b>#${m.rank}</b> ${idx === 0 ? '<span class="badge ok">最佳吻合</span>' : ""}</td>
          <td>${m.name_crop_rel ? `<img src="${fileUrl(m.name_crop_rel)}" style="height:26px;border-radius:4px;vertical-align:middle">` : ""}</td>
          <td><b>${m.team_name}</b></td>
          <td>${m.score ?? "-"}</td>
          <td><b>${(m.occupations || []).join(" / ")}</b></td>
          <td class="muted">${m.match_reason} (${Math.round(m.confidence * 100)}%)</td>
        </tr>`
      )
      .join("");
    box.innerHTML = `
      <div class="row" style="justify-content:space-between;margin-bottom:8px">
        <div class="row">
          <img src="${dataUrl}" alt="pasted" style="height:32px;border-radius:6px;border:1px solid var(--accent)">
          <span>OCR 讀出文字：<code>${res.ocr_text || "(純字形輪廓比對)"}</code></span>
        </div>
        <button class="btn secondary" style="padding:4px 10px;font-size:0.8rem" onclick="document.getElementById('scoutResultBox').style.display='none'">✖ 關閉</button>
      </div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>排名</th><th>排行榜原圖</th><th>戰隊名稱</th><th>積分</th><th>對方 8 職業陣容</th><th>比對依據</th></tr></thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>`;
  } catch (e) {
    box.innerHTML = `<div style="color:var(--danger)">截圖比對失敗：${e.message}</div>`;
  }
}

window.addEventListener("paste", (ev) => {
  const items = (ev.clipboardData && ev.clipboardData.items) || [];
  for (const item of items) {
    if (item.type && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (!file) continue;
      const reader = new FileReader();
      reader.onload = () => runImageScoutWithDataUrl(reader.result);
      reader.readAsDataURL(file);
      ev.preventDefault();
      break;
    }
  }
});

if ($("scoutFileInput")) {
  $("scoutFileInput").onchange = (ev) => {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => runImageScoutWithDataUrl(reader.result);
    reader.readAsDataURL(file);
  };
}

// Universal Click-to-Zoom & Pan Lightbox for all .preview charts in Local Web UI
(function initLocalWebZoom() {
  const modal = $("imgZoomModal");
  const stage = $("zoomStage");
  const img = $("zoomModalImg");
  const titleEl = $("zoomModalTitle");
  const pctEl = $("zoomPctLabel");
  const dlBtn = $("btnZoomDownload");
  if (!modal || !stage || !img) return;

  let scale = 1, tx = 0, ty = 0, dragging = false, startX = 0, startY = 0;
  function applyTransform() {
    img.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    if (pctEl) pctEl.textContent = Math.round(scale * 100) + "%";
  }
  function openZoom(src, title) {
    img.src = src;
    if (titleEl) titleEl.textContent = title || "圖表放大檢視";
    if (dlBtn) { dlBtn.href = src; dlBtn.download = (title || "chart") + ".png"; }
    scale = 1; tx = 0; ty = 0; applyTransform();
    modal.style.display = "flex";
  }
  function closeZoom() { modal.style.display = "none"; }

  document.addEventListener("click", (ev) => {
    const t = ev.target.closest("img.preview");
    if (t && t.src) openZoom(t.src, t.alt || "統計圖卡");
  });
  $("btnZoomIn").onclick = () => { scale = Math.min(5, +(scale + 0.25).toFixed(2)); applyTransform(); };
  $("btnZoomOut").onclick = () => { scale = Math.max(0.5, +(scale - 0.25).toFixed(2)); applyTransform(); };
  $("btnZoomReset").onclick = () => { scale = 1; tx = 0; ty = 0; applyTransform(); };
  $("btnZoomClose").onclick = closeZoom;
  stage.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    scale = Math.max(0.5, Math.min(5, +(scale + (ev.deltaY < 0 ? 0.2 : -0.2)).toFixed(2)));
    applyTransform();
  }, { passive: false });
  stage.addEventListener("mousedown", (ev) => {
    if (ev.button !== 0) return;
    dragging = true; startX = ev.clientX - tx; startY = ev.clientY - ty;
    stage.style.cursor = "grabbing";
  });
  window.addEventListener("mousemove", (ev) => {
    if (!dragging) return;
    tx = ev.clientX - startX; ty = ev.clientY - startY; applyTransform();
  });
  window.addEventListener("mouseup", () => { dragging = false; stage.style.cursor = "grab"; });
  stage.addEventListener("dblclick", () => {
    if (scale > 1.05) { scale = 1; tx = 0; ty = 0; } else { scale = 2.2; }
    applyTransform();
  });
  window.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && modal.style.display === "flex") closeZoom();
  });
})();

refreshRuns();
