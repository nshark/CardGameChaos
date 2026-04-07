import torch
import torch.nn as nn
import torch.nn.functional as F
from stateHelper import loadCardLibrary, ActiveCardState, AbilityKeys, Operands

N_TYPES    = 16   # len(Types)
N_TRIGGERS = 6    # len(EventTriggers)
N_EFFECTS  = 8    # len(EffectActions)
N_TARGETS  = 9    # len(SimpleProducers)
N_OPERANDS = 14   # Access options + Filter options + Comparison + ['and' + 'or']

ABILITY_HIDDEN = 96
ABILITY_DIM  = 64   # output dim per card's ability summary
TYPE_DIM     = 16   # output of type embedding pool
CARD_FEAT_DIM = 2 + TYPE_DIM + ABILITY_DIM


cardLibrary = loadCardLibrary()

class AbilityEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.prim_trigger_emb = nn.Embedding(N_TRIGGERS + 1, ABILITY_HIDDEN, padding_idx=0)
        self.prim_effect_emb = nn.Embedding(N_EFFECTS + 1, ABILITY_HIDDEN, padding_idx=0)
        self.prim_target_emb = nn.Embedding(N_TARGETS + 1, ABILITY_HIDDEN, padding_idx=0)
        self.operand_emb = nn.Embedding(N_OPERANDS + 1, ABILITY_HIDDEN, padding_idx=0)

        self.node_mlp = nn.Sequential(
            nn.Linear(ABILITY_HIDDEN*2, ABILITY_HIDDEN),
            nn.ReLU(),
            nn.Linear(ABILITY_HIDDEN, ABILITY_HIDDEN),
        )

        self.leaf_mlp = nn.Sequential(
            nn.Linear(ABILITY_HIDDEN, ABILITY_HIDDEN),
            nn.ReLU(),
        )

    def forward(self, node):
        primitives = []

        trigger = node.get(AbilityKeys.trigger.value, 0)
        action = node.get(AbilityKeys.action.value, 0)
        target = node.get(AbilityKeys.targeting.value, 0)

        if trigger and not isinstance(trigger, dict): primitives.append(self.prim_trigger_emb(torch.tensor(trigger)))
        if action and not isinstance(action, dict):  primitives.append(self.prim_effect_emb(torch.tensor(action)))
        if target and not isinstance(target, dict):  primitives.append(self.prim_target_emb(torch.tensor(target)))

        # --- recurse into nested child dicts ---
        children = []
        for val in node.values():
            if isinstance(val, dict):
                children.append(self.forward(val))  # recurse
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        children.append(self.forward(item))

        # --- get this node's operand ---
        operand_id = node.get(AbilityKeys.operand.value, 0)
        if operand_id == Operands['access'].value:
            operand_id = node.get(AbilityKeys.access.value, 0) + 2
        if operand_id == Operands['if'].value:
            operand_id = node.get(AbilityKeys.cmp.value, 0) + 6


        op_emb = self.operand_emb(torch.tensor(operand_id))  # (hidden,)

        # --- pool everything below this node ---
        all_below = primitives + children
        if all_below:
            pooled = torch.stack(all_below).sum(dim=0)  # (hidden,)
        else:
            pooled = torch.zeros(ABILITY_HIDDEN)

        if operand_id == 0 and not children:
            # pure leaf node — no operand, no children
            return self.leaf_mlp(pooled)

        # cat operand with pooled subtree, run through node MLP
        combined = torch.cat([op_emb, pooled])  # (hidden*2,)
        return self.node_mlp(combined)  # (hidden,)

class CardEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.abilityEncoder = AbilityEncoder()
        self.ability_pool = nn.Sequential(
            nn.Linear(ABILITY_HIDDEN, ABILITY_DIM),
            nn.ReLU(),
        )
        self.norm = nn.LayerNorm(CARD_FEAT_DIM)
        self.proj = nn.Linear(CARD_FEAT_DIM, CARD_FEAT_DIM)

    def forward(self, cardState):
        typeTensor = torch.zeros(N_TYPES)
        for typeIndex in cardState.types:
            typeTensor[typeIndex-1] = 1
        scalar = torch.tensor([cardState.atk/10.0, cardState.df/10.0], dtype=torch.float)
        if cardState.abilityData:
            ability_vecs = []
            for ability in cardState.abilityData:
                ability_vecs.append(self.abilityEncoder.forward(ability))
            pooled = torch.stack(ability_vecs).sum(dim=0)
        else:
            pooled = torch.zeros(self.ABILITY_HIDDEN)
        ability_tensor = self.ability_pool(pooled)

        raw = torch.cat([scalar, typeTensor, ability_tensor])
        return self.proj(self.norm(raw))

class ZoneEncoder(nn.Module):
    def __init__(self, card_feat_dim=CARD_FEAT_DIM, hidden=64, zone_dim=64):
        super().__init__()
        self.zone_dim = zone_dim
        self.phi = nn.Sequential(
            nn.Linear(card_feat_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
        )
        self.rho = nn.Sequential(
            nn.Linear(hidden, zone_dim),
            nn.ReLU(),
            nn.Linear(zone_dim, zone_dim),
        )

    def forward(self, card_vecs):
        if not card_vecs:
            return self.rho(torch.zeros(self.phi[-1].in_features))
        stacked = torch.stack(card_vecs)
        per_card = self.phi(stacked)
        pooled = per_card.sum(dim=0)
        return self.rho(pooled)

c_encoder = CardEncoder()
z_encoder = ZoneEncoder()

def game_stateEncoder(state):
    scalars = torch.tensor([
        state.activePlayer.life / 20.0,
        state.inactivePlayer.life / 20.0,
        min((state.turnNumber // 2) + 2, 10) / 10.0,
        (state.activePlayer.life - state.inactivePlayer.life) / 20.0,
        (len(state.activePlayer.battlefield) - len(state.inactivePlayer.battlefield)) / 7.0,
        (len(state.activePlayer.hand)/5.0)])
    zones = torch.cat(
        [battlefield_stateEncoder(state.activePlayer.battlefield),
        battlefield_stateEncoder(state.inactivePlayer.battlefield),
        hand_stateEncoder(state.activePlayer.hand)])
    return torch.cat([scalars, zones])

def battlefield_stateEncoder(field):
    card_vecs = []
    for card in field:
        card_vecs.append(c_encoder(card))
    return z_encoder.forward(card_vecs)

def hand_stateEncoder(hand):
    card_vecs = []
    for cID in hand:
        card_vecs.append(c_encoder.forward(ActiveCardState(None, cID=cID)))
    return z_encoder.forward(card_vecs)


