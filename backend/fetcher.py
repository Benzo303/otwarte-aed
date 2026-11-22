"""Publiczne Overpass API oraz jawnie syntetyczny rejestr instytucjonalny."""
from __future__ import annotations

import argparse
import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache"
INSTITUTIONAL_PATH = ROOT / "data" / "rejestr_instytucjonalny_demo.csv"
ENDPOINTS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
AREAS = {
    "polska": {"name": "Polska", "admin_level": "2", "city": None, "teryt": None},
    "warszawa": {"name": "Warszawa", "admin_level": "6", "city": "Warszawa", "teryt": "1465011"},
    "zachodniopomorskie": {"name": "województwo zachodniopomorskie", "admin_level": "4", "city": None, "teryt": None},
}
log = logging.getLogger(__name__)


@dataclass
class FetchResult:
    elements: list[dict]
    metadata: dict


def overpass_query(area: str = "warszawa") -> str:
    config = AREAS[area]  # Wyłącznie klucze z zamkniętej listy, bez interpolacji danych użytkownika.
    if area == "polska":
        return '''[out:json][timeout:60];
area["ISO3166-1"="PL"]["admin_level"="2"]->.polska;
nwr["emergency"="defibrillator"](area.polska);
out meta center;'''
    return f'''[out:json][timeout:35];
area["ISO3166-1"="PL"]["admin_level"="2"]->.polska;
rel(area.polska)["boundary"="administrative"]["admin_level"="{config['admin_level']}"]["name"="{config['name']}"];
map_to_area->.obszar;
nwr["emergency"="defibrillator"](area.obszar);
out meta center;'''


def check_payload(payload: dict) -> None:
    if not isinstance(payload, dict) or "remark" in payload:
        raise ValueError("Niepełna odpowiedź Overpass lub błąd wykonania zapytania.")
    elements = payload.get("elements")
    if not isinstance(elements, list) or not elements:
        raise ValueError("Overpass nie zwrócił rekordów; nie zastępuję poprawnego cache pustą odpowiedzią.")
    if not all(isinstance(e, dict) and e.get("type") in ("node", "way", "relation") and
               isinstance(e.get("id"), int) and isinstance(e.get("tags"), dict) and
               e["tags"].get("emergency") == "defibrillator" for e in elements):
        raise ValueError("Niepoprawna struktura elementów Overpass.")


def load_cache(area: str, cache_dir: Path = CACHE_DIR, reason: str | None = None) -> FetchResult:
    path = Path(cache_dir) / f"osm_{area}.json"
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope["area"] != area or not envelope.get("retrieved_at"):
            raise ValueError("Cache ma niewłaściwy obszar lub brak czasu pobrania.")
        check_payload(envelope["payload"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Brak poprawnego cache dla {area}: {exc}") from exc
    metadata = {key: value for key, value in envelope.items() if key != "payload"}
    metadata.update(from_cache=True, fallback_reason=reason,
                    osm_base_timestamp=envelope["payload"].get("osm3s", {}).get("timestamp_osm_base"))
    return FetchResult(envelope["payload"]["elements"], metadata)


def fetch_osm(area: str = "warszawa", *, offline: bool = False, cache_dir: Path = CACHE_DIR,
              endpoints=ENDPOINTS, session=None) -> FetchResult:
    if area not in AREAS:
        raise ValueError(f"Obsługiwane obszary: {', '.join(AREAS)}")
    if offline:
        return load_cache(area, cache_dir, "offline_requested")
    client = session or requests.Session()
    errors = []
    try:
        for endpoint in endpoints:
            try:
                response = client.post(endpoint, data={"data": overpass_query(area)},
                                       headers={"User-Agent": "OtwarteAED-Hackathon/0.1 (public AED integration)"},
                                       timeout=(8, 75 if area == "polska" else 45))
                response.raise_for_status()
                payload = response.json()
                check_payload(payload)
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{endpoint}: {exc}")
                log.warning("Overpass: %s", errors[-1])
                continue
            envelope = {"area": area, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "endpoint": endpoint, "query": overpass_query(area),
                        "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
                        "payload": payload}
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            target = Path(cache_dir) / f"osm_{area}.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(envelope, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
            temporary.replace(target)
            return FetchResult(payload["elements"], {
                **{k: v for k, v in envelope.items() if k != "payload"},
                "from_cache": False, "fallback_reason": None,
                "osm_base_timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
            })
    finally:
        if session is None:
            client.close()
    return load_cache(area, cache_dir, "; ".join(errors))


def fetch_institutional(path: Path = INSTITUTIONAL_PATH) -> list[dict]:
    """Inne nazwy kolumn, średnik i polski przecinek dziesiętny. Dane DEMO, CC0."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        required = {"numer", "obiekt", "szerokosc_geo", "dlugosc_geo", "tryb_dostepu", "demo"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Niepoprawne kolumny rejestru instytucjonalnego.")
        rows = list(reader)
    if any(row.get("demo") != "TAK" for row in rows):
        raise ValueError("Przykładowy rejestr musi być oznaczony DEMO.")
    return rows


def load_city_contexts(cache_dir: Path = CACHE_DIR) -> dict:
    """Przynależność punktów do miast potwierdzona osobnymi zapytaniami administracyjnymi.

    Nie wyznaczamy miasta z prostokąta ani z pobliskiego adresu. Normalizator
    używa kontekstu tylko dla tego samego obiektu i niezmienionej pozycji.
    """
    contexts = {}
    for area, config in AREAS.items():
        if not config.get("city"):
            continue
        try:
            cached = load_cache(area, cache_dir)
        except RuntimeError:
            continue
        for element in cached.elements:
            coords = element if element["type"] == "node" else element.get("center", {})
            contexts[(element["type"], element["id"])] = {
                "city": config["city"], "teryt": config.get("teryt"),
                "lat": coords.get("lat"), "lon": coords.get("lon"),
                "area": area, "retrieved_at": cached.metadata["retrieved_at"],
            }
    return contexts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", choices=AREAS, default="warszawa")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    result = fetch_osm(args.area, offline=args.offline)
    print(json.dumps({"records": len(result.elements), **result.metadata}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
