"""
Hardcoded default teams for testing (no team builder yet).

load_default_teams() queries the existing DB once for base stats, move data,
and nature modifiers, then returns two fully-built Trainer objects plus a
dict mapping team_pokemon_id -> list[Move] for the server to use when
initializing move slots.
"""

from __future__ import annotations

import math

from ..db import get_connection
from .models import Move, Pokemon, Trainer

# ── Team configurations ───────────────────────────────────────────────────────
# evs keys match DB stat column names: hp, attack, defense, sp_atk, sp_def, speed

_TEAM_RED: dict = {
    "trainer_name": "Red",
    "team_name": "Team Red",
    "pokemon": [
        {
            "name": "Charizard", "nature": "Timid", "ability": "Blaze", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"sp_atk": 252, "speed": 252, "hp": 4},
            "moves": ["Flamethrower", "Dragon Claw", "Air Slash", "Fire Blast"],
        },
        {
            "name": "Blastoise", "nature": "Modest", "ability": "Torrent", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"sp_atk": 252, "speed": 252, "hp": 4},
            "moves": ["Surf", "Ice Beam", "Hydro Pump", "Aura Sphere"],
        },
        {
            "name": "Venusaur", "nature": "Bold", "ability": "Overgrow", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"hp": 252, "defense": 252, "sp_atk": 4},
            "moves": ["Energy Ball", "Sludge Bomb", "Solar Beam", "Giga Drain"],
        },
        {
            "name": "Pikachu", "nature": "Hasty", "ability": "Static", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"sp_atk": 252, "speed": 252, "hp": 4},
            "moves": ["Thunderbolt", "Volt Tackle", "Wild Charge", "Surf"],
        },
        {
            "name": "Snorlax", "nature": "Careful", "ability": "Thick Fat", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"hp": 252, "sp_def": 252, "attack": 4},
            "moves": ["Body Slam", "Ice Beam", "Skull Bash", "Double-Edge"],
        },
        {
            "name": "Gengar", "nature": "Timid", "ability": "Cursed Body", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"sp_atk": 252, "speed": 252, "hp": 4},
            "moves": ["Shadow Ball", "Sludge Bomb", "Psychic", "Dark Pulse"],
        },
    ],
}

_TEAM_BLUE: dict = {
    "trainer_name": "Blue",
    "team_name": "Team Blue",
    "pokemon": [
        {
            "name": "Arcanine", "nature": "Adamant", "ability": "Intimidate", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"attack": 252, "speed": 252, "hp": 4},
            "moves": ["Flare Blitz", "Outrage", "Close Combat", "Overheat"],
        },
        {
            "name": "Lapras", "nature": "Modest", "ability": "Water Absorb", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"hp": 252, "sp_atk": 252, "sp_def": 4},
            "moves": ["Hydro Pump", "Blizzard", "Ice Beam", "Surf"],
        },
        {
            "name": "Alakazam", "nature": "Timid", "ability": "Magic Guard", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"sp_atk": 252, "speed": 252, "hp": 4},
            "moves": ["Psychic", "Shadow Ball", "Focus Blast", "Future Sight"],
        },
        {
            "name": "Machamp", "nature": "Adamant", "ability": "No Guard", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"attack": 252, "hp": 252, "defense": 4},
            "moves": ["Close Combat", "Earthquake", "Superpower", "Focus Punch"],
        },
        {
            "name": "Dragonite", "nature": "Adamant", "ability": "Multiscale", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"attack": 252, "speed": 252, "hp": 4},
            "moves": ["Outrage", "Dragon Rush", "Fly", "Hurricane"],
        },
        {
            "name": "Jolteon", "nature": "Timid", "ability": "Volt Absorb", "item": None,
            "level": 100, "ivs": 31,
            "evs": {"sp_atk": 252, "speed": 252, "hp": 4},
            "moves": ["Thunderbolt", "Thunder", "Shadow Ball", "Wild Charge"],
        },
    ],
}

# ── Stat calculation ──────────────────────────────────────────────────────────

_STAT_KEYS = ("attack", "defense", "sp_atk", "sp_def", "speed")


def _compute_hp(base: int, iv: int, ev: int, level: int) -> int:
    return math.floor(((2 * base + iv + math.floor(ev / 4)) * level) / 100) + level + 10


def _compute_stat(base: int, iv: int, ev: int, level: int, nature_mod: float) -> int:
    inner = math.floor(((2 * base + iv + math.floor(ev / 4)) * level) / 100) + 5
    return math.floor(inner * nature_mod)


def _nature_mods(stat_up: str | None, stat_down: str | None) -> dict[str, float]:
    mods = {s: 1.0 for s in _STAT_KEYS}
    if stat_up:
        mods[stat_up] = 1.1
    if stat_down:
        mods[stat_down] = 0.9
    return mods


# ── Team loading ──────────────────────────────────────────────────────────────

def load_default_teams() -> tuple[Trainer, Trainer, dict[int, list[Move]]]:
    """
    Build both default Trainer objects from a single DB pass.

    Returns (trainer_red, trainer_blue, pokemon_moves) where
    pokemon_moves maps team_pokemon_id -> list[Move] (the server
    uses this to initialize MoveSlots).
    """
    all_configs = _TEAM_RED["pokemon"] + _TEAM_BLUE["pokemon"]

    all_poke_names   = list({p["name"]   for p in all_configs})
    all_move_names   = list({m for p in all_configs for m in p["moves"]})
    all_nature_names = list({p["nature"] for p in all_configs})

    con = get_connection()

    pn = ",".join(["?"] * len(all_poke_names))
    poke_rows = con.execute(
        f"""
        SELECT name, primary_type, secondary_type,
               hp, attack, defense, sp_atk, sp_def, speed
        FROM   pokemon
        WHERE  name IN ({pn})
          AND  form_name IS NULL
        """,
        all_poke_names,
    ).fetchall()

    mn = ",".join(["?"] * len(all_move_names))
    move_rows = con.execute(
        f"""
        SELECT DISTINCT move_id, move_name, type, category, power, accuracy, pp, effect
        FROM   move
        WHERE  move_name IN ({mn})
        """,
        all_move_names,
    ).fetchall()

    nn = ",".join(["?"] * len(all_nature_names))
    nature_rows = con.execute(
        f"""
        SELECT name, stat_up, stat_down
        FROM   nature
        WHERE  name IN ({nn})
        """,
        all_nature_names,
    ).fetchall()

    con.close()

    # Build lookup dicts
    poke_by_name   = {r[0]: r for r in poke_rows}
    move_by_name   = {r[1]: r for r in move_rows}
    nature_by_name = {r[0]: r for r in nature_rows}

    pokemon_moves: dict[int, list[Move]] = {}
    next_id = 1

    def _build_trainer(team_cfg: dict) -> Trainer:
        nonlocal next_id
        roster: list[Pokemon] = []

        for cfg in team_cfg["pokemon"]:
            prow = poke_by_name.get(cfg["name"])
            if prow is None:
                raise ValueError(f"Pokemon '{cfg['name']}' not found in DB.")

            _, primary_type, secondary_type, base_hp, base_atk, base_def, base_spa, base_spd, base_spe = prow

            nrow = nature_by_name.get(cfg["nature"])
            if nrow is None:
                raise ValueError(f"Nature '{cfg['nature']}' not found in DB.")
            _, stat_up, stat_down = nrow
            mods = _nature_mods(stat_up, stat_down)

            ivs = cfg["ivs"]   # single int: all stats use this value
            evs = cfg["evs"]   # dict of stat_name -> ev_value (missing = 0)
            level = cfg["level"]

            max_hp = _compute_hp(base_hp, ivs, evs.get("hp", 0), level)

            pokemon = Pokemon(
                team_pokemon_id=next_id,
                name=cfg["name"],
                primary_type=primary_type,
                secondary_type=secondary_type,
                max_hp=max_hp,
                attack=_compute_stat(base_atk, ivs, evs.get("attack",  0), level, mods["attack"]),
                defense=_compute_stat(base_def, ivs, evs.get("defense", 0), level, mods["defense"]),
                sp_atk=_compute_stat(base_spa, ivs, evs.get("sp_atk",  0), level, mods["sp_atk"]),
                sp_def=_compute_stat(base_spd, ivs, evs.get("sp_def",  0), level, mods["sp_def"]),
                speed=_compute_stat(base_spe, ivs, evs.get("speed",   0), level, mods["speed"]),
                current_hp=max_hp,
                level=level,
                nature=cfg["nature"],
                ability=cfg.get("ability", "None"),
                item=cfg.get("item"),
            )

            moves: list[Move] = []
            for move_name in cfg["moves"]:
                mrow = move_by_name.get(move_name)
                if mrow is None:
                    print(f"  WARNING: move '{move_name}' not found in DB — skipping.")
                    continue
                move_id, mn_str, mtype, category, power, accuracy, pp, effect = mrow
                moves.append(Move(
                    move_id=move_id,
                    move_name=mn_str,
                    type=mtype,
                    category=category,
                    power=power,
                    accuracy=accuracy,
                    pp=pp,
                    effect=effect or "",
                ))

            pokemon_moves[next_id] = moves
            roster.append(pokemon)
            next_id += 1

        return Trainer(
            name=team_cfg["trainer_name"],
            team_name=team_cfg["team_name"],
            roster=roster,
        )

    trainer_red  = _build_trainer(_TEAM_RED)
    trainer_blue = _build_trainer(_TEAM_BLUE)

    return trainer_red, trainer_blue, pokemon_moves
