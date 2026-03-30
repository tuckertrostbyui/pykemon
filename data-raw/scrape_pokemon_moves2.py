"""
Pokémon Moves Scraper - pokemondb.net (any generation)

Scrapes level-up, TM, HM, TR, egg, tutor, evolution, pre-evolution,
special, and transfer-only moves for all Pokémon in a given generation,
using pokemon.csv as input.

Outputs a single CSV matching the pokemon_moves DuckDB schema:
    pokemon_move_id, pokemon_name, move_name, generation, game, method, detail

Skips Mega, Gigantamax, Primal, and Eternamax forms.

Usage:
    python scrape_moves.py --gen 9 --pokemon data-raw/raw/pokemon.csv --out data-raw/raw/pokemon_moves.csv

    or from Python:
        from scrape_moves import scrape_all_moves
        moves = scrape_all_moves("data-raw/raw/pokemon.csv", generation=9, output_file="pokemon_moves.csv")
"""

import csv
import time
import argparse
import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

SKIP_FORMS = {"Mega", "Gigantamax", "Primal", "Eternamax"}

# All section types pokemondb uses across all generations.
# Keys are used as the `method` value in output rows.
# Values are EXACT h3 text strings as they appear on pokemondb.net
# (discovered empirically via discover_headers.py across gens 3-8).
SECTION_HEADERS = {
    "level": "Moves learnt by level up",
    "tm": "Moves learnt by TM",
    "hm": "Moves learnt by HM",
    "tr": "Moves learnt by TR",  # Gen 8 Sword/Shield only
    "egg": "Egg moves",
    "tutor": "Move Tutor moves",
    "evolution": "Moves learnt on evolution",
    "pre_evo": "Pre-evolution moves",
    "special": "Special moves",
    "transfer": "Transfer-only moves",
}


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------


def get_moves_page(base_name: str, generation: int) -> BeautifulSoup | None:
    slug = (
        base_name.lower()
        .replace(" ", "-")
        .replace("'", "")
        .replace(".", "")
        .replace(":", "")
    )
    url = f"https://pokemondb.net/pokedex/{slug}/moves/{generation}"
    for attempt in range(3):
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "html.parser")
        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  Rate limited on {base_name}, waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            print(f"  WARNING: page not found for {base_name} (gen {generation})")
            return None
        print(f"  WARNING: {url} returned {resp.status_code}")
        return None
    print(f"  ERROR: gave up on {base_name} after 3 attempts")
    return None


# ---------------------------------------------------------------------------
# Tab discovery — finds all game tabs on the page dynamically
# ---------------------------------------------------------------------------


def get_all_game_tabs(soup: BeautifulSoup) -> dict[str, str]:
    """
    Return {game_slug: tab_div_id} for every game tab on the page.
    Tab labels like "Scarlet/Violet" become slugs like "scarlet-violet".
    """
    tabs = {}

    # Top-level tab list (games)
    tab_list = soup.find("div", class_="sv-tabs-tab-list")
    if not tab_list:
        # Some pages (very old gens) have no tabs at all — treat as single panel
        return {"default": None}

    for a in tab_list.find_all("a", recursive=False):
        href = a.get("href", "").lstrip("#")
        label = a.get_text(strip=True)
        slug = label.lower().replace("/", "-").replace(" ", "-").replace(":", "")
        tabs[slug] = href

    return tabs


# ---------------------------------------------------------------------------
# Panel resolution
# ---------------------------------------------------------------------------


def get_game_panel(soup: BeautifulSoup, tab_id: str | None) -> BeautifulSoup | None:
    """Return the div for a specific game tab, or the whole soup if no tabs."""
    if tab_id is None:
        return soup
    return soup.find("div", id=tab_id)


def get_section_panel(
    game_panel, form_name: str | None, method: str
) -> BeautifulSoup | None:
    """
    Find the resp-scroll div for a given section (level/tm/hm/egg/tutor/tr)
    within a game panel, optionally scoped to a specific form tab.
    """
    header_text = SECTION_HEADERS.get(method)
    if not header_text:
        return None

    # Find the h3 for this section — exact match against known header strings
    target_h3 = None
    for h3 in game_panel.find_all("h3"):
        if h3.get_text(strip=True) == header_text:
            target_h3 = h3
            break
    if not target_h3:
        return None

    # The next sibling wrapper is either a direct resp-scroll or a form tabs wrapper
    next_wrapper = target_h3.find_next(
        "div",
        class_=lambda c: c and ("resp-scroll" in c or "sv-tabs-wrapper" in c),
    )
    if not next_wrapper:
        return None

    # Direct table — no form subtabs
    if "resp-scroll" in next_wrapper.get("class", []):
        return next_wrapper

    # Form subtabs — match by label
    if "sv-tabs-wrapper" in next_wrapper.get("class", []):
        tab_list = next_wrapper.find("div", class_="sv-tabs-tab-list")
        panel_list = next_wrapper.find("div", class_="sv-tabs-panel-list")
        if not tab_list or not panel_list:
            return None
        panels = panel_list.find_all("div", class_="sv-tabs-panel", recursive=False)
        for i, tab in enumerate(tab_list.find_all("a")):
            label = tab.get_text(strip=True)
            if not form_name and i == 0:
                return panels[i].find("div", class_="resp-scroll")
            if form_name and form_name.lower() == label.lower():
                return panels[i].find("div", class_="resp-scroll")

    return None


# ---------------------------------------------------------------------------
# Unified table parser
# ---------------------------------------------------------------------------


def parse_move_table(panel, method: str) -> list[dict]:
    """
    Generic move table parser that works for all section types.

    - Finds the move name via <a class="ent-name">
    - Uses the first cell as the detail (level number, TM/HM/TR number, etc.)
    - Egg moves and tutors have no meaningful detail — detail is left blank
    """
    if not panel:
        return []
    table = panel.find("table")
    if not table:
        return []

    moves = []
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        # Find the move name link anywhere in the row
        move_link = None
        for cell in cells:
            move_link = cell.find("a", class_="ent-name")
            if move_link:
                break
        if not move_link:
            continue

        move_name = move_link.get_text(strip=True)
        first_cell = cells[0].get_text(strip=True)

        # Format the detail field
        if method == "level":
            detail = first_cell  # e.g. "1", "25", "Evo."
        elif method == "tm":
            detail = f"TM{first_cell.lstrip('TM').zfill(3)}" if first_cell else ""
        elif method == "hm":
            detail = f"HM{first_cell.lstrip('HM').zfill(2)}" if first_cell else ""
        elif method == "tr":
            detail = f"TR{first_cell.lstrip('TR').zfill(2)}" if first_cell else ""
        else:
            detail = ""  # egg, tutor

        moves.append({"move_name": move_name, "method": method, "detail": detail})

    return moves


# ---------------------------------------------------------------------------
# Per-Pokémon scrape
# ---------------------------------------------------------------------------


def scrape_pokemon_moves(
    base_name: str,
    form_name: str | None,
    generation: int,
    soup: BeautifulSoup,
) -> list[dict]:
    """
    Scrape all moves for one Pokémon form across all games in the generation.
    Returns flat list of dicts matching the DuckDB schema (minus pokemon_move_id).
    """
    pokemon_name = f"{base_name} ({form_name})" if form_name else base_name
    rows = []

    game_tabs = get_all_game_tabs(soup)

    for game_slug, tab_id in game_tabs.items():
        game_panel = get_game_panel(soup, tab_id)
        if not game_panel:
            continue

        for method in SECTION_HEADERS:
            panel = get_section_panel(game_panel, form_name, method)
            moves = parse_move_table(panel, method)
            for move in moves:
                rows.append(
                    {
                        "pokemon_name": pokemon_name,
                        "move_name": move["move_name"],
                        "generation": generation,
                        "game": game_slug,
                        "method": move["method"],
                        "detail": move["detail"],
                    }
                )

    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def should_skip(form_name: str) -> bool:
    if not form_name:
        return False
    return any(skip in form_name for skip in SKIP_FORMS)


def slug_to_base_name(base_name: str) -> str:
    """Normalise base_name for URL slug generation."""
    return (
        base_name.lower()
        .replace(" ", "-")
        .replace("'", "")
        .replace(".", "")
        .replace(":", "")
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def scrape_all_moves(
    pokemon_csv: str,
    generation: int,
    output_file: str | None = None,
    request_delay: float = 0.1,
) -> list[dict]:
    """
    Scrape all moves for the given generation.

    Args:
        pokemon_csv:    Path to pokemon.csv (must have base_name, form_name, name columns).
        generation:     Generation number (1–9).
        output_file:    If provided, write results to this CSV path.
        request_delay:  Seconds to sleep between page fetches (be polite).

    Returns:
        List of dicts with keys:
            pokemon_move_id, pokemon_name, move_name, generation, game, method, detail
    """
    # Load Pokémon list
    with open(pokemon_csv, encoding="utf-8") as f:
        pokemon_list = list(csv.DictReader(f))

    # Group forms by base_name so we only fetch each page once
    by_base: dict[str, list[dict]] = {}
    for p in pokemon_list:
        if should_skip(p["form_name"]):
            print(f"  Skipping {p['name']} (unsupported form)")
            continue
        by_base.setdefault(p["base_name"], []).append(p)

    all_moves: list[dict] = []

    for base_name, forms in by_base.items():
        print(f"Scraping {base_name} (gen {generation})...")
        soup = get_moves_page(base_name, generation)
        if not soup:
            continue

        for form in forms:
            form_name = form["form_name"] or None
            moves = scrape_pokemon_moves(base_name, form_name, generation, soup)

            all_moves.extend(moves)
            print(f"  {form['name']}: {len(moves)} move rows")

        time.sleep(request_delay)

    if output_file and all_moves:
        fieldnames = [
            "pokemon_name",
            "move_name",
            "generation",
            "game",
            "method",
            "detail",
        ]
        with open(output_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_moves)
        print(f"\nSaved {len(all_moves)} rows → {output_file}")
    elif output_file:
        print("WARNING: no rows scraped, output file not written.")

    return all_moves


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Pokémon moves from pokemondb.net"
    )
    parser.add_argument(
        "--gen", type=int, required=True, help="Generation number (e.g. 9)"
    )
    parser.add_argument(
        "--pokemon", type=str, required=True, help="Path to pokemon.csv"
    )
    parser.add_argument("--out", type=str, required=False, help="Output CSV path")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Seconds between requests (default 0.1)",
    )
    args = parser.parse_args()

    moves = scrape_all_moves(
        pokemon_csv=args.pokemon,
        generation=args.gen,
        output_file=args.out,
        request_delay=args.delay,
    )
    print(f"Total move rows: {len(moves)}")
