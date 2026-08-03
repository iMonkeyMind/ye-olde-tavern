"""
Tavern Settlement v0.3 — Higher-dimensional formal kernel
First practical layer of Recursive Cross / domain-pair attention routing
+ stronger multi-agent consequence for playable aliveness.

Locked first-layer domain mapping used:
N = ITS + I
S = WE + IT
T = ITS + IT
F = I + WE

Access regimes still govern bandwidth / valued / accepting / producing.
Pure formal layer. No LLM inside.
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

DOMAIN_PAIRS = {
    "N": ("ITS", "I"),
    "S": ("WE", "IT"),
    "T": ("ITS", "IT"),
    "F": ("I", "WE"),
}

TIM_PRIMARY = {
    "LSI": "T", "LSE": "T", "ILI": "T", "LIE": "T",
    "ESI": "F", "EII": "F", "SEE": "F", "ESE": "F",
    "SLE": "S", "SEI": "S", "IEE": "N", "ILE": "N",
    "IEI": "N", "EIE": "N",
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
    CONNECT = "connect"
    STRUCTURE = "structure"


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
    domain: str = ""
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

    def primary_domain(self) -> str:
        return TIM_PRIMARY.get(self.tim, "T")


VIOLENCE = re.compile(
    r"\b(kill|stab|sword|attack|slash|cut|murder|disembowel|gut|strike|hit|punch|fight|threaten|die|death|blood|weapon|blade)\b",
    re.I
)
OWNERSHIP = re.compile(r"\b(table|bar|room|space|keep|owner|mine|yours|claim|hall)\b", re.I)
SOCIAL = re.compile(r"\b(friend|story|tell|listen|together|we|us|help|please|sorry)\b", re.I)


class TavernSettlement:
    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self.pressure: float = 0.22
        self.scarcity = {"attention": 0.32, "space": 0.28, "ale": 0.18}
        self.event_log: List[dict] = []
        self.tick_count = 0
        self.user_threat = 0.0
        self.room_mood = 0.15
        self._seed()

    def _seed(self):
        specs = [
            ("Keep",   "LSI", 1, "Owner"),
            ("Bren",   "LIE", 2, "Merchant"),
            ("Nessa",  "IEE", 6, "Storyteller"),
            ("Tarin",  "IEE", 8, "Connector"),
            ("Kael",   "SLE", 4, "Hothead"),
            ("Sera",   "EII", 5, "Empath"),
            ("Orin",   "ILI", 3, "Observer"),
            ("Server", "SEI", 7, "Facilitator"),
        ]
        for n, t, p, r in specs:
            self.agents[n] = Agent(n, t, p, r)

        now = time.time()
        day = 86400.0
        seeds = [
            ("Keep", "Kael", -4, "table contest", -0.18),
            ("Kael", "Keep", -4, "table contest", -0.18),
            ("Keep", "Bren", -6, "supply delivery", 0.22),
            ("Bren", "Keep", -6, "supply delivery", 0.22),
            ("Nessa", "Tarin", -2, "shared gossip", 0.25),
            ("Tarin", "Nessa", -2, "shared gossip", 0.25),
            ("Nessa", "Sera", -3, "personal story", 0.12),
            ("Sera", "Nessa", -3, "personal story", 0.12),
            ("Kael", "Server", -1, "raised voice mediated", -0.05),
            ("Server", "Kael", -1, "mediated", 0.08),
            ("Sera", "Orin", -5, "quiet observation", 0.10),
            ("Orin", "Sera", -5, "quiet observation", 0.10),
            ("Bren", "Server", -1, "specialty request", 0.15),
            ("Server", "Bren", -1, "specialty request", 0.15),
            ("Orin", "Keep", -7, "seating note", 0.05),
            ("Keep", "Orin", -7, "seating note", 0.05),
        ]
        for a, o, d, e, delta in seeds:
            ag = self.agents[a]
            ag.history.append(DirectedHistory(now + d*day, o, e, delta))
            ag.trust[o] = ag.trust.get(o, 0.0) + delta

    def process_user_message(self, user_name: str, text: str) -> List[IntentionPacket]:
        event = {
            "id": str(uuid.uuid4()),
            "type": "user_speech",
            "actor": user_name,
            "content": text.strip(),
            "timestamp": time.time(),
        }
        self.event_log.append(event)

        vscore = len(VIOLENCE.findall(text))
        own = bool(OWNERSHIP.search(text))
        soc = bool(SOCIAL.search(text))

        if vscore:
            self.user_threat = min(1.0, self.user_threat + 0.28 * vscore)
            self.pressure = min(0.95, self.pressure + 0.20 * vscore)
            self.room_mood = min(1.0, self.room_mood + 0.22 * vscore)
            for ag in self.agents.values():
                delta = -0.14 * vscore
                if ag.name in ("Keep", "Kael", "Server"):
                    delta *= 1.7
                ag.trust[user_name] = ag.trust.get(user_name, 0.0) + delta
                ag.history.append(DirectedHistory(
                    time.time(), user_name, f"violence/threat x{vscore}", delta
                ))

        if own:
            self.pressure = min(0.95, self.pressure + 0.09)
            self.agents["Keep"].trust[user_name] = self.agents["Keep"].trust.get(user_name, 0.0) - 0.18

        if soc and vscore == 0:
            self.room_mood = max(0.05, self.room_mood - 0.08)
            for ag in self.agents.values():
                if ag.tim in ("IEE", "EII", "SEI"):
                    ag.trust[user_name] = ag.trust.get(user_name, 0.0) + 0.06

        return self.tick(event)

    def tick(self, trigger: Optional[dict] = None) -> List[IntentionPacket]:
        self.tick_count += 1
        packets = []
        for ag in self.agents.values():
            p = self._intention(ag, trigger)
            if p and p.priority > 0.11:
                ag.last_intention = p
                packets.append(p)
        packets.sort(key=lambda x: x.priority, reverse=True)
        return packets

    def _intention(self, agent: Agent, trigger: Optional[dict]) -> Optional[IntentionPacket]:
        acc = agent.access()
        dom = agent.primary_domain()
        pairs = DOMAIN_PAIRS[dom]
        pressure = self.pressure
        threat = self.user_threat
        mood = self.room_mood
        u_trust = agent.current_trust("Traveler") if trigger else 0.0
        content = (trigger.get("content", "") if trigger else "").lower()

        base = 0.18
        if acc["conscious"]:
            base += 0.16
        if acc["valued"]:
            base += 0.15
        if acc["accepting"] and trigger:
            base += 0.12
        if not acc["accepting"]:
            base += 0.08
        base += pressure * 0.32
        base += threat * 0.28
        base += mood * 0.12
        if u_trust < -0.12:
            base += abs(u_trust) * 0.45

        if agent.tim == "LSI":
            if threat > 0.32 or u_trust < -0.22:
                return IntentionPacket(
                    agent.name,
                    IntentionType.DEFEND if threat > 0.55 else IntentionType.CHALLENGE,
                    "user",
                    min(0.97, base + 0.38),
                    f"T-domain ownership + elevated threat (pairs {pairs})",
                    "assert the hall is under his control and issue consequence",
                    dom
                )
            if own or "space" in content or "table" in content:
                return IntentionPacket(
                    agent.name, IntentionType.CHALLENGE, "user",
                    min(0.91, base + 0.28),
                    "T-domain space claim",
                    "reassert ownership of the physical hall",
                    dom
                )
            return IntentionPacket(
                agent.name, IntentionType.STRUCTURE, None,
                base * 0.62,
                "T-domain structural observation",
                "quietly measure order, resources, and any breach of house law",
                dom
            )

        if agent.tim == "SLE":
            if threat > 0.22 or u_trust < -0.18:
                return IntentionPacket(
                    agent.name,
                    IntentionType.THREATEN if threat > 0.58 else IntentionType.CHALLENGE,
                    "user",
                    min(0.95, base + 0.42),
                    f"S-domain force under rising threat (pairs {pairs})",
                    "move body into the threat space and contest it directly",
                    dom
                )
            return IntentionPacket(
                agent.name, IntentionType.SPEAK, None,
                base,
                "S-domain vital presence",
                "blunt, embodied observation of the room",
                dom
            )

        if agent.tim == "SEI":
            if threat > 0.38:
                return IntentionPacket(
                    agent.name,
                    IntentionType.MEDIATE if u_trust > -0.28 else IntentionType.WITHDRAW,
                    "user",
                    min(0.87, base + 0.24),
                    "S-domain facilitation under social threat",
                    "try to lower the bodily tension or step out of the line of fire",
                    dom
                )
            return IntentionPacket(
                agent.name, IntentionType.OFFER, "user" if trigger else None,
                min(0.79, base + 0.14),
                "S-domain service",
                "offer a drink, a seat, or a small comfort",
                dom
            )

        if agent.tim == "EII":
            if threat > 0.28 or mood > 0.45:
                return IntentionPacket(
                    agent.name, IntentionType.MEDIATE, None,
                    min(0.86, base + 0.22),
                    f"F-domain relational field under strain (pairs {pairs})",
                    "feel the rupture in the room and attempt soft mediation",
                    dom
                )
            return IntentionPacket(
                agent.name, IntentionType.OBSERVE, None,
                base + 0.09,
                "F-domain quiet registration of bonds",
                "note the emotional weather between people",
                dom
            )

        if agent.tim == "IEE":
            if threat > 0.42:
                return IntentionPacket(
                    agent.name,
                    IntentionType.WITHDRAW if threat > 0.68 else IntentionType.CONNECT,
                    "user",
                    min(0.83, base + 0.16),
                    f"N-domain possibility under threat (pairs {pairs})",
                    "seek a different story or step back from the violence",
                    dom
                )
            return IntentionPacket(
                agent.name, IntentionType.CONNECT, "user" if trigger else None,
                min(0.85, base + 0.19),
                "N-domain connective possibility",
                "open a story, a question, or a shared what-if",
                dom
            )

        if agent.tim == "LIE":
            if threat > 0.48:
                return IntentionPacket(
                    agent.name, IntentionType.OBSERVE, None,
                    base * 0.68,
                    "T-domain practical risk assessment",
                    "calculate the cost of this conflict to goods and trade",
                    dom
                )
            return IntentionPacket(
                agent.name, IntentionType.SPEAK, None,
                base,
                "T-domain practical remark",
                "comment on supply, efficiency, or the night's trade",
                dom
            )

        if agent.tim == "ILI":
            return IntentionPacket(
                agent.name, IntentionType.OBSERVE, None,
                base * 0.52 + threat * 0.18,
                "T-domain temporal / structural observation",
                "watch the longer pattern of how this night is unfolding",
                dom
            )

        return IntentionPacket(
            agent.name, IntentionType.OBSERVE, None,
            base * 0.35,
            "ambient presence",
            "simply exist in the room",
            dom
        )

    def get_state_summary(self) -> dict:
        return {
            "tick": self.tick_count,
            "pressure": round(self.pressure, 3),
            "user_threat": round(self.user_threat, 3),
            "room_mood": round(self.room_mood, 3),
            "scarcity": self.scarcity,
            "agents": {
                n: {
                    "tim": a.tim,
                    "domain": a.primary_domain(),
                    "trust_user": round(a.current_trust("Traveler"), 3),
                }
                for n, a in self.agents.items()
            },
        }
