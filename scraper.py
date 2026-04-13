"""
Scraper cen ze sklepów Leroy Merlin i Castorama (PL).
Próbuje pobrać aktualne ceny — w razie błędu używa bazy domyślnych cen.
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "price_cache.json"
CACHE_TTL_HOURS = 6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ──────────────────────────────────────────────
# Domyślna baza cen (PLN, aktualna na 2024/2025)
# ──────────────────────────────────────────────
FALLBACK: dict = {
    "panele_podlogowe": {
        "leroy_merlin": [
            {"name": "Panele 7 mm AC3 dąb naturalny",   "price": 28.90, "unit": "m²"},
            {"name": "Panele 8 mm AC4 orzech ciemny",   "price": 49.90, "unit": "m²"},
            {"name": "Panele 10 mm AC5 dąb premium",    "price": 79.90, "unit": "m²"},
            {"name": "Panele 12 mm AC5 antracyt",       "price": 109.00, "unit": "m²"},
        ],
        "castorama": [
            {"name": "Panele laminowane 7 mm jasny dąb", "price": 26.99, "unit": "m²"},
            {"name": "Panele laminowane 8 mm buk",       "price": 44.99, "unit": "m²"},
            {"name": "Panele 10 mm HDF wenge",           "price": 74.99, "unit": "m²"},
            {"name": "Panele premium 12 mm grey oak",    "price": 99.99, "unit": "m²"},
        ],
    },
    "plytki_podlogowe": {
        "leroy_merlin": [
            {"name": "Płytki gresowe 60×60 jasnoszare",  "price": 39.90, "unit": "m²"},
            {"name": "Płytki gresowe 80×80 beton look",  "price": 69.90, "unit": "m²"},
            {"name": "Płytki ceramiczne 33×33 terakota",  "price": 29.90, "unit": "m²"},
            {"name": "Płytki drewnopodobne 20×120",      "price": 89.90, "unit": "m²"},
        ],
        "castorama": [
            {"name": "Płytki gresowe 60×60 łupek",       "price": 37.99, "unit": "m²"},
            {"name": "Płytki gresowe 75×75 white mat",   "price": 64.99, "unit": "m²"},
            {"name": "Terakota 33×33 terra cotta",        "price": 27.99, "unit": "m²"},
            {"name": "Płytki drewnopodobne 19×119",      "price": 85.99, "unit": "m²"},
        ],
    },
    "plytki_scienne": {
        "leroy_merlin": [
            {"name": "Płytki ścienne 25×40 białe",       "price": 24.90, "unit": "m²"},
            {"name": "Płytki metro 7,5×15 kremowe",      "price": 34.90, "unit": "m²"},
            {"name": "Płytki łazienkowe 30×60 marmur",   "price": 59.90, "unit": "m²"},
            {"name": "Mozaika szklana 30×30",             "price": 89.90, "unit": "m²"},
        ],
        "castorama": [
            {"name": "Płytki ścienne 25×40 ecru",        "price": 22.99, "unit": "m²"},
            {"name": "Płytki metro 7,5×15 białe",        "price": 32.99, "unit": "m²"},
            {"name": "Płytki łazienkowe 29×59 grafitowe", "price": 55.99, "unit": "m²"},
            {"name": "Mozaika ceramiczna 30×30",          "price": 79.99, "unit": "m²"},
        ],
    },
    "farba_do_scian": {
        "leroy_merlin": [
            {"name": "Farba Colours Biała 10 L",          "price": 59.90,  "unit": "opak.", "coverage_m2_per_l": 10},
            {"name": "Farba Dulux EasyCare 2,5 L",        "price": 89.90,  "unit": "opak.", "coverage_m2_per_l": 12},
            {"name": "Farba Dekoral Akrylit 5 L",         "price": 79.00,  "unit": "opak.", "coverage_m2_per_l": 10},
            {"name": "Farba Śnieżka Supermal 10 L",       "price": 139.00, "unit": "opak.", "coverage_m2_per_l": 12},
        ],
        "castorama": [
            {"name": "Farba Castocolor biała 10 L",       "price": 55.99,  "unit": "opak.", "coverage_m2_per_l": 10},
            {"name": "Farba Dulux Simply Refresh 2,5 L",  "price": 84.99,  "unit": "opak.", "coverage_m2_per_l": 12},
            {"name": "Farba Bondex Premium 5 L",          "price": 74.99,  "unit": "opak.", "coverage_m2_per_l": 10},
            {"name": "Farba Tikkurila Optiva 10 L",       "price": 159.00, "unit": "opak.", "coverage_m2_per_l": 12},
        ],
    },
    "farba_sufitowa": {
        "leroy_merlin": [
            {"name": "Farba sufitowa Colours 10 L",       "price": 49.90,  "unit": "opak.", "coverage_m2_per_l": 10},
            {"name": "Farba sufitowa Dulux 5 L",          "price": 59.90,  "unit": "opak.", "coverage_m2_per_l": 11},
            {"name": "Farba sufitowa Śnieżka 10 L",       "price": 89.00,  "unit": "opak.", "coverage_m2_per_l": 12},
        ],
        "castorama": [
            {"name": "Farba sufitowa Castocolor 10 L",    "price": 46.99,  "unit": "opak.", "coverage_m2_per_l": 10},
            {"name": "Farba sufitowa Bondex 5 L",         "price": 54.99,  "unit": "opak.", "coverage_m2_per_l": 11},
            {"name": "Farba sufitowa Tikkurila 10 L",     "price": 99.00,  "unit": "opak.", "coverage_m2_per_l": 12},
        ],
    },
    "tapeta": {
        "leroy_merlin": [
            {"name": "Tapeta papierowa 0,53×10 m",        "price": 29.90, "unit": "rolka"},
            {"name": "Tapeta winylowa 0,53×10 m",         "price": 49.90, "unit": "rolka"},
            {"name": "Tapeta flizelinowa 1,06×10 m",      "price": 89.90, "unit": "rolka"},
            {"name": "Tapeta strukturalna 1,06×25 m",     "price": 149.00, "unit": "rolka"},
        ],
        "castorama": [
            {"name": "Tapeta papierowa 0,53×10 m",        "price": 27.99, "unit": "rolka"},
            {"name": "Tapeta winylowa 0,53×10 m",         "price": 46.99, "unit": "rolka"},
            {"name": "Tapeta flizelinowa 1,06×10 m",      "price": 84.99, "unit": "rolka"},
            {"name": "Tapeta lateksowa 1,06×25 m",        "price": 139.00, "unit": "rolka"},
        ],
    },
    "klej_do_plytek": {
        "leroy_merlin": [
            {"name": "Klej Colours standard C1 25 kg",   "price": 24.90, "unit": "worek", "coverage_m2_per_kg": 0.20},
            {"name": "Klej Botament C2 25 kg",           "price": 39.90, "unit": "worek", "coverage_m2_per_kg": 0.22},
            {"name": "Klej Mapei Kerabond 25 kg",        "price": 54.90, "unit": "worek", "coverage_m2_per_kg": 0.20},
        ],
        "castorama": [
            {"name": "Klej Castofix standard 25 kg",     "price": 22.99, "unit": "worek", "coverage_m2_per_kg": 0.20},
            {"name": "Klej Ceresit C2 25 kg",            "price": 37.99, "unit": "worek", "coverage_m2_per_kg": 0.22},
            {"name": "Klej Mapei Keraflex 25 kg",        "price": 52.99, "unit": "worek", "coverage_m2_per_kg": 0.20},
        ],
    },
    "fuga": {
        "leroy_merlin": [
            {"name": "Fuga Colours epoksydowa 2 kg",     "price": 19.90, "unit": "opak.", "coverage_m2_per_kg": 0.30},
            {"name": "Fuga Mapei Ultracolor 2 kg",       "price": 29.90, "unit": "opak.", "coverage_m2_per_kg": 0.30},
            {"name": "Fuga Botament cementowa 5 kg",     "price": 24.90, "unit": "opak.", "coverage_m2_per_kg": 0.30},
        ],
        "castorama": [
            {"name": "Fuga Castofix cementowa 2 kg",     "price": 17.99, "unit": "opak.", "coverage_m2_per_kg": 0.30},
            {"name": "Fuga Ceresit CE 40 2 kg",          "price": 26.99, "unit": "opak.", "coverage_m2_per_kg": 0.30},
            {"name": "Fuga epoksydowa Mapei 2 kg",       "price": 69.99, "unit": "opak.", "coverage_m2_per_kg": 0.25},
        ],
    },
    "listwy_przypodlogowe": {
        "leroy_merlin": [
            {"name": "Listwa MDF biała 2,4 m",           "price": 8.90,  "unit": "szt."},
            {"name": "Listwa PCV dąb 2,4 m",             "price": 12.90, "unit": "szt."},
            {"name": "Listwa MDF dąb lakierowany 2,4 m", "price": 19.90, "unit": "szt."},
        ],
        "castorama": [
            {"name": "Listwa MDF biała 2,4 m",           "price": 7.99,  "unit": "szt."},
            {"name": "Listwa PCV orzech 2,4 m",          "price": 11.99, "unit": "szt."},
            {"name": "Listwa MDF drewnopodobna 2,4 m",   "price": 17.99, "unit": "szt."},
        ],
    },
    "wykładzina": {
        "leroy_merlin": [
            {"name": "Wykładzina dywanowa tekstura 4 m",  "price": 19.90, "unit": "mb"},
            {"name": "Wykładzina PCV drewno 4 m",         "price": 34.90, "unit": "mb"},
            {"name": "Wykładzina dywanowa premium 5 m",   "price": 59.90, "unit": "mb"},
        ],
        "castorama": [
            {"name": "Wykładzina dywanowa pętelkowa 4 m", "price": 17.99, "unit": "mb"},
            {"name": "Wykładzina PCV kamień 4 m",         "price": 32.99, "unit": "mb"},
            {"name": "Wykładzina SPC click 4 m",          "price": 74.99, "unit": "mb"},
        ],
    },
}


# ──────────────────────────────────────────────
# Scraper
# ──────────────────────────────────────────────

def _get(url: str, timeout: int = 8) -> Optional[BeautifulSoup]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as exc:
        logger.warning("GET %s failed: %s", url, exc)
        return None


def _extract_json_ld(soup: BeautifulSoup) -> list:
    products = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                items = data
            elif data.get("@type") == "ItemList":
                items = data.get("itemListElement", [])
            else:
                items = [data]
            for item in items:
                offer = item.get("offers", {})
                price = offer.get("price") or item.get("price")
                name  = item.get("name")
                if price and name:
                    try:
                        products.append({
                            "name": name,
                            "price": float(str(price).replace(",", ".")),
                            "unit": "szt.",
                        })
                    except ValueError:
                        pass
        except Exception:
            pass
    return products


def _scrape_leroy_merlin(category_slug: str) -> list:
    urls = {
        "panele_podlogowe": "https://www.leroymerlin.pl/podlogi-i-schody/panele-podlogowe/",
        "plytki_podlogowe": "https://www.leroymerlin.pl/podlogi-i-schody/plytki-podlogowe/",
        "plytki_scienne":   "https://www.leroymerlin.pl/lazienka/plytki-i-mozaika/plytki-scienne/",
        "farba_do_scian":   "https://www.leroymerlin.pl/farby-i-tapety/farby/farby-do-scian-i-sufitow/",
        "farba_sufitowa":   "https://www.leroymerlin.pl/farby-i-tapety/farby/farby-do-scian-i-sufitow/",
        "tapeta":           "https://www.leroymerlin.pl/farby-i-tapety/tapety/",
    }
    url = urls.get(category_slug)
    if not url:
        return []

    soup = _get(url)
    if not soup:
        return []

    # Próba 1: JSON-LD
    products = _extract_json_ld(soup)
    if products:
        return products[:5]

    # Próba 2: __NEXT_DATA__
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag:
        try:
            data = json.loads(tag.string or "")
            items = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("products", [])
            )
            result = []
            for it in items[:5]:
                price = it.get("price") or it.get("offerPrice")
                name  = it.get("name") or it.get("title")
                if price and name:
                    result.append({
                        "name": name,
                        "price": float(str(price).replace(",", ".")),
                        "unit": "szt.",
                    })
            if result:
                return result
        except Exception:
            pass

    # Próba 3: parsowanie kart produktów
    result = []
    for card in soup.select("[data-product-id], .product-card, .tile__product")[:5]:
        name_el  = card.select_one(".product-name, .tile__title, h3")
        price_el = card.select_one(".price-value, .price__value, [data-price]")
        if name_el and price_el:
            raw = re.sub(r"[^\d,.]", "", price_el.get_text()).replace(",", ".")
            try:
                result.append({
                    "name":  name_el.get_text(strip=True),
                    "price": float(raw),
                    "unit":  "szt.",
                })
            except ValueError:
                pass
    return result


def _scrape_castorama(category_slug: str) -> list:
    urls = {
        "panele_podlogowe": "https://www.castorama.pl/category/panele-podlogowe/",
        "plytki_podlogowe": "https://www.castorama.pl/category/plytki-podlogowe/",
        "plytki_scienne":   "https://www.castorama.pl/category/plytki-scienne/",
        "farba_do_scian":   "https://www.castorama.pl/category/farby-i-lakiery/farby-do-scian/",
        "farba_sufitowa":   "https://www.castorama.pl/category/farby-i-lakiery/farby-do-sufitow/",
        "tapeta":           "https://www.castorama.pl/category/tapety/",
    }
    url = urls.get(category_slug)
    if not url:
        return []

    soup = _get(url)
    if not soup:
        return []

    products = _extract_json_ld(soup)
    if products:
        return products[:5]

    result = []
    for card in soup.select(".product-tile, .product-card, [data-sku]")[:5]:
        name_el  = card.select_one("h3, .product-tile__title, [data-product-name]")
        price_el = card.select_one(".price, .product-price, [data-price]")
        if name_el and price_el:
            raw = re.sub(r"[^\d,.]", "", price_el.get_text()).replace(",", ".")
            try:
                result.append({
                    "name":  name_el.get_text(strip=True),
                    "price": float(raw),
                    "unit":  "szt.",
                })
            except ValueError:
                pass
    return result


# ──────────────────────────────────────────────
# Cache + główne API
# ──────────────────────────────────────────────

def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with CACHE_FILE.open() as f:
                data = json.load(f)
            expires = datetime.fromisoformat(data.get("expires", "2000-01-01"))
            if datetime.now() < expires:
                return data.get("prices", {})
        except Exception:
            pass
    return {}


def _save_cache(prices: dict) -> None:
    try:
        with CACHE_FILE.open("w") as f:
            json.dump(
                {
                    "expires": (datetime.now() + timedelta(hours=CACHE_TTL_HOURS)).isoformat(),
                    "prices": prices,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as exc:
        logger.warning("Nie udało się zapisać cache: %s", exc)


def get_prices(category: str, refresh: bool = False) -> dict:
    """
    Zwraca dict: {"leroy_merlin": [...], "castorama": [...], "source": "live"|"cache"|"fallback"}.
    """
    cache = {} if refresh else _load_cache()

    if category in cache:
        return {**cache[category], "source": "cache"}

    # Próba scrappingu
    lm = _scrape_leroy_merlin(category)
    time.sleep(0.5)
    ca = _scrape_castorama(category)

    if lm or ca:
        entry = {
            "leroy_merlin": lm or FALLBACK.get(category, {}).get("leroy_merlin", []),
            "castorama":    ca or FALLBACK.get(category, {}).get("castorama", []),
        }
        cache[category] = entry
        _save_cache(cache)
        return {**entry, "source": "live"}

    # Fallback
    fb = FALLBACK.get(category, {"leroy_merlin": [], "castorama": []})
    return {**fb, "source": "fallback"}


def get_all_categories() -> dict:
    """Zwraca słownik kategoria → czytelna nazwa."""
    return {
        "panele_podlogowe":    "Panele podłogowe",
        "plytki_podlogowe":    "Płytki podłogowe",
        "plytki_scienne":      "Płytki ścienne",
        "farba_do_scian":      "Farba do ścian",
        "farba_sufitowa":      "Farba sufitowa",
        "tapeta":              "Tapeta",
        "klej_do_plytek":      "Klej do płytek",
        "fuga":                "Fuga",
        "listwy_przypodlogowe":"Listwy przypodłogowe",
        "wykładzina":          "Wykładzina",
    }
