"use strict";

function reportRunState(rows) {
  const full = rows.filter(run => run.condition === "C");
  return {
    current: full.find(run => run.status === "complete"),
    pending: full.find(run => ["queued", "running"].includes(run.status)),
    latest: full[0],
  };
}

function communicationReportContent(run, speakerName) {
  if (run.status !== "complete" || !run.output) return "";
  const packet = run.input || {};
  const sources = new Map([...(packet.transcript || []), ...(packet.evidence || [])].map(source => [source.id, source]));
  const transcript = packet.transcript || [];
  const scope = transcript.length ? `${transcript.length} conversation excerpts / ${time(Math.min(...transcript.map(u => u.start)))} to ${time(Math.max(...transcript.map(u => u.end)))}` : "Conversation evidence";
  return `<div class="communication-report">
    <div class="report-summary"><p class="report-scope">${esc(speakerName)} / ${esc(scope)}</p><h3>At a glance</h3><p class="report-overview">${esc(run.output.summary)}</p><p class="report-qualification">This is an evidence-supported interpretation of a conversation window, not a personality assessment or a report on the entire recording.</p></div>
    ${run.output.claims.length ? `<ol class="report-findings" role="list" aria-label="Supported communication observations">${run.output.claims.map(claim => {
      const linked = [...new Set(claim.evidence_ids)].map(id => sources.get(id)).filter(Boolean);
      return `<li class="report-finding"><div class="finding-reading"><div class="finding-meta"><span>Observed behavior</span><span class="confidence-label">${esc(nice(claim.confidence))} confidence</span></div><h3>${esc(claim.observation)}</h3><p class="finding-inference"><strong>Possible interpretation</strong> ${esc(claim.inference)}</p>
        <details class="finding-evidence"><summary>See ${linked.length} supporting ${linked.length === 1 ? "moment" : "moments"}</summary><div class="finding-sources">${linked.map(source => `<figure><figcaption><button class="evidence-play" data-seek="${Number(source.start)}" aria-label="Play supporting audio at ${time(source.start)}"><svg aria-hidden="true" viewBox="0 0 16 16"><path d="M5 3l8 5-8 5z"/></svg><span class="mono">${time(source.start)}</span></button><span>${esc(speakerName)}</span></figcaption><blockquote>${esc(source.text)}</blockquote></figure>`).join("")}<button class="quiet" data-evidence="${esc(JSON.stringify(claim.evidence_ids))}">Open full evidence and context &rarr;</button></div></details>
        <details class="finding-limitation"><summary>Why this interpretation is uncertain</summary><p>${esc(claim.limitation)}</p></details></div>
        <div class="finding-adjustment"><h4>Try in your next conversation</h4><p>${esc(claim.suggestion)}</p></div></li>`;
    }).join("")}</ol>` : '<p class="report-no-claims">No supported communication observations were returned for this window. The transcript and measured features are still available.</p>'}
    <details class="report-limitations"><summary>Scope and limitations of this report</summary><p>${esc(packet.coverage || "This interpretation uses the supplied evidence window.")}</p>${run.output.limitations.map(limitation => `<p>${esc(limitation)}</p>`).join("")}<p>Citations have been checked for valid source IDs and speaker attribution. Independent reviewers have not yet established whether each source supports its interpretation.</p></details>
  </div>`;
}

async function speakerReportWorkspace(report) {
  const selection = reportRunState(report.llm_runs);
  let run = null;
  let loadError = "";
  if (selection.current) {
    try { run = await api(`/runs/${selection.current.id}`); }
    catch { loadError = "Your saved report could not be loaded. Refresh this page to try again; your recording and measurements are retained."; }
  }
  const label = selection.pending ? "Report in progress" : selection.current ? "Update report" : selection.latest?.status === "failed" ? "Try again" : "Create communication report";
  let status = "";
  if (selection.pending) status = `<div class="report-progress" role="status"><span class="report-state-dot" aria-hidden="true"></span><div><strong>${selection.pending.status === "running" ? "Writing your communication report" : "Your report is queued"}</strong><p>${selection.current ? "Your previous report stays available while the new one is prepared." : "The local worker will use this speaker's measurements and conversation evidence. This view updates when the report is ready."}</p></div></div>`;
  else if (selection.latest?.status === "failed") status = `<div class="report-failure"><strong>The latest report could not be created.</strong><p>${selection.current ? "Your previous completed report remains below." : "Your transcript and measurements are still available. Try again after checking the issue."}</p><details><summary>What went wrong</summary><p>${esc(selection.latest.error || "The interpretation did not pass validation.")}</p></details></div>`;
  let content = loadError ? `<p class="report-failure">${esc(loadError)}</p>` : communicationReportContent(run || {}, report.speaker.display_name);
  if (!selection.current && !selection.pending && !status) content = `<div class="report-start"><h3>Turn this speaker's evidence into a readable report.</h3><p>See the communication patterns supported by this conversation, the moments behind them, and adjustments you could try.</p>${selection.latest?.status === "stale" ? '<p>The recording or comparison settings changed. Create a new report using the current evidence.</p>' : ""}<p class="muted">Measured features are already available in Measurements. A personal comparison appears only when enough previous sessions exist.</p></div>`;
  return `<section class="panel session-pane report-workspace" data-session-pane="analysis"><div class="report-heading"><div><h2>Communication report</h2><p>For ${esc(report.speaker.display_name)} / comparison goal: ${esc(report.target_archetype)}</p></div><button class="primary" data-run="${esc(report.speaker.id)}" data-condition="C" ${selection.pending ? 'disabled aria-busy="true"' : ""}>${label}</button></div>${status}${content}<details class="report-history"><summary>Report history and research details</summary><p>Earlier attempts stay available for reproducibility. Transcript-only and structured-context reports are research comparisons; the report above uses full PSYCON.</p><div class="controls"><button data-run="${esc(report.speaker.id)}" data-condition="ABC" ${report.llm_runs.some(r => ["queued","running"].includes(r.status)) ? "disabled" : ""}>Run research comparison</button>${run?.blind_id ? `<a href="/review/${esc(run.blind_id)}" target="_blank" rel="noopener">Independent reviewer form &nearr;</a>` : ""}</div>${report.llm_runs.length ? runsTable(report.llm_runs) : '<p class="muted">No earlier reports.</p>'}${run ? `<details><summary>Current report input, model, and raw output</summary><pre>${esc(JSON.stringify(run, null, 2))}</pre></details>` : ""}</details></section>`;
}
