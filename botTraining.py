import copy
from itertools import combinations, chain
from re import search

import torch
import torch.nn as nn
import torch.nn.functional as F

from Harness.Card import Card
from stateHelper import loadCardLibrary, ActiveCardState, AbilityKeys, Operands
from testing import create_random_game

N_TYPES = 16  # len(Types)
N_TRIGGERS = 6  # len(EventTriggers)
N_EFFECTS = 8  # len(EffectActions)
N_TARGETS = 9  # len(SimpleProducers)
N_OPERANDS = 14  # Access options + Filter options + Comparison + ['and' + 'or']

ABILITY_HIDDEN = 96
ABILITY_DIM = 64  # output dim per card's ability summary
TYPE_DIM = 16  # output of type embedding pool
CARD_FEAT_DIM = 2 + TYPE_DIM + ABILITY_DIM
ZONE_DIM = 64

STATE_DIM = 7 + 5*ZONE_DIM

REL_HIDDEN  = 64
OUT_DIM     = 64
TOWER_DIM   = 128

EPSILON = 0.35

cardLibrary = loadCardLibrary()


class AbilityEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.prim_trigger_emb = nn.Embedding(N_TRIGGERS + 1, ABILITY_HIDDEN, padding_idx=0)
        self.prim_effect_emb = nn.Embedding(N_EFFECTS + 1, ABILITY_HIDDEN, padding_idx=0)
        self.prim_target_emb = nn.Embedding(N_TARGETS + 1, ABILITY_HIDDEN, padding_idx=0)
        self.operand_emb = nn.Embedding(N_OPERANDS + 1, ABILITY_HIDDEN, padding_idx=0)

        self.node_mlp = nn.Sequential(
            nn.Linear(ABILITY_HIDDEN * 2, ABILITY_HIDDEN),
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
        self.typeEncoder = nn.Linear(TYPE_DIM, TYPE_DIM)

    def forward(self, cardState):
        typeOneHotTensor = torch.zeros(N_TYPES)
        for typeIndex in cardState.types:
            typeOneHotTensor[typeIndex - 1] = 1
        scalar = torch.tensor([cardState.atk / 10.0, cardState.df / 10.0], dtype=torch.float)
        if cardState.abilityData:
            ability_vecs = []
            for ability in cardState.abilityData:
                ability_vecs.append(self.abilityEncoder.forward(ability))
            pooled = torch.stack(ability_vecs).sum(dim=0)
        else:
            pooled = torch.zeros(ABILITY_HIDDEN)
        ability_tensor = self.ability_pool(pooled)
        typeTensor = self.typeEncoder.forward(typeOneHotTensor)
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
            return self.rho(torch.zeros(self.phi[-1].out_features))
        stacked = torch.stack(card_vecs)
        per_card = self.phi(stacked)
        pooled = per_card.sum(dim=0)
        return self.rho(pooled)



class State_Encoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.z_encoder = ZoneEncoder()
        self.c_encoder = CardEncoder()

    def non_hand_stateEncoder(self, zone):
        card_vecs = []
        for card in zone:
            card_vecs.append(self.c_encoder.forward(card))
        return self.z_encoder.forward(card_vecs)

    def hand_stateEncoder(self, hand):
        card_vecs = []
        for cID in hand:
            card_vecs.append(self.c_encoder.forward(ActiveCardState(None, cID=cID)))
        return self.z_encoder.forward(card_vecs)


    def forward(self, state, active=True):
        if active:
            scalars = torch.tensor([1.0, state.activePlayer.life / 20.0, state.inactivePlayer.life / 20.0,
                                    min((state.turnNumber // 2) + 2, 10) / 10.0,
                                    (state.activePlayer.life - state.inactivePlayer.life) / 20.0,
                                    (len(state.activePlayer.battlefield) - len(state.inactivePlayer.battlefield)) / 7.0,
                                    (len(state.activePlayer.hand) / 5.0)])
            zones = torch.cat(
                [self.non_hand_stateEncoder(state.activePlayer.battlefield),
                 self.non_hand_stateEncoder(state.activePlayer.graveyard),
                 self.non_hand_stateEncoder(state.inactivePlayer.battlefield),
                 self.non_hand_stateEncoder(state.inactivePlayer.graveyard),
                 self.hand_stateEncoder(state.activePlayer.hand)])
        else:
            scalars = torch.tensor([-1.0, state.inactivePlayer.life / 20.0, state.activePlayer.life / 20.0,
                                    min((state.turnNumber // 2) + 2, 10) / 10.0,
                                    (state.inactivePlayer.life - state.activePlayer.life) / 20.0,
                                    (len(state.inactivePlayer.battlefield) - len(state.activePlayer.battlefield)) / 7.0,
                                    (len(state.inactivePlayer.hand)) / 5.0])
            zones = torch.cat(
                [self.non_hand_stateEncoder(state.inactivePlayer.battlefield),
                 self.non_hand_stateEncoder(state.inactivePlayer.graveyard),
                 self.non_hand_stateEncoder(state.activePlayer.battlefield),
                 self.non_hand_stateEncoder(state.activePlayer.graveyard),
                 self.hand_stateEncoder(state.inactivePlayer.hand)]
            )
        return torch.cat([scalars, zones])

class Evaluator(nn.Module):
    def __init__(self):
        super().__init__()
        self.s_encoder = State_Encoder()
        self.relation_net = nn.Sequential(
            nn.Linear(CARD_FEAT_DIM*2, REL_HIDDEN),
            nn.ReLU(),
            nn.Linear(REL_HIDDEN, REL_HIDDEN),
        )
        self.context_net = nn.Sequential(
            nn.Linear(CARD_FEAT_DIM+REL_HIDDEN, OUT_DIM),
            nn.ReLU(),
        )
        self.player_tower_net = nn.Sequential(
            nn.Linear(STATE_DIM, TOWER_DIM),
            nn.ReLU(),
            nn.Linear(TOWER_DIM, TOWER_DIM // 2),
            nn.ReLU()
        )
        self.value_head = nn.Sequential(
            nn.Linear(OUT_DIM*2 + TOWER_DIM//2 + 7, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )
        self.tanH = nn.Tanh()

    def _encode_battlefield(self, cards):
        if not cards:
            return None
        return torch.stack([self.s_encoder.c_encoder(card) for card in cards])

    def _aggregate_relations(self, key_cards, query_cards):
        if query_cards is None or key_cards is None:
            N = 0 if query_cards is None else query_cards[0].shape
            return torch.zeros(N, REL_HIDDEN)
        N, M = query_cards[0].shape, key_cards[0].shape
        q_exp = query_cards.unsqueeze(1).expand(N, M, -1)
        k_exp = key_cards.unsqueeze(0).expand(N, M, -1)
        pairs = torch.cat([q_exp, k_exp], dim=-1)
        scores = self.relation_net(pairs)
        return scores.sum(dim=1)

    def forward(self, state, active=True):
        self_player = state.activePlayer if active else state.inactivePlayer
        opp_player = state.inactivePlayer if active else state.activePlayer

        state_vec = self.s_encoder(state, active=active)
        player_rep = self.player_tower_net(state_vec)
        scalars = state_vec[:7]

        my_cards = self._encode_battlefield(self_player.battlefield)
        opp_cards = self._encode_battlefield(opp_player.battlefield)

        pos_syns_self = self.aggregate_relations(my_cards, my_cards)
        neg_syns_self = self.aggregate_relations(my_cards, opp_cards)

        pos_syns_opp = self.aggregate_relations(opp_cards, opp_cards)
        neg_syns_opp = self.aggregate_relations(opp_cards, my_cards)

        if my_cards is not None:
            enriched_self = self.context_net(torch.cat([my_cards, pos_syns_self+neg_syns_self], dim=-1))
            rel_rep_self = enriched_self.sum(dim=0)
        else:
            rel_rep_self = torch.zeros(OUT_DIM)
        if opp_cards is not None:
            enriched_opp = self.context_net(torch.cat([opp_cards, pos_syns_opp+neg_syns_opp], dim=-1))
            rel_rep_opp = enriched_opp.sum(dim=0)
        else:
            rel_rep_opp = torch.zeros(OUT_DIM)

        combined = torch.cat([rel_rep_self, rel_rep_opp, player_rep, scalars])
        return self.tanH(self.value_head(combined))


