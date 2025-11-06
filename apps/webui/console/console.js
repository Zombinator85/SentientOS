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
  return JSON.parse(text);
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
      <td>${node.trust_level}</td>
      <td>${capabilities}</td>
      <td>${voice}</td>
    `;
    nodesTable.appendChild(tr);
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
    source.onmessage = triggerRefresh;
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
