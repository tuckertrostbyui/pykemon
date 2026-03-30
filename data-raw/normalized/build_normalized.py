# %%
import polars as pl
from pathlib import Path

# %%
"""
Build Pokemon_Moves nomralized
"""
POKEMON_MOVES = Path("raw/pokemon_moves.csv")
POKEMON_MOVES_NORMALIZED = Path("normalized/pokemon_moves.csv")
POKEMON = Path("raw/pokemon.csv")
MOVES = Path("raw/moves.csv")
POKEMON_ABILITY = Path("raw/pokemon_ability.csv")
POKEMON_ABILITY_NORMALIZED = Path("normalized/pokemon_ability.csv")
ABILITY = Path("raw/ability.csv")
# %%
pokemon = pl.read_csv(POKEMON).with_row_index(name="pokemon_id", offset=1)
moves = pl.read_csv(MOVES).with_row_index(name="move_id", offset=1)
old_pokemon_moves = pl.read_csv(POKEMON_MOVES)
old_pokemon_moves
# %%
pokemon_moves_normalized = (
    pokemon.join(old_pokemon_moves, left_on="name", right_on="pokemon_name")
    .select("pokemon_id", "move_name", "generation", "game", "method", "detail")
    .join(moves, on="move_name")
    .select("pokemon_id", "move_id", "generation", "game", "method", "detail")
)

# %%
pokemon_moves_normalized.write_csv(POKEMON_MOVES_NORMALIZED)

# %%
"""
Build pokmeon_ability normalized
"""
pokemon = pl.read_csv(POKEMON).with_row_index(name="pokemon_id", offset=1)
ability = pl.read_csv(ABILITY).with_row_index(name="ability_id", offset=1)
old_pokemon_ability = pl.read_csv(POKEMON_ABILITY)

# %%
pokemon_ability_normalized = (
    pokemon.join(old_pokemon_ability, left_on="name", right_on="pokemon_name")
    .select("pokemon_id", "ability_name", "slot")
    .join(ability, on="ability_name")
    .select("pokemon_id", "ability_id", "slot")
)

# %%
pokemon_ability_normalized.write_csv(POKEMON_ABILITY_NORMALIZED)
