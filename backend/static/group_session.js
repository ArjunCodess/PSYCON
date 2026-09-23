(() => {
  const state = { selected: null };
  const byId = (id) => document.getElementById(id);

  function notice(message, isError = false) {
    const node = byId("notice");
    node.hidden = false;
    node.textContent = message;
    node.classList.toggle("error", isError);
  }

  function show(step) {
    byId("screen-upload").hidden = step !== 1;
    byId("screen-mark").hidden = step !== 2;
    byId("screen-done").hidden = step !== 3;
    byId("notice").hidden = true;
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
    const response = await fetch(path, { method: options.method || "GET", headers, body });
    const payload = await response.json().catch(() => ({ error: { message: "Invalid server response" } }));
    if (!response.ok) throw new Error(payload.error?.message || `Request failed: ${response.status}`);
    return payload;
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
      state.selected = marked.group_session.session.id;
      byId("marked-preview").src = `data:image/jpeg;base64,${marked.marked_frame_base64}`;
      byId("marked-caption").textContent = `${marked.face_count} faces. Participant 1 is the person on the right side. Numbers continue toward the left.`;
      byId("csv-form").reset();
      show(2);
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
        byId("intake-form").reset();
        byId("marked-preview").removeAttribute("src");
        show(1);
      }, 1600);
    } catch (error) {
      notice(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
})();
