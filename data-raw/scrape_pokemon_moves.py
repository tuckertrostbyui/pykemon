"""
Pokémon Moves Scraper - pokemondb.net gen 9

Scrapes level-up, TM, and egg moves for all Pokémon in gen 9
(Scarlet/Violet and Legends: Z-A), using the pokemon.csv as input.

Skips Mega evolutions and other non-standard forms that don't have
their own move tabs.

Usage:
    from scrape_moves import scrape_all_moves

    moves = scrape_all_moves("data-raw/raw/pokemon.csv")
"""

import time
import csv
import requests
from bs4 import BeautifulSoup


HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
GENERATION = 9
GAMES = {
    "scarlet-violet": "tab-moves-21",
    "legends-za": "tab-moves-22",
}
SKIP_FORMS = {"Mega", "Gigantamax", "Primal", "Eternamax"}


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------


def get_moves_page(base_name: str) -> BeautifulSoup | None:
    slug = base_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
    url = f"https://pokemondb.net/pokedex/{slug}/moves/9"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 429:
        print(f"  Rate limited on {base_name}, waiting 10s...")
        # time.sleep()
        resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"  WARNING: {url} returned {resp.status_code}")
        return None
    return BeautifulSoup(resp.text, "html.parser")


# ---------------------------------------------------------------------------
# Panel resolution - find the right game + form panel
# ---------------------------------------------------------------------------


def get_all_game_tabs(soup):
    """Return {game_label: tab_id} for whatever tabs exist on this page."""
    tabs = {}
    tab_list = soup.find("div", class_="sv-tabs-tab-list")
    if tab_list:
        for a in tab_list.find_all("a"):
            tab_id = a["href"].lstrip("#")
            label = a.get_text(strip=True)
            tabs[label] = tab_id
    return tabs


def get_game_panel(soup: BeautifulSoup, game_tab_id: str) -> BeautifulSoup | None:
    """Return the div for a specific game tab (e.g. tab-moves-21)."""
    panel = soup.find("div", id=game_tab_id)
    return panel


def get_form_panel(
    game_panel, form_name: str | None, section: str
) -> BeautifulSoup | None:
    section_header_text = {
        "level": "level up",
        "tm": "by TM",
        "hm": "by HM",
        "egg": "egg move",
        "tutor": "by Move Tutor",  # gen 3-7
        "tr": "by TR",  # gen 8 SwSh
    }

    target_h3 = None
    for h3 in game_panel.find_all("h3"):
        if section_header_text[section] in h3.get_text(strip=True):
            target_h3 = h3
            break

    if not target_h3:
        return None

    next_wrapper = target_h3.find_next(
        "div", class_=lambda c: c and ("resp-scroll" in c or "sv-tabs-wrapper" in c)
    )

    if not next_wrapper:
        return None

    # No form tabs — direct table
    if "resp-scroll" in next_wrapper.get("class", []):
        return next_wrapper

    # Form tabs — match by label
    if "sv-tabs-wrapper" in next_wrapper.get("class", []):
        tab_list = next_wrapper.find("div", class_="sv-tabs-tab-list")
        panels = next_wrapper.find("div", class_="sv-tabs-panel-list").find_all(
            "div", class_="sv-tabs-panel", recursive=False
        )
        for i, tab in enumerate(tab_list.find_all("a")):
            label = tab.get_text(strip=True)
            if not form_name and i == 0:
                return panels[i].find("div", class_="resp-scroll")
            if form_name and form_name.lower() == label.lower():
                return panels[i].find("div", class_="resp-scroll")

    return None


# ---------------------------------------------------------------------------
# Table parsers
# ---------------------------------------------------------------------------


def parse_level_table(panel) -> list[dict]:
    """Parse a level-up moves table. Returns list of {move_name, detail}."""
    if not panel:
        return []
    moves = []
    table = panel.find("table")
    if not table:
        return []
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        level = cells[0].get_text(strip=True)
        move_link = cells[1].find("a", class_="ent-name")
        if not move_link:
            continue
        moves.append(
            {
                "move_name": move_link.get_text(strip=True),
                "method": "level",
                "detail": level,
            }
        )
    return moves


def parse_tm_table(panel) -> list[dict]:
    """Parse a TM moves table. Returns list of {move_name, detail}."""
    if not panel:
        return []
    moves = []
    table = panel.find("table")
    if not table:
        return []
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        tm_num = cells[0].get_text(strip=True).zfill(3)
        move_link = cells[1].find("a", class_="ent-name")
        if not move_link:
            continue
        moves.append(
            {
                "move_name": move_link.get_text(strip=True),
                "method": "tm",
                "detail": f"TM{tm_num}",
            }
        )
    return moves


def parse_egg_table(panel) -> list[dict]:
    """Parse an egg moves table. Returns list of {move_name, detail}."""
    if not panel:
        return []

    # Egg moves section is found differently - after an h3 containing "egg"
    # panel here is the resp-scroll div or the game panel itself
    # We need to search from the h3 for egg moves
    moves = []
    table = panel.find("table")
    if not table:
        return []
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 1:
            continue
        move_link = cells[0].find("a", class_="ent-name")
        if not move_link:
            continue
        moves.append(
            {
                "move_name": move_link.get_text(strip=True),
                "method": "egg",
                "detail": "",
            }
        )
    return moves


# ---------------------------------------------------------------------------
# Per-pokemon scrape
# ---------------------------------------------------------------------------


def scrape_pokemon_moves(
    base_name: str,
    form_name: str | None,
    soup: BeautifulSoup,
) -> list[dict]:
    """
    Scrape all moves for one pokemon form across both games.
    Returns a flat list of pokemon_moves dicts.
    """
    pokemon_name = f"{base_name} ({form_name})" if form_name else base_name
    rows = []

    for game, tab_id in GAMES.items():
        game_panel = get_game_panel(soup, tab_id)
        if not game_panel:
            continue

        level_panel = get_form_panel(game_panel, form_name, "level")
        tm_panel = get_form_panel(game_panel, form_name, "tm")
        egg_panel = get_form_panel(game_panel, form_name, "egg")

        moves = []
        moves.extend(parse_level_table(level_panel))
        moves.extend(parse_tm_table(tm_panel))
        moves.extend(parse_egg_table(egg_panel))

        for move in moves:
            rows.append(
                {
                    "pokemon_name": pokemon_name,
                    "move_name": move["move_name"],
                    "generation": GENERATION,
                    "game": game,
                    "method": move["method"],
                    "detail": move["detail"],
                }
            )

    return rows


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def should_skip(form_name: str) -> bool:
    """Skip Megas, Gigantamax, and other battle-only forms with no move tabs."""
    if not form_name:
        return False
    return any(skip in form_name for skip in SKIP_FORMS)


def scrape_all_moves_gen_9(
    pokemon_csv: str, output_file: str | None = None
) -> list[dict]:
    """
    Scrape gen 9 moves for all pokemon in the csv.
    Groups by base_name so we only fetch each page once.
    """
    # Load pokemon list
    with open(pokemon_csv, encoding="utf-8") as f:
        pokemon_list = list(csv.DictReader(f))

    # Group forms by base_name so we fetch each page once
    by_base: dict[str, list[dict]] = {}
    for p in pokemon_list:
        if should_skip(p["form_name"]):
            print(f"  Skipping {p['name']}")
            continue
        by_base.setdefault(p["base_name"], []).append(p)

    all_moves = []

    for base_name, forms in by_base.items():
        print(f"Scraping {base_name}...")
        soup = get_moves_page(base_name)
        if not soup:
            continue

        for form in forms:
            form_name = form["form_name"] or None
            moves = scrape_pokemon_moves(base_name, form_name, soup)
            all_moves.extend(moves)
            print(f"  {form['name']}: {len(moves)} move rows")

        # time.sleep(0.05)  # be polite

    if output_file:
        with open(output_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_moves[0].keys())
            writer.writeheader()
            writer.writerows(all_moves)
        print(f"Saved {len(all_moves)} rows → {output_file}")

    return all_moves


if __name__ == "__main__":
    moves = scrape_all_moves_gen_9(
        "data-raw/raw/pokemon.csv",
        "data-raw/raw/pokemon_moves.csv",
    )
    print(f"Total move rows: {len(moves)}")
