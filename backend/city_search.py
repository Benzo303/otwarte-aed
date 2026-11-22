"""Wyszukiwanie AED w granicach miejscowości, niezależnie od tagu addr:city.

Jedno jawne wyszukanie użytkownika, trwały cache i maksymalnie 1 żądanie/s.
Brak autouzupełniania i masowego geokodowania punktów AED.
https://operations.osmfoundation.org/policies/nominatim/
"""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timezone

import requests

from .runtime_paths import cache_dir
CACHE_PATH = cache_dir() / "city_boundaries.json"
DEFAULT_URL = "https://nominatim.openstreetmap.org/search"


def city_key(name):
    name = str(name or "").strip().casefold().replace("ł", "l")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", name)


class CitySearchError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def _on_segment(x, y, a, b):
    cross = (x-a[0])*(b[1]-a[1]) - (y-a[1])*(b[0]-a[0])
    return (abs(cross) <= 1e-12 and min(a[0],b[0])-1e-10 <= x <= max(a[0],b[0])+1e-10
            and min(a[1],b[1])-1e-10 <= y <= max(a[1],b[1])+1e-10)


def _ring_state(x, y, ring):
    """-1 poza, 0 na granicy, 1 wewnątrz; współrzędne GeoJSON lon/lat."""
    inside = False
    for a, b in zip(ring, ring[1:]):
        if _on_segment(x, y, a, b):
            return 0
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return 1 if inside else -1


def contains(city, lat, lon):
    if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in (lat, lon)):
        return False
    south, north, west, east = city["bounds"]
    if not (south <= lat <= north and west <= lon <= east):
        return False
    geometry = city["geometry"]
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return any(_ring_state(lon, lat, rings[0]) >= 0 and
               not any(_ring_state(lon, lat, hole) == 1 for hole in rings[1:]) for rings in polygons)


def select_city(document, query):
    """Nie zgadujemy promienia miasta ani nie wybieramy losowo spośród imienników."""
    if not isinstance(document, list):
        raise CitySearchError("Nieprawidłowa odpowiedź wyszukiwania granic.", 503)
    requested = city_key(query.split(",", 1)[0])
    candidates = {}
    for item in document:
        if not isinstance(item, dict) or (item.get("address") or {}).get("country_code") != "pl":
            continue
        if item.get("addresstype") not in ("city", "town", "village", "municipality", "hamlet"):
            continue
        names = {city_key(item.get("name"))}
        for value in item.get("namedetails", {}).values():
            names.update(city_key(n) for n in str(value).split(";"))
        if requested not in names:
            continue
        geometry = item.get("geojson", {})
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        polygons = [geometry.get("coordinates")] if geometry["type"] == "Polygon" else geometry.get("coordinates")
        if not isinstance(polygons, list) or not polygons:
            continue
        points = []
        valid = True
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                valid = False; break
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    valid = False; break
                for point in ring:
                    if (not isinstance(point, list) or len(point) != 2 or
                            not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in point) or
                            not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
                        valid = False; break
                    points.append(point)
        if not valid or not points or len(points) > 200000:
            continue
        bounds = [min(p[1] for p in points), max(p[1] for p in points),
                  min(p[0] for p in points), max(p[0] for p in points)]
        identifier = f"{item.get('osm_type')}/{item.get('osm_id')}"
        candidates[identifier] = {"name": item["name"], "display_name": item["display_name"],
                                  "place_type": item["addresstype"],
                                  "osm_id": identifier, "bounds": bounds, "geometry": geometry,
                                  "source": "OpenStreetMap / Nominatim", "license": "ODbL-1.0",
                                  "url": f"https://www.openstreetmap.org/{identifier}",
                                  "retrieved_at": datetime.now(timezone.utc).isoformat()}
    # Pole służy szukaniu miasta: Łódź-miasto ma pierwszeństwo przed wsią Łódź.
    for place_type in ("city", "town"):
        preferred = {k: c for k, c in candidates.items() if c["place_type"] == place_type}
        if preferred:
            candidates = preferred
            break
    if len(candidates) > 1:
        names = "; ".join(c["display_name"] for c in list(candidates.values())[:4])
        raise CitySearchError(f"Nazwa jest niejednoznaczna. Dopisz powiat lub województwo: {names}")
    if not candidates:
        raise CitySearchError("Nie znaleziono jednoznacznej granicy tej miejscowości w Polsce. Sprawdź nazwę lub dopisz powiat/województwo.", 404)
    return next(iter(candidates.values()))


def public_city(city):
    return {k: v for k, v in city.items() if k != "geometry"} if city else None


class CityResolver:
    _network_lock = threading.Lock()
    _last_request = 0.0

    def __init__(self, *, cache_path=CACHE_PATH, session=None, allow_network=True):
        self.cache_path = Path(cache_path)
        self.session = session or requests.Session()
        self.allow_network = allow_network
        self.url = os.getenv("AED_GEOCODER_URL", DEFAULT_URL)
        self._negative = {}

    def _read(self):
        try:
            document = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return document.get("cities", {}) if document.get("version") == 1 else {}
        except (ValueError, OSError, TypeError, AttributeError):
            return {}

    def _save(self, query_key, city):
        entries = self._read()
        entries[query_key] = city
        # Pisownia oficjalna i bez znaków diakrytycznych korzystają z tej samej geometrii.
        if "," not in query_key:
            entries[city_key(city["name"])] = city
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.cache_path.parent, suffix=".tmp", delete=False) as stream:
            path = Path(stream.name)
            stream.write(json.dumps({"version": 1, "cities": entries}, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        path.replace(self.cache_path)

    def resolve(self, query, *, allow_lookup=True):
        query = query.strip()
        query_key = city_key(query)
        if not query_key:
            return None
        cached = self._read().get(query_key)
        if cached and cached.get("geometry", {}).get("type") in ("Polygon", "MultiPolygon"):
            return {**cached, "from_cache": True}
        if not self.allow_network or not allow_lookup:
            return None
        if len(query_key) < 2:
            raise CitySearchError("Wpisz pełną nazwę miejscowości i zatwierdź wyszukiwanie.")
        with self._network_lock:
            cached = self._read().get(query_key)
            if cached:
                return {**cached, "from_cache": True}
            failed = self._negative.get(query_key)
            if failed and time.monotonic() - failed[0] < 600:
                raise failed[1]
            delay = 1.05 - (time.monotonic() - CityResolver._last_request)
            if delay > 0:
                time.sleep(delay)
            CityResolver._last_request = time.monotonic()
            try:
                response = self.session.get(self.url, params={"q": query, "countrycodes": "pl", "format": "jsonv2",
                    "polygon_geojson": 1, "polygon_threshold": 0.00005, "addressdetails": 1,
                    "namedetails": 1, "limit": 10, "featureType": "settlement"},
                    headers={"User-Agent": "OtwarteAED/0.3 (local hackathon AED map)", "Accept-Language": "pl"}, timeout=(5, 12))
                response.raise_for_status()
                if len(response.content) > 10 * 1024 * 1024:
                    raise CitySearchError("Odpowiedź z granicą miasta jest zbyt duża.", 503)
                city = select_city(response.json(), query)
            except (requests.RequestException, ValueError) as exc:
                error = exc if isinstance(exc, CitySearchError) else CitySearchError("Nie udało się pobrać granicy miejscowości. Spróbuj ponownie lub wyczyść filtr miasta.", 503)
                self._negative[query_key] = (time.monotonic(), error)
                if error is exc:
                    raise
                raise error from exc
            self._save(query_key, city)
            return {**city, "from_cache": False}
