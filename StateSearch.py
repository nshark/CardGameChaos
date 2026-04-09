"""
terminal_search.py
==================
State-space traversal and terminal-proximity labeling for the TCG value network.

Public API
----------
generate_child_states(node, phase, pending_events=None) -> list[StateNode]
probe_terminal(node, pID, depth=15, gamma=0.95)         -> float | None

A StateNode is a tuple:
    (state,)                      — start of a new phase, phase inferred from turn
    (state, phase)                — state ready to enter a named phase
    (state, phase, pending_events) — state mid-phase with unresolved event queue

The event queue (pending_events) is a list of items produced by Game's search-mode
methods.  Each item is one of:
    (card_a, card_b)   — a blocked combat pair still to be resolved
    [attacker, *handlers] — an unblocked attacker that got through (deals face damage
                            + zero or more triggered handlers to fire afterward)
    callable           — a targeting decision needed before an effect can resolve;
                         calling it with (state, search=True) either returns the effect
                         (if a target is still needed) or returns None / fires inline.
    (int, card)        — a play/sac event: (+1, card) means play, (-1, card) means kill
"""

import copy
from itertools import combinations

from Harness.Card import Card


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _active_player(state):
    """The player whose turn it currently is."""
    return state.p1 if state.turnNumber % 2 == 0 else state.p2

def _inactive_player(state):
    """The player who is not currently taking their turn."""
    return state.p2 if state.turnNumber % 2 == 0 else state.p1

def _max_energy(state):
    return min((state.turnNumber // 2) + 2, 10)

def _sac_energy_available(battlefield):
    """Total ATK across all friendly cards — the budget for sac costs."""
    return sum(card.atk for card in battlefield)

def _is_game_over(state):
    return state.p1.life <= 0 or state.p2.life <= 0


# ---------------------------------------------------------------------------
# Play-phase helpers
# ---------------------------------------------------------------------------

def _all_possible_plays(hand, energy_budget, life_total, sac_budget):
    """
    Recursively enumerate every ordered subset of `hand` that fits within the
    energy, life, and sac-cost budgets.  Returns a list of card lists.
    The empty list (pass / play nothing) is NOT included here; the caller adds it.
    """
    playable = []
    for card in hand:
        if (card.costs['energy'] <= energy_budget
                and card.costs['sacCost'] <= sac_budget
                and card.costs['life'] < life_total):
            rest = list(hand)
            rest.remove(card)
            playable.append([card])
            follow_ups = _all_possible_plays(
                rest,
                energy_budget  - card.costs['energy'],
                life_total     - card.costs['life'],
                sac_budget     - card.costs['sacCost'],
            )
            for follow_up in follow_ups:
                playable.append([card] + follow_up)
    return playable

def _all_sacrifice_sets(battlefield, required_sac_total):
    """
    Return a list of sac sets, where each sac set is a list of cards whose
    combined ATK meets `required_sac_total`.  Stops recursing as soon as a
    card brings the remaining need to <= 0 (no over-sacrificing beyond that).

    Returns [] when required_sac_total is 0 (nothing to sacrifice).
    """
    if required_sac_total <= 0:
        # Called with 0 from the outside → no sacrifice needed, no sets to return.
        # Called with <=0 mid-recursion (a card pushed us over) → one valid set:
        # stop here and let the caller prepend the card that got us here.
        # We distinguish by whether any card has been picked yet, but since the
        # recursive call already prepends the card before appending, returning
        # [[]] mid-recursion and [] at the top level are both correct as written —
        # so we split on the explicit public contract: 0 means "no sac required".
        return []
    sac_sets = []
    for card in battlefield:
        remaining_need = required_sac_total - card.atk
        rest = list(battlefield)
        rest.remove(card)
        if remaining_need <= 0:
            # This card alone satisfies the requirement.
            sac_sets.append([card])
        else:
            for suffix in _all_sacrifice_sets(rest, remaining_need):
                sac_sets.append([card] + suffix)
    return sac_sets


# ---------------------------------------------------------------------------
# Combat-phase helpers
# ---------------------------------------------------------------------------

def _all_defender_orderings(available_defenders, num_attackers):
    """
    Return every ordered list of exactly `num_attackers` defenders drawn from
    `available_defenders` without replacement.  Each ordering is matched 1-to-1
    with the attacker list.

    Returns [] when num_attackers is 0 (nothing to block).
    """
    if num_attackers == 0:
        return []
    orderings = []
    for card in available_defenders:
        rest = list(available_defenders)
        rest.remove(card)
        if num_attackers == 1:
            # Base case: this card alone completes the assignment.
            orderings.append([card])
        else:
            for suffix in _all_defender_orderings(rest, num_attackers - 1):
                orderings.append([card] + suffix)
    return orderings


# ---------------------------------------------------------------------------
# Event-queue processor
# ---------------------------------------------------------------------------

def _resolve_pending_events(state, pending_events, phase, insta_return=False):
    """
    Walk through `pending_events` and apply each one to a *copy* of `state`.
    Returns either:
        (resolved_state, next_phase, remaining_events)  — normal completion
        list[StateNode]                                 — branching point hit

    A branching point occurs when a targeting decision is required.  At that
    point we fork: one child per valid target across both battlefields.
    """
    working_state  = copy.deepcopy(state)
    queue          = list(pending_events)

    while queue:
        event = queue.pop(0)

        # ── (int, card) — play or kill event from the play phase ──────────
        if isinstance(event, tuple) and isinstance(event[0], int):
            action, card = event
            if action == 1:     # play the card
                new_triggers = working_state.play(card, search=True)
                queue = new_triggers + queue
            elif action == -1:  # sacrifice / kill the card
                new_triggers = working_state.kill(card, search=True)
                queue = new_triggers + queue

        # ── (Card, Card) — blocked combat pair ────────────────────────────
        elif (isinstance(event, tuple)
              and len(event) == 2
              and isinstance(event[0], Card)
              and isinstance(event[1], Card)):
            attacker, defender = event
            if attacker.atk >= defender.df:
                kill_triggers = working_state.kill(defender, attacker, search=True)
                queue = kill_triggers + queue
            if defender.atk >= attacker.df:
                kill_triggers = working_state.kill(attacker, defender, search=True)
                queue = kill_triggers + queue

        # ── [attacker, *handlers] — unblocked attacker, deals face damage ─
        elif isinstance(event, list):
            attacker   = event[0]
            handlers   = event[1:]
            defending_player = _inactive_player(working_state)
            defending_player.life -= attacker.atk
            if defending_player.life <= 0:
                working_state.end()
            # prepend any follow-up handlers so they resolve before the next event
            queue = handlers + queue

        # ── callable — targeting decision or deferred effect ──────────────
        elif callable(event):
            result = event(working_state, search=True)

            # If the callable itself needs a target, we branch here.
            if callable(result):
                if insta_return:
                    # Caller wants a single partially-resolved state + remainder.
                    return working_state, phase, [event] + queue

                # Fan out: one child state per legal target on either battlefield.
                child_states = []
                for target_card in (working_state.p1.battlefield
                                    + working_state.p2.battlefield):
                    branch = copy.deepcopy(working_state)
                    result(branch, target_card)
                    child_states.append((branch, phase, queue))
                return child_states

    # Queue exhausted — hand off to the next phase.
    return working_state, phase, None


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

def generate_child_states(state, phase, pending_events=None):
    """
    Return all reachable successor states from (state, phase, pending_events).

    Each returned item is a StateNode tuple:
        (state, phase)               — ready to begin that phase
        (state, phase, events)       — mid-phase with events still to process

    Phases
    ------
    'play'          — active player chooses which cards to play (and sacrifices).
    'declareAttacks' — active player chooses which cards attack.
    'combat'        — defenders are assigned and combat resolves.
    """

    active   = _active_player(state)
    inactive = _inactive_player(state)

    # ── Phase: play ────────────────────────────────────────────────────────
    if phase == 'play':

        # Mid-phase: we already have a chosen play sequence to work through.
        if pending_events is not None:
            result = _resolve_pending_events(
                state, pending_events, phase, insta_return=True
            )
            # Branching: _resolve_pending_events returned a list of child nodes.
            if isinstance(result, list):
                return result
            resolved_state, _, remaining = result

            if remaining is not None:
                # Still unresolved events — return the partial state.
                return [(resolved_state, phase, remaining)]

            # Play sequence fully resolved.  Move to attacks (or skip if empty board).
            if active.battlefield:
                return [(resolved_state, 'declareAttacks', None)]
            else:
                resolved_state.curseTick()
                return [(resolved_state, 'play', None)]

        # Fresh play phase: enumerate every legal (cards_to_play, sacrifices) pair.
        sac_budget    = _sac_energy_available(active.battlefield)
        energy_budget = _max_energy(state)
        all_plays     = [[]] + _all_possible_plays(
            active.hand, energy_budget, active.life, sac_budget
        )

        # Pre-compute sac sets grouped by required total so we don't repeat work.
        sac_sets_by_cost = {}
        child_states = []

        for play_sequence in all_plays:
            total_sac_needed = sum(c.costs['sacCost'] for c in play_sequence)

            if total_sac_needed > 0:
                if total_sac_needed not in sac_sets_by_cost:
                    sac_sets_by_cost[total_sac_needed] = _all_sacrifice_sets(
                        active.battlefield, total_sac_needed
                    )
                for sac_set in sac_sets_by_cost[total_sac_needed]:
                    events = state.playPhase(play_sequence, sac_set, search=True)
                    child_states.append(
                        generate_child_states(state, phase, pending_events=events)
                    )
            else:
                events = state.playPhase(play_sequence, [], search=True)
                child_states.append(
                    generate_child_states(state, phase, pending_events=events)
                )

        # generate_child_states returns a list of nodes; flatten one level.
        flat = []
        for item in child_states:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)
        return flat

    # ── Phase: declareAttacks ──────────────────────────────────────────────
    if phase == 'declareAttacks':
        child_states = []

        # Every non-empty subset of the battlefield can attack.
        for r in range(len(active.battlefield)):
            for attack_group in combinations(active.battlefield, r):
                attackers = list(attack_group)
                if attackers:
                    child_states.append((state, 'combat', ['attackers'] + attackers))

        # Passing (no attackers) ends the turn.
        no_attack_state = copy.deepcopy(state)
        no_attack_state.curseTick()
        child_states.append((no_attack_state, 'play', None))

        return child_states

    # ── Phase: combat ──────────────────────────────────────────────────────
    if phase == 'combat':

        # Step 1: attackers just declared — now generate all defender assignments.
        if isinstance(pending_events, list) and pending_events[0] == 'attackers':
            attackers         = pending_events[1:]
            possible_defenses = _all_defender_orderings(inactive.battlefield, len(attackers))
            child_states = []
            for defenders in possible_defenses:
                events = state.combatPhase(
                    search=True, attackers=attackers, defenders=defenders
                )
                child_states.append(
                    generate_child_states(state, phase, pending_events=(attackers, defenders, events))
                )
            return child_states

        # Step 2: defender assignment known — resolve the combat event queue.
        if isinstance(pending_events, tuple):
            attackers, defenders, events = pending_events
            if events is None:
                events = state.combatPhase(
                    search=True, attackers=attackers, defenders=defenders
                )
            result = _resolve_pending_events(state, events, phase, insta_return=False)

            if isinstance(result, list):
                return result

            resolved_state, _, _ = result
            return [(resolved_state, 'play', None)]

    return []


# ---------------------------------------------------------------------------
# Terminal-proximity probe  (Phase 1 training labels)
# ---------------------------------------------------------------------------

def probe_terminal(node, pID, depth=15, gamma=0.95):
    """
    Recursively search for a terminal outcome reachable from `node` within
    `depth` steps, discounting by `gamma` per step.

    Returns
    -------
    float   — discounted value in [-1, +1] from pID's perspective.
    None    — no terminal found within the depth limit.

    A value of +1 means pID wins at the current node; -1 means pID loses.
    Both players losing (simultaneous lethal) returns 0.

    Parameters
    ----------
    node  : StateNode tuple — (state,) | (state, phase) | (state, phase, events)
    pID   : int             — 0 or 1; the player whose perspective we score from.
    depth : int             — remaining search depth.
    gamma : float           — per-step discount factor.
    """
    state = node[0]
    phase = node[1] if len(node) > 1 else 'play'

    # ── Terminal checks ────────────────────────────────────────────────────
    both_dead = state.p1.life <= 0 and state.p2.life <= 0
    p1_dead   = state.p1.life <= 0
    p2_dead   = state.p2.life <= 0

    if both_dead:
        return 0.0
    if p1_dead:
        return +1.0 if pID == 1 else -1.0
    if p2_dead:
        return +1.0 if pID == 0 else -1.0

    # ── Depth exhausted ────────────────────────────────────────────────────
    if depth == 0:
        # Track how often we hit the depth limit (useful for tuning).
        probe_terminal.depth_limit_hits = getattr(probe_terminal, 'depth_limit_hits', 0) + 1
        return None

    # ── Recurse into children ──────────────────────────────────────────────
    pending = node[2] if len(node) > 2 else None
    children = generate_child_states(state, phase, pending_events=pending)

    best_value = None
    for child in children:
        child_value = probe_terminal(child, pID, depth - 1, gamma)
        if child_value is None:
            continue
        discounted = child_value * gamma
        if best_value is None or abs(discounted) > abs(best_value):
            best_value = discounted

    return best_value  # None if no terminal found anywhere in the subtree