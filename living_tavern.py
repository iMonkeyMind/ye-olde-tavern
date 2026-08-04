"""
Living Tavern — multi-session, simultaneous-interaction layer
=============================================================

Sits on top of the frozen `tavern_kernel.py` (the pure formal core).
Implements the Living Tavern Specification v1.0:

  * Clean-seed sessions: every session is an independent TavernSettlement
    seeded identically; divergence comes only from interaction history.
  * Simultaneous NPC–NPC interaction: on every step, active agents
    generate formal intentions toward one another. These are first-class
    formal events — they update directed trust, pressure and mood through
    the same deterministic bookkeeping as user events, and they are
    appended to the settlement's event log.
  * The user is one more participant in an already-living room.
  * Fully deterministic: no randomness, no wall clock. A session's
    trajectory is an exact function of (seed, ordered input history).
    Exact replay therefore holds at the Tavern layer too.

The frozen kernel is imported, never modified. All Living-Tavern rules
live in the locked constant table `LK` below, in the same style as the
kernel's `K` table: fixed deltas, reconstructible trajectories.

Residual rules are NOT softened here. NPC–NPC dynamics ride on top of —
and are modulated by — the kernel's threat / pressure / mood state, but
never write user_threat and never bypass the kernel's consequence or
recovery rules.
"""

from __future__ import annotations

import itertools
import time
from typing import Dict, List, Optional, Tuple

from tavern_kernel import (
    Agent,
    IntentionPacket,
    TavernSettlement,
    DOMAIN_PAIRS,
    _clamp,
)

# ---------------------------------------------------------------------------
# 1. Locked Living-Tavern constants (deterministic; same spirit as kernel K)
# ---------------------------------------------------------------------------

LK = {
    # how many NPC initiators act per ambient step
    "initiators_per_step": 2,
    # regime thresholds read from kernel state (never written here)
    "pressure_friction_gate": 0.40,   # room pressure at/above -> friction regime
    "mood_friction_gate": 0.45,
    # NPC->NPC trust micro-deltas (small: the room drifts, it doesn't lurch)
    "bond_step": 0.02,                # positive interaction
    "friction_step": -0.03,           # challenge under pressure
    "mediate_heal_step": 0.015,       # mediation heals the frictional pair
    "mood_bond_relief": 0.01,         # each bonding interaction eases mood
    "mood_friction_cost": 0.015,      # each friction interaction feeds mood
    "pressure_mediate_relief": 0.01,
    # priority shaping for NPC-NPC packets (kept below user-directed urgency)
    "npc_base_priority": 0.30,
    "npc_friction_bonus": 0.10,
    "npc_priority_trust_scale": 0.10,  # + trust * scale for bonds
    "npc_priority_cap": 0.55,
    # withdrawn agents only observe at low priority
    "withdrawn_observe_priority": 0.28,
}

# Deterministic canonical agent order = seed population order.
# (dict preserves insertion order; the kernel seeds from DEFAULT_POPULATION.)

# Locked seed relationships (Spec §5): identical for every new session, so
# the room opens with structure — bonds, working ties, one standing friction
# — and divergence comes only from interaction history. Directed deltas
# applied on top of the kernel's uniform 0.3 baseline at t=0.
SEED_RELATIONSHIPS: Tuple[Tuple[str, str, float], ...] = (
    ("Keep",   "Server", 0.25), ("Server", "Keep",   0.25),  # the house team
    ("Nessa",  "Tarin",  0.20), ("Tarin",  "Nessa",  0.20),  # story & thread
    ("Bren",   "Keep",   0.15), ("Keep",   "Bren",   0.10),  # commerce
    ("Sera",   "Kael",   0.15), ("Kael",   "Sera",   0.10),  # the empath's project
    ("Orin",   "Nessa",  0.10),                              # quiet audience
    ("Kael",   "Orin",  -0.15), ("Orin",   "Kael",  -0.10),  # standing friction
    ("Server", "Sera",   0.10), ("Sera",   "Server", 0.10),
)


# ---------------------------------------------------------------------------
# 2. The Living Tavern: one session's living room
# ---------------------------------------------------------------------------

class LivingTavern:
    """One session: frozen-kernel settlement + simultaneous NPC-NPC loop.

    Public API (used by the web layer and tests):
        step_user(text)  -> List[IntentionPacket]   user event + NPC-NPC round
        step_ambient()   -> List[IntentionPacket]   ambient tick + NPC-NPC round
        state()          -> dict                    summary incl. NPC-NPC trust
        transcript_log() -> list                    full ordered event log
    """

    USER = "Traveler"

    def __init__(self) -> None:
        self.settlement = TavernSettlement()          # clean locked seed
        self.npc_step_counter = 0                     # drives initiator rotation
        self._names: List[str] = list(self.settlement.agents.keys())
        for src, dst, delta in SEED_RELATIONSHIPS:    # Spec §5 seed histories
            self.settlement.agents[src].adjust_trust(
                dst, delta, 0.0, event="seed_relationship")

    # ------------------------------------------------------------------ API

    def step_user(self, text: str) -> List[IntentionPacket]:
        """User message: kernel event first, then one simultaneous NPC round."""
        user_packets = self.settlement.process_user_message(self.USER, text)
        npc_packets = self._npc_round()
        return self._merge(user_packets, npc_packets)

    def step_ambient(self) -> List[IntentionPacket]:
        """Ambient tick: kernel decay/statuses, then one NPC round."""
        ambient_packets = self.settlement.tick()
        npc_packets = self._npc_round()
        return self._merge(ambient_packets, npc_packets)

    def state(self) -> dict:
        s = self.settlement.get_state_summary()
        s["npc_trust"] = {
            a.name: {
                other: round(v, 3)
                for other, v in sorted(a.trust.items())
                if other != self.USER
            }
            for a in self.settlement.agents.values()
        }
        s["npc_steps"] = self.npc_step_counter
        return s

    def transcript_log(self) -> List[dict]:
        return list(self.settlement.event_log)

    # ------------------------------------------------- NPC-NPC formal round

    def _npc_round(self) -> List[IntentionPacket]:
        """One simultaneous round: N initiators act toward housemates.

        Deterministic: initiators rotate through the canonical order by
        step counter; targets are chosen by locked trust/regime rules with
        name tie-breaks. Events are appended to the kernel event log and
        adjust directed NPC trust through the kernel's own bookkeeping.
        """
        packets: List[IntentionPacket] = []
        st = self.settlement
        n = len(self._names)
        for k in range(LK["initiators_per_step"]):
            idx = (self.npc_step_counter * LK["initiators_per_step"] + k) % n
            initiator = st.agents[self._names[idx]]
            pkt = self._npc_intention(initiator)
            if pkt is not None:
                packets.append(pkt)
        self.npc_step_counter += 1
        return packets

    def _npc_intention(self, a: Agent) -> Optional[IntentionPacket]:
        st = self.settlement
        if a.status == "incapacitated":
            return None
        dom = a.primary_domain()

        if a.status == "withdrawn":
            pkt = IntentionPacket(
                agent=a.name, intention_type="observe", target=None,
                priority=LK["withdrawn_observe_priority"],
                formal_reason="npc; status:withdrawn",
                content_hint=f"{a.name} watches the room from a guarded distance",
                domain=dom, trust_delta=0.0)
            self._log_npc_event(a.name, None, "observe", 0.0)
            return pkt

        friction = (st.pressure >= LK["pressure_friction_gate"]
                    or st.room_mood >= LK["mood_friction_gate"])

        if friction and dom in ("T", "S"):
            # Friction regime: hard-domain agents press their lowest-trust
            # housemate — the room's tension surfaces between the NPCs.
            target = self._extreme_housemate(a, lowest=True)
            delta = LK["friction_step"]
            a.adjust_trust(target.name, delta, st.clock,
                           event="npc_friction",
                           notes=f"{a.name} presses {target.name} under room pressure")
            target.adjust_trust(a.name, delta / 2, st.clock,
                                event="npc_friction_received")
            st.room_mood = _clamp(
                st.room_mood + LK["mood_friction_cost"], 0.0, 1.0)
            itype = "challenge" if dom == "T" else "action"
            hint = (f"{a.name} rounds on {target.name} — the room's pressure "
                    f"finds the nearest seam")
            self._log_npc_event(a.name, target.name, itype, delta)
            return self._npc_packet(a, itype, target.name, hint, dom,
                                    LK["npc_friction_bonus"], delta)

        if friction and dom == "F":
            # Mediators work the most frictional pair back together.
            pair = self._most_frictional_pair(exclude=a.name)
            if pair is not None:
                x, y = pair
                heal = LK["mediate_heal_step"]
                st.agents[x].adjust_trust(y, heal, st.clock, event="npc_mediated")
                st.agents[y].adjust_trust(x, heal, st.clock, event="npc_mediated")
                st.pressure = _clamp(
                    st.pressure - LK["pressure_mediate_relief"], 0.0, 1.0)
                hint = (f"{a.name} steps between {x} and {y}, "
                        f"stitching the strained thread")
                self._log_npc_event(a.name, f"{x}+{y}", "mediate", heal)
                return self._npc_packet(a, "mediate", x, hint, dom,
                                        LK["npc_friction_bonus"], heal)

        # Calm (or N-domain under friction): bond with highest-trust housemate.
        target = self._extreme_housemate(a, lowest=False)
        delta = LK["bond_step"]
        a.adjust_trust(target.name, delta, st.clock,
                       event="npc_bond",
                       notes=f"{a.name} -> {target.name}")
        target.adjust_trust(a.name, delta / 2, st.clock, event="npc_bond_received")
        st.room_mood = _clamp(st.room_mood - LK["mood_bond_relief"], 0.0, 1.0)
        itype, hint = self._bond_flavor(a, target, dom)
        self._log_npc_event(a.name, target.name, itype, delta)
        boost = a.current_trust(target.name) * LK["npc_priority_trust_scale"]
        return self._npc_packet(a, itype, target.name, hint, dom, boost, delta)

    # ----------------------------------------------------------- selectors

    def _housemates(self, a: Agent) -> List[Agent]:
        return [self.settlement.agents[n] for n in self._names
                if n != a.name
                and self.settlement.agents[n].status != "incapacitated"]

    def _extreme_housemate(self, a: Agent, lowest: bool) -> Agent:
        mates = self._housemates(a)
        key = lambda m: (a.current_trust(m.name), m.name)
        return min(mates, key=key) if lowest else max(
            mates, key=lambda m: (a.current_trust(m.name), m.name))

    def _most_frictional_pair(self, exclude: str) -> Optional[Tuple[str, str]]:
        """Ordered pair (x, y) with the lowest directed trust x->y."""
        best: Optional[Tuple[str, str]] = None
        best_v = None
        for x, y in itertools.permutations(self._names, 2):
            if exclude in (x, y):
                continue
            ax, ay = self.settlement.agents[x], self.settlement.agents[y]
            if ax.status == "incapacitated" or ay.status == "incapacitated":
                continue
            v = ax.current_trust(y)
            if best_v is None or (v, x, y) < (best_v, *best):
                best_v, best = v, (x, y)
        return best

    @staticmethod
    def _bond_flavor(a: Agent, target: Agent, dom: str) -> Tuple[str, str]:
        if dom == "N":
            return ("speak",
                    f"{a.name} spins a what-if toward {target.name}, "
                    f"fishing for the answering spark")
        if dom == "F":
            return ("connect",
                    f"{a.name} checks in on {target.name} with a quiet word")
        if dom == "S":
            return ("offer",
                    f"{a.name} slides something across to {target.name} — "
                    f"a cup, a plate, a small kept promise")
        return ("structure",
                f"{a.name} squares away a small matter with {target.name} — "
                f"tallies, stock, the day's order")

    # ------------------------------------------------------------ plumbing

    def _npc_packet(self, a: Agent, itype: str, target: Optional[str],
                    hint: str, dom: str, boost: float,
                    tdelta: float) -> IntentionPacket:
        p = _clamp(LK["npc_base_priority"] + boost, 0.0, LK["npc_priority_cap"])
        return IntentionPacket(
            agent=a.name, intention_type=itype, target=target,
            priority=round(p, 3),
            formal_reason=f"npc; domain:{dom}({'+'.join(DOMAIN_PAIRS[dom])})",
            content_hint=hint, domain=dom, trust_delta=round(tdelta, 3))

    def _log_npc_event(self, agent: str, target: Optional[str],
                       itype: str, delta: float) -> None:
        self.settlement.event_log.append({
            "kind": "npc",
            "t": self.settlement.clock,
            "agent": agent,
            "target": target,
            "intention_type": itype,
            "trust_delta": round(delta, 4),
        })

    @staticmethod
    def _merge(a: List[IntentionPacket],
               b: List[IntentionPacket]) -> List[IntentionPacket]:
        merged = list(a) + list(b)
        merged.sort(key=lambda p: (-p.priority, p.agent))
        return merged


# ---------------------------------------------------------------------------
# 3. Session store: clean-seed isolation (Spec §2, §7)
# ---------------------------------------------------------------------------

class SessionStore:
    """In-memory session_id -> LivingTavern. Correct for a single replica.

    * new_session() always returns a fresh clean-seed LivingTavern.
    * Sessions never share formal state.
    * Idle sessions are evicted after `ttl_seconds` (checked lazily).
    * `max_sessions` guards memory; oldest-idle is evicted first.
    """

    def __init__(self, ttl_seconds: int = 3600, max_sessions: int = 500,
                 _now=time.monotonic) -> None:
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        self._now = _now
        self._sessions: Dict[str, LivingTavern] = {}
        self._last_seen: Dict[str, float] = {}
        self._counter = 0

    def new_session(self) -> Tuple[str, LivingTavern]:
        self._evict()
        self._counter += 1
        sid = f"tv-{self._counter:08d}"
        tavern = LivingTavern()
        self._sessions[sid] = tavern
        self._last_seen[sid] = self._now()
        return sid, tavern

    def get(self, sid: str) -> Optional[LivingTavern]:
        self._evict()
        t = self._sessions.get(sid)
        if t is not None:
            self._last_seen[sid] = self._now()
        return t

    def reset(self, sid: str) -> LivingTavern:
        """Explicit reset: same id, brand-new clean seed."""
        tavern = LivingTavern()
        self._sessions[sid] = tavern
        self._last_seen[sid] = self._now()
        return tavern

    def drop(self, sid: str) -> None:
        self._sessions.pop(sid, None)
        self._last_seen.pop(sid, None)

    def _evict(self) -> None:
        now = self._now()
        stale = [s for s, t in self._last_seen.items() if now - t > self.ttl]
        for s in stale:
            self.drop(s)
        while len(self._sessions) >= self.max_sessions:
            oldest = min(self._last_seen, key=self._last_seen.get)
            self.drop(oldest)

    def __len__(self) -> int:
        return len(self._sessions)
