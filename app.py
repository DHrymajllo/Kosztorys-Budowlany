"""
Kosztorys Budowlany — serwer Flask.
Uruchom: python app.py
"""

from __future__ import annotations
import logging
from flask import Flask, render_template, request, jsonify
from scraper import get_prices, get_all_categories, FALLBACK
from calculator import Room, calculate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = Flask(__name__)


# ──────────────────────────────────────────────
# Strona główna
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────────────────────────
# API: kategorie
# ──────────────────────────────────────────────

@app.route("/api/categories")
def api_categories():
    return jsonify(get_all_categories())


# ──────────────────────────────────────────────
# API: ceny dla jednej kategorii
# ──────────────────────────────────────────────

@app.route("/api/prices/<category>")
def api_prices(category: str):
    refresh = request.args.get("refresh", "0") == "1"
    data = get_prices(category, refresh=refresh)
    return jsonify(data)


# ──────────────────────────────────────────────
# API: wszystkie ceny naraz (na start UI)
# ──────────────────────────────────────────────

@app.route("/api/prices/all")
def api_prices_all():
    result = {}
    for cat in get_all_categories():
        result[cat] = FALLBACK.get(cat, {"leroy_merlin": [], "castorama": []})
        result[cat]["source"] = "fallback"
    return jsonify(result)


# ──────────────────────────────────────────────
# API: oblicz kosztorys
# ──────────────────────────────────────────────

@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    data = request.get_json(force=True)
    if not data or "rooms" not in data:
        return jsonify({"error": "Brak danych pomieszczeń"}), 400

    rooms: list[Room] = []
    for rd in data["rooms"]:
        try:
            width  = float(rd["width"])
            length = float(rd["length"])
            height = float(rd.get("height", 2.6))
            if width <= 0 or length <= 0:
                return jsonify({"error": "Szerokość i długość muszą być większe od 0."}), 400
            if height < 1.5:
                return jsonify({"error": "Wysokość nie może być mniejsza niż 1.5 m."}), 400
            room = Room(
                name    = str(rd.get("name", "Pomieszczenie"))[:60],
                width   = width,
                length  = length,
                height  = height,
                windows = max(0, int(rd.get("windows", 1))),
                doors   = max(0, int(rd.get("doors", 1))),
                floor_material   = rd.get("floor_material"),
                wall_material    = rd.get("wall_material"),
                ceiling_material = rd.get("ceiling_material"),
            )
            rooms.append(room)
        except (KeyError, ValueError, TypeError) as exc:
            return jsonify({"error": f"Nieprawidłowe dane pomieszczenia: {exc}"}), 400

    result = calculate(rooms)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
