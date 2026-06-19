#!/usr/bin/env python3
"""
Persona 3 Reload – Save File JSON Editor
=========================================
Edits the *JSON* stage of save processing (after decrypt → gvas-to-json).
Feed it the .json file; it writes back a modified .json file.
Pass that back through your json-to-gvas → encrypt pipeline to get a
playable .sav.

Discovered structure (all indices are into the SaveDataArea_N flat array):

  HEADER  (SaveDataHeadder_0 dict)
    ├─ FirstName_0..5  – character bytes of first name
    ├─ LastName_0..3   – character bytes of last name
    ├─ PlayerLevel_0   – protagonist level shown on save screen
    ├─ Difficulty_0    – 0=Safety 1=Easy 2=Normal 3=Hard 4=Merciless
    ├─ Month_0, Day_0  – in-game calendar date
    ├─ TimeZone_0      – "ECldTimeZone::Shadow" when in Tartarus, etc.
    └─ FldMajorID_0, FldMinorID_0, FldPartsID_0 – field location IDs

  PERSISTENT PARTY BLOCKS  (9 members × 176 uint32s)
    Base = 13262, stride = 176
    ┌ +0  : 0x00CCID0001  (high word = char ID, low word = 0x0001)
    ├ +1  : Level
    ├ +2  : EXP
    ├ +3  : packed uint16-pair  (Stat-A lo | Stat-B hi)
    ├ +4  : packed uint16-pair  (Stat-C lo | Stat-D hi)
    ├ +5  : packed uint16-pair  (Stat-E lo | Stat-F hi)
    ├ +6  : packed uint16-pair  (Stat-G lo | MaxHP? hi)
    ├ +7  : 4 skill-IDs (one byte each, little-endian)
    └ +8  : 1 more skill-ID (low byte)

  MC ACTIVE PERSONA PALETTE  (up to 8 slots, 12 uint32s/slot)
    Base = 13086, stride = 12
    Same sub-structure as above (+0 PID header, +1 level, …, +7/+8 skills)

  ACTIVE BATTLE BLOCK  (offset from save area base = 13058)
    ├ +12 : Current HP
    ├ +13 : Current SP
    ├ +14 : Max HP (or related field)
    ├ +16 : Level (mirrors header PlayerLevel)
    └ +17 : EXP

  PERSONA COMPENDIUM  (sparse entries at ~7681+)
    Same 9-field sub-structure; variable gaps between slots (12–72 uint32s).
"""

import json
import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from copy import deepcopy
from pathlib import Path

# ─────────────────────────────── CONSTANTS ────────────────────────────────────

CHAR_IDS: dict[int, str] = {
    2:  "Makoto Yuki",
    4:  "Yukari Takeba",
    6:  "Junpei Iori",
    8:  "Akihiko Sanada",
    10: "Mitsuru Kirijo",
    12: "Fuuka Yamagishi",
    14: "Aigis",
    15: "Koromaru",
    16: "Ken Amada",
}

DIFFICULTIES: dict[int, str] = {
    0: "Safety",
    1: "Easy",
    2: "Normal",
    3: "Hard",
    4: "Merciless",
}

TIMEZONES: list[str] = [
    "ECldTimeZone::Shadow",
    "ECldTimeZone::Daytime",
    "ECldTimeZone::AfterSchool",
    "ECldTimeZone::Evening",
    "ECldTimeZone::Night",
    "ECldTimeZone::LateNight",
]

# Persistent party blocks
PARTY_BLOCK_BASE   = 13262
PARTY_BLOCK_STRIDE = 176

# MC active persona palette (slots inside the save area)
MC_PERSONA_BASE    = 13086
MC_PERSONA_STRIDE  = 12
MC_PERSONA_SLOTS   = 8

# Active battle state block base
BATTLE_BASE = 13058
BATTLE_OFF_CUR_HP  = 12
BATTLE_OFF_CUR_SP  = 13
BATTLE_OFF_MAX_HP  = 14
BATTLE_OFF_LEVEL   = 16
BATTLE_OFF_EXP     = 17

# Stat labels for packed uint16-pairs at offsets +3 through +6
STAT_LABELS = [
    "STR (base?)", "STR (bonus?)",
    "MAG (base?)", "MAG (bonus?)",
    "END (base?)", "END (bonus?)",
    "LUK / AGI",   "Max HP",
]

# ─── Boss location presets ─────────────────────────────────────────────────────
# Format: (FldMajorID, FldMinorID, FldPartsID, TimeZone)
# Fill in the correct IDs once confirmed from game data / community wiki.
# Entries marked with ??? need verification.
BOSS_PRESETS: dict[str, tuple | None] = {
    "── Custom (enter IDs manually) ──":  None,
    "Tartarus – Current area (save014)": (299, 263, 263, "ECldTimeZone::Shadow"),
    "Gekkoukan – After School (save015)": (103, 101, 3,   "ECldTimeZone::AfterSchool"),
    # ── Tartarus Full-Moon bosses (floor IDs are approximate – verify!) ──────
    "Tartarus Block 1 Boss (Arcana Lovers)":    (10, 17,  17,  "ECldTimeZone::Shadow"),
    "Tartarus Block 2 Boss (Arcana Emperor/Empress)": (10, 55, 55, "ECldTimeZone::Shadow"),
    "Tartarus Block 3 Boss (Arcana Hierophant/Lovers)": (10, 90, 90, "ECldTimeZone::Shadow"),
    "Tartarus Block 4 Boss (Arcana Hermit)":    (10, 122, 122, "ECldTimeZone::Shadow"),
    "Tartarus Block 5 Boss (Arcana Fortune/Strength)": (10, 152, 152, "ECldTimeZone::Shadow"),
    "Tartarus Block 6 Boss (Arcana Moon)":      (10, 199, 199, "ECldTimeZone::Shadow"),
    "Tartarus Top Floor (Nyx Avatar)":          (10, 254, 254, "ECldTimeZone::Shadow"),
}

# ─── P3R Persona names (IDs 1–206) ────────────────────────────────────────────
# Source: in-game compendium ordering. Expand as needed.
PERSONA_NAMES: dict[int, str] = {
    1: "Orpheus", 2: "Orpheus (F)", 3: "Thanatos",
    4: "Io", 5: "Apsaras", 6: "Hua Po",
    7: "Jack-o'-Lantern", 8: "Jack Frost", 9: "Pyro Jack",
    10: "Ghoul", 11: "Slime", 12: "Forneus",
    13: "Orobas", 14: "Eligor", 15: "Nata Taishi",
    16: "Surt", 17: "Fuu-Ki", 18: "Kin-Ki",
    19: "Sui-Ki", 20: "Oni", 21: "Rakshasa",
    22: "Valkyrie", 23: "Alilat", 24: "Unicorn",
    25: "High Pixie", 26: "Ara Mitama", 27: "Nigi Mitama",
    28: "Saki Mitama", 29: "Kushi Mitama", 30: "Pixie",
    31: "Dis", 32: "Leanan Sidhe", 33: "Lamia",
    34: "Empusa", 35: "Narcissus", 36: "Sylph",
    37: "Oberon", 38: "Titania", 39: "Undine",
    40: "Setanta", 41: "Cu Chulainn", 42: "Gdon",
    43: "Berith", 44: "Eligor", 45: "Decarabia",
    46: "Vetala", 47: "Choronzon", 48: "Nue",
    49: "Mothman", 50: "Taraka", 51: "Queen Mab",
    52: "Sudama", 53: "Shiisaa", 54: "Inugami",
    55: "Kaiwan", 56: "Nekomata", 57: "Dominion",
    58: "Archangel", 59: "Angel", 60: "Power",
    61: "Principality", 62: "Virtue", 63: "Uriel",
    64: "Raphael", 65: "Gabriel", 66: "Michael",
    67: "Metatron", 68: "Ganesha", 69: "Nandi",
    70: "Soma", 71: "Garuda", 72: "Barong",
    73: "Rangda", 74: "Throne", 75: "Cherub",
    76: "Seraph", 77: "Mara", 78: "Incubus",
    79: "Lilim", 80: "Succubus", 81: "Alp",
    82: "Black Frost", 83: "Pale Rider", 84: "Matador",
    85: "Demi-Urge", 86: "Loa", 87: "Mot",
    88: "Legion", 89: "Belzaboul", 90: "Abaddon",
    91: "Nebiros", 92: "Beelzebub", 93: "Attis",
    94: "Demeter", 95: "Persephone", 96: "Lachesis",
    97: "Clotho", 98: "Atropos", 99: "Mot",
    100: "Nyx", 101: "Erebus",
    # Party members use IDs 2-16 (even + 15)
    # Compendium personas are 35+ for the ones I've confirmed
}

# ─── Skill names (IDs 0–255) – partial listing, expand from game data ──────────
SKILL_NAMES: dict[int, str] = {
    0:  "(none)", 1:  "Slash Attack", 2:  "Strike Attack", 3:  "Pierce Attack",
    4:  "Agi", 5:  "Bufu", 6:  "Zio", 7:  "Garu",
    8:  "Marin Karin", 9:  "Tarunda", 10: "Rakunda", 11: "Sukunda",
    12: "Tarukaja", 13: "Rakukaja", 14: "Sukukaja", 15: "Sukukaja",
    16: "Media", 17: "Diarama", 18: "Dia", 19: "Recarm",
    20: "Samarecarm", 21: "Mediarama", 22: "Mediarahan", 23: "Full Analysis",
    24: "Agilao", 25: "Bufula", 26: "Zionga", 27: "Garula",
    28: "Agidyne", 29: "Bufudyne", 30: "Ziodyne", 31: "Garudyne",
    32: "Maagi", 33: "Mabufu", 34: "Mazio", 35: "Magaru",
    36: "Maragion", 37: "Mabufula", 38: "Mazionga", 39: "Magarula",
    40: "Maragidyne", 41: "Mabufudyne", 42: "Maziodyne", 43: "Magarudyne",
    44: "Blade of Fury", 45: "Tempest Slash", 46: "Vorpal Blade", 47: "Brave Blade",
    48: "Rampage", 49: "Assault Dive", 50: "Primal Force", 51: "God's Hand",
    52: "Gigantic Fist", 53: "Meteor Shower", 54: "Agneyastra", 55: "Myriad Arrows",
    56: "Thunder Reign", 57: "Panta Rhei", 58: "Inferno", 59: "Blizzard Edge",
    60: "Tentarafoo", 61: "Lullaby", 62: "Pulinpa", 63: "Foul Breath",
    64: "Stagnant Air", 65: "Bad Breath", 66: "Mudo", 67: "Mudoon",
    68: "Mamudo", 69: "Mamudoon", 70: "Hama", 71: "Hamaon",
    72: "Mahama", 73: "Mahamaon", 74: "Megidola", 75: "Megidolaon",
    76: "Heat Riser", 77: "Debilitate", 78: "Matarukaja", 79: "Matarunda",
    80: "Marakukaja", 81: "Marakunda", 82: "Masukukaja", 83: "Masukunda",
    84: "Fire Boost", 85: "Ice Boost", 86: "Elec Boost", 87: "Wind Boost",
    88: "Fire Break", 89: "Ice Break", 90: "Elec Break", 91: "Wind Break",
    92: "Repel Fire", 93: "Repel Ice", 94: "Repel Elec", 95: "Repel Wind",
    96: "Null Fire", 97: "Null Ice", 98: "Null Elec", 99: "Null Wind",
    100: "Drain Fire", 101: "Drain Ice", 102: "Drain Elec", 103: "Drain Wind",
    # Extend as game data is discovered
}


def skill_name(sid: int) -> str:
    return SKILL_NAMES.get(sid, f"Skill#{sid}")


def persona_name(pid: int) -> str:
    return PERSONA_NAMES.get(pid, f"Persona#{pid}")


# ─────────────────────────────── DATA MODEL ────────────────────────────────────

class SaveFile:
    """Loads, queries, and patches a P3R JSON save file."""

    def __init__(self) -> None:
        self._raw: dict = {}
        self._area: dict[int, int] = {}   # index → uint32 value
        self.path: Path | None = None
        self.modified = False

    # ── I/O ──────────────────────────────────────────────────────────────────

    def load(self, path: str | Path) -> None:
        self.path = Path(path)
        with open(self.path, encoding="utf-8") as fh:
            self._raw = json.load(fh)
        self._build_area_index()
        self.modified = False

    def save(self, path: str | Path | None = None) -> None:
        dest = Path(path) if path else self.path
        if dest is None:
            raise ValueError("No path specified")
        self._flush_area_index()
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(self._raw, fh, indent=2, ensure_ascii=False)
        self.path = dest
        self.modified = False

    def _build_area_index(self) -> None:
        self._area.clear()
        for key, val in self._raw["root"]["properties"].items():
            if key.startswith("SaveDataArea_"):
                self._area[int(key[13:])] = int(val)

    def _flush_area_index(self) -> None:
        props = self._raw["root"]["properties"]
        for idx, val in self._area.items():
            props[f"SaveDataArea_{idx}"] = val

    # ── Low-level area helpers ────────────────────────────────────────────────

    def get(self, idx: int, default: int = 0) -> int:
        return self._area.get(idx, default)

    def set(self, idx: int, val: int) -> None:
        clamped = int(val) & 0xFFFF_FFFF
        self._area[idx] = clamped
        self._raw["root"]["properties"][f"SaveDataArea_{idx}"] = clamped
        self.modified = True

    def remove(self, idx: int) -> None:
        self._area.pop(idx, None)
        self._raw["root"]["properties"].pop(f"SaveDataArea_{idx}", None)
        self.modified = True

    def get_u16_pair(self, idx: int) -> tuple[int, int]:
        v = self.get(idx)
        return (v & 0xFFFF, v >> 16)

    def set_u16_pair(self, idx: int, lo: int, hi: int) -> None:
        self.set(idx, (int(hi) << 16) | (int(lo) & 0xFFFF))

    def get_bytes4(self, idx: int) -> list[int]:
        v = self.get(idx)
        return list(v.to_bytes(4, "little"))

    def set_bytes4(self, idx: int, b: list[int]) -> None:
        self.set(idx, int.from_bytes(bytes(b[:4]), "little"))

    # ── Header ────────────────────────────────────────────────────────────────

    @property
    def _hdr(self) -> dict:
        return self._raw["root"]["properties"]["SaveDataHeadder_0"]

    def get_first_name(self) -> str:
        return "".join(
            chr(self._hdr.get(f"FirstName_{i}", 0))
            for i in range(6)
            if self._hdr.get(f"FirstName_{i}", 0) != 0
        )

    def set_first_name(self, name: str) -> None:
        name = name[:6]
        for i in range(6):
            key = f"FirstName_{i}"
            if i < len(name):
                self._hdr[key] = ord(name[i])
            else:
                self._hdr[key] = 0
        self.modified = True

    def get_last_name(self) -> str:
        return "".join(
            chr(self._hdr.get(f"LastName_{i}", 0))
            for i in range(4)
            if self._hdr.get(f"LastName_{i}", 0) != 0
        )

    def set_last_name(self, name: str) -> None:
        name = name[:4]
        for i in range(4):
            key = f"LastName_{i}"
            if i < len(name):
                self._hdr[key] = ord(name[i])
            else:
                self._hdr[key] = 0
        self.modified = True

    def get_header_int(self, key: str) -> int:
        return int(self._hdr.get(key, 0))

    def set_header_int(self, key: str, val: int) -> None:
        self._hdr[key] = int(val)
        self.modified = True

    def get_header_str(self, key: str) -> str:
        return str(self._hdr.get(key, ""))

    def set_header_str(self, key: str, val: str) -> None:
        self._hdr[key] = val
        self.modified = True

    # ── Persistent party blocks ───────────────────────────────────────────────

    def _party_base(self, slot: int) -> int:
        return PARTY_BLOCK_BASE + slot * PARTY_BLOCK_STRIDE

    def get_party_char_id(self, slot: int) -> int:
        return self.get(self._party_base(slot)) >> 16

    def get_party_level(self, slot: int) -> int:
        return self.get(self._party_base(slot) + 1)

    def set_party_level(self, slot: int, val: int) -> None:
        self.set(self._party_base(slot) + 1, val)

    def get_party_exp(self, slot: int) -> int:
        return self.get(self._party_base(slot) + 2)

    def set_party_exp(self, slot: int, val: int) -> None:
        self.set(self._party_base(slot) + 2, val)

    def get_party_stats(self, slot: int) -> list[int]:
        """Return 8 uint16 stat values (pairs at offsets +3 to +6)."""
        b = self._party_base(slot)
        result = []
        for off in range(3, 7):
            lo, hi = self.get_u16_pair(b + off)
            result.extend([lo, hi])
        return result

    def set_party_stats(self, slot: int, stats: list[int]) -> None:
        b = self._party_base(slot)
        for i, off in enumerate(range(3, 7)):
            lo = stats[i * 2]
            hi = stats[i * 2 + 1]
            self.set_u16_pair(b + off, lo, hi)

    def get_party_skills(self, slot: int) -> list[int]:
        b = self._party_base(slot)
        s = self.get_bytes4(b + 7)           # 4 skill bytes
        s.append(self.get_bytes4(b + 8)[0])  # 1 more
        return s

    def set_party_skills(self, slot: int, skills: list[int]) -> None:
        b = self._party_base(slot)
        s5 = (skills + [0] * 5)[:5]
        self.set_bytes4(b + 7, s5[:4])
        cur8 = self.get_bytes4(b + 8)
        cur8[0] = s5[4]
        self.set_bytes4(b + 8, cur8)

    # ── MC active persona palette ─────────────────────────────────────────────

    def _persona_base(self, slot: int) -> int:
        return MC_PERSONA_BASE + slot * MC_PERSONA_STRIDE

    def get_persona_id(self, slot: int) -> int:
        return self.get(self._persona_base(slot)) >> 16

    def set_persona_id(self, slot: int, pid: int) -> None:
        b = self._persona_base(slot)
        flag = self.get(b) & 0xFFFF
        self.set(b, (pid << 16) | flag)

    def get_persona_level(self, slot: int) -> int:
        return self.get(self._persona_base(slot) + 1)

    def set_persona_level(self, slot: int, val: int) -> None:
        self.set(self._persona_base(slot) + 1, val)

    def get_persona_exp(self, slot: int) -> int:
        return self.get(self._persona_base(slot) + 2)

    def set_persona_exp(self, slot: int, val: int) -> None:
        self.set(self._persona_base(slot) + 2, val)

    def get_persona_stats(self, slot: int) -> list[int]:
        b = self._persona_base(slot)
        result = []
        for off in range(3, 7):
            lo, hi = self.get_u16_pair(b + off)
            result.extend([lo, hi])
        return result

    def set_persona_stats(self, slot: int, stats: list[int]) -> None:
        b = self._persona_base(slot)
        for i, off in enumerate(range(3, 7)):
            self.set_u16_pair(b + off, stats[i * 2], stats[i * 2 + 1])

    def get_persona_skills(self, slot: int) -> list[int]:
        b = self._persona_base(slot)
        s = self.get_bytes4(b + 7)
        s.append(self.get_bytes4(b + 8)[0])
        return s

    def set_persona_skills(self, slot: int, skills: list[int]) -> None:
        b = self._persona_base(slot)
        s5 = (skills + [0] * 5)[:5]
        self.set_bytes4(b + 7, s5[:4])
        cur8 = self.get_bytes4(b + 8)
        cur8[0] = s5[4]
        self.set_bytes4(b + 8, cur8)

    # ── Active battle state ───────────────────────────────────────────────────

    def get_battle_hp(self)  -> int: return self.get(BATTLE_BASE + BATTLE_OFF_CUR_HP)
    def set_battle_hp(self, v: int) -> None: self.set(BATTLE_BASE + BATTLE_OFF_CUR_HP, v)

    def get_battle_sp(self)  -> int: return self.get(BATTLE_BASE + BATTLE_OFF_CUR_SP)
    def set_battle_sp(self, v: int) -> None: self.set(BATTLE_BASE + BATTLE_OFF_CUR_SP, v)

    def get_battle_maxhp(self) -> int: return self.get(BATTLE_BASE + BATTLE_OFF_MAX_HP)
    def set_battle_maxhp(self, v: int) -> None: self.set(BATTLE_BASE + BATTLE_OFF_MAX_HP, v)

    # ── Persona compendium (sparse scan) ─────────────────────────────────────

    def scan_compendium(self) -> list[dict]:
        """
        Scan the save area for all entries that look like persona records
        (uint32 whose low 16 bits == 1 and high 16 bits are a plausible
        persona ID 1–255, followed by a level in 1–99).
        Returns list sorted by index.
        """
        entries = []
        for idx in sorted(self._area):
            v    = self._area[idx]
            flag = v & 0xFFFF
            pid  = v >> 16
            nxt  = self._area.get(idx + 1, 0)
            if flag == 1 and 1 <= pid <= 255 and 1 <= nxt <= 99:
                entries.append({
                    "idx":   idx,
                    "pid":   pid,
                    "level": nxt,
                    "exp":   self._area.get(idx + 2, 0),
                })
        return entries


# ─────────────────────────────── GUI HELPERS ───────────────────────────────────

PAD = {"padx": 6, "pady": 4}


def int_var_entry(parent, width=8):
    v = tk.StringVar()
    e = ttk.Entry(parent, textvariable=v, width=width)
    return v, e


def labeled_entry(parent, label: str, row: int, col: int = 0,
                  width: int = 10, **grid_kw) -> tuple[tk.StringVar, ttk.Entry]:
    ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", **PAD)
    var = tk.StringVar()
    ent = ttk.Entry(parent, textvariable=var, width=width)
    ent.grid(row=row, column=col + 1, sticky="ew", **PAD, **grid_kw)
    return var, ent


def safe_int(s: str, fallback: int = 0, lo: int = 0, hi: int = 0xFFFF_FFFF) -> int:
    try:
        v = int(str(s).strip(), 0)
        return max(lo, min(hi, v))
    except ValueError:
        return fallback


# ─────────────────────────────── MAIN APP ─────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Persona 3 Reload – Save Editor")
        self.resizable(True, True)
        self.geometry("900x700")
        self.sf = SaveFile()
        self._build_menu()
        self._build_ui()
        self._set_enabled(False)

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = tk.Menu(self)
        fm = tk.Menu(mb, tearoff=False)
        fm.add_command(label="Open JSON…",    command=self.open_file, accelerator="Ctrl+O")
        fm.add_command(label="Save JSON",     command=self.save_file, accelerator="Ctrl+S")
        fm.add_command(label="Save JSON As…", command=self.save_as)
        fm.add_separator()
        fm.add_command(label="Quit", command=self.quit)
        mb.add_cascade(label="File", menu=fm)
        self.config(menu=mb)
        self.bind("<Control-o>", lambda _: self.open_file())
        self.bind("<Control-s>", lambda _: self.save_file())

    # ── Top-level layout ──────────────────────────────────────────────────────

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=4)
        self._lbl_file = ttk.Label(top, text="No file loaded", foreground="gray")
        self._lbl_file.pack(side="left")
        self._btn_save = ttk.Button(top, text="💾 Save", command=self.save_file)
        self._btn_save.pack(side="right")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        self._tab_header  = ttk.Frame(nb)
        self._tab_party   = ttk.Frame(nb)
        self._tab_persona = ttk.Frame(nb)
        self._tab_comp    = ttk.Frame(nb)
        self._tab_battle  = ttk.Frame(nb)

        nb.add(self._tab_header,  text="📋 Header / Location")
        nb.add(self._tab_party,   text="👥 Party Members")
        nb.add(self._tab_persona, text="🎭 MC Persona Palette")
        nb.add(self._tab_battle,  text="⚔️ Battle State")
        nb.add(self._tab_comp,    text="📖 Compendium (read)")

        self._build_header_tab()
        self._build_party_tab()
        self._build_persona_tab()
        self._build_battle_tab()
        self._build_comp_tab()

    # ── Header tab ────────────────────────────────────────────────────────────

    def _build_header_tab(self):
        f = ttk.LabelFrame(self._tab_header, text="Player Info")
        f.pack(fill="x", padx=10, pady=6)
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=1)

        self._hdr_first, _ = labeled_entry(f, "First Name:", 0, 0, width=12)
        self._hdr_last,  _ = labeled_entry(f, "Last Name:",  0, 2, width=12)
        self._hdr_level, _ = labeled_entry(f, "Level (header):", 1, 0, width=6)
        self._hdr_diff,  _ = labeled_entry(f, "Difficulty (0–4):", 1, 2, width=6)
        self._hdr_month, _ = labeled_entry(f, "Month:", 2, 0, width=4)
        self._hdr_day,   _ = labeled_entry(f, "Day:",   2, 2, width=4)

        ttk.Label(f, text="Difficulty codes: 0=Safety 1=Easy 2=Normal 3=Hard 4=Merciless",
                  foreground="gray").grid(row=3, column=0, columnspan=4, sticky="w", padx=6)

        f2 = ttk.LabelFrame(self._tab_header, text="Location / Boss Selector")
        f2.pack(fill="x", padx=10, pady=6)
        f2.columnconfigure(1, weight=1)

        ttk.Label(f2, text="Boss Preset:").grid(row=0, column=0, sticky="w", **PAD)
        self._boss_var = tk.StringVar()
        self._boss_cb  = ttk.Combobox(f2, textvariable=self._boss_var,
                                       values=list(BOSS_PRESETS.keys()),
                                       state="readonly", width=55)
        self._boss_cb.grid(row=0, column=1, columnspan=3, sticky="ew", **PAD)
        self._boss_cb.bind("<<ComboboxSelected>>", self._on_boss_preset)
        self._boss_cb.set(list(BOSS_PRESETS.keys())[0])

        self._hdr_fmaj, _ = labeled_entry(f2, "FldMajorID:", 1, 0, width=8)
        self._hdr_fmin, _ = labeled_entry(f2, "FldMinorID:", 1, 2, width=8)
        self._hdr_fpar, _ = labeled_entry(f2, "FldPartsID:", 2, 0, width=8)

        ttk.Label(f2, text="TimeZone:").grid(row=2, column=2, sticky="w", **PAD)
        self._hdr_tz = tk.StringVar()
        ttk.Combobox(f2, textvariable=self._hdr_tz, values=TIMEZONES, width=35
                     ).grid(row=2, column=3, sticky="ew", **PAD)

        note = ("Note: FldMajorID/MinorID/PartsID control where the game loads you.\n"
                "Boss arena IDs marked with ??? need confirmation from community wiki.")
        ttk.Label(f2, text=note, foreground="gray", wraplength=600, justify="left"
                  ).grid(row=3, column=0, columnspan=4, sticky="w", padx=6, pady=2)

        ttk.Button(self._tab_header, text="✅  Apply Header Changes",
                   command=self._apply_header).pack(pady=8)

    def _on_boss_preset(self, _=None):
        key = self._boss_var.get()
        v = BOSS_PRESETS.get(key)
        if v:
            maj, mn, par, tz = v
            self._hdr_fmaj.set(str(maj))
            self._hdr_fmin.set(str(mn))
            self._hdr_fpar.set(str(par))
            self._hdr_tz.set(tz)

    def _apply_header(self):
        sf = self.sf
        sf.set_first_name(self._hdr_first.get().strip())
        sf.set_last_name(self._hdr_last.get().strip())
        sf.set_header_int("PlayerLevel_0", safe_int(self._hdr_level.get(), 1, 1, 99))
        sf.set_header_int("Difficulty_0",  safe_int(self._hdr_diff.get(),  2, 0,  4))
        sf.set_header_int("Month_0",       safe_int(self._hdr_month.get(), 1, 1, 12))
        sf.set_header_int("Day_0",         safe_int(self._hdr_day.get(),   1, 1, 31))
        sf.set_header_int("FldMajorID_0",  safe_int(self._hdr_fmaj.get()))
        sf.set_header_int("FldMinorID_0",  safe_int(self._hdr_fmin.get()))
        sf.set_header_int("FldPartsID_0",  safe_int(self._hdr_fpar.get()))
        sf.set_header_str("TimeZone_0",    self._hdr_tz.get())
        messagebox.showinfo("Applied", "Header changes applied (not yet saved to disk).")

    # ── Party tab ─────────────────────────────────────────────────────────────

    def _build_party_tab(self):
        canvas = tk.Canvas(self._tab_party)
        vsb = ttk.Scrollbar(self._tab_party, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._party_widgets: list[dict] = []  # one dict per slot

        for slot in range(9):
            char_id = list(CHAR_IDS.keys())[slot]
            name = CHAR_IDS[char_id]
            lf = ttk.LabelFrame(inner, text=f"Slot {slot}  –  {name}  (CharID={char_id})")
            lf.pack(fill="x", padx=8, pady=4)
            lf.columnconfigure(1, weight=1)
            lf.columnconfigure(3, weight=1)
            lf.columnconfigure(5, weight=1)

            lvl_var = tk.StringVar()
            exp_var = tk.StringVar()
            ttk.Label(lf, text="Level:").grid(row=0, column=0, sticky="w", **PAD)
            ttk.Entry(lf, textvariable=lvl_var, width=6).grid(row=0, column=1, sticky="w", **PAD)
            ttk.Label(lf, text="EXP:").grid(row=0, column=2, sticky="w", **PAD)
            ttk.Entry(lf, textvariable=exp_var, width=10).grid(row=0, column=3, sticky="w", **PAD)

            stat_vars: list[tk.StringVar] = []
            for si, lbl in enumerate(STAT_LABELS):
                r = 1 + si // 4
                c = (si % 4) * 2
                ttk.Label(lf, text=f"{lbl}:").grid(row=r, column=c, sticky="w", padx=4)
                sv = tk.StringVar()
                ttk.Entry(lf, textvariable=sv, width=6).grid(row=r, column=c + 1, sticky="w", padx=2)
                stat_vars.append(sv)

            skill_vars: list[tk.StringVar] = []
            skill_frame = ttk.Frame(lf)
            skill_frame.grid(row=4, column=0, columnspan=6, sticky="ew", pady=2)
            ttk.Label(skill_frame, text="Skills (IDs):").pack(side="left", padx=4)
            for _ in range(5):
                sv = tk.StringVar()
                ttk.Entry(skill_frame, textvariable=sv, width=5).pack(side="left", padx=2)
                skill_vars.append(sv)
            skill_names_lbl = ttk.Label(skill_frame, text="", foreground="#555")
            skill_names_lbl.pack(side="left", padx=8)

            # wire skill name preview
            def _make_preview(svars, lbl_widget):
                def upd(*_):
                    parts = []
                    for sv in svars:
                        try:
                            sid = int(sv.get())
                            parts.append(skill_name(sid))
                        except ValueError:
                            pass
                    lbl_widget.config(text="  |  ".join(parts))
                for sv in svars:
                    sv.trace_add("write", upd)
            _make_preview(skill_vars, skill_names_lbl)

            apply_btn = ttk.Button(lf, text="Apply",
                                   command=lambda s=slot, lv=lvl_var, ev=exp_var,
                                   stv=stat_vars, skv=skill_vars:
                                   self._apply_party_slot(s, lv, ev, stv, skv))
            apply_btn.grid(row=5, column=0, columnspan=6, pady=4)

            self._party_widgets.append({
                "level": lvl_var, "exp": exp_var,
                "stats": stat_vars, "skills": skill_vars,
            })

    def _apply_party_slot(self, slot, lv_var, ev_var, stat_vars, skill_vars):
        sf = self.sf
        sf.set_party_level(slot, safe_int(lv_var.get(), 1, 1, 99))
        sf.set_party_exp(slot, safe_int(ev_var.get(), 0, 0))
        stats = [safe_int(sv.get(), 0, 0, 0xFFFF) for sv in stat_vars]
        sf.set_party_stats(slot, stats)
        skills = [safe_int(sv.get(), 0, 0, 255) for sv in skill_vars]
        sf.set_party_skills(slot, skills)
        messagebox.showinfo("Applied", f"Slot {slot} changes applied.")

    # ── Persona palette tab ───────────────────────────────────────────────────

    def _build_persona_tab(self):
        canvas = tk.Canvas(self._tab_persona)
        vsb = ttk.Scrollbar(self._tab_persona, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        ttk.Label(inner,
                  text=("MC can carry up to 8 personas simultaneously.\n"
                        "Each slot shows the Persona ID (1–255) and its attributes.\n"
                        "Slot 0 is the currently equipped persona."),
                  foreground="gray", justify="left").pack(anchor="w", padx=10, pady=4)

        self._persona_widgets: list[dict] = []

        for slot in range(MC_PERSONA_SLOTS):
            lf = ttk.LabelFrame(inner, text=f"Palette Slot {slot}")
            lf.pack(fill="x", padx=8, pady=3)
            lf.columnconfigure(1, weight=1)
            lf.columnconfigure(3, weight=1)
            lf.columnconfigure(5, weight=1)

            pid_var = tk.StringVar()
            lvl_var = tk.StringVar()
            exp_var = tk.StringVar()
            pid_name_lbl = ttk.Label(lf, text="", foreground="#336699")

            ttk.Label(lf, text="Persona ID:").grid(row=0, column=0, sticky="w", **PAD)
            ttk.Entry(lf, textvariable=pid_var, width=6).grid(row=0, column=1, sticky="w", **PAD)
            pid_name_lbl.grid(row=0, column=2, sticky="w", padx=4)

            def _pid_preview(pv=pid_var, lbl=pid_name_lbl):
                def upd(*_):
                    try:
                        lbl.config(text=persona_name(int(pv.get())))
                    except ValueError:
                        lbl.config(text="")
                pv.trace_add("write", upd)
            _pid_preview()

            ttk.Label(lf, text="Level:").grid(row=0, column=3, sticky="w", **PAD)
            ttk.Entry(lf, textvariable=lvl_var, width=6).grid(row=0, column=4, sticky="w", **PAD)
            ttk.Label(lf, text="EXP:").grid(row=0, column=5, sticky="w", **PAD)
            ttk.Entry(lf, textvariable=exp_var, width=10).grid(row=0, column=6, sticky="w", **PAD)

            stat_vars: list[tk.StringVar] = []
            for si, lbl in enumerate(STAT_LABELS):
                r = 1 + si // 4
                c = (si % 4) * 2
                ttk.Label(lf, text=f"{lbl}:").grid(row=r, column=c, sticky="w", padx=4)
                sv = tk.StringVar()
                ttk.Entry(lf, textvariable=sv, width=6).grid(row=r, column=c + 1, sticky="w", padx=2)
                stat_vars.append(sv)

            skill_vars: list[tk.StringVar] = []
            sf_row = ttk.Frame(lf)
            sf_row.grid(row=4, column=0, columnspan=8, sticky="ew", pady=2)
            ttk.Label(sf_row, text="Skills (IDs):").pack(side="left", padx=4)
            for _ in range(5):
                sv = tk.StringVar()
                ttk.Entry(sf_row, textvariable=sv, width=5).pack(side="left", padx=2)
                skill_vars.append(sv)
            sk_name_lbl = ttk.Label(sf_row, text="", foreground="#555")
            sk_name_lbl.pack(side="left", padx=8)

            def _sk_preview(svars=skill_vars, lbl=sk_name_lbl):
                def upd(*_):
                    parts = []
                    for sv in svars:
                        try:
                            parts.append(skill_name(int(sv.get())))
                        except ValueError:
                            pass
                    lbl.config(text="  |  ".join(parts))
                for sv in svars:
                    sv.trace_add("write", upd)
            _sk_preview()

            apply_btn = ttk.Button(lf, text="Apply",
                                   command=lambda s=slot, pv=pid_var, lv=lvl_var,
                                   ev=exp_var, stv=stat_vars, skv=skill_vars:
                                   self._apply_persona_slot(s, pv, lv, ev, stv, skv))
            apply_btn.grid(row=5, column=0, columnspan=8, pady=4)

            self._persona_widgets.append({
                "pid": pid_var, "level": lvl_var, "exp": exp_var,
                "stats": stat_vars, "skills": skill_vars,
            })

    def _apply_persona_slot(self, slot, pid_var, lv_var, ev_var, stat_vars, skill_vars):
        sf = self.sf
        sf.set_persona_id(slot,    safe_int(pid_var.get(), 0, 0, 255))
        sf.set_persona_level(slot, safe_int(lv_var.get(), 1, 1, 99))
        sf.set_persona_exp(slot,   safe_int(ev_var.get(), 0, 0))
        stats  = [safe_int(sv.get(), 0, 0, 0xFFFF) for sv in stat_vars]
        sf.set_persona_stats(slot, stats)
        skills = [safe_int(sv.get(), 0, 0, 255) for sv in skill_vars]
        sf.set_persona_skills(slot, skills)
        messagebox.showinfo("Applied", f"Persona slot {slot} changes applied.")

    # ── Battle state tab ──────────────────────────────────────────────────────

    def _build_battle_tab(self):
        f = ttk.LabelFrame(self._tab_battle,
                           text="Active Battle State (current HP / SP – affects next loaded battle)")
        f.pack(fill="x", padx=10, pady=10)
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=1)

        self._bat_hp, _ = labeled_entry(f, "Current HP:", 0, 0, width=8)
        self._bat_sp, _ = labeled_entry(f, "Current SP:", 0, 2, width=8)
        self._bat_mhp, _ = labeled_entry(f, "Max HP field:", 1, 0, width=8)

        ttk.Label(f, text=(
            "These values live in the 'active party snapshot' inside the save.\n"
            "Setting HP = Max HP ensures you enter combat at full health."
        ), foreground="gray", wraplength=600).grid(
            row=2, column=0, columnspan=4, sticky="w", padx=6, pady=2)

        ttk.Button(f, text="Set HP/SP to Max (999 / 999)",
                   command=self._max_hpsp).grid(row=3, column=0, columnspan=2, pady=4)
        ttk.Button(f, text="Apply Changes",
                   command=self._apply_battle).grid(row=3, column=2, columnspan=2, pady=4)

    def _max_hpsp(self):
        self._bat_hp.set("999")
        self._bat_sp.set("999")
        self._bat_mhp.set("999")

    def _apply_battle(self):
        sf = self.sf
        sf.set_battle_hp(safe_int(self._bat_hp.get(),  999, 0, 9999))
        sf.set_battle_sp(safe_int(self._bat_sp.get(),  999, 0, 9999))
        sf.set_battle_maxhp(safe_int(self._bat_mhp.get(), 999, 0, 9999))
        messagebox.showinfo("Applied", "Battle state changes applied.")

    # ── Compendium tab (read-only overview) ───────────────────────────────────

    def _build_comp_tab(self):
        top = ttk.Frame(self._tab_comp)
        top.pack(fill="x", padx=8, pady=4)
        ttk.Label(top, text="Filter by Persona ID or Name:").pack(side="left")
        self._comp_filter = tk.StringVar()
        self._comp_filter.trace_add("write", lambda *_: self._filter_comp())
        ttk.Entry(top, textvariable=self._comp_filter, width=25).pack(side="left", padx=4)
        ttk.Label(top, text="(read-only overview – edit via Palette tab)",
                  foreground="gray").pack(side="left", padx=8)

        cols = ("pid", "name", "level", "exp", "idx")
        self._comp_tree = ttk.Treeview(self._tab_comp, columns=cols, show="headings",
                                       selectmode="browse")
        for col, hdr, w in zip(cols,
                                ("Persona ID", "Name", "Level", "EXP", "Area Index"),
                                (90, 200, 70, 110, 90)):
            self._comp_tree.heading(col, text=hdr)
            self._comp_tree.column(col, width=w, anchor="center")

        vsb = ttk.Scrollbar(self._tab_comp, orient="vertical",
                             command=self._comp_tree.yview)
        self._comp_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._comp_tree.pack(fill="both", expand=True, padx=8, pady=4)

        self._comp_entries: list[dict] = []

    def _populate_comp(self):
        self._comp_entries = self.sf.scan_compendium()
        self._filter_comp()

    def _filter_comp(self, *_):
        f = self._comp_filter.get().strip().lower()
        tree = self._comp_tree
        for item in tree.get_children():
            tree.delete(item)
        for e in self._comp_entries:
            name = persona_name(e["pid"])
            if f and f not in str(e["pid"]) and f not in name.lower():
                continue
            tree.insert("", "end", values=(
                e["pid"], name, e["level"], e["exp"], e["idx"]))

    # ── File operations ───────────────────────────────────────────────────────

    def open_file(self, path: str = None):
        if path is None:
            path = filedialog.askopenfilename(
                title="Open save JSON",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.sf.load(path)
            self._populate_all()
            self._set_enabled(True)
            self._lbl_file.config(text=str(path), foreground="black")
        except Exception as exc:
            messagebox.showerror("Error loading file", str(exc))

    def save_file(self):
        if not self.sf.path:
            self.save_as()
            return
        try:
            self.sf.save()
            messagebox.showinfo("Saved", f"Saved to:\n{self.sf.path}")
        except Exception as exc:
            messagebox.showerror("Error saving", str(exc))

    def save_as(self):
        path = filedialog.asksaveasfilename(
            title="Save JSON As",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            try:
                self.sf.save(path)
                self._lbl_file.config(text=str(path))
                messagebox.showinfo("Saved", f"Saved to:\n{path}")
            except Exception as exc:
                messagebox.showerror("Error saving", str(exc))

    # ── Populate UI from loaded save ──────────────────────────────────────────

    def _populate_all(self):
        self._pop_header()
        self._pop_party()
        self._pop_persona()
        self._pop_battle()
        self._populate_comp()

    def _pop_header(self):
        sf = self.sf
        self._hdr_first.set(sf.get_first_name())
        self._hdr_last.set(sf.get_last_name())
        self._hdr_level.set(str(sf.get_header_int("PlayerLevel_0")))
        self._hdr_diff.set(str(sf.get_header_int("Difficulty_0")))
        self._hdr_month.set(str(sf.get_header_int("Month_0")))
        self._hdr_day.set(str(sf.get_header_int("Day_0")))
        self._hdr_fmaj.set(str(sf.get_header_int("FldMajorID_0")))
        self._hdr_fmin.set(str(sf.get_header_int("FldMinorID_0")))
        self._hdr_fpar.set(str(sf.get_header_int("FldPartsID_0")))
        self._hdr_tz.set(sf.get_header_str("TimeZone_0"))
        self._boss_var.set(list(BOSS_PRESETS.keys())[0])

    def _pop_party(self):
        for slot, w in enumerate(self._party_widgets):
            w["level"].set(str(self.sf.get_party_level(slot)))
            w["exp"].set(str(self.sf.get_party_exp(slot)))
            stats = self.sf.get_party_stats(slot)
            for i, sv in enumerate(w["stats"]):
                sv.set(str(stats[i]))
            skills = self.sf.get_party_skills(slot)
            for i, sv in enumerate(w["skills"]):
                sv.set(str(skills[i]))

    def _pop_persona(self):
        for slot, w in enumerate(self._persona_widgets):
            w["pid"].set(str(self.sf.get_persona_id(slot)))
            w["level"].set(str(self.sf.get_persona_level(slot)))
            w["exp"].set(str(self.sf.get_persona_exp(slot)))
            stats = self.sf.get_persona_stats(slot)
            for i, sv in enumerate(w["stats"]):
                sv.set(str(stats[i]))
            skills = self.sf.get_persona_skills(slot)
            for i, sv in enumerate(w["skills"]):
                sv.set(str(skills[i]))

    def _pop_battle(self):
        self._bat_hp.set(str(self.sf.get_battle_hp()))
        self._bat_sp.set(str(self.sf.get_battle_sp()))
        self._bat_mhp.set(str(self.sf.get_battle_maxhp()))

    # ── Enable / disable UI ───────────────────────────────────────────────────

    def _set_enabled(self, state: bool):
        s = "normal" if state else "disabled"
        self._btn_save.config(state=s)


# ─────────────────────────────── ENTRY POINT ──────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Persona 3 Reload – Save File JSON Editor"
    )
    parser.add_argument(
        "file", nargs="?", default=None,
        help="Path to a decrypted save JSON file to open on startup"
    )
    args = parser.parse_args()

    app = App()

    if args.file:
        # Schedule the load after the event loop starts so the window is ready
        app.after(100, lambda: app.open_file(args.file))

    app.mainloop()