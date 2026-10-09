// Synthetic rendering fixtures never enter PSYCON's database or research results.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const context = {
  esc: value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c])),
  nice: String,
  number: value => value === null || value === undefined ? "Unavailable" : String(value),
  time: value => `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, "0")}`,
  runsTable: rows => `<table>${rows.length} retained attempts</table>`,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync("backend/static/instrument_reports.js", "utf8"), context);
const run = {
  id: "valid", condition: "C", status: "complete",
  input: {transcript: [{id: "source", start: 62, end: 65, text: "An exact test quote <script>"}]},
  output: {summary: "Fixture summary", limitations: ["Synthetic fixture"], claims: [{
    observation: "Fixture observation", inference: "Fixture inference", suggestion: "Fixture suggestion",
    limitation: "Fixture limitation", confidence: "low", evidence_ids: ["source"],
  }]},
};
context.api = async () => run;
const report = {speaker: {id: "speaker", display_name: "Test speaker"}, target_archetype: "Builder", llm_runs: [run]};

(async () => {
  const html = await context.speakerReportWorkspace(report);
  assert(html.includes("Talking patterns"));
  assert(html.includes("Marksheet observations and predictions"));
  assert(html.indexOf("Marksheet observations and predictions") < html.indexOf("Behavioral observation report"));
  assert(!html.match(/<div class="report-heading">[\s\S]*?<button/)[0].includes("comparison goal"));
  const fixture={...report,session_id:"synthetic-session",features:[{name:"words_per_minute",value:120,unit:"words/min",status:"measured",confidence:"moderate"}],supervised_predictions:[{family:"at",target:"A",score:3,model_id:"synthetic-model",evaluation_status:"exploratory"}],human_observations:[
    {item_key:"A",state:"scored",score:0,source_type:"observer",participant_code:"P01",reviewer_id:"R<script>",label_revision:1,review_status:"approved",confidence:3,fair_opportunity:true,description:"Source definition",narrative:"Human note<script>",evidence_windows:[{kind:"support",start:12,end:15,context:"Context"}]},
    {item_key:"B",state:"not_observed",source_type:"self_report",reviewer_id:"Self",label_revision:1,review_status:"needs_review"},
    {item_key:"C",state:"missing",source_type:"independent_review",reviewer_id:"Other",label_revision:1,review_status:"needs_review"},
  ]};
  const comparison=context.marksheetComparison(fixture);
  assert(comparison.includes("0 / 4") && comparison.includes("3 / 4") && comparison.includes("N/O") && comparison.includes("Missing answer"));
  assert(comparison.includes("Participant self-report") && comparison.includes("Independent observer rating"));
  assert(comparison.includes("R&lt;script&gt;") && comparison.includes("Human note&lt;script&gt;"));
  assert(comparison.includes('data-seek="12"') && comparison.includes('data-source="synthetic-session"'));
  assert(context.talkingPatterns(fixture).includes("120"));
  assert(html.includes("At a glance"));
  assert(html.includes("Fixture observation"));
  assert(html.includes("Fixture inference"));
  assert(html.includes("Fixture suggestion"));
  assert(html.includes('data-seek="62"'));
  assert(html.includes("An exact test quote &lt;script&gt;"));
  assert(html.includes("Report history and research details"));
  assert(!html.includes("Interpretation runs"));
  assert.equal(context.communicationReportContent({...run, status: "stale"}, "Speaker"), "");
  assert.equal(context.communicationReportContent({...run, status: "failed"}, "Speaker"), "");
  const empty = await context.speakerReportWorkspace({...report, llm_runs: []});
  assert(empty.includes("Create observation report"));
  assert(!empty.includes("At a glance"));
  const pending = await context.speakerReportWorkspace({...report, llm_runs: [{condition: "C", status: "running"}]});
  assert(pending.includes('disabled aria-busy="true"'));
  assert(pending.includes("Writing your observation report"));
  const updating = await context.speakerReportWorkspace({...report, llm_runs: [{condition: "C", status: "queued"}, run]});
  assert(updating.includes("previous report stays available"));
  assert(updating.includes("Fixture summary"));
  const failed = await context.speakerReportWorkspace({...report, llm_runs: [{condition: "C", status: "failed", error: "Unavailable <script>"}]});
  assert(failed.includes("Try again"));
  assert(failed.includes("Unavailable &lt;script&gt;"));
  const stale = await context.speakerReportWorkspace({...report, llm_runs: [{...run, status: "stale"}]});
  assert(stale.includes("Create a new report"));
  assert(!stale.includes("Fixture summary"));
  const comparisons = await context.speakerReportWorkspace({...report, llm_runs: [{...run, condition: "A"}]});
  assert(!comparisons.includes("Fixture summary"));
  context.api = async () => { throw new Error("network failure"); };
  const unavailable = await context.speakerReportWorkspace(report);
  assert(unavailable.includes("saved report could not be loaded"));
  assert(!unavailable.includes("Fixture summary"));
  console.log("Report rendering: evidence links, escaping, selection, queued/updating/failed/stale/empty/unavailable states passed.");
})().catch(error => { console.error(error); process.exitCode = 1; });
