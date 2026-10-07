// Synthetic rendering fixtures never enter PSYCON's database or research results.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const context = {
  esc: value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c])),
  nice: String,
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
  assert(empty.includes("Create communication report"));
  assert(!empty.includes("At a glance"));
  const pending = await context.speakerReportWorkspace({...report, llm_runs: [{condition: "C", status: "running"}]});
  assert(pending.includes('disabled aria-busy="true"'));
  assert(pending.includes("Writing your communication report"));
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
