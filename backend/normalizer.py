"""Mapowanie źródeł, Haversine <25 m, pochodzenie i jawne błędy jakości danych."""
from __future__ import annotations

import copy
import math
import re
from datetime import date, datetime
from urllib.parse import urlparse
from itertools import product

from .availability import WARSAW, valid_hours
from .schema import field_names, load_schema


def clean(value):
    if isinstance(value, str):
        return value.strip() or None
    return value


def decimal(value):
    if isinstance(value, bool):
        raise ValueError("Współrzędna nie może być wartością logiczną.")
    value = float(value.replace(",", ".") if isinstance(value, str) else value)
    if not math.isfinite(value):
        raise ValueError("Współrzędna musi być skończoną liczbą.")
    return value


def canonical_values(row):
    result = {key: clean(row.get(key)) for key in field_names()}
    for key in ("lat", "lon"):
        if result[key] is not None:
            try:
                result[key] = decimal(result[key])
            except (TypeError, ValueError):
                pass  # Walidator wskaże błąd bez utraty oryginalnej wartości.
    for f in load_schema()[0]:
        value = result[f.name]
        if f.dtype.startswith("data ") and isinstance(value, (datetime, date)):
            if isinstance(value, datetime) and value.time() != datetime.min.time():
                result[f.name] = value.isoformat()  # Czas nie przejdzie walidacji daty.
            else:
                result[f.name] = value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return result


def validate_record(row, today=None) -> list[dict]:
    """Zbiera wszystkie błędy; braków OSM nie uzupełnia wymyślonym adresem lub statusem."""
    today = today or datetime.now(WARSAW).date()
    fields, enums = load_schema()
    errors = []

    def error(field, code, message):
        errors.append({"field": field, "code": code, "message": message})

    limits = {"id_aed": 100, "nazwa_obiektu": 200, "ulica_numer": 200, "miejscowosc": 100,
              "opis_lokalizacji_wewnatrz": 1000, "model_aed": 150, "dysponent_nazwa": 200}
    for field in fields:
        value = row.get(field.name)
        if value is None or value == "":
            if field.required:
                error(field.name, "required", "Pole jest wymagane przez wzorzec XLSX.")
            continue
        if field.name in ("lat", "lon"):
            bound = 90 if field.name == "lat" else 180
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -bound <= value <= bound:
                error(field.name, "coordinate", f"Wymagana liczba od {-bound} do {bound}.")
        elif field.dtype.startswith("data "):
            try:
                if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                    raise ValueError
                parsed = date.fromisoformat(value)
                if parsed < date(1900, 1, 1) or (field.name == "data_aktualizacji" and parsed > today):
                    raise ValueError
            except ValueError:
                error(field.name, "date", "Wymagana poprawna data YYYY-MM-DD; aktualizacja nie może być przyszła.")
        elif not isinstance(value, str):
            error(field.name, "text", "Wymagany tekst. Zachowaj zera wiodące kodów.")
        else:
            if len(value) > limits.get(field.name, 2000):
                error(field.name, "length", "Przekroczona długość pola.")
            if field.name in enums and value not in enums[field.name]:
                error(field.name, "enum", f"Dozwolone: {', '.join(enums[field.name])}.")
    for key, pattern in {"id_aed": r"[A-Za-z0-9_.:-]{3,100}", "kod_pocztowy": r"[0-9]{2}-[0-9]{3}", "kod_teryt": r"[0-9]{7}"}.items():
        value = row.get(key)
        if value is not None and (not isinstance(value, str) or not re.fullmatch(pattern, value)):
            error(key, "format", "Niepoprawny format identyfikatora lub kodu.")
    contact = row.get("dysponent_kontakt")
    if isinstance(contact, str) and not (re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact) or re.fullmatch(r"\+[1-9][0-9]{7,14}", contact)):
        error("dysponent_kontakt", "contact", "Wymagany e-mail lub telefon w formacie E.164.")
    url = row.get("zrodlo_referencyjne")
    if isinstance(url, str):
        try:
            for part in url.split(" | "):
                if re.fullmatch(r"dane\.gov\.pl \[ID: [0-9]+ - [^\[\]\r\n]+\]", part):
                    continue
                parsed = urlparse(part)
                if parsed.scheme not in ("http", "https") or not parsed.netloc or any(c.isspace() for c in part):
                    raise ValueError
        except ValueError:
            error("zrodlo_referencyjne", "url", "Wymagany URL http/https lub dane.gov.pl [ID: numer - instytucja]; źródła oddzielaj ' | '.")
    access, hours, key = (row.get(k) for k in ("dostepnosc_typ", "godziny_otwarcia_osm", "wymagany_klucz_lub_kod"))
    if hours and not valid_hours(hours):
        error("godziny_otwarcia_osm", "opening_hours", "Niepoprawna lub nieobsługiwana składnia OSM opening_hours.")
    if access == "24_7" and (hours != "24/7" or key != "NIE"):
        error("dostepnosc_typ", "consistency", "24_7 wymaga 24/7 i klucza NIE.")
    if access in ("godziny_pracy", "na_klucz_lub_kod"):
        if not hours or hours == "off":
            error("godziny_otwarcia_osm", "consistency", "Ograniczony dostęp wymaga harmonogramu.")
        if key != ("TAK" if access == "na_klucz_lub_kod" else "NIE"):
            error("wymagany_klucz_lub_kod", "consistency", "Wymaganie klucza jest sprzeczne z typem dostępu.")
    if access == "niedostepny" and hours != "off":
        error("godziny_otwarcia_osm", "consistency", "niedostepny wymaga off.")
    if row.get("status_techniczny") == "serwis" and access != "niedostepny":
        error("status_techniczny", "consistency", "serwis wymaga niedostepny.")
    return errors


def normalize_osm(element: dict, area_config: dict) -> dict:
    tags = element.get("tags", {})
    coords = element if element.get("type") == "node" else element.get("center", {})
    ref = f"https://www.openstreetmap.org/{element['type']}/{element['id']}"
    row = dict.fromkeys(field_names())
    hours = clean(tags.get("opening_hours"))
    access = clean(tags.get("access"))
    locked = tags.get("locked") == "yes"
    unavailable = access in ("no", "private") or tags.get("defibrillator:status") in ("broken", "out_of_order", "maintenance")
    explicitly_public = access in ("yes", "public") or tags.get("locked") == "no"
    row.update(
        id_aed=f"OSM-{element['type']}-{element['id']}",
        nazwa_obiektu=clean(tags.get("name")) or clean(tags.get("defibrillator:location")),
        ulica_numer=clean(" ".join(str(tags.get(k, "")) for k in ("addr:street", "addr:housenumber"))),
        kod_pocztowy=clean(tags.get("addr:postcode")),
        miejscowosc=clean(tags.get("addr:city")) or area_config.get("city"),
        kod_teryt=area_config.get("teryt"), lat=coords.get("lat"), lon=coords.get("lon"),
        opis_lokalizacji_wewnatrz=clean(tags.get("defibrillator:location")) or clean(tags.get("description")),
        dostepnosc_typ="niedostepny" if unavailable else "na_klucz_lub_kod" if locked else
                       ("24_7" if hours == "24/7" else "godziny_pracy" if hours else None) if explicitly_public else None,
        godziny_otwarcia_osm="off" if unavailable else hours,
        wymagany_klucz_lub_kod="TAK" if locked else "NIE" if explicitly_public else None,
        dostepnosc_niepelnosprawni={"yes": "tak", "no": "nie"}.get(tags.get("wheelchair"), "niezweryfikowano"),
        model_aed=clean(tags.get("defibrillator:model")) or clean(tags.get("model")),
        status_techniczny="serwis" if tags.get("defibrillator:status") in ("broken", "out_of_order", "maintenance") else "niezweryfikowany",
        data_waznosci_elektrod=clean(tags.get("defibrillator:pads:expiry_date")),
        data_waznosci_baterii=clean(tags.get("defibrillator:battery:expiry_date")),
        # Ostatnia edycja OSM nie jest potwierdzeniem sprawności przez dysponenta.
        data_aktualizacji=clean(tags.get("check_date:defibrillator")) or clean(tags.get("check_date")),
        dysponent_nazwa=clean(tags.get("operator")),
        dysponent_kontakt=clean(tags.get("operator:email")) or clean(tags.get("contact:email")) or clean(tags.get("operator:phone")),
        zrodlo_referencyjne=ref,
    )
    return attach_source(canonical_values(row), "OpenStreetMap", ref, "ODbL-1.0", False,
                         {"osm_edit_timestamp": element.get("timestamp"), "raw_tags": tags,
                          **({"administrative_context": area_config["administrative_context"]}
                             if area_config.get("administrative_context") else {})})


INSTITUTIONAL_MAP = dict(zip(
    ("numer", "obiekt", "adres", "poczta", "miasto", "teryt", "szerokosc_geo", "dlugosc_geo", "umiejscowienie", "tryb_dostepu", "harmonogram", "klucz", "bez_barier", "producent_model", "stan", "elektrody_do", "bateria_do", "potwierdzono", "jednostka", "kontakt", "url"),
    ("id_aed", "nazwa_obiektu", "ulica_numer", "kod_pocztowy", "miejscowosc", "kod_teryt", "lat", "lon", "opis_lokalizacji_wewnatrz", "dostepnosc_typ", "godziny_otwarcia_osm", "wymagany_klucz_lub_kod", "dostepnosc_niepelnosprawni", "model_aed", "status_techniczny", "data_waznosci_elektrod", "data_waznosci_baterii", "data_aktualizacji", "dysponent_nazwa", "dysponent_kontakt", "zrodlo_referencyjne")))


def normalize_institutional(raw):
    row = {target: raw.get(source) for source, target in INSTITUTIONAL_MAP.items()}
    row["dostepnosc_typ"] = {"calodobowo": "24_7", "w_godzinach": "godziny_pracy", "na_klucz": "na_klucz_lub_kod", "brak_dostepu": "niedostepny"}.get(raw.get("tryb_dostepu"), raw.get("tryb_dostepu"))
    row["status_techniczny"] = {"OK": "sprawny", "NAPRAWA": "serwis", "BRAK_WERYFIKACJI": "niezweryfikowany"}.get(raw.get("stan"), raw.get("stan"))
    row = canonical_values(row)
    return attach_source(row, "Rejestr instytucjonalny DEMO", row["zrodlo_referencyjne"], "CC0-1.0", True)


def attach_source(row, name, url, license_id=None, demo=False, details=None):
    return {**row, "sources": [{"name": name, "url": url, "license": license_id,
                                "source_record_id": row["id_aed"], **(details or {})}],
            "is_demo": demo, "merged_ids": [row["id_aed"]], "conflicts": {}}


def haversine(lat1, lon1, lat2, lon2):
    """Odległość w metrach na kuli o promieniu średnim 6 371 008,8 m."""
    a1, a2 = math.radians(lat1), math.radians(lat2)
    da, dl = a2 - a1, math.radians(lon2 - lon1)
    a = math.sin(da / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dl / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def usable_coordinates(row):
    return all(isinstance(row.get(k), (int, float)) and not isinstance(row[k], bool) and
               math.isfinite(row[k]) and -bound <= row[k] <= bound
               for k, bound in (("lat", 90), ("lon", 180)))


def confidence_score(row):
    """Kompletność, nie prawdopodobieństwo sprawności. Opis i godziny mają wagę 3."""
    errors = validate_record(row)
    invalid = {e["field"] for e in errors} | set(row.get("conflicts", {}))
    weighted = total = 0
    for key in field_names():
        weight = 3 if key in ("godziny_otwarcia_osm", "opis_lokalizacji_wewnatrz") else 1
        total += weight
        value = row.get(key)
        unknown = (key == "status_techniczny" and value == "niezweryfikowany") or (key == "dostepnosc_niepelnosprawni" and value == "niezweryfikowano")
        if value is not None and value != "" and key not in invalid and not unknown:
            weighted += weight
    completeness = 100 * weighted / total
    return round(min(100, completeness + (10 if official_source(row) else 0)), 1)


def official_source(row):
    return any(s.get("dataset_id") and s.get("institution_title") for s in row.get("sources", []))


def finalize(row):
    row["quality_errors"] = validate_record(row)
    row["schema_valid"] = not row["quality_errors"]
    row["confidence_score"] = confidence_score(row)
    return row


def deduplicate(records, threshold_m=25.0):
    """Stabilne grupy complete-link: każda para <25 m. DEMO nie wzbogaca realnych AED."""
    if threshold_m <= 0:
        raise ValueError("Próg deduplikacji musi być dodatni.")
    clusters, buckets = [], {}
    def cell(row):
        lat, lon = math.radians(row["lat"]), math.radians(row["lon"])
        radius = 6371008.8
        return tuple(math.floor(x / threshold_m) for x in
                     (radius * math.cos(lat) * math.cos(lon), radius * math.cos(lat) * math.sin(lon), radius * math.sin(lat)))
    for row in sorted(copy.deepcopy(records), key=lambda r: r["id_aed"]):
        if not usable_coordinates(row):
            continue
        address = cell(row)
        candidates = {i for delta in product((-1, 0, 1), repeat=3)
                      for i in buckets.get(tuple(a + d for a, d in zip(address, delta)), [])}
        for i in sorted(candidates):
            cluster = clusters[i]
            if row.get("is_demo", False) == cluster[0].get("is_demo", False) and all(
                haversine(row["lat"], row["lon"], other["lat"], other["lon"]) < threshold_m for other in cluster
            ):
                cluster.append(row)
                break
        else:
            buckets.setdefault(address, []).append(len(clusters))
            clusters.append([row])
    output = []
    for cluster in clusters:
        # Rekord bardziej kompletny jest bazą; remisy rozstrzyga stabilny identyfikator.
        ranked = sorted(cluster, key=lambda r: (-int(official_source(r)), -confidence_score(r), r["id_aed"]))
        merged = copy.deepcopy(ranked[0])
        merged["id_aed"] = min(r["id_aed"] for r in cluster)
        merged["merged_ids"] = sorted({i for r in cluster for i in r.get("merged_ids", [r["id_aed"]])})
        sources = {}
        for row in ranked:
            for source in row.get("sources", []):
                sources[(source.get("url"), source.get("source_record_id"), source.get("resource_id"))] = source
        merged["sources"] = [sources[k] for k in sorted(sources, key=str)]
        if any(official_source(r) for r in cluster):
            merged["zrodlo_referencyjne"] = " | ".join(sorted({r["zrodlo_referencyjne"] for r in cluster if r.get("zrodlo_referencyjne")}))
        conflicts = copy.deepcopy(merged.get("conflicts", {}))
        for key in field_names():
            if key == "id_aed":
                continue
            values = list(dict.fromkeys(r.get(key) for r in ranked if r.get(key) is not None))
            if merged.get(key) is None and values:
                merged[key] = values[0]
            if len(values) > 1 and key not in ("lat", "lon", "zrodlo_referencyjne"):
                conflicts[key] = values
        merged["conflicts"] = conflicts
        merged["deduplication_review_required"] = len(cluster) > 1
        merged["deduplication_max_distance_m"] = round(max((haversine(a["lat"], a["lon"], b["lat"], b["lon"]) for a in cluster for b in cluster), default=0), 2)
        output.append(finalize(merged))
    return sorted(output, key=lambda r: r["id_aed"])


def normalize_sources(osm_elements, institutional_rows=(), area_config=None, danegov_records=(), locality_contexts=None):
    mapped, rejected = [], []
    for element in osm_elements:
        config = area_config or {}
        context = (locality_contexts or {}).get((element.get("type"), element.get("id")))
        coords = element if element.get("type") == "node" else element.get("center", {})
        city_tag = clean(element.get("tags", {}).get("addr:city"))
        if (context and usable_coordinates(coords) and usable_coordinates(context)
                and (not city_tag or city_tag.casefold() == context["city"].casefold())
                and haversine(coords["lat"], coords["lon"], context["lat"], context["lon"]) <= 1):
            config = {**config, "city": context["city"], "teryt": context["teryt"],
                      "administrative_context": {"area": context["area"], "city": context["city"],
                                                 "retrieved_at": context["retrieved_at"], "method": "same_osm_object_in_administrative_area"}}
        row = normalize_osm(element, config)
        if usable_coordinates(row):
            mapped.append(row)
        else:
            rejected.append({"source": "OSM", "id": element.get("id"), "error": "Brak poprawnych współrzędnych."})
    for raw in institutional_rows:
        row = normalize_institutional(raw)
        if usable_coordinates(row):
            mapped.append(row)
        else:
            rejected.append({"source": "institutional_demo", "id": raw.get("numer"), "error": "Brak poprawnych współrzędnych."})
    for row in danegov_records:
        if usable_coordinates(row):
            mapped.append(row)
        else:
            rejected.append({"source": "dane.gov.pl", "id": row.get("id_aed"), "error": "Brak poprawnych współrzędnych."})
    return deduplicate(mapped), rejected
