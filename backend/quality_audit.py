"""Powtarzalny audyt surowych danych instytucji, bez zaliczania uzupełnień OSM."""
import json
from functools import lru_cache
from pathlib import Path
from .availability import valid_hours
from .city_search import contains
from .danegov_client import CACHE_PATH


@lru_cache(maxsize=1)
def poland():
    path = Path(__file__).parent / "data/cache/poland_boundary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def in_poland(lat, lon):
    boundary = poland()
    return contains(boundary, lat, lon) if boundary else False


def audit_cache():
    try:
        envelope = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"datasets": [], "ranking": [], "warning": "Brak cache instytucji. Uruchom synchronizację."}
    datasets = []
    for ds in envelope.get("datasets", []):
        rows = ds.get("records", [])
        resources = ds.get("resources", [])
        gps = [r for r in rows if in_poland(r.get("lat"), r.get("lon"))]
        n = len(rows)
        address = sum(bool(r.get("ulica_numer") and r.get("miejscowosc") and r.get("kod_pocztowy")) for r in gps)
        hours = sum(bool(r.get("godziny_otwarcia_osm") and valid_hours(r["godziny_otwarcia_osm"])) for r in gps)
        description = sum(bool(r.get("opis_lokalizacji_wewnatrz")) for r in gps)
        good_resources = [r for r in resources if r.get("status") == "integrated" and r.get("records_count")]
        best = max(good_resources, key=lambda r:r["records_count"]/(r["records_count"]+len(r.get("rejected_records", []))), default=None)
        denominator = n + (len(best.get("rejected_records", [])) if best else 0)
        breakdown = {"format": 20 if good_resources else 0,
                     "gps": round(30*len(gps)/max(1,denominator), 1),
                     "address": round(20*address/max(1,n), 1),
                     "opening_hours": round(15*hours/max(1,n), 1),
                     "location_description": round(15*description/max(1,n), 1)}
        score = round(sum(breakdown.values()), 1)
        grade = next(g for threshold,g in [(90,"A"),(80,"B"),(65,"C"),(50,"D"),(35,"E"),(0,"F")] if score>=threshold)
        errors = []
        if not good_resources: errors.append("Zasoby nie dostarczyły tabeli z lokalizacjami AED; sprawdź HTML zamiast pliku lub format.")
        if len(gps) < denominator: errors.append(f"GPS: {denominator-len(gps)} pozycji nie ma prawidłowych współrzędnych w granicach Polski.")
        if address < n: errors.append(f"Adres: uzupełnij {n-address} rekordów (ulica, miejscowość, kod pocztowy).")
        if hours < n: errors.append(f"Godziny: brak poprawnego harmonogramu w {n-hours} rekordach.")
        if description < n: errors.append(f"Lokalizacja wewnątrz: brak opisu piętra/holu w {n-description} rekordach.")
        for resource in resources:
            if resource.get("status") in ("error", "no_coordinates"):
                errors.append(f"Zasób {resource['id']} ({resource.get('format')}): {resource.get('error') or 'nie rozpoznano GPS/układu odniesienia' }"[:350])
        datasets.append({"dataset_id": ds["id"], "title": ds["title"], "institution": ds.get("institution_title"),
                         "url": ds.get("url"), "records_count": n, "valid_gps_points": len(gps),
                         "score": score, "grade": grade, "breakdown": breakdown, "errors": errors})
    ranking = []
    for institution in sorted({d["institution"] or "Nieustalona instytucja" for d in datasets}):
        members = [d for d in datasets if (d["institution"] or "Nieustalona instytucja") == institution]
        score = round(sum(d["score"]*max(1,d["records_count"]) for d in members)/sum(max(1,d["records_count"]) for d in members),1)
        ranking.append({"institution": institution, "score": score,
                        "grade": next(g for t,g in [(90,"A"),(80,"B"),(65,"C"),(50,"D"),(35,"E"),(0,"F")] if score>=t),
                        "valid_points": sum(d["valid_gps_points"] for d in members), "datasets": members,
                        "errors": [f"{d['dataset_id']}: {e}" for d in members for e in d["errors"]]})
    ranking.sort(key=lambda r:(-r["score"],-r["valid_points"],r["institution"]))
    return {"retrieved_at": envelope.get("retrieved_at"), "datasets": datasets, "ranking": ranking,
            "methodology": "100 pkt: maszynowy format 20, GPS w granicach Polski 30, adres 20, godziny 15, opis miejsca 15. Ocena surowych źródeł, przed wzbogaceniem OSM.",
            "country_boundary_available": poland() is not None, "boundary_source": (poland() or {}).get("url")}
