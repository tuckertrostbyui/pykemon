"""
Battle data models.

All stats on Pokemon are final computed values — base stats, IVs, EVs,
and nature modifiers are baked in at construction time via default_teams.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Move:
    move_id:   int
    move_name: str
    type:      str
    category:  str          # "Physical" | "Special" | "Status"
    power:     int | None   # None for status moves
    accuracy:  int | None   # None for moves that never miss (e.g. Swift)
    pp:        int
    effect:    str


@dataclass
class MoveSlot:
    move:       Move
    current_pp: int         # starts at move.pp; decremented on use


@dataclass
class Pokemon:
    # Identity
    team_pokemon_id: int
    name:            str
    primary_type:    str
    secondary_type:  str | None

    # Final computed stats (nature already applied)
    max_hp:  int
    attack:  int
    defense: int
    sp_atk:  int
    sp_def:  int
    speed:   int

    # Battle state
    current_hp: int
    is_fainted: bool = False

    # Metadata (display only; no mechanical effect in v1)
    level:  int = 100
    nature: str = "Hardy"
    ability: str = "None"
    item:   str | None = None


@dataclass
class Trainer:
    name:      str
    team_name: str
    roster:    list[Pokemon]    # up to 6, ordered as sent-out priority


@dataclass
class Field:
    active_t1: Pokemon
    active_t2: Pokemon
    moves_t1:  list[MoveSlot]   # 4 slots for active_t1
    moves_t2:  list[MoveSlot]   # 4 slots for active_t2
