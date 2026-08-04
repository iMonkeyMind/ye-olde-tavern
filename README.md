[README.md](https://github.com/user-attachments/files/30683643/README.md)
# Living Tavern

Delivery against *Living Tavern — Specification for Fable, v1.0*. The frozen
kernel (`tavern_kernel.py`) is included byte-for-byte unmodified; everything
new sits above it.

## Files

`tavern_kernel.py` is the frozen denser engine, untouched. `living_tavern.py`
is the Living Tavern layer: `LivingTavern` wraps one settlement and runs the
simultaneous NPC–NPC interaction round on every user step and every ambient
tick, and `SessionStore` provides clean-seed multi-session isolation.
`verbalizer.py` holds the non-causal verbalizers: `DeterministicVerbalizer`
(no dependencies, always available) and `GrokVerbalizer` (drop-in for the
existing xAI pipeline, activated by setting `XAI_API_KEY`; on any failure it
falls back to the deterministic renderer so the room never stalls). `app.py`
is the FastAPI web layer with an embedded chat page.
`test_living_tavern.py` pins the spec's seven success criteria plus
exact replay and verbalizer non-causality.

## Run

The formal layer and tests need only the standard library:

```
python3 test_living_tavern.py
```

The web layer needs FastAPI:

```
pip install fastapi "uvicorn[standard]" httpx
uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
```

Set `XAI_API_KEY` to route verbalization through Grok; leave it unset to use
the deterministic renderer.

## How the spec is satisfied

Every new page load calls `POST /session`, which builds a fresh
`LivingTavern` from the locked seed; the session id lives only in browser
JS memory, so a full refresh discards it and re-seeds (Spec §2). Sessions
never share state, and `POST /reset` returns a session to the clean seed
explicitly. A locked `SEED_RELATIONSHIPS` table gives every session the same
opening directed relationships (Spec §5), so trajectories diverge only
through interaction history.

Simultaneity (Spec §3): each step — user message or ambient tick — runs one
NPC–NPC round in which initiators rotate deterministically through the cast
and act toward housemates under locked rules. Under calm, agents bond with
their highest-trust housemate in their domain's register; under high room
pressure or mood, T/S agents press their lowest-trust housemate, F agents
mediate the most frictional pair, and the interactions feed pressure and
mood back. Every NPC–NPC interaction adjusts directed trust through the
kernel's own `adjust_trust` bookkeeping and lands in the settlement event
log as a first-class event, so the user's actions (which shift regimes and
statuses) perturb the NPC–NPC dynamics and vice versa.

Residual rules are the kernel's, unsoftened (Spec §6): the Tavern layer
never writes `user_threat` and never bypasses consequence, status, or
recovery rules. Threat holds its spine through ambient ticks; recovery
remains gradual and earned; withdrawn agents only observe; incapacitated
agents emit nothing.

Determinism: no randomness and no wall clock anywhere in the formal layer.
A session's packet stream is an exact function of the seed and the ordered
input history, verified by `test_determinism_exact_replay`.

## Success criteria → tests

Criterion 1 (arrive to a living room): `test_1_arrival_living_room`.
Criteria 2 and 4 (graduated, history-dependent trajectories):
`test_2_and_4_graduated_history_dependent_divergence`. Criterion 3
(simultaneous NPC–NPC as formal events): `test_3_npc_npc_are_formal_events`.
Residual weight: `test_5_residual_has_spine`. Criterion 5 (earned
recovery): `test_6_recovery_is_earned`. Criteria 6 and 7 (clean re-seed,
independent visitors): `test_7_session_isolation_and_clean_reseed`.

## Deployment note (Railway)

The in-memory `SessionStore` is correct for a single replica, per Spec §7.
If you ever scale to multiple replicas, either pin sessions to a replica
(sticky routing) or move the store behind a shared serializer — the
`LivingTavern` trajectory is fully reconstructible from its input history,
so event-log replay is a valid persistence strategy.
