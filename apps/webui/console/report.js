const summaryContent = document.getElementById("summary-content");
const proofContent = document.getElementById("proof-content");
const diffContent = document.getElementById("diff-content");
const evidenceContent = document.getElementById("evidence-content");
const rawReportEl = document.getElementById("raw-report");
const rawLink = document.getElementById("raw-link");

function getJobId() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("job");
  if (fromQuery) return fromQuery;
  if (window.location.hash) return window.location.hash.replace(/^#/, "");
  return "";
}

function formatTimestamp(value) {
  if (!value && value !== 0) return "–";
  if (typeof value === "number") {
    return new Date(value * 1000).toLocaleString();
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return String(value);
  return new Date(parsed).toLocaleString();
}

function formatValue(value) {
  if (value === null || value === undefined) return "–";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch (error) {
    return String(value);
  }
}

function renderSummary(report) {
  if (!report || typeof report !== "object") {
    summaryContent.textContent = "Report unavailable.";
    return;
  }
  summaryContent.innerHTML = "";
  const items = [];
  items.push(["Job ID", report.job_id || "–"]);
  items.push(["Verdict", report.verdict || "–"]);
  if (report.score !== undefined && report.score !== null) {
    items.push(["Score", Number(report.score).toFixed(2)]);
  }
  items.push(["From Node", report.from_node || "–"]);
  items.push(["Verifier Node", report.verifier_node || "–"]);
  const timestamps = report.timestamps || {};
  items.push(["Submitted", formatTimestamp(timestamps.submitted)]);
  items.push(["Verified", formatTimestamp(timestamps.verified)]);
  if (report.proof_hash) {
    items.push(["Proof Hash", report.proof_hash]);
  }
  const proofCounts = report.proof_counts || {};
  items.push(["Proof Pass", proofCounts.pass ?? 0]);
  items.push(["Proof Fail", proofCounts.fail ?? 0]);
  items.push(["Proof Error", proofCounts.error ?? 0]);
  for (const [label, value] of items) {
    const wrapper = document.createElement("div");
    wrapper.className = "summary-item";
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = String(value ?? "–");
    wrapper.append(dt, dd);
    summaryContent.appendChild(wrapper);
  }
}

function renderProofs(proofs) {
  proofContent.innerHTML = "";
  if (!Array.isArray(proofs) || proofs.length === 0) {
    proofContent.textContent = "No proofs recorded.";
    return;
  }
  const table = document.createElement("table");
  table.className = "proof-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Step</th><th>Precondition</th><th>Postcondition</th><th>Status</th></tr>";
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const trace of proofs) {
    const row = document.createElement("tr");
    const stepCell = document.createElement("td");
    stepCell.textContent = trace.step ?? "–";
    const preCell = document.createElement("td");
    preCell.innerHTML = trace.pre ? `<code class="proof-expression">${trace.pre}</code>` : "–";
    const postCell = document.createElement("td");
    postCell.innerHTML = trace.post ? `<code class="proof-expression">${trace.post}</code>` : "–";
    const statusCell = document.createElement("td");
    const status = (trace.status || "skip").toString().toLowerCase();
    const badge = document.createElement("span");
    badge.className = `proof-status ${status}`;
    badge.textContent = trace.status ? trace.status.replace(/_/g, " ") : "SKIP";
    const detail = [];
    if (trace.pre_status && trace.pre_status !== trace.status) {
      detail.push(`pre: ${trace.pre_status}`);
    }
    if (trace.post_status && trace.post_status !== trace.status) {
      detail.push(`post: ${trace.post_status}`);
    }
    if (trace.error) {
      detail.push(trace.error);
    }
    if (detail.length) {
      badge.title = detail.join(" | ");
    }
    statusCell.appendChild(badge);
    row.append(stepCell, preCell, postCell, statusCell);
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  proofContent.appendChild(table);
}

function renderDiffs(diffs) {
  diffContent.innerHTML = "";
  if (!Array.isArray(diffs) || diffs.length === 0) {
    diffContent.textContent = "No divergences detected.";
    return;
  }
  const table = document.createElement("table");
  table.className = "diff-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Step</th><th>Field</th><th>Expected</th><th>Observed</th></tr>";
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const diff of diffs) {
    const row = document.createElement("tr");
    const stepCell = document.createElement("td");
    stepCell.textContent = diff.step ?? "–";
    const fieldCell = document.createElement("td");
    fieldCell.textContent = diff.field || "–";
    const expectedCell = document.createElement("td");
    expectedCell.textContent = formatValue(diff.expected);
    const observedCell = document.createElement("td");
    observedCell.textContent = formatValue(diff.observed);
    row.append(stepCell, fieldCell, expectedCell, observedCell);
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  diffContent.appendChild(table);
}

function renderEvidence(evidence) {
  evidenceContent.innerHTML = "";
  if (!evidence || typeof evidence !== "object") {
    evidenceContent.textContent = "No evidence recorded.";
    return;
  }
  const container = document.createElement("div");
  container.className = "summary-grid";
  for (const [key, value] of Object.entries(evidence)) {
    const item = document.createElement("div");
    item.className = "summary-item";
    const dt = document.createElement("dt");
    dt.textContent = key.replace(/_/g, " ");
    const dd = document.createElement("dd");
    dd.textContent = formatValue(value);
    item.append(dt, dd);
    container.appendChild(item);
  }
  evidenceContent.appendChild(container);
}

async function loadReport() {
  const jobId = getJobId();
  if (!jobId) {
    summaryContent.textContent = "Missing job identifier.";
    return;
  }
  rawLink.href = `/admin/verify/report/${encodeURIComponent(jobId)}`;
  try {
    const headers = {};
    if (window.NODE_TOKEN) {
      headers["X-Node-Token"] = window.NODE_TOKEN;
    }
    const response = await fetch(`/admin/verify/report/${encodeURIComponent(jobId)}`, {
      headers,
    });
    if (!response.ok) {
      throw new Error(`request failed: ${response.status}`);
    }
    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    if (data && typeof data === "object" && "csrf_token" in data) {
      delete data.csrf_token;
    }
    renderSummary(data);
    renderProofs(data.proofs);
    renderDiffs(data.diffs);
    renderEvidence(data.evidence);
    rawReportEl.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    summaryContent.textContent = "Failed to load report.";
    proofContent.textContent = "";
    diffContent.textContent = "";
    evidenceContent.textContent = "";
    rawReportEl.textContent = String(error);
  }
}

loadReport();
