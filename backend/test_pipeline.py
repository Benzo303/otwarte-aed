"""Testy offline. Uruchom: .venv/Scripts/python.exe -m unittest backend.test_pipeline -v"""
import copy
import csv
import io
import json
import math
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from lxml import etree
from openpyxl import Workbook
import requests
from zipfile import ZipFile

from .availability import availability_now, valid_hours
from .fetcher import AREAS, CACHE_DIR, fetch_institutional, fetch_osm, load_cache, load_city_contexts
from .harvester_export import csv_text, geojson, metadata_xml, run_pipeline, validate_metadata
from .main import create_app
from .normalizer import (canonical_values, confidence_score, deduplicate, haversine,
                         normalize_institutional, normalize_osm, normalize_sources, validate_record)
from .schema import field_names, load_schema
from .upload_validation import MAX_UPLOAD_BYTES, validate_upload

TZ = ZoneInfo("Europe/Warsaw")
MONDAY = datetime(2026, 11, 23, 10, 0, tzinfo=TZ)


def example():
    return normalize_institutional(fetch_institutional()[2])


def csv_upload(records):
    return csv_text(records, extensions=False).encode("utf-8")


def xlsx_upload(records, formula=False):
    wb = Workbook()
    ws = wb.active
    ws.title = "Szablon_Do_Wypelnienia"
    ws.append(field_names())
    for record in records:
        ws.append([record.get(k) for k in field_names()])
    if formula:
        ws["B2"] = '=CONCAT("Nazwa", " obiektu")'
    stream = io.BytesIO()
    wb.save(stream)
    wb.close()
    return stream.getvalue()


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo, cls.rejected = normalize_sources([], fetch_institutional())

    def test_schema_read_from_workbook(self):
        self.assertEqual(len(field_names()), 21)
        self.assertEqual(load_schema()[1]["dostepnosc_typ"], ("24_7", "godziny_pracy", "na_klucz_lub_kod", "niedostepny"))

    def test_real_overpass_cache_exists(self):
        result = load_cache("warszawa")
        self.assertGreater(len(result.elements), 0)
        self.assertTrue(all(e["tags"]["emergency"] == "defibrillator" for e in result.elements))
        self.assertTrue(result.metadata["retrieved_at"])
        self.assertEqual(result.metadata["license"], "ODbL-1.0")

    def test_api_timeout_uses_unchanged_cache(self):
        client = Mock()
        client.post.side_effect = requests.Timeout("timeout podczas demo")
        result = fetch_osm(session=client, endpoints=("https://overpass.test/interpreter",))
        self.assertTrue(result.metadata["from_cache"])
        self.assertIn("timeout", result.metadata["fallback_reason"])
        self.assertEqual(result.metadata["retrieved_at"], load_cache("warszawa").metadata["retrieved_at"])

    def test_fresh_success_writes_cache(self):
        client = Mock()
        payload = {"elements": load_cache("warszawa").elements[:1]}
        client.post.return_value.json.return_value = payload
        with TemporaryDirectory() as directory:
            fetched = fetch_osm(cache_dir=Path(directory), session=client, endpoints=("https://overpass.test",))
            self.assertFalse(fetched.metadata["from_cache"])
            self.assertEqual(load_cache("warszawa", Path(directory)).elements, payload["elements"])

    def test_partial_response_does_not_overwrite_cache(self):
        client = Mock()
        client.post.return_value.json.return_value = {"remark": "runtime timeout", "elements": []}
        with TemporaryDirectory() as directory:
            target = Path(directory) / "osm_warszawa.json"
            original = (CACHE_DIR / target.name).read_bytes()
            target.write_bytes(original)
            result = fetch_osm(cache_dir=Path(directory), session=client, endpoints=("https://overpass.test",))
            self.assertTrue(result.metadata["from_cache"])
            self.assertEqual(target.read_bytes(), original)

    def test_missing_and_corrupt_cache_fail_explicitly(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                fetch_osm(offline=True, cache_dir=Path(directory))
            (Path(directory) / "osm_warszawa.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                fetch_osm(offline=True, cache_dir=Path(directory))

    def test_institutional_mapping_decimal_comma_and_codes(self):
        row = example()
        self.assertEqual(row["dostepnosc_typ"], "godziny_pracy")
        self.assertEqual(row["status_techniczny"], "sprawny")
        self.assertEqual(row["lat"], 52.233)
        self.assertEqual(row["kod_pocztowy"], "00-002")
        self.assertEqual(validate_record(row), [])

    def test_unknown_osm_does_not_become_public_or_verified(self):
        row = normalize_osm({"type": "node", "id": 1, "lat": 52.2, "lon": 21.0,
                             "timestamp": "2026-11-21T00:00:00Z", "tags": {"emergency": "defibrillator", "opening_hours": "24/7"}}, AREAS["warszawa"])
        self.assertIsNone(row["dostepnosc_typ"])
        self.assertIsNone(row["data_aktualizacji"])
        self.assertEqual(row["status_techniczny"], "niezweryfikowany")
        self.assertIsNone(availability_now(row, MONDAY)["otwarte_teraz"])

    def test_osm_way_uses_center(self):
        row = normalize_osm({"type": "way", "id": 2, "center": {"lat": 52.0, "lon": 21.0},
                             "tags": {"emergency": "defibrillator", "access": "yes", "opening_hours": "24/7"}}, AREAS["warszawa"])
        self.assertEqual(row["lat"], 52.0)
        self.assertEqual(row["dostepnosc_typ"], "24_7")

    def test_national_city_filter_retains_warsaw_area_context(self):
        # Regresja: niemal wszystkie warszawskie AED nie mają tagu addr:city.
        element = next(e for e in load_cache("warszawa").elements
                       if not e["tags"].get("addr:city") and e["tags"].get("opening_hours") == "24/7"
                       and e["tags"].get("access") == "yes" and not e["tags"].get("locked"))
        rows, rejected = normalize_sources([element], area_config=AREAS["polska"], locality_contexts=load_city_contexts())
        self.assertEqual(rejected, [])
        self.assertEqual(rows[0]["miejscowosc"], "Warszawa")
        self.assertEqual(rows[0]["kod_teryt"], "1465011")
        self.assertTrue(availability_now(rows[0], MONDAY)["otwarte_teraz"])
        self.assertIn("administrative_context", rows[0]["sources"][0])
        # Przeniesienie tego samego urządzenia nie dziedziczy dawnego miasta.
        moved = copy.deepcopy(element); moved["lat"] += .1
        rows, _ = normalize_sources([moved], area_config=AREAS["polska"], locality_contexts=load_city_contexts())
        self.assertIsNone(rows[0]["miejscowosc"])

    def test_haversine_known_distance(self):
        self.assertAlmostEqual(haversine(0, 0, 0, 1), 111195.08, places=1)
        self.assertEqual(haversine(52, 21, 52, 21), 0)

    def test_dedup_25m_threshold_and_provenance(self):
        base = example()
        base["lat"], base["lon"] = 0.0, 0.0
        near = copy.deepcopy(base)
        near["id_aed"] = "DEMO-NEAR"
        near["lat"] = math.degrees(24.9 / 6371008.8)
        near["sources"][0]["url"] = "https://example.org/near"
        far = copy.deepcopy(base)
        far["id_aed"] = "DEMO-FAR"
        far["lat"] = math.degrees(50.1 / 6371008.8)
        rows = deduplicate([base, near, far])
        self.assertEqual(len(rows), 2)
        merged = next(r for r in rows if len(r["sources"]) == 2)
        self.assertLess(merged["deduplication_max_distance_m"], 25)
        self.assertEqual(rows, deduplicate([far, near, base]))
        boundary = copy.deepcopy(base)
        boundary["id_aed"] = "DEMO-BOUNDARY"
        boundary["lat"] = math.degrees(25.01 / 6371008.8)
        self.assertEqual(len(deduplicate([base, boundary])), 2)

    def test_demo_never_enriches_real_record(self):
        real, demo = example(), example()
        real["is_demo"] = False
        real["id_aed"] = "REAL-1"
        self.assertEqual(len(deduplicate([real, demo])), 2)

    def test_conflicting_availability_never_shown_open(self):
        first = example()
        second = copy.deepcopy(first)
        second.update(id_aed="DEMO-OTHER", dostepnosc_typ="na_klucz_lub_kod", wymagany_klucz_lub_kod="TAK")
        merged = deduplicate([first, second])[0]
        self.assertIn("dostepnosc_typ", merged["conflicts"])
        self.assertIsNot(availability_now(merged, MONDAY)["otwarte_teraz"], True)

    def test_confidence_drops_when_hours_or_description_missing(self):
        full = example()
        partial = full | {"godziny_otwarcia_osm": None, "opis_lokalizacji_wewnatrz": None}
        self.assertEqual(confidence_score(full), 100)
        self.assertLess(confidence_score(partial), confidence_score(full))

    def test_hours_weekday_weekend_and_exclusive_end(self):
        row = example()
        self.assertTrue(availability_now(row, MONDAY)["otwarte_teraz"])
        self.assertFalse(availability_now(row, datetime(2026, 11, 22, 10, tzinfo=TZ))["otwarte_teraz"])
        self.assertFalse(availability_now(row, MONDAY.replace(hour=18))["otwarte_teraz"])
        self.assertTrue(availability_now(row, MONDAY.replace(hour=19))["otwarte_teraz"])

    def test_hours_overnight_holiday_timezone_and_dst(self):
        row = example() | {"godziny_otwarcia_osm": "Mo 22:00-02:00"}
        self.assertTrue(availability_now(row, datetime(2026, 11, 24, 1, tzinfo=TZ))["otwarte_teraz"])
        row["godziny_otwarcia_osm"] = "Mo-Su 08:00-20:00; PH off"
        self.assertFalse(availability_now(row, datetime(2026, 11, 11, 12, tzinfo=TZ))["otwarte_teraz"])
        row["godziny_otwarcia_osm"] = "Mo-Fr 08:00-18:00"
        self.assertTrue(availability_now(row, datetime(2026, 7, 6, 6, tzinfo=ZoneInfo("UTC")))["otwarte_teraz"])
        self.assertTrue(availability_now(row, datetime(2026, 11, 23, 7, tzinfo=ZoneInfo("UTC")))["otwarte_teraz"])

    def test_locked_service_and_invalid_hours(self):
        for row in (example() | {"wymagany_klucz_lub_kod": "TAK"}, example() | {"status_techniczny": "serwis"}):
            self.assertFalse(availability_now(row, MONDAY)["otwarte_teraz"])
        self.assertFalse(valid_hours("błędny harmonogram"))
        self.assertIsNone(availability_now(example() | {"godziny_otwarcia_osm": "błędne"}, MONDAY)["otwarte_teraz"])

    def test_csv_json_geojson_values_and_quoting(self):
        row = example()
        row["opis_lokalizacji_wewnatrz"] = 'Szafka, znak "AED"\nparter, ściana żółta'
        exported = list(csv.DictReader(io.StringIO(csv_text([row]), newline="")))
        self.assertEqual(exported[0]["opis_lokalizacji_wewnatrz"], row["opis_lokalizacji_wewnatrz"])
        self.assertEqual(exported[0]["kod_pocztowy"], "00-002")
        self.assertEqual(geojson([row])["features"][0]["geometry"]["coordinates"], [row["lon"], row["lat"]])

    def test_metadata_xsd_and_license_constraints(self):
        for license_id in ("CC0-1.0", "CC-BY-4.0"):
            xml = metadata_xml(self.demo, base_url="https://example.org", license_id=license_id)
            validate_metadata(xml)
            root = etree.fromstring(xml)
            self.assertEqual(root.tag, "{urn:otwarte-dane:harvester:1.13}datasets")
            self.assertEqual(len(root.findall("dataset/resources/resource")), 3)
        osm = copy.deepcopy(self.demo)
        osm[0]["sources"][0]["license"] = "ODbL-1.0"
        validate_metadata(metadata_xml(osm, base_url="https://example.org"))
        with self.assertRaises(ValueError):
            metadata_xml(osm, base_url="https://example.org", license_id="CC0-1.0")
        with self.assertRaises(ValueError):
            metadata_xml(self.demo, base_url="http://localhost:8000")

    def test_upload_csv_xlsx_semicolon_and_decimal_comma(self):
        record = example()
        for payload, name in ((csv_upload([record]), "aed.csv"), (xlsx_upload([record]), "aed.xlsx")):
            report = validate_upload(payload, name)
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(report["normalized_json"][0]["kod_pocztowy"], "00-002")
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=field_names(), delimiter=";")
        writer.writeheader()
        writer.writerow({k: str(record[k]).replace(".", ",") if k in ("lat", "lon") else record.get(k) for k in field_names()})
        self.assertTrue(validate_upload(stream.getvalue().encode("utf-8-sig"), "aed.csv")["valid"])

    def test_upload_all_errors_and_only_valid_output(self):
        bad = example() | {"id_aed": "BAD-001", "lat": 200, "kod_teryt": "123", "status_techniczny": "nieznany"}
        report = validate_upload(csv_upload([example(), bad]), "aed.csv")
        self.assertFalse(report["valid"])
        self.assertEqual(report["rows_valid"], 1)
        fields = {e["field"] for e in report["errors"]}
        self.assertTrue({"lat", "kod_teryt", "status_techniczny"}.issubset(fields))
        self.assertEqual(len(report["normalized_json"]), 1)

    def test_upload_missing_columns_duplicates_formula_and_future_date(self):
        report = validate_upload(b"id_aed,lat,lon\nABC,52,21\n", "aed.csv")
        self.assertIn("missing_column", {e["code"] for e in report["errors"]})
        report = validate_upload(csv_upload([example(), example()]), "aed.csv")
        self.assertEqual(report["rows_valid"], 0)
        self.assertIn("duplicate_id", {e["code"] for e in report["errors"]})
        report = validate_upload(xlsx_upload([example()], formula=True), "aed.xlsx")
        self.assertIn("formula", {e["code"] for e in report["errors"]})
        report = validate_upload(csv_upload([example() | {"data_aktualizacji": "2999-01-01"}]), "aed.csv")
        self.assertIn("date", {e["code"] for e in report["errors"]})

    def test_malformed_csv_and_xlsx_xml_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_upload(b'"unclosed', "aed.csv")
        valid = xlsx_upload([example()])
        stream = io.BytesIO()
        with ZipFile(io.BytesIO(valid)) as original, ZipFile(stream, "w") as modified:
            for item in original.infolist():
                modified.writestr(item.filename, b"<broken" if item.filename == "xl/worksheets/sheet1.xml" else original.read(item.filename))
        with self.assertRaises(ValueError):
            validate_upload(stream.getvalue(), "aed.xlsx")

    def test_actual_workbook_upload(self):
        from .schema import SCHEMA_PATH
        report = validate_upload(SCHEMA_PATH.read_bytes(), "wzorzec.xlsx")
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["rows_valid"], 5)
        wroclaw = next(r for r in report["normalized_json"] if r["id_aed"] == "DEMO-WRO-004")
        self.assertEqual(wroclaw["kod_teryt"], "0264011")

    def test_endpoints_filters_upload_and_download_types(self):
        with TestClient(create_app(records=self.demo, clock=lambda: MONDAY)) as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn('<html lang="pl">', response.text)
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["service"], "otwarte-aed")
            self.assertEqual(health.json()["records"], 4)
            for asset in ("app.js", "core.js", "styles.css", "vendor/leaflet.js", "vendor/qrcode.js"):
                self.assertEqual(client.get("/frontend/" + asset).status_code, 200)
            template = client.get("/data-standard/wzorzec_danych_aed.xlsx")
            self.assertEqual(template.status_code, 200)
            self.assertTrue(template.content.startswith(b"PK"))
            all_rows = client.get("/api/aed", params={"miasto": "wArSzAwA", "tylko_otwarte_teraz": "false"}).json()
            self.assertEqual(all_rows["count"], 4)
            opened = client.get("/api/aed?tylko_otwarte_teraz=true").json()
            self.assertEqual(opened["count"], 2)
            self.assertEqual(client.get("/api/aed?miasto=Kraków").json()["count"], 0)
            self.assertEqual(client.get("/api/aed?tylko_otwarte_teraz=abc").status_code, 422)
            for fmt, mime in (("csv", "text/csv"), ("json", "application/json"), ("geojson", "application/geo+json"), ("xml", "application/xml")):
                response = client.get("/export/" + fmt)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.headers["content-type"].startswith(mime))
                self.assertIn("attachment", response.headers["content-disposition"])
            self.assertEqual(client.get("/export/pdf").status_code, 404)
            for data, name in ((csv_upload([example()]), "aed.csv"), (xlsx_upload([example()]), "aed.xlsx")):
                response = client.post("/api/validate-upload", files={"file": (name, data)})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["valid"])
            self.assertEqual(client.get("/api/aed").json()["count"], 4)  # Upload nie publikuje.
            self.assertEqual(client.post("/api/validate-upload", files={"file": ("aed.pdf", b"test")}).status_code, 415)
            self.assertEqual(client.post("/api/validate-upload", files={"file": ("aed.xlsx", b"broken")}).status_code, 400)
            self.assertEqual(client.post("/api/validate-upload", files={"file": ("aed.csv", b"x" * (MAX_UPLOAD_BYTES + 1))}).status_code, 413)

    def test_real_offline_pipeline_writes_four_formats_and_report(self):
        with TemporaryDirectory() as directory:
            records, report = run_pipeline(offline=True, output_dir=Path(directory))
            self.assertGreater(len(records), 0)
            self.assertTrue(report["source"]["from_cache"])
            self.assertFalse(any(r["is_demo"] for r in records))
            self.assertEqual(json.loads((Path(directory) / "aed_polska.json").read_text(encoding="utf-8")), records)
            validate_metadata((Path(directory) / "harvester_metadata.xml").read_bytes())
            self.assertEqual(set(report["files_sha256"]), {"aed_polska.csv", "aed_polska.json", "aed_polska.geojson", "harvester_metadata.xml", "danegov_api_payload.json"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
