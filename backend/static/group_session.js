(() => {
  const state = { selected: null, step: 1, refresh: null, speechStop: null };
  const byId = (id) => document.getElementById(id);
  const make = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  const fixed = (value, places = 1) => value == null ? "—" : Number(value).toFixed(places);

  function notice(message, isError = false) {
    const node = byId("notice");
    node.hidden = false;
    node.textContent = message;
    node.classList.toggle("error", isError);
  }

  function show(step) {
    state.step = step;
    byId("screen-upload").hidden = step !== 1;
    byId("screen-mark").hidden = step !== 2;
    byId("screen-done").hidden = step !== 3;
    byId("notice").hidden = true;
    if (step !== 2 && state.refresh) clearTimeout(state.refresh);
    if (step !== 2) state.speechStop?.();
  }

  async function api(path, options = {}) {
    const headers = {};
    let body;
    if (options.raw) {
      body = options.body;
    } else if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }
    const response = await fetch(path, { method: options.method || "GET", headers, body, cache: "no-store" });
    const payload = await response.json().catch(() => ({ error: { message: "Invalid server response" } }));
    if (!response.ok) throw new Error(payload.error?.message || `Request failed: ${response.status}`);
    return payload;
  }

  function addMetric(parent, label, value, unit = "") {
    const cell = make("div", "voice-metric");
    cell.append(make("span", "voice-metric-label", label));
    cell.append(make("strong", "voice-metric-value", value === "—" ? value : `${value}${unit}`));
    parent.append(cell);
  }

  function addSegments(parent, segments) {
    if (!segments.length) {
      parent.append(make("p", "field-helper", "No windows recorded."));
      return;
    }
    const list = make("ol", "voice-segments");
    for (const row of segments) {
      list.append(make("li", "", `${fixed(row.start_s, 2)}–${fixed(row.end_s, 2)} s · confidence ${fixed(row.confidence, 2)}${row.overlap_refused_s ? ` · ${fixed(row.overlap_refused_s, 2)} s overlap refused` : ""}`));
    }
    parent.append(list);
  }

  function addSpeechPlayer(card, person, sessionId, assigned) {
    const player = make("audio", "face-voice-audio");
    player.controls = true;
    player.preload = "none";
    player.src = `/api/v1/group-sessions/${sessionId}/face-voices/${person.slot_number}/audio`;
    const label = person.label || `participant ${person.slot_number}`;
    player.setAttribute("aria-label", assigned ? `Speech assigned to ${label}` : `Tentative speech excerpt for ${label}`);
    if (!assigned) card.append(make("p", "field-helper", "Short stitched speech excerpt near this face's mouth activity. It may contain another voice or overlap and is excluded from training."));
    const stop = () => { player.pause(); if (state.speechStop === stop) state.speechStop = null; };
    player.addEventListener("play", () => {
      if (state.speechStop !== stop) state.speechStop?.();
      state.speechStop = stop;
    });
    player.addEventListener("ended", stop);
    card.append(player);
  }

  function personCard(person, processing, sessionId) {
    const card = make("article", "face-voice-card");
    const header = make("div", "face-voice-card-heading");
    const title = make("div");
    title.append(make("span", "face-voice-number", String(person.slot_number).padStart(2, "0")));
    title.append(make("h3", "", person.label || `Participant ${person.slot_number}`));
    if (person.marksheet?.class_name) title.append(make("span", "face-voice-class", person.marksheet.class_name));
    header.append(title);
    const voice = person.voice;
    const tentative = voice?.metrics?.tentative;
    const status = voice?.status === "ready" ? "Voice ready" :
      tentative ? "Tentative voice measures" :
      voice?.status === "insufficient_speech" ? "Insufficient speech" :
      processing.status === "failed" ? "Voice analysis failed" :
      processing.status === "not_analyzed" ? "Reprocessing required" :
      processing.status === "complete" ? "Voice unavailable" : "Analyzing voice";
    header.append(make("span", `face-voice-badge ${voice?.status === "ready" ? "is-ready" : ""}`, status));
    card.append(header);
    if (voice?.status === "ready" || person.review_seconds > 0) addSpeechPlayer(card, person, sessionId, voice?.status === "ready");
    const metrics = make("div", "voice-metrics");
    addMetric(metrics, tentative ? "Confirmed speech" : "Usable speech", fixed(voice?.usable_seconds), " s");
    if (person.review_seconds > 0) addMetric(metrics, "Tentative excerpt", fixed(person.review_seconds), " s");
    addMetric(metrics, tentative ? "Excerpt windows" : "Assigned windows", tentative?.window_count ?? person.segments.length);
    addMetric(metrics, tentative ? "Excerpt turns" : "Turns", tentative?.turn_count ?? voice?.metrics?.turn_count ?? "—");
    addMetric(metrics, "Overlap refused", tentative ? "Unknown speaker" : fixed(voice?.metrics?.overlap_refused_s), tentative ? "" : " s");
    addMetric(metrics, tentative ? "Excerpt pauses" : "Pauses", fixed(tentative?.pause_total_s ?? voice?.metrics?.pause_total_s), " s");
    const wordRate = tentative?.word_rate_wpm ?? voice?.metrics?.word_rate_wpm;
    addMetric(metrics, tentative ? "Excerpt word rate" : "Word rate", tentative && wordRate == null ? "No transcript" : fixed(wordRate, 0), wordRate == null ? "" : " / min");
    addMetric(metrics, "Pitch jitter", tentative ? "Needs clean speech" : fixed(voice?.metrics?.pitch_jitter_relative, 4));
    addMetric(metrics, "Combined feature", person.combined_feature_ready ? "Ready" : tentative ? "Needs confirmed voice" : "Waiting");
    card.append(metrics);
    const detail = make("details", "face-voice-detail");
    detail.append(make("summary", "", "View windows, measures and vectors"));
    const body = make("div", "face-voice-detail-body");
    body.append(make("h4", "", "Assigned speech windows"));
    addSegments(body, person.segments);
    if (person.review_segments?.length) {
      body.append(make("h4", "", "Tentative review windows"));
      addSegments(body, person.review_segments);
    }
    body.append(make("h4", "", "Voice measures"));
    body.append(make("pre", "voice-json", JSON.stringify({
      status: voice?.status ?? "pending", engine: voice?.engine ?? null,
      embedding_engine: voice?.embedding_engine ?? null,
      usable_seconds: voice?.usable_seconds ?? null, metrics: voice?.metrics ?? null,
    }, null, 2)));
    body.append(make("h4", "", "Saved feature vectors"));
    body.append(make("pre", "voice-json", JSON.stringify({
      face_vector: person.face?.vector ?? null,
      spectral_voice_vector: voice?.vector ?? null,
      tentative_spectral_vector: tentative?.spectral_vector ?? null,
      speaker_embedding: voice?.embedding ?? null,
      face_box: person.face?.box ?? null,
    }, null, 2)));
    if (person.marksheet) {
      body.append(make("h4", "", "Marksheet row"));
      body.append(make("pre", "voice-json", JSON.stringify(person.marksheet, null, 2)));
    }
    detail.append(body);
    card.append(detail);
    return card;
  }

  function renderVoice(data) {
    state.speechStop?.();
    const processing = data.voice_matching || { status: "pending" };
    const people = data.people || [];
    const ready = people.filter((person) => person.voice?.status === "ready").length;
    const tentative = people.filter((person) => person.voice?.metrics?.tentative).length;
    byId("voice-status").textContent = ({
      pending: "Voice analysis queued", running: "Voice analysis running",
      complete: `${ready} confirmed · ${tentative} tentative / ${people.length} voices`,
      failed: "Voice analysis failed", unavailable: "Voice analysis unavailable",
      not_analyzed: "Voice analysis not run",
    })[processing.status] || "Voice analysis pending";
    byId("voice-status").classList.toggle("is-ready", processing.status === "complete");
    const unknown = data.unknown_segments || [];
    byId("voice-summary").textContent = processing.status === "complete" && !ready ?
      `${unknown.length} speech windows stayed unassigned. Tentative excerpt measures are shown where available; combined training still needs confirmed speech.` :
      processing.status === "not_analyzed" ? "This recording was processed before voice matching was available." :
      processing.status === "failed" ? `Voice matching failed${processing.reason ? `: ${processing.reason}` : "."}` : "";
    byId("face-voice-list").replaceChildren(...people.map((person) => personCard(person, processing, state.selected)));
    byId("unknown-voice").hidden = unknown.length === 0;
    byId("unknown-count").textContent = unknown.length;
    byId("unknown-list").replaceChildren();
    addSegments(byId("unknown-list"), unknown);
    const timeline = make("ol", "voice-segments");
    for (const row of data.speaking_timeline || []) {
      const name = row.status === "assigned" ? `Participant ${row.slot_number}` : "Unknown";
      const reason = row.status === "assigned" ? "" : ` · ${(row.evidence?.reason || "uncertain").replaceAll("_", " ")}`;
      timeline.append(make("li", "", `${fixed(row.start_s, 2)}–${fixed(row.end_s, 2)} s · ${name}${reason}`));
    }
    byId("speaking-timeline").replaceChildren(timeline);
  }

  async function refreshVoice() {
    if (!state.selected || state.step !== 2) return;
    try {
      const sessionId = state.selected;
      const data = await api(`/api/v1/group-sessions/${sessionId}/face-voices`);
      if (state.step !== 2 || state.selected !== sessionId) return;
      renderVoice(data);
      if (["pending", "running"].includes(data.voice_matching?.status)) {
        state.refresh = setTimeout(refreshVoice, 2500);
      }
    } catch (error) {
      byId("voice-status").textContent = `Voice details unavailable: ${error.message}`;
      if (state.step === 2) state.refresh = setTimeout(refreshVoice, 5000);
    }
  }

  function openMarkedSession(sessionId, faceCount) {
    state.selected = sessionId;
    byId("marked-caption").textContent = `${faceCount} faces. Participant 1 is the person on the right side. Numbers continue toward the left.`;
    byId("csv-form").reset();
    show(2);
    refreshVoice();
  }

  byId("intake-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = new FormData();
    body.append("file", byId("intake-video").files[0]);
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    notice("Reading the first frame.");
    try {
      const marked = await api("/api/v1/group-sessions/from-video", { method: "POST", body, raw: true });
      if (marked.status !== "marked") {
        notice(`Found ${marked.face_count} faces. A recording needs between 2 and 10.`, true);
        return;
      }
      const sessionId = marked.group_session.session.id;
      byId("marked-preview").src = `data:image/jpeg;base64,${marked.marked_frame_base64}`;
      history.replaceState(null, "", `/group?session=${sessionId}`);
      openMarkedSession(sessionId, marked.face_count);
    } catch (error) {
      notice(error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  byId("csv-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.selected) {
      notice("Submit a recording first.", true);
      return;
    }
    const body = new FormData();
    body.append("file", byId("csv-file").files[0]);
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      const stored = await api(`/api/v1/group-sessions/${state.selected}/labels`, { method: "POST", body, raw: true });
      const classes = Object.entries(stored.classes || {}).map(([slot, name]) => `${slot} ${name}`).join(", ");
      byId("done-copy").textContent = `Stored ${stored.labels} scores. Classes: ${classes}.`;
      show(3);
      window.setTimeout(() => {
        state.selected = null;
        history.replaceState(null, "", "/group");
        byId("intake-form").reset();
        byId("marked-preview").removeAttribute("src");
        byId("face-voice-list").replaceChildren();
        show(1);
      }, 1600);
    } catch (error) {
      notice(error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  const sessionId = new URLSearchParams(location.search).get("session");
  if (sessionId && /^[0-9a-f-]{36}$/i.test(sessionId)) {
    api(`/api/v1/group-sessions/${sessionId}`).then((data) => {
      if (!data.marked_frame_ready) throw new Error("This session has no marked frame.");
      byId("marked-preview").src = `/api/v1/group-sessions/${sessionId}/reference-frame`;
      openMarkedSession(sessionId, data.participants.length);
    }).catch((error) => notice(error.message, true));
  }
})();
