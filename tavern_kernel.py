"""
Tavern Settlement v0.2 — Upgraded Deterministic Kernel
Incorporates pressure escalation, persistent trust deltas, and stronger
positional weighting drawn from the Living Knot Levels 1–3 / Monte Carlo results.

Still pure formal layer. No LLM inside.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import time
import uuid
import re


POSITION_ACCESS = {
    1: {"bandwidth": 4, "conscious": True,  "valued": True,  "accepting": True},
    2: {"bandwidth": 3, "conscious": True,  "valued": True,  "accepting": False},
    3: {"bandwidth": 2, "conscious": True,  "valued": False, "accepting": True},
    4: {"bandwidth": 1, "conscious": True,  "valued": False, "accepting": False},
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
    DEFEND = "defend"
    THREATEN = "threaten"
    ADMIT = "admit"
    REFUSE = "refuse"


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

    def access(self) -> dict:
        return POSITION_ACCESS[self.position]

    def current_trust(self, other: str) -> float:
        return self.trust.get(other, 0.0)


VIOLENCE_PATTERNS = re.compile(
    r"\b(kill|stab|sword|attack|slash|cut|murder|disembowel|gut|strike|hit|punch|fight|threaten|die|death|blood|weapon)\b",
    re.IGNORECASE
)
OWNERSHIP_PATTERNS = re.compile(
    r"\b(table|bar|room|space|keep|owner|mine|yours|claim)\b",
    re.IGNORECASE
)


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
        self.user_threat_level: float = 0.0
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

        violence_score = len(VIOLENCE_PATTERNS.findall(text))
        ownership_challenge = bool(OWNERSHIP_PATTERNS.search(text))

        if violence_score > 0:
            self.user_threat_level = min(1.0, self.user_threat_level + 0.25 * violence_score)
            self.pressure = min(0.95, self.pressure + 0.18 * violence_score)
            for agent in self.agents.values():
                delta = -0.12 * violence_score
                if agent.name in ("Keep", "Kael", "Server"):
                    delta *= 1.6
                agent.trust[user_name] = agent.trust.get(user_name, 0.0) + delta
                agent.history.append(DirectedHistory(
                    timestamp=time.time(),
                    other=user_name,
                    event=f"User violence/threat detected (score {violence_score})",
                    trust_delta=delta
                ))

        if ownership_challenge:
            self.pressure = min(0.95, self.pressure + 0.08)
            keep = self.agents["Keep"]
            keep.trust[user_name] = keep.trust.get(user_name, 0.0) - 0.15

        return self.tick(trigger_event=event)

    def tick(self, trigger_event: Optional[dict] = None) -> List[IntentionPacket]:
        self.tick_count += 1
        packets: List[IntentionPacket] = []
        for name, agent in self.agents.items():
            intention = self._generate_intention(agent, trigger_event)
            if intention and intention.priority > 0.12:
                agent.last_intention = intention
                packets.append(intention)
        packets.sort(key=lambda p: p.priority, reverse=True)
        return packets

    def _generate_intention(self, agent: Agent, trigger: Optional[dict]) -> Optional[IntentionPacket]:
        access = agent.access()
        pressure = self.pressure
        threat = self.user_threat_level
        user_trust = agent.current_trust("Traveler") if trigger else 0.0

        base = 0.20
        if access["conscious"]:
            base += 0.18
        if access["valued"]:
            base += 0.14
        if access["accepting"] and trigger:
            base += 0.10
        base += pressure * 0.35
        base += threat * 0.25

        if user_trust < -0.15:
            base += abs(user_trust) * 0.4

        content = (trigger.get("content", "") if trigger else "").lower()

        if agent.tim == "LSI":
            if threat > 0.35 or user_trust < -0.25:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.DEFEND if threat > 0.55 else IntentionType.CHALLENGE,
                    target="user",
                    priority=min(0.98, base + 0.35),
                    formal_reason="Ownership + elevated threat / negative trust under pressure",
                    content_hint="assert control of the room, refuse the threat, or prepare defense",
                )
            if "table" in content or "bar" in content or "space" in content:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.CHALLENGE,
                    target="user",
                    priority=min(0.92, base + 0.25),
                    formal_reason="Space ownership claim under mild scarcity",
                    content_hint="reassert ownership of the physical space",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base * 0.65,
                formal_reason="Structural observation under current pressure",
                content_hint="assess order, resources, and any breach of house rules",
            )

        if agent.tim == "SLE":
            if threat > 0.25 or user_trust < -0.20:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.CHALLENGE if threat < 0.6 else IntentionType.THREATEN,
                    target="user",
                    priority=min(0.96, base + 0.40),
                    formal_reason="Force valuation under rising threat and negative trust",
                    content_hint="contest the threat, assert force, or move to intercept",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target=None,
                priority=base,
                formal_reason="Vital energy under ambient pressure",
                content_hint="blunt observation or restless energy",
            )

        if agent.tim == "SEI":
            if threat > 0.40:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.MEDIATE if user_trust > -0.3 else IntentionType.WITHDRAW,
                    target="user",
                    priority=min(0.88, base + 0.22),
                    formal_reason="Facilitation under elevated social threat",
                    content_hint="attempt to de-escalate or step back from the violence",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OFFER if trigger else IntentionType.SPEAK,
                target="user" if trigger else None,
                priority=min(0.80, base + 0.12),
                formal_reason="Facilitation constitution under social presence",
                content_hint="offer service, comfort, or smooth the moment",
            )

        if agent.tim == "EII":
            if threat > 0.30:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.MEDIATE,
                    target=None,
                    priority=min(0.85, base + 0.20),
                    formal_reason="Relational valuation under threat — attempt soft mediation",
                    content_hint="register the relational rupture and attempt quiet mediation",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base + 0.08,
                formal_reason="Relational valuation and empathic registration",
                content_hint="quiet relational note",
            )

        if agent.tim == "IEE":
            if threat > 0.45:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.WITHDRAW if threat > 0.7 else IntentionType.SPEAK,
                    target="user",
                    priority=min(0.82, base + 0.15),
                    formal_reason="Ne connection under rising threat — seek information or distance",
                    content_hint="ask what is happening or step back from the violence",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target="user" if trigger else None,
                priority=min(0.84, base + 0.18),
                formal_reason="Ne-driven connection + relational history",
                content_hint="story, question, or connective remark",
            )

        if agent.tim == "LIE":
            if threat > 0.50:
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.OBSERVE,
                    target=None,
                    priority=base * 0.7,
                    formal_reason="Practical observation under high threat",
                    content_hint="assess the practical risk to goods and trade",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target=None,
                priority=base,
                formal_reason="Te-driven practical observation under mild scarcity",
                content_hint="practical remark about supply or efficiency",
            )

        if agent.tim == "ILI":
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base * 0.55 + threat * 0.15,
                formal_reason="Structural / temporal observation under current pressure",
                content_hint="quiet structural or temporal observation of the unfolding event",
            )

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
            "pressure": round(self.pressure, 3),
            "user_threat_level": round(self.user_threat_level, 3),
            "scarcity": self.scarcity,
            "agents": {
                name: {
                    "tim": a.tim,
                    "position": a.position,
                    "role": a.role,
                    "trust_toward_user": round(a.current_trust("Traveler"), 3),
                }
                for name, a in self.agents.items()
            },
            "recent_events": self.event_log[-4:],
        }
