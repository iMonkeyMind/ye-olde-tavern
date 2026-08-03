"""
Tavern Settlement v0.1 — Pure Deterministic Kernel
Stage-1.5 of Mara under locked Parametric Field formalisms.

No LLM inside this file. All behavior emerges from:
- Locked position-to-access properties
- Domain pairs (implicit in TIM)
- Directed histories + trust
- Mild ambient pressure + scarcity

Intention packets are the only output. Verbalization is external (Grok API overlay).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import time
import uuid


# ---------------------------------------------------------------------------
# Locked access properties by position number (from Formal Bridge / Living Knot)
# Bandwidth: 1=4D, 2=3D, 3=2D, 4=1D, 5=1D, 6=2D, 7=3D, 8=4D
# Conscious: 1-4, Automatic: 5-8
# Valued: 1,2,5,6   Unvalued: 3,4,7,8
# Accepting: 1,3,5,7   Producing: 2,4,6,8
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
    priority: float          # 0.0 – 1.0
    formal_reason: str       # short reconstructible reason from constitution + history + pressure
    content_hint: str        # brief internal hint for verbalizer (never free text)
    trust_delta: float = 0.0


@dataclass
class Agent:
    name: str
    tim: str
    position: int
    role: str
    history: List[DirectedHistory] = field(default_factory=list)
    trust: Dict[str, float] = field(default_factory=dict)   # other -> current trust
    last_intention: Optional[IntentionPacket] = None

    def access(self) -> dict:
        return POSITION_ACCESS[self.position]

    def current_trust(self, other: str) -> float:
        return self.trust.get(other, 0.0)


# ---------------------------------------------------------------------------
# Tavern Settlement
# ---------------------------------------------------------------------------

class TavernSettlement:
    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self.pressure: float = 0.25          # mild ambient
        self.scarcity: Dict[str, float] = {  # 0.0 = plenty, 1.0 = critical
            "attention": 0.35,
            "space": 0.30,
            "ale": 0.20,
        }
        self.event_log: List[dict] = []
        self.tick_count: int = 0
        self._seed_population()
        self._seed_histories()

    def _seed_population(self):
        """8 agents under locked rules. Positions chosen for coverage + tavern dynamics."""
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
        """Minimal directed seed events from the locked contract."""
        now = time.time()
        day = 86400.0

        seeds = [
            # Keep ↔ Kael
            ("Keep", "Kael", now - 4*day, "Kael contested preferred table; Keep enforced ownership", -0.18),
            ("Kael", "Keep", now - 4*day, "Challenged table claim and was refused", -0.18),
            # Keep ↔ Bren
            ("Keep", "Bren", now - 6*day, "Accepted large supply delivery under mild scarcity", +0.22),
            ("Bren", "Keep", now - 6*day, "Delivered supply under structured terms", +0.22),
            # Nessa ↔ Tarin
            ("Nessa", "Tarin", now - 2*day, "Shared extended gossip about a transient", +0.25),
            ("Tarin", "Nessa", now - 2*day, "Shared extended gossip about a transient", +0.25),
            # Nessa ↔ Sera
            ("Nessa", "Sera", now - 3*day, "Told a personal story; Sera registered relational texture", +0.12),
            ("Sera", "Nessa", now - 3*day, "Registered relational texture of Nessa's story", +0.12),
            # Kael ↔ Server
            ("Kael", "Server", now - 1*day, "Server mediated raised-voice exchange", -0.05),
            ("Server", "Kael", now - 1*day, "Mediated Kael's raised-voice exchange", +0.08),
            # Sera ↔ Orin
            ("Sera", "Orin", now - 5*day, "Quiet shared observation of corner-table dispute", +0.10),
            ("Orin", "Sera", now - 5*day, "Quiet shared observation of corner-table dispute", +0.10),
            # Bren ↔ Server
            ("Bren", "Server", now - 1*day, "Server relayed customer request for specialty", +0.15),
            ("Server", "Bren", now - 1*day, "Relayed customer request for Bren's specialty", +0.15),
            # Orin ↔ Keep
            ("Orin", "Keep", now - 7*day, "Noted structural inefficiency in seating layout", +0.05),
            ("Keep", "Orin", now - 7*day, "Registered structural note without immediate change", +0.05),
        ]

        for agent_name, other, ts, event, delta in seeds:
            a = self.agents[agent_name]
            a.history.append(DirectedHistory(timestamp=ts, other=other, event=event, trust_delta=delta))
            a.trust[other] = a.trust.get(other, 0.0) + delta

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def process_user_message(self, user_name: str, text: str) -> List[IntentionPacket]:
        """
        Turn free text into a structured event, advance one tick,
        return the list of intention packets for the verbalizer.
        """
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
        """
        Advance the settlement one step under current pressure + scarcity.
        Returns structured intention packets only.
        """
        self.tick_count += 1
        packets: List[IntentionPacket] = []

        # Simple relevance: agents react more if the event mentions them
        # or if pressure/scarcity is elevated, or if they have active threads.
        for name, agent in self.agents.items():
            intention = self._generate_intention(agent, trigger_event)
            if intention and intention.priority > 0.15:
                agent.last_intention = intention
                packets.append(intention)

        # Sort by priority descending so verbalizer can render strongest first
        packets.sort(key=lambda p: p.priority, reverse=True)
        return packets

    def _generate_intention(self, agent: Agent, trigger: Optional[dict]) -> Optional[IntentionPacket]:
        """
        Pure formal generation. No language model.
        Intention emerges from access properties + trust + pressure + scarcity + recent history.
        """
        access = agent.access()
        pressure = self.pressure
        att_scar = self.scarcity["attention"]
        space_scar = self.scarcity["space"]

        # Baseline priority influenced by conscious bandwidth and valued status
        base = 0.25
        if access["conscious"]:
            base += 0.15
        if access["valued"]:
            base += 0.10
        base += pressure * 0.3
        base += att_scar * 0.2

        # If user just spoke, raise priority for social / accepting agents
        if trigger and trigger.get("type") == "user_speech":
            if access["accepting"] or agent.tim in ("IEE", "SEI", "EII", "ESE"):
                base += 0.25
            if agent.tim in ("SLE", "LSI") and space_scar > 0.25:
                base += 0.15  # resource / territory sensitivity

        # Active negative trust raises challenge or withdraw probability
        negative_trust = [o for o, t in agent.trust.items() if t < -0.1]
        positive_trust = [o for o, t in agent.trust.items() if t > 0.15]

        # Simple deterministic selection based on TIM + access
        # (In full Living Knot this would be Hamiltonian / block-grammar constrained.
        #  Here we stay minimal and reconstructible.)
        if agent.tim == "LSI" and access["accepting"]:  # Keep
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

        if agent.tim == "SLE":  # Kael
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

        if agent.tim in ("IEE",):  # Nessa / Tarin
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target="user" if trigger else (positive_trust[0] if positive_trust else None),
                priority=min(0.85, base + 0.2),
                formal_reason="Ne-driven connection + positive relational history",
                content_hint="story, question, or connective remark",
            )

        if agent.tim == "EII":  # Sera
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.MEDIATE if negative_trust else IntentionType.OBSERVE,
                target=None,
                priority=base + 0.1,
                formal_reason="Relational valuation and empathic registration",
                content_hint="quiet relational note or soft mediation",
            )

        if agent.tim == "SEI":  # Server
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OFFER if trigger else IntentionType.SPEAK,
                target="user" if trigger else None,
                priority=min(0.8, base + 0.15),
                formal_reason="Facilitation constitution under social presence",
                content_hint="offer service, comfort, or smooth transition",
            )

        if agent.tim == "LIE":  # Bren
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.SPEAK,
                target=None,
                priority=base,
                formal_reason="Te-driven practical observation under mild scarcity",
                content_hint="practical remark about supply, trade, or efficiency",
            )

        if agent.tim == "ILI":  # Orin
            return IntentionPacket(
                agent=agent.name,
                intention_type=IntentionType.OBSERVE,
                target=None,
                priority=base * 0.6,
                formal_reason="Structural / Ni observation under low pressure",
                content_hint="quiet structural or temporal observation",
            )

        # Fallback
        return IntentionPacket(
            agent=agent.name,
            intention_type=IntentionType.OBSERVE,
            target=None,
            priority=base * 0.5,
            formal_reason="Baseline ambient response",
            content_hint="presence in the room",
        )

    def get_state_summary(self) -> dict:
        """Minimal formal state for logging / debugging / prompt context."""
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


# ---------------------------------------------------------------------------
# Quick self-test (run directly)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tavern = TavernSettlement()
    print("=== Tavern Settlement v0.1 seeded ===")
    print(f"Agents: {list(tavern.agents.keys())}")
    print(f"Pressure: {tavern.pressure}, Scarcity: {tavern.scarcity}")
    print()

    packets = tavern.process_user_message("Traveler", "Good evening. Is there room at the fire?")
    print("=== Intentions after user message ===")
    for p in packets:
        print(f"  {p.agent:8} | {p.intention_type.value:10} | prio={p.priority:.2f} | {p.formal_reason}")
        print(f"           hint: {p.content_hint}")
    print()
    print("State summary keys:", list(tavern.get_state_summary().keys()))
