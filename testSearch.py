"""
test_terminal_search.py
=======================
Quick sanity-check suite for terminal_search.py.

Run with:
    python test_terminal_search.py
"""

import copy
import sys

from testing import create_random_game
from StateSearch import (
    _all_possible_plays,
    _all_sacrifice_sets,
    _all_defender_orderings,
    generate_child_states,
    probe_terminal,
)


# ── helpers ──────────────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
_results = []

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    _results.append(condition)

def section(title):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ── 1. pure enumerators (no game state) ──────────────────────────────────────

section("_all_possible_plays")

class _FakeCard:
    """Minimal card stand-in for testing cost logic."""
    def __init__(self, name, energy=1, life=0, sac=0):
        self.name  = name
        self.costs = {'energy': energy, 'life': life, 'sacCost': sac}
    def __repr__(self):
        return self.name

c1 = _FakeCard("A", energy=1)
c2 = _FakeCard("B", energy=2)
c3 = _FakeCard("C", energy=3)

plays_3e = _all_possible_plays([c1, c2, c3], energy_budget=3, life_total=20, sac_budget=0)
check("budget=3 allows A, B, C individually",
      any(p == [c1] for p in plays_3e) and
      any(p == [c2] for p in plays_3e) and
      any(p == [c3] for p in plays_3e))
check("budget=3 allows A+B (costs 3 total)",    any(set(p) == {c1, c2} for p in plays_3e))
check("budget=3 forbids A+C (costs 4 total)",   all(set(p) != {c1, c3} for p in plays_3e))
check("budget=0 returns empty list",             _all_possible_plays([c1], 0, 20, 0) == [])

expensive = _FakeCard("X", energy=1, life=19)  # costs 19 life
check("life constraint blocks card when life == cost",
      _all_possible_plays([expensive], 10, 19, 0) == [])  # cost < life required, 19 < 19 is False
check("life constraint allows card when life > cost",
      len(_all_possible_plays([expensive], 10, 20, 0)) == 1)

section("_all_sacrifice_sets")

s1 = _FakeCard("S1"); s1.atk = 2
s2 = _FakeCard("S2"); s2.atk = 3
s3 = _FakeCard("S3"); s3.atk = 1

sacs_2 = _all_sacrifice_sets([s1, s2, s3], required_sac_total=2)
check("required=0 returns empty list",           _all_sacrifice_sets([s1], 0) == [])
check("required=2 includes S1 (atk=2) alone",   any(s1 in s for s in sacs_2))
check("required=2 includes S3+S1 combo",
      any(s3 in s and s1 in s for s in sacs_2))

section("_all_defender_orderings")

d1 = _FakeCard("D1"); d2 = _FakeCard("D2"); d3 = _FakeCard("D3")

check("0 attackers → empty list",               _all_defender_orderings([d1, d2], 0) == [])
check("1 attacker, 2 defenders → 2 orderings",  len(_all_defender_orderings([d1, d2], 1)) == 2)
check("2 attackers, 3 defenders → 6 orderings", len(_all_defender_orderings([d1, d2, d3], 2)) == 6)
check("all orderings are distinct",
      len(set(tuple(o) for o in _all_defender_orderings([d1, d2, d3], 2))) == 6)


# ── 2. generate_child_states ──────────────────────────────────────────────────

section("generate_child_states — play phase (fresh)")

game = create_random_game()
active = game.p1 if game.turnNumber % 2 == 0 else game.p2

children = generate_child_states(game, 'play')
check("returns a non-empty list",            len(children) > 0)
check("every child is a tuple",              all(isinstance(c, tuple) for c in children))
check("every child starts with a Game",      all(hasattr(c[0], 'p1') for c in children))
check("pass (empty play) is always present", # at least one child where nothing was played
      any(len(c) >= 2 and c[1] in ('declareAttacks', 'play') for c in children))

section("generate_child_states — declareAttacks")

# Force a state with cards on the battlefield for a meaningful test.
declare_game = copy.deepcopy(game)
declare_children = generate_child_states(declare_game, 'declareAttacks')
check("returns a list",                      isinstance(declare_children, list))
# "no attack" option should always exist
has_no_attack = any(
    len(c) >= 2 and c[1] == 'play' for c in declare_children
)
check("no-attack (pass) option always present", has_no_attack)

section("generate_child_states — combat phase")

combat_game = copy.deepcopy(game)
active_combat = combat_game.p1 if combat_game.turnNumber % 2 == 0 else combat_game.p2
if active_combat.battlefield:
    # Provide the 'attackers' sentinel to trigger defender enumeration.
    attackers_node = ['attackers'] + list(active_combat.battlefield[:1])
    combat_children = generate_child_states(combat_game, 'combat', pending_events=attackers_node)
    check("combat with 1 attacker returns children",  len(combat_children) > 0)
    check("combat children are tuples",               all(isinstance(c, tuple) for c in combat_children))
else:
    print("  [SKIP] no cards on battlefield — skipping combat sub-test")


# ── 3. probe_terminal ─────────────────────────────────────────────────────────

section("probe_terminal — immediate terminal detection")

# Build a state where p1 is already dead.
dead_p1_game = copy.deepcopy(game)
dead_p1_game.p1.life = -1
check("p1 dead → returns -1.0 for pID=0",   probe_terminal((dead_p1_game, 'play'), pID=0) == -1.0)
check("p1 dead → returns +1.0 for pID=1",   probe_terminal((dead_p1_game, 'play'), pID=1) == +1.0)

dead_p2_game = copy.deepcopy(game)
dead_p2_game.p2.life = -1
check("p2 dead → returns +1.0 for pID=0",   probe_terminal((dead_p2_game, 'play'), pID=0) == +1.0)
check("p2 dead → returns -1.0 for pID=1",   probe_terminal((dead_p2_game, 'play'), pID=1) == -1.0)

both_dead_game = copy.deepcopy(game)
both_dead_game.p1.life = -1
both_dead_game.p2.life = -1
check("both dead → returns 0.0",             probe_terminal((both_dead_game, 'play'), pID=0) == 0.0)

section("probe_terminal — depth=0 on live game")

probe_terminal.depth_limit_hits = 0
result_d0 = probe_terminal((game, 'play'), pID=0, depth=0)
check("depth=0 on live game returns None",   result_d0 is None)
check("depth_limit_hits incremented",        probe_terminal.depth_limit_hits == 1)

section("probe_terminal — shallow search on live game")

# depth=3 is cheap; should complete quickly.
probe_terminal.depth_limit_hits = 0
result_d3 = probe_terminal((game, 'play'), pID=0, depth=3, gamma=0.95)
check("depth=3 returns float or None",       result_d3 is None or isinstance(result_d3, float))
if result_d3 is not None:
    check("value in (-1, 1]",               -1.0 <= result_d3 <= 1.0,
          f"got {result_d3:.4f}")

# ── summary ────────────────────────────────────────────────────t───────────────

section("Summary")
passed = sum(_results)
total  = len(_results)
print(f"  {passed}/{total} checks passed.\n")
if passed < total:
    sys.exit(1)