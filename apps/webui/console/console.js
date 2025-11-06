const overviewGrid = document.getElementById("overview-grid");
const nodesTable = document.querySelector("#nodes-table tbody");
const memoryInfo = document.getElementById("memory-info");
const healthChecks = document.getElementById("health-checks");
const installButton = document.getElementById("install-button");
const moodLabel = document.getElementById("mood-label");
const moodIntensity = document.getElementById("mood-intensity");
const moodSpectrum = document.getElementById("mood-spectrum");
const emotionTone = document.getElementById("emotion-tone");
const emotionPulse = document.getElementById("emotion-pulse");
const goalText = document.getElementById("goal-text");
const goalStatus = document.getElementById("goal-status");
const goalPriority = document.getElementById("goal-priority");
const goalProgressFill = document.getElementById("goal-progress-fill");
const goalProgressLabel = document.getElementById("goal-progress-label");
const goalDeadline = document.getElementById("goal-deadline");
const loopProgressFill = document.getElementById("loop-progress-fill");
const loopProgressLabel = document.getElementById("loop-progress-label");
const loopMeta = document.getElementById("loop-meta");
const loopNext = document.getElementById("loop-next");
const verifierCounts = document.getElementById("verifier-counts");
const verifierTable = document.querySelector("#verifier-table tbody");

let csrfToken = null;
const verifierState = {
  jobs: [],
  counts: {},
  proofCounts: { pass: 0, fail: 0, error: 0 },
};

let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredPrompt = event;
  installButton.hidden = false;
});

installButton?.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  await deferredPrompt.userChoice;
  deferredPrompt = null;
  installButton.hidden = true;
});

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`request failed: ${response.status}`);
  const text = await response.text();
  if (!text) return {};
  const data = JSON.parse(text);
  if (data && typeof data === "object" && "csrf_token" in data) {
    csrfToken = data.csrf_token;
  }
  return data;
}

const STATUS_COLORS = {
  completed: "#22c55e",
  failed: "#f87171",
  blocked: "#f97316",
  needs_review: "#facc15",
  stuck: "#facc15",
  in_progress: "#38bdf8",
};

function clamp(value, min = 0, max = 1) {
  const number = Number(value);
  if (Number.isNaN(number)) return min;
  return Math.min(Math.max(number, min), max);
}

function formatPercent(value) {
  const clamped = clamp(value, 0, 100);
  return `${Math.round(clamped)}%`;
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) {
    return "";
  }
  const total = Math.max(0, Number(seconds));
  if (!Number.isFinite(total)) return "";
  if (total < 60) return `${Math.round(total)}s`;
  const minutes = Math.round(total / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) {
    const remainderMinutes = Math.round(minutes % 60);
    return remainderMinutes ? `${hours}h ${remainderMinutes}m` : `${hours}h`;
  }
  const days = Math.round(hours / 24);
  const remainderHours = hours % 24;
  return remainderHours ? `${days}d ${remainderHours}h` : `${days}d`;
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatRelativeAge(createdAtSeconds) {
  if (!createdAtSeconds) return "–";
  const created = Number(createdAtSeconds) * 1000;
  if (!Number.isFinite(created)) return "–";
  const deltaSeconds = (Date.now() - created) / 1000;
  if (deltaSeconds < 0) return "just now";
  return `${formatDuration(deltaSeconds)} ago`;
}

function renderMetrics(metrics) {
  overviewGrid.innerHTML = "";
  const items = [
    { label: "Role", value: metrics.role },
    { label: "Model", value: metrics.model },
    { label: "Backend", value: metrics.backend },
    { label: "Uptime", value: `${Math.round(metrics.uptime_seconds)} s` },
    { label: "Dream Loop", value: metrics.dream_loop?.active ? "Active" : "Idle" },
    { label: "Pending Goals", value: metrics.pending_goals },
  ];
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "metric";
    card.innerHTML = `<h3>${item.label}</h3><p>${item.value ?? "–"}</p>`;
    overviewGrid.appendChild(card);
  }
}

function renderNodes(payload) {
  nodesTable.innerHTML = "";
  for (const node of payload.nodes ?? []) {
    const tr = document.createElement("tr");
    const capabilities = Object.keys(node.capabilities || {}).join(", ") || "–";
    const voice = node.last_voice_activity ? new Date(node.last_voice_activity * 1000).toLocaleTimeString() : "–";
    tr.innerHTML = `
      <td>${node.hostname}</td>
      <td>${node.trust_level}${node.trust_score !== undefined ? ` (${node.trust_score})` : ""}</td>
      <td>${capabilities}</td>
      <td>${voice}</td>
    `;
    nodesTable.appendChild(tr);
  }
}

function normalizeTimestamp(value) {
  if (value === null || value === undefined) {
    return Date.now() / 1000;
  }
  if (typeof value === "number") {
    return value;
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return Date.now() / 1000;
  }
  return parsed / 1000;
}

function setJobInProgress(jobId, inProgress) {
  const job = verifierState.jobs.find((entry) => entry.job_id === jobId);
  if (job) {
    job.in_progress = inProgress;
  }
}

function upsertVerifierJob(job) {
  if (!job || !job.job_id) return;
  const existingIndex = verifierState.jobs.findIndex((entry) => entry.job_id === job.job_id);
  if (existingIndex >= 0) {
    verifierState.jobs.splice(existingIndex, 1);
  }
  verifierState.jobs.unshift(job);
  verifierState.jobs = verifierState.jobs.slice(0, 10);
}

function applyVerifierUpdate(update) {
  if (!update || typeof update !== "object") return;
  const verdict = update.verdict || "unknown";
  if (verdict) {
    verifierState.counts[verdict] = (verifierState.counts[verdict] || 0) + 1;
  }
  const job = {
    job_id: update.job_id,
    script_hash: update.script_hash || "",
    verdict,
    from_node: update.from_node || "–",
    created_at: normalizeTimestamp(update.timestamp),
    score: update.score,
    verifier_node: update.verifier_node,
    in_progress: false,
  };
  upsertVerifierJob(job);
  renderVerifier();
}

function renderVerifier() {
  if (verifierCounts) {
    verifierCounts.innerHTML = "";
    const counts = verifierState.counts || {};
    const entries = Object.entries(counts);
    if (!entries.length) {
      const empty = document.createElement("p");
      empty.textContent = "No verification activity today.";
      verifierCounts.appendChild(empty);
    } else {
      for (const [verdict, count] of entries) {
        const badge = document.createElement("div");
        badge.className = "verifier-badge";
        badge.innerHTML = `<strong>${count}</strong><span>${verdict.replace(/_/g, " ")}</span>`;
        verifierCounts.appendChild(badge);
      }
    }
    const proof = verifierState.proofCounts || {};
    const hasProofMetrics = Object.values(proof).some((value) => Number(value) > 0);
    if (hasProofMetrics) {
      const proofRow = document.createElement("div");
      proofRow.className = "proof-counts";
      const passPill = document.createElement("span");
      passPill.className = "proof-pill pass";
      passPill.innerHTML = `<strong>${proof.pass ?? 0}</strong> pass`;
      const failPill = document.createElement("span");
      failPill.className = "proof-pill fail";
      failPill.innerHTML = `<strong>${proof.fail ?? 0}</strong> fail`;
      const errorPill = document.createElement("span");
      errorPill.className = "proof-pill error";
      errorPill.innerHTML = `<strong>${proof.error ?? 0}</strong> error`;
      proofRow.append(passPill, failPill, errorPill);
      verifierCounts.appendChild(proofRow);
    }
  }

  if (verifierTable) {
    verifierTable.innerHTML = "";
    const jobs = [...verifierState.jobs];
    if (!jobs.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 6;
      cell.textContent = "No verification jobs yet.";
      row.appendChild(cell);
      verifierTable.appendChild(row);
      return;
    }
    for (const job of jobs) {
      const tr = document.createElement("tr");
      const link = document.createElement("a");
      link.href = `/console/report.html?job=${encodeURIComponent(job.job_id)}`;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = job.job_id;
      const jobCell = document.createElement("td");
      jobCell.appendChild(link);

      const scriptCell = document.createElement("td");
      scriptCell.textContent = (job.script_hash || "").toString().slice(0, 12) || "–";

      const verdictCell = document.createElement("td");
      if (job.in_progress) {
        const status = document.createElement("span");
        status.className = "verifier-status in-progress";
        const spinner = document.createElement("span");
        spinner.className = "spinner";
        const label = document.createElement("span");
        label.textContent = "In progress";
        status.append(spinner, label);
        verdictCell.appendChild(status);
      } else {
        verdictCell.textContent = job.verdict || "–";
      }

      const nodeCell = document.createElement("td");
      nodeCell.textContent = job.from_node || "–";

      const ageCell = document.createElement("td");
      ageCell.textContent = formatRelativeAge(job.created_at);

      const actionCell = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "verify-action-button";
      if (job.in_progress) {
        button.disabled = true;
        button.textContent = "Running…";
      } else {
        button.textContent = "Re-run verify";
        button.addEventListener("click", () => replayJob(job.job_id));
      }
      actionCell.appendChild(button);

      tr.append(jobCell, scriptCell, verdictCell, nodeCell, ageCell, actionCell);
      verifierTable.appendChild(tr);
    }
  }
}

async function replayJob(jobId) {
  if (!jobId) return;
  setJobInProgress(jobId, true);
  renderVerifier();
  try {
    const response = await fetch(`/admin/verify/replay/${jobId}`, {
      method: "POST",
      headers: {
        "X-Node-Token": window.NODE_TOKEN ?? "",
        "X-CSRF-Token": csrfToken ?? "",
      },
    });
    if (!response.ok) throw new Error(`request failed: ${response.status}`);
    const text = await response.text();
    if (text) {
      const data = JSON.parse(text);
      if (data && typeof data === "object") {
        if ("csrf_token" in data) {
          csrfToken = data.csrf_token;
          delete data.csrf_token;
        }
        applyVerifierUpdate(data);
      }
    }
  } catch (error) {
    console.error("Failed to replay verification", error);
  } finally {
    setJobInProgress(jobId, false);
    renderVerifier();
  }
}

function handleVerifierUpdate(event) {
  try {
    const data = JSON.parse(event.data);
    applyVerifierUpdate(data);
  } catch (error) {
    console.warn("Failed to parse verifier update", error);
  }
}

function renderMemory(summary) {
  memoryInfo.innerHTML = "";
  const fragment = document.createElement("pre");
  fragment.textContent = JSON.stringify(summary, null, 2);
  memoryInfo.appendChild(fragment);
}

function renderHealth(snapshot) {
  healthChecks.innerHTML = "";
  for (const check of snapshot.checks ?? []) {
    const div = document.createElement("div");
    div.className = "health-row";
    div.innerHTML = `
      <span>${check.name}</span>
      <span class="status">${check.healthy ? "✅" : "⚠️"}</span>
    `;
    healthChecks.appendChild(div);
  }
  if (!snapshot.checks?.length) {
    const fallback = document.createElement("p");
    fallback.textContent = "No watchdog checks registered yet.";
    healthChecks.appendChild(fallback);
  }
}

function renderDream(dream) {
  if (!dream || typeof dream !== "object") {
    return;
  }
  const mood = dream.mood ?? {};
  const pulse = dream.pulse ?? {};
  const loop = dream.loop ?? {};
  const progress = loop.progress ?? {};
  const goal = dream.active_goal ?? null;

  const dominant = mood.dominant ?? "Neutral";
  const intensity = typeof mood.intensity === "number" ? clamp(mood.intensity) : 0;
  const pulseColor = typeof pulse.color === "string" ? pulse.color : "#38bdf8";
  const pulseIntensity = typeof pulse.intensity === "number" ? clamp(pulse.intensity) : intensity;
  if (moodLabel) moodLabel.textContent = dominant;
  if (moodIntensity) moodIntensity.textContent = formatPercent(intensity * 100);
  if (emotionTone) {
    const tone = pulse.tone || pulse.level || dominant;
    emotionTone.textContent = (tone || "Neutral").toString().toUpperCase();
  }
  if (emotionPulse) {
    emotionPulse.style.setProperty("--pulse-color", pulseColor);
    emotionPulse.style.setProperty("--pulse-intensity", String(pulseIntensity));
  }
  if (moodSpectrum) {
    const top = Array.isArray(mood.top) ? mood.top : [];
    if (top.length) {
      moodSpectrum.innerHTML = top
        .map((entry) => {
          const label = entry.label ?? "";
          const percent = typeof entry.percent === "number" ? entry.percent : (entry.value ?? 0) * 100;
          return `<span>${label}: ${formatPercent(percent)}</span>`;
        })
        .join("");
    } else {
      moodSpectrum.innerHTML = "<span>Awaiting signals</span>";
    }
  }

  if (goalText) {
    if (goal && goal.text) {
      goalText.textContent = String(goal.text ?? "");
      const status = (goal.status ?? "active").toString().toLowerCase();
      if (goalStatus) {
        goalStatus.textContent = status.replace(/_/g, " ").toUpperCase();
        const statusColor = STATUS_COLORS[status] ?? pulseColor;
        goalStatus.style.color = statusColor;
      }
      if (goalPriority) {
        goalPriority.textContent =
          goal.priority !== undefined && goal.priority !== null ? `Priority ${goal.priority}` : "";
      }
      const goalProgress = goal.progress ?? {};
      const fraction = clamp(
        typeof goalProgress.fraction === "number"
          ? goalProgress.fraction
          : (typeof goalProgress.percent === "number" ? goalProgress.percent / 100 : 0)
      );
      const percent = typeof goalProgress.percent === "number" ? goalProgress.percent : fraction * 100;
      if (goalProgressFill) {
        const progressColor = STATUS_COLORS[(goal.status ?? "").toString().toLowerCase()] ?? pulseColor;
        goalProgressFill.style.setProperty("--progress-color", progressColor);
        goalProgressFill.style.width = `${clamp(percent, 0, 100)}%`;
      }
      if (goalProgressLabel) goalProgressLabel.textContent = formatPercent(percent);
      if (goalDeadline) {
        if (goal.deadline) {
          goalDeadline.textContent = `Deadline: ${formatTimestamp(goal.deadline)}`;
        } else if (goal.scheduled_at) {
          goalDeadline.textContent = `Scheduled: ${formatTimestamp(goal.scheduled_at)}`;
        } else {
          goalDeadline.textContent = "";
        }
      }
    } else {
      goalText.textContent = "No active goals.";
      if (goalStatus) {
        goalStatus.textContent = "";
        goalStatus.style.color = "#94a3b8";
      }
      if (goalPriority) goalPriority.textContent = "";
      if (goalProgressFill) {
        goalProgressFill.style.width = "0%";
        goalProgressFill.style.setProperty("--progress-color", "#38bdf8");
      }
      if (goalProgressLabel) goalProgressLabel.textContent = "0%";
      if (goalDeadline) goalDeadline.textContent = "";
    }
  }

  const loopFraction = clamp(
    typeof progress.fraction === "number"
      ? progress.fraction
      : (typeof progress.percent === "number" ? progress.percent / 100 : 0)
  );
  const loopPercent = typeof progress.percent === "number" ? progress.percent : loopFraction * 100;
  if (loopProgressFill) {
    const loopColor = loop.active ? pulseColor : "#94a3b8";
    loopProgressFill.style.setProperty("--progress-color", loopColor);
    loopProgressFill.style.width = `${clamp(loopPercent, 0, 100)}%`;
  }
  if (loopProgressLabel) loopProgressLabel.textContent = formatPercent(loopPercent);
  const sinceLabel = progress.since_label || formatDuration(progress.seconds_since_last_cycle);
  if (loopMeta) {
    if (sinceLabel) {
      const timestamp = loop.last_cycle ? formatTimestamp(loop.last_cycle) : null;
      loopMeta.textContent = timestamp
        ? `Last cycle ${sinceLabel} ago (${timestamp})`
        : `Last cycle ${sinceLabel} ago`;
    } else {
      loopMeta.textContent = loop.active ? "Dream loop active" : "Dream loop idle";
    }
  }
  if (loopNext) {
    const untilLabel = progress.until_label || formatDuration(progress.seconds_until_next_cycle);
    loopNext.textContent = untilLabel ? `Next cycle in ${untilLabel}` : "";
  }
}

async function refreshAll() {
  try {
    const status = await fetchJson("/admin/status", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderMetrics(status);
    const dream = await fetchJson("/admin/dream", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderDream(dream);
    const nodes = await fetchJson("/admin/nodes", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderNodes(nodes);
    let verifierList = { reports: [] };
    try {
      verifierList = await fetchJson("/admin/verify/list?limit=5", {
        headers: { "X-Node-Token": window.NODE_TOKEN ?? "" },
      });
    } catch (error) {
      console.debug("Verifier list unavailable", error);
    }
    const currentStatus = status?.verifier ?? {};
    const existingInProgress = new Map(verifierState.jobs.map((job) => [job.job_id, job.in_progress]));
    verifierState.counts = Object.fromEntries(Object.entries(currentStatus.counts || {}));
    const proof = currentStatus.proof_counts || {};
    verifierState.proofCounts = {
      pass: Number(proof.pass ?? 0),
      fail: Number(proof.fail ?? 0),
      error: Number(proof.error ?? 0),
    };
    verifierState.jobs = (verifierList.reports || []).map((job) => ({
      job_id: job.job_id,
      script_hash: job.script_hash,
      verdict: job.verdict,
      from_node: job.from_node,
      created_at: normalizeTimestamp(job.created_at ?? 0),
      score: job.score,
      verifier_node: job.verifier_node,
      in_progress: existingInProgress.get(job.job_id) || false,
    }));
    renderVerifier();
    const memory = await fetchJson("/admin/memory/summary", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderMemory(memory);
    const health = await fetchJson("/admin/health", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderHealth(health.watchdog ?? health);
  } catch (error) {
    console.warn("Failed to refresh console", error);
  }
}

refreshAll();

function connectEventStream() {
  if (typeof EventSource === "undefined") {
    return false;
  }

  let retryDelay = 2000;
  const url = new URL("/sse", window.location.origin);
  if (window.NODE_TOKEN) {
    url.searchParams.set("token", window.NODE_TOKEN);
  }

  const establish = () => {
    const source = new EventSource(url.toString());
    const triggerRefresh = () => {
      refreshAll();
    };
    source.addEventListener("refresh", triggerRefresh);
    source.addEventListener("message", triggerRefresh);
    source.addEventListener("verifier_update", handleVerifierUpdate);
    source.onopen = () => {
      retryDelay = 2000;
    };
    source.onerror = () => {
      source.close();
      setTimeout(establish, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 30000);
    };
  };

  establish();
  return true;
}

if (!connectEventStream()) {
  setInterval(refreshAll, 10000);
}
