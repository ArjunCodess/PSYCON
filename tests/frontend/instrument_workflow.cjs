// Synthetic fixtures verify user-visible training gates without writing application data.
const assert=require("node:assert/strict"), fs=require("node:fs"), vm=require("node:vm");
const context={esc:v=>String(v??"").replaceAll("<","&lt;"),number:String,time:String,empty:()=>"",document:{addEventListener(){}},setTimeout:()=>1,clearTimeout(){},location:{hash:"#training"}};
const split=(records,groups)=>({records,groups,classes:[0,4]});
const target={can_fit:true,reasons:[],splits:{train:split(12,12),validation:split(3,3),test:split(3,3)}};
const snapshot=(id,can_fit)=>({id,task_id:"at",created_at:"2026-10-09",manifest:{counts:{examples:18,groups:18}},readiness:{status:can_fit?"Ready to fit":"Insufficient training data",can_fit,targets:can_fit?{I:target}:{}}});
let data={snapshots:[snapshot("ready",true),snapshot("empty",false),snapshot("invalid",true)],invalidations:[{snapshot_id:"invalid"}],runs:[],events:[],models:[],evaluations:[],prediction_speakers:[{id:"speaker",session_id:"session",filename:"<synthetic>",recorded_at:"2026-10-09"}]};
let readiness={status:"Insufficient data",rows:[]};
context.api=async path=>path==="/training"?data:path.includes("agreement")?{pairs:[],status:"Unavailable"}:readiness;
vm.createContext(context);vm.runInContext(fs.readFileSync("backend/static/instrument_workflow.js","utf8"),context);
(async()=>{
 let html=await vm.runInContext("PSYCONWorkflow.training()",context);
 assert.match(html,/data-train-snapshot="ready" >Start training/);
 assert.match(html,/data-train-snapshot="empty" disabled/);
 assert.match(html,/data-train-snapshot="invalid" disabled/);
 assert.match(html,/<button disabled>Freeze reviewed dataset/);
 assert.match(html,/12 \/ 12/);assert.match(html,/3 \/ 3/);
 assert.match(html,/&lt;synthetic>/);assert(!html.includes('name="speaker_id" value='));
 assert.match(html,/<button disabled>Predict with active models/);
 readiness={status:"Eligible",rows:[{eligible:true,session_id:"session",participant_code:"P",target:"I",reasons:[]}]};
 data.models=[{id:"model",family:"at",target:"I",status:"active",evaluation_status:"exploratory",limitations:["Synthetic only"],manifest:{}}];
 html=await vm.runInContext("PSYCONWorkflow.training()",context);
 assert.match(html,/<button >Freeze reviewed dataset/);assert.match(html,/<button >Predict with active models/);
 assert.match(html,/Exploratory model/);assert.match(html,/Held-out evaluation unavailable/);
 console.log("Training interface: frozen split counts, fit/invalidation gates, empty data, model status and speaker choices passed.");
})().catch(error=>{console.error(error);process.exitCode=1;});
