"""
Item Scraper - pokemondb.net/item/all

Requirements:
    pip install requests beautifulsoup4

Usage:
    from scrape_items import scrape_items

    data = scrape_items()                  # returns a list of dicts
    data = scrape_items("items.csv")       # also saves to a csv file
"""

import csv
import requests
from bs4 import BeautifulSoup
from pathlib import Path


def scrape_items(output_file=None):
    """
    Scrapes all items from pokemondb.net and returns a list of dicts.

    Each entry contains:
        name, category, effect, sprite_url

    Args:
        output_file (str, optional): If provided, saves the result as CSV to this path.

    Returns:
        list[dict]: All item entries.
    """
    url = "https://pokemondb.net/item/all"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.select_one("#main > div.resp-scroll > table")

    if not table:
        raise RuntimeError("Could not find items table on page.")

    items_list = []

    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Sprite
        img_tag = cells[0].find("img")
        sprite_url = img_tag["src"] if img_tag else ""

        # Name
        ent_link = cells[0].find("a", class_="ent-name")
        name = ent_link.get_text(strip=True) if ent_link else ""

        # Category
        category = cells[1].get_text(strip=True)

        # Effect
        effect = cells[2].get_text(strip=True)

        items_list.append(
            {
                "name": name,
                "category": category,
                "effect": effect,
                "sprite_url": sprite_url,
            }
        )

    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=items_list[0].keys())
            writer.writeheader()
            writer.writerows(items_list)
        print(f"Saved {len(items_list)} items → {output_file}")

    return items_list


if __name__ == "__main__":
    data = scrape_items("data-raw/raw/items.csv")
    print(f"Scraped {len(data)} items")
    print(data[0])
