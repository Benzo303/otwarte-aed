"""Scenariusze ratunkowe, paszporty, trwałość zgłoszeń i importer BIP/PDF."""
import copy
import io
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from fastapi.testclient import TestClient
import httpx
from .chaos_import import coordinate, clean_import, download_public
from .feature_store import FeatureStore
from .features_api import passport_svg
from .main import create_app
from .quality_audit import audit_cache, in_poland
from .rescue import nearest
from .schema import field_names
from .test_pipeline import MONDAY, example


def point(aid="OPEN",lat=52.23,lon=21.01):
    row=example();row.update(id_aed=aid,lat=lat,lon=lon,is_demo=False,miejscowosc="Warszawa",
                            dostepnosc_typ="24_7",godziny_otwarcia_osm="24/7",wymagany_klucz_lub_kod="NIE",conflicts={},merged_ids=[aid],confidence_score=80)
    return row


def pdf_fixture():
    text=b"BT /F1 11 Tf 40 750 Td (Nazwa;Adres;lat;lon) Tj 0 -18 Td (AED;ul. Testowa 1;54.19;16.18) Tj ET"
    objects=[b"<< /Type /Catalog /Pages 2 0 R >>",b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",b"<< /Length "+str(len(text)).encode()+b" >>\nstream\n"+text+b"\nendstream"]
    output=b"%PDF-1.4\n";offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(len(output));output+=f"{i} 0 obj\n".encode()+obj+b"\nendobj\n"
    xref=len(output);output+=f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()
    output+=b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return output+f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()


class FeatureTests(unittest.TestCase):
    def test_nearest_skips_closer_locked_and_damaged_points(self):
        locked=point("LOCK",52.23001);locked.update(dostepnosc_typ="na_klucz_lub_kod",wymagany_klucz_lub_kod="TAK")
        damaged=point("BAD",52.23002);damaged["field_access_alert"]="damaged"
        opened=[point(f"OPEN-{i}",52.23+.001*i) for i in range(1,5)]
        result=nearest([locked,damaged,*opened],52.23,21.01,MONDAY)
        self.assertEqual([r["id_aed"] for r in result["top3"]],["OPEN-1","OPEN-2","OPEN-3"])
        self.assertEqual(result["excluded"]["field_report"],1)
        best=result["top3"][0]
        self.assertAlmostEqual(best["walking_distance_m"],best["straight_distance_m"]*1.25,delta=1)
        self.assertAlmostEqual(best["round_trip_seconds"],2*best["walking_time_seconds"],delta=1)
        self.assertTrue(best["estimated"])

    def test_reports_persist_and_positive_report_cannot_clear_damage(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"aed.db";store=FeatureStore(path);row=point()
            store.report(row["id_aed"],"damaged",MONDAY)
            store.report(row["id_aed"],"working",MONDAY+timedelta(minutes=1))
            current=store.overlay([row],MONDAY+timedelta(minutes=2))[0]
            self.assertEqual(current["field_access_alert"],"damaged")
            self.assertLess(current["confidence_score"],row.get("confidence_score",0))
            store.close();reopened=FeatureStore(path)
            self.assertEqual(reopened.overlay([row],MONDAY+timedelta(minutes=3))[0]["field_reports_count"],2)
            self.assertIsNone(reopened.overlay([row],MONDAY+timedelta(hours=25))[0]["field_access_alert"])
            reopened.close()

    def test_real_qr_svg_and_direct_device_link(self):
        svg,link=passport_svg(point(),"http://localhost:8000/","<script> & AED")
        self.assertEqual(link,"http://localhost:8000/?aed=OPEN")
        document=ElementTree.fromstring(svg)
        self.assertFalse(any(n.tag.endswith("script") for n in document.iter()))
        self.assertIn("&lt;script&gt;",svg)
        self.assertTrue(any(len(n.attrib.get("d",""))>1000 for n in document.iter()))

    def test_dms_decimal_comma_and_exact_21_field_csv(self):
        self.assertAlmostEqual(coordinate('54°11′24″N',"lat"),54.19)
        self.assertEqual(coordinate("16,18","lon"),16.18)
        with self.assertRaises(ValueError):coordinate('54°61′00″N',"lat")
        content='Nazwa;Adres;Szerokość;Długość\nAED;ul. Długa 1;54°11′24″N;16°10′48″E\n'.encode()
        result=clean_import(content,"aed.csv")
        self.assertEqual(result["output_records"],1)
        self.assertEqual(set(result["standard_json"][0]),set(field_names()))
        self.assertEqual(result["normalized_csv"].splitlines()[0].split(","),field_names())
        self.assertFalse(result["publication_ready"])

    def test_combined_dms_and_optional_geocoding_limit(self):
        content='nazwa;współrzędne\nAED;54°11′24″N 16°10′48″E\n'.encode()
        self.assertEqual(clean_import(content,"aed.csv")["output_records"],1)
        content=('nazwa,adres,miejscowosc\n'+''.join(f'AED {i},Testowa {i},Koszalin\n' for i in range(6))).encode()
        with patch("backend.chaos_import.geocode_address",return_value={"lat":54.19,"lon":16.18}) as geocoder:
            result=clean_import(content,"aed.csv",geocode=True)
            self.assertEqual(geocoder.call_count,5)
            self.assertEqual(result["geocoded_addresses"],5)
            self.assertEqual(len(result["pending_records"]),1)

    def test_html_pdf_geojson_are_inputs_not_export_formats(self):
        html=b'<table><tr><th>Nazwa</th><th>lat</th><th>lon</th></tr><tr><td>AED</td><td>54.19</td><td>16.18</td></tr></table>'
        self.assertEqual(clean_import(html,"bip.html",source_url="https://bip.example.org/aed")["output_records"],1)
        self.assertEqual(clean_import(pdf_fixture(),"aed.pdf")["output_records"],1)
        geo={"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"AED"},"geometry":{"type":"Point","coordinates":[16.18,54.19]}}]}
        self.assertEqual(clean_import(json.dumps(geo).encode(),"aed.geojson")["output_records"],1)

    def test_country_check_is_polygon_not_bounding_rectangle(self):
        self.assertTrue(in_poland(54.19,16.18))
        self.assertFalse(in_poland(51.1,14.2))  # Niemcy, mimo zakresu bbox Polski.
        self.assertFalse(in_poland(float("nan"),20))

    def test_malformed_pdf_and_xml_return_validation_errors(self):
        with TestClient(create_app(records=[point()],clock=lambda:MONDAY)) as client:
            for filename,content in [("bad.pdf",b"not a PDF"),("bad.xml",b"<row>")]:
                response=client.post("/api/chaos-import",files={"file":(filename,content)})
                self.assertEqual(response.status_code,422,response.text)
                self.assertIn("Nie mo",response.json()["detail"])

    def test_rescue_respects_local_working_hours_and_unknown_access(self):
        office=point("OFFICE",52.23001)
        office.update(dostepnosc_typ="godziny_pracy",godziny_otwarcia_osm="Mo-Fr 08:00-16:00")
        unknown=point("UNKNOWN",52.23002)
        unknown.update(dostepnosc_typ=None,godziny_otwarcia_osm=None,wymagany_klucz_lub_kod=None)
        weekend=MONDAY+timedelta(days=5)
        result=nearest([office,unknown,point("ALLDAY",52.231)],52.23,21.01,weekend)
        self.assertEqual([r["id_aed"] for r in result["top3"]],["ALLDAY"])
        self.assertEqual(result["excluded"]["unconfirmed"],1)
        self.assertEqual(result["excluded"]["closed_or_locked"],1)

    def test_bip_blocks_private_and_redirect_to_private(self):
        with self.assertRaisesRegex(ValueError,"lokalne"):
            download_public("http://127.0.0.1/aed")
        def dns(host,*args,**kwargs):return [(2,1,6,"",("8.8.8.8" if host=="bip.example.org" else "127.0.0.1",443))]
        response=httpx.Response(302,headers={"location":"http://127.0.0.1/secret"},request=httpx.Request("GET","https://bip.example.org"))
        with patch("backend.chaos_import.socket.getaddrinfo",side_effect=dns),patch("httpx.Client.send",return_value=response) as send:
            with self.assertRaises(ValueError):download_public("https://bip.example.org/aed")
            self.assertEqual(send.call_count,1)

    def test_new_endpoints_and_legacy_api_share_field_alerts(self):
        with TestClient(create_app(records=[point()],clock=lambda:MONDAY)) as client:
            self.assertEqual(client.get("/api/aed/OPEN").status_code,200)
            svg=client.get("/api/aed/OPEN/passport.svg")
            self.assertEqual(svg.status_code,200);self.assertIn("image/svg+xml",svg.headers["content-type"])
            self.assertEqual(client.post("/api/rescue/nearest",json={"lat":52.23,"lon":21.01}).json()["count"],1)
            report=client.post("/api/aed/OPEN/report",json={"kind":"damaged"})
            self.assertTrue(report.json()["saved"])
            self.assertEqual(client.get("/api/aed?tylko_otwarte_teraz=true").json()["count"],0)
            self.assertEqual(client.post("/api/rescue/nearest",json={"lat":52.23,"lon":21.01}).json()["count"],0)
            self.assertEqual(client.post("/api/aed/OPEN/report",json={"kind":"invented"}).status_code,422)
            self.assertEqual(client.get("/export/pdf").status_code,404)

    def test_import_preview_is_durable_and_separate_from_public_records(self):
        with TestClient(create_app(records=[point()],clock=lambda:MONDAY)) as client:
            response=client.post("/api/chaos-import",files={"file":("aed.csv",b"name,lat,lon\nAED,54.19,16.18\n")})
            self.assertEqual(response.status_code,200,response.text)
            data=response.json();self.assertEqual(data["output_records"],1)
            self.assertTrue(client.post(f"/api/import/{data['import_id']}/preview").json()["active"])
            self.assertEqual(client.get("/api/import/preview").json()["count"],1)
            self.assertEqual(client.get("/api/aed").json()["count"],1)
            html=b'<table><tr><th>name</th><th>lat</th><th>lon</th></tr><tr><td>AED</td><td>54.19</td><td>16.18</td></tr></table>'
            with patch("backend.features_api.download_public",return_value=(html,"text/html","https://bip.example.org/aed")):
                self.assertEqual(client.post("/api/import/bip-url",json={"url":"https://bip.example.org/aed"}).json()["output_records"],1)

    def test_audit_scores_real_source_data(self):
        audit=audit_cache();self.assertEqual(len(audit["ranking"]),4)
        self.assertTrue(all(0<=r["score"]<=100 and r["grade"] in "ABCDEF" for r in audit["ranking"]))
        self.assertEqual(next(d for d in audit["datasets"] if d["dataset_id"]=="39512")["grade"],"F")
        self.assertTrue(any("Godziny" in error for r in audit["ranking"] for error in r["errors"]))


if __name__=="__main__":unittest.main(verbosity=2)
