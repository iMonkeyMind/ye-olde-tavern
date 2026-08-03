"""
Tavern Settlement v0.2 — Pure Deterministic Kernel
Upgraded intention layer for threat / violence / escalation reactivity.

Still pure formal. No LLM inside.
Intention packets remain the only output. Verbalization stays external.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import time
import uuid
import re


# ---------------------------------------------------------------------------
# Locked access properties by position number
# ---------------------------------------------------------------------------

POSITION_ACCESS = {
    1: {"bandwidth": 4, "conscious": True, "valued": True,  "accepting": True},
    2: {"bandwidth": 3, "conscious": True, "valued": True,  "accepting": False},
    3: {"bandwidth": 2, "conscious": True, "valued": False, "accepting": True},
    4: {"bandwidth": 1, "conscious": True, "valued": False, "accepting": False},
    5: {"bandwidth": 1, "conscious": False, "valued": True,  "accepting": True},
    6: {"bandwidth": 2, "conscious": False, "valued": True,  "accepting": False},
    7: {"bandwidth": 3, "conscious": False, "valued": False, "accepting": True},
    8: {"bandwidth": 4, "conscious": False, "valued": False, "accepting": False},
}


class IntentionType(str, Enum):
    SPEAK = "speak"
    ACTION = "action"
    OBSERVE = "observe"
    OFFER = "offer"
    CHALLENGE = "challenge"
    MEDIATE = "mediate"
    WITHDRAW = "withdraw"
    ADMIT = "admit"
    REFUSE = "refuse"
    DEFEND = "defend"
    ATTACK = "attack"
    ALARM = "alarm"
    FALL = "fall"          # incapacitated / dying


@dataclass
class DirectedHistory:
    timestamp: float
    other: str
    event: str
    trust_delta: float
    notes: str = ""


@dataclass
class IntentionPacket:
    agent: str
    intention_type: IntentionType
    target: Optional[str]
    priority: float
    formal_reason: str
    content_hint: str
    trust_delta: float = 0.0


@dataclass
class Agent:
    name: str
    tim: str
    position: int
    role: str
    history: List[DirectedHistory] = field(default_factory=list)
    trust: Dict[str, float] = field(default_factory=dict)
    last_intention: Optional[IntentionPacket] = None
    incapacitated: bool = False


# ---------------------------------------------------------------------------
# Threat detection helpers
# ---------------------------------------------------------------------------

VIOLENCE_WORDS = {
    "blade", "sword", "knife", "stab", "cut", "slash", "kill", "murder",
    "draw", "weapon", "attack", "strike", "hit", "punch", "fight",
    "heads", "platter", "blood", "die", "death", "run through", "skewer"
}

THREAT_PHRASES = [
    r"draw.*(blade|sword|knife)",
    r"stab",
    r"run .* through",
    r"kill",
    r"heads on a platter",
    r"dark seeds",
    r"attack",
]


def detect_threat_level(text: str) -> float:
    """Return 0.0–1.0 threat intensity from user text."""
    if not text:
        return 0.0
    lower = text.lower()
    score = 0.0

    for w in VIOLENCE_WORDS:
        if w in lower:
            score += 0.25

    for pat in THREAT_PHRASES:
        if re.search(pat, lower):
            score += 0.35

    # Escalation markers
    if "run the bar keep through" in lower or "run him through" in lower or "run her through" in lower:
        score += 0.6
    if "stab" in lower and ("keep" in lower or "bar" in lower):
        score += 0.5

    return min(1.0, score)


# ---------------------------------------------------------------------------
# Tavern Settlement
# ---------------------------------------------------------------------------

class TavernSettlement:
    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self.pressure: float = 0.25
        self.scarcity: Dict[str, float] = {
            "attention": 0.35,
            "space": 0.30,
            "ale": 0.20,
        }
        self.event_log: List[dict] = []
        self.tick_count: int = 0
        self.current_threat: float = 0.0
        self._seed_population()
        self._seed_histories()

    def _seed_population(self):
        specs = [
            ("Keep",   "LSI", 1, "Owner / admission & resource control"),
            ("Bren",   "LIE", 2, "Merchant / supplier"),
            ("Nessa",  "IEE", 6, "Storyteller regular"),
            ("Tarin",  "IEE", 8, "Connector regular (divergent)"),
            ("Kael",   "SLE", 4, "Hothead regular"),
            ("Sera",   "EII", 5, "Empath / relational observer"),
            ("Orin",   "ILI", 3, "Quiet structural observer"),
            ("Server", "SEI", 7, "Facilitator"),
        ]
        for name, tim, pos, role in specs:
            self.agents[name] = Agent(name=name, tim=tim, position=pos, role=role)

    def _seed_histories(self):
        now = time.time()
        day = 86400.0
        seeds = [
            ("Keep", "Kael", now - 4*day, "Kael contested preferred table; Keep enforced ownership", -0.18),
            ("Kael", "Keep", now - 4*day, "Challenged table claim and was refused", -0.18),
            ("Keep", "Bren", now - 6*day, "Accepted large supply delivery under mild scarcity", +0.22),
            ("Bren", "Keep", now - 6*day, "Delivered supply under structured terms", +0.22),
            ("Nessa", "Tarin", now - 2*day, "Shared extended gossip about a transient", +0.25),
            ("Tarin", "Nessa", now - 2*day, "Shared extended gossip about a transient", +0.25),
            ("Nessa", "Sera", now - 3*day, "Told a personal story; Sera registered relational texture", +0.12),
            ("Sera", "Nessa", now - 3*day, "Registered relational texture of Nessa's story", +0.12),
            ("Kael", "Server", now - 1*day, "Server mediated raised-voice exchange", -0.05),
            ("Server", "Kael", now - 1*day, "Mediated Kael's raised-voice exchange", +0.08),
            ("Sera", "Orin", now - 5*day, "Quiet shared observation of corner-table dispute", +0.10),
            ("Orin", "Sera", now - 5*day, "Quiet shared observation of corner-table dispute", +0.10),
            ("Bren", "Server", now - 1*day, "Server relayed customer request for specialty", +0.15),
            ("Server", "Bren", now - 1*day, "Relayed customer request for Bren's specialty", +0.15),
            ("Orin", "Keep", now - 7*day, "Noted structural inefficiency in seating layout", +0.05),
            ("Keep", "Orin", now - 7*day, "Registered structural note without immediate change", +0.05),
        ]
        for agent_name, other, ts, event, delta in seeds:
            a = self.agents[agent_name]
            a.history.append(DirectedHistory(timestamp=ts, other=other, event=event, trust_delta=delta))
            a.trust[other] = a.trust.get(other, 0.0) + delta

    def process_user_message(self, user_name: str, text: str) -> List[IntentionPacket]:
        event = {
            "id": str(uuid.uuid4()),
            "type": "user_speech",
            "actor": user_name,
            "content": text.strip(),
            "timestamp": time.time(),
        }
        self.event_log.append(event)

        # Update threat level from this message
        self.current_threat = detect_threat_level(text)

        # Check for lethal action against Keep
        lower = text.lower()
        if self.current_threat > 0.7 and any(w in lower for w in ("keep", "bar keep", "barkeeper", "owner")):
            if any(w in lower for w in ("stab", "run through", "kill", "skewer", "blade through")):
                if "Keep" in self.agents and not self.agents["Keep"].incapacitated:
                    self.agents["Keep"].incapacitated = True
                    self.pressure = min(1.0, self.pressure + 0.45)
                    self.scarcity["attention"] = min(1.0, self.scarcity["attention"] + 0.4)

        return self.tick(trigger_event=event)

    def tick(self, trigger_event: Optional[dict] = None) -> List[IntentionPacket]:
        self.tick_count += 1
        packets: List[IntentionPacket] = []

        for name, agent in self.agents.items():
            if agent.incapacitated:
                # Only produce a single low or zero priority fall/observe once
                if agent.last_intention is None or agent.last_intention.intention_type != IntentionType.FALL:
                    packets.append(IntentionPacket(
                        agent=name,
                        intention_type=IntentionType.FALL,
                        target=None,
                        priority=0.95,
                        formal_reason="Agent incapacitated by lethal action",
                        content_hint="falls or lies still, no further speech",
                    ))
                continue

            intention = self._generate_intention(agent, trigger_event)
            if intention and intention.priority > 0.12:
                agent.last_intention = intention
                packets.append(intention)

        packets.sort(key=lambda p: p.priority, reverse=True)
        return packets

    def _generate_intention(self, agent: Agent, trigger: Optional[dict]) -> Optional[IntentionPacket]:
        access = agent.access()
        threat = self.current_threat
        pressure = self.pressure

        base = 0.22
        if access["conscious"]:
            base += 0.12
        if access["valued"]:
            base += 0.10
        base += pressure * 0.25

        # High threat strongly suppresses soft social intentions
        if threat > 0.55 and agent.tim in ("IEE", "EII", "SEI") and agent.name != "Server":
            base *= 0.35

        negative_trust = [o for o, t in agent.trust.items() if t < -0.1]

        # ---------- Keep (LSI) ----------
        if agent.name == "Keep":
            if threat > 0.6:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.DEFEND if threat < 0.85 else IntentionType.CHALLENGE,
                    target="user",
                    priority=min(0.98, 0.7 + threat * 0.3),
                    formal_reason="Ownership and structural integrity under direct physical threat",
                    content_hint="assert authority, warn, or move to stop the threat",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base * 0.75,
                formal_reason="Structural observation under baseline pressure",
                content_hint="quiet assessment of order and resources",
            )

        # ---------- Kael (SLE) ----------
        if agent.name == "Kael":
            if threat > 0.4:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.CHALLENGE if threat < 0.75 else IntentionType.ATTACK,
                    target="user",
                    priority=min(0.97, 0.65 + threat * 0.35),
                    formal_reason="Force valuation and territorial response under rising violence",
                    content_hint="move toward confrontation or seize the moment of disorder",
                )
            if negative_trust:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.CHALLENGE,
                    target=negative_trust[0],
                    priority=0.7,
                    formal_reason="Residual negative trust under ambient pressure",
                    content_hint="assert dominance or contest space",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target=None,
                priority=base,
                formal_reason="Vital energy under ambient pressure",
                content_hint="blunt observation or restless energy",
            )

        # ---------- Server (SEI) ----------
        if agent.name == "Server":
            if threat > 0.55:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.ALARM if threat > 0.75 else IntentionType.MEDIATE,
                    target="user",
                    priority=min(0.88, 0.5 + threat * 0.4),
                    formal_reason="Facilitation constitution under social rupture",
                    content_hint="call for calm, shield someone, or cry out",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OFFER if trigger else IntentionType.SPEAK,
                target="user" if trigger else None,
                priority=min(0.75, base + 0.12),
                formal_reason="Facilitation under normal social presence",
                content_hint="offer service, comfort, or smooth transition",
            )

        # ---------- Sera (EII) ----------
        if agent.name == "Sera":
            if threat > 0.5:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.MEDIATE,
                    target=None,
                    priority=0.55 + threat * 0.2,
                    formal_reason="Relational valuation under rupture",
                    content_hint="register the break in bonds or attempt soft mediation",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base + 0.08,
                formal_reason="Relational valuation and empathic registration",
                content_hint="quiet relational note",
            )

        # ---------- Nessa / Tarin (IEE) ----------
        if agent.tim == "IEE":
            if threat > 0.6:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.WITHDRAW,
                    target=None,
                    priority=0.45,
                    formal_reason="Connection drive under high threat — withdraw or freeze",
                    content_hint="step back, freeze, or speak a single shocked line",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target="user" if trigger else None,
                priority=min(0.78, base + 0.18),
                formal_reason="Ne-driven connection under normal conditions",
                content_hint="story, question, or connective remark",
            )

        # ---------- Bren (LIE) ----------
        if agent.name == "Bren":
            if threat > 0.6:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.WITHDRAW,
                    target=None,
                    priority=0.5,
                    formal_reason="Practical valuation under violence — protect self and goods",
                    content_hint="step back or secure valuables",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target=None,
                priority=base,
                formal_reason="Te-driven practical observation",
                content_hint="practical remark about supply or efficiency",
            )

        # ---------- Orin (ILI) ----------
        if agent.name == "Orin":
            if threat > 0.5:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.OBSERVE,
                    target=None,
                    priority=0.55,
                    formal_reason="Structural observation under rupture",
                    content_hint="quiet structural note of the sudden change",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base * 0.55,
                formal_reason="Structural / Ni observation under low pressure",
                content_hint="quiet structural or temporal observation",
            )

        # Fallback
        return IntentionPacket(
            agent=agent.name,
            intention_type=IntentionType.OBSERVE,
            target=None,
            priority=base * 0.4,
            formal_reason="Baseline ambient response",
            content_hint="presence in the room",
        )

    def get_state_summary(self) -> dict:
        return {
            "tick": self.tick_count,
            "pressure": self.pressure,
            "scarcity": self.scarcity,
            "current_threat": self.current_threat,
            "agents": {
                name: {
                    "tim": a.tim,
                    "position": a.position,
                    "role": a.role,
                    "trust": a.trust,
                    "incapacitated": a.incapacitated,
                }
                for name, a in self.agents.items()
            },
            "recent_events": self.event_log[-5:],
        }


if __name__ == "__main__":
    tavern = TavernSettlement()
    print("=== Tavern Settlement v0.2 ===")
    packets = tavern.process_user_message("Traveler", "I draw my blade and stab the Keep")
    for p in packets:
        print(f"  {p.agent:8} | {p.intention_type.value:10} | prio={p.priority:.2f} | {p.content_hint}")
