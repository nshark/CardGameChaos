# test_harness.py
import random
import json
import traceback
from math import ceil
from Game import Deck, Game, Player
from Card import Card

# ── Load card library ──────────────────────────────────────────────────────────
cardPath = 'cards.json'
with open(cardPath, 'r') as f:
    cardData = json.load(f)['cards']
cardLibrary = {c['id']: c for c in cardData}

# ── Bot decision-making (replaces CLI input) ───────────────────────────────────
def card_value(card):
    """Heuristic score for a card's board presence."""
    return card.atk + card.df


def bot_opponent(self, game):
    return game.p2 if self.deck.cards[0].pID == 0 else game.p1


def would_survive_attack(attacker, defender):
    """True if defender dies and attacker lives through the trade."""
    defender_dies = attacker.atk >= defender.df
    attacker_dies = defender.atk >= attacker.df
    return defender_dies and not attacker_dies


def favorable_trade(attacker, defender):
    """True if trading is worth it: attacker kills defender or is higher value."""
    return attacker.atk >= defender.df and card_value(attacker) >= card_value(defender)


# ── Bot decision-making ────────────────────────────────────────────────────────

def bot_request_decision(self, type, game, num=0, energy=0, attackers=[], availableDefenders=[], pCard=None):
    pID = self.deck.cards[0].pID
    opponent = bot_opponent(self, game)

    # ── Play cards ────────────────────────────────────────────────────────────
    if type == 'playCards':
        # Candidates: affordable without sacrifices first
        affordable = [
            c for c in self.hand
            if c.costs['energy'] <= energy
               and c.costs['life'] < self.life
               and c.costs['sacCost'] == 0
        ]
        # Sort: prefer high-value cards that fit within energy budget greedily
        affordable.sort(key=card_value, reverse=True)

        # Greedy knapsack: play as many high-value cards as energy allows
        card_order = []
        remaining_energy = energy
        for card in affordable:
            if card.costs['energy'] <= remaining_energy:
                card_order.append(card)
                remaining_energy -= card.costs['energy']

        # Consider sac-cost cards if we have weak cards on the field worth trading
        # Pick the weakest battlefield cards as potential sacrifices
        potential_sacs = sorted(self.battlefield, key=card_value)
        sac_pool = list(potential_sacs)
        sac_energy_available = sum(c.atk for c in sac_pool)

        for card in sorted(self.hand, key=card_value, reverse=True):
            if card in card_order:
                continue
            if (card.costs['energy'] <= remaining_energy
                    and card.costs['life'] < self.life
                    and card.costs['sacCost'] > 0
                    and sac_energy_available >= card.costs['sacCost']
                    and card_value(card) > card.costs['sacCost']):  # only if net gain
                card_order.append(card)
                remaining_energy -= card.costs['energy']

        return card_order, sac_pool

    # ── Choose attackers ──────────────────────────────────────────────────────
    elif type == 'attackers':
        if not self.battlefield:
            return []

        selected = []
        op_field = list(opponent.battlefield)

        if not op_field:
            # No defenders: attack with everything to drain life
            return list(self.battlefield)

        for attacker in self.battlefield:
            # Attack if we can kill something without dying, or if opponent has
            # no defenders that can kill us (pure damage through)
            kills_something = any(attacker.atk >= d.df for d in op_field)
            safe_kill = any(would_survive_attack(attacker, d) for d in op_field)
            favorable = any(favorable_trade(attacker, d) for d in op_field)

            if safe_kill or favorable:
                selected.append(attacker)
            elif kills_something and attacker.atk > attacker.df:
                # High-attack, low-defense cards: trade aggressively
                selected.append(attacker)
            elif not any(d.atk >= attacker.df for d in op_field):
                # No opponent card can kill us: attack freely
                selected.append(attacker)

        # If we have board advantage, pile on to drain life even with weaker attackers
        if len(self.battlefield) > len(op_field) + 1 and not selected:
            selected = list(self.battlefield)

        return selected

    # ── Choose defenders ──────────────────────────────────────────────────────
    elif type == 'defenders':
        if not self.battlefield:
            return []

        defenders = []
        available = list(self.battlefield)  # defenders we haven't assigned yet

        # Sort attackers strongest first to prioritize blocking the biggest threats
        sorted_attackers = sorted(attackers, key=lambda a: a.atk, reverse=True)

        for attacker in sorted_attackers:
            if not available:
                break

            # Find the best blocker for this attacker:
            # Prefer a blocker that kills the attacker and survives.
            # Fall back to one that at least kills the attacker.
            # If no kill is possible, only block if the attacker is dangerous
            # (would deal >= 5 damage to our life) and it's worth soaking.

            ideal = next(
                (d for d in available if would_survive_attack(d, attacker)), None
            )
            if ideal:
                defenders.append(ideal)
                available.remove(ideal)
                continue

            can_kill = next(
                (d for d in available if d.atk >= attacker.df), None
            )
            if can_kill:
                # Only trade if we're not giving up too much value
                if card_value(can_kill) <= card_value(attacker) + 2:
                    defenders.append(can_kill)
                    available.remove(can_kill)
                    continue

            # Last resort: if attacker would deal killing/severe damage, chump block
            if attacker.atk >= self.life or attacker.atk >= 5:
                # Use the lowest-value card we have
                chump = min(available, key=card_value)
                defenders.append(chump)
                available.remove(chump)
            # Otherwise let it through — not worth losing the blocker

        return defenders

    # ── Discard ───────────────────────────────────────────────────────────────
    elif type == 'discard':
        # Discard lowest-value cards first
        sorted_hand = sorted(range(len(self.hand)), key=lambda i: card_value(self.hand[i]))
        return sorted_hand[:num]

    # ── Target ───────────────────────────────────────────────────────────────
    elif type == 'target':
        if not opponent.battlefield:
            return None
        # Target the highest-ATK card (biggest threat) that we can actually kill,
        # otherwise just the strongest card on the board
        killable = [c for c in opponent.battlefield if pCard and pCard.atk >= c.df]
        if killable:
            return max(killable, key=card_value)
        return max(opponent.battlefield, key=lambda c: c.atk)


Player.requestDecision = bot_request_decision


# ── Invariant checks ───────────────────────────────────────────────────────────
def check_invariants(game, context=""):
    errors = []

    for label, player in [("P1", game.p1), ("P2", game.p2)]:
        # No card should appear in multiple zones
        all_zones = player.hand + player.battlefield + player.graveyard
        ids = [c.id for c in all_zones]
        if len(ids) != len(set(ids)):
            errors.append(f"{label}: card appears in multiple zones @ {context}")
        # Life should never be absurdly negative (runaway damage bug)
        if player.life < -1000:
            errors.append(f"{label}: life is {player.life}, possible runaway damage @ {context}")

        # Battlefield cards should all have valid atk/def
        for card in player.battlefield:
            if card.atk < 0 or card.df < 0:
                errors.append(f"{label}: {card.name} has negative stats ({card.atk}/{card.df}) @ {context}")

    return errors

# ── Single game runner ─────────────────────────────────────────────────────────
def run_game(game_number, max_turns=200):
    result = {
        'game': game_number,
        'turns': 0,
        'outcome': None,
        'errors': [],
        'exception': None,
        'cumulativeAdvantage': 0
    }

    ids_a = random.choices(range(1, 68), k=20) + random.choices(range(69,76), k=random.randint(0,2))
    ids_b = random.choices(range(1, 68), k=20) + random.choices(range(69,76), k=random.randint(0,2))

    try:
        deck_a = Deck(cardLibrary, ids_a, 0)
        deck_b = Deck(cardLibrary, ids_b, 1)
        game = Game(deck_a, deck_b)
    except Exception as e:
        result['exception'] = f"Setup failed: {traceback.format_exc()}"
        return result

    for turn in range(max_turns):
        # Check invariants before each turn
        errors = check_invariants(game, context=f"turn {turn}")
        result['errors'].extend(errors)

        if game.scheduleEnd:
            result['outcome'] = 'completed'
            result['turns'] = turn
            result['cumulativeAdvantage'] = game.advantage
            result['winningDeck'] = [c.name for c in game.p1.deck.cards] if game.advantage > 0 else [c.name for c in game.p2.deck.cards]
            result['losingDeck'] = [c.name for c in game.p2.deck.cards] if game.advantage > 0 else [c.name for c in game.p1.deck.cards]
            break
        try:
            game.takeTurn()
        except Exception as e:
            result['exception'] = traceback.format_exc()
            result['turns'] = turn
            break
    else:
        result['outcome'] = 'timeout'
        result['turns'] = max_turns

    if result['outcome'] is None and result['exception'] is None:
        result['outcome'] = 'completed'

    return result

# ── Test suite ─────────────────────────────────────────────────────────────────
def run_suite(n_games=50):
    print(f"Running {n_games} games...\n")
    results = [run_game(i) for i in range(n_games)]
    print(f"Finished running {n_games} games\n")
    cardPairing = {}
    for result in results:
        if result['outcome'] != 'completed':
            continue
        for cID in result['winningDeck']:
            if cID not in cardPairing:
                cardPairing[cID] = {'totalAdvantage':2}
            else:
                cardPairing[cID]['totalAdvantage'] += 1.25
            for pairCID in result['winningDeck']:
                if cID != pairCID:
                    if pairCID not in cardPairing[cID]:
                        cardPairing[cID][pairCID] = 1.25
                    else:
                        cardPairing[cID][pairCID] += 1.25
            for allCID in cardPairing[cID]:
                cardPairing[cID][allCID] -= 0.25
        for cID in result['losingDeck']:
            if cID not in cardPairing:
                cardPairing[cID] = {'totalAdvantage':-1.25}
            else:
                cardPairing[cID]['totalAdvantage'] -= 1.25
            for pairCID in result['losingDeck']:
                if cID != pairCID:
                    if cID not in cardPairing:
                        cardPairing[cID] = {pairCID:-1.25}
                    elif pairCID not in cardPairing[cID]:
                        cardPairing[cID][pairCID] = -1.25
                    else:
                        cardPairing[cID][pairCID] -= 1.25
            for allCID in cardPairing[cID]:
                cardPairing[cID][allCID] += 0.25
    for cID in cardPairing:
        avg = 0
        count = 0
        for pairCID in cardPairing[cID]:
            avg += cardPairing[cID][pairCID]
            count += 1
        cardPairing[cID]['averageSynergy'] = avg / count
    return cardPairing



if __name__ == '__main__':
    output = open('cardSynergies.json', 'w')
    json.dump(run_suite(n_games=10000),output)
    output.close()
