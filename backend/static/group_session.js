(() => {
  const letters = "ABCDEFGHIJKLMNOPQRST".split("");
  const state = {
    token: localStorage.getItem("psyconGroupToken") || "",
    accountId: "",
    role: "",
    selected: null,
    view: null,
    seats: [],
    items: {},
    saveTimer: 0,
    primaryRaterId: "",
  };
  const byId = (id) => document.getElementById(id);
  byId("account-token").value = state.token;

  function notice(message, isError = false) {
    const node = byId("notice");
    node.hidden = false;
    node.textContent = message;
    node.classList.toggle("error", isError);
    window.setTimeout(() => { node.hidden = true; }, 5000);
  }

  async function api(path, options = {}) {
    const headers = { Authorization: `Bearer ${state.token}` };
    let body;
    if (options.raw) {
      body = options.body;
    } else if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }
    const response = await fetch(path, { method: options.method || "GET", headers, body });
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({ error: { message: "Invalid server response" } }));
    if (!response.ok) throw new Error(payload.error?.message || `Request failed: ${response.status}`);
    return payload;
  }

  async function checkHealth() {
    try {
      const response = await fetch("/api/v1/ready");
      const body = await response.json();
      const ok = response.ok && body.status === "ready";
      byId("health-dot").classList.toggle("ok", ok);
      byId("health-label").textContent = ok ? "Ready" : "Unavailable";
    } catch {
      byId("health-label").textContent = "Offline";
    }
  }

  async function connect() {
    state.token = byId("account-token").value.trim();
    localStorage.setItem("psyconGroupToken", state.token);
    const me = await api("/api/v1/group-accounts/me");
    state.accountId = me.account.id;
    state.role = me.account.role;
    byId("account-role").textContent = `${me.account.label} / ${me.account.role}`;
    await loadSessions();
  }

  async function loadSessions() {
    const list = byId("session-list");
    if (!state.token) {
      list.replaceChildren();
      const empty = document.createElement("p");
      empty.className = "empty-inline";
      empty.textContent = "Connect with a named account token to see group sessions.";
      list.append(empty);
      return;
    }
    try {
      const body = await api("/api/v1/group-sessions");
      list.replaceChildren();
      if (!body.group_sessions.length) {
        const empty = document.createElement("p");
        empty.className = "empty-inline";
        empty.textContent = "No group sessions yet. Create one below.";
        list.append(empty);
        return;
      }
      body.group_sessions.forEach((session) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "session-item";
        if (session.id === state.selected) button.classList.add("active");
        const title = document.createElement("strong");
        title.textContent = session.session_code;
        const detail = document.createElement("span");
        detail.textContent = `${session.consent_status} / ${session.participant_count} slots / ${session.recording_state || "no video"}`;
        button.append(title, detail);
        button.addEventListener("click", () => selectSession(session.id));
        list.append(button);
      });
    } catch (error) {
      list.replaceChildren();
      const paragraph = document.createElement("p");
      paragraph.className = "empty-inline";
      paragraph.textContent = error.message;
      list.append(paragraph);
      notice(error.message, true);
    }
  }

  async function selectSession(id) {
    state.selected = id;
    state.view = await api(`/api/v1/group-sessions/${id}`);
    state.seats = (state.view.seats || []).map((seat) => ({ x: seat.x, y: seat.y, width: seat.width, height: seat.height }));
    byId("empty-state").hidden = true;
    byId("session-content").hidden = false;
    renderSession();
    await loadSessions();
    await showFrame();
  }

  function renderSession() {
    const session = state.view.session;
    const recording = state.view.recording;
    byId("session-code").textContent = session.session_code;
    byId("session-title").textContent = session.topic;
    byId("session-summary").textContent = `${session.id} / ${session.recording_disposition}`;
    byId("metric-consent").textContent = session.consent_version;
    byId("metric-participants").textContent = String(state.view.participants.length);
    byId("metric-recording").textContent = recording ? recording.video_codec : "none";
    byId("metric-processing").textContent = recording ? recording.processing_state : "—";
    const select = byId("participant-select");
    select.replaceChildren();
    state.view.participants.forEach((person) => {
      const option = document.createElement("option");
      option.value = person.id;
      option.textContent = person.label;
      select.append(option);
    });
    renderSeats();
    renderMappings();
    renderTranscript();
    renderItems();
    loadMarksheet().catch(() => {});
  }

  function renderSeats() {
    const list = byId("seat-list");
    list.replaceChildren();
    const ordered = [...state.seats].sort((left, right) => (right.x + right.width / 2) - (left.x + left.width / 2));
    ordered.forEach((seat, index) => {
      const item = document.createElement("li");
      const indexNode = document.createElement("span");
      indexNode.textContent = String(index + 1).padStart(2, "0");
      const copy = document.createElement("p");
      copy.textContent = `Participant ${index + 1} at x ${seat.x.toFixed(2)}`;
      item.append(indexNode, copy);
      list.append(item);
    });
  }

  function renderMappings() {
    const form = byId("mapping-form");
    form.replaceChildren();
    const clusters = [...new Set((state.view.speaker_turns || []).map((turn) => turn.cluster_label))];
    if (!clusters.length) {
      const empty = document.createElement("p");
      empty.className = "empty-inline";
      empty.textContent = "Voice clusters appear after the recording is processed.";
      form.append(empty);
      return;
    }
    clusters.forEach((cluster) => {
      const turn = state.view.speaker_turns.find((item) => item.cluster_label === cluster);
      const row = document.createElement("div");
      row.className = "stack-row";
      const title = document.createElement("strong");
      title.textContent = `${cluster} / ${turn.start_s.toFixed(1)}–${turn.end_s.toFixed(1)}s`;
      const controls = document.createElement("span");
      const select = document.createElement("select");
      select.dataset.cluster = cluster;
      const unknown = document.createElement("option");
      unknown.value = "";
      unknown.textContent = "unknown";
      select.append(unknown);
      state.view.participants.forEach((person) => {
        const option = document.createElement("option");
        option.value = person.id;
        option.textContent = person.label;
        select.append(option);
      });
      const current = state.view.speaker_mappings?.[cluster];
      if (current?.participant_id && current.status === "confirmed") select.value = current.participant_id;
      const play = document.createElement("button");
      play.type = "button";
      play.className = "secondary-button compact-button";
      play.textContent = "Play";
      play.addEventListener("click", () => openAt(turn.start_s));
      controls.append(select, document.createTextNode(" "), play);
      row.append(title, controls);
      form.append(row);
    });
    const save = document.createElement("button");
    save.type = "button";
    save.className = "secondary-button";
    save.textContent = "Save voice mapping";
    save.addEventListener("click", saveMappings);
    form.append(save);
  }

  async function saveMappings() {
    const mappings = [...byId("mapping-form").querySelectorAll("select")].map((select) => ({
      cluster_label: select.dataset.cluster,
      participant_id: select.value || null,
      status: select.value ? "confirmed" : "unknown",
    }));
    await api(`/api/v1/group-sessions/${state.selected}/speaker-mappings`, { method: "PUT", body: { mappings } });
    notice("Voice mapping saved.");
    await selectSession(state.selected);
  }

  function renderTranscript() {
    const host = byId("transcript");
    host.replaceChildren();
    const rows = state.view.transcript || [];
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "empty-inline";
      empty.textContent = "No transcript yet.";
      host.append(empty);
      return;
    }
    rows.forEach((row) => {
      const line = document.createElement("div");
      line.className = "stack-row";
      const title = document.createElement("strong");
      title.textContent = `${row.cluster_label} / ${Number(row.start_s).toFixed(1)}–${Number(row.end_s).toFixed(1)}s`;
      const detail = document.createElement("span");
      detail.textContent = row.text;
      line.append(title, detail);
      host.append(line);
    });
  }

  function renderItems() {
    const host = byId("items");
    host.replaceChildren();
    letters.forEach((letter) => {
      const block = document.createElement("article");
      block.className = "mark-item";
      block.dataset.letter = letter;
      const title = document.createElement("h3");
      title.textContent = `Item ${letter}`;
      const scores = document.createElement("div");
      scores.className = "score-row";
      ["0", "1", "2", "3", "4", "N/O"].forEach((score) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "secondary-button compact-button score-button";
        button.textContent = score;
        button.addEventListener("click", () => chooseScore(letter, score, block));
        scores.append(button);
      });
      const fields = document.createElement("div");
      fields.className = "mark-fields";
      fields.innerHTML = `
        <label class="field-label">Preceding event<textarea data-field="preceding_event"></textarea></label>
        <label class="field-label">Observed response<textarea data-field="observed_response"></textarea></label>
        <label class="field-label">Evidence start<input data-field="start_s" type="number" step="0.1"></label>
        <label class="field-label">Evidence end<input data-field="end_s" type="number" step="0.1"></label>
        <label class="field-label">Baseline start<input data-field="baseline_start_s" type="number" step="0.1"></label>
        <label class="field-label">Baseline end<input data-field="baseline_end_s" type="number" step="0.1"></label>
        <label class="field-label">Trigger start<input data-field="trigger_start_s" type="number" step="0.1"></label>
        <label class="field-label">Trigger end<input data-field="trigger_end_s" type="number" step="0.1"></label>
        <label class="field-label">Trigger<textarea data-field="trigger_description"></textarea></label>
        <label class="field-label">N/O reason
          <select data-field="no_score_reason">
            <option value="no_opportunity">no opportunity</option>
            <option value="poor_recording">poor recording</option>
            <option value="uncertain_speaker_identity">uncertain speaker identity</option>
          </select>
        </label>`;
      fields.addEventListener("change", scheduleSave);
      block.append(title, scores, fields);
      host.append(block);
    });
  }

  function chooseScore(letter, score, block) {
    const current = readItem(letter, block);
    current.score = score;
    current.fair_opportunity = score === "0";
    state.items[letter] = current;
    block.querySelectorAll(".score-button").forEach((button) => {
      button.setAttribute("aria-pressed", button.textContent === score ? "true" : "false");
    });
    scheduleSave();
  }

  function readItem(letter, block) {
    const value = (field) => block.querySelector(`[data-field="${field}"]`).value;
    const start = Number(value("start_s"));
    const end = Number(value("end_s"));
    const item = {
      item_letter: letter,
      score: (state.items[letter] || {}).score || null,
      preceding_event: value("preceding_event"),
      observed_response: value("observed_response"),
      fair_opportunity: (state.items[letter] || {}).score === "0",
      no_score_reason: value("no_score_reason"),
      intervals: [],
    };
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
      item.intervals.push({ kind: "evidence", start_s: start, end_s: end, description: value("observed_response") });
    }
    if ("QRST".includes(letter)) {
      const baselineStart = Number(value("baseline_start_s"));
      const baselineEnd = Number(value("baseline_end_s"));
      const triggerStart = Number(value("trigger_start_s"));
      const triggerEnd = Number(value("trigger_end_s"));
      if (Number.isFinite(baselineStart) && Number.isFinite(baselineEnd) && baselineEnd > baselineStart) {
        item.intervals.push({ kind: "baseline", start_s: baselineStart, end_s: baselineEnd, description: "same-participant baseline" });
      }
      if (Number.isFinite(triggerStart) && Number.isFinite(triggerEnd) && triggerEnd > triggerStart) {
        item.intervals.push({ kind: "trigger", start_s: triggerStart, end_s: triggerEnd, description: value("trigger_description") });
      }
    }
    return item;
  }

  function scheduleSave() {
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(() => { saveDraft().catch((error) => notice(error.message, true)); }, 400);
  }

  async function saveDraft() {
    if (!state.accountId || state.role !== "psychologist") return;
    const participantId = byId("participant-select").value;
    const items = letters.map((letter) => state.items[letter]).filter((item) => item && item.score);
    await api(`/api/v1/group-sessions/${state.selected}/participants/${participantId}/marksheets/${state.accountId}`, {
      method: "PUT",
      body: { items },
    });
    byId("save-status").textContent = "Draft saved.";
  }

  function applyLoadedItems() {
    Object.entries(state.items).forEach(([letter, item]) => {
      const block = byId("items").querySelector(`[data-letter="${letter}"]`);
      if (!block) return;
      block.querySelectorAll(".score-button").forEach((button) => {
        button.setAttribute("aria-pressed", button.textContent === item.score ? "true" : "false");
      });
      const preceding = block.querySelector('[data-field="preceding_event"]');
      const observed = block.querySelector('[data-field="observed_response"]');
      if (preceding) preceding.value = item.preceding_event || "";
      if (observed) observed.value = item.observed_response || "";
      const evidence = (item.intervals || []).find((interval) => interval.kind === "evidence");
      const baseline = (item.intervals || []).find((interval) => interval.kind === "baseline");
      const trigger = (item.intervals || []).find((interval) => interval.kind === "trigger");
      if (evidence) {
        block.querySelector('[data-field="start_s"]').value = evidence.start_s;
        block.querySelector('[data-field="end_s"]').value = evidence.end_s;
      }
      if (baseline) {
        block.querySelector('[data-field="baseline_start_s"]').value = baseline.start_s;
        block.querySelector('[data-field="baseline_end_s"]').value = baseline.end_s;
      }
      if (trigger) {
        block.querySelector('[data-field="trigger_start_s"]').value = trigger.start_s;
        block.querySelector('[data-field="trigger_end_s"]').value = trigger.end_s;
        block.querySelector('[data-field="trigger_description"]').value = trigger.description || "";
      }
    });
  }

  async function loadMarksheet() {
    if (!state.accountId || state.role !== "psychologist") return;
    const participantId = byId("participant-select").value;
    try {
      const sheet = await api(`/api/v1/group-sessions/${state.selected}/participants/${participantId}/marksheets/${state.accountId}`);
      state.items = Object.fromEntries((sheet.items || []).filter((item) => item.score).map((item) => [item.item_letter, item]));
      byId("save-status").textContent = sheet.state === "submitted" ? "Submitted." : "Draft loaded.";
      applyLoadedItems();
    } catch (error) {
      if (!String(error.message).includes("No marksheet")) notice(error.message, true);
    }
  }

  async function showFrame() {
    if (!state.view?.marked_frame_ready) return;
    const response = await fetch(`/api/v1/group-sessions/${state.selected}/reference-frame`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!response.ok) return;
    byId("frame").src = URL.createObjectURL(await response.blob());
  }

  async function openAt(second) {
    const video = byId("playback");
    if (!video.src) {
      const grant = await api(`/api/v1/group-sessions/${state.selected}/recording/playback`, { method: "POST", body: {} });
      video.src = `${grant.media_path}?playback_token=${encodeURIComponent(grant.playback_token)}`;
      await new Promise((resolve) => video.addEventListener("loadedmetadata", resolve, { once: true }));
    }
    video.currentTime = Number(second);
    await video.play();
  }

  function claimButton(label, second) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button";
    button.textContent = label;
    button.addEventListener("click", () => openAt(second).catch((error) => notice(error.message, true)));
    return button;
  }

  byId("connect-button").addEventListener("click", () => connect().catch((error) => notice(error.message, true)));
  byId("refresh-button").addEventListener("click", () => loadSessions());
  byId("session-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    payload.participant_count = Number(payload.participant_count);
    payload.consent_version = "group-consent-2.0";
    try {
      const created = await api("/api/v1/group-sessions", { method: "POST", body: payload });
      notice("Group session created.");
      await selectSession(created.group_session.session.id);
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = new FormData();
    body.append("file", byId("video-file").files[0]);
    try {
      await api(`/api/v1/group-sessions/${state.selected}/recording`, { method: "POST", body, raw: true });
      notice("Video stored.");
      await selectSession(state.selected);
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("frame-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = new FormData();
    body.append("file", byId("frame-file").files[0]);
    try {
      await api(`/api/v1/group-sessions/${state.selected}/reference-frame`, { method: "POST", body, raw: true });
      notice("Reference frame stored.");
      await selectSession(state.selected);
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("signature-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = new FormData();
    body.append("form_line", byId("signature-line").value);
    body.append("file", byId("signature-file").files[0]);
    try {
      await api(`/api/v1/group-sessions/${state.selected}/consent-signatures`, { method: "POST", body, raw: true });
      notice("Signature stored on the consent record.");
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("frame").addEventListener("click", (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width) return;
    state.seats.push({
      x: Math.min(0.82, Math.max(0, (event.clientX - rect.left) / rect.width)),
      y: Math.min(0.6, Math.max(0, (event.clientY - rect.top) / rect.height)),
      width: 0.18,
      height: 0.4,
    });
    renderSeats();
  });
  byId("confirm-seats").addEventListener("click", async () => {
    try {
      await api(`/api/v1/group-sessions/${state.selected}/participants`, {
        method: "PUT",
        body: { confirmed: true, camera_orientation: "facing participants", frame_time_s: 0, regions: state.seats },
      });
      notice("Seat order confirmed from right to left.");
      await selectSession(state.selected);
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("open-video").addEventListener("click", async () => {
    try {
      const grant = await api(`/api/v1/group-sessions/${state.selected}/recording/playback`, { method: "POST", body: {} });
      byId("playback").src = `${grant.media_path}?playback_token=${encodeURIComponent(grant.playback_token)}`;
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("participant-select").addEventListener("change", () => loadMarksheet().catch((error) => notice(error.message, true)));
  byId("submit-marksheet").addEventListener("click", async () => {
    try {
      await saveDraft();
      const participantId = byId("participant-select").value;
      await api(`/api/v1/group-sessions/${state.selected}/participants/${participantId}/marksheets/${state.accountId}/submit`, { method: "POST", body: {} });
      byId("save-status").textContent = "Submitted.";
      notice("Marksheet submitted.");
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("pdf-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const participantId = byId("participant-select").value;
    const body = new FormData();
    body.append("file", byId("pdf-file").files[0]);
    try {
      const result = await api(`/api/v1/group-sessions/${state.selected}/participants/${participantId}/attachments`, { method: "POST", body, raw: true });
      const response = await fetch(`/api/v1/group-sessions/${state.selected}/participants/${participantId}/attachments/${result.attachment.id}`, {
        headers: { Authorization: `Bearer ${state.token}` },
      });
      byId("pdf-frame").src = URL.createObjectURL(await response.blob());
      byId("pdf-frame").hidden = false;
      notice("PDF attached for review. It is not a training label.");
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("load-disagreements").addEventListener("click", async () => {
    try {
      const result = await api(`/api/v1/group-sessions/${state.selected}/participants/${byId("participant-select").value}/disagreements`);
      state.primaryRaterId = result.primary_rater_id;
      const host = byId("disagreements");
      host.replaceChildren();
      if (!result.disagreements.length) {
        const empty = document.createElement("p");
        empty.className = "empty-inline";
        empty.textContent = "No item disagreements.";
        host.append(empty);
        return;
      }
      result.disagreements.forEach((row) => {
        const line = document.createElement("div");
        line.className = "stack-row";
        const title = document.createElement("strong");
        title.textContent = `Item ${row.item_letter}`;
        const detail = document.createElement("span");
        detail.textContent = `primary ${row.primary} / independent ${row.independent}`;
        line.append(title, detail);
        host.append(line);
      });
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("submit-review").addEventListener("click", async () => {
    try {
      const items = letters.map((letter) => state.items[letter]).filter(Boolean);
      await api(`/api/v1/group-sessions/${state.selected}/participants/${byId("participant-select").value}/review`, {
        method: "POST",
        body: { reason: byId("review-reason").value, items },
      });
      notice("Adjudicated answers recorded. Both originals remain.");
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("load-correction").addEventListener("click", async () => {
    try {
      if (!state.primaryRaterId) {
        const result = await api(`/api/v1/group-sessions/${state.selected}/participants/${byId("participant-select").value}/disagreements`);
        state.primaryRaterId = result.primary_rater_id;
      }
      const sheet = await api(`/api/v1/group-sessions/${state.selected}/participants/${byId("participant-select").value}/marksheets/${state.primaryRaterId}`);
      state.items = Object.fromEntries((sheet.items || []).map((item) => [item.item_letter, item]));
      renderItems();
      applyLoadedItems();
      notice("Submitted sheet loaded for correction.");
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("save-correction").addEventListener("click", async () => {
    try {
      const items = letters.map((letter) => state.items[letter]).filter((item) => item && item.score);
      await api(`/api/v1/group-sessions/${state.selected}/participants/${byId("participant-select").value}/marksheets/${state.primaryRaterId}/corrections`, {
        method: "POST",
        body: { reason: byId("review-reason").value, items },
      });
      notice("Correction recorded. The original submission remains.");
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("predict-button").addEventListener("click", async () => {
    try {
      const result = await api(`/api/v1/group-sessions/${state.selected}/predictions`, { method: "POST", body: {} });
      const host = byId("predictions");
      host.replaceChildren();
      const human = document.createElement("article");
      human.className = "inference-decision";
      const humanSummary = document.createElement("div");
      humanSummary.className = "decision-summary";
      const humanState = document.createElement("strong");
      humanState.className = "decision-state";
      humanState.textContent = "psychologist";
      humanSummary.append(humanState);
      const humanCopy = document.createElement("p");
      humanCopy.className = "decision-copy";
      humanCopy.textContent = result.psychologist.length
        ? "Session patterns below open the cited moment."
        : "No session pattern is established from the submitted scores.";
      human.append(humanSummary, humanCopy);
      result.psychologist.forEach((row) => human.append(claimButton(`${row.item_letter} scored ${row.score}`, row.evidence_start_s)));
      const model = document.createElement("article");
      model.className = "inference-decision";
      const modelSummary = document.createElement("div");
      modelSummary.className = "decision-summary";
      const modelState = document.createElement("strong");
      modelState.className = "decision-state";
      modelState.textContent = result.model.length ? "model" : "unavailable";
      if (!result.model.length) modelState.classList.add("decision-state--abstained");
      modelSummary.append(modelState);
      const modelCopy = document.createElement("p");
      modelCopy.className = "decision-copy";
      const claims = result.predictions.filter((row) => row.playback_fragment);
      modelCopy.textContent = claims.length
        ? "Each model claim opens its verified interval."
        : "No model claim is available. The psychologist's scores stay as entered.";
      model.append(modelSummary, modelCopy);
      claims.forEach((row) => model.append(claimButton(`${row.item_letter} ${row.predicted_label} ${row.playback_fragment}`, row.evidence_start_s)));
      host.append(human, model);
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("export-button").addEventListener("click", async () => {
    try {
      const payload = await api(`/api/v1/group-sessions/${state.selected}/export`);
      const node = byId("export-summary");
      node.hidden = false;
      node.textContent = `package ${payload.package_sha256}\nrecording ${payload.recording_sha256}\nexamples ${payload.examples.length}\npdf labels ${payload.pdf_text_used_as_labels}`;
      notice("Research package built.");
    } catch (error) {
      notice(error.message, true);
    }
  });
  byId("delete-button").addEventListener("click", async () => {
    if (!state.selected || !window.confirm("Delete this group session and its recording? This cannot be undone.")) return;
    try {
      await api(`/api/v1/group-sessions/${state.selected}`, { method: "DELETE" });
      state.selected = null;
      state.view = null;
      byId("session-content").hidden = true;
      byId("empty-state").hidden = false;
      notice("Group session deleted.");
      await loadSessions();
    } catch (error) {
      notice(error.message, true);
    }
  });

  checkHealth();
  loadSessions();
  setInterval(checkHealth, 10000);
  if (state.token) connect().catch(() => {});
})();
