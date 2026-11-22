"""Kontrolowany import PDF/HTML i niejednolitych tabel do 21 pól AED; tylko podgląd."""
from __future__ import annotations
import csv
import hashlib
import io
import ipaddress
import json
import re
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import httpx
import pdfplumber
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pdfplumber.utils.exceptions import PdfminerException
from lxml import etree
from openpyxl.utils.exceptions import InvalidFileException

from .city_search import CityResolver
from .danegov_client import ALIASES, key, parse_rows, table_rows
from .harvester_export import csv_text
from .normalizer import attach_source, canonical_values, decimal, deduplicate, finalize
from .quality_audit import in_poland
from .schema import field_names

MAX_BYTES, MAX_ROWS = 5*1024*1024, 500
from .runtime_paths import cache_dir
GEOCODE_CACHE = cache_dir() / "address_geocodes.json"


def coordinate(value, axis):
    if isinstance(value, str):
        text = value.strip().upper()
        direction = re.findall(r"[NSEW]", text)
        numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", text)
        if direction or "°" in text or "′" in text or "'" in text:
            if not 1 <= len(numbers) <= 3 or len(direction)>1:
                raise ValueError("Niepoprawne współrzędne DMS.")
            parts = [float(v.replace(",",".")) for v in numbers]
            if any(not 0<=v<60 for v in parts[1:]):
                raise ValueError("Minuty i sekundy DMS muszą być mniejsze od 60.")
            if direction and direction[0] not in ("NS" if axis=="lat" else "EW"):
                raise ValueError("Kierunek DMS nie pasuje do osi współrzędnych.")
            sign = -1 if parts[0]<0 or (direction and direction[0] in "SW") else 1
            return sign*(abs(parts[0])+(parts[1]/60 if len(parts)>1 else 0)+(parts[2]/3600 if len(parts)>2 else 0))
    return decimal(value)


def download_public(url):
    """DNS jest sprawdzany i przypinany do publicznego IP także po przekierowaniu."""
    with httpx.Client(timeout=httpx.Timeout(20, connect=6), trust_env=False, follow_redirects=False) as client:
        for _ in range(4):
            parsed = urlsplit(url)
            if parsed.scheme not in ("http","https") or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,80,443):
                raise ValueError("Podaj publiczny adres strony HTTP/HTTPS bez danych logowania.")
            addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme=="https" else 80), type=socket.SOCK_STREAM)}
            if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
                raise ValueError("Adresy lokalne, prywatne i specjalne nie są obsługiwane przez importer URL.")
            original = httpx.URL(url)
            request = client.build_request("GET", original.copy_with(host=sorted(addresses,key=lambda a:ipaddress.ip_address(a).version)[0]),
                headers={"Host": original.netloc.decode("ascii"), "User-Agent":"OtwarteAED-BIP/0.3", "Accept":"text/html,application/pdf,text/csv,application/json"},
                extensions={"sni_hostname": original.host})
            response=client.send(request, stream=True)
            try:
                if response.status_code in (301,302,303,307,308):
                    url = urljoin(url,response.headers["location"]); continue
                response.raise_for_status()
                parts, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size>MAX_BYTES: raise ValueError("Plik przekracza limit 5 MiB.")
                    parts.append(chunk)
                return b"".join(parts), response.headers.get("content-type", ""), url
            finally:
                response.close()
    raise ValueError("Zbyt wiele przekierowań.")


def text_rows(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for delimiter in (";","\t","|"):
        headers = next((i for i,line in enumerate(lines[:40]) if line.count(delimiter)>=2 and any(k in key(line) for k in ("lat","szerokosc","adres"))),None)
        if headers is not None:
            return table_rows(list(csv.reader(lines[headers:],delimiter=delimiter)))
    result=[]
    # Wolny tekst: zachowujemy wyłącznie linie z jawną parą GPS.
    for line in lines:
        pair = re.search(r"\b(5[0-5][.,]\d{3,})\s*[,;|\s]+\s*(1[4-9][.,]\d{3,}|2[0-4][.,]\d{3,})\b",line)
        if pair:
            result.append({"nazwa":line[:pair.start()].strip(" ,;-") or "AED z dokumentu", "lat":pair[1],"lon":pair[2]})
    return result


def extract_rows(content, filename):
    suffix=Path(filename.split("?",1)[0]).suffix.lower().lstrip(".")
    if suffix in ("csv","xlsx","json","geojson","xml"):
        try:
            return parse_rows(content,suffix)
        except (etree.XMLSyntaxError, csv.Error, InvalidFileException) as exc:
            raise ValueError(f"Nie można odczytać tabeli {suffix.upper()}: niepoprawny format pliku.") from exc
    if suffix in ("html","htm"):
        soup=BeautifulSoup(content,"html.parser")
        for node in soup(["script","style","noscript"]):node.decompose()
        rows=[]
        for table in soup.find_all("table"):
            matrix=[[cell.get_text(" ",strip=True) for cell in tr.find_all(["th","td"])] for tr in table.find_all("tr")]
            rows.extend(table_rows(matrix))
        if not rows:
            rows=text_rows("\n".join(n.get_text(" ",strip=True) for n in soup.find_all(["li","p"])))
        return rows
    if suffix=="pdf":
        rows=[]
        try:
            with pdfplumber.open(io.BytesIO(content)) as book:
                if len(book.pages)>20: raise ValueError("Limit PDF: 20 stron.")
                for page in book.pages:
                    tables=page.extract_tables()
                    for matrix in tables: rows.extend(table_rows(matrix))
                    if not tables: rows.extend(text_rows(page.extract_text() or ""))
            if not rows:
                reader=PdfReader(io.BytesIO(content))
                rows=text_rows("\n".join(p.extract_text() or "" for p in reader.pages[:20]))
        except (PdfminerException, PdfReadError) as exc:
            raise ValueError("Nie można odczytać PDF. Plik jest uszkodzony, zaszyfrowany lub nie jest dokumentem PDF.") from exc
        return rows
    raise ValueError("Obsługiwane: PDF, HTML, CSV, XLSX, JSON, GeoJSON i XML.")


def geocode_address(address):
    # Wspólny limit z wyszukiwaniem granic miast, maksymalnie pięć adresów na import.
    with CityResolver._network_lock:
        try: cache=json.loads(GEOCODE_CACHE.read_text(encoding="utf-8"))
        except (OSError,ValueError): cache={}
        cache_key=key(address)
        if cache_key in cache:return cache[cache_key]
        delay=1.05-(time.monotonic()-CityResolver._last_request)
        if delay>0:time.sleep(delay)
        CityResolver._last_request=time.monotonic()
        url=os_geocoder_url()
        with httpx.Client(timeout=15) as client:
            response=client.get(url,params={"q":address,"countrycodes":"pl","format":"jsonv2","limit":1},headers={"User-Agent":"OtwarteAED/0.3 limited AED address import"})
            response.raise_for_status(); items=response.json()
        result={"lat":float(items[0]["lat"]),"lon":float(items[0]["lon"])} if items else None
        cache[cache_key]=result
        GEOCODE_CACHE.parent.mkdir(parents=True,exist_ok=True)
        temporary=GEOCODE_CACHE.with_suffix(".tmp");temporary.write_text(json.dumps(cache),encoding="utf-8");temporary.replace(GEOCODE_CACHE)
        return result


def os_geocoder_url():
    import os
    return os.getenv("AED_GEOCODER_URL","https://nominatim.openstreetmap.org/search")


def clean_import(content, filename, *, source_url=None, geocode=False):
    if len(content)>MAX_BYTES:raise ValueError("Limit pliku: 5 MiB.")
    raw_rows=extract_rows(content,filename)
    if len(raw_rows)>MAX_ROWS:raise ValueError("Limit importu niejednolitych danych: 500 wierszy.")
    if not raw_rows:raise ValueError("Nie znaleziono tabeli ani jawnych par GPS. Skan PDF wymaga OCR lub eksportu tabeli do CSV/XLSX.")
    mapped,errors,changes,pending=[],[],[],[]
    geocoded=0;geocoding_attempts=0
    for number,raw in enumerate(raw_rows,1):
        values={key(k):v for k,v in raw.items()}
        row={field:values.get(key(field)) for field in field_names()}
        for field,aliases in ALIASES.items():
            if row.get(field) in (None,""):
                row[field]=next((values[a] for a in aliases if values.get(a) not in (None,"")),None)
        row["opis_lokalizacji_wewnatrz"]=row.get("opis_lokalizacji_wewnatrz") or values.get("opis") or values.get("description")
        if raw.get("__coordinates"):
            row["lon"],row["lat"]=raw["__coordinates"][:2]
        if row.get("lat") is None or row.get("lon") is None:
            geometry=raw.get("geometry")
            if isinstance(geometry,dict) and geometry.get("type")=="Point":
                coords=geometry.get("coordinates")
                if isinstance(coords,dict):row["lat"],row["lon"]=coords.get("lat"),coords.get("lon",coords.get("long"))
                elif isinstance(coords,list):row["lon"],row["lat"]=coords[:2]
            for value in values.values():
                match=re.fullmatch(r"\s*POINT\s*\(\s*([-+\d.]+)\s+([-+\d.]+)\s*\)\s*",str(value),re.I)
                if match:row["lon"],row["lat"]=match.groups();break
            combined=values.get("wspolrzedne") or values.get("wspolrzednegps")
            if combined and (row.get("lat") is None or row.get("lon") is None):
                text=str(combined)
                dms_parts=re.findall(r"[-+]?\d[\d.,\s°'′\"″]*[NSEW]",text,re.I)
                if len(dms_parts)==2:
                    for part in dms_parts:
                        row["lat" if part[-1].upper() in "NS" else "lon"]=part
                else:
                    parts=re.split(r"\s*[;|/]\s*",text)
                    if len(parts)!=2:parts=re.findall(r"[-+]?\d+(?:[.,]\d+)?",text)
                    if len(parts)==2:row["lat"],row["lon"]=parts
        try:
            for axis in ("lat","lon"):
                original=row.get(axis);row[axis]=coordinate(original,axis)
                if isinstance(original,str) and ("," in original or "°" in original):changes.append({"row":number,"field":axis,"message":"Przekonwertowano przecinek/DMS do stopni dziesiętnych."})
        except (ValueError,TypeError):
            address=" ".join(str(row.get(k) or "") for k in ("ulica_numer","kod_pocztowy","miejscowosc")).strip()
            if geocode and geocoding_attempts<5 and row.get("ulica_numer") and row.get("miejscowosc"):
                geocoding_attempts+=1
                try: coords=geocode_address(address)
                except (httpx.HTTPError,ValueError):coords=None
                if coords:
                    geocoded+=1
                    row.update(coords);changes.append({"row":number,"field":"lat/lon","message":"GPS oszacowany z adresu, wymaga weryfikacji w terenie."})
                else:
                    pending.append({"row":number,"data":row});errors.append({"row":number,"message":"Nie udało się ustalić GPS."});continue
            else:
                pending.append({"row":number,"data":row});errors.append({"row":number,"message":"Brak rozpoznanych współrzędnych; uzupełnij GPS lub włącz ograniczone geokodowanie."});continue
        if not in_poland(row["lat"],row["lon"]) and in_poland(row["lon"],row["lat"]):
            row["lat"],row["lon"]=row["lon"],row["lat"];changes.append({"row":number,"field":"lat/lon","message":"Zamieniono osie GPS."})
        if not in_poland(row["lat"],row["lon"]):
            errors.append({"row":number,"message":"GPS poza granicami Polski lub niepoprawny układ odniesienia."});continue
        row["id_aed"]=str(row.get("id_aed") or "IMPORT-"+hashlib.sha256(f"{filename}|{number}|{row['lat']}|{row['lon']}".encode()).hexdigest()[:16])
        row["status_techniczny"]=row.get("status_techniczny") or "niezweryfikowany"
        row["dostepnosc_niepelnosprawni"]=row.get("dostepnosc_niepelnosprawni") or "niezweryfikowano"
        if row.get("dostepnosc_typ")=="24_7":
            row["godziny_otwarcia_osm"]=row.get("godziny_otwarcia_osm") or "24/7"
            row["wymagany_klucz_lub_kod"]=row.get("wymagany_klucz_lub_kod") or "NIE"
        row["zrodlo_referencyjne"]=row.get("zrodlo_referencyjne") or source_url
        row=canonical_values(row)
        mapped.append(attach_source(row,"Import BIP / pliku",source_url,details={"filename":filename,"import_row":number}))
    normalized=deduplicate(mapped)
    quality=[{"id_aed":r["id_aed"],"errors":r["quality_errors"]} for r in normalized if r["quality_errors"]]
    standard=[{field:row.get(field) for field in field_names()} for row in normalized]
    report={"rows_total":len(raw_rows),"rows_rescued":len(mapped),"output_records":len(normalized),
            "duplicates_merged":len(mapped)-len(normalized),"schema_valid_records":sum(r["schema_valid"] for r in normalized),
            "changes":changes,"errors":errors,"quality":quality,"pending_records":pending,
            "normalized_json":normalized,"standard_json":standard,"normalized_csv":csv_text(normalized,extensions=False),
            "geocoded_addresses":geocoded,"geocoding_attempts":geocoding_attempts,"publication_ready":False,
            "note":"Import jest roboczy. Braki 21 pól i prawa do publikacji wymagają sprawdzenia; PDF/HTML to wejście, eksport danych pozostaje CSV/JSON."}
    return json.loads(json.dumps(report,ensure_ascii=False,default=str),parse_constant=lambda _:None)
