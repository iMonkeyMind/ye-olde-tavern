"""
Tavern Settlement v0.1 — Pure Deterministic Kernel
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import time
import uuid


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
        return self.tick(trigger_event=event)

    def tick(self, trigger_event: Optional[dict] = None) -> List[IntentionPacket]:
        self.tick_count += 1
        packets: List[IntentionPacket] = []
        for name, agent in self.agents.items():
            intention = self._generate_intention(agent, trigger_event)
            if intention and intention.priority > 0.15:
                agent.last_intention = intention
                packets.append(intention)
        packets.sort(key=lambda p: p.priority, reverse=True)
        return packets

    def _generate_intention(self, agent: Agent, trigger: Optional[dict]) -> Optional[IntentionPacket]:
        access = agent.access()
        pressure = self.pressure
        att_scar = self.scarcity["attention"]
        space_scar = self.scarcity["space"]

        base = 0.25
        if access["conscious"]:
            base += 0.15
        if access["valued"]:
            base += 0.10
        base += pressure * 0.3
        base += att_scar * 0.2

        if trigger and trigger.get("type") == "user_speech":
            if access["accepting"] or agent.tim in ("IEE", "SEI", "EII", "ESE"):
                base += 0.25
            if agent.tim in ("SLE", "LSI") and space_scar > 0.25:
                base += 0.15

        negative_trust = [o for o, t in agent.trust.items() if t < -0.1]
        positive_trust = [o for o, t in agent.trust.items() if t > 0.15]

        if agent.tim == "LSI":
            if space_scar > 0.4 or (trigger and "table" in trigger.get("content", "").lower()):
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.CHALLENGE if space_scar > 0.5 else IntentionType.SPEAK,
                    target="user" if trigger else None,
                    priority=min(0.95, base + 0.2),
                    formal_reason="Resource/space valuation under mild scarcity + ownership constitution",
                    content_hint="assert ownership or structure of the room",
                )
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base * 0.7,
                formal_reason="Structural observation under baseline pressure",
                content_hint="quiet assessment of order and resources",
            )

        if agent.tim == "SLE":
            if negative_trust or (trigger and any(w in trigger.get("content", "").lower() for w in ("fight", "challenge", "space", "table"))):
                return IntentionPacket(
                    agent=agent.name,
                    intention_type=IntentionType.CHALLENGE,
                    target=negative_trust[0] if negative_trust else "user",
                    priority=min(0.9, base + 0.25),
                    formal_reason="Force valuation under residual negative trust or territorial trigger",
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

        if agent.tim == "IEE":
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target="user" if trigger else (positive_trust[0] if positive_trust else None),
                priority=min(0.85, base + 0.2),
                formal_reason="Ne-driven connection + positive relational history",
                content_hint="story, question, or connective remark",
            )

        if agent.tim == "EII":
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.MEDIATE if negative_trust else IntentionType.OBSERVE,
                target=None,
                priority=base + 0.1,
                formal_reason="Relational valuation and empathic registration",
                content_hint="quiet relational note or soft mediation",
            )

        if agent.tim == "SEI":
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OFFER if trigger else IntentionType.SPEAK,
                target="user" if trigger else None,
                priority=min(0.8, base + 0.15),
                formal_reason="Facilitation constitution under social presence",
                content_hint="offer service, comfort, or smooth transition",
            )

        if agent.tim == "LIE":
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target=None,
                priority=base,
                formal_reason="Te-driven practical observation under mild scarcity",
                content_hint="practical remark about supply, trade, or efficiency",
            )

        if agent.tim == "ILI":
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base * 0.6,
                formal_reason="Structural / Ni observation under low pressure",
                content_hint="quiet structural or temporal observation",
            )

        return IntentionPacket(
            agent=agent.name,
            intention_type=IntentionType.OBSERVE,
            target=None,
            priority=base * 0.5,
            formal_reason="Baseline ambient response",
            content_hint="presence in the room",
        )

    def get_state_summary(self) -> dict:
        return {
            "tick": self.tick_count,
            "pressure": self.pressure,
            "scarcity": self.scarcity,
            "agents": {
                name: {
                    "tim": a.tim,
                    "position": a.position,
                    "role": a.role,
                    "trust": a.trust,
                }
                for name, a in self.agents.items()
            },
            "recent_events": self.event_log[-5:],
        }
