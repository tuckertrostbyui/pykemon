"""
Pokémon Ability Data Scraper - pokemondb.net

Scrapes ability effect for all unique abilities in pokemon_abilities.csv.

Usage:
    python scrape_abilities_data.py --abilities data-raw/raw/pokemon_abilities.csv --out data-raw/raw/abilities.csv
"""

import re
import time
import argparse
import requests
import polars as pl
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def ability_name_to_slug(ability_name: str) -> str:
    slug = ability_name.lower()
    slug = slug.replace(" ", "-")
    slug = slug.replace("'", "")
    slug = slug.replace(".", "")
    slug = re.sub(r"-+", "-", slug)
    return slug


def get_ability_page(ability_name: str) -> BeautifulSoup | None:
    slug = ability_name_to_slug(ability_name)
    url = f"https://pokemondb.net/ability/{slug}"
    for attempt in range(3):
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "html.parser")
        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  Rate limited on {ability_name}, waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            print(f"  WARNING: page not found for {ability_name} (slug: {slug})")
            return None
    print(f"  ERROR: gave up on {ability_name} after 3 attempts")
    return None


def parse_ability_page(ability_name: str, soup: BeautifulSoup) -> dict:
    result = {"ability_name": ability_name, "effect": None}

    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True) == "Effect":
            next_sibling = h2.find_next_sibling()
            if next_sibling and next_sibling.name == "p":
                effect = next_sibling.get_text(separator=" ", strip=True)
                result["effect"] = re.split(r"Game descriptions", effect)[0].strip()
            break

    return result


def scrape_all_ability_data(
    pokemon_abilities_csv: str,
    output_file: str | None = None,
    request_delay: float = 0.2,
) -> pl.DataFrame:
    ability_names = (
        pl.read_csv(pokemon_abilities_csv)
        .select("ability_name")
        .unique()["ability_name"]
        .to_list()
    )

    print(f"Found {len(ability_names)} unique abilities to scrape.")

    rows = []
    for i, ability_name in enumerate(ability_names, 1):
        print(f"[{i}/{len(ability_names)}] {ability_name}...")
        soup = get_ability_page(ability_name)
        if not soup:
            rows.append({"ability_name": ability_name, "effect": None})
            continue
        rows.append(parse_ability_page(ability_name, soup))
        time.sleep(request_delay)

    df = pl.DataFrame(rows, schema={"ability_name": pl.Utf8, "effect": pl.Utf8})

    if output_file:
        df.write_csv(output_file)
        print(f"\nSaved {len(df)} rows → {output_file}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape ability data from pokemondb.net"
    )
    parser.add_argument(
        "--abilities", type=str, required=True, help="Path to pokemon_abilities.csv"
    )
    parser.add_argument("--out", type=str, required=False, help="Output CSV path")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Seconds between requests (default 0.2)",
    )
    args = parser.parse_args()

    scrape_all_ability_data(
        pokemon_abilities_csv=args.abilities,
        output_file=args.out,
        request_delay=args.delay,
    )
