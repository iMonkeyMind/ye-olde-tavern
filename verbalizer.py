"""
Non-causal verbalizer for the Living Tavern.
============================================

The verbalizer receives the priority-ordered IntentionPackets from the
formal layer and renders multi-voice chat lines. It NEVER:

  * invents outcomes,
  * erases or overrides residual / status,
  * feeds anything back into formal state.

Two implementations:

  * DeterministicVerbalizer — pure-template rendering from content hints.
    No dependencies, no network. Used as the always-available fallback and
    in tests (keeps the whole stack deterministic end to end).
  * GrokVerbalizer — drop-in adapter for the existing Grok pipeline. It
    builds a strictly-constrained prompt from the packets and returns the
    model's prose. If the HTTP client or API key is missing, callers
    should fall back to DeterministicVerbalizer (see `make_verbalizer`).
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

try:  # only needed for GrokVerbalizer
    import httpx  # type: ignore
except Exception:  # pragma: no cover - environment-dependent
    httpx = None


class DeterministicVerbalizer:
    """Renders packets to chat lines from their formal content hints only."""

    max_lines = 5

    _VERBS = {
        "speak": "says",
        "offer": "offers",
        "connect": "leans in",
        "structure": "notes",
        "observe": "watches",
        "mediate": "intercedes",
        "challenge": "confronts",
        "threaten": "warns, low and hard",
        "defend": "moves to block",
        "withdraw": "draws back",
        "action": "moves",
        "refuse": "refuses",
    }

    def render(self, packets: List[dict], state: dict) -> List[dict]:
        lines: List[dict] = []
        for p in packets[: self.max_lines]:
            verb = self._VERBS.get(p["intention_type"], "acts")
            tgt = f" (to {p['target']})" if p.get("target") else ""
            lines.append({
                "speaker": p["agent"],
                "line": f"*{p['content_hint']}.* {p['agent']} {verb}{tgt}.",
                "intention_type": p["intention_type"],
                "target": p.get("target"),
                "priority": p["priority"],
            })
        return lines


GROK_SYSTEM_PROMPT = """You are the verbalizer for a formal multi-agent \
tavern simulation. You receive intention packets (agent, intention_type, \
target, priority, content_hint) plus a state summary. Render them as a \
short multi-voice scene: one line of prose or dialogue per packet, in \
priority order, distinct voices per character.

Hard constraints (non-causal contract):
- Do NOT invent events, injuries, deaths, recoveries, or outcomes not in \
the packets.
- Do NOT contradict agent status (withdrawn/incapacitated agents do not \
speak or act beyond their packet).
- Do NOT soften or erase residual: if threat/pressure is high, the room \
stays tense.
- Each line must realize its packet's content_hint and intention_type.
Return JSON: {"lines": [{"speaker": str, "line": str}, ...]}."""


class GrokVerbalizer:
    """Adapter for the existing FastAPI + Grok pipeline (xAI API)."""

    def __init__(self, api_key: Optional[str] = None,
                 model: str = "grok-2-latest",
                 base_url: str = "https://api.x.ai/v1",
                 timeout: float = 20.0) -> None:
        if httpx is None:
            raise RuntimeError("httpx not installed")
        self.api_key = api_key or os.environ.get("XAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("XAI_API_KEY not set")
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self._fallback = DeterministicVerbalizer()

    def render(self, packets: List[dict], state: dict) -> List[dict]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": GROK_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(
                    {"packets": packets[:6], "state": state})},
            ],
            "temperature": 0.7,
        }
        try:
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload, timeout=self.timeout)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            data = json.loads(text)
            lines = data.get("lines", [])
            if not isinstance(lines, list) or not lines:
                raise ValueError("empty verbalization")
            return [{"speaker": str(l.get("speaker", "?")),
                     "line": str(l.get("line", ""))} for l in lines]
        except Exception:
            # Non-causal: a verbalizer failure must never stall the room.
            return self._fallback.render(packets, state)


def make_verbalizer():
    """Grok if configured, deterministic otherwise."""
    try:
        return GrokVerbalizer()
    except Exception:
        return DeterministicVerbalizer()
