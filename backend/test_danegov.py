"""Kontrakty klienta, parserów, awarii sieci i atomowej synchronizacji API."""
import base64
import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient
from openpyxl import Workbook

from .danegov_client import (BASE_URL, CACHE_PATH, DaneGovClient, normalize_table_row,
                            parse_rows, public_url, source_summary)
from .normalizer import deduplicate, confidence_score, validate_record
from .harvester_export import build_snapshot, danegov_api_payload, metadata_xml
from .main import create_app
from .test_pipeline import MONDAY, example


DS = {"type": "dataset", "id": "123", "attributes": {"title": "Defibrylatory AED", "license_name": "CC0 1.0"},
      "relationships": {"institution": {"data": {"type": "institution", "id": "10"}}}}
RES = {"type": "resource", "id": "99", "attributes": {"format": "csv", "file_url": "https://api.dane.gov.pl/media/a.csv"}}


def official(raw=None):
    return normalize_table_row(raw or {"id": "1", "lat": 52.2, "lon": 21.0, "nazwa": "Urząd"}, DS, RES, "Urząd Miasta")


class DaneGovTests(unittest.TestCase):
    def test_polish_aliases_address_comma_decimal_and_wkt(self):
        row = official({"Numer Id": 7, "Szerokość geograficzna": "52,2", "Długość geograficzna": "21,0", "Lokalizacja": "Hol", "Adres": "ul. Testowa 1, 00-001 Warszawa"})
        self.assertEqual((row["lat"], row["lon"], row["miejscowosc"]), (52.2, 21.0, "Warszawa"))
        self.assertEqual(row["zrodlo_referencyjne"], "dane.gov.pl [ID: 123 - Urząd Miasta]")
        self.assertEqual(row["ulica_numer"], "ul. Testowa 1")
        self.assertNotIn("url", [e["code"] for e in validate_record(row)])
        for raw in ({"geom": "POINT(21 52.2)"}, {"geom": "SRID=4326;POINT(21 52.2)"}, {"x": 21, "y": 52.2},
                    {"longitude": 21, "latitude": 52.2}, {"lng": 21, "szerokosc": 52.2}):
            self.assertEqual(official(raw)["lat"], 52.2)

    def test_axis_swap_is_explicit_and_projected_points_are_rejected(self):
        row = official({"lon": 52.2, "lat": 21})
        self.assertEqual((row["lat"], row["lon"]), (52.2, 21))
        self.assertTrue(row["sources"][0]["parser_warnings"])
        for raw in ({"lat": float("nan"), "lon": 21}, {"x": 600000, "y": 500000}, {"geom": "POINT(21 52 0)"}):
            with self.assertRaises(ValueError):
                official(raw)

    def test_csv_xlsx_json_geojson_xml_parsers(self):
        for content in (b'lat;lon;nazwa\n52.2;21;Office', b'"lat,lon,nazwa"\n"52.2,21,Office"'):
            self.assertEqual(len(parse_rows(content, "csv")), 1)
            self.assertEqual(official(parse_rows(content, "csv")[0])["lat"], 52.2)
        book = Workbook(); book.active.append(["Tytuł tabeli"]); book.active.append(["lat", "lon", "nazwa"]); book.active.append([52.2, 21, "Hol"])
        stream = io.BytesIO(); book.save(stream); book.close()
        self.assertEqual(official(parse_rows(stream.getvalue(), "xlsx")[0])["lon"], 21)
        feature = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "Hol"}, "geometry": {"type": "Point", "coordinates": [21, 52.2]}}]}
        self.assertEqual(official(parse_rows(json.dumps(feature).encode(), "geojson")[0])["lat"], 52.2)
        nested = {"result": {"records": [{"name": "Hol", "geometry": {"type": "Point", "coordinates": {"lat": 52.2, "long": 21}}}]}}
        self.assertEqual(official(parse_rows(json.dumps(nested).encode(), "json")[0])["lat"], 52.2)
        xml = b'<records><record><lat>52.2</lat><lon>21</lon></record></records>'
        self.assertEqual(official(parse_rows(xml, "xml")[0])["lat"], 52.2)
        for fmt, content in (("json", b'<!DOCTYPE html><html>login</html>'), ("xml", b'<!DOCTYPE x [<!ENTITY a "evil">]><records/>')):
            with self.assertRaises(ValueError):
                parse_rows(content, fmt)

    def test_pagination_uses_page_per_page_and_all_queries(self):
        session = Mock(); session.headers = {}
        responses = [{"data": [DS] * 50, "meta": {"count": 51}}, {"data": [DS], "meta": {"count": 51}}]
        session.get.side_effect = [Mock(status_code=200, json=Mock(return_value=d)) for d in responses]
        client = DaneGovClient(session=session)
        self.assertEqual(len(list(client.pages(BASE_URL + "/datasets", {"q": "AED"}))), 2)
        self.assertEqual([c.kwargs["params"] for c in session.get.call_args_list],
                         [{"q": "AED", "per_page": 50, "page": 1}, {"q": "AED", "per_page": 50, "page": 2}])
        self.assertEqual(session.headers["Accept"], "application/vnd.api+json")

    def test_realistic_fetch_cache_and_timeout_keep_original_files(self):
        session = Mock(); session.headers = {}
        queries = []
        def respond(url, **kwargs):
            body = None
            if url.endswith("/datasets"):
                queries.append(kwargs["params"]["q"]); body = {"data": [DS], "meta": {"count": 1}}
            elif "/institutions/" in url:
                body = {"data": {"attributes": {"title": "Urząd Miasta"}}}
            elif url.endswith("/resources"):
                body = {"data": [RES, {"id": "pdf", "attributes": {"format": "pdf"}}], "meta": {"count": 2}}
            response = Mock(status_code=200)
            response.json.return_value = body
            response.iter_content.return_value = iter([b'lat,lon,nazwa\n52.2,21,Office\n'])
            return response
        session.get.side_effect = respond
        with TemporaryDirectory() as directory:
            path = Path(directory) / "danegov_cache.json"
            result = DaneGovClient(session=session, cache_path=path).fetch()
            self.assertEqual(queries, ["AED", "defibrylator", "defibrylatory"])
            self.assertEqual(len(result.records), 1)
            self.assertEqual(result.metadata["datasets"][0]["resources"][1]["status"], "unsupported_format")
            original = path.read_bytes()
            self.assertNotIn("raw_base64", json.dumps(source_summary(result.metadata)))
            session.get.side_effect = requests.Timeout("offline")
            fallback = DaneGovClient(session=session, cache_path=path).fetch()
            self.assertTrue(fallback.metadata["from_cache"])
            self.assertEqual(fallback.records, result.records)
            self.assertEqual(path.read_bytes(), original)

    def test_official_priority_score_provenance_and_access_conflicts(self):
        osm = example(); osm["is_demo"] = False; osm["lat"] = 52.2; osm["lon"] = 21
        osm["sources"] = [{"name": "OpenStreetMap", "url": "https://www.openstreetmap.org/node/1", "license": "ODbL-1.0"}]
        osm["zrodlo_referencyjne"] = osm["sources"][0]["url"]
        gov = official({"lat": 52.2, "lon": 21, "name": "Oficjalna nazwa", "dostepnosc_typ": "niedostepny", "godziny_otwarcia_osm": "off"})
        no_authority = copy.deepcopy(gov); no_authority["sources"] = []
        self.assertEqual(confidence_score(gov) - confidence_score(no_authority), 10)
        merged = deduplicate([osm, gov])[0]
        self.assertEqual(merged["nazwa_obiektu"], "Oficjalna nazwa")
        self.assertIn("dane.gov.pl [ID: 123", merged["zrodlo_referencyjne"])
        self.assertIn("openstreetmap.org", merged["zrodlo_referencyjne"])
        self.assertIn("dostepnosc_typ", merged["conflicts"])

    def test_payload_is_jsonapi_and_does_not_relicense_osm(self):
        cc0 = danegov_api_payload([official()], base_url="https://aed.example.org")
        self.assertEqual(cc0["data"]["attributes"]["license_name"], "CC0 1.0")
        row = official(); row["sources"].append({"license": "ODbL-1.0", "name": "OpenStreetMap"})
        payload = danegov_api_payload([row], base_url="https://aed.example.org")
        self.assertEqual(payload["data"]["type"], "dataset")
        self.assertTrue(all(r["type"] == "resource" for r in payload["included"]))
        self.assertEqual(payload["data"]["attributes"]["license_name"], "ODbL 1.0")
        self.assertFalse(payload["meta"]["public_api_write_supported"])
        self.assertTrue(payload["meta"]["publication_blockers"])

    def test_refresh_failure_and_success_use_atomic_snapshot(self):
        initial = [example()]
        with TestClient(create_app(records=initial, clock=lambda: MONDAY)) as client:
            before = client.get("/export/json").content
            with patch("backend.main.build_snapshot", side_effect=RuntimeError("sieć")):
                self.assertEqual(client.post("/api/danegov/refresh").status_code, 503)
            self.assertEqual(client.get("/export/json").content, before)
            report = {"area": "polska", "source": {}, "generated_at": MONDAY.isoformat(), "input_osm": 1, "input_danegov": 1,
                      "duplicates_merged": 1, "cross_source_groups": 1, "danegov": {"datasets": [], "from_cache": True}}
            with patch("backend.main.build_snapshot", return_value=(initial, report, {"aed_polska.json": b'[]'})), \
                 patch("backend.main.write_bundle"), patch.object(Path, "write_bytes"):
                response = client.post("/api/danegov/refresh")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["duplicates_merged"], 1)
            self.assertFalse(response.json()["sync_in_progress"])
            self.assertEqual(client.get("/export/json").content, b'[]')
            self.assertEqual(client.get("/api/sources/stats").json()["osm_records"], 1)

    def test_real_downloaded_cache_records_have_dataset_and_institution(self):
        result = DaneGovClient().fetch(offline=True)
        self.assertGreater(len(result.records), 0)
        self.assertEqual({d["id"] for d in result.metadata["datasets"] if d["records_count"]}, {"3624", "4581", "4955"})
        for row in result.records:
            self.assertTrue(row["sources"][0]["institution_title"])
            self.assertIn(row["sources"][0]["dataset_id"], row["zrodlo_referencyjne"])
        warsaw = next(d for d in result.metadata["datasets"] if d["id"] == "39512")
        self.assertEqual(warsaw["records_count"], 0)
        self.assertIn("HTML", warsaw["resources"][0]["error"])

    def test_nonpublic_urls_are_not_downloaded(self):
        for url in ("file:///etc/passwd", "http://127.0.0.1/a", "http://192.168.0.1/a", "http://localhost/a", "http://[::1]/", "http://u:p@api.dane.gov.pl/a"):
            with self.assertRaises(ValueError):
                public_url(url)

    def test_preview_range_does_not_download_whole_export(self):
        with TestClient(create_app(records=[example()], clock=lambda: MONDAY)) as client:
            full = client.get("/export/json").content
            preview = client.get("/export/json", headers={"Range": "bytes=0-99"})
            self.assertEqual(preview.status_code, 206)
            self.assertEqual(preview.content, full[:100])
            self.assertEqual(preview.headers["content-range"], f"bytes 0-99/{len(full)}")
            self.assertEqual(client.get("/export/json", headers={"Range": "bytes=999999999-"}).status_code, 416)
            self.assertEqual(client.get("/export/json").content, full)

    def test_national_source_filters_preserve_merged_records(self):
        gov = official({"lat": 49.7, "lon": 21.7, "name": "Urząd", "miejscowosc": "Krosno"})
        osm = example(); osm["id_aed"] = "OSM-ONLY"
        osm["sources"] = [{"name": "OpenStreetMap", "url": "https://www.openstreetmap.org/node/1", "license": "ODbL-1.0"}]
        merged = copy.deepcopy(gov); merged["id_aed"] = "DG-AND-OSM"; merged["sources"].extend(osm["sources"])
        with TestClient(create_app(records=[gov, osm, merged], clock=lambda: MONDAY)) as client:
            all_rows = client.get("/api/aed").json()
            self.assertEqual(all_rows["count"], 3)
            self.assertIsNone(all_rows["filters"]["miasto"])
            self.assertEqual(all_rows["area"], "polska")
            gov_rows = client.get("/api/aed?zrodlo=danegov").json()
            self.assertEqual({r["id_aed"] for r in gov_rows["items"]}, {gov["id_aed"], "DG-AND-OSM"})
            osm_rows = client.get("/api/aed?zrodlo=osm").json()
            self.assertEqual({r["id_aed"] for r in osm_rows["items"]}, {"OSM-ONLY", "DG-AND-OSM"})
            self.assertEqual(gov_rows["scope"]["danegov_points"], 2)
            self.assertEqual(gov_rows["scope"]["matched_before_availability"], 2)
            self.assertEqual(client.get("/api/aed?zrodlo=bad").status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
