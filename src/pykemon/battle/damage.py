"""
Damage calculation functions.

All functions are pure — no side effects, no mutation.
damage_calc() returns (final_damage, event_strings).
The caller is responsible for calling accuracy_check() first.
"""

from __future__ import annotations

import random

from .models import Move, Pokemon
from .type_chart import get_effectiveness


def accuracy_check(move: Move) -> bool:
    """Return True if the move hits. None accuracy means it never misses."""
    if move.accuracy is None:
        return True
    return random.randint(1, 100) <= move.accuracy


def calc_stab(move: Move, attacker: Pokemon) -> float:
    """Return 1.5 if move type matches attacker's primary or secondary type, else 1.0."""
    if move.type == attacker.primary_type:
        return 1.5
    if attacker.secondary_type and move.type == attacker.secondary_type:
        return 1.5
    return 1.0


def is_crit() -> bool:
    """1/16 chance of a critical hit."""
    return random.random() < 0.0625


def damage_calc(
    attacker: Pokemon,
    move: Move,
    defender: Pokemon,
) -> tuple[int, list[str]]:
    """
    Compute final damage dealt and the associated event strings.

    Returns (damage, events). damage is 0 for immune matchups.
    Only call this for Physical or Special moves (not Status).
    """
    events: list[str] = []

    # Stat selection
    if move.category == "Special":
        atk_stat = attacker.sp_atk
        def_stat = defender.sp_def
    else:
        atk_stat = attacker.attack
        def_stat = defender.defense

    power = move.power or 0
    level = attacker.level

    # Base damage: floor(floor(floor(2*level/5 + 2) * power * (atk/def)) / 50 + 2)
    step1 = 2 * level // 5 + 2
    step2 = int(step1 * power * atk_stat / def_stat)
    dmg = step2 // 50 + 2

    # Type effectiveness
    effectiveness = get_effectiveness(
        move.type, defender.primary_type, defender.secondary_type
    )

    if effectiveness == 0.0:
        events.append(f"It doesn't affect {defender.name}...")
        return 0, events

    # Apply modifiers sequentially (floor after each)
    stab = calc_stab(move, attacker)
    crit_mult = 1.5 if is_crit() else 1.0

    dmg = int(dmg * stab)
    if stab > 1.0:
        events.append("STAB bonus applied!")

    dmg = int(dmg * effectiveness)
    if effectiveness >= 4.0:
        events.append("It's super effective! (2x)")
    elif effectiveness >= 2.0:
        events.append("It's super effective!")
    elif effectiveness <= 0.25:
        events.append("It's not very effective...")
    elif effectiveness < 1.0:
        events.append("It's not very effective...")

    dmg = int(dmg * crit_mult)
    if crit_mult > 1.0:
        events.append("A critical hit!")

    return max(1, dmg), events
