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

function setText(id, value) {
  const el = $(id);
  if (el) {
    el.textContent = value;
  }
  return el;
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
  updateSelectionSummaryVisibility();
  clearError();
}

function pipelineLabel() {
  const match = state.pipelines.find((pipeline) => pipeline.id === state.pipelineId);
  return match?.name || state.pipelineDetail?.name || state.pipelineId || "—";
}

function criteriaLabel() {
  const hasExtractor = pipelineHasExtractor(state.pipelineDetail);
  if (hasExtractor) {
    return state.rfpFilename ? `From RFP: ${state.rfpFilename}` : "Extracted from RFP";
  }
  return $("criteriaSetSelect")?.value || state.criteriaSetName || "—";
}

function updateSelectionSummary() {
  const project = state.collectionName || $("collectionName")?.value.trim() || "—";
  setText("summaryProject", project);

  setText("summaryPipeline", pipelineLabel());
  const personas = state.pipelineDetail?.personas || [];
  const meta = [];
  if (state.pipelineDetail?.profile) {
    meta.push(`Profile: ${state.pipelineDetail.profile}`);
  }
  if (state.pipelineDetail?.evaluation_mode === "multi_persona" && personas.length) {
    meta.push(`Personas: ${personas.map((p) => p.label || p.id).join(", ")}`);
  }
  setText("summaryPipelineMeta", meta.join(" · "));

  setText("summaryCriteria", criteriaLabel());

  const draftRow = $("summaryDraftRow");
  const draftName = $("draftStatus")?.textContent?.replace(/^Uploaded:\s*/, "") || "";
  if (draftRow && state.draftArtifactId && draftName && !draftName.startsWith("PDF of")) {
    draftRow.hidden = false;
    setText("summaryDraft", draftName);
  } else if (draftRow) {
    draftRow.hidden = true;
    setText("summaryDraft", "—");
  }
}

function updateSelectionSummaryVisibility() {
  const summary = $("selectionSummary");
  if (!summary) {
    return;
  }
  summary.hidden = state.step < 2;
}

function setButtonLoading(button, loading, loadingText) {
  if (!button) {
    return;
  }
  const label = button.querySelector(".btn-label") || button;
  if (loading) {
    button.disabled = true;
    button.classList.add("loading");
    if (label === button) {
      if (!button.dataset.originalHtml) {
        button.dataset.originalHtml = button.innerHTML;
      }
      button.innerHTML = `<span class="spinner" aria-hidden="true"></span>${loadingText || "Working…"}`;
    } else {
      label.textContent = loadingText || "Working…";
    }
    return;
  }

  button.disabled = false;
  button.classList.remove("loading");
  if (button.dataset.originalHtml) {
    button.innerHTML = button.dataset.originalHtml;
    delete button.dataset.originalHtml;
  } else if (label !== button) {
    label.textContent = "Run review";
  }
}

function showReviewProgress() {
  const progress = $("reviewProgress");
  const report = $("reportContent");
  if (progress) {
    progress.hidden = false;
  }
  if (report) {
    report.hidden = true;
  }
}

function showReportContent() {
  const progress = $("reviewProgress");
  const report = $("reportContent");
  if (progress) {
    progress.hidden = true;
  }
  if (report) {
    report.hidden = false;
  }
}

function getReviewIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const queryReview = params.get("review");
  if (queryReview) {
    return queryReview;
  }
  const match = window.location.pathname.match(/^\/review\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : "";
}

function buildReviewUrl(reviewId) {
  return `/review/${encodeURIComponent(reviewId)}`;
}

function syncReviewUrl(reviewId) {
  const nextUrl = reviewId ? buildReviewUrl(reviewId) : "/";
  const currentUrl = `${window.location.pathname}${window.location.search}`;
  if (currentUrl !== nextUrl) {
    history.replaceState({ reviewId: reviewId || "" }, "", nextUrl);
  }
}

function updateShareLink() {
  const shareRow = $("reportShare");
  const link = $("reportShareLink");
  if (!shareRow || !link || !state.reviewId) {
    if (shareRow) {
      shareRow.style.display = "none";
    }
    return;
  }
  const url = `${window.location.origin}${buildReviewUrl(state.reviewId)}`;
  shareRow.style.display = "flex";
  link.href = url;
  link.textContent = url;
}

async function copyReviewLink() {
  if (!state.reviewId) {
    return;
  }
  const url = `${window.location.origin}${buildReviewUrl(state.reviewId)}`;
  await navigator.clipboard.writeText(url);
  const button = $("btnCopyReviewLink");
  const previous = button.textContent;
  button.textContent = "Copied!";
  setTimeout(() => {
    button.textContent = previous;
  }, 1500);
}

async function openReviewFromUrl(reviewId) {
  state.reviewId = reviewId;
  syncReviewUrl(reviewId);

  const status = await fetchJSON(`${API}/reviews/${reviewId}`);
  state.collectionName = status.collection_name || "";
  state.pipelineId = status.pipeline_id || "";
  if (state.pipelineId && $("pipelineSelect")) {
    $("pipelineSelect").value = state.pipelineId;
    await onPipelineChange();
  }
  if ($("collectionName")) {
    $("collectionName").value = state.collectionName;
  }
  state.criteriaSetName = status.criteria_set_name || state.criteriaSetName;
  if (status.criteria_source_name) {
    state.rfpFilename = status.criteria_source_name;
  }
  if (state.criteriaSetName && $("criteriaSetSelect")) {
    $("criteriaSetSelect").value = state.criteriaSetName;
  }
  const firstResult = (status.results || [])[0];
  if (firstResult?.filename) {
    state.draftArtifactId = firstResult.artifact_id || firstResult.filename.replace(/\.pdf$/i, "");
    $("draftStatus").textContent = `Uploaded: ${firstResult.filename}`;
  }
  updateSelectionSummary();
  updateProgress(status);

  if (status.status === "completed") {
    await loadReport();
    setStep(3);
    showReportContent();
    return;
  }

  setStep(3);
  showReviewProgress();
  if (["running", "pending"].includes(status.status)) {
    const cancelButton = $("btnCancelReview");
    if (cancelButton) {
      cancelButton.disabled = false;
    }
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
    }
    state.pollTimer = setInterval(pollReview, 2000);
    return;
  }

  const cancelButton = $("btnCancelReview");
  if (cancelButton) {
    cancelButton.disabled = true;
  }
  if (status.error) {
    showError(status.error);
  }
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
  updateSelectionSummary();
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

async function handleUploadAndStart() {
  const btn = $("btnRunReview");
  setButtonLoading(btn, true, "Uploading…");
  try {
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
    state.criteriaSetName = $("criteriaSetSelect")?.value || state.criteriaSetName;
    updateSelectionSummary();

    setStep(3);
    showReviewProgress();
    $("progressLabel").textContent = "Starting review…";
    $("progressFill").style.width = "0%";
    $("logBox").innerHTML = "";
    setButtonLoading(btn, true, "Starting review…");

    await startReview();
  } finally {
    setButtonLoading(btn, false);
  }
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
  const progressFill = $("progressFill");
  if (progressFill) {
    progressFill.style.width = `${pct}%`;
  }
  setText(
    "progressLabel",
    `${status.status} — ${current}/${total}` +
      (status.current_item ? ` · ${status.current_item}` : ""),
  );
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
    $("btnCancelReview").disabled = true;
    if (status.status === "completed") {
      await loadReport();
      showReportContent();
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
  syncReviewUrl(state.reviewId);
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

function buildEvaluationSummary(evaluations) {
  if (!evaluations?.length) {
    return "";
  }
  const met = evaluations.filter((item) => item.answer === true).length;
  const notMet = evaluations.filter((item) => item.answer === false).length;
  const other = evaluations.length - met - notMet;
  const parts = [`${evaluations.length} criteria evaluated`];
  if (met) {
    parts.push(`${met} met`);
  }
  if (notMet) {
    parts.push(`${notMet} not met`);
  }
  if (other) {
    parts.push(`${other} partial/other`);
  }
  return `${parts.join(" · ")}. See per-criterion results below.`;
}

async function loadReport() {
  const report = await fetchJSON(`${API}/reviews/${state.reviewId}/report`);
  $("reportMeta").textContent =
    `Review ${report.review_id} · ${report.pipeline_id} · ${report.status}`;
  updateShareLink();

  const artifact = (report.artifacts || [])[0];
  const synthesis = artifact?.synthesis?.summary || buildEvaluationSummary(artifact?.evaluations);
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
    state.pollTimer = null;
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
  $("progressLabel").textContent = "Starting…";
  showReviewProgress();
  updateShareLink();
  syncReviewUrl("");
  setStep(1);
}

function bindEvents() {
  $("pipelineSelect")?.addEventListener("change", () => onPipelineChange().catch(showError));
  $("criteriaSetSelect")?.addEventListener("change", () => {
    state.criteriaSetName = $("criteriaSetSelect").value;
    updateSelectionSummary();
  });
  $("collectionName")?.addEventListener("input", () => updateSelectionSummary());
  $("btnToUpload")?.addEventListener("click", async () => {
    try {
      if (!$("collectionName").value.trim()) {
        throw new Error("Enter a project name.");
      }
      if (!pipelineHasExtractor(state.pipelineDetail) && !$("criteriaSetSelect").value) {
        throw new Error("Select a criteria set.");
      }
      state.collectionName = $("collectionName").value.trim();
      state.criteriaSetName = $("criteriaSetSelect").value || state.criteriaSetName;
      updateSelectionSummary();
      setStep(2);
    } catch (err) {
      showError(err.message);
    }
  });
  $("btnBackSetup")?.addEventListener("click", () => setStep(1));
  $("btnRunReview")?.addEventListener("click", () => handleUploadAndStart().catch(showError));
  $("btnCancelReview")?.addEventListener("click", () => cancelReview().catch(showError));
  $("btnCopyReviewLink")?.addEventListener("click", () => copyReviewLink().catch(showError));
  $("btnNewReview")?.addEventListener("click", resetApp);
  window.addEventListener("popstate", () => {
    const reviewId = getReviewIdFromUrl();
    if (reviewId) {
      openReviewFromUrl(reviewId).catch(showError);
      return;
    }
    if (state.reviewId) {
      resetApp();
    }
  });
}

async function init() {
  bindEvents();
  try {
    await Promise.all([loadPipelines(), loadCriteriaSets()]);
    const reviewId = getReviewIdFromUrl();
    if (reviewId) {
      await openReviewFromUrl(reviewId);
    }
  } catch (err) {
    showError(err.message);
  }
}

init();
