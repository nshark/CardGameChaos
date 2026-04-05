"""
visualize_game.py  –  auto-bot card game with a visual viewer
Run: python visualize_game.py
Press "Advance Turn" to step through the game.
"""

import json, random, sys, os, traceback, tkinter as tk
from tkinter import font as tkfont
from math import ceil
from copy import copy

# ── locate cards.json next to this script ────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CARD_PATH = os.path.join(SCRIPT_DIR, "cards.json")

# ── patch sys.path so we can import the game modules ─────────────────────────
sys.path.insert(0, SCRIPT_DIR)

# ── load card library ─────────────────────────────────────────────────────────
with open(CARD_PATH) as f:
    _raw = json.load(f)["cards"]
cardLibrary = {c["id"]: c for c in _raw}

# ── import game objects ───────────────────────────────────────────────────────
from Game import Deck, Game, Player
from Card import Card

# ─────────────────────────────────────────────────────────────────────────────
# BOT AI  (identical to testing.py)
# ─────────────────────────────────────────────────────────────────────────────
def card_value(card):
    return card.atk + card.df

def bot_opponent(self, game):
    return game.p2 if self.deck.cards[0].pID == 0 else game.p1

def would_survive_attack(attacker, defender):
    return attacker.atk >= defender.df and not (defender.atk >= attacker.df)

def favorable_trade(attacker, defender):
    return attacker.atk >= defender.df and card_value(attacker) >= card_value(defender)

def bot_request_decision(self, type, game, num=0, energy=0,
                          attackers=[], availableDefenders=[], pCard=None):
    pID      = self.deck.cards[0].pID
    opponent = bot_opponent(self, game)

    if type == "playCards":
        affordable = [c for c in self.hand
                      if c.costs["energy"] <= energy
                      and c.costs["life"] < self.life
                      and c.costs["sacCost"] == 0]
        affordable.sort(key=card_value, reverse=True)
        card_order, remaining_energy = [], energy
        for card in affordable:
            if card.costs["energy"] <= remaining_energy:
                card_order.append(card)
                remaining_energy -= card.costs["energy"]
        potential_sacs = sorted(self.battlefield, key=card_value)
        sac_pool = list(potential_sacs)
        sac_energy_available = sum(c.atk for c in sac_pool)
        for card in sorted(self.hand, key=card_value, reverse=True):
            if card in card_order:
                continue
            if (card.costs["energy"] <= remaining_energy
                    and card.costs["life"] < self.life
                    and card.costs["sacCost"] > 0
                    and sac_energy_available >= card.costs["sacCost"]
                    and card_value(card) > card.costs["sacCost"]):
                card_order.append(card)
                remaining_energy -= card.costs["energy"]
        return card_order, sac_pool

    elif type == "attackers":
        if not self.battlefield:
            return []
        op_field = list(opponent.battlefield)
        if not op_field:
            return list(self.battlefield)
        selected = []
        for attacker in self.battlefield:
            kills_something = any(attacker.atk >= d.df for d in op_field)
            safe_kill   = any(would_survive_attack(attacker, d) for d in op_field)
            favorable   = any(favorable_trade(attacker, d) for d in op_field)
            if safe_kill or favorable:
                selected.append(attacker)
            elif kills_something and attacker.atk > attacker.df:
                selected.append(attacker)
            elif not any(d.atk >= attacker.df for d in op_field):
                selected.append(attacker)
        if len(self.battlefield) > len(op_field) + 1 and not selected:
            selected = list(self.battlefield)
        return selected

    elif type == "defenders":
        if not self.battlefield:
            return []
        defenders, available = [], list(self.battlefield)
        for attacker in sorted(attackers, key=lambda a: a.atk, reverse=True):
            if not available:
                break
            ideal = next((d for d in available if would_survive_attack(d, attacker)), None)
            if ideal:
                defenders.append(ideal); available.remove(ideal); continue
            can_kill = next((d for d in available if d.atk >= attacker.df), None)
            if can_kill:
                if card_value(can_kill) <= card_value(attacker) + 2:
                    defenders.append(can_kill); available.remove(can_kill); continue
            if attacker.atk >= self.life or attacker.atk >= 5:
                chump = min(available, key=card_value)
                defenders.append(chump); available.remove(chump)
        return defenders

    elif type == "discard":
        return sorted(range(len(self.hand)), key=lambda i: card_value(self.hand[i]))[:num]

    elif type == "target":
        if not opponent.battlefield:
            return None
        killable = [c for c in opponent.battlefield if pCard and pCard.atk >= c.df]
        if killable:
            return max(killable, key=card_value)
        return max(opponent.battlefield, key=lambda c: c.atk)

Player.requestDecision = bot_request_decision

# ─────────────────────────────────────────────────────────────────────────────
# GAME FACTORY
# ─────────────────────────────────────────────────────────────────────────────
def new_game():
    ids_a = random.choices(range(1, 68), k=20)
    ids_b = random.choices(range(1, 68), k=20)
    deck_a = Deck(cardLibrary, ids_a, 0)
    deck_b = Deck(cardLibrary, ids_b, 1)
    return Game(deck_a, deck_b)

# ─────────────────────────────────────────────────────────────────────────────
# PALETTE & CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
BG       = "#0d0f14"
PANEL    = "#141720"
BORDER   = "#1e2535"
ACCENT   = "#4f8ef7"
RED      = "#e8445a"
GREEN    = "#3ecf8e"
GOLD     = "#f5c542"
MUTED    = "#5a6480"
TEXT     = "#d0d8f0"
TEXT_DIM = "#6b7394"
WHITE    = "#ffffff"

P1_COLOR = "#4f8ef7"   # blue
P2_COLOR = "#e8445a"   # red

CARD_W, CARD_H = 110, 76
CARD_PAD       = 8

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
class GameViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Card Game Viewer")
        self.configure(bg=BG)
        self.resizable(True, True)

        self._load_fonts()
        self.game   = new_game()
        self.log    = []        # list of strings for the log panel
        self._build_ui()
        self._render()

    # ── fonts ─────────────────────────────────────────────────────────────────
    def _load_fonts(self):
        self.f_title  = tkfont.Font(family="Courier", size=13, weight="bold")
        self.f_name   = tkfont.Font(family="Courier", size=8,  weight="bold")
        self.f_stat   = tkfont.Font(family="Courier", size=9)
        self.f_label  = tkfont.Font(family="Courier", size=9,  weight="bold")
        self.f_small  = tkfont.Font(family="Courier", size=7)
        self.f_log    = tkfont.Font(family="Courier", size=8)
        self.f_life   = tkfont.Font(family="Courier", size=22, weight="bold")

    # ── build static UI skeleton ───────────────────────────────────────────────
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── top header bar ────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=PANEL, height=48)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)

        self.lbl_turn = tk.Label(hdr, text="", bg=PANEL, fg=ACCENT,
                                 font=self.f_title, padx=16)
        self.lbl_turn.grid(row=0, column=0, sticky="w")

        self.lbl_status = tk.Label(hdr, text="", bg=PANEL, fg=TEXT,
                                   font=self.f_stat)
        self.lbl_status.grid(row=0, column=1)

        self.btn_advance = tk.Button(
            hdr, text="▶  ADVANCE TURN", command=self._advance,
            bg=ACCENT, fg=WHITE, activebackground="#2d5ecb",
            activeforeground=WHITE, relief="flat",
            font=self.f_label, padx=18, pady=6, cursor="hand2"
        )
        self.btn_advance.grid(row=0, column=2, padx=12, pady=6, sticky="e")

        self.btn_new = tk.Button(
            hdr, text="↺  NEW GAME", command=self._new_game,
            bg=PANEL, fg=MUTED, activebackground=BORDER,
            activeforeground=TEXT, relief="flat",
            font=self.f_label, padx=12, pady=6, cursor="hand2"
        )
        self.btn_new.grid(row=0, column=3, padx=(0, 12), pady=6, sticky="e")

        # ── main body: board + log ─────────────────────────────────────────────
        body = tk.Frame(self, bg=BG)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=220)
        body.rowconfigure(0, weight=1)

        # board canvas
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.canvas.bind("<Configure>", lambda e: self._render())

        # log panel
        log_frame = tk.Frame(body, bg=PANEL, width=220)
        log_frame.grid(row=0, column=1, sticky="nsew", padx=(0,8), pady=8)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        tk.Label(log_frame, text="GAME LOG", bg=PANEL, fg=MUTED,
                 font=self.f_label, pady=6).grid(row=0, column=0)

        self.log_text = tk.Text(
            log_frame, bg=PANEL, fg=TEXT_DIM, font=self.f_log,
            relief="flat", wrap="word", state="disabled",
            width=28, insertbackground=TEXT
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0,6))
        sb = tk.Scrollbar(log_frame, command=self.log_text.yview, bg=PANEL,
                          troughcolor=PANEL, relief="flat")
        sb.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sb.set)

    # ── advance one turn ──────────────────────────────────────────────────────
    def _advance(self):
        if self.game.scheduleEnd:
            self._add_log("── Game over. Start a new game. ──")
            return
        try:
            self.game.takeTurn()
            self._add_log(f"Turn {self.game.turnNumber} complete")
        except Exception:
            self._add_log("ERROR: " + traceback.format_exc().splitlines()[-1])
        self._render()

    def _new_game(self):
        self.game = new_game()
        self.log  = []
        self._clear_log()
        self._add_log("New game started!")
        self._render()

    # ── log helpers ───────────────────────────────────────────────────────────
    def _add_log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # RENDER
    # ─────────────────────────────────────────────────────────────────────────
    def _render(self):
        c  = self.canvas
        g  = self.game
        c.delete("all")

        W  = c.winfo_width()  or 800
        H  = c.winfo_height() or 600
        cx = W // 2

        # header labels
        turn_owner = "Player 1" if g.turnNumber % 2 == 0 else "Player 2"
        energy = min((g.turnNumber // 2) + 2, 10)
        self.lbl_turn.config(text=f"TURN {g.turnNumber}")
        status = f"Active: {turn_owner}  |  Energy: {energy}"
        if g.scheduleEnd:
            if g.p1.life <= 0 and g.p2.life <= 0:
                status = "⚔  DRAW"
            elif g.p1.life <= 0:
                status = "🏆  PLAYER 2 WINS"
            else:
                status = "🏆  PLAYER 1 WINS"
        self.lbl_status.config(text=status)

        # ── layout rows ───────────────────────────────────────────────────────
        #   row 0 (top)   : P2 hand
        #   row 1         : P2 battlefield
        #   row 2 (center): divider / life bars
        #   row 3         : P1 battlefield
        #   row 4 (bottom): P1 hand

        row_h     = (H - 60) // 5   # height per row (minus a small footer)
        row_tops  = [10 + i * row_h for i in range(5)]

        # ── draw divider ──────────────────────────────────────────────────────
        mid_y = row_tops[2] + row_h // 2
        c.create_line(20, mid_y, W - 20, mid_y, fill=BORDER, width=1, dash=(4, 4))

        # ── life bars ─────────────────────────────────────────────────────────
        self._draw_life_bar(c, g.p2, cx - 140, mid_y - 30, 120, label="P2", color=P2_COLOR)
        self._draw_life_bar(c, g.p1, cx + 20,  mid_y - 30, 120, label="P1", color=P1_COLOR)

        # graveyard counts in middle
        c.create_text(cx, mid_y + 10, text=f"P2 gy: {len(g.p2.graveyard)}   P1 gy: {len(g.p1.graveyard)}",
                      fill=MUTED, font=self.f_small)

        # ── zones ─────────────────────────────────────────────────────────────
        self._draw_zone(c, g.p2.hand,        W, row_tops[0], row_h, "P2 HAND",        P2_COLOR, face_down=True)
        self._draw_zone(c, g.p2.battlefield, W, row_tops[1], row_h, "P2 BATTLEFIELD",  P2_COLOR)
        self._draw_zone(c, g.p1.battlefield, W, row_tops[3], row_h, "P1 BATTLEFIELD",  P1_COLOR)
        self._draw_zone(c, g.p1.hand,        W, row_tops[4], row_h, "P1 HAND",         P1_COLOR)

        # deck sizes bottom-right
        c.create_text(W - 10, H - 10,
                      text=f"P1 deck: {len(g.p1.deck.drawOrder)}   P2 deck: {len(g.p2.deck.drawOrder)}",
                      fill=TEXT_DIM, font=self.f_small, anchor="se")

    # ── life bar ──────────────────────────────────────────────────────────────
    def _draw_life_bar(self, c, player, x, y, w, label, color):
        life     = max(player.life, 0)
        pct      = min(life / 20, 1.0)
        bar_h    = 14
        # background
        c.create_rectangle(x, y + 18, x + w, y + 18 + bar_h,
                           fill=BORDER, outline="", width=0)
        # fill
        fill_w = int(w * pct)
        if fill_w > 0:
            c.create_rectangle(x, y + 18, x + fill_w, y + 18 + bar_h,
                               fill=color, outline="", width=0)
        # life number
        life_txt = str(player.life)
        c.create_text(x + w // 2, y + 18 + bar_h // 2,
                      text=life_txt, fill=WHITE, font=self.f_stat)
        # label
        c.create_text(x, y + 12, text=label, fill=color,
                      font=self.f_label, anchor="w")

    # ── zone of cards ─────────────────────────────────────────────────────────
    def _draw_zone(self, c, cards, canvas_w, y, row_h, label, color, face_down=False):
        # zone label on left
        c.create_text(14, y + 8, text=label, fill=color,
                      font=self.f_small, anchor="nw")

        if not cards:
            c.create_text(canvas_w // 2, y + row_h // 2,
                          text="—", fill=MUTED, font=self.f_stat)
            return

        total_w  = len(cards) * (CARD_W + CARD_PAD) - CARD_PAD
        start_x  = (canvas_w - total_w) // 2
        card_y   = y + (row_h - CARD_H) // 2

        for i, card in enumerate(cards):
            cx_ = start_x + i * (CARD_W + CARD_PAD)
            self._draw_card(c, card, cx_, card_y, color, face_down)

    # ── single card ───────────────────────────────────────────────────────────
    def _draw_card(self, c, card, x, y, accent, face_down=False):
        r = 5  # corner radius

        # shadow
        c.create_rectangle(x+3, y+3, x+CARD_W+3, y+CARD_H+3,
                           fill="#000000", outline="", width=0)

        # card face
        if face_down:
            bg = "#1a1f30"
        else:
            bg = "#1c2236"

        # rounded-rect simulation (tkinter lacks native rounded rect on canvas easily)
        c.create_rectangle(x, y, x+CARD_W, y+CARD_H,
                           fill=bg, outline=accent, width=1)

        if face_down:
            # draw a simple pattern
            c.create_rectangle(x+6, y+6, x+CARD_W-6, y+CARD_H-6,
                               fill="", outline=BORDER, width=1, dash=(3,3))
            c.create_text(x + CARD_W//2, y + CARD_H//2,
                          text="?", fill=MUTED, font=self.f_title)
            return

        # accent bar at top
        c.create_rectangle(x, y, x+CARD_W, y+5, fill=accent, outline="", width=0)

        # name (truncate if needed)
        name = card.name if len(card.name) <= 14 else card.name[:12] + "…"
        c.create_text(x + CARD_W//2, y + 16,
                      text=name, fill=TEXT, font=self.f_name, anchor="center")

        # type tag
        type_str = "/".join(card.types)[:12]
        c.create_text(x + CARD_W//2, y + 28,
                      text=type_str, fill=MUTED, font=self.f_small)

        # divider
        c.create_line(x+6, y+36, x+CARD_W-6, y+36, fill=BORDER)

        # ATK / DEF
        c.create_text(x + 18, y + 50, text=f"⚔ {card.atk}", fill=RED,  font=self.f_stat)
        c.create_text(x + CARD_W - 18, y + 50, text=f"🛡 {card.df}", fill=GREEN, font=self.f_stat)

        # cost hint
        cost_str = f"E:{card.costs['energy']}"
        if card.costs['life']:
            cost_str += f" L:{card.costs['life']}"
        if card.costs['sacCost']:
            cost_str += f" S:{card.costs['sacCost']}"
        c.create_text(x + CARD_W//2, y + CARD_H - 7,
                      text=cost_str, fill=TEXT_DIM, font=self.f_small)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = GameViewer()
    app.minsize(780, 560)
    app.geometry("1000x660")
    app.mainloop()