"use strict";

const marksheetAreas = [
  ["Discussion tracking", "ABCD"], ["Contribution structure", "EFGH"],
  ["Turn-taking and reciprocity", "IJKL"], ["Response to challenge", "MNOP"],
  ["Pressure-linked delivery change", "QRST"],
];

function talkingPatterns(report) {
  const names = ["speaking_time", "speaking_share", "turn_count", "words_per_minute", "question_rate", "interruption_candidate_rate"];
  const rows = names.map(name => (report.features || []).find(f => f.name === name)).filter(Boolean);
  return `<section class="panel talking-patterns"><div class="section-head"><div><h2>Talking patterns</h2><p>Measured inputs for ${esc(report.speaker.display_name)}</p></div></div>${rows.length ? `<dl class="behavior-measures">${rows.map(f => `<div><dt>${esc(nice(f.name))}</dt><dd>${number(f.value)} <small>${esc(f.unit)}</small></dd><p>${esc(f.status)} / ${esc(f.confidence)} confidence</p></div>`).join("")}</dl>` : '<p>Supported measurements are unavailable for this speaker.</p>'}<p class="muted">Question markers and overlap entries are estimates. They do not establish understanding, interruption intent, or an A-T rating.</p></section>`;
}

function marksheetComparison(report) {
  const human = report.human_observations || [];
  const predictions = (report.supervised_predictions || []).filter(p => p.family === "at");
  const sessionId = report.session_id || "";
  const humanValue = answer => answer.state === "scored" ? `${answer.score} / 4` : answer.state === "not_observed" ? "N/O" : "Missing answer";
  const rating = answer => `<div class="human-rating"><strong>${esc(humanValue(answer))}</strong><p>${esc(answer.source_type === "self_report" ? "Participant self-report" : answer.source_type === "independent_review" ? "Independent observer rating" : "Human observer rating")} / ${esc(answer.participant_code)} / reviewer ${esc(answer.reviewer_id || "not recorded")}</p><small>Revision ${answer.label_revision} / ${esc(nice(answer.review_status))}${answer.independent_reviewer_id ? ` by ${esc(answer.independent_reviewer_id)}` : ""} / ${esc(answer.component || "modality not recorded")} / opportunity ${answer.fair_opportunity === true ? "confirmed" : answer.fair_opportunity === false ? "absent" : "not recorded"} / confidence ${answer.confidence ?? "not recorded"}</small>${answer.adjudicated_score !== null && answer.adjudicated_score !== undefined ? `<p>Separate adjudication: ${answer.adjudicated_score} / 4 by ${esc(answer.adjudicator_id)}. ${esc(answer.adjudication_rationale)}</p>` : ""}<details><summary>Human evidence and context</summary><p>${esc(answer.narrative || answer.missing_reason || "No narrative supplied")}</p>${(answer.evidence_windows || []).map(w => `<div class="human-window"><button data-seek="${Number(w.start)}" data-source="${esc(sessionId)}">Play ${time(w.start)} to ${time(w.end)}</button><p>${esc(nice(w.kind))}: ${esc(w.context)} ${esc(w.response || "")} ${esc(w.participation_effect || "")}</p></div>`).join("") || '<p>No timestamped evidence supplied.</p>'}</details></div>`;
  const predicted = p => p ? `<strong>${p.abstention ? "Abstained" : `${p.score} / 4`}</strong><p>${esc(p.abstention || "Supervised estimate")}</p><small>${esc(p.evaluation_status)} / model ${esc(p.model_id)}</small><details><summary>Prediction uncertainty and lineage</summary><pre>${esc(JSON.stringify({uncertainty:p.uncertainty,distribution:p.distribution,lineage:p.lineage},null,2))}</pre></details>` : '<span class="muted">No current prediction</span>';
  return `<section class="panel marksheet-comparison"><div class="section-head"><div><h2>Marksheet observations and predictions</h2><p>Contextual A-T ratings for ${esc(report.speaker.display_name)}</p></div><a href="#sessions/${esc(sessionId)}/participants">Review participant answers &rarr;</a></div><p>Human ratings and model predictions remain separate. This comparison does not establish a statistical correlation or a validated psychological profile.</p>${!human.length ? '<p class="notice">No current human ratings are linked through a confirmed participant-to-speaker mapping. Saved unmapped answers remain in Participants & answers.</p>' : ""}<div class="marksheet-areas">${marksheetAreas.map(([name,letters]) => `<section class="marksheet-area"><h3>${esc(name)} <span class="muted">${letters[0]}-${letters.at(-1)}</span></h3>${!human.some(a => letters.includes(a.item_key)) && !predictions.some(p => letters.includes(p.target)) ? '<p class="muted">No linked human observations for this area / no current model predictions.</p>' : `<div class="table-wrap"><table><thead><tr><th>Item</th><th>Human annotation</th><th>Supervised prediction</th></tr></thead><tbody>${[...letters].map(key => { const answers = human.filter(a => a.item_key === key); const prediction = predictions.find(p => p.target === key); return `<tr><td><strong>${key}</strong><p>${esc(answers[0]?.description || "See the source marksheet definition")}</p></td><td>${answers.map(rating).join("") || '<span class="muted">Not supplied</span>'}</td><td>${predicted(prediction)}</td></tr>`; }).join("")}</tbody></table></div>`}</section>`).join("")}</div><p class="muted">Zero means not observed despite fair opportunity. N/O means no supported conclusion; missing means no supplied answer. Q-T needs an earlier same-session baseline and event windows, separate from previous-session history. Review status does not establish training eligibility.</p><a href="#training">Inspect data readiness and per-target evaluation &rarr;</a></section>`;
}

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
  const label = selection.pending ? "Report in progress" : selection.current ? "Update report" : selection.latest?.status === "failed" ? "Try again" : "Create observation report";
  let status = "";
  if (selection.pending) status = `<div class="report-progress" role="status"><span class="report-state-dot" aria-hidden="true"></span><div><strong>${selection.pending.status === "running" ? "Writing your observation report" : "Your report is queued"}</strong><p>${selection.current ? "Your previous report stays available while the new one is prepared." : "The local worker will use this speaker's measurements and conversation evidence. This view updates when the report is ready."}</p></div></div>`;
  else if (selection.latest?.status === "failed") status = `<div class="report-failure"><strong>The latest report could not be created.</strong><p>${selection.current ? "Your previous completed report remains below." : "Your transcript and measurements are still available. Try again after checking the issue."}</p><details><summary>What went wrong</summary><p>${esc(selection.latest.error || "The interpretation did not pass validation.")}</p></details></div>`;
  let content = loadError ? `<p class="report-failure">${esc(loadError)}</p>` : communicationReportContent(run || {}, report.speaker.display_name);
  if (!selection.current && !selection.pending && !status) content = `<div class="report-start"><h3>Turn this speaker's evidence into a readable report.</h3><p>See the communication patterns supported by this conversation, the moments behind them, and adjustments you could try.</p>${selection.latest?.status === "stale" ? '<p>The recording or comparison settings changed. Create a new report using the current evidence.</p>' : ""}<p class="muted">Measured features are already available in Measurements. A personal comparison appears only when enough previous sessions exist.</p></div>`;
  return `<div class="session-pane behavioral-report" data-session-pane="analysis">${talkingPatterns(report)}${marksheetComparison(report)}<section class="panel report-workspace"><div class="report-heading"><div><h2>Behavioral observation report</h2><p>Interpretation of ${esc(report.speaker.display_name)}'s observed conversation</p></div><button class="primary" data-run="${esc(report.speaker.id)}" data-condition="C" ${selection.pending ? 'disabled aria-busy="true"' : ""}>${label}</button></div>${status}${content}<details class="report-history"><summary>Report history and research details</summary><p>Earlier attempts stay available for reproducibility. Transcript-only and structured-context reports are research comparisons; the report above uses full PSYCON.</p><p>Optional exploratory comparison goal: ${esc(report.target_archetype)}. Saved reports retain the goal and inputs used at generation time.</p><div class="controls"><button data-run="${esc(report.speaker.id)}" data-condition="ABC" ${report.llm_runs.some(r => ["queued","running"].includes(r.status)) ? "disabled" : ""}>Run research comparison</button>${run?.blind_id ? `<a href="/review/${esc(run.blind_id)}" target="_blank" rel="noopener">Independent reviewer form &nearr;</a>` : ""}</div>${report.llm_runs.length ? runsTable(report.llm_runs) : '<p class="muted">No earlier reports.</p>'}${run ? `<details><summary>Current report input, model, and raw output</summary><pre>${esc(JSON.stringify(run, null, 2))}</pre></details>` : ""}</details></section></div>`;
}
