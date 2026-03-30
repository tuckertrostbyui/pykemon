# %%
import polars as pl
from pathlib import Path
from scrape_pokemon import scrape_pokemon
from scrape_item import scrape_items
from scrape_pokemon_moves import scrape_all_moves_gen_9
from scrape_pokemon_moves2 import scrape_all_moves
from scrape_moves import scrape_all_move_data
from scrape_pokemon_abilities import scrape_all_abilities
from scrape_ability import scrape_all_ability_data

# %%
POKEMON_CSV = Path("raw/pokemon.csv")

data = scrape_pokemon(POKEMON_CSV)

# %%

ITEMS_CSV = Path("raw/items.csv")

data = scrape_items(ITEMS_CSV)

# %%
POKEMON_MOVES_CSV = Path("raw/pokemon_moves.csv")

# data = scrape_all_moves_gen_9(POKEMON_CSV, POKEMON_MOVES_CSV)

# %%
all_moves = []


for gen in range(1, 10):
    print(f"\n=== Generation {gen} ===")
    moves = scrape_all_moves(
        pokemon_csv="raw/pokemon.csv",
        generation=gen,
        request_delay=0.05,
    )
    all_moves.extend(moves)

# Write once at the end
import csv

fieldnames = [
    "pokemon_name",
    "move_name",
    "generation",
    "game",
    "method",
    "detail",
]
with open("raw/pokemon_moves.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_moves)

print(f"\nDone. Total rows: {len(all_moves)}")

# %%

MOVES_CSV = Path("raw/moves.csv")
POKEMON_MOVES_CSV = Path("raw/pokemon_moves.csv")

data = scrape_all_move_data(POKEMON_MOVES_CSV, MOVES_CSV, 0.01)

# %%

POKEMON_ABILITY_CSV = Path("raw/pokemon_ability.csv")

scrape_all_abilities(
    pokemon_csv=POKEMON_CSV,
    output_file=POKEMON_ABILITY_CSV,
    request_delay=0.01,
)
# %%

ABILITY_CSV = Path("raw/ability.csv")
POKEMON_ABILITY_CSV = Path("raw/pokemon_ability.csv")
scrape_all_ability_data(POKEMON_ABILITY_CSV, ABILITY_CSV, request_delay=0.01)


# %%%
# # %%
# from scrape_pokemon_moves import *

# soup = get_moves_page("Seel")

# # Check what game tab IDs actually exist
# tabs = soup.find_all("a", class_="sv-tabs-tab")
# for tab in tabs:
#     print(tab.get_text(strip=True), "→", tab.get("href"))
# # %%

# soup = get_moves_page("Seel")
# game_panel = get_game_panel(soup, "tab-moves-21")

# # Check what h3s are in the panel
# for h3 in game_panel.find_all("h3"):
#     print(repr(h3.get_text(strip=True)))
# # %%
# soup = get_moves_page("Seel")
# game_panel = get_game_panel(soup, "tab-moves-21")

# for h3 in game_panel.find_all("h3"):
#     print("H3:", repr(h3.get_text(strip=True)))
#     sib = h3.find_next_sibling()
#     print("  next sibling tag:", sib.name if sib else None)
#     print("  next sibling classes:", sib.get("class") if sib else None)
#     print()
#     # %%
#     soup = get_moves_page("Seel")
# game_panel = get_game_panel(soup, "tab-moves-21")

# for h3 in game_panel.find_all("h3"):
#     print("H3:", repr(h3.get_text(strip=True)))
#     sib = h3.find_next_sibling()
#     print("  next sibling tag:", sib.name if sib else None)
#     print("  next sibling classes:", sib.get("class") if sib else None)
#     print()

# # %%
# soup = get_moves_page("Seel")
# game_panel = get_game_panel(soup, "tab-moves-21")

# for h3 in game_panel.find_all("h3"):
#     print("H3:", repr(h3.get_text(strip=True)))
#     next_wrapper = h3.find_next("div", class_=lambda c: c and (
#         "resp-scroll" in c or "sv-tabs-wrapper" in c
#     ))
#     print("  found:", next_wrapper.name if next_wrapper else None)
#     print("  classes:", next_wrapper.get("class") if next_wrapper else None)
#     table = next_wrapper.find("table") if next_wrapper else None
#     print("  has table:", table is not None)
#     print()
# # %%
