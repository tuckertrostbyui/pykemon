"""
Pokémon Abilities Scraper - pokemondb.net

Scrapes abilities for all Pokémon from their main pokedex page.
Uses pokemon.csv link column as the base URL.

Outputs a CSV:
    pokemon_name, ability_name, slot

Where slot is 1, 2, or "hidden"

Usage:
    python scrape_abilities.py --pokemon data-raw/raw/pokemon.csv --out data-raw/raw/pokemon_abilities.csv
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
SKIP_FORMS = {"Gigantamax", "Eternamax"}  # keep Mega and Primal


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------


def get_pokedex_page(link: str) -> BeautifulSoup | None:
    for attempt in range(3):
        resp = requests.get(link, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "html.parser")
        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  Rate limited on {link}, waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            print(f"  WARNING: page not found for {link}")
            return None
        print(f"  WARNING: {link} returned {resp.status_code}")
        return None
    print(f"  ERROR: gave up on {link} after 3 attempts")
    return None


# ---------------------------------------------------------------------------
# Ability parsing
# ---------------------------------------------------------------------------


def parse_abilities(soup: BeautifulSoup, form_name: str | None) -> list[dict]:
    tab_list = soup.find("div", class_="sv-tabs-tab-list")
    panel_list = soup.find("div", class_="sv-tabs-panel-list")

    if not tab_list or not panel_list:
        target_table = soup.find("table", class_="vitals-table")
    else:
        tabs = tab_list.find_all("a")
        panels = panel_list.find_all("div", class_="sv-tabs-panel", recursive=False)

        target_table = None
        for i, tab in enumerate(tabs):
            label = tab.get_text(strip=True)
            if not form_name and i == 0:
                target_table = panels[i].find("table", class_="vitals-table")
                break
            if form_name and form_name.lower() == label.lower():
                target_table = panels[i].find("table", class_="vitals-table")
                break

    if not target_table:
        return []

    for row in target_table.find_all("tr"):
        th = row.find("th")
        if th and th.get_text(strip=True) == "Abilities":
            return parse_ability_row(row)

    return []


def parse_ability_row(row) -> list[dict]:
    """
    Parse the abilities cell into structured rows.
    Slot 1 and 2 are in <span class="text-muted">
    Hidden ability is in <small class="text-muted">
    """
    abilities = []
    td = row.find("td")
    if not td:
        return []

    # Regular abilities — numbered spans
    for span in td.find_all("span", class_="text-muted"):
        link = span.find("a")
        if not link:
            continue
        text = span.get_text(strip=True)
        # Extract slot number from "1. Overgrow" or "2. Chlorophyll"
        slot = text.split(".")[0].strip() if "." in text else "1"
        abilities.append({"ability_name": link.get_text(strip=True), "slot": slot})

    # Hidden ability — in <small>
    small = td.find("small", class_="text-muted")
    if small:
        link = small.find("a")
        if link:
            abilities.append(
                {"ability_name": link.get_text(strip=True), "slot": "hidden"}
            )

    return abilities


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def should_skip(form_name: str) -> bool:
    if not form_name:
        return False
    return any(skip in form_name for skip in SKIP_FORMS)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def scrape_all_abilities(
    pokemon_csv: str,
    output_file: str | None = None,
    request_delay: float = 0.3,
) -> list[dict]:
    with open(pokemon_csv, encoding="utf-8") as f:
        pokemon_list = list(csv.DictReader(f))

    # Group by link (base page) so we only fetch each page once
    by_link: dict[str, list[dict]] = {}
    for p in pokemon_list:
        if should_skip(p["form_name"]):
            print(f"  Skipping {p['name']} (unsupported form)")
            continue
        by_link.setdefault(p["link"], []).append(p)

    all_rows: list[dict] = []

    for link, forms in by_link.items():
        base_name = forms[0]["base_name"]
        print(f"Scraping {base_name}...")
        soup = get_pokedex_page(link)
        if not soup:
            continue

        for form in forms:
            form_name = (
                form["form_name"] if form["form_name"] not in ("", "None") else None
            )
            pokemon_name = (
                f"{form['base_name']} ({form_name})" if form_name else form["base_name"]
            )
            print(f"  form_name being passed: '{form_name}'")  # add this

            abilities = parse_abilities(soup, form_name)
            for ability in abilities:
                all_rows.append(
                    {
                        "pokemon_name": pokemon_name,
                        "ability_name": ability["ability_name"],
                        "slot": ability["slot"],
                    }
                )

            print(f"  {pokemon_name}: {[a['ability_name'] for a in abilities]}")

        time.sleep(request_delay)

    if output_file and all_rows:
        fieldnames = ["pokemon_name", "ability_name", "slot"]
        with open(output_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\nSaved {len(all_rows)} rows → {output_file}")
    elif output_file:
        print("WARNING: no rows scraped, output file not written.")

    return all_rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape Pokémon abilities from pokemondb.net"
    )
    parser.add_argument(
        "--pokemon", type=str, required=True, help="Path to pokemon.csv"
    )
    parser.add_argument("--out", type=str, required=False, help="Output CSV path")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Seconds between requests (default 0.3)",
    )
    args = parser.parse_args()

    scrape_all_abilities(
        pokemon_csv=args.pokemon,
        output_file=args.out,
        request_delay=args.delay,
    )
