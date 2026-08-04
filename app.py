"""
Living Tavern web layer (Spec §7).
==================================

FastAPI app mapping session_id -> LivingTavern instance. The pure core
and Living-Tavern layer need no changes here; this file only manages the
mapping and rendering.

Session rules (Spec §2, non-negotiable):
  * First page load  -> new clean seed, new session id (kept in JS memory,
    NOT persisted, so a full refresh discards it and re-seeds).
  * /chat and /tick carry the session id and reuse the same instance.
  * Different visitors never share formal state.
  * /reset returns the same id to the clean seed explicitly.

Run:  uvicorn app:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from living_tavern import SessionStore
from verbalizer import make_verbalizer

app = FastAPI(title="Living Tavern")
store = SessionStore(ttl_seconds=3600, max_sessions=500)
verbalizer = make_verbalizer()


class ChatIn(BaseModel):
    session_id: str
    text: str


class SessionIn(BaseModel):
    session_id: str


def _respond(tavern, packets):
    dicts = [p.as_dict() for p in packets]
    state = tavern.state()
    return {
        "lines": verbalizer.render(dicts, state),
        "packets": dicts,
        "state": state,
    }


@app.post("/session")
def new_session():
    sid, tavern = store.new_session()
    # Arrival: the room is already alive — run one ambient round so the
    # visitor walks into NPCs mid-relationship (Success criterion 1).
    packets = tavern.step_ambient()
    out = _respond(tavern, packets)
    out["session_id"] = sid
    return out


@app.post("/chat")
def chat(msg: ChatIn):
    tavern = store.get(msg.session_id)
    if tavern is None:
        raise HTTPException(410, "session expired — refresh for a clean seed")
    text = msg.text.strip()
    if not text:
        raise HTTPException(422, "empty message")
    packets = tavern.step_user(text[:2000])
    return _respond(tavern, packets)


@app.post("/tick")
def tick(msg: SessionIn):
    tavern = store.get(msg.session_id)
    if tavern is None:
        raise HTTPException(410, "session expired — refresh for a clean seed")
    packets = tavern.step_ambient()
    return _respond(tavern, packets)


@app.post("/reset")
def reset(msg: SessionIn):
    tavern = store.reset(msg.session_id)
    packets = tavern.step_ambient()
    return _respond(tavern, packets)


@app.get("/state/{session_id}")
def state(session_id: str):
    tavern = store.get(session_id)
    if tavern is None:
        raise HTTPException(410, "session expired")
    return tavern.state()


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Living Tavern</title>
<style>
  body{font-family:Georgia,serif;background:#1b1410;color:#e8dcc8;
       max-width:760px;margin:0 auto;padding:16px}
  h1{font-size:1.3em;color:#d9a441;margin:8px 0}
  #log{height:60vh;overflow-y:auto;background:#241a13;border:1px solid #3a2c1f;
       border-radius:8px;padding:12px;font-size:.95em;line-height:1.5}
  .npc b{color:#d9a441}.you b{color:#7fb27f}.sys{color:#8a7a66;font-style:italic}
  #bar{display:flex;gap:8px;margin-top:10px}
  #msg{flex:1;padding:10px;border-radius:6px;border:1px solid #3a2c1f;
       background:#2b2016;color:#e8dcc8;font-size:1em}
  button{padding:10px 14px;border-radius:6px;border:0;background:#d9a441;
         color:#1b1410;font-weight:bold;cursor:pointer}
  #meters{font-size:.8em;color:#8a7a66;margin-top:6px}
</style></head><body>
<h1>The Living Tavern</h1>
<div id="log"></div>
<div id="bar">
  <input id="msg" placeholder="Speak or act… (e.g. ‘Any tales tonight?’)"
         autocomplete="off">
  <button onclick="send()">Send</button>
  <button onclick="doReset()" title="Return to the clean seed">Reset</button>
</div>
<div id="meters"></div>
<script>
let SID=null;                       // in-memory only: refresh => clean seed
const log=document.getElementById('log'),
      meters=document.getElementById('meters'),
      msg=document.getElementById('msg');
function add(cls,who,text){
  const d=document.createElement('div');d.className=cls;
  d.innerHTML=(who?('<b>'+who+':</b> '):'')+text;
  log.appendChild(d);log.scrollTop=log.scrollHeight;}
function show(r){
  (r.lines||[]).forEach(l=>add('npc',l.speaker,l.line));
  const s=r.state;
  meters.textContent='threat '+s.user_threat+' · pressure '+s.pressure+
    ' · mood '+s.room_mood+' · events '+s.events_processed;}
async function post(url,body){
  const r=await fetch(url,{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body||{})});
  if(!r.ok)throw new Error(await r.text());return r.json();}
async function boot(){
  const r=await post('/session');SID=r.session_id;
  add('sys','','You push open the door. The room is already mid-conversation…');
  show(r);}
async function send(){
  const t=msg.value.trim();if(!t||!SID)return;msg.value='';
  add('you','You',t);
  try{show(await post('/chat',{session_id:SID,text:t}));}
  catch(e){add('sys','','('+e.message+')');}}
async function doReset(){
  log.innerHTML='';add('sys','','The room resets to its clean seed.');
  try{show(await post('/reset',{session_id:SID}));}
  catch(e){add('sys','','('+e.message+')');}}
msg.addEventListener('keydown',e=>{if(e.key==='Enter')send();});
setInterval(async()=>{                 // ambient life every 25s
  if(!SID)return;
  try{show(await post('/tick',{session_id:SID}));}catch(e){}},25000);
boot();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML
