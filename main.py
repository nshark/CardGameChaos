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
for i in range(len(cardData)):
    cardLibrary[cardData[i]['id']] = cardData[i]

a = Deck(cardLibrary, random.choices(range(1,68), k=20), 0)
b = Deck(cardLibrary, random.choices(range(1,68), k=20), 1)
game = Game(a, b)
while True:
    game.takeTurn()
    print(game)