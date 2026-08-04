"""
Living Tavern success-criteria tests (Spec §8) — stdlib only, deterministic.
Run: python3 test_living_tavern.py
"""

from living_tavern import LivingTavern, SessionStore
from verbalizer import DeterministicVerbalizer


def dicts(packets):
    return [p.as_dict() for p in packets]


def run(tavern, script):
    out = []
    for kind, arg in script:
        if kind == "user":
            out.extend(dicts(tavern.step_user(arg)))
        else:
            out.extend(dicts(tavern.step_ambient()))
    return out


PEACE = [("user", "Any tales tonight? Drinks on me."),
         ("ambient", None), ("user", "Tell us a story of this place."),
         ("ambient", None)]
VIOLENCE = [("user", "I draw my sword and swing at Kael!"),
            ("user", "I kill Kael! I run him through!"),
            ("ambient", None), ("ambient", None)]
RECOVERY = [("user", "I'm sorry. I was wrong. I put my sword away."),
            ("user", "Drinks on me — I pay for the damage."),
            ("user", "I sit quietly in the corner and just listen."),
            ("user", "Would anyone tell us a story of this place?")]


def test_1_arrival_living_room():
    """Criterion 1: clean seed; NPCs already interacting with each other."""
    t = LivingTavern()
    pkts = dicts(t.step_ambient())
    npc_npc = [p for p in pkts if p["target"] not in (None, "Traveler")
               and p["agent"] != "Traveler"]
    assert npc_npc, "arrival round must contain NPC->NPC intentions"
    assert t.state()["user_threat"] == 0.0


def test_3_npc_npc_are_formal_events():
    """Criterion 3: NPC-NPC interactions update directed trust + event log."""
    t = LivingTavern()
    before = {a: dict(t.settlement.agents[a].trust) for a in t.settlement.agents}
    for _ in range(8):
        t.step_ambient()
    after = {a: dict(t.settlement.agents[a].trust) for a in t.settlement.agents}
    changed = any(
        before[a].get(b) != after[a].get(b)
        for a in after for b in after[a] if b != "Traveler")
    assert changed, "NPC->NPC directed trust must evolve"
    npc_events = [e for e in t.transcript_log() if e.get("kind") == "npc"]
    assert len(npc_events) >= 16, "NPC events must be first-class in the log"


def test_2_and_4_graduated_history_dependent_divergence():
    """Criteria 2+4: different inputs -> different trajectories from one seed;
    change is graduated (peaceful room stays near seed, violent room doesn't)."""
    a, b = LivingTavern(), LivingTavern()
    run(a, PEACE)
    run(b, VIOLENCE)
    sa, sb = a.state(), b.state()
    assert sa["user_threat"] == 0.0 and sb["user_threat"] > 0.5
    assert sb["pressure"] > sa["pressure"]
    assert sa["npc_trust"] != sb["npc_trust"], \
        "user history must perturb NPC-NPC dynamics too"
    # graduated: one violent line moves the room less than two
    c = LivingTavern(); c.step_user("I draw my sword and swing at Kael!")
    assert 0.0 < c.state()["user_threat"] < sb["user_threat"]


def test_5_residual_has_spine():
    """Criterion 4/6: residual does not decay away on ambient ticks alone."""
    t = LivingTavern()
    run(t, VIOLENCE)
    threat_after_violence = t.state()["user_threat"]
    for _ in range(10):
        t.step_ambient()
    assert t.state()["user_threat"] == threat_after_violence, \
        "threat must hold its spine through ambient ticks"
    kael = t.settlement.agents["Kael"]
    assert any(e.get("violence") == "lethal" for e in t.transcript_log()
               if e.get("kind") != "npc")
    assert kael.violence_received.get("Traveler", 0) >= 1


def test_6_recovery_is_earned():
    """Criterion 5: repeated genuine de-escalation measurably recovers."""
    t = LivingTavern()
    run(t, VIOLENCE)
    hi = t.state()
    run(t, RECOVERY)
    lo = t.state()
    assert lo["user_threat"] < hi["user_threat"]
    assert lo["agents"]["Sera"]["trust_traveler"] > \
        hi["agents"]["Sera"]["trust_traveler"], "F-domain recovers first"
    # but not a free pass: one apology after lethal violence is not clean
    t2 = LivingTavern()
    run(t2, VIOLENCE)
    t2.step_user("I'm sorry.")
    assert t2.state()["user_threat"] > 0.3, "recovery is gradual, not instant"


def test_7_session_isolation_and_clean_reseed():
    """Criteria 6+7: independent sessions; refresh/reset -> clean seed."""
    store = SessionStore()
    sid_a, ta = store.new_session()
    sid_b, tb = store.new_session()
    run(ta, VIOLENCE)
    # Visitor B untouched by A's residual
    assert tb.state()["user_threat"] == 0.0
    assert store.get(sid_b).state()["events_processed"] == 0
    # Explicit reset returns A to the clean seed
    ta2 = store.reset(sid_a)
    assert ta2.state()["user_threat"] == 0.0
    assert ta2.state()["events_processed"] == 0
    # A fresh session equals another fresh session (same locked seed)
    _, tc = store.new_session()
    assert tc.state() == LivingTavern().state()


def test_determinism_exact_replay():
    """Tavern-layer replay: identical input history -> identical packets."""
    script = PEACE + VIOLENCE + RECOVERY + [("ambient", None)] * 3
    s1 = run(LivingTavern(), script)
    s2 = run(LivingTavern(), script)
    assert s1 == s2, "exact replay must hold at the Living Tavern layer"


def test_session_store_eviction():
    clock = [0.0]
    store = SessionStore(ttl_seconds=10, max_sessions=3, _now=lambda: clock[0])
    sid1, _ = store.new_session()
    clock[0] = 5.0
    sid2, _ = store.new_session()
    clock[0] = 12.0                      # sid1 idle > ttl
    assert store.get(sid1) is None
    assert store.get(sid2) is not None
    store.new_session(); store.new_session()   # hit max_sessions
    assert len(store) <= 3


def test_verbalizer_non_causal():
    """The verbalizer renders lines and touches no formal state."""
    t = LivingTavern()
    pkts = dicts(t.step_user("I draw my sword and swing at Kael!"))
    before = t.state()
    lines = DeterministicVerbalizer().render(pkts, before)
    assert lines and all("speaker" in l and "line" in l for l in lines)
    assert t.state() == before, "verbalizer must not alter formal state"


if __name__ == "__main__":
    import sys
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
