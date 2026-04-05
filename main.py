import random
import json
from Game import Deck
from Game import Game
global cardLibrary
cardPath = 'cards.json'
cardFile = open(cardPath, 'r')
cardData = json.load(cardFile)['cards']
cardFile.close()
cardLibrary = {}
regularCards = []
curseCards = []
for i in range(len(cardData)):
    cardLibrary[cardData[i]['id']] = cardData[i]
    if not 'Curse' in cardData[i]['types']:
        regularCards.append(cardData[i])
    else:
        curseCards.append(cardData[i])

a = Deck(cardLibrary, random.choices(regularCards, k=20)+random.choices(curseCards, k=random.randint(0,2)), 0)
b = Deck(cardLibrary, random.choices(regularCards, k=20)+random.choices(curseCards, k=random.randint(0,2)), 1)
game = Game(a, b)
while True:
    game.takeTurn()
    print(game)