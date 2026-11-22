"""Rzeczywisty katalog JSON:API 1.4, parsery tabel i trwała migawka offline.

Katalog publiczny ma wyłącznie operacje GET. Ten moduł niczego nie publikuje.
Brak współrzędnych lub HTML pod adresem JSON jest raportowany, nie geokodowany.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import csv
import ipaddress
import json
import math
import os
import re
import tempfile
import unicodedata
from statistics import median
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zipfile import ZipFile
from zipfile import BadZipFile

import requests
from lxml import etree
from openpyxl import load_workbook

from .normalizer import attach_source, canonical_values, decimal, clean, haversine

BASE_URL = "https://api.dane.gov.pl/1.4"
from .runtime_paths import cache_dir
CACHE_PATH = cache_dir() / "danegov_cache.json"
FORMATS = {"csv", "json", "geojson", "xlsx", "xml"}
QUERIES = ("AED", "defibrylator", "defibrylatory")
MAX_BYTES, MAX_ROWS = 20 * 1024 * 1024, 50000


def plain(value):
    return unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()


def key(value):
    text = str(value or "").lower().replace("ł", "l")
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode())


ALIASES = {
    "lat": ("lat", "latitude", "szerokosc", "szerokoscgeograficzna", "szerokoscgeo", "y", "wspolrzednay"),
    "lon": ("lon", "lng", "longitude", "dlugosc", "dlugoscgeograficzna", "dlugoscgeo", "x", "wspolrzednax"),
    "nazwa_obiektu": ("nazwaobiektu", "lokalizacja", "obiekt", "nazwa", "name", "title", "placowka"),
    "ulica_numer": ("ulicanumer", "adres", "address", "ulica", "street"),
    "miejscowosc": ("miejscowosc", "miasto", "city", "town"),
    "kod_pocztowy": ("kodpocztowy", "postcode", "postalcode", "poczta"),
    "opis_lokalizacji_wewnatrz": ("opislokalizacjiwewnatrz", "umiejscowienie", "pietrohol", "dokladnalokalizacja", "locationdescription"),
    "godziny_otwarcia_osm": ("godzinyotwarciaosm", "openinghours", "harmonogram"),
    "dostepnosc_typ": ("dostepnosctyp", "access"),
    "wymagany_klucz_lub_kod": ("wymaganykluczlubkod", "klucz", "locked"),
    "dostepnosc_niepelnosprawni": ("dostepnoscniepelnosprawni", "wheelchair"),
    "model_aed": ("modelaed", "model", "producentmodel"),
    "status_techniczny": ("statustechniczny",),
    "dysponent_kontakt": ("dysponentkontakt", "email", "contactemail", "phone", "telefon"),
    "dysponent_nazwa": ("dysponentnazwa", "operator", "jednostka"),
    "data_aktualizacji": ("dataaktualizacji", "checkdate", "potwierdzono"),
}


def public_url(url):
    p = urlparse(url)
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError("Zasób wymaga publicznego adresu HTTP(S).")
    if p.hostname.lower() in ("localhost",) or p.hostname.endswith((".local", ".internal")):
        raise ValueError("Niepubliczny adres zasobu.")
    try:
        if not ipaddress.ip_address(p.hostname).is_global:
            raise ValueError("Niepubliczny adres IP.")
    except ValueError as exc:
        if re.fullmatch(r"[0-9.:]+", p.hostname) or ":" in p.hostname:
            raise ValueError("Niepubliczny adres IP.") from exc
    return url


def decode_table(content):
    for enc in ("utf-8-sig", "cp1250", "iso-8859-2"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            pass
    raise ValueError("Nieobsługiwane kodowanie tabeli.")


def table_rows(matrix):
    rows = [list(r) for r in matrix if any(v is not None and str(v).strip() for v in r)]
    if not rows:
        return []
    if all(len(r) == 1 for r in rows) and "," in str(rows[0][0]):
        rows = [next(csv.reader([str(r[0])], delimiter=",")) for r in rows]
    # Nagłówek może poprzedzać tytuł raportu i puste wiersze.
    known = {x for aliases in ALIASES.values() for x in aliases}
    header_index = max(range(min(30, len(rows))), key=lambda i: sum(key(c) in known for c in rows[i]))
    header = [str(v or "").strip() for v in rows[header_index]]
    if len(header) != len(set(header)):
        raise ValueError("Powtarzające się nazwy kolumn.")
    if len(rows) - header_index > MAX_ROWS + 1:
        raise ValueError("Przekroczono limit wierszy.")
    return [dict(zip(header, r)) for r in rows[header_index + 1:]]


def parse_rows(content: bytes, fmt: str):
    """Wyłącznie dane tabelaryczne/Point WGS84. Bez wykonywania formuł i XML entities."""
    if len(content) > MAX_BYTES:
        raise ValueError("Zasób przekracza 20 MiB.")
    if content.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise ValueError("Adres opisany jako dane zwrócił stronę HTML, a nie plik maszynowy.")
    if fmt == "csv":
        text = decode_table(content).replace("\r\r\n", "\n")
        try:
            first = text.splitlines()[0]
            delimiter = max((",", ";", "\t", "|"), key=first.count)
            dialect = csv.Sniffer().sniff(first + "\n", delimiters=delimiter)
        except csv.Error:
            dialect = csv.excel
        matrix = list(csv.reader(io.StringIO(text), delimiter=delimiter if text.strip() else ",", skipinitialspace=True))
        # Niektóre eksporty (m.in. Marki) opakowują cały rekord w dodatkowy cudzysłów.
        if matrix and all(len(r) <= 1 for r in matrix):
            matrix = [next(csv.reader([r[0]], delimiter=",")) for r in matrix if r]
        return table_rows(matrix)
    if fmt == "xlsx":
        with ZipFile(io.BytesIO(content)) as archive:
            if sum(z.file_size for z in archive.infolist()) > 64 * 1024 * 1024:
                raise ValueError("Zbyt duży rozpakowany skoroszyt.")
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            result = []
            for sheet in book:
                if sheet.max_column > 200 or sheet.max_row > MAX_ROWS + 30:
                    raise ValueError("Przekroczono limit arkusza.")
                matrix = []
                for cells in sheet.iter_rows():
                    if any(c.data_type == "f" for c in cells):
                        raise ValueError("Źródłowy arkusz zawiera formuły; wymagane wartości.")
                    matrix.append([c.value for c in cells])
                result.extend(table_rows(matrix))
            return result
        finally:
            book.close()
    if fmt in ("json", "geojson"):
        data = json.loads(content.decode("utf-8-sig"))
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            data = data.get("features", [])
        elif isinstance(data, dict) and data.get("type") == "Feature":
            data = [data]
        else:
            while isinstance(data, dict):
                nested = next((data[k] for k in ("results", "records", "items", "data", "result") if isinstance(data.get(k), (list, dict))), None)
                if nested is None:
                    data = [data]
                    break
                data = nested
        if not isinstance(data, list) or len(data) > MAX_ROWS:
            raise ValueError("Oczekiwano ograniczonej listy rekordów JSON.")
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "Feature":
                geometry = item.get("geometry") or {}
                row = dict(item.get("properties") or {})
                if geometry.get("type") == "Point":
                    row["__coordinates"] = geometry.get("coordinates")
                result.append(row)
            elif isinstance(item.get("values"), list):
                result.append({v["key"]: v.get("value") for v in item["values"] if "key" in v})
            else:
                result.append(item.get("attributes", item))
        return result
    if fmt == "xml":
        root = etree.fromstring(content, etree.XMLParser(resolve_entities=False, no_network=True))
        if root.getroottree().docinfo.doctype:
            raise ValueError("XML z DTD nie jest obsługiwany.")
        result = []
        members = root.xpath('//*[local-name()="featureMember" or local-name()="member"]')
        if not members:
            members = root.xpath('//*[local-name()="row" or local-name()="record"]')
        for member in members[:MAX_ROWS + 1]:
            row = {etree.QName(e).localname: e.text for e in member.iterdescendants() if not len(e) and e.text}
            # GML wymaga jawnego CRS: różna kolejność osi i układy projektowane nie są zgadywane.
            for point in member.xpath('.//*[local-name()="Point"]'):
                crs = point.get("srsName", "")
                if "4326" in crs or "CRS84" in crs:
                    pos = point.xpath('.//*[local-name()="pos" or local-name()="coordinates"]/text()')
                    if pos:
                        nums = re.split(r"[ ,]+", pos[0].strip())
                        if len(nums) == 2:
                            row["__coordinates"] = nums if "CRS84" in crs else nums[::-1]
            result.append(row)
        if len(result) > MAX_ROWS:
            raise ValueError("Za dużo rekordów XML.")
        return result
    raise ValueError(f"Nieobsługiwany format: {fmt}")


def normalize_table_row(raw, dataset, resource, institution):
    values = {key(k): clean(v) for k, v in raw.items() if not isinstance(v, (list, dict))}
    row = {target: next((values[a] for a in aliases if values.get(a) is not None), None)
           for target, aliases in ALIASES.items()}
    for field in ("kod_teryt", "data_waznosci_elektrod", "data_waznosci_baterii"):
        row[field] = values.get(key(field))
    warnings = []
    coords = raw.get("__coordinates")
    geometry = raw.get("geometry")
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except ValueError:
            pass
    if isinstance(geometry, dict) and geometry.get("type") == "Point":
        coords = geometry.get("coordinates")
        if isinstance(coords, dict):
            coords = [coords.get("lon", coords.get("long", coords.get("lng"))), coords.get("lat")]
    if coords and len(coords) >= 2:
        row["lon"], row["lat"] = coords[:2]
    elif row.get("lat") is None or row.get("lon") is None:
        for value in values.values():
            match = re.fullmatch(r"\s*(?:SRID=4326;)?POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)\s*", str(value), flags=re.I)
            if match:
                row["lon"], row["lat"] = match.groups()
                break
    try:
        row["lat"], row["lon"] = decimal(row["lat"]), decimal(row["lon"])
    except (ValueError, TypeError):
        raise ValueError("Brak rozpoznanych współrzędnych WGS84.") from None
    # Dane polskie: zamiana tylko kiedy jedna orientacja jednoznacznie mieści się w Polsce.
    in_pl = lambda lat, lon: 49 <= lat <= 55.1 and 14 <= lon <= 24.2
    if not in_pl(row["lat"], row["lon"]) and in_pl(row["lon"], row["lat"]):
        row["lat"], row["lon"] = row["lon"], row["lat"]
        warnings.append("Zamieniono błędnie opisane osie współrzędnych (jednoznaczny zakres Polski).")
    if not in_pl(row["lat"], row["lon"]):
        raise ValueError("Współrzędne poza zakresem Polski lub inny układ odniesienia.")
    house = values.get("homenumber") or values.get("housenumber") or values.get("numerbudynku")
    if house and row.get("ulica_numer"):
        row["ulica_numer"] = f"{row['ulica_numer']} {house}"
    address = str(row.get("ulica_numer") or "")
    postal = re.search(r"\b(\d{2}-\d{3})\s+([^,]+)", address)
    if postal:
        row["kod_pocztowy"] = row.get("kod_pocztowy") or postal[1]
        row["miejscowosc"] = row.get("miejscowosc") or postal[2].strip()
        row["ulica_numer"] = address[:postal.start()].strip(", ")
    dsid, rid = str(dataset["id"]), str(resource["id"])
    source_id = values.get("idaed") or values.get("numerid") or values.get("id")
    if source_id is None:
        source_id = hashlib.sha256(f"{row['lat']:.6f}|{row['lon']:.6f}|{row.get('nazwa_obiektu')}".encode()).hexdigest()[:16]
    row["id_aed"] = f"DG-{dsid}-{re.sub(r'[^A-Za-z0-9_.:-]', '_', str(source_id))[:65]}"
    row["dysponent_nazwa"] = row.get("dysponent_nazwa") or institution
    row["status_techniczny"] = row.get("status_techniczny") or "niezweryfikowany"
    row["dostepnosc_niepelnosprawni"] = row.get("dostepnosc_niepelnosprawni") or "niezweryfikowano"
    # Nie uznajemy daty modyfikacji pliku ani słowa „publiczny” za kontrolę AED.
    row["zrodlo_referencyjne"] = f"dane.gov.pl [ID: {dsid} - {institution}]"
    attrs = dataset["attributes"]
    license_name = attrs.get("license_name")
    license_id = {"CC0 1.0": "CC0-1.0", "CC BY 4.0": "CC-BY-4.0"}.get(license_name)
    url = f"https://dane.gov.pl/pl/dataset/{dsid}"
    return attach_source(canonical_values(row), row["zrodlo_referencyjne"], url, license_id, False,
                         {"dataset_id": dsid, "resource_id": rid, "institution_title": institution,
                          "dataset_title": plain(attrs.get("title")), "license_name": license_name,
                          "license_conditions": {k: v for k, v in attrs.items() if k.startswith("license_condition") and v},
                          "resource_url": resource["attributes"].get("file_url") or resource["attributes"].get("download_url"),
                          "parser_warnings": warnings})


@dataclass
class DaneGovResult:
    records: list[dict]
    metadata: dict


class DaneGovClient:
    def __init__(self, *, session=None, cache_path=CACHE_PATH):
        self.session = session or requests.Session()
        self.owns_session = session is None
        self.cache_path = Path(cache_path)
        self.session.headers.update({"Accept": "application/vnd.api+json", "Accept-Language": "pl",
                                     "User-Agent": "OtwarteAED/0.2 public AED data integration"})

    def get(self, url, **kwargs):
        for _ in range(6):
            public_url(url)
            response = self.session.get(url, timeout=(8, 35), allow_redirects=False, **kwargs)
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers["Location"])
                kwargs.pop("params", None)
                continue
            response.raise_for_status()
            return response
        raise ValueError("Za wiele przekierowań zasobu.")

    def pages(self, url, params=None):
        # related links są zaufane tylko w tej samej wersji oficjalnego API.
        if not url.startswith(BASE_URL + "/"):
            raise ValueError("Link paginacji spoza oficjalnego API 1.4.")
        page = 1
        while page <= 200:
            document = self.get(url, params={**(params or {}), "per_page": 50, "page": page}).json()
            if not isinstance(document.get("data"), list):
                raise ValueError("Nieprawidłowa lista JSON:API.")
            yield document
            count = document.get("meta", {}).get("count")
            if count is not None:
                more = page * 50 < int(count)
            else:
                more = bool(document.get("links", {}).get("next")) or len(document["data"]) == 50
            if not more:
                return
            page += 1
        raise ValueError("Przekroczono limit paginacji; zachowano poprzednią migawkę.")

    def cached(self, reason="offline_requested"):
        try:
            envelope = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if envelope["version"] != 1 or not isinstance(envelope["records"], list) or not envelope["retrieved_at"] or not isinstance(envelope["datasets"], list):
                raise ValueError("Niekompletny cache.")
            return DaneGovResult(envelope["records"], {k: v for k, v in envelope.items() if k != "records" and k != "search_responses"} |
                                 {"from_cache": True, "fallback_reason": reason})
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise RuntimeError(f"Brak poprawnego cache dane.gov.pl: {exc}") from exc

    def fetch(self, *, offline=False):
        try:
            if offline:
                return self.cached()
            return self._fetch()
        except (requests.RequestException, ValueError, KeyError) as exc:
            return self.cached(str(exc))
        finally:
            if self.owns_session:
                self.session.close()

    def _fetch(self):
        found, searches, ignored = {}, [], []
        for query in QUERIES:
            for document in self.pages(BASE_URL + "/datasets", {"q": query}):
                searches.append({"query": query, "response": document})
                for ds in document["data"]:
                    attrs = ds.get("attributes", {})
                    text = plain(" ".join(str(attrs.get(k, "")) for k in ("title", "notes", "keywords")))
                    if re.search(r"\bAED\b|defibr|defibry", text, re.I):
                        found[str(ds["id"])] = ds
                    else:
                        ignored.append(str(ds["id"]))
        previous = {}
        if self.cache_path.exists():
            try:
                previous = {d["id"]: d for d in self.cached().metadata["datasets"]}
            except RuntimeError:
                pass
        datasets, all_records, errors = [], [], []
        for dsid, ds in sorted(found.items()):
            try:
                inst_rel = ds.get("relationships", {}).get("institution", {})
                inst_url = inst_rel.get("links", {}).get("related") or f"{BASE_URL}/institutions/{inst_rel['data']['id']}"
                if not inst_url.startswith(BASE_URL + "/institutions/"):
                    raise ValueError("Nieprawidłowy link instytucji.")
                inst_doc = self.get(inst_url).json()
                institution = plain(inst_doc["data"]["attributes"]["title"])
                resources_url = ds.get("relationships", {}).get("resources", {}).get("links", {}).get("related") or f"{BASE_URL}/datasets/{dsid}/resources"
                resource_docs = [r for doc in self.pages(resources_url) for r in doc["data"]]
                info = {"id": dsid, "title": plain(ds["attributes"].get("title")), "institution_title": institution,
                        "url": f"https://dane.gov.pl/pl/dataset/{dsid}", "api_url": ds.get("links", {}).get("self"),
                        "license_name": ds["attributes"].get("license_name"), "dataset_metadata": ds,
                        "institution_metadata": inst_doc, "resources": [], "records": [], "from_cache": False}
                indexed = {}
                # Najnowszy zasób wygrywa przy powtórzeniu tego samego identyfikatora.
                for resource in sorted(resource_docs, key=lambda r: r["attributes"].get("modified") or "", reverse=True):
                    attrs = resource["attributes"]
                    fmt = str(attrs.get("format", "")).lower().lstrip(".")
                    entry = {"id": str(resource["id"]), "format": fmt, "metadata": resource, "records_count": 0}
                    info["resources"].append(entry)
                    if fmt not in FORMATS:
                        entry["status"] = "unsupported_format"
                        continue
                    urls = list(dict.fromkeys(u for u in (attrs.get("file_url"), attrs.get("download_url")) if u))
                    issues = []
                    for url in urls:
                        try:
                            response = self.get(url, stream=True)
                            try:
                                chunks, size = [], 0
                                for chunk in response.iter_content(65536):
                                    size += len(chunk)
                                    if size > MAX_BYTES:
                                        raise ValueError("Zasób przekracza 20 MiB.")
                                    chunks.append(chunk)
                                content = b"".join(chunks)
                            finally:
                                response.close()
                            rows = parse_rows(content, fmt)
                            parsed, rejected = [], []
                            for index, raw in enumerate(rows, 1):
                                try:
                                    parsed.append(normalize_table_row(raw, ds, resource, institution))
                                except (ValueError, TypeError) as exc:
                                    rejected.append({"row": index, "error": str(exc)})
                            # Jawny błąd przestrzenny w miejskim pliku (np. Marki: punkt w Krośnie).
                            # Wyłącznie gdy >=5 punktów wskazuje tę samą miejscowość; bez geokodowania.
                            cities = {r.get("miejscowosc") for r in parsed}
                            if len(parsed) >= 5 and len(cities) == 1 and None not in cities:
                                center = median(r["lat"] for r in parsed), median(r["lon"] for r in parsed)
                                accepted = []
                                for row in parsed:
                                    if haversine(*center, row["lat"], row["lon"]) > 100000:
                                        rejected.append({"id": row["id_aed"], "error": "Punkt >100 km od mediany pozostałych punktów tej samej miejscowości. Wymaga weryfikacji u dysponenta."})
                                    else:
                                        accepted.append(row)
                                parsed = accepted
                            entry.update(url=url, sha256=hashlib.sha256(content).hexdigest(), raw_base64=base64.b64encode(content).decode("ascii"),
                                         records_count=len(parsed), rejected_records=rejected, status="integrated" if parsed else "no_coordinates")
                            for row in parsed:
                                if row["id_aed"] in indexed:
                                    indexed[row["id_aed"]]["sources"].extend(row["sources"])
                                else:
                                    indexed[row["id_aed"]] = row
                            break
                        except (requests.RequestException, ValueError, TypeError, KeyError, csv.Error, BadZipFile, etree.XMLSyntaxError) as exc:
                            issues.append(f"{url}: {exc}")
                    else:
                        entry.update(status="error", error="; ".join(issues) or "Brak URL pliku.")
                    if issues:
                        entry["attempt_errors"] = issues
                info["records"] = list(indexed.values())
                if not indexed and dsid in previous and previous[dsid].get("records"):
                    old = previous[dsid]
                    info.update(records=old["records"], from_cache=True, fallback_reason="Bieżące zasoby nie dostarczyły współrzędnych; zachowano poprzednie dane.")
                info["records_count"] = len(info["records"])
                info["status"] = "integrated" if info["records_count"] else "not_integrated"
            except (requests.RequestException, ValueError, KeyError) as exc:
                errors.append({"dataset_id": dsid, "error": str(exc)})
                info = previous.get(dsid, {"id": dsid, "title": plain(ds["attributes"].get("title")), "institution_title": None,
                       "url": f"https://dane.gov.pl/pl/dataset/{dsid}", "records": [], "records_count": 0, "resources": [], "status": "error"}).copy()
                info.update(from_cache=bool(info["records"]), fallback_reason=str(exc))
            datasets.append(info)
            all_records.extend(info["records"])
        envelope = {"version": 1, "api_base_url": BASE_URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "queries": list(QUERIES), "search_responses": searches, "ignored_dataset_ids": sorted(set(ignored)),
                    "datasets": datasets, "records": all_records, "errors": errors}
        # Awaria części sieci nie zastępuje poprawnej migawki pustą listą.
        if not all_records and (self.cache_path.exists() or errors or any(r.get("status") == "error" for d in datasets for r in d.get("resources", []))):
            raise ValueError("Nie pobrano żadnych współrzędnych; zachowano cache.")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.cache_path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(envelope, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
        os.replace(temporary, self.cache_path)
        return DaneGovResult(all_records, {k: v for k, v in envelope.items() if k not in ("records", "search_responses")} |
                             {"from_cache": False, "fallback_reason": None})


def fetch_danegov(*, offline=False, **kwargs):
    return DaneGovClient(**kwargs).fetch(offline=offline)


def source_summary(metadata):
    """Kompaktowy publiczny raport bez kopii plików i pełnych odpowiedzi API."""
    return {k: v for k, v in metadata.items() if k != "datasets"} | {"datasets": [
        {k: v for k, v in d.items() if k not in ("records", "dataset_metadata", "institution_metadata", "resources")} |
        {"resources": [{k: v for k, v in r.items() if k not in ("raw_base64", "metadata")} for r in d.get("resources", [])]}
        for d in metadata.get("datasets", [])]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    result = fetch_danegov(offline=args.offline)
    print(json.dumps(source_summary(result.metadata), ensure_ascii=True, indent=2))
