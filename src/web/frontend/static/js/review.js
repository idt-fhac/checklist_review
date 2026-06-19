const API = "/api/v1";

const state = {
  step: 1,
  pipelines: [],
  criteriaSets: [],
  pipelineId: "",
  pipelineDetail: null,
  collectionName: "",
  criteriaSetName: "",
  rfpFilename: "",
  draftArtifactId: "",
  reviewId: "",
  pollTimer: null,
};

function $(id) {
  return document.getElementById(id);
}

function showError(message) {
  const banner = $("errorBanner");
  banner.textContent = message;
  banner.classList.add("visible");
}

function clearError() {
  $("errorBanner").classList.remove("visible");
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function setStep(step) {
  state.step = step;
  document.querySelectorAll(".step-pill").forEach((pill) => {
    const n = Number(pill.dataset.step);
    pill.classList.toggle("active", n === step);
    pill.classList.toggle("done", n < step);
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", Number(panel.dataset.step) === step);
  });
  clearError();
}

function pipelineHasExtractor(detail) {
  return (detail?.stages || []).includes("criteria_extractor");
}

function updateCriteriaVisibility() {
  const hasExtractor = pipelineHasExtractor(state.pipelineDetail);
  $("criteriaSetField").style.display = hasExtractor ? "none" : "block";
  $("criteriaSetHint").textContent = hasExtractor
    ? "Criteria will be extracted from the RFP automatically."
    : "Select a criteria set from the workspace.";
}

async function loadPipelines() {
  state.pipelines = await fetchJSON(`${API}/pipelines`);
  const select = $("pipelineSelect");
  select.innerHTML = "";
  for (const pipeline of state.pipelines) {
    const option = document.createElement("option");
    option.value = pipeline.id;
    option.textContent = pipeline.name || pipeline.id;
    select.appendChild(option);
  }
  if (state.pipelines.length) {
    state.pipelineId = state.pipelines[0].id;
    await onPipelineChange();
  }
}

async function loadCriteriaSets() {
  state.criteriaSets = await fetchJSON(`${API}/criteria-sets`);
  const select = $("criteriaSetSelect");
  select.innerHTML = "";
  for (const item of state.criteriaSets) {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = item.name;
    select.appendChild(option);
  }
  if (state.criteriaSets.length) {
    state.criteriaSetName = state.criteriaSets[0].name;
  }
}

async function onPipelineChange() {
  state.pipelineId = $("pipelineSelect").value;
  state.pipelineDetail = await fetchJSON(`${API}/pipelines/${encodeURIComponent(state.pipelineId)}`);
  const personas = state.pipelineDetail.personas || [];
  const hint = [`Profile: ${state.pipelineDetail.profile || "—"}`];
  if (state.pipelineDetail.evaluation_mode === "multi_persona" && personas.length) {
    hint.push(`Personas: ${personas.map((p) => p.label || p.id).join(", ")}`);
  }
  $("pipelineHint").textContent = hint.join(" · ");
  updateCriteriaVisibility();
}

async function ensureCollection() {
  const name = $("collectionName").value.trim();
  if (!name) {
    throw new Error("Enter a project name.");
  }
  await fetchJSON(`${API}/collections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }).catch(async (err) => {
    if (!String(err.message).includes("already exists")) {
      throw err;
    }
  });
  state.collectionName = name;
}

async function uploadDocument(file, role) {
  const form = new FormData();
  form.append("file", file);
  form.append("role", role);
  return fetchJSON(`${API}/collections/${encodeURIComponent(state.collectionName)}/documents`, {
    method: "POST",
    body: form,
  });
}

async function saveReferences() {
  const lines = $("referenceUrls").value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) {
    return;
  }
  await fetchJSON(`${API}/collections/${encodeURIComponent(state.collectionName)}/references`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls: lines }),
  });
}

async function handleUploadStep() {
  await ensureCollection();
  const hasExtractor = pipelineHasExtractor(state.pipelineDetail);
  const rfpInput = $("rfpFile");
  const draftInput = $("draftFile");

  if (hasExtractor && !rfpInput.files.length) {
    throw new Error("Upload the RFP / requirements PDF for this pipeline.");
  }
  if (!draftInput.files.length) {
    throw new Error("Upload the draft PDF to evaluate.");
  }

  if (rfpInput.files.length) {
    const result = await uploadDocument(rfpInput.files[0], "rfp");
    state.rfpFilename = result.filename;
    $("rfpCard").classList.add("uploaded");
    $("rfpStatus").textContent = `Uploaded: ${result.filename}`;
  }

  const draftResult = await uploadDocument(draftInput.files[0], "artifact");
  state.draftArtifactId = draftResult.artifact_id || draftResult.filename.replace(/\.pdf$/i, "");
  $("draftCard").classList.add("uploaded");
  $("draftStatus").textContent = `Uploaded: ${draftResult.filename}`;

  await saveReferences();

  $("runSummary").textContent =
    `Project: ${state.collectionName} · Pipeline: ${state.pipelineId} · Draft: ${draftResult.filename}`;
  setStep(3);
}

function renderLogs(messages) {
  const box = $("logBox");
  box.innerHTML = "";
  for (const entry of messages.slice(-40)) {
    const line = document.createElement("div");
    line.textContent = `[${entry.timestamp || ""}] ${entry.message || ""}`;
    box.appendChild(line);
  }
  box.scrollTop = box.scrollHeight;
}

function updateProgress(status) {
  const total = status.total || 1;
  const current = status.current || 0;
  const pct = Math.min(100, Math.round((current / total) * 100));
  $("progressFill").style.width = `${pct}%`;
  $("progressLabel").textContent =
    `${status.status} — ${current}/${total}` +
    (status.current_item ? ` · ${status.current_item}` : "");
  renderLogs(status.log_messages || []);
}

async function pollReview() {
  if (!state.reviewId) {
    return;
  }
  const status = await fetchJSON(`${API}/reviews/${state.reviewId}`);
  updateProgress(status);
  if (["completed", "failed", "stopped"].includes(status.status)) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
    $("btnStartReview").disabled = false;
    $("btnCancelReview").disabled = true;
    if (status.status === "completed") {
      await loadReport();
      setStep(4);
    } else if (status.error) {
      showError(status.error);
    }
  }
}

async function startReview() {
  const body = {
    collection_name: state.collectionName,
    pipeline_id: state.pipelineId,
    artifact_ids: state.draftArtifactId ? [state.draftArtifactId] : undefined,
    skip_existing: false,
  };
  if (pipelineHasExtractor(state.pipelineDetail)) {
    body.criteria_source_name = state.rfpFilename;
  } else {
    body.criteria_set_name = $("criteriaSetSelect").value || state.criteriaSetName;
  }

  const result = await fetchJSON(`${API}/reviews`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  state.reviewId = result.review_id;
  $("btnStartReview").disabled = true;
  $("btnCancelReview").disabled = false;
  state.pollTimer = setInterval(pollReview, 2000);
  await pollReview();
}

async function cancelReview() {
  if (!state.reviewId) {
    return;
  }
  await fetchJSON(`${API}/reviews/${state.reviewId}/cancel`, { method: "POST" });
  $("btnCancelReview").disabled = true;
}

function answerBadge(answer) {
  const span = document.createElement("span");
  span.classList.add("badge");
  if (answer === true) {
    span.classList.add("pass");
    span.textContent = "MET";
  } else if (answer === false) {
    span.classList.add("fail");
    span.textContent = "NOT MET";
  } else {
    span.classList.add("warn");
    span.textContent = String(answer ?? "—");
  }
  return span;
}

async function loadReport() {
  const report = await fetchJSON(`${API}/reviews/${state.reviewId}/report`);
  $("reportMeta").textContent =
    `Review ${report.review_id} · ${report.pipeline_id} · ${report.status}`;

  const artifact = (report.artifacts || [])[0];
  const synthesis = artifact?.synthesis?.summary || "";
  $("reportSummary").textContent = synthesis || "No synthesis available.";

  const downloads = $("reportDownloads");
  downloads.innerHTML = "";
  for (const output of artifact?.outputs || []) {
    const link = document.createElement("a");
    link.href = output.path;
    link.textContent = `Download ${output.name}`;
    link.className = "primary";
    link.style.textDecoration = "none";
    link.style.padding = "0.6rem 1rem";
    link.style.borderRadius = "8px";
    link.target = "_blank";
    downloads.appendChild(link);
  }

  const tbody = $("reportBody");
  tbody.innerHTML = "";
  for (const item of artifact?.evaluations || []) {
    const tr = document.createElement("tr");

    const criterionCell = document.createElement("td");
    criterionCell.textContent = item.criterion_text || item.criterion_id || "Criterion";

    const resultCell = document.createElement("td");
    resultCell.appendChild(answerBadge(item.answer));
    if (item.disagreement) {
      const warn = document.createElement("div");
      warn.className = "persona-row";
      warn.textContent = "Personas disagreed";
      resultCell.appendChild(warn);
    }

    const notesCell = document.createElement("td");
    notesCell.textContent = item.reasoning || "";
    const personaScores = item.persona_scores || {};
    for (const [personaId, score] of Object.entries(personaScores)) {
      const row = document.createElement("div");
      row.className = "persona-row";
      row.textContent = `${score.label || personaId}: ${score.answer ? "MET" : "NOT MET"}`;
      notesCell.appendChild(row);
    }

    tr.appendChild(criterionCell);
    tr.appendChild(resultCell);
    tr.appendChild(notesCell);
    tbody.appendChild(tr);
  }
}

function resetApp() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  state.reviewId = "";
  state.rfpFilename = "";
  state.draftArtifactId = "";
  $("rfpFile").value = "";
  $("draftFile").value = "";
  $("referenceUrls").value = "";
  $("rfpCard").classList.remove("uploaded");
  $("draftCard").classList.remove("uploaded");
  $("progressFill").style.width = "0%";
  $("logBox").innerHTML = "";
  setStep(1);
}

function bindEvents() {
  $("pipelineSelect").addEventListener("change", () => onPipelineChange().catch(showError));
  $("btnToUpload").addEventListener("click", async () => {
    try {
      if (!$("collectionName").value.trim()) {
        throw new Error("Enter a project name.");
      }
      if (!pipelineHasExtractor(state.pipelineDetail) && !$("criteriaSetSelect").value) {
        throw new Error("Select a criteria set.");
      }
      setStep(2);
    } catch (err) {
      showError(err.message);
    }
  });
  $("btnBackSetup").addEventListener("click", () => setStep(1));
  $("btnToRun").addEventListener("click", () => handleUploadStep().catch(showError));
  $("btnBackUpload").addEventListener("click", () => setStep(2));
  $("btnStartReview").addEventListener("click", () => startReview().catch(showError));
  $("btnCancelReview").addEventListener("click", () => cancelReview().catch(showError));
  $("btnNewReview").addEventListener("click", resetApp);
}

async function init() {
  bindEvents();
  try {
    await Promise.all([loadPipelines(), loadCriteriaSets()]);
  } catch (err) {
    showError(err.message);
  }
}

init();
