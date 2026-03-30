"""
Pokédex Scraper - pokemondb.net/pokedex/all

Requirements:
    pip install requests beautifulsoup4

Usage:
    from scrape_pokedex import scrape_pokedex

    data = scrape_pokedex()               # returns a list of dicts
    data = scrape_pokedex("pokedex.json") # also saves to a file
"""

import json
import requests
from bs4 import BeautifulSoup


def scrape_pokedex(output_file=None):
    """
    Scrapes the full Pokédex from pokemondb.net and returns a list of dicts.

    Each entry contains:
        number, name, base_name, form_name,
        primary_type, secondary_type,
        total, hp, attack, defense, sp_atk, sp_def, speed,
        link, sprite_url

    Args:
        output_file (str, optional): If provided, saves the result as JSON to this path.

    Returns:
        list[dict]: All Pokémon entries including regional forms and megas.
    """
    url = "https://pokemondb.net/pokedex/all"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="pokedex")
    if not table:
        raise RuntimeError("Could not find #pokedex table on page.")

    pokemon_list = []

    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        # Number
        num_span = cells[0].find("span", class_="infocard-cell-data")
        number = num_span.get_text(strip=True) if num_span else ""

        # Sprite
        source_tag = cells[0].find("source")
        img_tag = cells[0].find("img")
        if source_tag and source_tag.get("srcset"):
            sprite_url = source_tag["srcset"].strip()
        elif img_tag and img_tag.get("src"):
            sprite_url = img_tag["src"].strip()
        else:
            sprite_url = ""

        # Name, form, link
        ent_link = cells[1].find("a", class_="ent-name")
        base_name = ent_link.get_text(strip=True) if ent_link else ""
        link = (
            ("https://pokemondb.net" + ent_link["href"])
            if ent_link and ent_link.get("href")
            else ""
        )
        small_tag = cells[1].find("small", class_="text-muted")
        form_name = small_tag.get_text(strip=True) if small_tag else ""
        display_name = f"{base_name} ({form_name})" if form_name else base_name

        # Types
        type_links = cells[2].find_all("a", class_=lambda c: c and "type-icon" in c)
        types = [t.get_text(strip=True) for t in type_links]
        primary_type = types[0] if len(types) > 0 else ""
        secondary_type = types[1] if len(types) > 1 else ""

        # Stats
        def to_int(cell):
            txt = cell.get_text(strip=True)
            return int(txt) if txt.isdigit() else txt

        pokemon_list.append(
            {
                "number": number,
                "name": display_name,
                "base_name": base_name,
                "form_name": form_name,
                "primary_type": primary_type,
                "secondary_type": secondary_type,
                "total": to_int(cells[3]),
                "hp": to_int(cells[4]),
                "attack": to_int(cells[5]),
                "defense": to_int(cells[6]),
                "sp_atk": to_int(cells[7]),
                "sp_def": to_int(cells[8]),
                "speed": to_int(cells[9]),
                "link": link,
                "sprite_url": sprite_url,
            }
        )

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(pokemon_list, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(pokemon_list)} entries → {output_file}")

    return pokemon_list


if __name__ == "__main__":
    data = scrape_pokedex("pokedex.json")
    print(json.dumps(data[0], indent=2))
