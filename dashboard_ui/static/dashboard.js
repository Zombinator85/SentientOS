const CATEGORY_ENDPOINTS = {
  feed: "/feed",
  oracle: "/oracle",
  gapseeker: "/gapseeker",
  commits: "/commits",
  research: "/research",
};

const DRIFT_ENDPOINTS = {
  recent: "/api/drift/recent",
  detail: "/api/drift",
  silhouette: "/api/drift/silhouette",
};

const PRESSURE_ENDPOINTS = {
  due: "/api/pressure/due",
  revalidate: "/api/pressure",
  close: "/api/pressure",
  recent: "/api/pressure/recent",
  stream: "/api/pressure/stream",
};

const STATE = {
  events: {
    feed: [],
    oracle: [],
    gapseeker: [],
    commits: [],
    research: [],
  },
  driftReports: [],
  driftSelection: null,
  filter24h: false,
  moduleFilter: "",
  pressure: {
    due: [],
    recent: [],
    closeTarget: null,
    streamLastId: localStorage.getItem("pressureLastEventId") || "",
    seenIds: new Set(),
  },
  driftStreamLastDate: localStorage.getItem("driftLastEventId") || "",
  driftSeenIds: new Set(),
};

const controls = {
  last24h: document.getElementById("toggle-24h"),
  moduleFilter: document.getElementById("module-filter"),
  download: document.getElementById("download-archive"),
  status: document.getElementById("status-indicator"),
};

const lists = {
  feed: document.getElementById("feed-list"),
  oracle: document.getElementById("oracle-list"),
  gapseeker: document.getElementById("gapseeker-list"),
  commits: document.getElementById("commits-list"),
  research: document.getElementById("research-list"),
};

const driftElements = {
  list: document.getElementById("drift-list"),
  detailDate: document.getElementById("drift-detail-date"),
  detailJson: document.getElementById("drift-detail-json"),
  detailLink: document.getElementById("drift-detail-link"),
};

const pressureElements = {
  dueBody: document.getElementById("pressure-due-body"),
  recentList: document.getElementById("pressure-recent-list"),
  actor: document.getElementById("pressure-actor"),
  refresh: document.getElementById("pressure-refresh"),
  status: document.getElementById("pressure-status"),
  modal: document.getElementById("pressure-close-modal"),
  modalDismiss: document.getElementById("pressure-close-dismiss"),
  modalCancel: document.getElementById("pressure-close-cancel"),
  modalForm: document.getElementById("pressure-close-form"),
  modalReason: document.getElementById("pressure-close-reason"),
  modalNote: document.getElementById("pressure-close-note"),
};

const DRIFT_ICONS = [
  { key: "posture_stuck", icon: "⚠", label: "posture" },
  { key: "plugin_dominance", icon: "🔁", label: "plugin" },
  { key: "motion_starvation", icon: "💤", label: "motion" },
  { key: "anomaly_trend", icon: "🔺", label: "anomaly" },
];

function cloneTemplate() {
  const template = document.getElementById("event-template");
  return template.content.firstElementChild.cloneNode(true);
}

function applyFilters(events) {
  let filtered = [...events];
  if (STATE.filter24h) {
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    filtered = filtered.filter((event) => new Date(event.timestamp).getTime() >= cutoff);
  }
  if (STATE.moduleFilter) {
    filtered = filtered.filter((event) => event.module === STATE.moduleFilter);
  }
  return filtered;
}

function renderCategory(category) {
  const list = lists[category];
  const fragment = document.createDocumentFragment();
  const events = applyFilters(STATE.events[category]);

  events.forEach((event) => {
    const element = cloneTemplate();
    element.querySelector(".event-module").textContent = event.module;
    element.querySelector(".event-message").textContent = event.message;
    element.querySelector(".event-timestamp").textContent = new Date(event.timestamp).toLocaleString();
    fragment.appendChild(element);
  });

  list.innerHTML = "";
  list.appendChild(fragment);
}

function renderAll() {
  Object.keys(CATEGORY_ENDPOINTS).forEach(renderCategory);
  populateModuleFilter();
}

function renderDriftList() {
  driftElements.list.innerHTML = "";
  const reports = STATE.driftReports;
  if (!reports.length) {
    const empty = document.createElement("li");
    empty.className = "drift-empty";
    empty.textContent = "No drift detections yet.";
    driftElements.list.appendChild(empty);
    return;
  }

  reports.forEach((report) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "drift-item";
    button.dataset.date = report.date;
    if (STATE.driftSelection === report.date) {
      button.dataset.active = "true";
    }

    const title = document.createElement("span");
    title.className = "drift-date";
    title.textContent = report.date;
    button.appendChild(title);

    const tags = document.createElement("span");
    tags.className = "drift-tags";
    DRIFT_ICONS.forEach(({ key, icon, label }) => {
      if (!report[key]) return;
      const tag = document.createElement("span");
      tag.className = "drift-tag";
      tag.title = label;
      tag.textContent = icon;
      tags.appendChild(tag);
    });
    if (!tags.childElementCount) {
      const clear = document.createElement("span");
      clear.className = "drift-tag drift-tag--clear";
      clear.textContent = "✓";
      clear.title = "clear";
      tags.appendChild(clear);
    }
    button.appendChild(tags);

    button.addEventListener("click", () => selectDriftDate(report.date));
    item.appendChild(button);
    driftElements.list.appendChild(item);
  });
}

function renderDriftDetail(report) {
  driftElements.detailDate.textContent = report.date
    ? `Drift report for ${report.date}`
    : "Select a drift date to inspect.";
  driftElements.detailJson.textContent = JSON.stringify(report, null, 2);
}

function formatCounts(counts) {
  if (!counts || typeof counts !== "object") return "—";
  const entries = Object.entries(counts);
  if (!entries.length) return "—";
  return entries.map(([key, value]) => `${key}:${value}`).join(", ");
}

function renderPressureDue() {
  pressureElements.dueBody.innerHTML = "";
  if (!STATE.pressure.due.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "No due signals";
    row.appendChild(cell);
    pressureElements.dueBody.appendChild(row);
    return;
  }

  STATE.pressure.due.forEach((signal) => {
    const row = document.createElement("tr");
    const typeCell = document.createElement("td");
    typeCell.textContent = signal.signal_type || "—";
    const severityCell = document.createElement("td");
    severityCell.textContent = signal.severity || "—";
    const statusCell = document.createElement("td");
    statusCell.textContent = signal.status || "—";
    const dueCell = document.createElement("td");
    dueCell.textContent = signal.next_review_due_at
      ? new Date(signal.next_review_due_at).toLocaleString()
      : "—";
    const countsCell = document.createElement("td");
    countsCell.textContent = formatCounts(signal.counts);
    const actionCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "pressure-actions";

    const revalidateButton = document.createElement("button");
    revalidateButton.type = "button";
    revalidateButton.textContent = "Revalidate";
    revalidateButton.addEventListener("click", () => revalidatePressure(signal.id));

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.textContent = "Close";
    closeButton.addEventListener("click", () => openCloseModal(signal.id));

    actions.appendChild(revalidateButton);
    actions.appendChild(closeButton);
    actionCell.appendChild(actions);

    row.appendChild(typeCell);
    row.appendChild(severityCell);
    row.appendChild(statusCell);
    row.appendChild(dueCell);
    row.appendChild(countsCell);
    row.appendChild(actionCell);
    pressureElements.dueBody.appendChild(row);
  });
}

function renderPressureRecent() {
  pressureElements.recentList.innerHTML = "";
  if (!STATE.pressure.recent.length) {
    const item = document.createElement("li");
    item.className = "pressure-event";
    item.textContent = "No recent events";
    pressureElements.recentList.appendChild(item);
    return;
  }

  STATE.pressure.recent.forEach((event) => {
    const item = document.createElement("li");
    item.className = "pressure-event";
    const timestamp = event.timestamp ? new Date(event.timestamp).toLocaleString() : "—";
    const digest = event.digest || "—";
    const name = event.event || "pressure_event";
    item.textContent = `${timestamp} ${name} ${digest}`;
    pressureElements.recentList.appendChild(item);
  });
}

async function refreshPressureDueOnly() {
  const asOf = new Date().toISOString();
  try {
    const response = await fetch(`${PRESSURE_ENDPOINTS.due}?as_of=${encodeURIComponent(asOf)}&limit=50`);
    if (!response.ok) throw new Error("Failed to refresh due signals");
    const dueData = await response.json();
    STATE.pressure.due = Array.isArray(dueData.signals) ? dueData.signals : [];
    renderPressureDue();
  } catch (error) {
    pressureElements.status.textContent = error.message;
  }
}

let pressureDueRefreshPending = false;

function schedulePressureDueRefresh() {
  if (pressureDueRefreshPending) return;
  pressureDueRefreshPending = true;
  setTimeout(async () => {
    pressureDueRefreshPending = false;
    await refreshPressureDueOnly();
  }, 500);
}

function applyPressureStreamEvent(payload) {
  if (!payload || typeof payload !== "object") return;
  if (STATE.pressure.seenIds.has(payload.event_id)) return;
  if (payload.event_id) {
    STATE.pressure.seenIds.add(payload.event_id);
  }
  const entry = {
    timestamp: payload.timestamp || new Date().toISOString(),
    digest: payload.digest || payload.payload?.digest || "—",
    event: payload.event_type || "pressure_event",
  };
  STATE.pressure.recent.unshift(entry);
  if (STATE.pressure.recent.length > 50) {
    STATE.pressure.recent = STATE.pressure.recent.slice(0, 50);
  }
  renderPressureRecent();
  schedulePressureDueRefresh();
}

async function selectDriftDate(date) {
  STATE.driftSelection = date;
  renderDriftList();
  try {
    const response = await fetch(`${DRIFT_ENDPOINTS.detail}/${date}`);
    if (!response.ok) throw new Error("Failed to load drift report");
    const report = await response.json();
    renderDriftDetail(report);
  } catch (error) {
    driftElements.detailDate.textContent = "Drift report unavailable.";
    driftElements.detailJson.textContent = JSON.stringify({ error: error.message }, null, 2);
  }
  await updateSilhouetteLink(date);
}

async function updateSilhouetteLink(date) {
  driftElements.detailLink.classList.add("hidden");
  try {
    const response = await fetch(`${DRIFT_ENDPOINTS.silhouette}/${date}`);
    if (!response.ok) return;
    driftElements.detailLink.href = `${DRIFT_ENDPOINTS.silhouette}/${date}`;
    driftElements.detailLink.classList.remove("hidden");
  } catch (error) {
    driftElements.detailLink.classList.add("hidden");
  }
}

function populateModuleFilter() {
  const uniqueModules = new Set();
  Object.values(STATE.events).forEach((events) => {
    events.forEach((event) => uniqueModules.add(event.module));
  });

  const currentValue = controls.moduleFilter.value;
  controls.moduleFilter.innerHTML = '<option value="">All</option>';
  [...uniqueModules].sort().forEach((module) => {
    const option = document.createElement("option");
    option.value = module;
    option.textContent = module;
    controls.moduleFilter.appendChild(option);
  });

  if ([...controls.moduleFilter.options].some((option) => option.value === currentValue)) {
    controls.moduleFilter.value = currentValue;
  }
}

async function loadInitialData() {
  await Promise.all(
    Object.entries(CATEGORY_ENDPOINTS).map(async ([category, endpoint]) => {
      const response = await fetch(endpoint);
      if (!response.ok) return;
      const data = await response.json();
      STATE.events[category] = data.events || [];
    })
  );
  renderAll();
}

async function loadDriftData() {
  try {
    const response = await fetch(`${DRIFT_ENDPOINTS.recent}?n=7`);
    if (!response.ok) throw new Error("Failed to load drift reports");
    const reports = await response.json();
    STATE.driftReports = Array.isArray(reports) ? reports : [];
  } catch (error) {
    STATE.driftReports = [];
  }
  renderDriftList();
  if (STATE.driftReports.length) {
    selectDriftDate(STATE.driftReports[0].date);
  } else {
    renderDriftDetail({
      date: "",
      posture_stuck: false,
      plugin_dominance: false,
      motion_starvation: false,
      anomaly_trend: false,
      tags: [],
      source: "drift_detector",
    });
  }
}

async function loadPressureData() {
  pressureElements.status.textContent = "Loading…";
  const asOf = new Date().toISOString();
  try {
    const [dueResponse, recentResponse] = await Promise.all([
      fetch(`${PRESSURE_ENDPOINTS.due}?as_of=${encodeURIComponent(asOf)}&limit=50`),
      fetch(`${PRESSURE_ENDPOINTS.recent}?limit=20`),
    ]);
    if (!dueResponse.ok) throw new Error("Failed to load due signals");
    if (!recentResponse.ok) throw new Error("Failed to load recent events");
    const dueData = await dueResponse.json();
    const recentData = await recentResponse.json();
    STATE.pressure.due = Array.isArray(dueData.signals) ? dueData.signals : [];
    STATE.pressure.recent = Array.isArray(recentData.events) ? recentData.events : [];
    pressureElements.status.textContent = "Loaded";
  } catch (error) {
    pressureElements.status.textContent = error.message;
    STATE.pressure.due = [];
    STATE.pressure.recent = [];
  }
  renderPressureDue();
  renderPressureRecent();
}

function upsertDriftReport(report) {
  if (!report || !report.date) return;
  const existingIndex = STATE.driftReports.findIndex((item) => item.date === report.date);
  if (existingIndex >= 0) {
    STATE.driftReports[existingIndex] = { ...STATE.driftReports[existingIndex], ...report };
  } else {
    STATE.driftReports.unshift(report);
  }
  STATE.driftReports.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  if (STATE.driftReports.length > 30) {
    STATE.driftReports = STATE.driftReports.slice(0, 30);
  }
  renderDriftList();
  if (!STATE.driftSelection) {
    selectDriftDate(report.date);
  }
}

async function revalidatePressure(digest) {
  const actor = pressureElements.actor.value.trim();
  if (!actor) {
    pressureElements.status.textContent = "Actor required";
    return;
  }
  pressureElements.status.textContent = "Revalidating…";
  try {
    const response = await fetch(`${PRESSURE_ENDPOINTS.revalidate}/${digest}/revalidate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor, as_of: new Date().toISOString() }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Revalidate failed");
    }
    await loadPressureData();
  } catch (error) {
    pressureElements.status.textContent = error.message;
  }
}

function openCloseModal(digest) {
  STATE.pressure.closeTarget = digest;
  pressureElements.modalReason.value = "resolved";
  pressureElements.modalNote.value = "";
  pressureElements.modal.classList.remove("hidden");
}

function closeCloseModal() {
  STATE.pressure.closeTarget = null;
  pressureElements.modal.classList.add("hidden");
}

async function submitCloseModal(event) {
  event.preventDefault();
  const digest = STATE.pressure.closeTarget;
  if (!digest) return;
  const actor = pressureElements.actor.value.trim();
  if (!actor) {
    pressureElements.status.textContent = "Actor required";
    return;
  }
  pressureElements.status.textContent = "Closing…";
  try {
    const response = await fetch(`${PRESSURE_ENDPOINTS.close}/${digest}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        actor,
        reason: pressureElements.modalReason.value,
        note: pressureElements.modalNote.value.trim(),
        as_of: new Date().toISOString(),
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Close failed");
    }
    closeCloseModal();
    await loadPressureData();
  } catch (error) {
    pressureElements.status.textContent = error.message;
  }
}

function addEventToState(event) {
  if (!STATE.events[event.category]) {
    STATE.events[event.category] = [];
  }
  STATE.events[event.category].unshift(event);
  renderCategory(event.category);
  populateModuleFilter();
}

function setupControls() {
  controls.last24h.addEventListener("click", () => {
    STATE.filter24h = !STATE.filter24h;
    controls.last24h.dataset.active = String(STATE.filter24h);
    controls.last24h.textContent = STATE.filter24h ? "Showing Last 24h" : "Show Last 24h";
    renderAll();
  });

  controls.moduleFilter.addEventListener("change", (event) => {
    STATE.moduleFilter = event.target.value;
    renderAll();
  });

  controls.download.addEventListener("click", async () => {
    controls.status.textContent = "Preparing archive…";
    try {
      const response = await fetch("/research/archive");
      if (!response.ok) throw new Error("Failed to fetch archive");
      const data = await response.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `research-archive-${new Date().toISOString()}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      controls.status.textContent = "Archive downloaded";
    } catch (error) {
      controls.status.textContent = `Archive error: ${error.message}`;
    }
  });

  pressureElements.refresh.addEventListener("click", () => loadPressureData());
  pressureElements.modalDismiss.addEventListener("click", closeCloseModal);
  pressureElements.modalCancel.addEventListener("click", closeCloseModal);
  pressureElements.modalForm.addEventListener("submit", submitCloseModal);
}

function connectEventStream() {
  const source = new EventSource("/events");
  source.onopen = () => {
    controls.status.textContent = "Live updates connected";
  };
  source.onerror = () => {
    controls.status.textContent = "Live updates disconnected (retrying…)";
  };
  source.onmessage = (event) => {
    if (!event.data) return;
    try {
      const payload = JSON.parse(event.data);
      addEventToState(payload);
    } catch (error) {
      console.error("Failed to parse event", error);
    }
  };
}

function connectPressureStream() {
  const url = new URL(PRESSURE_ENDPOINTS.stream, window.location.origin);
  if (STATE.pressure.streamLastId) {
    url.searchParams.set("since_id", STATE.pressure.streamLastId);
  }
  url.searchParams.set("limit", "50");
  const source = new EventSource(url);
  source.onerror = () => {
    pressureElements.status.textContent = "Pressure stream disconnected (retrying…)";
  };
  source.onmessage = (event) => {
    if (!event.data) return;
    try {
      const payload = JSON.parse(event.data);
      const lastId = event.lastEventId || payload.event_id;
      if (lastId) {
        STATE.pressure.streamLastId = String(lastId);
        localStorage.setItem("pressureLastEventId", STATE.pressure.streamLastId);
      }
      applyPressureStreamEvent(payload);
    } catch (error) {
      console.error("Failed to parse pressure event", error);
    }
  };
}

function connectDriftStream() {
  const url = new URL("/api/drift/stream", window.location.origin);
  if (STATE.driftStreamLastDate) {
    url.searchParams.set("since_date", STATE.driftStreamLastDate);
  }
  url.searchParams.set("limit", "7");
  const source = new EventSource(url);
  source.onerror = () => {
    driftElements.detailDate.textContent = "Drift stream disconnected (retrying…)";
  };
  source.onmessage = (event) => {
    if (!event.data) return;
    try {
      const payload = JSON.parse(event.data);
      const lastId = event.lastEventId || payload.event_id || payload.date;
      if (lastId) {
        STATE.driftStreamLastDate = String(lastId);
        localStorage.setItem("driftLastEventId", STATE.driftStreamLastDate);
      }
      if (payload.event_id && STATE.driftSeenIds.has(payload.event_id)) {
        return;
      }
      if (payload.event_id) {
        STATE.driftSeenIds.add(payload.event_id);
      }
      const report = payload.payload || payload;
      upsertDriftReport({
        ...report,
        date: report.date || payload.event_id || payload.date,
      });
    } catch (error) {
      console.error("Failed to parse drift event", error);
    }
  };
}

setupControls();
loadInitialData();
loadDriftData();
loadPressureData();
connectEventStream();
connectPressureStream();
connectDriftStream();
