"""
Pokémon Move Data Scraper - pokemondb.net

Scrapes move stats (type, category, power, accuracy, pp, makes_contact,
introduced, effect, z_effect) for all unique moves in the pokemon_moves table.

Usage:
    python scrape_moves_data.py --db path/to/pykemon.duckdb --out data-raw/raw/moves.csv

    or from Python:
        from scrape_moves_data import scrape_all_move_data
        df = scrape_all_move_data("pykemon.duckdb", "moves.csv")
"""

import re
import time
import argparse
import requests
import polars as pl
import duckdb
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


def move_name_to_slug(move_name: str) -> str:
    """
    Convert a move name to a pokemondb URL slug.

    Examples:
        "Focus Energy"  → "focus-energy"
        "Mud-Slap"      → "mud-slap"
        "ThunderPunch"  → "thunderpunch"
        "U-turn"        → "u-turn"
        "10,000,000 Volt Thunderbolt" → "10000000-volt-thunderbolt"
    """
    slug = move_name.lower()
    slug = slug.replace(",", "")  # remove commas
    slug = slug.replace("'", "")  # remove apostrophes
    slug = slug.replace(".", "")  # remove periods
    slug = slug.replace(" ", "-")  # spaces to dashes
    # Collapse any double dashes that might result
    slug = re.sub(r"-+", "-", slug)
    return slug


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------


def get_move_page(move_name: str) -> BeautifulSoup | None:
    slug = move_name_to_slug(move_name)
    url = f"https://pokemondb.net/move/{slug}"
    for attempt in range(3):
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "html.parser")
        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  Rate limited on {move_name}, waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            print(f"  WARNING: page not found for {move_name} (slug: {slug})")
            return None
        print(f"  WARNING: {url} returned {resp.status_code}")
        return None
    print(f"  ERROR: gave up on {move_name} after 3 attempts")
    return None


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------


def parse_move_page(move_name: str, soup: BeautifulSoup) -> dict:
    """
    Extract move data from a pokemondb move page.
    Returns a dict with all fields; missing values are None.
    """
    result = {
        "move_name": move_name,
        "type": None,
        "category": None,
        "power": None,
        "accuracy": None,
        "pp": None,
        "makes_contact": None,
        "introduced": None,
        "effect": None,
        "z_effect": None,
    }

    # --- Vitals table ---
    vitals = soup.find("table", class_="vitals-table")
    if vitals:
        for row in vitals.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True)
            value = td.get_text(strip=True)

            if label == "Type":
                result["type"] = (
                    td.find("a").get_text(strip=True) if td.find("a") else None
                )

            elif label == "Category":
                # Category is in the img alt text: "Physical", "Special", "Status"
                img = td.find("img")
                result["category"] = img["alt"] if img else None

            elif label == "Power":
                result["power"] = None if value == "—" else _parse_int(value)

            elif label == "Accuracy":
                result["accuracy"] = None if value == "—" else _parse_int(value)

            elif label == "PP":
                # "30 (max. 48)" → 30
                result["pp"] = _parse_int(value.split()[0])

            elif label == "Makes contact?":
                result["makes_contact"] = value.strip() == "Yes"

            elif label == "Introduced":
                # "Generation 1" → 1
                match = re.search(r"\d+", value)
                result["introduced"] = int(match.group()) if match else None

    # --- Effect ---
    effects_h2 = soup.find("h2", id="move-effects")
    if effects_h2:
        # First <p> after the h2
        next_p = effects_h2.find_next("p")
        if next_p:
            result["effect"] = next_p.get_text(strip=True)

    # --- Z-Move effect ---
    for h3 in soup.find_all("h3"):
        if "Z-Move effects" in h3.get_text(strip=True):
            next_p = h3.find_next("p")
            if next_p:
                result["z_effect"] = next_p.get_text(strip=True)
            break

    return result


def _parse_int(value: str) -> int | None:
    """Parse an integer from a string, returning None if not possible."""
    try:
        return int(re.search(r"\d+", value).group())
    except (AttributeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def scrape_all_move_data(
    pokemon_moves_csv: str,
    output_file: str | None = None,
    request_delay: float = 0.1,
) -> pl.DataFrame:
    """
    Scrape move data for all unique moves in the pokemon_moves table.

    Args:
        db_path:        Path to the DuckDB database file.
        output_file:    If provided, write results to this CSV path.
        request_delay:  Seconds to sleep between requests.

    Returns:
        Polars DataFrame with columns:
            move_name, type, category, power, accuracy, pp,
            makes_contact, introduced, effect, z_effect
    """
    # Get unique move names from the csv
    move_names = (
        pl.read_csv(pokemon_moves_csv)
        .select("move_name")
        .unique()["move_name"]
        .to_list()
    )

    print(f"Found {len(move_names)} unique moves to scrape.")

    rows = []
    for i, move_name in enumerate(move_names, 1):
        print(f"[{i}/{len(move_names)}] {move_name}...")
        soup = get_move_page(move_name)
        if not soup:
            # Still add a row with nulls so we know it was attempted
            rows.append(
                {
                    "move_name": move_name,
                    "type": None,
                    "category": None,
                    "power": None,
                    "accuracy": None,
                    "pp": None,
                    "makes_contact": None,
                    "introduced": None,
                    "effect": None,
                    "z_effect": None,
                }
            )
            continue

        row = parse_move_page(move_name, soup)
        rows.append(row)
        time.sleep(request_delay)

    df = pl.DataFrame(
        rows,
        schema={
            "move_name": pl.Utf8,
            "type": pl.Utf8,
            "category": pl.Utf8,
            "power": pl.Int64,
            "accuracy": pl.Int64,
            "pp": pl.Int64,
            "makes_contact": pl.Boolean,
            "introduced": pl.Int64,
            "effect": pl.Utf8,
            "z_effect": pl.Utf8,
        },
    )

    if output_file:
        df.write_csv(output_file)
        print(f"\nSaved {len(df)} rows → {output_file}")

    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape move data from pokemondb.net")
    parser.add_argument("--db", type=str, required=True, help="Path to pykemon.duckdb")
    parser.add_argument("--out", type=str, required=False, help="Output CSV path")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Seconds between requests (default 0.1)",
    )
    args = parser.parse_args()

    df = scrape_all_move_data(
        db_path=args.db,
        output_file=args.out,
        request_delay=args.delay,
    )
    print(f"Total moves scraped: {len(df)}")
