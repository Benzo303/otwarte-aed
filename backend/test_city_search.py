"""Regresje: AED bez miejscowości, granice, cache i brak autocomplete."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import requests

from .city_search import CityResolver, CitySearchError, city_key, contains, select_city
from .main import create_app
from .test_pipeline import example, MONDAY


def city():
    return {"name": "Miasto", "display_name": "Miasto, Polska", "bounds": [50, 54, 20, 24],
            "geometry": {"type": "Polygon", "coordinates": [
                [[20,50],[24,50],[24,54],[20,54],[20,50]],
                [[21,51],[22,51],[22,52],[21,52],[21,51]]]},
            "osm_id": "relation/123", "source": "OpenStreetMap / Nominatim", "retrieved_at": "2026-11-21T12:00:00+00:00"}


def document():
    return [{"name": "Miasto", "display_name": "Miasto, Polska", "osm_type": "relation", "osm_id": 123,
             "addresstype": "city", "address": {"country_code": "pl"}, "geojson": city()["geometry"]}]


class CitySearchTests(unittest.TestCase):
    def test_polygon_holes_boundary_and_multipolygon(self):
        shape = city()
        self.assertTrue(contains(shape, 53, 23))
        self.assertFalse(contains(shape, 51.5, 21.5))
        self.assertFalse(contains(shape, 49, 23))
        self.assertTrue(contains(shape, 50, 20))
        self.assertTrue(contains(shape, 51, 21))
        self.assertFalse(contains(shape, None, 21))
        multi = copy.deepcopy(shape)
        multi["geometry"] = {"type": "MultiPolygon", "coordinates": [shape["geometry"]["coordinates"]]}
        self.assertTrue(contains(multi, 53, 23))

    def test_normalized_spelling_and_ambiguous_names(self):
        self.assertEqual(city_key("  ŁÓDŹ "), city_key("lodz"))
        self.assertEqual(select_city(document(), "miasto")["osm_id"], "relation/123")
        duplicate = copy.deepcopy(document()[0]); duplicate["osm_id"] = 456; duplicate["display_name"] = "Miasto, Inny powiat, Polska"
        with self.assertRaisesRegex(CitySearchError, "niejednoznaczna"):
            select_city(document() + [duplicate], "Miasto")
        with self.assertRaises(CitySearchError):
            select_city(document(), "Inne miasto")
        village = copy.deepcopy(document()[0]); village["osm_id"] = 789; village["addresstype"] = "village"
        self.assertEqual(select_city(document() + [village], "Miasto")["osm_id"], "relation/123")

    def test_real_lookup_is_cached_and_autocomplete_never_uses_network(self):
        session = Mock(); session.get.return_value.json.return_value = document(); session.get.return_value.content = b"[]"
        with TemporaryDirectory() as directory:
            resolver = CityResolver(cache_path=Path(directory)/"cities.json", session=session)
            self.assertIsNone(resolver.resolve("Miasto", allow_lookup=False))
            session.get.assert_not_called()
            with patch("backend.city_search.time.sleep"):
                first = resolver.resolve("Miasto")
            self.assertFalse(first["from_cache"])
            session.get.side_effect = requests.Timeout("offline")
            second = resolver.resolve("MIASTO")
            self.assertTrue(second["from_cache"])
            self.assertEqual(session.get.call_count, 1)
            self.assertEqual(session.get.call_args.kwargs["params"]["countrycodes"], "pl")
            self.assertEqual(first["geometry"], second["geometry"])

    def test_unavailable_geocoder_is_reported_not_returned_as_zero_aed(self):
        session = Mock(); session.get.side_effect = requests.Timeout("offline")
        with TemporaryDirectory() as directory:
            resolver = CityResolver(cache_path=Path(directory)/"cities.json", session=session)
            with patch("backend.city_search.time.sleep"), self.assertRaises(CitySearchError) as error:
                resolver.resolve("Miasto")
            self.assertEqual(error.exception.status_code, 503)

    def test_city_api_selects_coordinates_even_when_city_field_is_empty(self):
        inside = example(); inside["lat"] = 53; inside["lon"] = 23; inside["miejscowosc"] = None
        outside = copy.deepcopy(inside); outside["id_aed"] = "OUTSIDE"; outside["lat"] = 49; outside["miejscowosc"] = "Miasto"
        resolver = Mock(); resolver.resolve.return_value = city()
        with TestClient(create_app(records=[inside,outside], clock=lambda: MONDAY, city_resolver=resolver)) as client:
            result = client.get("/api/aed?miasto=Miasto&tylko_otwarte_teraz=true").json()
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["items"][0]["id_aed"], inside["id_aed"])
            self.assertEqual(result["items"][0]["miejscowosc_wyszukiwania"], "Miasto")
            self.assertIsNone(result["items"][0]["miejscowosc"])
            self.assertEqual(result["city"]["bounds"], city()["bounds"])
            self.assertNotIn("geometry", result["city"])
            resolver.resolve.side_effect = CitySearchError("Doprecyzuj miasto.", 422)
            response = client.get("/api/aed?miasto=Nieznane")
            self.assertEqual(response.status_code, 422)
            self.assertIn("Doprecyzuj", response.json()["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
