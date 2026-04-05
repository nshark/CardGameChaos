import random
from math import ceil

from Card import Card


class Game:
    def __init__(self, DeckA, DeckB):
        self.lastEntered = None
        self.scheduleEnd = False
        self.turnNumber = 0
        self.advantage = 0
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
                f"{'═' * 40}",
                f"  {label}  |  Life: {player.life}  |  Hand: {len(player.hand)}  |  Deck: {len(player.deck.drawOrder)}",
                fmt_zone("Battlefield", player.battlefield),
                fmt_zone("Graveyard  ", player.graveyard),
            ]
            return "\n".join(lines)

        turn_owner = "Player 1" if self.turnNumber % 2 == 0 else "Player 2"

        return "\n".join([
            f"\n{'█' * 40}",
            f"  Turn {self.turnNumber}  |  Active: {turn_owner}  |  Advantage: {self.advantage}",
            fmt_player("PLAYER 2", self.p2),
            f"  {'─' * 36}",
            fmt_player("PLAYER 1", self.p1),
            f"{'█' * 40}\n",
        ])
    def takeTurn(self):
        energy = min(round((self.turnNumber/2) + 2), 10)
        if self.turnNumber % 2 == 0:
            player = self.p1
        else:
            player = self.p2
        self.draw(player, max(1, 3-len(player.hand)))

        #the id of the cards in the order they should be played, and the cards that should be sacrificed(if any)
        cardOrder, toSac = player.requestDecision('playCards', self, energy=energy)
        # total possible sacrifice energy:
        totalPossibleSacEnergy = 0
        for sac in toSac:
            totalPossibleSacEnergy += sac.atk

        sacEnergy = 0 #if there is extra sacrifice energy, it will be stored here to carry over to the next card
        for card in cardOrder:
            if card in player.hand:
                if energy >= card.costs['energy'] and player.life > card.costs['life'] and totalPossibleSacEnergy >= \
                        card.costs['sacCost']:
                    while sacEnergy < card.costs['sacCost'] and len(toSac) > 0:
                        if (toSac[-1].pID + 1) % 2 == self.turnNumber % 2:
                            sacrifice = toSac.pop(-1)
                            sacEnergy += sacrifice.atk
                            self.kill(sacrifice, card)
                        else:
                            toSac.pop(-1)
                    energy -= card.costs['energy']
                    player.life -= card.costs['life']
                    if sacEnergy >= card.costs['sacCost']:
                        sacEnergy -= card.costs['sacCost']
                        totalPossibleSacEnergy -= card.costs['sacCost']
                        self.play(card)
        self.combatPhase()
        for card in self.p1.battlefield + self.p2.battlefield:
            if card.types == ['curse'] and card.df > 0:
                card.df -= 1
            elif card.types == ['curse'] and card.df == 0:
                self.kill(card)
        self.turnNumber += 1
        if self.scheduleEnd:
            self.reset()
    def combatPhase(self):
        if self.turnNumber % 2 == 0:
            attacker = self.p1
            defender = self.p2
        else:
            attacker = self.p2
            defender = self.p1

        attackers = attacker.requestDecision('attackers', self, availableDefenders=defender.battlefield)
        defenders = defender.requestDecision('defenders', self, attackers=attackers)
        attackers.sort(key=lambda x: x.atk, reverse=True)
        while len(attackers) > 0:
            if len(defenders) > 0:
                self.fight(attackers[0], defenders[0])
                attackers.remove(attackers[0])
                defenders.remove(defenders[0])
            else:
                defender.life -= attackers[0].atk
                attackers.pop(0)
                if defender.life <= 0:
                    self.end()


    def fight(self, a, b):
        if a.atk >= b.df:
            self.kill(a, b)
        if b.atk >= a.df:
            self.kill(b, a)
    def play(self, card, noAnyEntrance=False):
        self.lastEntered = card
        if card.pID == 0 and card in self.p1.hand:
            self.p1.hand.remove(card)
        elif card.pID == 1 and card in self.p2.hand:
            self.p2.hand.remove(card)
        self.addToBattlefield(card)
        if card.id in self.handlers['entranceThis']:
            if (self.handlers['entranceThis'][card.id][0](self, 'entranceThis')):
                self.handlers['entranceThis'][card.id][1](self)
        if not noAnyEntrance:
            for entranceAnyTriggers in self.handlers['entranceAny']:
                if entranceAnyTriggers[0](self, 'entranceAny'):
                    entranceAnyTriggers[1](self)

    def isActive(self, card):
        return card in self.p1.battlefield or card in self.p2.battlefield
    def kill(self, card, culprit=None):
        if card.pID == 0 and card in self.p1.battlefield:
            self.p1.battlefield.remove(card)
            self.p1.graveyard.append(card)
        elif card.pID == 1 and card in self.p2.battlefield:
            self.p2.battlefield.remove(card)
            self.p2.graveyard.append(card)
        else:
            return#the card does not exist in a battlefield
        if card.id in self.handlers['exitThis']:
            if (self.handlers['exitThis'][card.id][0](self, 'exitThis')):
                self.handlers['exitThis'][card.id][1](self)
        if culprit != None and (culprit.id in self.handlers['onKill']):
            if (self.handlers['onKill'][culprit.id][0](self, 'onKill')):
                self.handlers['onKill'][culprit.id][1](self)
        for exitAnyTriggers in self.handlers['exitAny']:
            if exitAnyTriggers[0](self, 'exitAny'):
                exitAnyTriggers[1](self)
        if card.pID == 0 and not card in self.p1.battlefield:
            card.exit(self)
        elif card.pID == 1 and not card in self.p2.battlefield:
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
        for i in range(num):
            toDraw = player.draw()
            if toDraw == 0:
                player.life -= max(ceil(player.life/2), 5)
                if player.life <= 0:
                    self.end()
            else:
                player.hand.append(toDraw)

    def discard(self, player, num):
        if num >= len(player.hand):
            for card in player.hand:
                player.deck.cardExitField(card)
            player.hand = []
            return
        for index in sorted(player.requestDecision('discard', self, num=num), reverse=True):
            player.deck.cardExitField(player.hand.pop(index))
    def addToBattlefield(self, card):
        card.entrance(self)
        if card.pID == 0:
            self.p1.battlefield.append(card)
        else:
            self.p2.battlefield.append(card)
    def removeFromBattlefield(self, card):
        card.exit(self)
        if card.pID == 0 and card in self.p1.battlefield:
            self.p1.battlefield.remove(card)
        elif card.pID == 1 and card in self.p2.battlefield:
            self.p2.battlefield.remove(card)
    def end(self):
        if self.scheduleEnd:
            return
        if (self.p1.life <= 0 and self.p2.life <= 0):
            print('draw')
        elif (self.p1.life <= 0):
            print('p2 wins')
            self.advantage -= 1
        elif (self.p2.life <= 0):
            print('p1 wins')
            self.advantage += 1
        if (self.p1.life <= 0 or self.p2.life <= 0):
            self.scheduleEnd = True
    def reset(self):
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
        if toDraw == 0 and len(self.graveyard)>0:
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
                print(f"\n{player_label} has no cards to attack with.")
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
                print(f"\n{player_label} has no cards to defend with.")
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
                print(f"\n{player_label}: no targets available.")
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
        self.cards = []
        self.drawOrder = []
        self.curses = []
        for i in range(len(cardIDs)):
            self.cards.append(Card(cardLibrary[cardIDs[i]], pID, i))
        self.reset()


    def drawHand(self):
        random.shuffle(self.drawOrder)
        hand = self.drawOrder[:5]
        self.drawOrder = list(set(self.drawOrder) - set(hand))
        hand += self.curses
        return hand

    def draw(self):
        if len(self.drawOrder) == 0:
            return 0
        return self.drawOrder.pop(0)

    def cardExitField(self, card):
        if (card.types[0] != 'curse'):
            self.drawOrder.append(card)

    def reset(self):
        self.drawOrder = []
        for card in self.cards:
            if card.types[0] != 'curse':
                self.drawOrder.append(card)
