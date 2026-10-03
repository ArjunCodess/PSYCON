"use strict";
let token = "";
let owner = false;
const el = id => document.getElementById(id);
const message = text => { el("message").textContent = text; };
async function api(path, method="GET", body) {
  const options={method,headers:{Authorization:`Bearer ${token}`}};
  if(body instanceof FormData) options.body=body;
  else if(body!==undefined){options.headers["Content-Type"]="application/json";options.body=JSON.stringify(body);}
  const response=await fetch(`/api/v1/communication${path}`,options);
  if(response.status===204)return null;
  const data=await response.json();
  if(!response.ok)throw new Error(data.error?.message||"Request failed");
  return data;
}
function node(tag,text,parent){const n=document.createElement(tag);n.textContent=text;if(parent)parent.append(n);return n;}
function action(parent,text,fn){const b=node("button",text,parent);b.type="button";b.addEventListener("click",()=>run(fn));}
async function run(fn){try{await fn();}catch(error){message(error.message);}}
function bind(id,fn){el(id).addEventListener("submit",event=>{event.preventDefault();run(fn);});}
function signout(){token="";el("token").value="";el("workspace").hidden=true;el("account").textContent="";for(const id of ["history","conversations","goals","grants","grant-token"])el(id).replaceChildren();}
async function refresh(){
  const profile=await api("/me");owner=profile.access_scope==="owner";el("account").textContent=`${profile.label} · ${profile.enrolled?"Voice enrolled":`Enrollment: ${profile.enrollment_status||"needed"}`}`;el("role").value=profile.role;el("consent").checked=profile.consent;
  for(const id of ["profile","enroll","upload","goal","grant"])el(id).hidden=!owner;
  el("delete-profile").hidden=!owner;el("remove-enrollment").hidden=!owner;el("export").hidden=!owner;
  const history=await api("/history");const target=el("history");target.replaceChildren();node("p",`Coaching focus: ${history.focus.join(", ")}`,target);
  if(!history.baselines.length)node("p","Upload eligible conversations to start building your baseline.",target);
  for(const b of history.baselines){const r=b.current.requirements;node("p",`${b.cohort.join(" / ")}: ${b.current.state}. ${b.current.conversations}/${r.conversations} conversations, ${b.current.days}/${r.days} days, ${Math.round(b.current.usable_speech_s/60)}/${Math.round(r.usable_speech_s/60)} minutes of usable speech.`,target);}
  if(!history.patterns.length)node("p","No supported recurring changes yet. A single event does not establish a pattern.",target);
  for(const pattern of history.patterns){const card=node("article","",target);node("h3",pattern.observation,card);node("p",`Possible effect: ${pattern.possible_effect}`,card);node("p",pattern.suggested_adjustment,card);node("small",pattern.uncertainty,card);const d=node("details","",card);node("summary","Review supporting evidence",d);for(const e of pattern.evidence){node("p",`${e.occurred_at}: measured ${e.value.toFixed(2)}; baseline median ${pattern.baseline.median.toFixed(2)}.`,d);for(const i of e.intervals)node("p",`${i.start_s.toFixed(1)}–${i.end_s.toFixed(1)} seconds: ${i.excerpt||"Timing evidence; transcript unavailable."}`,d);}}
  const conversations=await api("/conversations");el("conversations").replaceChildren();
  for(const c of conversations.conversations){const card=node("article","",el("conversations"));node("h3",`${c.occurred_at} · ${c.state}`,card);node("p",`${c.context.conversation_type} / ${c.context.setting} / ${c.context.microphone}`,card);node("small",`Identity: ${c.analysis.identity||"pending"}. Semantic interpretation: ${c.analysis.semantic_status||"pending"}. Raw audio: ${c.raw_state}.`,card);if(c.error)node("p",`Processing failed: ${c.error}`,card);for(const e of c.analysis.evidence||[])node("p",`${e.id}: ${e.start_s.toFixed(1)}–${e.end_s.toFixed(1)} seconds: ${e.excerpt||"Timing evidence only"}`,card);
    if(c.analysis.metrics){const d=node("details","",card);node("summary","Measured session observations",d);for(const [key,value] of Object.entries(c.analysis.metrics))node("p",`${key.replaceAll("_"," ")}: ${Number(value).toFixed(2)}`,d);for(const overlap of c.analysis.overlap_events||[])node("p",`Measured overlap ${overlap.start_s.toFixed(1)}–${overlap.end_s.toFixed(1)} seconds; intent is unknown.`,d);}
    const corrected=Object.hasOwn(c.analysis,"human_events");
    const events=corrected?(c.analysis.human_events||[]).map(e=>({...e,evidence_ids:[e.evidence_id]})):(c.analysis.events||[]);
    for(const event of events){const d=node("details","",card);node("summary",`${corrected?"Wearer correction":"Validated local interpretation"}: ${event.type}`,d);for(const id of event.evidence_ids){const evidence=(c.analysis.evidence||[]).find(e=>e.id===id);if(evidence)node("p",`${id}: ${evidence.start_s.toFixed(1)}–${evidence.end_s.toFixed(1)} seconds: ${evidence.excerpt||"Timing evidence only"}`,d);}}
    const comparison=(history.comparisons||[]).find(row=>row.conversation_id===c.id);
    if(comparison){const d=node("details","",card);node("summary","Compare with your earlier baseline",d);for(const [key,value] of Object.entries(comparison.metrics))node("p",`${key.replaceAll("_"," ")}: ${value.value.toFixed(2)}, earlier median ${value.baseline_median.toFixed(2)}, change ${value.delta.toFixed(2)}.`,d);node("small",comparison.uncertainty,d);}
    if(owner&&c.state==="complete"){action(card,"Correct context",async()=>{const answer=prompt("Edit conversation context as JSON",JSON.stringify(c.context,null,2));if(answer!==null){await api(`/conversations/${c.id}`,"PATCH",{context:JSON.parse(answer)});await refresh();}});action(card,"Add or correct observed events",async()=>{const answer=prompt('Enter events as JSON, for example [{"type":"acknowledgement","evidence_id":"e0"}]',JSON.stringify(c.analysis.human_events||[]));if(answer!==null){await api(`/conversations/${c.id}`,"PATCH",{events:JSON.parse(answer)});await refresh();}});}
    if(owner&&c.state==="failed"&&c.raw_state!=="deleted")action(card,"Retry analysis",async()=>{await api(`/conversations/${c.id}/retry`,"POST");await refresh();});
    if(owner)action(card,"Delete conversation",async()=>{if(confirm("Delete this conversation and its dependent observations?")){await api(`/conversations/${c.id}`,"DELETE");await refresh();}});
  }
  const goals=await api("/goals");el("goals").replaceChildren();for(const g of goals.goals){const card=node("article",`${g.direction} ${g.metric.replaceAll("_"," ")} · ${g.state}`,el("goals"));for(const c of g.comparisons)node("p",`Baseline ${c.baseline_median.toFixed(2)}; later median ${c.later_median.toFixed(2)} over ${c.conversations} conversations. ${c.interpretation}`,card);}
  const grants=owner?await api("/grants"):{grants:[]};el("grants").replaceChildren();for(const g of grants.grants){const card=node("article",`${g.scope}: ${g.revoked?"revoked":`expires ${g.expires_at}`}`,el("grants"));if(!g.revoked)action(card,"Revoke",async()=>{await api(`/grants/${g.id}`,"DELETE");await refresh();});}
  message("History updated.");
}
bind("login",async()=>{token=el("token").value.trim();await refresh();el("token").value="";el("workspace").hidden=false;});
el("logout").addEventListener("click",signout);
bind("profile",async()=>{await api("/me","PATCH",{role:el("role").value,consent:el("consent").checked});await refresh();});
bind("enroll",async()=>{const form=new FormData();for(const file of el("clips").files)form.append("clips",file);form.append("consent",el("enrollment-consent").checked?"yes":"no");message("Enrolling locally…");await api("/me/enrollment","POST",form);el("clips").value="";await refresh();});
el("remove-enrollment").addEventListener("click",()=>run(async()=>{await api("/me/enrollment","DELETE");await refresh();}));
bind("upload",async()=>{const form=new FormData();form.append("audio",el("audio").files[0]);const context={};for(const key of ["language","conversation_type","microphone","setting","topic","counterpart_relationship","objective"])context[key]=el(key).value;form.append("context",JSON.stringify(context));form.append("occurred_at",new Date(el("occurred").value).toISOString());await api("/conversations","POST",form);el("audio").value="";await refresh();message("Queued for local analysis. Refresh to see processing results.");});
el("refresh").addEventListener("click",()=>run(refresh));
bind("goal",async()=>{await api("/goals","POST",{metric:el("metric").value,direction:el("direction").value});await refresh();});
bind("grant",async()=>{const grant=await api("/grants","POST",{scope:el("scope").value});await refresh();el("grant-token").textContent=`Save this grant token: ${grant.token}`;});
el("export").addEventListener("click",()=>run(async()=>{const data=await api("/context");const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));const link=document.createElement("a");link.href=url;link.download="psycon-context.json";link.click();URL.revokeObjectURL(url);}));
el("delete-profile").addEventListener("click",()=>run(async()=>{if(confirm("Delete your entire personal history and revoke all access?")){await api("/me","DELETE");signout();message("Profile revoked. Personal history deleted; any failed raw cleanup will be retried by the worker.");}}));
