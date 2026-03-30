"""
Build small tables that don't need to be scraped
current:
    natures
    status_effects
"""

# %%
import polars as pl
from pathlib import Path

# %%
# fmt: off
nature = pl.DataFrame({ 
    "name": [
        "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
        "Bold", "Docile", "Relaxed", "Impish", "Lax",
        "Timid", "Hasty", "Serious", "Jolly", "Naive",
        "Modest", "Mild", "Quiet", "Bashful", "Rash",
        "Calm", "Gentle", "Sassy", "Careful", "Quirky"
    ],
    "stat_up": [
        None, "attack", "attack", "attack", "attack",
        "defense", None, "defense", "defense", "defense",
        "speed", "speed", None, "speed", "speed",
        "sp_atk", "sp_atk", "sp_atk", None, "sp_atk",
        "sp_def", "sp_def", "sp_def", "sp_def", None
    ],
    "stat_down": [
        None, "defense", "speed", "sp_atk", "sp_def",
        "attack", None, "speed", "sp_atk", "sp_def",
        "attack", "defense", None, "sp_atk", "sp_def",
        "attack", "defense", "speed", None, "sp_def",
        "attack", "defense", "speed", "sp_atk", None
    ],
})

status_effect = pl.DataFrame({
    "name": ["burn", "paralysis", "poison", "bad_poison", "sleep", "freeze"],
    "abbreviation": ["BRN", "PAR", "PSN", "TOX", "SLP", "FRZ"],
    "end_of_turn_damage": [1/16, None, 1/8, None, None, None],
    "speed_modifier": [None, 0.5, None, None, None, None],
    "attack_modifier": [0.5, None, None, None, None, None],
    "max_turns": [None, None, None, None, 5, 1],
    "effect": [
        "Loses 1/16 HP per turn, attack halved",
        "Speed halved, 25% chance to be fully paralyzed",
        "Loses 1/8 HP per turn",
        "Damage increases each turn (1/16, 2/16, ... up to 15/16)",
        "Cannot move for 1-5 turns",
        "Cannot move, thaws on fire moves or 20% chance per turn"
    ]
})
# fmt: on
# %%
NATURE = Path("raw/nature.csv")
STATUS_EFFECT = Path("raw/status_effect.csv")

nature.write_csv(NATURE)
status_effect.write_csv(STATUS_EFFECT)
