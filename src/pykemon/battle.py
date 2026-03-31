"""
Core battle models and game logic.

BattlePokemon / Move data classes, level-50 stat scaling,
damage calculation, and turn resolution.
"""

import random
from dataclasses import dataclass
from typing import Optional

from .db import get_connection

LEVEL = 50


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Move:
    move_id: int
    name: str
    type: str
    category: str   # 'Physical' | 'Special'
    power: int
    accuracy: int   # 1-100


@dataclass
class BattlePokemon:
    pokemon_id: int
    name: str
    primary_type: str
    secondary_type: Optional[str]
    max_hp: int
    current_hp: int
    attack: int
    defense: int
    sp_atk: int
    sp_def: int
    speed: int
    moves: list  # List[Move]

    @property
    def is_fainted(self) -> bool:
        return self.current_hp <= 0

    def hp_bar(self, width: int = 20) -> str:
        ratio = max(0.0, self.current_hp / self.max_hp)
        filled = round(ratio * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {self.current_hp}/{self.max_hp}"


# ── Stat scaling ──────────────────────────────────────────────────────────────

def _scale_stat(base: int, is_hp: bool = False) -> int:
    """Scale a base stat to level LEVEL (Gen 3+ formula, no EVs/IVs)."""
    if is_hp:
        return (2 * base * LEVEL) // 100 + LEVEL + 10
    return (2 * base * LEVEL) // 100 + 5


# ── Database loading ──────────────────────────────────────────────────────────

def load_pokemon(pokemon_id: int) -> BattlePokemon:
    """Load a BattlePokemon from the DB at level 50 with its top-4 damaging moves."""
    con = get_connection()

    row = con.execute(
        """
        SELECT pokemon_id, name, primary_type, secondary_type,
               hp, attack, defense, sp_atk, sp_def, speed
        FROM   pokemon
        WHERE  pokemon_id = ?
        """,
        [pokemon_id],
    ).fetchone()

    if row is None:
        con.close()
        raise ValueError(f"Pokemon ID {pokemon_id} not found in database.")

    move_rows = con.execute(
        """
        SELECT DISTINCT
               m.move_id,
               m.move_name,
               m.type,
               m.category,
               COALESCE(m.power, 0)   AS power,
               COALESCE(m.accuracy, 100) AS accuracy
        FROM   pokemon_move pm
        JOIN   move m ON pm.move_id = m.move_id
        WHERE  pm.pokemon_id = ?
          AND  m.category IN ('Physical', 'Special')
          AND  m.power > 0
        ORDER  BY m.power DESC
        LIMIT  4
        """,
        [pokemon_id],
    ).fetchall()

    con.close()

    moves = [Move(r[0], r[1], r[2], r[3], r[4], r[5] or 100) for r in move_rows]
    max_hp = _scale_stat(row[4], is_hp=True)

    return BattlePokemon(
        pokemon_id=row[0],
        name=row[1],
        primary_type=row[2],
        secondary_type=row[3],
        max_hp=max_hp,
        current_hp=max_hp,
        attack=_scale_stat(row[5]),
        defense=_scale_stat(row[6]),
        sp_atk=_scale_stat(row[7]),
        sp_def=_scale_stat(row[8]),
        speed=_scale_stat(row[9]),
        moves=moves,
    )


# ── Curated roster ────────────────────────────────────────────────────────────

_ROSTER_NUMBERS = [
    1, 4, 7, 25, 52, 54, 58, 63, 66,
    79, 94, 113, 131, 133, 143, 147, 152, 155, 158, 196,
]


def get_pokemon_list() -> list:
    """Return a curated list of (pokemon_id, name, primary_type, secondary_type)."""
    con = get_connection()
    placeholders = ",".join(["?"] * len(_ROSTER_NUMBERS))
    rows = con.execute(
        f"""
        SELECT pokemon_id, name, primary_type, secondary_type
        FROM   pokemon
        WHERE  number IN ({placeholders})
          AND  form_name IS NULL
        ORDER  BY number
        """,
        _ROSTER_NUMBERS,
    ).fetchall()
    con.close()
    return rows


# ── Battle mechanics ──────────────────────────────────────────────────────────

def calculate_damage(attacker: BattlePokemon, move: Move, defender: BattlePokemon) -> int:
    """
    Return damage dealt, or -1 if the move missed.
    Uses a simplified Gen 4 damage formula (no type chart, no crits for MVP).
    """
    if move.accuracy < 100 and random.randint(1, 100) > move.accuracy:
        return -1

    atk = attacker.sp_atk if move.category == "Special" else attacker.attack
    def_ = defender.sp_def if move.category == "Special" else defender.defense

    dmg = ((2 * LEVEL / 5 + 2) * move.power * atk / def_) / 50 + 2
    dmg *= random.uniform(0.85, 1.0)
    return max(1, int(dmg))


def resolve_turn(
    host: BattlePokemon,
    host_move: Move,
    opp: BattlePokemon,
    opp_move: Move,
) -> list:
    """
    Resolve one battle turn in speed order. Mutates current_hp of both pokemon.

    Returns a list of event dicts with keys:
        attacker_side : 'host' | 'opp'
        move          : str
        missed        : bool
        damage        : int
        fainted_side  : 'host' | 'opp' | None
    """
    events = []

    # Ties go to host
    if host.speed >= opp.speed:
        order = [
            ("host", host, host_move, "opp", opp),
            ("opp",  opp,  opp_move,  "host", host),
        ]
    else:
        order = [
            ("opp",  opp,  opp_move,  "host", host),
            ("host", host, host_move, "opp", opp),
        ]

    for att_side, attacker, move, def_side, defender in order:
        if defender.is_fainted:
            break

        dmg = calculate_damage(attacker, move, defender)
        fainted_side = None

        if dmg > 0:
            defender.current_hp = max(0, defender.current_hp - dmg)
            if defender.is_fainted:
                fainted_side = def_side

        events.append({
            "attacker_side": att_side,
            "move":          move.name,
            "missed":        dmg == -1,
            "damage":        max(0, dmg),
            "fainted_side":  fainted_side,
        })

    return events


def format_events(events: list, perspective: str) -> list:
    """
    Format turn events as human-readable strings from 'host' or 'opp' perspective.
    """
    lines = []
    for e in events:
        actor = "You" if perspective == e["attacker_side"] else "Opponent"
        if e["missed"]:
            lines.append(f"{actor} used {e['move']}... but it missed!")
        else:
            lines.append(f"{actor} used {e['move']}! ({e['damage']} damage)")
        if e["fainted_side"]:
            whose = "Your" if perspective == e["fainted_side"] else "Opponent's"
            lines.append(f"  {whose} Pokemon fainted!")
    return lines
