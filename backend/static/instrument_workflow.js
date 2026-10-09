/* Participant answers and supervised model lifecycle in the existing research workspace. */
const PSYCONWorkflow = (() => {
  let family = "at", pendingFile = null, pendingOptions = null, trainingPoll = null, predictionSpeakers = [];
  const field = (label, name, value = "", extra = "") => `<label>${esc(label)}<input name="${esc(name)}" value="${esc(value)}" ${extra}></label>`;
  const select = (label, name, values, selected) => `<label>${esc(label)}<select name="${esc(name)}">${values.map(v => `<option value="${esc(Array.isArray(v) ? v[0] : v)}" ${String(Array.isArray(v) ? v[0] : v) === String(selected) ? "selected" : ""}>${esc(Array.isArray(v) ? v[1] : v)}</option>`).join("")}</select></label>`;
  const steps=items => `<ol class="workflow-steps" aria-label="Workflow steps">${items.map(([name,detail]) => `<li><strong>${esc(name)}</strong><span>${esc(detail)}</span></li>`).join("")}</ol>`;
  const identity = () => field("Reviewer or respondent code", "reviewer_id");
  const formChoice = () => select("Form", "form_id", [["at-4.0", "A–T contextual observation v4.0"], ["communication-1", "Independent communication observations"]]);
  const sourceChoice = () => select("Answer source", "source_type", [["observer", "Observer rating"], ["self_report", "Participant self-report"], ["independent_review", "Independent reviewer rating"]]);
  const metadataFields=[['date','Observation date'],['seat_channel','Seat / speaker channel'],['class_section','Class / section'],['topic','Discussion topic'],['observation_minutes','Observation minutes'],['languages','Languages, separated by semicolons'],['recording_quality','Recording quality, 1 to 5'],['contextual_account','Contextual account'],['evidence_summary','Evidence summary'],['signature','Observer signature / code'],['signed_at','Signed at, ISO time with timezone']];
  const contextFlags=['limited_opportunity','overlap','poor_recording','unfamiliar_language','moderation','unequal_participation','sensitive_topic','accommodation'];
  const patternNames=['discussion_tracking','contribution_structure','turn_sharing','challenge_linked_change','pressure_linked_delivery'];
  const windowsFields=() => [['event','Preceding event'],['response','Observable response'],['same_session_baseline','Earlier same-session baseline'],['second_support','Second contextual support']].map(([kind,label]) => `<fieldset><legend>${label}</legend>${field('Start seconds',kind+'_start','', 'type="number" min="0" step="0.01"')}${field('End seconds',kind+'_end','', 'type="number" min="0" step="0.01"')}${field('Observable context',kind+'_context')}</fieldset>`).join('');
  const reviewTurnRow = turn => `<tr data-review-turn><td>${field("Anonymous cluster label","cluster_label",turn.speaker || "")}</td><td>${field("Start seconds","turn_start",turn.start ?? "",'type="number" min="0" step="0.01" required')}</td><td>${field("End seconds","turn_end",turn.end ?? "",'type="number" min="0" step="0.01" required')}</td><td><button type="button" data-remove-review-turn>Remove interval</button></td></tr>`;
  const diagnostic = value => `<details><summary>Provenance and reproducibility</summary><pre>${esc(JSON.stringify(value, null, 2))}</pre></details>`;

  async function participants(detail) {
    const sid = detail.session.id;
    const [data,provenance] = await Promise.all([api(`/sessions/${sid}/participants`),api(`/sessions/${sid}/source-reviews`)]);
    const diarization=detail.stages.find(s => s.name === "diarization")?.output;
    const turns=Array.isArray(diarization) ? diarization : detail.turns.map(t => ({speaker:detail.speakers.find(s => s.id === t.speaker_id)?.label || "UNKNOWN",start:t.start,end:t.end}));
    const correction=`<details><summary>Correct merged or split speaker clusters</summary><p>A correction creates a separate analysis and retains the current transcript, answers and citation IDs. Give different cluster labels to split a merged speaker, or the same label to join fragments belonging to one speaker. Review the new participant mappings after processing.</p><form data-workflow="reanalysis" data-sid="${esc(sid)}"><div class="form-grid">${identity()}${field("Correction reason","reason","","required")}${field("Maximum speakers","max_speakers",12,'type="number" min="1" max="12" required')}</div><label><input type="checkbox" name="use_reviewed_turns"> Use my reviewed interval table rather than automatic diarization</label><details><summary>Review anonymous cluster intervals</summary><div class="table-wrap"><table><thead><tr><th>Cluster</th><th>Start</th><th>End</th><th>Action</th></tr></thead><tbody data-reviewed-turns>${turns.map(reviewTurnRow).join("")}</tbody></table></div><button type="button" data-add-review-turn>Add interval</button></details><button>Create separate analysis</button></form></details>`;
    const cards = await Promise.all(data.participants.map(async p => {
      const saved = await api(`/sessions/${sid}/participants/${p.id}/answers`);
      const mapping = data.mappings.filter(m => m.participant_id === p.id).at(-1);
      const consent=data.consents.filter(c => c.participant_id === p.id).at(-1);
      const status = p.withdrawn_at ? "Withdrawn" : !mapping || mapping.status !== "confirmed" ? "Needs mapping" : !saved.submissions.length ? "No answers uploaded" : "Uploaded · review eligibility in Training";
      return `<article class="participant-record"><div class="section-head"><div><h3>${esc(p.code)}</h3><p>${esc(status)}</p></div><button data-answers-open="${esc(p.id)}" data-sid="${esc(sid)}">Enter or correct answers</button></div>
        <details><summary>Review speaker association and consent</summary><form data-workflow="mapping" data-sid="${esc(sid)}" data-pid="${esc(p.id)}"><div class="form-grid">${select("Speaker cluster", "speaker_id", [["", "No speaker / silent participant"], ...detail.speakers.map(s => [s.id, s.display_name])], mapping?.speaker_id || "")}${select("Mapping status", "status", ["uncertain", "confirmed", "unmapped"], mapping?.status)}${identity()}${field("Reason", "reason")}</div><button>Save reviewed mapping</button></form>
        <form data-workflow="consent" data-sid="${esc(sid)}" data-pid="${esc(p.id)}"><div class="form-grid">${select("Consent", "status", ["not documented", "documented", "withdrawn"], consent?.status)}${select("Training permission", "training_allowed", [["false", "Not granted"], ["true", "Explicitly granted"]], String(consent?.training_allowed ?? false))}${field("Recorded by", "recorded_by", "", "required")}${field("Consent source or record", "source", "", "required")}</div><button>Record consent</button></form></details>
        <details><summary>Upload participant answers</summary>${uploadForm(sid, p.id)}</details>
        ${saved.submissions.length ? `<details><summary>Submitted answers and immutable revisions (${saved.submissions.length})</summary>${saved.submissions.map(s => `<section class="answer-revision"><h4>Revision ${s.revision} · ${esc(s.source_type)} · reviewer ${esc(s.reviewer_id || "not recorded")}</h4><p>${esc(s.correction_reason || "Original submission")}</p><a href="/api/instrument/sessions/${esc(sid)}/imports/${esc(s.import_id)}/source">Download original source</a><div class="table-wrap"><table><thead><tr><th>Item</th><th>Answer</th><th>Opportunity</th><th>Confidence</th><th>Evidence</th><th>Adjudication</th></tr></thead><tbody>${saved.answers.filter(a => a.submission_id === s.id).map(a => `<tr><td>${esc(a.item_key)}</td><td>${a.state === "scored" ? a.score : a.state === "not_observed" ? "N/O" : "Missing"}</td><td>${a.fair_opportunity === null ? "Not recorded" : a.fair_opportunity ? "Yes" : "No"}</td><td>${a.confidence ?? "Not recorded"}</td><td>${saved.evidence.filter(e => e.answer_id === a.id).map(e => `${esc(e.kind)} ${time(e.start_s)}–${time(e.end_s)} ${esc(e.context)}`).join("<br>")}</td><td><details><summary>Resolve a disagreement</summary><form data-workflow="adjudicate" data-answer="${esc(a.id)}">${select("Adjudicated score", "score", ["0","1","2","3","4"])}${identity()}${field("Rationale", "rationale", "", "required")}<button>Record adjudication</button></form></details></td></tr>`).join("")}</tbody></table></div><form data-workflow="review" data-submission="${esc(s.id)}"><div class="form-grid">${identity()}${select("Independent review", "decision", ["needs_review", "approved", "rejected"])}${field("Review notes", "notes")}</div><button>Save independent review</button></form><form data-workflow="attachment" data-submission="${esc(s.id)}"><label>Scanned source (PDF, PNG or JPEG, up to 10 MiB)<input type="file" name="attachment" accept=".pdf,.png,.jpg,.jpeg" required></label><button>Retain scanned source</button></form>${saved.attachments.filter(a => a.submission_id === s.id).map(a => `<p><a href="/api/instrument/attachments/${esc(a.id)}/source">${esc(a.filename)}</a></p>`).join("")}${diagnostic(s.metadata)}</section>`).join("")}</details>` : `<p class="muted">Saved answers remain available even before consent, mapping, or training eligibility.</p>`}
        <details class="danger-disclosure"><summary>Withdrawal controls</summary><form data-workflow="withdraw" data-sid="${esc(sid)}" data-pid="${esc(p.id)}"><label><input type="checkbox" name="confirmed" required> Withdraw this participant from future analysis and training</label><button class="danger">Record withdrawal</button></form></details>${diagnostic(p)}</article>`;
    }));
    return `<section class="panel session-pane" data-session-pane="participants"><div class="section-head"><div><h2>Participants & answers</h2><p>Anonymous session participants are separate from people and diarized speaker clusters.</p></div><a href="#training">Data readiness →</a></div>${steps([["Add participants","Use anonymous session codes"],["Confirm mappings","Review the correct speaker"],["Upload observations","Preview and save human answers"],["Review readiness","Check consent and evidence"]])}<form data-workflow="participant" data-sid="${esc(sid)}"><div class="controls">${field("Participant code", "code", "", "required maxlength=100")}${select("Longitudinal person", "person_id", [["", "Unlinked / session only"], ...data.people.filter(p => !p.withdrawn_at).map(p => [p.id, p.code])])}<button>Add participant</button></div></form><details><summary>Create an anonymous longitudinal person</summary><form data-workflow="person">${field("Person code", "code", "", "required maxlength=100")}<button>Create person</button></form></details><details><summary>Review original recording and excerpt ancestry</summary><p>Check the original filename, source history and playback before confirming independence. Excerpts, cropped copies and re-encoded recordings share one training split with their original. Unknown ancestry excludes labels from training.</p><form data-workflow="source-review" data-sid="${esc(sid)}"><div class="form-grid">${select("Recording relationship","kind",[["uncertain","Not established"],["independent","Reviewed independent recording"],["excerpt","Excerpt of another recording"],["derived","Re-encoded or derived copy"]])}${select("Original source session","source_session_id",[["","None / independent or uncertain"],...provenance.sources.map(s => [s.id,s.filename+" / "+s.recorded_at])])}${identity()}${field("How ancestry was checked","reason","","required")}</div><button>Save source review</button></form>${provenance.reviews.map(r => `<p>Revision ${r.revision}: ${esc(r.kind)} / ${esc(r.reviewer_id)} / ${esc(r.reason)}</p>`).join("") || "<p>No source review recorded.</p>"}</details>${correction}${cards.join("") || empty("No participants yet", "Add each participant, including silent participants. Confirm their speaker mapping before using answers for training.")}<details><summary>Upload a batch CSV or XLSX</summary>${uploadForm(sid,"",data.participants)}</details><div id="import-preview" role="status" aria-live="polite"></div></section>`;
  }

  function uploadForm(sid, pid = "", participants = []) {
    return `<form data-workflow="preview" data-sid="${esc(sid)}" data-pid="${esc(pid)}"><label>Answer file<input type="file" name="answers" accept=".csv,.xlsx" required></label><div class="form-grid">${formChoice()}${sourceChoice()}${identity()}${field("Worksheet, for workbooks with several sheets", "worksheet")}</div>${!pid ? `<fieldset><legend>Match file codes to session participants</legend><p>Enter each participant code exactly as it appears in the file. Leave unused participants empty.</p>${participants.filter(p => !p.withdrawn_at).map(p => `<label>${esc(p.code)}<input data-file-participant="${esc(p.id)}" value="${esc(p.code)}" aria-label="File code for ${esc(p.code)}"></label>`).join("")}</fieldset>` : ""}<p><a href="/api/instrument/forms/at-4.0/template">A–T CSV template</a> / <a href="/api/instrument/forms/at-4.0/template?format=xlsx">XLSX template</a> · <a href="/api/instrument/forms/communication-1/template">Communication template</a></p><button>Preview answers</button></form>`;
  }

  function snapshotSplits(snapshot) {
    return `<p>${esc(snapshot.readiness.status)}</p><div class="table-wrap"><table><thead><tr><th>Target</th><th>Training records / groups</th><th>Validation records / groups</th><th>Final evaluation records / groups</th><th>Fit readiness</th></tr></thead><tbody>${Object.entries(snapshot.readiness.targets).map(([target, row]) => `<tr><td>${esc(target)}</td>${["train","validation","test"].map(split => `<td>${row.splits[split].records} / ${row.splits[split].groups}</td>`).join("")}<td>${row.can_fit ? "Ready to fit; evaluation still required" : esc(row.reasons.join("; "))}</td></tr>`).join("") || '<tr><td colspan="5">No eligible human labels in this snapshot.</td></tr>'}</tbody></table></div>`;
  }
  function watchTraining(previous) {
    const runs=previous.runs;
    clearTimeout(trainingPoll);
    if (!runs.some(r => ["queued","training"].includes(r.status))) return;
    trainingPoll=setTimeout(async () => {
      if (location.hash !== "#training") return;
      try {
        const fresh=await api("/training");
        const signature=value => JSON.stringify([value.runs.map(r => [r.id,r.status,r.error]),value.events.map(e => e.id),value.models.map(m => [m.id,m.status])]);
        const changed=signature(fresh) !== signature(previous);
        if (changed && !document.querySelector('[data-workflow="deploy"]:focus-within')) await render();
        else watchTraining(changed ? previous : fresh);
      } catch(error) { notice(`Training status unavailable: ${error.message}. Refresh to retry.`,true); }
    },3000);
  }
  async function trainingView() {
    const [data, readiness, agreement] = await Promise.all([api("/training"), api(`/training/readiness?family=${family}`),api(`/training/agreement?family=${family}`)]);
    const invalid = new Set(data.invalidations.map(i => i.snapshot_id));
    watchTraining(data);
    predictionSpeakers=data.prediction_speakers;
    const predictionSessions=[...new Map(predictionSpeakers.map(s => [s.session_id,{id:s.session_id,filename:s.filename}])).values()];
    const predictionSession=predictionSessions[0];
    const predictionOptions=predictionSpeakers.filter(s => s.session_id === predictionSession?.id);
    return `<section class="panel training-introduction"><h2>Train from reviewed marksheets</h2>${steps([["Upload marksheets","Save contextual human observations"],["Review eligibility","Confirm mapping, consent and review"],["Freeze a dataset","Inspect reproducible target splits"],["Train and evaluate","Activate a model deliberately"]])}<p>Upload actual psychologist observations for each recording, confirm speaker mappings and consent, and approve the labels through an independent reviewer. Freeze the eligible examples, then start training from that snapshot. Models learn associations between speaker-specific conversation measurements and human ratings; they do not assign a personality type.</p><p><a href="#dashboard">Choose a discussion and upload answers</a> / <a href="/api/instrument/forms/at-4.0/template?format=xlsx">Download marksheet XLSX template</a></p><p>The Docker CPU trainer works independently of video processing. Training records, progress, evaluations and model lineage are saved in PostgreSQL. Model files remain registered locally.</p></section><section class="panel"><div class="section-head"><div><h2>Data readiness</h2><p>Every label must retain consent, confirmed speaker mapping, independent review, and supported evidence.</p></div><label>Target family<select id="training-family"><option value="at" ${family === "at" ? "selected" : ""}>A–T ratings</option><option value="communication" ${family === "communication" ? "selected" : ""}>Communication observations</option></select></label></div><p>${esc(readiness.status)} · ${readiness.rows.filter(r => r.eligible).length} eligible item observations</p><div class="table-wrap"><table><thead><tr><th>Participant</th><th>Target</th><th>Readiness</th><th>Reasons</th></tr></thead><tbody>${readiness.rows.map(r => `<tr><td><a href="#sessions/${esc(r.session_id)}/participants">${esc(r.participant_code)}</a></td><td>${esc(r.target)}</td><td>${r.eligible ? "Eligible" : "Excluded"}</td><td>${esc(r.reasons.join("; "))}</td></tr>`).join("") || '<tr><td colspan="4">No human answers uploaded. Add participants and their actual answers in a session.</td></tr>'}</tbody></table></div><form data-workflow="freeze"><div class="controls">${select("Study protocol", "study", [["unseen_participant", "Unseen participant, grouped sources"], ["longitudinal", "Within-person, explicit forward roles"]])}${field("Reproducible seed", "seed", "42", 'type="number" required')}<button ${readiness.rows.some(r => r.eligible) ? "" : "disabled"}>Freeze reviewed dataset</button></div></form></section>
      <section class="panel"><h2>Human annotation agreement</h2><p>Agreement compares actual shared judgments from independent reviewers. It does not validate the psychological meaning of a target.</p>${agreement.pairs.length ? `<div class="table-wrap"><table><thead><tr><th>Target</th><th>Reviewers</th><th>Shared participants</th><th>Exact agreement</th><th>MAE</th><th>Ordinal kappa</th></tr></thead><tbody>${agreement.pairs.map(p => `<tr><td>${esc(p.target)}</td><td>${esc(p.reviewers.join(" / "))}</td><td>${p.paired_participants}</td><td>${number(p.exact_agreement)}</td><td>${number(p.mae)}</td><td>${p.quadratic_kappa === null ? "Unavailable" : number(p.quadratic_kappa)}</td></tr>`).join("")}</tbody></table></div>` : `<p>${esc(agreement.status)}</p>`}${diagnostic(agreement)}</section><section class="panel"><h2>Frozen datasets</h2>${data.snapshots.map(s => `<div class="trait-row"><div><h3>${esc(s.task_id)} · ${new Date(s.created_at).toLocaleString()}</h3><p>${s.manifest.counts.examples} examples from ${s.manifest.counts.groups} independent groups · ${invalid.has(s.id) ? "Invalidated" : "Immutable snapshot"}</p><a href="/api/instrument/training/snapshots/${esc(s.id)}/export">Download frozen manifest</a>${snapshotSplits(s)}${diagnostic(s.manifest)}</div><button data-train-snapshot="${esc(s.id)}" ${invalid.has(s.id) || !s.readiness.can_fit ? "disabled" : ""}>Start training</button></div>`).join("") || '<p>Freeze a dataset to record label revisions, mapping revisions, features, and split assignments. Empty snapshots never produce fitted models.</p>'}</section>
      <section class="panel"><h2>Training jobs</h2>${data.runs.map(r => `<div class="trait-row"><div><h3>${esc(r.status)}</h3><p>${esc(r.error || "")}</p>${data.events.filter(e => e.run_id === r.id).map(e => `<p>${esc(e.message)}</p>`).join("")}${diagnostic(r.versions)}</div>${["queued", "training"].includes(r.status) ? `<button data-cancel-job="${esc(r.job_id)}">Cancel job</button>` : ""}</div>`).join("") || '<p>No training jobs. Workers fit separate supervised predictors; the LLM is not retrained.</p>'}</section>
      <section class="panel"><h2>Models & evaluation</h2>${data.models.map(m => { const evaluations = data.evaluations.filter(e => e.model_id === m.id); return `<article class="model-record"><h3>${esc(m.family)} / ${esc(m.target)} · ${m.evaluation_status === "evaluated" ? "Evaluated model" : "Exploratory model"}</h3><p>${esc(m.status)} · ${esc(m.limitations.join("; "))}</p><div class="table-wrap"><table><thead><tr><th>Held-out role</th><th>Records</th><th>MAE</th><th>Median baseline MAE</th><th>Macro-F1</th><th>Balanced accuracy</th></tr></thead><tbody>${evaluations.map(e => `<tr><td>${esc(e.split)}</td><td>${e.n}</td><td>${number(e.metrics.mae)}</td><td>${number(e.baseline.mae)}</td><td>${number(e.metrics.macro_f1)}</td><td>${number(e.metrics.balanced_accuracy)}</td></tr>`).join("") || '<tr><td colspan="6">Held-out evaluation unavailable. This model is exploratory.</td></tr>'}</tbody></table></div>${evaluations.map(e => diagnostic({split: e.split, confusion: e.metrics.confusion, calibration: e.metrics.probability_status, context_slices: e.metrics.context_slices, uncertainty: e.uncertainty})).join("")}<form data-workflow="deploy" data-model="${esc(m.id)}"><div class="form-grid">${field("Operator code", "operator_id", "", "required")}${field("Reason for this model change", "reason", "", "required")}${select("Model action", "action", ["activate", "rollback"])}</div>${m.evaluation_status !== "evaluated" ? '<label><input type="checkbox" name="acknowledge_exploratory" required> I acknowledge that this model has not met held-out evaluation criteria</label>' : ""}<button ${m.status === "needs_retraining" ? "disabled" : ""}>Apply model action</button></form>${!["retired","needs_retraining"].includes(m.status) ? `<a href="/api/instrument/models/${esc(m.id)}/artifact">Download verified model artifact</a>` : ""}${diagnostic(m.manifest)}</article>`; }).join("") || '<p>No fitted models. PSYCON continues to provide measured features, evidence, baselines, and transparent reports.</p>'}</section>
      <section class="panel"><h2>Inspect supervised predictions</h2><form data-workflow="predict"><div class="controls">${select("Recording", "prediction_session", predictionSessions.map(s => [s.id,`${s.filename} / ${predictionSpeakers.find(p => p.session_id === s.id).recorded_at} / analysis ${s.id.slice(0,8)}`]))}${select("Speaker", "speaker_id", predictionOptions.length ? predictionOptions.map(s => [s.id,s.display_name]) : [["","No processed recording available"]])}<button ${predictionOptions.length && data.models.some(m => m.status === "active") ? "" : "disabled"}>Predict with active models</button></div><details><summary>Add independent event context for a contextual A-T target</summary><p>These windows describe observable context; they do not supply a human target score. Without reviewed context, event-linked models abstain.</p><div class="form-grid">${select("Contextual target","context_target",[["","No event context"],..."KMNOPQRT".split("")])}${field("Context reviewer code","context_reviewer")}</div>${windowsFields()}</details></form><div id="prediction-results"></div></section>`;
  }

  async function answerEditor(sid, pid) {
    const [forms,saved] = await Promise.all([api("/forms"),api(`/sessions/${sid}/participants/${pid}/answers`)]);
    const dialog = document.querySelector("#answers-dialog");
    function draw(formId) {
      dialog.innerHTML = `<div class="dialog-title"><h2 id="answers-title">Enter or correct participant answers</h2><button type="button" data-close="answers-dialog" aria-label="Close answers">×</button></div><form data-workflow="entry" data-sid="${esc(sid)}" data-pid="${esc(pid)}"><div class="form-grid">${formChoice()}${sourceChoice()}${identity()}</div><p>0 means a supported negative observation. N/O means no fair opportunity or insufficient recording. Empty means missing.</p><div class="table-wrap"><table><thead><tr><th>Item and actual definition</th><th>Answer</th><th>Fair opportunity</th><th>Confidence</th><th>Supporting window</th></tr></thead><tbody>${forms.items.filter(i => i.form_id === formId).map(i => `<tr data-answer-item="${esc(i.key)}"><td><strong>${esc(i.key)}</strong><small>${esc(i.description)}</small></td><td>${select("Answer", "score", [["", "Missing"], ["N/O", "N/O"], "0", "1", "2", "3", "4"])}</td><td>${select("Opportunity", "fair_opportunity", [["", "Unknown"], ["yes", "Yes"], ["no", "No"]])}</td><td>${select("Confidence", "confidence", [["", "Not recorded"], "1", "2", "3"])}${field("Reason for N/O or missing answer","missing_reason")}${select("Observable component","component",[["audio","Audio / transcript"],["participation","Participation change"],["visual","Visual, excluded from audio training"]])}</td><td>${field("Start seconds", "start_s", "", 'type="number" min="0" step="0.01"')}${field("End seconds", "end_s", "", 'type="number" min="0" step="0.01"')}<label>Observable context and response<textarea name="narrative"></textarea></label><details><summary>Event, response, baseline or repeated evidence</summary>${windowsFields()}<details><summary>Advanced window import</summary><label>Additional windows<textarea name="evidence" placeholder='[{"kind":"event","start_s":12,"end_s":14,"context":"Peer disagrees"}]'></textarea></label></details></details></td></tr>`).join("")}</tbody></table></div><fieldset><legend>Actual form metadata</legend><div class="form-grid">${metadataFields.map(([name,label]) => field(label,"meta_"+name)).join("")}</div></fieldset><fieldset><legend>Context check</legend><div class="form-grid">${contextFlags.map(name => select(nice(name),"flag_"+name,[["","Not recorded"],["yes","Present"],["no","Absent"]])+field("Context note","flag_note_"+name)).join("")}</div></fieldset><fieldset><legend>Grouped contextual patterns</legend>${patternNames.map(name => `<div class="form-grid">${select(nice(name),"pattern_"+name,[["","Not recorded"],"Observed","Not clear","N/O"])}${select("Confidence","pattern_confidence_"+name,[["","Not recorded"],"1","2","3"])}${field("Observable narrative","pattern_narrative_"+name)}</div>`).join("")}</fieldset><fieldset><legend>Observation validity</legend><div class="form-grid">${select("Reliable speaker identity", "speaker_identity", [["", "Not recorded"], "Yes", "No", "Uncertain"])}${select("Recording supports evidence", "recording_support", [["", "Not recorded"], "Yes", "No", "Partly"])}${select("Fair opportunity for every scored item", "validity_opportunity", [["", "Not recorded"], "Yes", "No"])}${select("Context affects interpretation", "context_effect", [["", "Not recorded"], "No", "Possibly", "Yes"])}</div>${["speaker_identity","recording_support","fair_opportunity","context_effect"].map(name => field(nice(name)+" explanation","validity_explanation_"+name)).join("")}</fieldset><details><summary>Session form metadata, context flags, and five pattern summaries</summary><label>Metadata<textarea name="metadata" placeholder='{"seat_channel":"2","observation_minutes":10,"languages":["en"],"recording_quality":4,"contextual_account":"..."}'></textarea></label><label>Context flags<textarea name="context_flags" placeholder='{"overlap":{"present":true,"notes":"..."}}'></textarea></label><label>Human contextual patterns<textarea name="patterns" placeholder='{"discussion_tracking":{"category":"Not clear","confidence":1,"narrative":"..."}}'></textarea></label></details><label>Correction reason, required when replacing your previous submission<textarea name="correction_reason"></textarea></label><button class="primary">Save human answers</button></form>`;
      dialog.querySelector('[name="form_id"]').value = formId;
      const previous=saved.submissions.find(s => s.form_id === formId);
      if(previous) {
        const put=(node,name,value) => {const field=node.querySelector(`[name="${name}"]`);if(field) field.value=value ?? "";};
        put(dialog,"source_type",previous.source_type);put(dialog,"reviewer_id",previous.reviewer_id);
        for(const [name] of metadataFields) put(dialog,"meta_"+name,Array.isArray(previous.metadata[name]) ? previous.metadata[name].join(";") : previous.metadata[name]);
        for(const node of dialog.querySelectorAll('[data-answer-item]')) {
          const answer=saved.answers.find(a => a.submission_id === previous.id && a.item_key === node.dataset.answerItem);
          if(!answer) continue;
          put(node,"score",answer.state === "scored" ? String(answer.score) : answer.state === "not_observed" ? "N/O" : "");
          put(node,"fair_opportunity",answer.fair_opportunity === null ? "" : answer.fair_opportunity ? "yes" : "no");
          put(node,"confidence",answer.confidence);put(node,"narrative",answer.narrative);put(node,"missing_reason",answer.missing_reason);put(node,"component",answer.component);
          put(node,"evidence",JSON.stringify(saved.evidence.filter(w => w.answer_id === answer.id).map(w => ({kind:w.kind,start_s:w.start_s,end_s:w.end_s,context:w.context,response:w.response,participation_effect:w.participation_effect,evidence_id:w.evidence_id}))));
        }
        for(const flag of saved.context_history.annotation_context_flags.filter(r => r.submission_id === previous.id)) {put(dialog,"flag_"+flag.name,flag.present === null ? "" : flag.present ? "yes" : "no");put(dialog,"flag_note_"+flag.name,flag.notes);}
        for(const pattern of saved.context_history.annotation_pattern_summaries.filter(r => r.submission_id === previous.id)) {
          put(dialog,"pattern_"+pattern.name,pattern.category);put(dialog,"pattern_confidence_"+pattern.name,pattern.confidence);put(dialog,"pattern_narrative_"+pattern.name,pattern.narrative);
        }
        const validityNames={fair_opportunity:"validity_opportunity",speaker_identity:"speaker_identity",recording_support:"recording_support",context_effect:"context_effect"};
        for(const check of saved.context_history.annotation_validity_checks.filter(r => r.submission_id === previous.id)) {put(dialog,validityNames[check.name],check.category);put(dialog,"validity_explanation_"+check.name,check.explanation);}
      }
      dialog.querySelector('[name="source_type"]').addEventListener('change',event => {
        if(!previous || event.target.value === previous.source_type) return;
        for(const node of dialog.querySelectorAll('[data-answer-item]')) for(const field of node.querySelectorAll('input,select,textarea')) field.value="";
        dialog.querySelector('[name="reviewer_id"]').value="";
        notice("Starting a separate human source clears the previous reviewer's answers.");
      });
      dialog.querySelector('[name="form_id"]').addEventListener("change", e => draw(e.target.value));
    }
    draw("at-4.0"); dialog.showModal();
  }

  function showPreview(result) {
    const node = document.querySelector("#import-preview");
    if (result.needs_worksheet) { node.innerHTML = `<p>Select one of these worksheets and preview again: ${esc(result.worksheets.join(", "))}</p>`; return; }
    node.innerHTML = `<h3>Answer preview</h3><p>${result.rows.length} normalized answers · ${result.errors.length} errors${result.duplicate ? " · duplicate source" : ""}</p><details><summary>Map columns explicitly</summary><form data-workflow="remap"><div class="form-grid">${result.headers.map(h => select(h, h, [[h, `Keep ${h}`], ...["participant","item","score","fair_opportunity","confidence","reviewer_id","narrative","evidence","metadata","validity","context_flags","patterns","source_type","component","missing_reason",...metadataFields.map(([name]) => name),"session_id","participant_code","observer_code","reviewer_code","reviewed_at",...contextFlags,"ignore"].filter(k => k !== h)])).join("")}</div><button>Preview mapped columns</button></form></details>${result.errors.map(e => `<p class="error">Row ${e.row}: ${esc(e.error)}</p>`).join("")}<div class="table-wrap"><table><thead><tr><th>Participant</th><th>Item</th><th>Answer</th><th>Reviewer</th><th>Current revision</th><th>Opportunity / confidence</th><th>Evidence and retained context</th></tr></thead><tbody>${result.rows.slice(0,200).map(r => `<tr><td>${esc(r.participant_code)}</td><td>${esc(r.item_key)}</td><td>${r.state === "scored" ? r.score : r.state === "not_observed" ? "N/O" : "Missing"}</td><td>${esc(r.reviewer_id || "Not recorded")}</td><td>${r.expected_revision}</td><td>${r.fair_opportunity === null ? "Unknown" : r.fair_opportunity ? "Yes" : "No"} / ${r.confidence ?? "Not recorded"}</td><td>${diagnostic({windows:r.evidence,metadata:r.metadata,validity:r.validity,flags:r.context_flags,patterns:r.patterns})}</td></tr>`).join("")}</tbody></table></div><p>Showing up to 200 preview rows. Saving stores every valid row atomically. It does not grant training eligibility.</p><form data-workflow="commit" data-import="${esc(result.import_id)}" data-sid="${esc(selectedSession)}"><label>Correction reason<textarea name="correction_reason"></textarea></label><button class="primary" ${result.errors.length ? "disabled" : ""}>Confirm and save answers</button></form>`;
  }

  document.addEventListener("click", async e => {
    const target = e.target.closest("button"); if (!target) return;
    try {
      if (target.hasAttribute("data-remove-review-turn")) target.closest("[data-review-turn]").remove();
      if (target.hasAttribute("data-add-review-turn")) target.closest("form").querySelector("[data-reviewed-turns]").insertAdjacentHTML("beforeend",reviewTurnRow({}));
      if (target.dataset.answersOpen) await answerEditor(target.dataset.sid,target.dataset.answersOpen);
      if (target.dataset.trainSnapshot) { target.disabled = true; await api("/training/runs", {method:"POST",body:JSON.stringify({snapshot_id:target.dataset.trainSnapshot})}); notice("Training queued in PostgreSQL. The Docker trainer or local trainer will fit this frozen dataset; activation remains a separate decision."); await render(); }
      if (target.dataset.cancelJob) { await api(`/jobs/${target.dataset.cancelJob}/cancel`,{method:"POST",body:"{}"}); await render(); }
    } catch (error) { target.disabled = false; notice(error.message,true); }
  });
  document.addEventListener("change", async e => {
    if (e.target.id === "training-family") { family=e.target.value; render(); }
    if (e.target.name === "prediction_session") {
      const form=e.target.closest("form"),button=form.querySelector("button"),speaker=form.querySelector('[name="speaker_id"]');
      const enabled=!button.disabled; button.disabled=true; speaker.disabled=true;
      try {
        const options=predictionSpeakers.filter(s => s.session_id === e.target.value);
        speaker.innerHTML=options.map(s => `<option value="${esc(s.id)}">${esc(s.display_name)}</option>`).join("");
        button.disabled=!enabled || !options.length;
      } catch(error) { notice(error.message,true); } finally { speaker.disabled=false; }
    }
  });
  document.addEventListener("submit", async e => {
    const form=e.target; if (!form.dataset.workflow) return;
    e.preventDefault(); const action=form.dataset.workflow, values=Object.fromEntries(new FormData(form)), sid=form.dataset.sid, pid=form.dataset.pid;
    const button=form.querySelector('button[type="submit"], button:not([type])'); if (button) button.disabled=true;
    try {
      let path, body=values;
      if (action === "reanalysis") {
        path=`/sessions/${sid}/reanalysis`;
        body={reviewer_id:values.reviewer_id,reason:values.reason,max_speakers:Number(values.max_speakers),reviewed_turns:values.use_reviewed_turns === "on" ? [...form.querySelectorAll("[data-review-turn]")].map(row => ({speaker:row.querySelector('[name="cluster_label"]').value,start:Number(row.querySelector('[name="turn_start"]').value),end:Number(row.querySelector('[name="turn_end"]').value)})) : []};
      }
      if (action === "source-review") path=`/sessions/${sid}/source-reviews`;
      if (action === "participant") path=`/sessions/${sid}/participants`;
      if (action === "person") path="/people";
      if (action === "mapping") path=`/sessions/${sid}/participants/${pid}/mapping`;
      if (action === "consent") { path=`/sessions/${sid}/participants/${pid}/consent`; body.training_allowed=values.training_allowed === "true"; }
      if (action === "withdraw") path=`/sessions/${sid}/participants/${pid}/withdraw`;
      if (action === "adjudicate") {path=`/answers/${form.dataset.answer}/adjudicate`;body.score=Number(values.score);}
      if (action === "review") path=`/submissions/${form.dataset.submission}/review`;
      if (action === "freeze") { path="/training/snapshots"; body={family,seed:Number(values.seed),study:values.study}; }
      if (action === "deploy") { path=`/models/${form.dataset.model}/${values.action}`; body.acknowledge_exploratory=values.acknowledge_exploratory === "on"; }
      if (action === "commit") { path=`/sessions/${sid}/answers/commit`; body={import_id:form.dataset.import,correction_reason:values.correction_reason,durable:true}; }
      if (action === "entry") {
        const validity={}; for (const [key,name] of [["speaker_identity","speaker_identity"],["recording_support","recording_support"],["fair_opportunity","validity_opportunity"],["context_effect","context_effect"]]) if(values[name]) validity[key]={category:values[name],explanation:values["validity_explanation_"+key]};
        const metadata=JSON.parse(values.metadata || "{}"),flags=JSON.parse(values.context_flags || "{}"),patterns=JSON.parse(values.patterns || "{}");
          for(const [name] of metadataFields) {
            const value=values["meta_"+name];if(!value) continue;
            metadata[name]=name === "languages" ? value.split(";").map(v => v.trim()).filter(Boolean) : ["observation_minutes","recording_quality"].includes(name) ? Number(value) : value;
          }
          for(const name of contextFlags) if(values["flag_"+name]) flags[name]={present:values["flag_"+name] === "yes",notes:values["flag_note_"+name]};
          for(const name of patternNames) if(values["pattern_"+name]) patterns[name]={category:values["pattern_"+name],confidence:Number(values["pattern_confidence_"+name]),narrative:values["pattern_narrative_"+name]};
          const rows=[...form.querySelectorAll("[data-answer-item]")].map(row => { const get=name => row.querySelector(`[name="${name}"]`).value; const evidence=JSON.parse(get("evidence") || "[]"); for(const kind of ["event","response","same_session_baseline","second_support"]) {
            const start=get(kind+"_start"),end=get(kind+"_end");
            if(Boolean(start)!==Boolean(end)) throw new Error("Enter both bounds for each evidence window.");
            if(start && end) evidence.push({kind:kind === "second_support" ? "support" : kind,start_s:Number(start),end_s:Number(end),context:get(kind+"_context")});
          }
          if(Boolean(get("start_s"))!==Boolean(get("end_s"))) throw new Error("Enter both bounds for the supporting window.");
          if(get("start_s") !== "" && get("end_s") !== "") evidence.push({kind:"support",start_s:Number(get("start_s")),end_s:Number(get("end_s")),context:get("narrative")}); return {item:row.dataset.answerItem,score:get("score"),fair_opportunity:get("fair_opportunity"),confidence:get("confidence"),narrative:get("narrative"),missing_reason:get("missing_reason"),component:get("component"),evidence,validity,metadata,context_flags:flags,patterns}; });
        path=`/sessions/${sid}/participants/${pid}/answers`; body={rows,form_id:values.form_id,source_type:values.source_type,reviewer_id:values.reviewer_id,correction_reason:values.correction_reason};
      }
      if (action === "preview" || action === "remap") {
        if (action === "preview") {
          const codes=[...form.querySelectorAll("[data-file-participant]")].map(i => i.value.trim()).filter(Boolean);
          if(new Set(codes).size !== codes.length) throw new Error("Each file code must match exactly one session participant.");
          pendingFile=form.querySelector('[name="answers"]').files[0]; pendingOptions={form_id:values.form_id,source_type:values.source_type,reviewer_id:values.reviewer_id,participant_id:pid || null,worksheet:values.worksheet || null,participants:pid ? {} : Object.fromEntries([...form.querySelectorAll("[data-file-participant]")].filter(i => i.value.trim()).map(i => [i.value.trim(),i.dataset.fileParticipant]))}; }
        else pendingOptions.columns=values;
        const data=new FormData(); data.append("answers",pendingFile); data.append("options",JSON.stringify(pendingOptions));
        const result=await api(`/sessions/${sid || selectedSession}/answers/preview`,{method:"POST",body:data}); showPreview(result); return;
      }
      if (action === "attachment") {
        const data=new FormData();data.append("attachment",form.querySelector('[name="attachment"]').files[0]);
        await api(`/submissions/${form.dataset.submission}/attachments`,{method:"POST",body:data});
        notice("Scanned source retained. Its contents are not automatically treated as answers.");await render();return;
      }
      if (action === "predict") {
        const context_windows={};
        if(values.context_target) {
          const windows=[];
          for(const kind of ["event","response","same_session_baseline"]) {
            const start=values[kind+"_start"],end=values[kind+"_end"];
            if(Boolean(start)!==Boolean(end)) throw new Error("Enter both bounds for each inference context window.");
            if(start && end) windows.push({kind,start_s:Number(start),end_s:Number(end),context:values[kind+"_context"],reviewer_id:values.context_reviewer});
          }
          context_windows[values.context_target]=windows;
        }
        const result=await api(`/speakers/${values.speaker_id}/predict`,{method:"POST",body:JSON.stringify({context_windows})});
        document.querySelector("#prediction-results").innerHTML=`<p>${esc(result.status)}</p>${result.predictions.map(p => `<div class="trait-row"><div><h3>${esc(p.family)} / ${esc(p.target)}: ${p.abstention ? "Abstained" : `Predicted score ${p.score}`}</h3><small>${esc(p.evaluation_status)} / model version ${esc(p.model_id)}</small><p>${esc(p.abstention || "Supervised prediction, separate from human answers")}</p>${diagnostic(p)}</div></div>`).join("")}`; return;
      }
      if (path) { const result=await api(path,{method:"POST",body:JSON.stringify(body)});
        if(action === "commit") {
          notice("Save queued. A worker will commit the entire validated import atomically.");
          const jobId=result.id;
          async function checkImport() {
            try {
              const state=await api(`/jobs/${jobId}`);
              if(state.status === "complete") {notice("Answers saved with source provenance and immutable revisions.");await render();}
              else if(["failed","canceled"].includes(state.status)) notice(state.error || `Import ${state.status}`,true);
              else setTimeout(checkImport,3000);
            } catch(error) {notice(error.message,true);}
          }
          setTimeout(checkImport,1000);return;
        } if(action === "freeze") {notice("Reviewed dataset frozen with immutable label revisions and split assignments. Inspect its target readiness below, then start training.");await render();return;} if(action === "reanalysis") {location.hash=`sessions/${result.session_id}/overview`;notice("Separate analysis queued. Original evidence and answers remain available.");return;} if(action === "entry") document.querySelector("#answers-dialog").close(); notice("Saved. Human answers and revisions remain separate from predictions."); await render(); }
    } catch (error) { notice(error.message,true); } finally { if(button) button.disabled=false; }
  });
  function predictions(report) {
    return `<section class="panel session-pane" data-session-pane="measurements"><h2>Supervised predictions</h2><p>These estimates come from deliberately activated models. Human answers and measured indicators remain separate.</p>${report.supervised_predictions.length ? report.supervised_predictions.map(p => `<div class="trait-row"><div><h3>${esc(p.family)} / ${esc(p.target)}</h3><p>${p.abstention ? esc(p.abstention) : `Predicted score ${p.score} of 4`} / ${esc(p.evaluation_status)}</p><small>Model version ${esc(p.model_id)}</small>${diagnostic({uncertainty:p.uncertainty,distribution:p.distribution,lineage:p.lineage})}</div>${p.evidence_ids.length ? `<button data-evidence="${esc(JSON.stringify(p.evidence_ids))}">View evidence</button>` : ""}</div>`).join("") : '<p>No current trained predictions are available. The report still shows supported measurements, evidence, and personal comparisons.</p>'}</section>`;
  }
  return {participants,training:trainingView,predictions};
})();
