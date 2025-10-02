const CATEGORY_ENDPOINTS = {
  feed: "/feed",
  oracle: "/oracle",
  gapseeker: "/gapseeker",
  commits: "/commits",
  research: "/research",
};

const STATE = {
  events: {
    feed: [],
    oracle: [],
    gapseeker: [],
    commits: [],
    research: [],
  },
  filter24h: false,
  moduleFilter: "",
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

setupControls();
loadInitialData();
connectEventStream();
