"""
Kalkulator materiałów budowlanych.

Dla każdego pomieszczenia oblicza:
  - ilość materiału potrzebnego na podłogę, ściany, sufit
  - koszt wybranych produktów
  - naddatek procentowy (odpad)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math


WASTE = {
    "panele_podlogowe":    0.10,   # 10 %
    "plytki_podlogowe":    0.10,
    "plytki_scienne":      0.10,
    "farba_do_scian":      0.05,
    "farba_sufitowa":      0.05,
    "tapeta":              0.10,
    "klej_do_plytek":      0.05,
    "fuga":                0.05,
    "listwy_przypodlogowe":0.05,
    "wykładzina":          0.10,
}

# Typowe okno i drzwi (m²) odejmowane ze ścian
WINDOW_AREA = 1.5   # m²
DOOR_AREA   = 1.9   # m²

# Pokrycie farby na litr, 2 warstwy
DEFAULT_PAINT_COVERAGE = 10  # m²/L per warstwa => 5 m²/L for 2 layers


@dataclass
class Room:
    name: str
    width: float          # m
    length: float         # m
    height: float         # m
    windows: int = 1
    doors: int    = 1

    # Wybrany materiał na podłogę / ściany / sufit:
    # {"category": str, "product": dict}
    floor_material:   Optional[dict] = None
    wall_material:    Optional[dict] = None
    ceiling_material: Optional[dict] = None

    @property
    def floor_area(self) -> float:
        return round(self.width * self.length, 2)

    @property
    def ceiling_area(self) -> float:
        return self.floor_area

    @property
    def wall_area(self) -> float:
        perimeter = 2 * (self.width + self.length)
        gross = perimeter * self.height
        deductions = self.windows * WINDOW_AREA + self.doors * DOOR_AREA
        return round(max(gross - deductions, 0), 2)

    @property
    def perimeter(self) -> float:
        return round(2 * (self.width + self.length), 2)


# ──────────────────────────────────────────────
# Obliczenia ilości materiału
# ──────────────────────────────────────────────

def _qty_with_waste(area: float, category: str) -> float:
    return round(area * (1 + WASTE.get(category, 0.10)), 2)


def _paint_liters(area_m2: float, product: dict) -> float:
    """Zwraca litry farby potrzebne na 2 warstwy."""
    cov = product.get("coverage_m2_per_l", DEFAULT_PAINT_COVERAGE)
    layers = 2
    total_m2 = area_m2 * (1 + WASTE.get("farba_do_scian", 0.05))
    liters = total_m2 * layers / cov
    return round(liters, 2)


def _paint_packs(liters: float, product: dict, pack_volume: float) -> float:
    """Zwraca liczbę opakowań (zaokrąglona w górę)."""
    return math.ceil(liters / pack_volume)


def _tapeta_rolls(area_m2: float) -> int:
    """Rolka 0,53×10 m = 5,3 m²; flizelinowa 1,06×10 m = 10,6 m². Zakładamy standard 5,3 m²."""
    roll_area = 5.3
    return math.ceil(area_m2 * (1 + WASTE["tapeta"]) / roll_area)


def _listwy_pieces(perimeter: float) -> int:
    strip_len = 2.4  # m
    return math.ceil(perimeter * (1 + WASTE["listwy_przypodlogowe"]) / strip_len)


def _tiles_area(area_m2: float, category: str) -> float:
    return _qty_with_waste(area_m2, category)


def _klej_bags(area_m2: float, product: dict) -> int:
    coverage = product.get("coverage_m2_per_kg", 0.20)  # m²/kg
    kg_needed = area_m2 / coverage * (1 + WASTE["klej_do_plytek"])
    bag_kg = 25
    return math.ceil(kg_needed / bag_kg)


def _fuga_packs(area_m2: float, product: dict) -> int:
    coverage = product.get("coverage_m2_per_kg", 0.30)
    kg_needed = area_m2 / coverage * (1 + WASTE["fuga"])
    pack_kg = 2
    return math.ceil(kg_needed / pack_kg)


# ──────────────────────────────────────────────
# Kalkulacja kosztu jednego materiału
# ──────────────────────────────────────────────

@dataclass
class MaterialLine:
    description: str
    qty: float
    unit: str
    unit_price: float
    total: float


def _calc_floor(room: Room) -> list[MaterialLine]:
    mat = room.floor_material
    if not mat:
        return []
    cat  = mat["category"]
    prod = mat["product"]
    lines: list[MaterialLine] = []

    if cat == "panele_podlogowe":
        qty = _qty_with_waste(room.floor_area, cat)
        lines.append(MaterialLine(
            f"Panele: {prod['name']}",
            qty, "m²", prod["price"],
            round(qty * prod["price"], 2),
        ))
        # Listwy (jeśli panele — zawsze potrzebne)
        lp = _listwy_pieces(room.perimeter)
        lines.append(MaterialLine(
            "Listwy przypodłogowe (MDF biała 2,4 m)",
            lp, "szt.", 8.90, round(lp * 8.90, 2),
        ))
    elif cat in ("plytki_podlogowe", "wykładzina"):
        qty = _qty_with_waste(room.floor_area, cat)
        unit = "m²" if cat == "plytki_podlogowe" else "mb"
        lines.append(MaterialLine(
            f"{prod['name']}",
            qty, unit, prod["price"],
            round(qty * prod["price"], 2),
        ))
        if cat == "plytki_podlogowe":
            # klej
            klej_price = 24.90
            klej_bags  = _klej_bags(room.floor_area, {"coverage_m2_per_kg": 0.20})
            lines.append(MaterialLine(
                "Klej do płytek (standard 25 kg)",
                klej_bags, "worek", klej_price,
                round(klej_bags * klej_price, 2),
            ))
            # fuga
            fuga_price = 19.90
            fuga_packs = _fuga_packs(room.floor_area, {"coverage_m2_per_kg": 0.30})
            lines.append(MaterialLine(
                "Fuga (2 kg)",
                fuga_packs, "opak.", fuga_price,
                round(fuga_packs * fuga_price, 2),
            ))
    return lines


def _calc_walls(room: Room) -> list[MaterialLine]:
    mat = room.wall_material
    if not mat:
        return []
    cat  = mat["category"]
    prod = mat["product"]
    area = room.wall_area
    lines: list[MaterialLine] = []

    if cat == "farba_do_scian":
        liters    = _paint_liters(area, prod)
        pack_vol  = _infer_pack_volume(prod["name"])
        packs     = _paint_packs(liters, prod, pack_vol)
        lines.append(MaterialLine(
            f"Farba ścienna: {prod['name']}",
            packs, "opak.", prod["price"],
            round(packs * prod["price"], 2),
        ))
    elif cat == "tapeta":
        rolls = _tapeta_rolls(area)
        lines.append(MaterialLine(
            f"Tapeta: {prod['name']}",
            rolls, "rolka", prod["price"],
            round(rolls * prod["price"], 2),
        ))
    elif cat == "plytki_scienne":
        qty = _tiles_area(area, cat)
        lines.append(MaterialLine(
            f"Płytki ścienne: {prod['name']}",
            qty, "m²", prod["price"],
            round(qty * prod["price"], 2),
        ))
        klej_bags = _klej_bags(area, {"coverage_m2_per_kg": 0.22})
        lines.append(MaterialLine(
            "Klej do płytek ściennych (25 kg)",
            klej_bags, "worek", 24.90,
            round(klej_bags * 24.90, 2),
        ))
        fuga_packs = _fuga_packs(area, {"coverage_m2_per_kg": 0.30})
        lines.append(MaterialLine(
            "Fuga ścienna (2 kg)",
            fuga_packs, "opak.", 19.90,
            round(fuga_packs * 19.90, 2),
        ))
    return lines


def _calc_ceiling(room: Room) -> list[MaterialLine]:
    mat = room.ceiling_material
    if not mat:
        return []
    cat  = mat["category"]
    prod = mat["product"]
    area = room.ceiling_area
    lines: list[MaterialLine] = []

    if cat == "farba_sufitowa":
        liters    = _paint_liters(area, prod)
        pack_vol  = _infer_pack_volume(prod["name"])
        packs     = _paint_packs(liters, prod, pack_vol)
        lines.append(MaterialLine(
            f"Farba sufitowa: {prod['name']}",
            packs, "opak.", prod["price"],
            round(packs * prod["price"], 2),
        ))
    elif cat == "farba_do_scian":
        liters    = _paint_liters(area, prod)
        pack_vol  = _infer_pack_volume(prod["name"])
        packs     = _paint_packs(liters, prod, pack_vol)
        lines.append(MaterialLine(
            f"Farba sufitowa: {prod['name']}",
            packs, "opak.", prod["price"],
            round(packs * prod["price"], 2),
        ))
    return lines


def _infer_pack_volume(name: str) -> float:
    """Wyciąga pojemność opakowania z nazwy, np. '10 L' → 10.0"""
    m = __import__("re").search(r"([\d,]+)\s*[Ll]", name)
    if m:
        return float(m.group(1).replace(",", "."))
    return 5.0


# ──────────────────────────────────────────────
# Główna funkcja
# ──────────────────────────────────────────────

@dataclass
class RoomResult:
    room_name: str
    floor_lines:   list[MaterialLine] = field(default_factory=list)
    wall_lines:    list[MaterialLine] = field(default_factory=list)
    ceiling_lines: list[MaterialLine] = field(default_factory=list)
    floor_area:    float = 0.0
    wall_area:     float = 0.0
    ceiling_area:  float = 0.0

    @property
    def total(self) -> float:
        return round(
            sum(l.total for l in self.floor_lines + self.wall_lines + self.ceiling_lines),
            2,
        )


def calculate(rooms: list[Room]) -> dict:
    results: list[RoomResult] = []
    grand_total = 0.0

    for room in rooms:
        rr = RoomResult(
            room_name    = room.name,
            floor_lines  = _calc_floor(room),
            wall_lines   = _calc_walls(room),
            ceiling_lines= _calc_ceiling(room),
            floor_area   = room.floor_area,
            wall_area    = room.wall_area,
            ceiling_area = room.ceiling_area,
        )
        grand_total += rr.total
        results.append(rr)

    return {
        "rooms": [_room_to_dict(r) for r in results],
        "grand_total": round(grand_total, 2),
    }


def _room_to_dict(rr: RoomResult) -> dict:
    def lines_to_list(lines: list[MaterialLine]) -> list[dict]:
        return [
            {
                "description": l.description,
                "qty":         l.qty,
                "unit":        l.unit,
                "unit_price":  l.unit_price,
                "total":       l.total,
            }
            for l in lines
        ]

    return {
        "room_name":     rr.room_name,
        "floor_area":    rr.floor_area,
        "wall_area":     rr.wall_area,
        "ceiling_area":  rr.ceiling_area,
        "floor_lines":   lines_to_list(rr.floor_lines),
        "wall_lines":    lines_to_list(rr.wall_lines),
        "ceiling_lines": lines_to_list(rr.ceiling_lines),
        "total":         rr.total,
    }
