import random
from math import ceil

from Card import Card

# ── Log-event categories ──────────────────────────────────────────────────────
# Each entry in turnLog is now a dict:  { 'cat': str, 'msg': str }
# Categories:  'phase'  'play'  'sac'  'combat'  'kill'  'trigger'  'damage'
#              'draw'   'discard' 'bounce' 'revive' 'stat'  'info'

def _ev(cat, msg):
    return {'cat': cat, 'msg': msg}


class Game:
    def __init__(self, DeckA, DeckB, logging=False):
        self.lastEntered = None
        self.lastExited = None
        self.scheduleEnd = False
        self.turnNumber = 0
        self.advantage = 0
        self.logging = logging
        self.turnLog = []
        self.p1 = Player(DeckA)
        self.p2 = Player(DeckB)
        self.handlers = {'entranceThis':{}, 'exitThis':{}, 'entranceAny':[], 'exitAny':[], 'onKill': {}}

    def __str__(self):
        def fmt_card(card):
            return f"{card.name}({card.atk}/{card.df})"

        def fmt_zone(label, cards):
            if not cards:
                return f"  {label}: —"
            return f"  {label}: " + ", ".join(fmt_card(c) for c in cards)

        def fmt_player(label, player):
            lines = [
                f"{'=' * 40}",
                f"  {label}  |  Life: {player.life}  |  Hand: {len(player.hand)}  |  Deck: {len(player.deck.drawOrder)}",
                fmt_zone("Battlefield", player.battlefield),
                fmt_zone("Graveyard  ", player.graveyard),
            ]
            return "\n".join(lines)

        turn_owner = "Player 1" if self.turnNumber % 2 == 0 else "Player 2"

        return "\n".join([
            f"\n{'#' * 40}",
            f"  Turn {self.turnNumber}  |  Active: {turn_owner}  |  Advantage: {self.advantage}",
            fmt_player("PLAYER 1", self.p2),
            f"  {'-' * 36}",
            fmt_player("PLAYER 0", self.p1),
            f"{'#' * 40}\n",
        ])

    def takeTurn(self):
        self.turnLog = []
        energy = min((self.turnNumber // 2) + 2, 10)
        if self.turnNumber % 2 == 0:
            player = self.p1
            pLabel = "P0"
        else:
            player = self.p2
            pLabel = "P1"

        if self.logging:
            self.turnLog.append(_ev('phase',
                f"{pLabel}'s Turn  (energy: {energy}, life: {player.life})"))

        # Draw phase
        drawn = max(1, 3 - len(player.hand))
        if self.logging:
            self.turnLog.append(_ev('phase', f"Draw phase — {pLabel} draws {drawn}"))
        self.draw(player, drawn)

        # Play phase
        if self.logging:
            self.turnLog.append(_ev('phase', "Play phase"))

        cardOrder, toSac = player.requestDecision('playCards', self, energy=energy)

        totalPossibleSacEnergy = sum(sac.atk for sac in toSac)
        sacEnergy = 0

        for card in cardOrder:
            if card in player.hand:
                if (energy >= card.costs['energy']
                        and player.life > card.costs['life']
                        and totalPossibleSacEnergy >= card.costs['sacCost']):
                    while sacEnergy < card.costs['sacCost'] and len(toSac) > 0:
                        if (toSac[-1].pID + 1) % 2 == self.turnNumber % 2:
                            sacrifice = toSac.pop(-1)
                            sacEnergy += sacrifice.atk
                            if self.logging:
                                self.turnLog.append(_ev('sac',
                                    f"{pLabel} sacrifices {sacrifice.name} "
                                    f"[{sacrifice.atk}/{sacrifice.df}]"))
                            self.kill(sacrifice, card)
                        else:
                            toSac.pop(-1)
                    energy -= card.costs['energy']
                    player.life -= card.costs['life']
                    if sacEnergy >= card.costs['sacCost']:
                        sacEnergy -= card.costs['sacCost']
                        totalPossibleSacEnergy -= card.costs['sacCost']
                        self.play(card)

        # Combat phase
        if self.turnNumber > 0:
            if self.logging:
                self.turnLog.append(_ev('phase', "Combat phase"))
            self.combatPhase()

        # Curse tick
        for card in list(self.p1.battlefield + self.p2.battlefield):
            if card.types == ['Curse'] and card.df > 0:
                card.df -= 1
                if self.logging:
                    self.turnLog.append(_ev('stat',
                        f"Curse {card.name} ticks to def {card.df}"))
            elif card.types == ['Curse'] and card.df == 0:
                self.kill(card)

        self.turnNumber += 1
        if self.scheduleEnd:
            self.reset()

    def combatPhase(self):
        if self.turnNumber % 2 == 0:
            attacker = self.p1
            aLabel = "P0"
            defender = self.p2
            dLabel = "P1"
        else:
            attacker = self.p2
            aLabel = "P1"
            defender = self.p1
            dLabel = "P0"

        attackers = attacker.requestDecision('attackers', self, availableDefenders=defender.battlefield)
        defenders = defender.requestDecision('defenders', self, attackers=attackers)
        attackers.sort(key=lambda x: x.atk, reverse=True)
        for at in attackers:
            if at.types[0] == 'Curse':
                attackers.remove(at)
        for df in defenders:
            if df.types[0] == 'Curse':
                defenders.remove(df)
        if self.logging:
            if attackers:
                names = ", ".join(f"{a.name}[{a.atk}/{a.df}]" for a in attackers)
                self.turnLog.append(_ev('combat', f"{aLabel} attacks with: {names}"))
            else:
                self.turnLog.append(_ev('info', f"{aLabel} declares no attackers"))

            if defenders:
                names = ", ".join(f"{d.name}[{d.atk}/{d.df}]" for d in defenders)
                self.turnLog.append(_ev('combat', f"{dLabel} blocks with: {names}"))

        while len(attackers) > 0:
            if len(defenders) > 0:
                a_card, d_card = attackers[0], defenders[0]
                if self.logging:
                    self.turnLog.append(_ev('combat',
                        f"  {a_card.name}[{a_card.atk}/{a_card.df}]"
                        f" vs {d_card.name}[{d_card.atk}/{d_card.df}]"))
                self.fight(attackers[0], defenders[0])
                attackers.remove(attackers[0])
                defenders.remove(defenders[0])
            else:
                a_card = attackers[0]
                life_before = defender.life
                defender.life -= a_card.atk
                if self.logging:
                    self.turnLog.append(_ev('damage',
                        f"  {a_card.name} deals {a_card.atk} to {dLabel} "
                        f"({life_before} → {defender.life})"))
                attackers.pop(0)
                if defender.life <= 0:
                    self.end()

    def fight(self, a, b):
        if a.atk >= b.df:
            self.kill(b, a)
        if b.atk >= a.df:
            self.kill(a, b)

    def play(self, card, noAnyEntrance=False):
        self.lastEntered = card
        if card.pID == 0 and card in self.p1.hand:
            self.p1.hand.remove(card)
        elif card.pID == 1 and card in self.p2.hand:
            self.p2.hand.remove(card)
        self.addToBattlefield(card)
        if self.logging:
            cost_parts = [f"{card.costs['energy']}E"]
            if card.costs['life']:
                cost_parts.append(f"{card.costs['life']}L")
            if card.costs['sacCost']:
                cost_parts.append(f"{card.costs['sacCost']}S")
            self.turnLog.append(_ev('play',
                f"P{card.pID} plays {card.name} [{card.atk}/{card.df}]"
                f"  ({', '.join(cost_parts)})"))
        if card.id in self.handlers['entranceThis']:
            if self.handlers['entranceThis'][card.id][0](self, 'entranceThis'):
                if self.logging:
                    self.turnLog.append(_ev('trigger',
                        f"  entranceThis triggers for {card.name}"))
                self.handlers['entranceThis'][card.id][1](self)
        if not noAnyEntrance:
            for entranceAnyTriggers in self.handlers['entranceAny']:
                if entranceAnyTriggers[0](self, 'entranceAny'):
                    if self.logging:
                        self.turnLog.append(_ev('trigger',
                            f"  entranceAny trigger fires"))
                    entranceAnyTriggers[1](self)
        if card.df == 0:
            self.removeFromBattlefield(card)

    def isActive(self, card):
        return card in self.p1.battlefield or card in self.p2.battlefield

    def kill(self, card, culprit=None):
        if self.logging:
            if culprit is not None:
                self.turnLog.append(_ev('kill',
                    f"P{card.pID}'s {card.name}[{card.atk}/{card.df}] "
                    f"killed by {culprit.name}"))
            else:
                self.turnLog.append(_ev('kill',
                    f"P{card.pID}'s {card.name}[{card.atk}/{card.df}] exits"))

        if card.pID == 0 and card in self.p1.battlefield and card.types != ['Curse']:
            self.lastExited = card
            self.p1.battlefield.remove(card)
            self.p1.graveyard.append(card)
        elif card.pID == 1 and card in self.p2.battlefield and card.types != ['Curse']:
            self.lastExited = card
            self.p2.battlefield.remove(card)
            self.p2.graveyard.append(card)
        elif card.types != ['Curse']:
            return

        if card.id in self.handlers['exitThis']:
            if self.handlers['exitThis'][card.id][0](self, 'exitThis'):
                if self.logging:
                    self.turnLog.append(_ev('trigger',
                        f"  exitThis triggers for {card.name}"))
                self.handlers['exitThis'][card.id][1](self)
        if culprit is not None and culprit.id in self.handlers['onKill']:
            if self.handlers['onKill'][culprit.id][0](self, 'onKill'):
                if self.logging:
                    self.turnLog.append(_ev('trigger',
                        f"  onKill triggers for {culprit.name}"))
                self.handlers['onKill'][culprit.id][1](self)
        for exitAnyTriggers in self.handlers['exitAny']:
            if exitAnyTriggers[0](self, 'exitAny'):
                if self.logging:
                    self.turnLog.append(_ev('trigger', "  exitAny trigger fires"))
                exitAnyTriggers[1](self)

        if card.pID == 0 and card not in self.p1.battlefield:
            card.exit(self)
        elif card.pID == 1 and card not in self.p2.battlefield:
            card.exit(self)

    def addHandler(self, type, verifier, effect, cID=0):
        if cID == 0:
            self.handlers[type].append((verifier, effect))
        else:
            self.handlers[type][cID] = (verifier, effect)

    def removeHandler(self, type, verifier, effect, cID=0):
        if cID == 0:
            if (verifier, effect) in self.handlers[type]:
                self.handlers[type].remove((verifier, effect))
        else:
            if cID in self.handlers[type]:
                self.handlers[type].pop(cID)

    def draw(self, player, num):
        pLabel = f"P{player.deck.pID}"
        drawn_names = []
        for i in range(num):
            toDraw = player.draw()
            if toDraw == 0:
                penalty = max(ceil(player.life / 2), 5)
                player.life -= penalty
                if self.logging:
                    self.turnLog.append(_ev('damage',
                        f"{pLabel} mills (empty deck) — loses {penalty} life "
                        f"(now {player.life})"))
                if player.life <= 0:
                    self.end()
            else:
                drawn_names.append(toDraw.name)
                player.hand.append(toDraw)
        if self.logging and drawn_names:
            self.turnLog.append(_ev('draw',
                f"{pLabel} draws: {', '.join(drawn_names)}"))

    def discard(self, player, num):
        pLabel = f"P{player.deck.pID}"
        if num >= len(player.hand):
            if self.logging:
                names = ", ".join(c.name for c in player.hand)
                self.turnLog.append(_ev('discard',
                    f"{pLabel} discards entire hand: {names}"))
            for card in player.hand:
                player.deck.cardExitField(card)
            player.hand = []
            return
        indices = player.requestDecision('discard', self, num=num)
        if self.logging:
            names = ", ".join(player.hand[i].name for i in sorted(indices))
            self.turnLog.append(_ev('discard', f"{pLabel} discards: {names}"))
        for index in sorted(indices, reverse=True):
            player.deck.cardExitField(player.hand.pop(index))

    def addToBattlefield(self, card):
        card.entrance(self)
        if card.pID == 0:
            self.p1.battlefield.append(card)
        else:
            self.p2.battlefield.append(card)

    def removeFromBattlefield(self, card):
        card.exit(self)
        self.lastExited = card
        if card.pID == 0 and card in self.p1.battlefield:
            self.p1.battlefield.remove(card)
        elif card.pID == 1 and card in self.p2.battlefield:
            self.p2.battlefield.remove(card)

    def end(self):
        if self.scheduleEnd:
            return
        if self.p1.life <= 0:
            self.advantage -= 1
        elif self.p2.life <= 0:
            self.advantage += 1
        if self.p1.life <= 0 or self.p2.life <= 0:
            self.scheduleEnd = True

    def reset(self):
        self.lastExited = None
        self.lastEntered = None
        self.p1.deck.reset()
        self.p2.deck.reset()
        self.p1 = Player(self.p1.deck)
        self.p2 = Player(self.p2.deck)
        self.turnNumber = 0


class Player:
    def __init__(self, Deck):
        self.deck = Deck
        self.battlefield = []
        self.life = 20
        self.graveyard = []
        self.hand = self.deck.drawHand()

    def draw(self):
        toDraw = self.deck.draw()
        if toDraw == 0 and len(self.graveyard) > 0:
            return self.graveyard.pop(0)
        return toDraw

    def requestDecision(self, type, game, num=0, energy=0, attackers=[], availableDefenders=[], pCard=None):
        player_label = f"Player {self.deck.cards[0].pID + 1}"

        if type == 'playCards':
            print(f"\n{player_label}, your hand:")
            for i, card in enumerate(self.hand):
                print(f"  [{i}] {card.name} | ATK:{card.atk} DEF:{card.df} | "
                      f"Cost: {card.costs['energy']} energy, {card.costs['life']} life, {card.costs['sacCost']} sac")
            print(f"  Available energy: {energy} | Your life: {self.life}")

            order_input = input("Enter card indices to play in order (e.g. '0 2 1'), or leave blank: ").strip()
            cardOrder = []
            if order_input:
                for idx in order_input.split():
                    cardOrder.append(self.hand[int(idx)])

            sac_input = input(
                "Enter card indices on YOUR battlefield to sacrifice (e.g. '0 1'), or leave blank: ").strip()
            toSac = []
            if sac_input:
                for idx in sac_input.split():
                    toSac.append(self.battlefield[int(idx)])
            return cardOrder, toSac

        elif type == 'attackers':
            if not self.battlefield:
                return []
            print(f"\n{player_label}, choose attackers:")
            for i, card in enumerate(self.battlefield):
                print(f"  [{i}] {card.name} | ATK:{card.atk} DEF:{card.df}")
            atk_input = input("Enter indices of attacking cards (e.g. '0 2'), or leave blank: ").strip()
            attackers = []
            if atk_input:
                for idx in atk_input.split():
                    attackers.append(self.battlefield[int(idx)])
            return attackers

        elif type == 'defenders':
            if not self.battlefield:
                return []
            print(f"\n{player_label}, incoming attackers:")
            for i, card in enumerate(attackers):
                print(f"  [{i}] {card.name} | ATK:{card.atk} DEF:{card.df}")
            print(f"  Your battlefield:")
            for i, card in enumerate(self.battlefield):
                print(f"  [{i}] {card.name} | ATK:{card.atk} DEF:{card.df}")
            def_input = input(
                "Enter indices of defending cards in order (matched 1:1 with attackers), or leave blank: ").strip()
            defenders = []
            if def_input:
                for idx in def_input.split():
                    defenders.append(self.battlefield[int(idx)])
            return defenders

        elif type == 'discard':
            print(f"\n{player_label}, you must discard {num} card(s). Your hand:")
            for i, card in enumerate(self.hand):
                print(f"  [{i}] {card.name} | ATK:{card.atk} DEF:{card.df}")
            while True:
                dis_input = input(f"Enter {num} card index/indices to discard: ").strip()
                indices = [int(x) for x in dis_input.split()]
                if len(indices) == num and all(0 <= i < len(self.hand) for i in indices):
                    return indices
                print(f"  Please enter exactly {num} valid index/indices.")

        elif type == 'target':
            opponent = game.p2 if self.deck.cards[0].pID == 0 else game.p1
            if not opponent.battlefield:
                return None
            print(f"\n{player_label}, choose a target for {pCard.name}:")
            for i, card in enumerate(opponent.battlefield):
                print(f"  [{i}] {card.name} | ATK:{card.atk} DEF:{card.df}")
            while True:
                t_input = input("Enter target index: ").strip()
                if t_input.isdigit() and 0 <= int(t_input) < len(opponent.battlefield):
                    return opponent.battlefield[int(t_input)]
                print("  Invalid index, try again.")


class Deck:
    def __init__(self, cardLibrary, cardIDs, pID):
        self.pID = pID
        self.cards = []
        self.drawOrder = []
        self.curses = []
        for i in range(len(cardIDs)):
            self.cards.append(Card(cardLibrary[cardIDs[i]], pID, i))
        self.reset()

    def drawHand(self):
        random.shuffle(self.drawOrder)
        hand = self.drawOrder[:(5 + self.pID)]
        self.drawOrder = list(set(self.drawOrder) - set(hand))
        hand += self.curses
        return hand

    def draw(self):
        if len(self.drawOrder) == 0:
            return 0
        return self.drawOrder.pop(0)

    def cardExitField(self, card):
        if card.types[0] != 'Curse':
            self.drawOrder.append(card)

    def reset(self):
        self.drawOrder = []
        for card in self.cards:
            if card.types[0] != 'Curse':
                self.drawOrder.append(card)