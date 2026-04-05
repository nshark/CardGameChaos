"""
visualInterface.py  –  auto-bot card game with a visual viewer
Run: python visualInterface.py
Press "Advance Turn" to step through the game.
"""

import json, random, sys, os, traceback, tkinter as tk
from tkinter import font as tkfont
from math import ceil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CARD_PATH   = os.path.join(SCRIPT_DIR, "cards.json")
sys.path.insert(0, SCRIPT_DIR)

with open(CARD_PATH) as f:
    cardData = json.load(f)["cards"]
regularCards = []
curseCards = []
cardLibrary = {}
for i in range(len(cardData)):
    cardLibrary[cardData[i]['id']] = cardData[i]
    if not 'Curse' in cardData[i]['types']:
        regularCards.append(cardData[i])
    else:
        curseCards.append(cardData[i])
from Game import Deck, Game, Player
from Card import Card

# ─────────────────────────────────────────────────────────────────────────────
# BOT AI
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
    ids_a = random.choices(regularCards, k=20)+random.choices(curseCards, k=random.randint(0,2))
    ids_b = random.choices(regularCards, k=20)+random.choices(curseCards, k=random.randint(0,2))
    deck_a = Deck(cardLibrary, ids_a, 0)
    deck_b = Deck(cardLibrary, ids_b, 1)
    return Game(deck_a, deck_b, logging=True)

# ─────────────────────────────────────────────────────────────────────────────
# PALETTE & CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
BG        = "#0d0f14"
PANEL     = "#141720"
PANEL2    = "#0f1219"
BORDER    = "#1e2535"
ACCENT    = "#4f8ef7"
RED       = "#e8445a"
GREEN     = "#3ecf8e"
GOLD      = "#f5c542"
ORANGE    = "#f09a3e"
PURPLE    = "#a97cf5"
MUTED     = "#5a6480"
TEXT      = "#d0d8f0"
TEXT_DIM  = "#6b7394"
WHITE     = "#ffffff"
P1_COLOR  = "#4f8ef7"
P2_COLOR  = "#e8445a"

CARD_W, CARD_H = 110, 76
CARD_PAD       = 8

# Map log category -> (icon, fg color)
CAT_STYLE = {
    'phase':   (" - ",  "#4a5580"),
    'play':    (" > ",  ACCENT),
    'sac':     (" * ",  PURPLE),
    'combat':  (" x ",  GOLD),
    'kill':    (" X ",  RED),
    'trigger': (" ! ",  ORANGE),
    'damage':  (" v ",  "#e05555"),
    'draw':    (" + ",  GREEN),
    'discard': (" ^ ",  MUTED),
    'bounce':  (" < ",  "#5ad4f5"),
    'revive':  (" ~ ",  GREEN),
    'stat':    (" . ",  MUTED),
    'info':    ("   ",  TEXT_DIM),
}

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
        self.game = new_game()
        self._build_ui()
        self._render()

    def _load_fonts(self):
        self.f_title  = tkfont.Font(family="Courier", size=13, weight="bold")
        self.f_name   = tkfont.Font(family="Courier", size=8,  weight="bold")
        self.f_stat   = tkfont.Font(family="Courier", size=9)
        self.f_label  = tkfont.Font(family="Courier", size=9,  weight="bold")
        self.f_small  = tkfont.Font(family="Courier", size=7)
        self.f_log    = tkfont.Font(family="Courier", size=8)
        self.f_log_hd = tkfont.Font(family="Courier", size=8,  weight="bold")
        self.f_life   = tkfont.Font(family="Courier", size=22, weight="bold")

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # top header bar
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
            hdr, text=">  ADVANCE TURN", command=self._advance,
            bg=ACCENT, fg=WHITE, activebackground="#2d5ecb",
            activeforeground=WHITE, relief="flat",
            font=self.f_label, padx=18, pady=6, cursor="hand2"
        )
        self.btn_advance.grid(row=0, column=2, padx=12, pady=6, sticky="e")

        self.btn_new = tk.Button(
            hdr, text="NEW GAME", command=self._new_game,
            bg=PANEL, fg=MUTED, activebackground=BORDER,
            activeforeground=TEXT, relief="flat",
            font=self.f_label, padx=12, pady=6, cursor="hand2"
        )
        self.btn_new.grid(row=0, column=3, padx=(0, 12), pady=6, sticky="e")

        # main body
        body = tk.Frame(self, bg=BG)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=270)
        body.rowconfigure(0, weight=1)

        # board canvas
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.canvas.bind("<Configure>", lambda e: self._render())

        # right panel
        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=8)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.rowconfigure(3, weight=1)

        # Last Turn panel
        tk.Label(right, text="LAST TURN", bg=BG, fg=MUTED,
                 font=self.f_label, pady=4).grid(row=0, column=0, sticky="w", padx=4)

        lt_frame = tk.Frame(right, bg=PANEL2, bd=0)
        lt_frame.grid(row=1, column=0, sticky="nsew")
        lt_frame.columnconfigure(0, weight=1)
        lt_frame.rowconfigure(0, weight=1)

        self.lt_text = tk.Text(
            lt_frame, bg=PANEL2, fg=TEXT, font=self.f_log,
            relief="flat", wrap="word", state="disabled",
            width=32, insertbackground=TEXT,
            spacing1=1, spacing3=1,
        )
        self.lt_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        lt_sb = tk.Scrollbar(lt_frame, command=self.lt_text.yview, bg=PANEL2,
                             troughcolor=PANEL2, relief="flat")
        lt_sb.grid(row=0, column=1, sticky="ns")
        self.lt_text.configure(yscrollcommand=lt_sb.set)

        # color tags for last-turn panel
        for cat, (icon, color) in CAT_STYLE.items():
            self.lt_text.tag_configure(f"icon_{cat}", foreground=color,
                                       font=self.f_log_hd)
            self.lt_text.tag_configure(f"msg_{cat}",  foreground=color)
        self.lt_text.tag_configure("phase_line", foreground="#5a6ba0",
                                   font=self.f_log_hd)
        self.lt_text.tag_configure("turn_hdr", foreground=ACCENT,
                                   font=self.f_log_hd)
        self.lt_text.tag_configure("section_div", foreground=BORDER)

        # Full log label + panel
        tk.Label(right, text="FULL LOG", bg=BG, fg=MUTED,
                 font=self.f_label, pady=4).grid(row=2, column=0, sticky="w", padx=4)

        hist_frame = tk.Frame(right, bg=PANEL, bd=0)
        hist_frame.grid(row=3, column=0, sticky="nsew")
        hist_frame.columnconfigure(0, weight=1)
        hist_frame.rowconfigure(0, weight=1)

        self.hist_text = tk.Text(
            hist_frame, bg=PANEL, fg=TEXT_DIM, font=self.f_small,
            relief="flat", wrap="word", state="disabled",
            width=32, insertbackground=TEXT,
        )
        self.hist_text.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        hist_sb = tk.Scrollbar(hist_frame, command=self.hist_text.yview, bg=PANEL,
                               troughcolor=PANEL, relief="flat")
        hist_sb.grid(row=0, column=1, sticky="ns")
        self.hist_text.configure(yscrollcommand=hist_sb.set)

        # color tags for full log
        for cat, (icon, color) in CAT_STYLE.items():
            self.hist_text.tag_configure(f"h_{cat}", foreground=color)
        self.hist_text.tag_configure("h_phase", foreground="#3a4260")
        self.hist_text.tag_configure("h_hdr", foreground=ACCENT)

    # ── advance one turn ──────────────────────────────────────────────────────
    def _advance(self):
        if self.game.scheduleEnd:
            self._append_history("-- Game over --", "info")
            return
        try:
            self.game.takeTurn()
            self._refresh_last_turn(self.game.turnLog, self.game.turnNumber - 1)
            self._append_turn_to_history(self.game.turnLog, self.game.turnNumber - 1)
        except Exception:
            err = traceback.format_exc().splitlines()[-1]
            self._append_history(f"ERROR: {err}", "info")
        self._render()

    def _new_game(self):
        self.game = new_game()
        self._clear_widget(self.lt_text)
        self._clear_widget(self.hist_text)
        self._append_history("New game started!", "info")
        self._render()

    # ── Last Turn panel ───────────────────────────────────────────────────────
    def _refresh_last_turn(self, turn_log, turn_number):
        w = self.lt_text
        w.configure(state="normal")
        w.delete("1.0", "end")

        active = "P0" if turn_number % 2 == 0 else "P1"
        w.insert("end", f"Turn {turn_number}  -  {active}'s turn\n", "turn_hdr")
        w.insert("end", "-" * 28 + "\n", "section_div")

        if not turn_log:
            w.insert("end", "  (nothing happened)\n", "msg_info")
            w.configure(state="disabled")
            return

        prev_was_phase = False
        for entry in turn_log:
            if isinstance(entry, dict):
                cat, msg = entry['cat'], entry['msg']
            else:
                cat, msg = 'info', str(entry)

            if cat == 'phase':
                if not prev_was_phase:
                    w.insert("end", "\n")
                w.insert("end", f"  {msg}\n", "phase_line")
                prev_was_phase = True
                continue

            prev_was_phase = False
            icon, _ = CAT_STYLE.get(cat, ("   ", TEXT_DIM))
            w.insert("end", icon, f"icon_{cat}")
            w.insert("end", f"{msg}\n", f"msg_{cat}")

        w.see("end")
        w.configure(state="disabled")

    # ── Full log panel ────────────────────────────────────────────────────────
    def _append_turn_to_history(self, turn_log, turn_number):
        w = self.hist_text
        w.configure(state="normal")
        active = "P0" if turn_number % 2 == 0 else "P1"
        w.insert("end", f"\nT{turn_number} ({active})\n", "h_hdr")
        for entry in turn_log:
            if isinstance(entry, dict):
                cat, msg = entry['cat'], entry['msg']
            else:
                cat, msg = 'info', str(entry)
            if cat == 'phase':
                continue
            icon, _ = CAT_STYLE.get(cat, ("   ", TEXT_DIM))
            w.insert("end", f"{icon}{msg}\n", f"h_{cat}")
        w.see("end")
        w.configure(state="disabled")

    def _append_history(self, msg, cat="info"):
        w = self.hist_text
        w.configure(state="normal")
        w.insert("end", f"{msg}\n", f"h_{cat}")
        w.see("end")
        w.configure(state="disabled")

    def _clear_widget(self, w):
        w.configure(state="normal")
        w.delete("1.0", "end")
        w.configure(state="disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # RENDER  (board canvas)
    # ─────────────────────────────────────────────────────────────────────────
    def _render(self):
        c = self.canvas
        g = self.game
        c.delete("all")

        W  = c.winfo_width()  or 800
        H  = c.winfo_height() or 600
        cx = W // 2

        turn_owner = "Player 0" if g.turnNumber % 2 == 0 else "Player 1"
        energy = min((g.turnNumber // 2) + 2, 10)
        self.lbl_turn.config(text=f"TURN {g.turnNumber}")
        status = f"Active: {turn_owner}  |  Energy: {energy}"
        if g.scheduleEnd:
            if g.p1.life <= 0 and g.p2.life <= 0:
                status = "DRAW"
            elif g.p1.life <= 0:
                status = "PLAYER 1 WINS"
            else:
                status = "PLAYER 0 WINS"
        self.lbl_status.config(text=status)

        row_h    = (H - 60) // 5
        row_tops = [10 + i * row_h for i in range(5)]
        mid_y    = row_tops[2] + row_h // 2

        c.create_line(20, mid_y, W - 20, mid_y, fill=BORDER, width=1, dash=(4, 4))

        self._draw_life_bar(c, g.p2, cx - 140, mid_y - 30, 120, "P1", P2_COLOR)
        self._draw_life_bar(c, g.p1, cx + 20,  mid_y - 30, 120, "P0", P1_COLOR)

        c.create_text(cx, mid_y + 14,
                      text=f"gy  P1:{len(g.p2.graveyard)}   P0:{len(g.p1.graveyard)}",
                      fill=MUTED, font=self.f_small)

        self._draw_zone(c, g.p2.hand,        W, row_tops[0], row_h, "P1 HAND",        P2_COLOR, face_down=True)
        self._draw_zone(c, g.p2.battlefield, W, row_tops[1], row_h, "P1 BATTLEFIELD",  P2_COLOR)
        self._draw_zone(c, g.p1.battlefield, W, row_tops[3], row_h, "P0 BATTLEFIELD",  P1_COLOR)
        self._draw_zone(c, g.p1.hand,        W, row_tops[4], row_h, "P0 HAND",         P1_COLOR)

        c.create_text(W - 10, H - 10,
                      text=f"deck  P0:{len(g.p1.deck.drawOrder)}  P1:{len(g.p2.deck.drawOrder)}",
                      fill=TEXT_DIM, font=self.f_small, anchor="se")

    def _draw_life_bar(self, c, player, x, y, w, label, color):
        life  = max(player.life, 0)
        pct   = min(life / 20, 1.0)
        bar_h = 14
        c.create_rectangle(x, y + 18, x + w, y + 18 + bar_h,
                           fill=BORDER, outline="", width=0)
        fill_w = int(w * pct)
        if fill_w > 0:
            c.create_rectangle(x, y + 18, x + fill_w, y + 18 + bar_h,
                               fill=color, outline="", width=0)
        c.create_text(x + w // 2, y + 18 + bar_h // 2,
                      text=str(player.life), fill=WHITE, font=self.f_stat)
        c.create_text(x, y + 12, text=label, fill=color,
                      font=self.f_label, anchor="w")

    def _draw_zone(self, c, cards, canvas_w, y, row_h, label, color, face_down=False):
        c.create_text(14, y + 8, text=label, fill=color,
                      font=self.f_small, anchor="nw")
        if not cards:
            c.create_text(canvas_w // 2, y + row_h // 2,
                          text="--", fill=MUTED, font=self.f_stat)
            return
        total_w = len(cards) * (CARD_W + CARD_PAD) - CARD_PAD
        start_x = (canvas_w - total_w) // 2
        card_y  = y + (row_h - CARD_H) // 2
        for i, card in enumerate(cards):
            cx_ = start_x + i * (CARD_W + CARD_PAD)
            self._draw_card(c, card, cx_, card_y, color, face_down)

    def _draw_card(self, c, card, x, y, accent, face_down=False):
        c.create_rectangle(x+3, y+3, x+CARD_W+3, y+CARD_H+3,
                           fill="#000000", outline="", width=0)
        bg = "#1a1f30" if face_down else "#1c2236"
        c.create_rectangle(x, y, x+CARD_W, y+CARD_H,
                           fill=bg, outline=accent, width=1)
        if face_down:
            c.create_rectangle(x+6, y+6, x+CARD_W-6, y+CARD_H-6,
                               fill="", outline=BORDER, width=1, dash=(3, 3))
            c.create_text(x + CARD_W//2, y + CARD_H//2,
                          text="?", fill=MUTED, font=self.f_title)
            return

        c.create_rectangle(x, y, x+CARD_W, y+5, fill=accent, outline="", width=0)

        name = card.name if len(card.name) <= 14 else card.name[:12] + "..."
        c.create_text(x + CARD_W//2, y + 16,
                      text=name, fill=TEXT, font=self.f_name, anchor="center")

        type_str = "/".join(card.types)[:12]
        c.create_text(x + CARD_W//2, y + 28,
                      text=type_str, fill=MUTED, font=self.f_small)

        c.create_line(x+6, y+36, x+CARD_W-6, y+36, fill=BORDER)

        # gold tint if stat was modified by a trigger
        atk_color = GOLD  if card.atk != card.base_atk else RED
        def_color = GOLD  if card.df  != card.base_df  else GREEN
        c.create_text(x + 18,          y + 50, text=f"A {card.atk}", fill=atk_color, font=self.f_stat)
        c.create_text(x + CARD_W - 18, y + 50, text=f"D {card.df}",  fill=def_color, font=self.f_stat)

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
    app.minsize(820, 560)
    app.geometry("1150x680")
    app.mainloop()