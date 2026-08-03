"""
Ye Olde Tavern — Complete runnable backend + frontend
Pure kernel + non-causal Grok verbalizer.

Run: uvicorn main:app --reload --port 8000
Requires: GROK_API_KEY environment variable (or set below for testing).
"""

from __future__ import annotations
import os
import json
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from tavern_kernel import TavernSettlement, IntentionPacket

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GROK_API_KEY = os.getenv("GROK_API_KEY", "")  # set this
GROK_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-3"  # or the current available model

# ---------------------------------------------------------------------------
# App + single shared tavern instance (for single-user / sequential play)
# ---------------------------------------------------------------------------
app = FastAPI(title="Ye Olde Tavern")
tavern = TavernSettlement()

# ---------------------------------------------------------------------------
# Grok verbalizer (non-causal overlay)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a pure non-causal verbalizer for the Living Knot Ye Olde Tavern.
You receive only formal intention packets produced by the deterministic kernel.
Your sole job is to turn those packets into short, atmospheric chat lines.

STRICT RULES:
1. Output ONLY lines in one of these exact formats:
   Name: dialogue text here
   or
   *Name does a short action description*
2. Use only the agents and intentions supplied in the packets.
3. Do not invent new events, decisions, outcomes, agents, or world facts.
4. Do not add narrator text, scene descriptions, or anything outside the lines.
5. Keep every line short (one sentence max).
6. Match the tone lightly to the formal_reason and content_hint given for each packet.
7. If multiple packets are given, output one line per packet in priority order.
8. Output nothing else. No preamble, no explanation, no markdown."""

async def verbalize(packets: list[IntentionPacket], user_text: str, recent_log: list) -> str:
    if not GROK_API_KEY:
        # Fallback for testing without key: return formal intentions as plain text
        lines = []
        for p in packets[:6]:
            lines.append(f"{p.agent}: [{p.intention_type.value}] {p.content_hint} ({p.formal_reason})")
        return "\n".join(lines)

    packets_json = [
        {
            "agent": p.agent,
            "intention_type": p.intention_type.value,
            "target": p.target,
            "priority": round(p.priority, 2),
            "formal_reason": p.formal_reason,
            "content_hint": p.content_hint,
        }
        for p in packets[:6]  # limit to strongest
    ]

    user_content = f"""Formal intention packets:
{json.dumps(packets_json, indent=2)}

Recent formal log (last few events only):
{json.dumps(recent_log[-3:], indent=2) if recent_log else "[]"}

User just said: "{user_text}"

Produce the chat lines now."""

    payload = {
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.7,
        "max_tokens": 400,
    }

    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(GROK_API_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    user_name: str = "Traveler"

@app.post("/chat")
async def chat(req: ChatRequest):
    if not req.message.strip():
        return JSONResponse({"error": "empty message"}, status_code=400)

    packets = tavern.process_user_message(req.user_name, req.message)
    recent = tavern.event_log[-5:]
    try:
        text = await verbalize(packets, req.message, recent)
    except Exception as e:
        # On API failure still return formal intentions so the site is never dead
        text = "\n".join(
            f"{p.agent}: [{p.intention_type.value}] {p.content_hint}"
            for p in packets[:5]
        )
        text = f"[verbalizer offline — formal intentions]\n{text}\n\nError: {str(e)[:120]}"

    return {
        "reply": text,
        "tick": tavern.tick_count,
        "pressure": tavern.pressure,
        "agents_active": [p.agent for p in packets[:5]],
    }

@app.get("/state")
async def state():
    return tavern.get_state_summary()

# ---------------------------------------------------------------------------
# Single-page chat frontend (served at /)
# ---------------------------------------------------------------------------
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ye Olde Tavern</title>
<style>
  :root { --bg: #1a120b; --panel: #2a1f14; --ink: #e8d5b5; --accent: #c9a227; --muted: #8a7355; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--ink); font-family: "Georgia", "Times New Roman", serif; height: 100vh; display: flex; flex-direction: column; }
  header { background: var(--panel); padding: 12px 20px; border-bottom: 2px solid var(--accent); display: flex; justify-content: space-between; align-items: center; }
  header h1 { font-size: 1.4rem; letter-spacing: 0.05em; color: var(--accent); }
  header .status { font-size: 0.85rem; color: var(--muted); }
  #log { flex: 1; overflow-y: auto; padding: 16px 20px; line-height: 1.55; }
  .line { margin-bottom: 10px; white-space: pre-wrap; }
  .line.user { color: #a8c5d4; }
  .line.npc { color: var(--ink); }
  .line.system { color: var(--muted); font-style: italic; font-size: 0.9rem; }
  #input-area { background: var(--panel); padding: 12px 16px; border-top: 1px solid #3d2e1f; display: flex; gap: 10px; }
  #msg { flex: 1; background: #0f0b07; border: 1px solid #3d2e1f; color: var(--ink); padding: 10px 14px; font-family: inherit; font-size: 1rem; border-radius: 4px; }
  #msg:focus { outline: 1px solid var(--accent); }
  button { background: var(--accent); color: #1a120b; border: none; padding: 10px 18px; font-family: inherit; font-weight: bold; cursor: pointer; border-radius: 4px; }
  button:disabled { opacity: 0.5; cursor: wait; }
</style>
</head>
<body>
<header>
  <h1>Ye Olde Tavern</h1>
  <div class="status" id="status">tick 0 · mild pressure</div>
</header>
<div id="log">
  <div class="line system">You push open the heavy oak door. The tavern is already alive with low conversation and the smell of woodsmoke. A few regulars glance your way.</div>
</div>
<div id="input-area">
  <input id="msg" type="text" placeholder="Speak to the room..." autocomplete="off" autofocus>
  <button id="send">Say</button>
</div>
<script>
const log = document.getElementById('log');
const msg = document.getElementById('msg');
const sendBtn = document.getElementById('send');
const status = document.getElementById('status');

function addLine(text, cls) {
  const div = document.createElement('div');
  div.className = 'line ' + cls;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

async function send() {
  const text = msg.value.trim();
  if (!text) return;
  msg.value = '';
  sendBtn.disabled = true;
  addLine('You: ' + text, 'user');

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, user_name: 'Traveler'})
    });
    const data = await res.json();
    if (data.reply) {
      data.reply.split('\\n').forEach(line => {
        if (line.trim()) addLine(line.trim(), 'npc');
      });
    }
    if (data.tick !== undefined) {
      status.textContent = `tick ${data.tick} · pressure ${data.pressure.toFixed(2)}`;
    }
  } catch (e) {
    addLine('[connection error — try again]', 'system');
  }
  sendBtn.disabled = false;
  msg.focus();
}

sendBtn.onclick = send;
msg.onkeydown = e => { if (e.key === 'Enter') send(); };

// Opening autonomous beat
setTimeout(() => {
  addLine('Keep: The fire is burning. Speak if you have business.', 'npc');
  addLine('*Server wipes a mug and watches the door*', 'npc');
}, 800);
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
