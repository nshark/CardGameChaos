import json
from enum import IntEnum as Enum, IntEnum

from Harness.Card import Card

Types = Enum('Types', ["Fire", "Water", "Earth", "Dark", "Light", "Thunder",
    "Wind", "Holy", "Nature", "Dragon", "Warrior", "Beast",
    "Mage", "Spell", "Undead", "Curse"])
EventTriggers = Enum('EventTriggers',  ["entranceThis", "exitThis", "entranceAny", "exitAny", "onKill", "onThisDmgPlayer"])
SimpleProducers = Enum('SimpleProducers', ["this", "lastEntered", "lastExited", "lastKilled","target", "self", "opponent", "allOpCards", "allFrCards"])
Operands = Enum('Operands', ["and", "or", "if", "access", "filter"])
ComparisonValues = Enum('ComparisonValues', ["==", "<", "<=", "contains"])
AccessOptions = Enum('AccessOptions', ["types", "atk", "df", "len"])
EffectActions = Enum('EffectActions', ["dmg", "kill", "draw", "discard", "modAtk", "modDef", "bounce", "revive"])
FilterOptions = Enum('FilterOptions', ['attr>', 'attr<', 'attr='])
DecisionTypes = Enum('DecisionTypes', ['playCards', 'attackers', 'defenders', 'discard', 'target'])
AbilityKeys = Enum('AbilityKeys', ['access', 'operand', 'filter', 'triggers', 'effect', 'trigger', 'pow', 'action', 'cmp', 'targeting', 'actionData', 'actions', 'type', 'attr', 'a', 'args'])
def enumContains(key, en):
    if not isinstance(key, str):
        return False
    try:
        getattr(en, key)
        return True
    except AttributeError:
        return False
def loadCardLibrary():
    cardPath = './Harness/cards.json'
    with open(cardPath, 'r') as f:
        cardData = json.load(f)['cards']
    cardLibrary = {}
    for i in range(len(cardData)):
        cardLibrary[cardData[i]['id']] = cardData[i]
    return cardLibrary
def recurseEncoding(data):
    toReturn = {}
    for key in data.keys():
        if (data[key] == '__len__'):
            data[key] = 'len'
        if isinstance(data[key], list):
            toReturn[AbilityKeys[key].value] = []
            for item in data[key]:
                if isinstance(item, dict):
                    toReturn[AbilityKeys[key].value].append(recurseEncoding(item))
                if enumContains(item, EventTriggers):
                    toReturn[AbilityKeys[key].value].append(EventTriggers[item].value)
                if enumContains(item, SimpleProducers):
                    toReturn[AbilityKeys[key].value].append(SimpleProducers[item].value)
                if enumContains(item, Types):
                    toReturn[AbilityKeys[key].value].append(Types[item].value)
                if isinstance(item, int):
                    toReturn[AbilityKeys[key].value].append(int(item))
            continue
        if isinstance(data[key], dict):
            toReturn[AbilityKeys[key].value] = recurseEncoding(data[key])
        if key == 'pow' and isinstance(data[key], int):
            toReturn[AbilityKeys[key].value] = data[key]
            continue
        if enumContains(data[key], AccessOptions):
            toReturn[AbilityKeys[key].value] = AccessOptions[data[key]].value
        if enumContains(data[key], Operands):
            toReturn[AbilityKeys[key].value] = Operands[data[key]].value
        if enumContains(data[key], ComparisonValues):
            toReturn[AbilityKeys[key].value] = ComparisonValues[data[key]].value
        if enumContains(data[key], EffectActions):
            toReturn[AbilityKeys[key].value] = EffectActions[data[key]].value
        if enumContains(data[key], FilterOptions):
            toReturn[AbilityKeys[key].value] = FilterOptions[data[key]].value
        if enumContains(data[key], SimpleProducers):
            toReturn[AbilityKeys[key].value] = SimpleProducers[data[key]].value
    return toReturn





def loadAbilityEncodingForCID(cID):
    if not hasattr(loadAbilityEncodingForCID, 'lib'):
        loadAbilityEncodingForCID.lib = loadCardLibrary()
    return[recurseEncoding(a) for a in loadAbilityEncodingForCID.lib[cID]['abilt']]



class GameState():
    def __init__(self, game, activePID, activeDecision):
        self.activeDecision = DecisionTypes[activeDecision].value
        self.turnNumber = game.turnNumber

        if activePID == 0:
            self.activePlayer = PlayerState(game.p1)
            self.inactivePlayer = PlayerState(game.p2)
        else:
            self.activePlayer = PlayerState(game.p2)
            self.inactivePlayer = PlayerState(game.p1)

class PlayerState():
    def __init__(self, player):
        self.life = player.life
        self.hand = [card.id[0] for card in player.hand]
        self.battlefield = [ActiveCardState(card) for card in player.battlefield]
        self.graveyard = [ActiveCardState(card) for card in player.graveyard]

class ActiveCardState():
    cardLib = loadCardLibrary()
    def __init__(self, card, cID=0):
        if (cID != 0):
            card = Card(self.cardLib[cID], 0, 0)
        self.atk = card.atk
        self.df = card.df
        self.types = [Types[tp].value for tp in card.types]
        self.abilityData = loadAbilityEncodingForCID(card.id[0])