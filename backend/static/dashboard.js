(() => {
  const state = { token: localStorage.getItem("psyconOperatorToken") || "psycon-local-operator", selected: null, timer: null };
  const byId = (id) => document.getElementById(id);
  const tokenInput = byId("operator-token");
  tokenInput.value = state.token;

  async function api(path, options = {}) {
    const response = await fetch(`/api/v1${path}`, {
      ...options,
      headers: { "Authorization": `Bearer ${state.token}`, "Content-Type": "application/json", ...(options.headers || {}) }
    });
    const body = await response.json().catch(() => ({ status: "error", error: { message: "Invalid server response" } }));
    if (!response.ok) throw new Error(body.error?.message || `Request failed: ${response.status}`);
    return body;
  }

  function notice(message, isError = false) {
    const node = byId("notice"); node.hidden = false; node.textContent = message; node.classList.toggle("error", isError);
    window.setTimeout(() => { node.hidden = true; }, 5000);
  }

  async function checkHealth() {
    try {
      const response = await fetch("/api/v1/ready"); const body = await response.json();
      const ok = response.ok && body.status === "ready";
      byId("health-dot").classList.toggle("ok", ok); byId("health-label").textContent = ok ? "Ready" : "Unavailable";
    } catch { byId("health-label").textContent = "Offline"; }
  }

  async function loadSessions() {
    const list = byId("session-list");
    try {
      const body = await api("/sessions"); list.replaceChildren();
      if (!body.sessions.length) { const empty = document.createElement("p"); empty.className = "empty-inline"; empty.textContent = "No sessions yet. Start the simulator or create one below."; list.append(empty); return; }
      body.sessions.forEach((session, index) => {
        const button = document.createElement("button"); button.type = "button"; button.className = "session-item";
        button.style.animationDelay = `${index * 45}ms`;
        const title = document.createElement("strong"); title.textContent = session.anonymous_code;
        const detail = document.createElement("span"); detail.textContent = `${session.state} / ${session.chunk_count} chunks`;
        button.append(title, detail); button.addEventListener("click", () => selectSession(session.id));
        if (session.id === state.selected) button.classList.add("active"); list.append(button);
      });
    } catch (error) { list.replaceChildren(); const p = document.createElement("p"); p.className = "empty-inline"; p.textContent = error.message; list.append(p); notice(error.message, true); }
  }

  async function selectSession(id) {
    state.selected = id; byId("empty-state").hidden = true; byId("session-content").hidden = false;
    await Promise.all([loadSessions(), loadSnapshot()]);
    clearInterval(state.timer); state.timer = setInterval(loadSnapshot, 5000);
  }

  function empty(container, text) { const p = document.createElement("p"); p.className = "empty-inline"; p.textContent = text; container.replaceChildren(p); }

  async function loadSnapshot() {
    if (!state.selected) return;
    try {
      const body = await api(`/sessions/${state.selected}`); const session = body.session;
      byId("session-code").textContent = session.anonymous_code; byId("session-title").textContent = `Session ${session.state}`;
      byId("session-id").textContent = session.id; byId("metric-state").textContent = session.state;
      byId("metric-chunks").textContent = body.streams.reduce((sum, stream) => sum + Number(stream.count), 0);
      byId("metric-devices").textContent = new Set(body.streams.map((stream) => stream.device_id)).size;
      byId("metric-features").textContent = body.features.length;
      renderStreams(body.streams); renderStatus(body.status); renderJobs(body.jobs); renderFeatures(body.features); renderInferences(body.inferences);
    } catch (error) { notice(error.message, true); }
  }

  function renderStreams(streams) {
    const container = byId("stream-list"); if (!streams.length) return empty(container, "Waiting for authenticated Protocol v2 packets.");
    const table = document.createElement("table"); table.className = "window-table";
    const head = document.createElement("thead"); head.innerHTML = "<tr><th>Device</th><th>Stream</th><th>Packets</th><th>Sequence</th><th>Max sync uncertainty</th></tr>"; table.append(head);
    const body = document.createElement("tbody"); streams.forEach((stream) => {
      const row = document.createElement("tr"); [stream.device_id, stream.stream_type, stream.count, `${stream.first_sequence}–${stream.last_sequence}`, stream.max_sync_uncertainty_us == null ? "unavailable" : `${stream.max_sync_uncertainty_us} µs`].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }); body.append(row);
    }); table.append(body); container.replaceChildren(table);
  }

  function renderStatus(events) {
    const container = byId("status-list"); if (!events.length) return empty(container, "No device status received."); container.replaceChildren();
    events.forEach((event) => { const row = document.createElement("div"); row.className = "stack-row"; const title = document.createElement("strong"); title.textContent = `${event.device_id} / ${event.event_type}`; const detail = document.createElement("span"); detail.textContent = JSON.stringify(event.payload); row.append(title, detail); container.append(row); });
  }

  function renderJobs(jobs) {
    const container = byId("job-list"); if (!jobs.length) return empty(container, "No processing requested."); container.replaceChildren();
    jobs.forEach((job) => { const row = document.createElement("div"); row.className = "stack-row"; const title = document.createElement("strong"); title.textContent = `${job.job_type}: ${job.state}`; const detail = document.createElement("span"); detail.textContent = job.error || `${job.attempts} attempt${job.attempts === 1 ? "" : "s"}`; row.append(title, detail); container.append(row); });
  }

  function renderFeatures(features) {
    const container = byId("feature-list"); if (!features.length) return empty(container, "Process the session to create quality-gated feature records."); container.replaceChildren();
    const groups = new Map();
    features.forEach((feature) => { const group = groups.get(feature.modality) || []; group.push(feature); groups.set(feature.modality, group); });
    groups.forEach((items, modalityName) => {
      const row = document.createElement("div"); row.className = "feature-row";
      const heading = document.createElement("div"); heading.className = "feature-summary";
      const modality = document.createElement("strong"); modality.textContent = modalityName;
      const states = [...new Set(items.map((item) => item.quality_state))].join(", ");
      const quality = document.createElement("span"); quality.textContent = `${items.length} window${items.length === 1 ? "" : "s"} / ${states}`;
      heading.append(modality, quality);
      const values = document.createElement("code"); values.textContent = JSON.stringify(items.at(-1).features, null, 2);
      row.append(heading, values); container.append(row);
    });
  }

  function renderInferences(inferences) {
    const container = byId("inference-list"); if (!inferences.length) return empty(container, "No inference decision exists. Processing will abstain until inputs match a validated model contract."); container.replaceChildren();
    const inference = inferences.at(-1); const row = document.createElement("article"); row.className = "inference-decision";
    const summary = document.createElement("div"); summary.className = "decision-summary";
    const stateNode = document.createElement("strong"); stateNode.className = `decision-state decision-state--${inference.state}`; stateNode.textContent = inference.state;
    const model = document.createElement("span"); model.className = "decision-model"; model.textContent = `${inference.model_name} / ${inference.model_version}`;
    summary.append(stateNode, model);

    const reasonList = Array.isArray(inference.reasons) ? inference.reasons : [];
    const missing = reasonList.find((reason) => reason.startsWith("missing_model_features:"));
    const description = document.createElement("p"); description.className = "decision-copy";
    if (missing) {
      const missingFeatures = missing.slice("missing_model_features:".length).split(",").filter(Boolean);
      description.textContent = `No score was produced because ${missingFeatures.length} calibrated model inputs are unavailable in this simulated raw-packet session.`;
      const details = document.createElement("details"); details.className = "decision-details";
      const detailsLabel = document.createElement("summary"); detailsLabel.textContent = `Review missing feature contract (${missingFeatures.length})`;
      const values = document.createElement("code"); values.textContent = missingFeatures.join(" / ");
      details.append(detailsLabel, values); row.append(summary, description, details);
    } else {
      description.textContent = reasonList.length ? reasonList.join(". ") : "The validated model contract was satisfied for this decision.";
      row.append(summary, description);
    }
    if (inference.score != null) {
      const score = document.createElement("p"); score.className = "decision-score"; score.textContent = `Score ${Number(inference.score).toFixed(3)} / confidence ${inference.confidence == null ? "unavailable" : Number(inference.confidence).toFixed(3)}`; row.append(score);
    }
    const history = document.createElement("p"); history.className = "decision-history"; history.textContent = `Latest session decision / ${inferences.length} processed window${inferences.length === 1 ? "" : "s"}`;
    row.append(history); container.append(row);
  }

  async function action(suffix, message) { if (!state.selected) return; try { await api(`/sessions/${state.selected}/${suffix}`, { method: "POST", body: "{}" }); notice(message); await loadSnapshot(); } catch (error) { notice(error.message, true); } }

  byId("connect-button").addEventListener("click", async () => { state.token = tokenInput.value.trim(); localStorage.setItem("psyconOperatorToken", state.token); await loadSessions(); });
  byId("refresh-button").addEventListener("click", loadSessions);
  byId("process-button").addEventListener("click", () => action("process", "Processing queued."));
  byId("close-button").addEventListener("click", () => action("close", "Session closed."));
  byId("export-button").addEventListener("click", () => action("exports", "Research export created."));
  byId("delete-button").addEventListener("click", async () => {
    if (!state.selected || !window.confirm("Delete this session, its raw packets, derived records, and exports? This cannot be undone.")) return;
    try { await api(`/sessions/${state.selected}`, { method:"DELETE", headers:{} }); state.selected = null; clearInterval(state.timer); byId("session-content").hidden = true; byId("empty-state").hidden = false; notice("Session deleted."); await loadSessions(); } catch (error) { notice(error.message, true); }
  });
  byId("session-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement); const versions = { firmware:"simulator-1", hardware:"simulated", pcb:"simulated", protocol:"2", dataset:"week4-demo-1", model:"0.1.0", configuration:"local-demo-1", calibration:"simulated-1", documentation:"week4-1" };
    try { const body = await api("/sessions", { method:"POST", body:JSON.stringify({ anonymous_code:form.get("anonymous_code"), versions, metadata:{ source:"dashboard" } }) }); formElement.reset(); await loadSessions(); await selectSession(body.session.id); notice("Session created."); } catch (error) { notice(error.message, true); }
  });
  checkHealth(); loadSessions(); setInterval(checkHealth, 10000);
})();
