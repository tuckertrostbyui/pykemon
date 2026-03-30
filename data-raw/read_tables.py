# %%
import sys

sys.path.insert(0, "data-raw")
import polars as pl
import duckdb
from pathlib import Path
# %%

con = duckdb.connect("../src/pykemon/data/pykemon.duckdb")


pokemon = con.sql("SELECT * FROM pokemon").pl()
pokemon_moves = con.sql("SELECT * FROM pokemon_move").pl()
moves = con.sql("SELECT * FROM move").pl()
items = con.sql("SELECT * FROM item").pl()
abilities = con.sql("SELECT * FROM ability").pl()
pokemon_abilities = con.sql("SELECT * FROM pokemon_ability").pl()
natures = con.sql("SELECT * FROM nature").pl()
status_effects = con.sql("SELECT * FROM status_effect").pl()

# Sanity checks
print("=== Row counts ===")
print(f"pokemon:           {len(pokemon)}")
print(f"moves:             {len(moves)}")
print(f"items:             {len(items)}")
print(f"abilities:         {len(abilities)}")
print(f"natures:           {len(natures)}")
print(f"status_effects:    {len(status_effects)}")
print(f"pokemon_moves:     {len(pokemon_moves)}")
print(f"pokemon_abilities: {len(pokemon_abilities)}")

# Check for nulls in key columns
print("\n=== Null checks ===")
print(f"pokemon nulls in pokemon_id:          {pokemon['pokemon_id'].null_count()}")
print(f"moves nulls in move_id:               {moves['move_id'].null_count()}")
print(f"abilities nulls in ability_id:        {abilities['ability_id'].null_count()}")
print(
    f"pokemon_moves nulls in pokemon_id:    {pokemon_moves['pokemon_id'].null_count()}"
)
print(f"pokemon_moves nulls in move_id:       {pokemon_moves['move_id'].null_count()}")
print(
    f"pokemon_abilities nulls in pokemon_id:{pokemon_abilities['pokemon_id'].null_count()}"
)
print(
    f"pokemon_abilities nulls in ability_id:{pokemon_abilities['ability_id'].null_count()}"
)

# Spot checks
print("\n=== Spot checks ===")
print(pokemon.filter(pl.col("name") == "Bulbasaur"))
print(pokemon_abilities.filter(pl.col("pokemon_id") == 1))
print(moves.filter(pl.col("move_name") == "Tackle"))
print(natures.filter(pl.col("name") == "Adamant"))

con.close()

# %%
pokemon_moves.group_by("pokemon_name", "move_name").agg(pl.len())
