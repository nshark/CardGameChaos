import json
import tkinter as tk
from tkinter import ttk, messagebox
from Harness.Card import Card
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TYPES = [
    "Fire", "Water", "Earth", "Dark", "Light", "Thunder",
    "Wind", "Holy", "Nature", "Dragon", "Warrior", "Beast",
    "Mage", "Spell", "Undead", "Curse",
]
SIMPLE_TRIGGERS = ["entranceThis", "exitThis", "entranceAny", "exitAny", "onKill", "onThisDmgPlayer"]
SIMPLE_PRODUCERS = ["this", "lastEntered", "lastExited", "lastKilled","target", "self", "opponent", "allOpCards", "allFrCards"]
PRIMITIVE_VALUES = (
    SIMPLE_PRODUCERS
    + SIMPLE_TRIGGERS
)
OPERANDS = ["and", "or", "if", "access", "filter"]
CMP_OPTIONS = ["==", "<", "<=", "contains"]
ACCESS_OPTIONS = ["types", "atk", "df", "__len__"]
EFFECT_TARGETING = [
    "this", "lastEntered", "lastExited", "lastKilled",
    "target", "self", "opponent", "allOpCards", "allFrCards",
]
EFFECT_ACTIONS = ["dmg", "kill", "draw", "discard", "modAtk", "modDef", "bounce", "revive"]
CARDS_PATH = "/cards.json"
COMPLEX_SENTINEL = "complex(...)"
PRIMITIVE_FILTERS = ['attr>', 'attr<', 'attr=']

# ---------------------------------------------------------------------------
# TriggerSlotWidget
# ---------------------------------------------------------------------------
class TriggerSlotWidget:
    """
    Represents one trigger/pow slot.  Can be in two modes:
      simple  – a combobox with primitive values + COMPLEX_SENTINEL
      complex – operand combobox + operand-specific child slots
    """

    def __init__(self, parent, is_pow=False, on_change=None, is_action=False, reqBoolean=False):
        self.combo_var = None
        self.is_action = is_action
        self.parent = parent
        self.is_pow = is_pow
        self.on_change = on_change  # called after any structural change
        self.mode = "simple"
        self.reqBoolean = reqBoolean
        # child state (complex mode)
        self.children = []      # list of TriggerSlotWidget (for and/or)
        self.child_a = None     # first child (if)
        self.child_b = None     # second child (if)
        self.child = None       # single child (access)

        self.container = tk.Frame(parent, bd=1, relief="groove", padx=4, pady=2)
        self.container.pack(fill="x", expand=True, pady=2)

        self._build_simple()

    # ------------------------------------------------------------------
    # Simple mode
    # ------------------------------------------------------------------
    def _build_simple(self):
        self.mode = "simple"
        for w in self.container.winfo_children():
            w.destroy()

        row = tk.Frame(self.container)
        row.pack(fill="x")

        if self.is_pow:
            tk.Label(row, text="pow:").pack(side="left")
            self.pow_var = tk.StringVar(value="0")
            self.pow_spin = tk.Spinbox(
                row, from_=-99, to=99, width=5, textvariable=self.pow_var
            )
            self.pow_spin.pack(side="left", padx=2)
            tk.Label(row, text="or").pack(side="left")
        elif self.is_action:
            tk.Label(row, text="source:").pack(side="left")
            self.action_var = tk.StringVar(value=EFFECT_TARGETING[0])
            self.action_combo = ttk.Combobox(row, textvariable=self.action_var, values=EFFECT_TARGETING+[COMPLEX_SENTINEL], state="readonly", width=22)
            self.action_combo.pack(side="left", padx=2)
            self.action_combo.bind("<<ComboboxSelected>>", self._on_simple_select)
            tk.Label(row, text="or").pack(side="left")
        if not self.is_action:
            if not self.reqBoolean:
                self.combo_var = tk.StringVar(
                    value=SIMPLE_PRODUCERS[0] if not (self.is_pow or self.is_action) else COMPLEX_SENTINEL)
                choices = ([COMPLEX_SENTINEL] + TYPES + SIMPLE_PRODUCERS) if (self.is_pow or self.is_action) else (
                            TYPES + SIMPLE_PRODUCERS + [COMPLEX_SENTINEL])
            else:
                self.combo_var = tk.StringVar(value=SIMPLE_TRIGGERS[0] if not (self.is_pow or self.is_action) else COMPLEX_SENTINEL)
                choices = ([COMPLEX_SENTINEL] + SIMPLE_TRIGGERS) if (self.is_pow or self.is_action) else (SIMPLE_TRIGGERS + [COMPLEX_SENTINEL])
            self.combo = ttk.Combobox(
                row, textvariable=self.combo_var, values=choices, state="readonly", width=22
            )
            self.combo.pack(side="left", padx=2)
            self.combo.bind("<<ComboboxSelected>>", self._on_simple_select)

    def _on_simple_select(self, _event=None):
        if self.is_action and self.action_var.get() == COMPLEX_SENTINEL:
            self._switch_to_complex()
        if (not self.is_action) and self.combo_var.get() == COMPLEX_SENTINEL:
            self._switch_to_complex()
        if self.on_change:
            self.on_change()

    # ------------------------------------------------------------------
    # Complex mode
    # ------------------------------------------------------------------
    def _switch_to_complex(self):
        self.mode = "complex"
        for w in self.container.winfo_children():
            w.destroy()
        header = tk.Frame(self.container)
        header.pack(fill="x")
        if not self.is_action:
            tk.Label(header, text="operand:").pack(side="left")
            self.operand_var = tk.StringVar(value=OPERANDS[0])
            op_combo = ttk.Combobox(
                header, textvariable=self.operand_var,
                values=OPERANDS, state="readonly", width=8
            )
            op_combo.pack(side="left", padx=2)
            op_combo.bind("<<ComboboxSelected>>", self._on_operand_change)
        else:
            tk.Label(header, text="filter:").pack(side="left")
            self.filter_var = tk.StringVar(value=PRIMITIVE_FILTERS[0])
            filter_combo = ttk.Combobox(header, textvariable=self.filter_var, values=PRIMITIVE_FILTERS, state="readonly", width=8)
            filter_combo.pack(side="left", padx=2)
            filter_combo.bind("<<ComboboxSelected>>", self._on_filter_change)
        tk.Button(
            header, text="Collapse", command=self._collapse, padx=2
        ).pack(side="left", padx=4)

        self.complex_frame = tk.Frame(self.container, padx=8)
        self.complex_frame.pack(fill="x")
        if not self.is_action:
            self._build_operand_fields(self.operand_var.get())
        else:
            self._build_filter_fields(self.filter_var.get())
    def _on_filter_change(self, _event=None):
        self._build_filter_fields(self.filter_var.get())
        if self.on_change:
            self.on_change()

    def _build_filter_fields(self, filter_var):
        self.children = []
        for w in self.complex_frame.winfo_children():
            w.destroy()
        if filter_var in ['attr>', 'attr<', 'attr=']:
            self.child_list_frame = tk.Frame(self.complex_frame)
            self.child_list_frame.pack(fill="x")

            btn_row = tk.Frame(self.complex_frame)
            btn_row.pack(fill="x")

            tk.Button(btn_row, text="+Add source", command=self._add_child).pack(side="left")
            tk.Button(btn_row, text="+Remove last", command=self._remove_child).pack(side="left")

            tk.Label(btn_row, text="attr:").pack(anchor="w")
            self.attr_var = tk.StringVar(value=ACCESS_OPTIONS[0])
            ttk.Combobox(
                btn_row, textvariable=self.attr_var,
                values=ACCESS_OPTIONS, state="readonly", width=12
            ).pack(anchor="w", padx=2, pady=2)
            tk.Label(btn_row, text="A:").pack(side="left")
            if filter_var in ['attr>', 'attr<']:
                self.a_var = tk.StringVar(value="0")
                tk.Spinbox(btn_row, from_=-20, to=20, width=4, textvariable=self.a_var).pack(side="left", padx=2)
            else:
                self.a_var = tk.StringVar(value=TYPES[0])
                ttk.Combobox(
                    btn_row, textvariable=self.a_var,
                    values=TYPES, state="readonly", width=12
                ).pack(anchor="w", padx=2, pady=2)

            self._add_child(become_action=True)


    def _on_operand_change(self, _event=None):
        self._build_operand_fields(self.operand_var.get())
        if self.on_change:
            self.on_change()

    def _build_operand_fields(self, operand):
        # Reset child references
        self.children = []
        self.child_a = None
        self.child_b = None
        self.child = None

        for w in self.complex_frame.winfo_children():
            w.destroy()

        if operand in ("and", "or"):
            self._build_and_or_fields()
        elif operand == "if":
            self._build_if_fields()
        elif operand == "access":
            self._build_access_fields()
        elif operand == "filter":
            tk.Label(self.complex_frame, text="actionFilter:").pack(side="left")
            self.child = TriggerSlotWidget(self.complex_frame, is_action=True, on_change=self.on_change)



    def _build_and_or_fields(self):
        self.child_list_frame = tk.Frame(self.complex_frame)
        self.child_list_frame.pack(fill="x")

        btn_row = tk.Frame(self.complex_frame)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="+ Add Trigger", command=self._add_child).pack(side="left")
        tk.Button(btn_row, text="- Remove Last", command=self._remove_child).pack(side="left", padx=4)

        # Start with one child
        self._add_child()

    def _add_child(self, become_action=False):
        if not self.is_action and self.operand_var.get() in ['and', 'or']:
            slot = TriggerSlotWidget(self.child_list_frame, is_pow=False, is_action=(self.is_action or become_action),
                                     on_change=self.on_change, reqBoolean=True)
        else:
            slot = TriggerSlotWidget(self.child_list_frame, is_pow=False, is_action=(self.is_action or become_action), on_change=self.on_change)
        self.children.append(slot)
        if self.on_change:
            self.on_change()

    def _remove_child(self):
        if self.children:
            removed = self.children.pop()
            removed.container.destroy()
            if self.on_change:
                self.on_change()

    def _build_if_fields(self):
        tk.Label(self.complex_frame, text="cmp:").pack(anchor="w")
        self.cmp_var = tk.StringVar(value=CMP_OPTIONS[0])
        ttk.Combobox(
            self.complex_frame, textvariable=self.cmp_var,
            values=CMP_OPTIONS, state="readonly", width=12
        ).pack(anchor="w", padx=2, pady=2)

        tk.Label(self.complex_frame, text="Left trigger:").pack(anchor="w")
        self.child_a = TriggerSlotWidget(self.complex_frame, is_pow=False, on_change=self.on_change)

        tk.Label(self.complex_frame, text="Right trigger:").pack(anchor="w")
        self.child_b = TriggerSlotWidget(self.complex_frame, is_pow=False, on_change=self.on_change)

    def _build_access_fields(self):
        tk.Label(self.complex_frame, text="Source trigger:").pack(anchor="w")
        self.child = TriggerSlotWidget(self.complex_frame, is_pow=False, on_change=self.on_change)

        tk.Label(self.complex_frame, text="access:").pack(anchor="w")
        self.access_var = tk.StringVar(value=ACCESS_OPTIONS[0])
        ttk.Combobox(
            self.complex_frame, textvariable=self.access_var,
            values=ACCESS_OPTIONS, state="readonly", width=10
        ).pack(anchor="w", padx=2, pady=2)

    def _collapse(self):
        # Reset child state before rebuilding simple
        self.children = []
        self.child_a = None
        self.child_b = None
        self.child = None
        self._build_simple()
        if self.on_change:
            self.on_change()

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------
    def get_value(self):
        if self.mode == "simple":
            if self.combo_var:
                chosen = self.combo_var.get()
                if self.is_pow and chosen == COMPLEX_SENTINEL:
                    # Use int spinbox value
                    try:
                        return int(self.pow_var.get())
                    except ValueError:
                        return 0
                if chosen == COMPLEX_SENTINEL:
                    return None  # incomplete
                return chosen
            elif self.is_action:
                return self.action_var.get()
        if self.is_action:
            if self.filter_var.get() in ['attr>', 'attr<', 'attr=']:
                action_values = [c.get_value() for c in self.children]
                return {"actions": action_values, "filter": {"type": self.filter_var.get(), "args":{"attr":self.attr_var.get(), "a":self.a_var.get()}}}
        # complex mode
        operand = self.operand_var.get()
        if operand in ("and", "or"):
            trigger_values = [c.get_value() for c in self.children]
            if any(v is None for v in trigger_values):
                return None
            return {"operand": operand, "triggers": trigger_values}

        if operand == "if":
            a = self.child_a.get_value() if self.child_a else None
            b = self.child_b.get_value() if self.child_b else None
            if a is None or b is None:
                return None
            return {"operand": "if", "cmp": self.cmp_var.get(), "triggers": [a, b]}

        if operand == "access":
            src = self.child.get_value() if self.child else None
            if src is None:
                return None
            return {"operand": "access", "triggers": [src], "access": self.access_var.get()}

        if operand == "filter":
            return {"operand": "filter", "actionData": self.child.get_value()} if self.child else None
        return None


# ---------------------------------------------------------------------------
# AbilityWidget
# ---------------------------------------------------------------------------
class AbilityWidget:
    def __init__(self, parent, remove_callback, on_change=None):
        self.on_change = on_change
        self.frame = tk.LabelFrame(parent, text="Ability", padx=6, pady=4)
        self.frame.pack(fill="x", pady=4, padx=4)

        # Trigger
        tk.Label(self.frame, text="Trigger:", font=("", 9, "bold")).pack(anchor="w")
        self.trigger_slot = TriggerSlotWidget(self.frame, is_pow=False, on_change=on_change, reqBoolean=True)

        # Effect
        eff_frame = tk.LabelFrame(self.frame, text="Effect", padx=4, pady=4)
        eff_frame.pack(fill="x", pady=4)

        row1 = tk.Frame(eff_frame)
        row1.pack(fill="x")
        tk.Label(row1, text="Targeting:").pack(side="left")
        self.target_slot = TriggerSlotWidget(row1, is_pow=False, is_action=True)

        tk.Label(row1, text="Action:").pack(side="left")
        self.action_var = tk.StringVar(value=EFFECT_ACTIONS[0])
        ttk.Combobox(
            row1, textvariable=self.action_var,
            values=EFFECT_ACTIONS, state="readonly", width=10
        ).pack(side="left", padx=4)

        tk.Label(eff_frame, text="Pow (int or complex):", font=("", 9, "bold")).pack(anchor="w")
        self.pow_slot = TriggerSlotWidget(eff_frame, is_pow=True, on_change=on_change)

        tk.Button(self.frame, text="Remove Ability", fg="red",
                  command=remove_callback).pack(anchor="e")

    def get_value(self):
        trigger = self.trigger_slot.get_value()
        pow_val = self.pow_slot.get_value()
        if trigger is None or pow_val is None:
            return None
        return {
            "trigger": trigger,
            "effect": {
                "targeting": self.target_slot.get_value(),
                "action": self.action_var.get(),
                "pow": pow_val,
            },
        }


# ---------------------------------------------------------------------------
# CardCreatorApp
# ---------------------------------------------------------------------------
class CardCreatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Card Creator")
        self.geometry("700x800")
        self.abilities: list[AbilityWidget] = []

        self._build_scrollable_body()
        self._build_basic_info()
        self._build_types()
        self._build_costs()
        self._build_abilities_section()
        self._build_save_button()

        # Bind mousewheel scrolling
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)

    # ------------------------------------------------------------------
    # Layout scaffolding
    # ------------------------------------------------------------------
    def _build_scrollable_body(self):
        outer = tk.Frame(self)
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer, highlightthickness=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vscroll.set)

        vscroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _refresh_scroll(self):
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # ------------------------------------------------------------------
    # Basic info section
    # ------------------------------------------------------------------
    def _build_basic_info(self):
        frame = tk.LabelFrame(self.inner, text="Basic Info", padx=8, pady=6)
        frame.pack(fill="x", padx=8, pady=6)

        row = tk.Frame(frame)
        row.pack(fill="x")

        tk.Label(row, text="ID:").pack(side="left")
        self.id_var = tk.StringVar(value="")
        tk.Entry(row, textvariable=self.id_var, width=6).pack(side="left", padx=4)

        tk.Label(row, text="Name:").pack(side="left")
        self.name_var = tk.StringVar(value="")
        tk.Entry(row, textvariable=self.name_var, width=20).pack(side="left", padx=4)

        tk.Label(row, text="ATK:").pack(side="left")
        self.atk_var = tk.StringVar(value="0")
        tk.Spinbox(row, from_=0, to=8, width=4, textvariable=self.atk_var).pack(side="left", padx=2)

        tk.Label(row, text="DEF:").pack(side="left")
        self.def_var = tk.StringVar(value="0")
        tk.Spinbox(row, from_=0, to=8, width=4, textvariable=self.def_var).pack(side="left", padx=2)

    # ------------------------------------------------------------------
    # Types section
    # ------------------------------------------------------------------
    def _build_types(self):
        frame = tk.LabelFrame(self.inner, text="Types (select 1–2)", padx=8, pady=6)
        frame.pack(fill="x", padx=8, pady=4)

        self.type_vars = {t: tk.BooleanVar() for t in TYPES}
        cols = 4
        for i, t in enumerate(TYPES):
            tk.Checkbutton(frame, text=t, variable=self.type_vars[t]).grid(
                row=i // cols, column=i % cols, sticky="w", padx=4
            )

    # ------------------------------------------------------------------
    # Costs section
    # ------------------------------------------------------------------
    def _build_costs(self):
        frame = tk.LabelFrame(self.inner, text="Costs", padx=8, pady=6)
        frame.pack(fill="x", padx=8, pady=4)

        row = tk.Frame(frame)
        row.pack(fill="x")

        tk.Label(row, text="Sac Cost:").pack(side="left")
        self.sac_var = tk.StringVar(value="0")
        tk.Spinbox(row, from_=0, to=5, width=4, textvariable=self.sac_var).pack(side="left", padx=2)

        tk.Label(row, text="Energy:").pack(side="left")
        self.energy_var = tk.StringVar(value="0")
        tk.Spinbox(row, from_=-5, to=7, width=4, textvariable=self.energy_var).pack(side="left", padx=2)

        tk.Label(row, text="Life:").pack(side="left")
        self.life_var = tk.StringVar(value="0")
        tk.Spinbox(row, from_=0, to=2, width=4, textvariable=self.life_var).pack(side="left", padx=2)

    # ------------------------------------------------------------------
    # Abilities section
    # ------------------------------------------------------------------
    def _build_abilities_section(self):
        self.abilities_outer = tk.LabelFrame(self.inner, text="Abilities", padx=8, pady=6)
        self.abilities_outer.pack(fill="x", padx=8, pady=4)

        self.abilities_frame = tk.Frame(self.abilities_outer)
        self.abilities_frame.pack(fill="x")

        tk.Button(
            self.abilities_outer, text="+ Add Ability", command=self._add_ability
        ).pack(anchor="w", pady=4)

    def _add_ability(self):
        idx = len(self.abilities)

        def remove(i=idx):
            self._remove_ability(i)

        widget = AbilityWidget(self.abilities_frame, remove_callback=remove, on_change=self._refresh_scroll)
        self.abilities.append(widget)
        self._refresh_scroll()

    def _remove_ability(self, idx):
        if idx < len(self.abilities):
            self.abilities[idx].frame.destroy()
            self.abilities.pop(idx)
            # Rebind remove callbacks so indices stay correct
            for i, ab in enumerate(self.abilities):
                btn = None
                for child in ab.frame.winfo_children():
                    if isinstance(child, tk.Button) and child.cget("text") == "Remove Ability":
                        btn = child
                        break
                if btn:
                    btn.configure(command=lambda i=i: self._remove_ability(i))
            self._refresh_scroll()

    # ------------------------------------------------------------------
    # Save button
    # ------------------------------------------------------------------
    def _build_save_button(self):
        tk.Button(
            self.inner, text="Save Card", bg="#4caf50", fg="white",
            font=("", 11, "bold"), padx=10, pady=6,
            command=self.save_card
        ).pack(pady=10)

    # ------------------------------------------------------------------
    # Build dict & validate
    # ------------------------------------------------------------------
    def build_card_dict(self):
        # id
        try:
            card_id = int(self.id_var.get())
            if card_id < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation", "ID must be a non-negative integer.")
            return None

        # name
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation", "Name must not be empty.")
            return None

        # types
        selected_types = [t for t, v in self.type_vars.items() if v.get()]
        if not (1 <= len(selected_types) <= 2):
            messagebox.showwarning("Validation", "Select 1 or 2 types.")
            return None

        # atk / def
        try:
            atk = int(self.atk_var.get())
            df = int(self.def_var.get())
        except ValueError:
            messagebox.showwarning("Validation", "ATK and DEF must be integers.")
            return None

        # costs
        try:
            sac = int(self.sac_var.get())
            energy = int(self.energy_var.get())
            life = int(self.life_var.get())
        except ValueError:
            messagebox.showwarning("Validation", "Cost fields must be integers.")
            return None

        # abilities
        abilities = []
        for i, ab in enumerate(self.abilities):
            val = ab.get_value()
            if val is None:
                messagebox.showwarning(
                    "Validation",
                    f"Ability {i + 1} has an incomplete trigger or pow field.\n"
                    "Finish filling in all complex nodes or collapse them."
                )
                return None
            abilities.append(val)

        return {
            "id": card_id,
            "name": name,
            "types": selected_types,
            "atk": atk,
            "def": df,
            "abilt": abilities,
            "costs": {"sacCost": sac, "energy": energy, "life": life},
        }

    # ------------------------------------------------------------------
    # Save card to JSON
    # ------------------------------------------------------------------
    def save_card(self):
        card = self.build_card_dict()
        if card is None:
            return

        try:
            with open(CARDS_PATH, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            messagebox.showerror("Error", f"Could not read cards.json:\n{e}")
            return

        cards = data.get("cards", [])
        target_id = card["id"]
        overwritten = False
        for i, c in enumerate(cards):
            if c.get("id") == target_id:
                cards[i] = card
                overwritten = True
                break
        if not overwritten:
            cards.append(card)

        data["cards"] = cards
        try:
            with open(CARDS_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            messagebox.showerror("Error", f"Could not write cards.json:\n{e}")
            return

        action = "Overwrote" if overwritten else "Appended"
        messagebox.showinfo("Saved", f"{action} card '{card['name']}' (id={target_id}).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = CardCreatorApp()
    app.mainloop()
