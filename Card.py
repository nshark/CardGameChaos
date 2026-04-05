def compCardAtk(a, b):
    return a.atk - b.atk
class Card:

    def __init__(self, cardData, pID, deckPos):
        self.entered = False
        self.pID = pID
        self.id = (cardData['id'], deckPos)
        self.types = cardData['types']
        self.name = cardData['name']
        self.atk = cardData['atk']
        self.df = cardData['def']
        self.base_atk = cardData['atk']  # add these two
        self.base_df = cardData['def']
        self.triggers = []
        self.effects = []
        if len(cardData['abilt']) > 0:
            for ability in cardData['abilt']:
                self.triggers.append(triggerFactory(ability['trigger'], self))
                self.effects.append(Effect(ability['effect'], self))
        self.costs = cardData['costs']
    def entrance(self, game):
        if self.entered:
            return
        self.entered = True
        for i in range(len(self.triggers)):
            if self.triggers[i].primary == 'entranceThis' or self.triggers[i].primary == 'exitThis' or self.triggers[i].primary == 'onKill' or self.triggers[i].primary == 'onThisDmgPlayer':
                game.addHandler(self.triggers[i].primary, self.triggers[i].check, self.effects[i].execute, cID=self.id)
            else:
                game.addHandler(self.triggers[i].primary, self.triggers[i].check, self.effects[i].execute)
    def exit(self, game):
        if not self.entered:
            return
        self.entered = False
        self.atk = self.base_atk  # replace the += logic
        self.df = self.base_df
        for i in range(len(self.triggers)):
            if self.triggers[i].primary == 'entranceThis' or self.triggers[i].primary == 'exitThis' or self.triggers[i].primary == 'onKill' or self.triggers[i].primary == 'onThisDmgPlayer':
                game.removeHandler(self.triggers[i].primary, self.triggers[i].check, self.effects[i].execute, cID=self.id)
            else:
                game.removeHandler(self.triggers[i].primary, self.triggers[i].check, self.effects[i].execute)

    def __eq__(self, other):
        if isinstance(other, Card):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

class primitiveTrigger():
    def check(self, game, eventType):
        return False

class producingTrigger(primitiveTrigger):
    def __init__(self, pCard, actionID):
        self.action = primActFactory(pCard, actionID)
    def check(self, game, eventType):
        return self.action.run(game)


def triggerFactory(triggerData, pCard):
    if type(triggerData) == int:
        return triggerData
    if type(triggerData) == str:
        if triggerData in ['this', 'lastEntered', 'lastExited', 'lastKilled', 'target', 'self', 'opponent', 'allOpCards', 'allFrCards']:
            return producingTrigger(pCard, triggerData)
        return primitiveNonProducingTrigger(triggerData)
    if type(triggerData) == dict and triggerData['operand'] == 'filter':
        return producingTrigger(pCard, triggerData['actionData'])
    else:
        return Trigger(triggerData, pCard)

class Trigger(primitiveTrigger):
    def __init__(self, triggerData, pCard):
        self.operand = triggerData['operand']
        if self.operand == "if":
            self.cmp = triggerData['cmp']
        if self.operand == "access":
            self.access = triggerData['access']
        self.triggers = []
        for trigger in triggerData['triggers']:
            self.triggers.append(triggerFactory(trigger, pCard))
        if self.operand == 'and' or self.operand == 'or':
            self.primary = self.triggers[0].primary

    def check(self, game, eventType):
        for trigger in self.triggers:
            if type(trigger) != int and trigger.check(game, eventType) is None:
                return None
        if self.operand == "and":
            for trigger in self.triggers:
                if not trigger.check(game, eventType):
                    return False
            return True
        if self.operand == "or":
            for trigger in self.triggers:
                if trigger.check(game, eventType):
                    return True
            return False
        if self.operand == "if":
            valA = self.triggers[0]
            valB = self.triggers[1]
            if (type(valA) != int):
                valA = valA.check(game, eventType)
            if (type(valB) != int):
                valB = valB.check(game, eventType)
            if self.cmp == '==':
                return valA == valB
            if self.cmp == '<':
                return valA < valB
            if self.cmp == '<=':
                return valA <= valB
            if self.cmp == 'contains':
                return valB in valA
        if self.operand == "access":
            toReturn = getattr(self.triggers[0].check(game, eventType), self.access)
            if callable(toReturn):
                return toReturn()
            return toReturn





class Effect:
    def __init__(self, effectData, pCard):
        self.targetingAction = primActFactory(pCard, effectData['targeting'])
        self.effect = primEffFactory(effectData['action'], effectData['pow'], pCard)
    def execute(self, game):
        targets = self.targetingAction.run(game)
        self.effect.run(game, targets)


def primEffFactory(effectID, pow, pCard):
    if  effectID == 'dmg':
        return primDmg(pow, pCard)
    elif effectID == 'kill':
        return primKill(pow, pCard)
    elif effectID == 'draw':
        return primDraw(pow, pCard)
    elif effectID == 'discard':
        return primDiscard(pow, pCard)
    elif effectID == 'modAtk':
        return primModAtk(pow, pCard)
    elif effectID == 'modDef':
        return primModDef(pow, pCard)
    elif effectID == 'bounce':
        return primBounce(pow, pCard)
    elif effectID == 'revive':
        return primRevive(pow, pCard)

def primActFactory(pCard, actionID):
    if type(actionID) != str:
        return filterAction(pCard, actionID)
    elif actionID == 'this':
        return primThis(pCard)
    elif actionID == 'lastEntered':
        return primLastEntered(pCard)
    elif actionID == 'lastExited':
        return primLastExited(pCard)
    elif actionID == 'lastKilled':
        return primLastKilled(pCard)
    elif actionID == 'target':
        return primTarget(pCard)
    elif actionID == 'self':
        return primSelf(pCard)
    elif actionID == 'opponent':
        return primOpponent(pCard)
    elif actionID == 'allOpCards':
        return primAllOpCards(pCard)
    elif actionID == 'allFrCards':
        return primAllFrCards(pCard)

class primitiveAction:
    def __init__(self, pCard):
        self.parentCard = pCard
    def run(self, game):
        return 'default'

class primThis(primitiveAction):
    def run(self, game):
        return self.parentCard

class primLastEntered(primitiveAction):
    def run(self, game):
        return game.lastEntered

class primLastExited(primitiveAction):
    def run(self, game):
        return game.lastExited

class primLastKilled(primitiveAction):
    def run(self, game):
        return self.parentCard.lKill

class primTarget(primitiveAction):
    def run(self, game):
        if (self.parentCard.pID == 0):
            return game.p1.requestDecision('target', game, pCard=self.parentCard)
        else:
            return game.p2.requestDecision('target', game, pCard=self.parentCard)

class primSelf(primitiveAction):
    def run(self, game):
        if (self.parentCard.pID == 0):
            return game.p1
        else:
            return game.p2

class primOpponent(primitiveAction):
    def run(self, game):
        if (self.parentCard.pID == 0):
            return game.p2
        else:
            return game.p1

class primAllOpCards(primitiveAction):
    def run(self, game):
        if (self.parentCard.pID == 0):
            return game.p2.battlefield
        else:
            return game.p1.battlefield

class primAllFrCards(primitiveAction):
    def run(self, game):
        if (self.parentCard.pID == 0):
            return game.p1.battlefield
        else:
            return game.p2.battlefield
class primitiveEffect():
    def __init__(self, pow, pCard):
        if type(pow) == int:
            self.pow = pow
        else:
            self.pow = triggerFactory(pow, pCard)
    def run(self, game, targets):
        if targets is None:
            return
        if type(targets) == list:
            for target in targets:
                self.run(game, target)

class primDmg(primitiveEffect):
    def run(self, game, targets):
        if type(self.pow) != int:
            pw = self.pow.check(game, 'dynamicPower')
        else:
            pw = self.pow
        if type(targets) == list:
            super().run(game, targets)
        elif type(targets) == Card:
            if pw>= targets.df:
                game.kill(targets)
        elif type(targets) == type(game.p1):
            targets.life -= pw
            if game.logging:
               game.turnLog.append({'cat': 'trigger', 'msg': f"Trigger deals {pw} dmg to P{targets.deck.pID} (life: {targets.life})"})
            if targets.life <= 0:
                game.end()
class primKill(primitiveEffect):
    def run(self, game, targets):
        if type(targets) == list:
            super().run(game, targets)
        if type(targets) == Card:
            game.kill(targets)
class primDraw(primitiveEffect):
    def run(self, game, targets):
        if type(self.pow) != int:
            pw = self.pow.check(game, 'dynamicPower')
        else:
            pw = self.pow
        if type(targets) == list:
            super().run(game, targets)
        if type(targets) == type(game.p1):
            game.draw(targets, pw)
class primDiscard(primitiveEffect):
    def run(self, game, targets):
        if type(self.pow) != int:
            pw = self.pow.check(game, 'dynamicPower')
        else:
            pw = self.pow
        if type(targets) == list:
            super().run(game, targets)
        if type(targets) == type(game.p1):
            game.discard(targets, pw)
class primModAtk(primitiveEffect):
    def run(self, game, targets):
        if type(self.pow) != int:
            pw = self.pow.check(game, 'dynamicPower')
        else:
            pw = self.pow
        if type(targets) == list:
            super().run(game, targets)
        if type(targets) == Card:
            if game.logging:
                game.turnLog.append({'cat': 'stat', 'msg': f"Trigger: {targets.name} ATK {targets.atk - pw} -> {targets.atk}"})
            targets.atk += pw
            if targets.atk < 0:
                targets.atk = 0
class primModDef(primitiveEffect):
    def run(self, game, targets):
        if type(self.pow) != int:
            pw = self.pow.check(game, 'dynamicPower')
        else:
            pw = self.pow
        if type(targets) == list:
            super().run(game, targets)
        if type(targets) == Card:
            if game.logging:
                game.turnLog.append({'cat': 'stat', 'msg': f"Trigger: {targets.name} DEF {targets.df - pw} -> {targets.df}"})
            targets.df += pw
            if targets.df < 0:
                targets.df = 0
            if targets.df == 0:
                game.kill(targets)
class primBounce(primitiveEffect):
    def run(self, game, targets):
        if type(targets) == list:
            super().run(game, targets)
        if type(targets) == Card:
            if targets.pID == 0:
                game.p1.hand.append(targets)
                game.removeFromBattlefield(targets)
            else:
                game.p2.hand.append(targets)
                game.removeFromBattlefield(targets)
class primRevive(primitiveEffect):
    def run(self, game, targets):
        if type(self.pow) != int:
            pw = self.pow.check(game, 'dynamicPower')
        else:
            pw = self.pow
        if type(targets) == list:
            super().run(game, targets)
        if type(targets) == Card:
            if not game.isActive(targets):
                if targets.pID == 0 and game.p1.life > pw and targets in game.p1.graveyard:
                    game.p1.graveyard.remove(targets)
                    game.play(targets, noAnyEntrance=True)
                    game.p1.life -= pw
                elif game.p2.life > pw and targets in game.p2.graveyard:
                    game.p2.graveyard.remove(targets)
                    game.play(targets, noAnyEntrance=True)
                    game.p2.life -= pw

class primitiveNonProducingTrigger(primitiveTrigger):
    def __init__(self, triggerData):
        self.primary = triggerData
    def check(self, game, eventType):
        return eventType == self.primary

def filterFactory(filterData):
    filterArgs = filterData['args']
    if filterData['type'] == 'attr>':
        return primitiveAttributeGreaterThan(filterArgs)
    elif filterData['type'] == 'attr<':
        return primitiveAttributeLessThan(filterArgs)
    elif filterData['type'] == 'attr=':
        return primitiveAttributeContains(filterArgs)

class primitiveFilter():
    def __init__(self, args):
        self.args = args
    def filter(self, card):
        return True

class primitiveAttributeGreaterThan(primitiveFilter):
    def filter(self, card):
        return getattr(card, self.args['attr']) > self.args['a']
class primitiveAttributeLessThan(primitiveFilter):
    def filter(self, card):
        return getattr(card, self.args['attr']) < self.args['a']
class primitiveAttributeContains(primitiveFilter):
    def filter(self, card):
        return self.args['a'] in getattr(card, self.args['attr'])


class filterAction(primitiveAction):
    def __init__(self, pCard, actionData):
        super().__init__(pCard)
        self.actions = []
        for action in actionData['actions']:
            self.actions.append(primActFactory(pCard, action))
        self.fil = filterFactory(actionData['filter'])
    def run(self, game):
        toFilter = []
        for action in self.actions:
            toAdd = action.run(game)
            def flattenList(l):
                for item in l:
                    if type(item) == list:
                        flattenList(item)
                    else:
                        toFilter.append(item)
            flattenList(toAdd)
        toReturn = []
        for item in toFilter:
            if self.fil.filter(item):
                toReturn.append(item)
        return toReturn


