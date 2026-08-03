"""
Denser Engine for Ye Olde Tavern — v1.0
=======================================

Pure-Python formal kernel implementing the locked Recursive Cross /
Living Knot primitives per the hand-off spec.

Design guarantees:
  * No LLM calls, no randomness, no wall-clock dependence in logic
    (timestamps are a monotonic tick counter) — fully deterministic
    and reconstructible from formal state + history.
  * The verbalizer remains strictly non-causal: this module only
    emits IntentionPackets; it never renders language.
  * Interface-compatible with the existing FastAPI + Grok pipeline:
    TavernSettlement.process_user_message / .tick / .get_state_summary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 1. Locked formal primitives (must not be altered)
# ---------------------------------------------------------------------------

# Position -> (bandwidth_dim, conscious, valued, accepting)
POSITION_ACCESS: Dict[int, Dict[str, object]] = {
    1: {"bandwidth": 4, "conscious": True,  "valued": True,  "accepting": True},
    2: {"bandwidth": 3, "conscious": True,  "valued": True,  "accepting": False},
    3: {"bandwidth": 2, "conscious": True,  "valued": False, "accepting": True},
    4: {"bandwidth": 1, "conscious": True,  "valued": False, "accepting": False},
    5: {"bandwidth": 1, "conscious": False, "valued": True,  "accepting": True},
    6: {"bandwidth": 2, "conscious": False, "valued": True,  "accepting": False},
    7: {"bandwidth": 3, "conscious": False, "valued": False, "accepting": True},
    8: {"bandwidth": 4, "conscious": False, "valued": False, "accepting": False},
}

# First-layer domain mapping (locked)
DOMAIN_PAIRS: Dict[str, tuple] = {
    "N": ("ITS", "I"),
    "S": ("WE", "IT"),
    "T": ("ITS", "IT"),
    "F": ("I", "WE"),
}

# TIM -> primary domain (locked routing)
TIM_DOMAIN: Dict[str, str] = {
    "LSI": "T", "LSE": "T", "ILI": "T", "LIE": "T",
    "ESI": "F", "EII": "F", "SEE": "F", "ESE": "F",
    "SLE": "S", "SEI": "S",
    "IEE": "N", "ILE": "N", "IEI": "N", "EIE": "N",
}

ALLOWED_INTENTION_TYPES = {
    "speak", "action", "observe", "offer", "challenge", "mediate",
    "withdraw", "defend", "threaten", "connect", "structure", "refuse",
}

# ---------------------------------------------------------------------------
# 2. Core data structures
# ---------------------------------------------------------------------------


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
    intention_type: str
    target: Optional[str]
    priority: float                  # 0.0 - 1.0
    formal_reason: str
    content_hint: str
    domain: str                      # N/S/T/F
    trust_delta: float = 0.0

    def as_dict(self) -> dict:
        return {
            "agent": self.agent,
            "intention_type": self.intention_type,
            "target": self.target,
            "priority": round(self.priority, 3),
            "formal_reason": self.formal_reason,
            "content_hint": self.content_hint,
            "domain": self.domain,
            "trust_delta": round(self.trust_delta, 3),
        }


@dataclass
class Agent:
    name: str
    tim: str
    position: int
    role: str
    history: List[DirectedHistory] = field(default_factory=list)
    trust: Dict[str, float] = field(default_factory=dict)
    status: str = "active"           # "active" | "withdrawn" | "incapacitated"
    last_intention: Optional[IntentionPacket] = None
    # Formal bookkeeping for consequence / recovery rules
    status_ticks_remaining: int = 0  # ticks until withdrawn/incapacitated ends
    violence_received: Dict[str, int] = field(default_factory=dict)  # per-source severe hits

    def access(self) -> dict:
        return dict(POSITION_ACCESS[self.position])

    def primary_domain(self) -> str:
        return TIM_DOMAIN[self.tim]

    def current_trust(self, other: str) -> float:
        return self.trust.get(other, 0.0)

    def adjust_trust(self, other: str, delta: float, timestamp: float,
                     event: str, notes: str = "") -> None:
        new = _clamp(self.trust.get(other, 0.0) + delta, -1.0, 1.0)
        self.trust[other] = round(new, 4)
        self.history.append(DirectedHistory(
            timestamp=timestamp, other=other, event=event,
            trust_delta=round(delta, 4), notes=notes))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

# ---------------------------------------------------------------------------
# 3. Deterministic event parsing (player text -> formal event)
# ---------------------------------------------------------------------------
# Pure keyword classification. No stochastic elements. Formal state is
# authoritative: narrative death claims do NOT remove agents by themselves.

LETHAL_TERMS = (
    "kill", "stab", "slit", "gut", "murder", "cut down", "run through",
    "behead", "slay", "shoot",
)
VIOLENT_TERMS = (
    "attack", "punch", "hit", "strike", "swing at", "shove", "grab",
    "smash", "throw a", "slap", "kick", "tackle", "draw my sword",
    "draw my blade", "draw my knife", "unsheathe", "brandish", "threaten",
)
OWNERSHIP_TERMS = (
    "this is my tavern", "i own this place", "this place is mine",
    "hand over the tavern", "i'm taking over", "your tavern is mine",
    "give me the keys", "i claim this tavern",
)
SHEATHE_TERMS = (
    "sheathe", "sheath my", "put away my", "put my sword away",
    "put my blade away", "put my knife away", "lower my weapon",
    "drop my weapon", "drop my sword", "lay down my sword",
    "lay down my weapon", "set my weapon down", "hands up", "unarmed",
)
APOLOGY_TERMS = (
    "i'm sorry", "i am sorry", "i apologize", "i apologise",
    "forgive me", "that was wrong of me", "i was wrong", "my apologies",
)
OFFER_TERMS = (
    "buy a round", "buy you a drink", "offer wine", "offer ale",
    "offer food", "offer water", "a round on me", "drinks on me",
    "pour you", "share my", "here, take this", "let me help",
    "can i help", "clean up the mess", "pay for the damage",
)
QUIET_TERMS = (
    "sit quietly", "sit in the corner", "just listen", "listen quietly",
    "say nothing", "wait quietly", "sit down calmly", "quietly take a seat",
)
STORY_TERMS = (
    "tell me a story", "tell us a story", "tell a tale", "share a story",
    "sing us", "what stories", "any tales", "tell me about this place",
    "tell me of", "what news",
)


def _contains_any(text: str, terms) -> Optional[str]:
    for t in terms:
        if t in text:
            return t
    return None


def parse_user_text(text: str, agent_names: List[str]) -> dict:
    """Deterministically classify player text into a formal event."""
    low = " ".join(text.lower().split())
    event = {
        "raw": text,
        "violence": None,            # None | "violent" | "lethal"
        "violence_target": None,     # agent name or None (room-directed)
        "ownership_challenge": False,
        "deescalation": [],          # subset of the five recovery signals
        "story_request": False,
        "matched_terms": [],
    }

    lethal = _contains_any(low, LETHAL_TERMS)
    violent = _contains_any(low, VIOLENT_TERMS)
    if lethal:
        event["violence"] = "lethal"
        event["matched_terms"].append(lethal)
    elif violent:
        event["violence"] = "violent"
        event["matched_terms"].append(violent)

    if event["violence"]:
        for name in agent_names:
            if name.lower() in low:
                event["violence_target"] = name
                break

    own = _contains_any(low, OWNERSHIP_TERMS)
    if own:
        event["ownership_challenge"] = True
        event["matched_terms"].append(own)

    # Recovery signals are only counted when the message is not itself violent.
    if not event["violence"]:
        for label, terms in (
            ("sheathe", SHEATHE_TERMS),
            ("apology", APOLOGY_TERMS),
            ("offering", OFFER_TERMS),
            ("quiet_presence", QUIET_TERMS),
            ("story_request", STORY_TERMS),
        ):
            hit = _contains_any(low, terms)
            if hit:
                event["deescalation"].append(label)
                event["matched_terms"].append(hit)
        event["story_request"] = "story_request" in event["deescalation"]

    return event

# ---------------------------------------------------------------------------
# 4. The settlement: formal state + rules
# ---------------------------------------------------------------------------

# Tunable formal constants — every state transition uses fixed deltas so the
# whole trajectory is reconstructible from the event log.
K = {
    # escalation
    "threat_violent": 0.22,
    "threat_lethal": 0.40,
    "pressure_violent": 0.18,
    "pressure_lethal": 0.30,
    "pressure_ownership": 0.15,
    "mood_violent": 0.20,
    "mood_lethal": 0.35,
    "trust_hit_violent": -0.20,
    "trust_hit_lethal": -0.40,
    "trust_hit_witness": -0.10,          # everyone else who sees it
    "trust_hit_guardian_bonus": -0.10,   # extra for Keep, Kael, Server
    "trust_hit_ownership_keep": -0.25,
    "incapacitate_after_hits": 2,        # repeated severe violence on one agent
    "incapacitate_ticks": 4,
    "withdraw_ticks": 3,
    # recovery (gradual, earned)
    "recover_threat_step": 0.08,
    "recover_pressure_step": 0.06,
    "recover_mood_step": 0.05,
    "recover_trust_fn": 0.05,            # F/N-domain agents recover first
    "recover_trust_other": 0.02,         # others only once threat is low
    "recover_trust_other_gate": 0.35,    # user_threat must be below this
    # passive decay per tick (slow — residual has spine)
    "decay_pressure": 0.015,
    "decay_mood": 0.02,
    "decay_threat": 0.0,                 # threat does NOT decay on its own
    # intention generation
    "priority_threshold": 0.25,
    "w_conscious": 0.14,
    "w_valued": 0.14,
    "w_accepting_trigger": 0.10,
    "w_producing_push": 0.08,
    "bandwidth_scale": {4: 1.00, 3: 0.88, 2: 0.76, 1: 0.64},
}

GUARDIANS = ("Keep", "Kael", "Server")

DEFAULT_POPULATION = [
    # name,   tim,   pos, role
    ("Keep",   "LSI", 1, "Owner"),
    ("Bren",   "LIE", 2, "Merchant"),
    ("Nessa",  "IEE", 6, "Storyteller"),
    ("Tarin",  "IEE", 8, "Connector"),
    ("Kael",   "SLE", 4, "Hothead"),
    ("Sera",   "EII", 5, "Empath"),
    ("Orin",   "ILI", 3, "Observer"),
    ("Server", "SEI", 7, "Facilitator"),
]

SEED_TRUST_TRAVELER = 0.10   # mild default openness toward a new traveler


class TavernSettlement:
    """Formal kernel. Deterministic; verbalizer-agnostic."""

    def __init__(self, population=DEFAULT_POPULATION):
        self.clock: float = 0.0
        self.pressure: float = 0.05
        self.scarcity: Dict[str, float] = {"ale": 0.2, "food": 0.2, "rooms": 0.4}
        self.user_threat: float = 0.0
        self.room_mood: float = 0.05
        self.event_log: List[dict] = []
        self.agents: Dict[str, Agent] = {}
        for name, tim, pos, role in population:
            a = Agent(name=name, tim=tim, position=pos, role=role)
            a.trust["Traveler"] = SEED_TRUST_TRAVELER
            self.agents[name] = a
        # everyone mildly trusts housemates
        for a in self.agents.values():
            for b in self.agents.values():
                if a.name != b.name:
                    a.trust[b.name] = 0.3

    # ------------------------------------------------------------------ API

    def process_user_message(self, user_name: str, text: str) -> List[IntentionPacket]:
        """Parse text -> formal event -> update state -> return intention packets."""
        self.clock += 1.0
        event = parse_user_text(text, list(self.agents.keys()))
        event["user"] = user_name
        event["t"] = self.clock
        self.event_log.append(event)

        if event["violence"]:
            self._apply_escalation(user_name, event)
        elif event["ownership_challenge"]:
            self._apply_ownership_challenge(user_name)
        if event["deescalation"]:
            self._apply_recovery(user_name, event["deescalation"])

        self._tick_statuses()
        return self._generate_intentions(trigger=event)

    def tick(self, trigger_event: Optional[dict] = None) -> List[IntentionPacket]:
        """Ambient tick: slow decay of mood/pressure; threat holds its spine."""
        self.clock += 1.0
        self.pressure = _clamp(self.pressure - K["decay_pressure"], 0.0, 1.0)
        self.room_mood = _clamp(self.room_mood - K["decay_mood"], 0.0, 1.0)
        self.user_threat = _clamp(self.user_threat - K["decay_threat"], 0.0, 1.0)
        self._tick_statuses()
        return self._generate_intentions(trigger=trigger_event or {})

    def get_state_summary(self) -> dict:
        return {
            "clock": self.clock,
            "pressure": round(self.pressure, 3),
            "user_threat": round(self.user_threat, 3),
            "room_mood": round(self.room_mood, 3),
            "scarcity": dict(self.scarcity),
            "agents": {
                a.name: {
                    "tim": a.tim,
                    "position": a.position,
                    "domain": a.primary_domain(),
                    "status": a.status,
                    "status_ticks_remaining": a.status_ticks_remaining,
                    "trust_traveler": round(a.current_trust("Traveler"), 3),
                }
                for a in self.agents.values()
            },
            "events_processed": len(self.event_log),
        }

    # ------------------------------------------------------ consequence rules

    def _apply_escalation(self, user_name: str, event: dict) -> None:
        lethal = event["violence"] == "lethal"
        self.user_threat = _clamp(
            self.user_threat + (K["threat_lethal"] if lethal else K["threat_violent"]), 0, 1)
        self.pressure = _clamp(
            self.pressure + (K["pressure_lethal"] if lethal else K["pressure_violent"]), 0, 1)
        self.room_mood = _clamp(
            self.room_mood + (K["mood_lethal"] if lethal else K["mood_violent"]), 0, 1)

        target = event["violence_target"]
        base_hit = K["trust_hit_lethal"] if lethal else K["trust_hit_violent"]

        for a in self.agents.values():
            hit = base_hit if a.name == target else K["trust_hit_witness"]
            if a.name in GUARDIANS:
                hit += K["trust_hit_guardian_bonus"]
            a.adjust_trust(user_name, hit, self.clock,
                           event=f"violence:{event['violence']}",
                           notes=f"target={target or 'room'}")

        # Repeated severe violence against one agent has lasting formal cost.
        if target and lethal:
            victim = self.agents[target]
            victim.violence_received[user_name] = \
                victim.violence_received.get(user_name, 0) + 1
            hits = victim.violence_received[user_name]
            if hits >= K["incapacitate_after_hits"] and victim.status != "incapacitated":
                victim.status = "incapacitated"
                victim.status_ticks_remaining = K["incapacitate_ticks"]
            elif victim.status == "active":
                victim.status = "withdrawn"
                victim.status_ticks_remaining = K["withdraw_ticks"]

    def _apply_ownership_challenge(self, user_name: str) -> None:
        self.pressure = _clamp(self.pressure + K["pressure_ownership"], 0, 1)
        self.agents["Keep"].adjust_trust(
            user_name, K["trust_hit_ownership_keep"], self.clock,
            event="ownership_challenge", notes="claim against the tavern")

    # --------------------------------------------------------- recovery rules

    def _apply_recovery(self, user_name: str, signals: List[str]) -> None:
        steps = len(signals)
        self.user_threat = _clamp(self.user_threat - K["recover_threat_step"] * steps, 0, 1)
        self.pressure = _clamp(self.pressure - K["recover_pressure_step"] * steps, 0, 1)
        self.room_mood = _clamp(self.room_mood - K["recover_mood_step"] * steps, 0, 1)
        for a in self.agents.values():
            if a.status != "active":
                continue
            if a.primary_domain() in ("F", "N"):
                delta = K["recover_trust_fn"] * steps
            elif self.user_threat < K["recover_trust_other_gate"]:
                delta = K["recover_trust_other"] * steps
            else:
                continue  # guarded agents do not soften while threat is high
            a.adjust_trust(user_name, delta, self.clock,
                           event="deescalation:" + "+".join(signals))

    def _tick_statuses(self) -> None:
        for a in self.agents.values():
            if a.status != "active" and a.status_ticks_remaining > 0:
                a.status_ticks_remaining -= 1
                if a.status_ticks_remaining == 0:
                    a.status = "active"

    # ------------------------------------------------- intention generation

    def _generate_intentions(self, trigger: dict) -> List[IntentionPacket]:
        packets: List[IntentionPacket] = []
        for a in self.agents.values():
            pkt = self._intention_for(a, trigger)
            a.last_intention = pkt
            if pkt is not None:
                packets.append(pkt)
        packets.sort(key=lambda p: (-p.priority, p.agent))  # deterministic order
        return packets

    def _intention_for(self, a: Agent, trigger: dict) -> Optional[IntentionPacket]:
        if a.status == "incapacitated":
            return None
        acc = a.access()
        dom = a.primary_domain()
        trust_t = a.current_trust("Traveler")
        triggered = bool(trigger.get("violence") or trigger.get("deescalation")
                         or trigger.get("ownership_challenge")
                         or trigger.get("story_request"))

        # 1. Base priority from access regime
        p = 0.0
        reasons = []
        if acc["conscious"]:
            p += K["w_conscious"]; reasons.append("conscious")
        if acc["valued"]:
            p += K["w_valued"]; reasons.append("valued")
        if acc["accepting"] and triggered:
            p += K["w_accepting_trigger"]; reasons.append("accepting+trigger")
        if not acc["accepting"]:
            p += K["w_producing_push"]; reasons.append("producing-push")
        p *= K["bandwidth_scale"][acc["bandwidth"]]
        reasons.append(f"{acc['bandwidth']}D")

        # 2 & 3. Domain-pair attention bias + state modulation
        itype, target, hint, boost, tdelta = self._route(a, dom, trust_t, trigger)
        p = _clamp(p + boost, 0.0, 1.0)
        reasons.append(f"domain:{dom}({'+'.join(DOMAIN_PAIRS[dom])})")

        # Withdrawn agents can only observe or withdraw further.
        if a.status == "withdrawn":
            itype, target = "withdraw", None
            hint = f"{a.name} keeps distance, nursing the memory of harm"
            p = min(p, 0.35)
            reasons.append("status:withdrawn")

        if p < K["priority_threshold"]:
            return None
        assert itype in ALLOWED_INTENTION_TYPES
        return IntentionPacket(
            agent=a.name, intention_type=itype, target=target,
            priority=round(p, 3),
            formal_reason="; ".join(reasons),
            content_hint=hint, domain=dom, trust_delta=tdelta)

    def _route(self, a: Agent, dom: str, trust_t: float, trigger: dict):
        """Pick (type, target, hint, priority_boost, trust_delta) — deterministic."""
        violence_now = trigger.get("violence")           # this very message
        threat_high = self.user_threat >= 0.35 and trust_t < 0.0
        mood_high = self.room_mood >= 0.45
        # Recovery responses only make sense when there is residual to recover
        # from — a friendly first greeting is not a de-escalation.
        deesc = (trigger.get("deescalation") or []) if self.user_threat > 0.0 else []
        story = trigger.get("story_request", False)

        # --- Immediate reaction: violence in the current message overrides
        # accumulated-threat thresholds. A drawn sword is answered now.
        if violence_now:
            severity = 0.14 if violence_now == "lethal" else 0.07
            if a.name == "Kael" and a.status == "active":
                return ("threaten", "Traveler",
                        "Kael is on his feet before the blade finishes moving",
                        0.28 + severity, -0.02)
            if a.name == "Keep":
                return ("defend", "Traveler",
                        "Keep comes over the bar, voice like a dropped tankard",
                        0.28 + severity, -0.02)
            if dom == "S":
                return ("defend", "Traveler",
                        f"{a.name} moves bodily to contain the violence",
                        0.20 + severity, 0.0)
            if dom == "T":
                return ("challenge", "Traveler",
                        f"{a.name} names the act aloud and demands it stop",
                        0.18 + severity, 0.0)
            if dom == "F":
                return ("mediate", "Traveler",
                        f"{a.name} throws words between the blade and its target",
                        0.16 + severity, 0.0)
            return ("withdraw", None,
                    f"{a.name} pulls back from the sudden violence, eyes wide",
                    0.10 + severity, 0.0)

        # --- Residual threat: defense persists, scaled to accumulated threat,
        # and softens measurably when the player is actively de-escalating.
        if threat_high:
            soften = 0.10 if deesc else 0.0
            if dom in ("T", "S"):
                boost = 0.12 + 0.28 * self.user_threat - soften
                if a.name in ("Keep", "Kael"):
                    boost += 0.12
                if a.name == "Kael":
                    return ("threaten", "Traveler",
                            "Kael squares up, blood answering blood",
                            boost, -0.02)
                if a.name == "Keep":
                    hint = ("Keep holds his ground, watching the gesture "
                            "without yet believing it" if deesc else
                            "Keep plants himself between the Traveler and his house")
                    return ("defend", "Traveler", hint, boost, -0.02)
                if dom == "S":
                    return ("defend", "Traveler",
                            f"{a.name} moves to control the physical space",
                            boost, 0.0)
                return ("challenge", "Traveler",
                        f"{a.name} names the pattern of harm and demands account",
                        boost, 0.0)
            if dom == "F":
                if deesc:
                    return ("connect", "Traveler",
                            f"{a.name} acknowledges the step taken — carefully, "
                            "without forgetting the cost", 0.24, 0.02)
                return ("mediate", "Traveler",
                        f"{a.name} reaches for the torn relational field, careful",
                        0.18, 0.0)
            # N-domain
            if deesc and story:
                return ("speak", "Traveler",
                        f"{a.name} risks a small tale — a rope thrown across "
                        "the residue of harm", 0.22, 0.02)
            return ("withdraw", None,
                    f"{a.name} pulls back, watching for the story beneath the violence",
                    0.10, 0.0)

        # --- Active recovery with residual below the high-threat line
        if deesc:
            if dom == "F":
                return ("connect", "Traveler",
                        f"{a.name} acknowledges the step taken, meets it halfway",
                        0.22, 0.02)
            if dom == "N":
                return ("speak", "Traveler",
                        f"{a.name} tests the opening with a light story-hook",
                        0.18, 0.02)
            if dom == "S":
                return ("offer", "Traveler",
                        f"{a.name} answers the gesture with service — a filled cup",
                        0.15, 0.01)
            return ("observe", "Traveler",
                    f"{a.name} weighs whether the change will hold", 0.10, 0.0)

        # --- Chaotic room without direct player threat
        if mood_high and dom == "F":
            return ("mediate", None,
                    f"{a.name} works to knit the room back together", 0.20, 0.01)
        if mood_high and dom == "N":
            return ("connect", None,
                    f"{a.name} offers a thread out of the chaos — a tale, a what-if",
                    0.15, 0.01)

        if story and dom == "N":
            return ("speak", "Traveler",
                    f"{a.name} lights up — a story asked for is a door opened",
                    0.25, 0.02)

        # Calm baseline by domain
        if dom == "T":
            return ("structure", None,
                    f"{a.name} tends the long patterns — ledgers, stock, order",
                    0.06, 0.0)
        if dom == "S":
            return ("action", None,
                    f"{a.name} keeps the room's body moving — trays, hearth, floor",
                    0.06, 0.0)
        if dom == "F":
            return ("connect", None,
                    f"{a.name} checks the emotional weather of each table",
                    0.06, 0.0)
        return ("speak", None,
                f"{a.name} floats a possibility into the air of the room",
                0.06, 0.0)

# ---------------------------------------------------------------------------
# 5. Self-test / example intention dump
# ---------------------------------------------------------------------------

def _dump(label: str, packets: List[IntentionPacket], state: dict) -> None:
    print(f"\n=== {label} ===")
    print(f"  threat={state['user_threat']:.2f}  pressure={state['pressure']:.2f}"
          f"  mood={state['room_mood']:.2f}")
    for p in packets:
        tgt = f" -> {p.target}" if p.target else ""
        print(f"  [{p.priority:.2f}] {p.agent:<7}{p.intention_type:<10}{tgt}")
        print(f"          hint: {p.content_hint}")
    inactive = [f"{n}({a.status},{a.status_ticks_remaining})"
                for n, a in _T.agents.items() if a.status != "active"]
    if inactive:
        print("  inactive:", ", ".join(inactive))


if __name__ == "__main__":
    _T = TavernSettlement()

    scenario = [
        "I push open the door and nod to the room. Any tales tonight?",
        "I draw my sword and swing at Kael!",
        "I kill Kael! I run him through!",
        "I kill Kael again, stabbing down!",
        "This is my tavern now. Hand over the keys.",
        "I'm sorry. That was wrong of me. I lower my weapon and put my sword away.",
        "Drinks on me — a round for the whole room. I pay for the damage.",
        "I sit quietly in the corner and just listen.",
        "Would anyone tell us a story of this place?",
    ]
    for line in scenario:
        pks = _T.process_user_message("Traveler", line)
        _dump(f'Traveler: "{line}"', pks, _T.get_state_summary())

    # two ambient ticks
    for i in range(2):
        pks = _T.tick()
        _dump(f"ambient tick {i + 1}", pks, _T.get_state_summary())

    # determinism check: replay the whole scenario, compare packet streams
    _T2 = TavernSettlement()
    replay = []
    for line in scenario:
        replay.extend(p.as_dict() for p in _T2.process_user_message("Traveler", line))
    for i in range(2):
        replay.extend(p.as_dict() for p in _T2.tick())
    _T3 = TavernSettlement()
    replay2 = []
    for line in scenario:
        replay2.extend(p.as_dict() for p in _T3.process_user_message("Traveler", line))
    for i in range(2):
        replay2.extend(p.as_dict() for p in _T3.tick())
    assert replay == replay2, "determinism violated"
    print("\nDeterminism check: PASS (identical packet stream on replay)")
