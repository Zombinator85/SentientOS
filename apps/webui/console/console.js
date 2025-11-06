const overviewGrid = document.getElementById("overview-grid");
const nodesTable = document.querySelector("#nodes-table tbody");
const memoryInfo = document.getElementById("memory-info");
const healthChecks = document.getElementById("health-checks");
const installButton = document.getElementById("install-button");
const dreamMoodLabel = document.getElementById("dream-mood-label");
const dreamMoodIntensity = document.getElementById("dream-mood-intensity");
const dreamActiveGoal = document.getElementById("dream-active-goal");
const dreamGoalMeta = document.getElementById("dream-goal-meta");
const dreamLoopProgress = document.getElementById("dream-loop-progress");
const dreamLoopBar = document.getElementById("dream-loop-bar");
const dreamLoopStatus = document.getElementById("dream-loop-status");
const emotionPulseCard = document.getElementById("emotion-pulse-card");
const emotionPulseDot = document.getElementById("emotion-pulse-dot");
const emotionPulseLabel = document.getElementById("emotion-pulse-label");
const emotionPulseNote = document.getElementById("emotion-pulse-note");

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

function formatTimestamp(iso) {
  if (!iso) return "No cycle recorded";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

function clampPercent(value) {
  const numeric = Number.isFinite(value) ? value : Number(value) || 0;
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, numeric));
}

function renderDream(snapshot) {
  if (!snapshot || snapshot.error) {
    if (dreamLoopStatus) {
      dreamLoopStatus.textContent = "Dream telemetry unavailable";
    }
    return;
  }
  const mood = snapshot.mood ?? {};
  const goalProgress = snapshot.goal_progress ?? {};
  const state = snapshot.dream_state ?? {};
  const pulse = snapshot.emotion_pulse ?? {};

  const moodLabel = mood.label ?? snapshot.dominant_emotion ?? "Neutral";
  const intensity = Number.isFinite(mood.intensity) ? Number(mood.intensity) : Number(mood.intensity || 0);
  if (dreamMoodLabel) {
    dreamMoodLabel.textContent = moodLabel;
  }
  if (dreamMoodIntensity) {
    const pct = clampPercent(intensity * 100);
    dreamMoodIntensity.textContent = `Intensity ${pct.toFixed(0)}%`;
  }

  const goal = snapshot.active_goal;
  if (dreamActiveGoal) {
    dreamActiveGoal.textContent = goal?.text || "No active goals";
  }
  if (dreamGoalMeta) {
    const total = goalProgress.total ?? 0;
    const completed = goalProgress.completed ?? 0;
    const open = goalProgress.open ?? Math.max(total - completed, 0);
    const percent = clampPercent(goalProgress.percent ?? 0);
    dreamGoalMeta.textContent = `${completed}/${total} completed • ${open} open • ${percent.toFixed(0)}% progress`;
  }

  if (dreamLoopProgress) {
    const loopPercent = clampPercent(snapshot.loop_progress_percent ?? 0);
    dreamLoopProgress.textContent = `${loopPercent.toFixed(0)}%`;
    if (dreamLoopBar) {
      dreamLoopBar.style.width = `${loopPercent}%`;
    }
  }
  if (dreamLoopStatus) {
    if (state.active) {
      dreamLoopStatus.textContent = "Dream loop active";
    } else if (snapshot.last_cycle_at) {
      dreamLoopStatus.textContent = `Last cycle ${formatTimestamp(snapshot.last_cycle_at)}`;
    } else {
      dreamLoopStatus.textContent = "Awaiting first dream cycle";
    }
  }

  const pulseColor = pulse.color || "#38bdf8";
  if (emotionPulseLabel) {
    emotionPulseLabel.textContent = pulse.label || moodLabel;
  }
  if (emotionPulseNote) {
    const pct = clampPercent((pulse.intensity ?? intensity) * 100);
    emotionPulseNote.textContent = pct ? `Pulse at ${pct.toFixed(0)}%` : "Pulse idle";
  }
  if (emotionPulseDot) {
    emotionPulseDot.style.borderColor = pulseColor;
    emotionPulseDot.style.boxShadow = `0 0 25px ${pulseColor}66`;
    emotionPulseDot.style.background = `radial-gradient(circle at 30% 30%, rgba(255,255,255,0.85), ${pulseColor}33)`;
  }
  if (emotionPulseCard) {
    emotionPulseCard.style.borderColor = `${pulseColor}88`;
    emotionPulseCard.style.boxShadow = `0 15px 35px ${pulseColor}22`;
  }
}

async function refreshAll() {
  try {
    const status = await fetchJson("/admin/status", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderMetrics(status);
    const nodes = await fetchJson("/admin/nodes", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderNodes(nodes);
    const memory = await fetchJson("/admin/memory/summary", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderMemory(memory);
    const health = await fetchJson("/admin/health", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderHealth(health.watchdog ?? health);
    const dream = await fetchJson("/admin/dream", { headers: { "X-Node-Token": window.NODE_TOKEN ?? "" } });
    renderDream(dream);
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
