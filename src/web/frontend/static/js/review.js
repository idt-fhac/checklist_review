const API = "/api/v1";

const state = {
  step: 1,
  pipelines: [],
  criteriaSets: [],
  pipelineId: "",
  pipelineDetail: null,
  collectionName: "",
  criteriaSetName: "",
  criteriaMode: "preset",
  rfpFilename: "",
  draftArtifactId: "",
  reviewId: "",
  pollTimer: null,
  reportArtifact: null,
  activePersonaId: "",
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
  const mode = state.criteriaMode || $("criteriaMode")?.value || "preset";
  if (mode === "extract") {
    return state.rfpFilename ? `From RFP: ${state.rfpFilename}` : "Extract from RFP";
  }
  if (mode === "custom") {
    return "Custom criteria";
  }
  return $("criteriaSetSelect")?.value || state.criteriaSetName || "—";
}

function artifactIdFromFilename(filename) {
  return filename.replace(/\.[^.]+$/, "");
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
    state.criteriaMode = "extract";
  } else if (status.criteria_set_name === "custom") {
    state.criteriaMode = "custom";
  } else {
    state.criteriaMode = "preset";
  }
  if (state.criteriaSetName && $("criteriaSetSelect")) {
    $("criteriaSetSelect").value = state.criteriaSetName;
  }
  updateCriteriaModeUI();
  const firstResult = (status.results || [])[0];
  if (firstResult?.filename) {
    state.draftArtifactId = firstResult.artifact_id || artifactIdFromFilename(firstResult.filename);
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

function updateCriteriaModeUI() {
  const hasExtractor = pipelineHasExtractor(state.pipelineDetail);
  const modeSelect = $("criteriaMode");
  const presetSelect = $("criteriaSetSelect");
  const customArea = $("customCriteria");
  const hint = $("criteriaModeHint");
  if (!modeSelect || !presetSelect || !customArea) {
    return;
  }

  const extractOption = modeSelect.querySelector('option[value="extract"]');
  if (extractOption) {
    extractOption.hidden = !hasExtractor;
  }

  if (hasExtractor && !["extract", "custom", "preset"].includes(state.criteriaMode)) {
    state.criteriaMode = "extract";
  } else if (!hasExtractor && state.criteriaMode === "extract") {
    state.criteriaMode = "preset";
  }
  modeSelect.value = state.criteriaMode;

  const mode = modeSelect.value;
  presetSelect.hidden = mode !== "preset";
  customArea.hidden = mode !== "custom";

  if (hint) {
    if (mode === "extract") {
      hint.textContent = "Criteria will be extracted from the uploaded RFP automatically.";
    } else if (mode === "custom") {
      hint.textContent = "Enter one criterion per line, or paste YAML with a criteria list.";
    } else {
      hint.textContent = "Select a saved criteria set from the workspace.";
    }
  }
  updateSelectionSummary();
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
  if (pipelineHasExtractor(state.pipelineDetail)) {
    state.criteriaMode = "extract";
  } else if (state.criteriaMode === "extract") {
    state.criteriaMode = "preset";
  }
  updateCriteriaModeUI();
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

async function saveCustomCriteria() {
  const text = $("customCriteria")?.value.trim();
  if (!text) {
    throw new Error("Enter custom criteria.");
  }
  await fetchJSON(`${API}/collections/${encodeURIComponent(state.collectionName)}/criteria`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ criteria_set_name: "custom", text }),
  });
  state.criteriaSetName = "custom";
}

async function handleUploadAndStart() {
  const btn = $("btnRunReview");
  setButtonLoading(btn, true, "Uploading…");
  try {
    await ensureCollection();
    const mode = $("criteriaMode")?.value || state.criteriaMode;
    state.criteriaMode = mode;
    const hasExtractor = pipelineHasExtractor(state.pipelineDetail);
    const rfpInput = $("rfpFile");
    const draftInput = $("draftFile");

    if (mode === "extract" && !rfpInput.files.length) {
      throw new Error("Upload the RFP / requirements document for this pipeline.");
    }
    if (mode === "preset" && !$("criteriaSetSelect")?.value) {
      throw new Error("Select a criteria set.");
    }
    if (mode === "custom" && !$("customCriteria")?.value.trim()) {
      throw new Error("Enter custom criteria.");
    }
    if (!draftInput.files.length) {
      throw new Error("Upload the draft document to evaluate.");
    }

    if (rfpInput.files.length) {
      const result = await uploadDocument(rfpInput.files[0], "rfp");
      state.rfpFilename = result.filename;
      $("rfpCard").classList.add("uploaded");
      $("rfpStatus").textContent = `Uploaded: ${result.filename}`;
    }

    const draftResult = await uploadDocument(draftInput.files[0], "artifact");
    state.draftArtifactId = draftResult.artifact_id || artifactIdFromFilename(draftResult.filename);
    $("draftCard").classList.add("uploaded");
    $("draftStatus").textContent = `Uploaded: ${draftResult.filename}`;

    if (mode === "custom") {
      setButtonLoading(btn, true, "Saving criteria…");
      await saveCustomCriteria();
    } else if (mode === "preset") {
      state.criteriaSetName = $("criteriaSetSelect").value;
    } else if (hasExtractor) {
      state.criteriaSetName = "extracted";
    }

    await saveReferences();
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
  const mode = $("criteriaMode")?.value || state.criteriaMode;
  const body = {
    collection_name: state.collectionName,
    pipeline_id: state.pipelineId,
    artifact_ids: state.draftArtifactId ? [state.draftArtifactId] : undefined,
    skip_existing: false,
  };

  if (mode === "extract") {
    body.criteria_source_name = state.rfpFilename;
    body.criteria_set_name = "extracted";
  } else if (mode === "custom") {
    body.criteria_set_name = "custom";
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

function sanitizeHtml(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("script, iframe, object, embed, form, style").forEach((el) => el.remove());
  doc.querySelectorAll("*").forEach((el) => {
    [...el.attributes].forEach((attr) => {
      if (attr.name.startsWith("on") || attr.name === "srcdoc") {
        el.removeAttribute(attr.name);
      }
    });
  });
  return doc.body.innerHTML;
}

function toggleCollapsibleSection(section) {
  if (!section) {
    return;
  }
  const button = section.querySelector(".collapsible-header");
  const body = section.querySelector(".collapsible-body");
  if (!button || !body) {
    return;
  }
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", expanded ? "false" : "true");
  section.classList.toggle("collapsed", expanded);
}

function bindCollapsibleSections() {
  document.querySelectorAll(".collapsible-header").forEach((button) => {
    button.addEventListener("click", () => {
      toggleCollapsibleSection(button.closest(".collapsible-section"));
    });
  });
}

function renderReportSummary(text, { markdown = false } = {}) {
  const el = $("reportSummary");
  if (!el) {
    return;
  }
  if (!text) {
    el.textContent = "No synthesis available.";
    el.classList.remove("markdown-body");
    return;
  }
  if (markdown && typeof marked !== "undefined") {
    el.innerHTML = sanitizeHtml(
      marked.parse(text, { breaks: true, gfm: true }),
    );
    el.classList.add("markdown-body");
    return;
  }
  el.textContent = text;
  el.classList.remove("markdown-body");
}

function renderOverviewStats(summary) {
  const container = $("overviewStats");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!summary) {
    return;
  }

  const cards = [
    {
      label: "Criteria",
      value: summary.total ?? 0,
      detail: `${summary.met ?? 0} met · ${summary.not_met ?? 0} not met`,
    },
  ];

  if (summary.weighted_score_percent != null) {
    cards.push({
      label: "Weighted score",
      value: `${summary.weighted_score_percent}%`,
      detail: `${summary.weighted_earned ?? 0} / ${summary.weighted_total ?? 0} points earned`,
    });
  }

  if (summary.disagreements) {
    cards.push({
      label: "Disagreements",
      value: summary.disagreements,
      detail: "Personas diverged on one or more criteria",
    });
  }

  for (const card of cards) {
    const el = document.createElement("div");
    el.className = "stat-card";
    el.innerHTML = `
      <span class="stat-label">${card.label}</span>
      <span class="stat-value">${card.value}</span>
      <span class="stat-detail">${card.detail}</span>
    `;
    container.appendChild(el);
  }
}

function renderOverviewTable(rows) {
  const tbody = $("overviewBody");
  const section = $("reportOverview");
  if (!tbody || !section) {
    return;
  }
  tbody.innerHTML = "";
  if (!rows?.length) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  for (const row of rows) {
    const tr = document.createElement("tr");

    const criterionCell = document.createElement("td");
    criterionCell.textContent = row.description || row.criterion_id || "Criterion";

    const weightCell = document.createElement("td");
    weightCell.textContent = row.weight_label || "—";

    const resultCell = document.createElement("td");
    resultCell.appendChild(answerBadge(row.answer));
    if (row.disagreement) {
      const warn = document.createElement("div");
      warn.className = "persona-row";
      warn.textContent = "Personas disagreed";
      resultCell.appendChild(warn);
    }

    const refCell = document.createElement("td");
    refCell.textContent = row.source_ref || "—";

    tr.appendChild(criterionCell);
    tr.appendChild(weightCell);
    tr.appendChild(resultCell);
    tr.appendChild(refCell);
    tbody.appendChild(tr);
  }
}

function buildOverviewLookup(overview) {
  const lookup = new Map();
  for (const row of overview?.rows || []) {
    if (row.criterion_id) {
      lookup.set(row.criterion_id, row);
    }
  }
  return lookup;
}

function renderEvidenceList(supportingTexts) {
  const list = document.createElement("div");
  list.className = "evidence-list";
  const items = (supportingTexts || []).slice(0, 4);
  if (!items.length) {
    list.textContent = "—";
    return list;
  }
  for (const item of items) {
    const block = document.createElement("div");
    block.className = "evidence-item";
    const meta = document.createElement("div");
    meta.className = "evidence-meta";
    const page = item.page_number >= 0 ? `Page ${item.page_number}` : "Analysis";
    meta.textContent = page;
    const text = document.createElement("div");
    text.className = "evidence-text";
    text.textContent = item.short_explanation || item.text_crop || "";
    block.appendChild(meta);
    block.appendChild(text);
    list.appendChild(block);
  }
  return list;
}

function getPersonaReviewViews(artifact) {
  const views = [];
  const manifestPersonas = artifact?.persona_manifest?.personas || [];
  const personaEvaluations = artifact?.persona_evaluations || {};

  if (manifestPersonas.length && personaEvaluations) {
    for (const persona of manifestPersonas) {
      const evaluations = personaEvaluations[persona.id];
      if (Array.isArray(evaluations) && evaluations.length) {
        views.push({
          id: persona.id,
          label: persona.label || persona.id,
          evaluations,
        });
      }
    }
    return views;
  }

  if (artifact?.evaluations?.length) {
    views.push({
      id: "merged",
      label: "Reviewer",
      evaluations: artifact.evaluations,
    });
  }
  return views;
}

function renderPersonaReviewTable(view, overviewLookup) {
  const tbody = $("personaReviewBody");
  if (!tbody || !view) {
    return;
  }
  tbody.innerHTML = "";

  for (const item of view.evaluations) {
    const tr = document.createElement("tr");
    const overviewRow = overviewLookup.get(item.criterion_id) || {};

    const criterionCell = document.createElement("td");
    criterionCell.textContent =
      item.criterion_text || overviewRow.description || item.criterion_id || "Criterion";

    const weightCell = document.createElement("td");
    weightCell.textContent = overviewRow.weight_label || "—";

    const resultCell = document.createElement("td");
    resultCell.appendChild(answerBadge(item.answer));

    const evidenceCell = document.createElement("td");
    evidenceCell.appendChild(renderEvidenceList(item.supporting_texts));

    tr.appendChild(criterionCell);
    tr.appendChild(weightCell);
    tr.appendChild(resultCell);
    tr.appendChild(evidenceCell);
    tbody.appendChild(tr);
  }
}

function renderPersonaReviews(artifact) {
  const section = $("personaReviews");
  const tabs = $("personaTabs");
  if (!section || !tabs) {
    return;
  }

  const views = getPersonaReviewViews(artifact);
  tabs.innerHTML = "";
  if (!views.length) {
    section.hidden = true;
    state.activePersonaId = "";
    return;
  }

  section.hidden = false;
  if (!views.some((view) => view.id === state.activePersonaId)) {
    state.activePersonaId = views[0].id;
  }

  for (const view of views) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "persona-tab";
    button.dataset.personaId = view.id;
    button.textContent = view.label;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", view.id === state.activePersonaId ? "true" : "false");
    if (view.id === state.activePersonaId) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => {
      state.activePersonaId = view.id;
      renderPersonaReviews(state.reportArtifact);
    });
    tabs.appendChild(button);
  }

  const activeView = views.find((view) => view.id === state.activePersonaId) || views[0];
  renderPersonaReviewTable(activeView, buildOverviewLookup(artifact?.overview));
}

async function openDocumentViewer(viewUrl, label) {
  const data = await fetchJSON(viewUrl);
  $("documentViewerTitle").textContent = `${label || "Document"}: ${data.filename}`;
  $("documentViewerContent").textContent = data.content || "";
  const viewer = $("documentViewer");
  if (viewer) {
    viewer.hidden = false;
    viewer.removeAttribute("hidden");
  }
}

function closeDocumentViewer() {
  const viewer = $("documentViewer");
  if (!viewer) {
    return;
  }
  viewer.hidden = true;
  viewer.setAttribute("hidden", "");
  $("documentViewerContent").textContent = "";
}

function renderInputDocuments(report) {
  const section = $("reportInputDocuments");
  const container = $("inputDocumentLinks");
  if (!section || !container) {
    return;
  }
  container.innerHTML = "";
  const docs = report.input_documents || [];
  if (!docs.length) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  for (const doc of docs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "doc-link";
    button.textContent = `${doc.label || doc.role}: ${doc.filename}`;
    button.addEventListener("click", () => {
      openDocumentViewer(doc.view_url, doc.label || doc.role).catch(showError);
    });
    container.appendChild(button);
  }
}

async function loadReport() {
  const report = await fetchJSON(`${API}/reviews/${state.reviewId}/report`);
  $("reportMeta").textContent =
    `Review ${report.review_id} · ${report.pipeline_id} · ${report.status}`;
  updateShareLink();
  renderInputDocuments(report);

  const artifact = (report.artifacts || [])[0];
  state.reportArtifact = artifact;
  renderOverviewStats(artifact?.overview?.summary);
  renderOverviewTable(artifact?.overview?.rows);

  const synthesis = artifact?.synthesis?.summary || buildEvaluationSummary(artifact?.evaluations);
  renderReportSummary(synthesis, { markdown: Boolean(artifact?.synthesis?.summary) });

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

  renderPersonaReviews(artifact);
}

function resetApp() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  state.reviewId = "";
  state.reportArtifact = null;
  state.activePersonaId = "";
  state.rfpFilename = "";
  state.draftArtifactId = "";
  state.criteriaMode = pipelineHasExtractor(state.pipelineDetail) ? "extract" : "preset";
  if ($("customCriteria")) {
    $("customCriteria").value = "";
  }
  updateCriteriaModeUI();
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
  $("criteriaMode")?.addEventListener("change", () => {
    state.criteriaMode = $("criteriaMode").value;
    updateCriteriaModeUI();
  });
  $("criteriaSetSelect")?.addEventListener("change", () => {
    state.criteriaSetName = $("criteriaSetSelect").value;
    updateSelectionSummary();
  });
  $("customCriteria")?.addEventListener("input", () => updateSelectionSummary());
  $("collectionName")?.addEventListener("input", () => updateSelectionSummary());
  $("btnToUpload")?.addEventListener("click", async () => {
    try {
      if (!$("collectionName").value.trim()) {
        throw new Error("Enter a project name.");
      }
      state.collectionName = $("collectionName").value.trim();
      updateSelectionSummary();
      setStep(2);
    } catch (err) {
      showError(err.message);
    }
  });
  $("btnBackSetup")?.addEventListener("click", () => setStep(1));
  $("btnBackToSetup")?.addEventListener("click", () => setStep(1));
  $("btnRunReview")?.addEventListener("click", () => handleUploadAndStart().catch(showError));
  $("btnCancelReview")?.addEventListener("click", () => cancelReview().catch(showError));
  $("btnCopyReviewLink")?.addEventListener("click", () => copyReviewLink().catch(showError));
  $("btnNewReview")?.addEventListener("click", resetApp);
  $("btnCloseDocumentViewer")?.addEventListener("click", (event) => {
    event.preventDefault();
    closeDocumentViewer();
  });
  $("documentViewer")?.querySelector(".document-viewer-panel")?.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  $("documentViewer")?.addEventListener("click", (event) => {
    if (event.target === $("documentViewer")) {
      closeDocumentViewer();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("documentViewer") && !$("documentViewer").hidden) {
      closeDocumentViewer();
    }
  });
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
  bindCollapsibleSections();
  try {
    await Promise.all([loadPipelines(), loadCriteriaSets()]);
    updateCriteriaModeUI();
    const reviewId = getReviewIdFromUrl();
    if (reviewId) {
      await openReviewFromUrl(reviewId);
    }
  } catch (err) {
    showError(err.message);
  }
}

init();
