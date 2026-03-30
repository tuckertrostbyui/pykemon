"""
Quick script to discover all h3 section headers used across gens 3-8
on pokemondb.net, so we can verify SECTION_HEADERS in scrape_moves.py.

Uses a small sample of Pokémon that exist across all gens.
Usage:
    python discover_headers.py
"""

import time
import requests
from bs4 import BeautifulSoup
from collections import defaultdict

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# A handful of Pokémon that exist across all gens 1-9
SAMPLE_POKEMON = ["pikachu", "dragonite", "machamp", "alakazam"]


def get_page(slug: str, gen: int) -> BeautifulSoup | None:
    url = f"https://pokemondb.net/pokedex/{slug}/moves/{gen}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 200:
        return BeautifulSoup(resp.text, "html.parser")
    print(f"  {url} → {resp.status_code}")
    return None


def get_game_tabs(soup: BeautifulSoup) -> dict[str, str]:
    tabs = {}
    tab_list = soup.find("div", class_="sv-tabs-tab-list")
    if not tab_list:
        return {"default": None}
    for a in tab_list.find_all("a", recursive=False):
        href = a.get("href", "").lstrip("#")
        label = a.get_text(strip=True)
        tabs[label] = href
    return tabs


def get_game_panel(soup: BeautifulSoup, tab_id: str | None):
    if tab_id is None:
        return soup
    return soup.find("div", id=tab_id)


# {gen: {game: set(h3 texts)}}
results = defaultdict(lambda: defaultdict(set))

for gen in range(3, 9):
    print(f"\n=== Gen {gen} ===")
    for slug in SAMPLE_POKEMON:
        print(f"  {slug}...")
        soup = get_page(slug, gen)
        if not soup:
            continue
        tabs = get_game_tabs(soup)
        for game_label, tab_id in tabs.items():
            panel = get_game_panel(soup, tab_id)
            if not panel:
                continue
            for h3 in panel.find_all("h3"):
                text = h3.get_text(strip=True)
                results[gen][game_label].add(text)
        time.sleep(0.2)

# Print summary
print("\n\n=== RESULTS ===")
for gen in sorted(results):
    print(f"\nGen {gen}:")
    all_headers = set()
    for game, headers in results[gen].items():
        all_headers |= headers
    for game, headers in sorted(results[gen].items()):
        print(f"  [{game}]")
        for h in sorted(headers):
            print(f"    {repr(h)}")

print("\n\n=== ALL UNIQUE H3s ACROSS GENS 3-8 ===")
all_unique = set()
for gen in results:
    for game in results[gen]:
        all_unique |= results[gen][game]
for h in sorted(all_unique):
    print(f"  {repr(h)}")
