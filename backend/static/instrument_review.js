"use strict";
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const blindId = document.querySelector("[data-blind-id]").dataset.blindId;
const notice = text => { document.querySelector("#review-notice").textContent = text; document.querySelector("#review-notice").className = "notice"; };
async function load() {
  const response = await fetch(`/api/instrument/review/${encodeURIComponent(blindId)}`);
  const result = await response.json(); if (!response.ok) throw new Error(result.error || "Report unavailable");
  const speakers = [...new Set(result.transcript.map(u=>u.speaker_id).filter(Boolean))];
  const speakerLabel = id => id ? `Speaker ${speakers.indexOf(id) + 1}` : "Unattributed";
  const sources = result.sources || [];
  const refs = new Map(sources.map((source, index)=>[source.id, index + 1]));
  document.querySelector("#review-sources").innerHTML = sources.map((source, index)=>`<div class="evidence-quote" id="review-source-${index + 1}"><h3>Source ${index + 1}</h3><small class="mono">${source.start.toFixed(2)}-${source.end.toFixed(2)} seconds - ${esc(speakerLabel(source.speaker_id))}</small><p>${esc(source.text)}</p></div>`).join("") || '<p class="muted">No cited source excerpts are available.</p>';
  document.querySelector("#review-report").innerHTML = `<p>${esc(result.report.summary)}</p>` + result.report.claims.map((c, i) => `<div class="evidence-quote"><h3>Claim ${i + 1}</h3><p>Observation: ${esc(c.observation)}</p><p>Inference: ${esc(c.inference)}</p><p class="muted">${esc(c.confidence)} confidence · ${esc(c.limitation)}</p><p>Possible adjustment: ${esc(c.suggestion)}</p><div class="controls">${c.evidence_ids.map(id=>`<a href="#review-source-${refs.get(id)}">Source ${refs.get(id) || "unavailable"}</a>`).join("")}</div></div>`).join("") + result.report.limitations.map(l => `<p class="muted">${esc(l)}</p>`).join("");
  document.querySelector("#review-transcript").innerHTML = result.transcript.map(u => `<div class="evidence-quote"><small class="mono">${u.start.toFixed(2)}–${u.end.toFixed(2)} · ${esc(speakerLabel(u.speaker_id))} · ${esc(u.id)}</small><p>${esc(u.text)}</p></div>`).join("");
  document.querySelector("#review-item").innerHTML += result.report.claims.map((c, i) => `<option value="${i}">Claim ${i + 1}: ${esc(c.observation.slice(0, 90))}</option>`).join("");
  document.querySelector("#review-ratings").innerHTML = result.criteria.map(c => `<label>${esc(c.replaceAll("_", " "))}<select name="${esc(c)}" required><option value="">Choose a rating</option>${[0,1,2,3,4].map(n => `<option value="${n}">${n} / 4</option>`).join("")}</select></label>`).join("");
}
document.querySelector("#review-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.target.querySelector("button[type=submit]"); button.disabled = true; button.setAttribute("aria-busy", "true");
  try { const values = Object.fromEntries(new FormData(event.target)); for (const key of Object.keys(values)) if (!["reviewer_id", "notes"].includes(key)) values[key] = Number(values[key]); const response = await fetch(`/api/instrument/review/${encodeURIComponent(blindId)}`, {method:"POST", headers:{"Content-Type":"application/json", "X-PSYCON-Request":"research-instrument"}, body:JSON.stringify(values)}); const result = await response.json(); if (!response.ok) throw new Error(result.error); notice("Annotation saved. Your previous rating of this same item is replaced when you submit again."); } catch (error) { notice(error.message); } finally { button.disabled = false; button.removeAttribute("aria-busy"); }
});
load().catch(error => notice(error.message));
