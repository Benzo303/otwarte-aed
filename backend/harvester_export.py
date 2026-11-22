"""Maszynowe eksporty oraz XML harvestera walidowany oficjalnym XSD 1.13."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from lxml import etree

from .fetcher import AREAS, fetch_institutional, fetch_osm, load_city_contexts
from .normalizer import normalize_sources
from .danegov_client import fetch_danegov, source_summary
from .schema import field_names

ROOT = Path(__file__).resolve().parent
EXPORT_DIR = ROOT / "exports"
XSD_PATH = ROOT / "schemas" / "otwarte_dane_latest.xsd"
NS = "urn:otwarte-dane:harvester:1.13"
XSD_URL = "https://dane.gov.pl/static/xml/otwarte_dane_latest.xsd"
EXTRA_FIELDS = ["confidence_score", "schema_valid", "is_demo", "sources", "merged_ids", "conflicts",
                "quality_errors", "deduplication_review_required", "deduplication_max_distance_m"]
LICENSES = {
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "ODbL-1.0": "https://opendatacommons.org/licenses/odbl/1-0/",
}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def csv_text(records, *, extensions=True):
    stream = io.StringIO(newline="")
    columns = field_names() + (EXTRA_FIELDS if extensions else [])
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for record in records:
        writer.writerow({key: json.dumps(record.get(key), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                         if isinstance(record.get(key), (list, dict, bool)) else record.get(key)
                         for key in columns})
    return stream.getvalue()


def geojson(records):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": row["id_aed"],
         "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
         "properties": {k: v for k, v in row.items() if k not in ("lat", "lon")}}
        for row in records
    ]}


def validate_metadata(xml: bytes):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    schema = etree.XMLSchema(etree.parse(str(XSD_PATH), parser))
    schema.assertValid(etree.fromstring(xml, parser))


def metadata_xml(records, *, base_url, area="warszawa", generated_at=None, license_id=None,
                 update_frequency="irregular", source_info=None):
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Harvester wymaga bazowego publicznego URL HTTPS bez query/fragmentu.")
    base_url = base_url.rstrip("/")
    contains_osm = any(s.get("license") == "ODbL-1.0" for r in records for s in r.get("sources", []))
    unknown_license = any(not s.get("license") for r in records for s in r.get("sources", []))
    contains_ccby = any(s.get("license") == "CC-BY-4.0" for r in records for s in r.get("sources", []))
    license_id = license_id or ("ODbL-1.0" if contains_osm else "CC-BY-4.0" if contains_ccby else "CC0-1.0")
    if contains_osm and license_id != "ODbL-1.0":
        raise ValueError("Danych pochodnych OSM nie można oznaczyć jako CC0/CC BY; zachowaj ODbL-1.0.")
    if unknown_license:
        raise ValueError("Nie określono praw do wszystkich źródeł. Walidacja uploadu nie nadaje licencji.")
    if contains_ccby and license_id == "CC0-1.0":
        raise ValueError("Źródła CC BY wymagają zachowania autorstwa; nie można nadać CC0.")
    if license_id not in LICENSES:
        raise ValueError("Nieobsługiwana licencja.")
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        raise ValueError("Czas generowania musi zawierać strefę.")
    root = etree.Element(f"{{{NS}}}datasets", nsmap={"p": NS, "xsi": "http://www.w3.org/2001/XMLSchema-instance"})
    root.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", f"{NS} {XSD_URL}")

    def add(parent, name, value):
        node = etree.SubElement(parent, name)
        node.text = str(value)
        return node

    def localized(parent, name, value):
        node = etree.SubElement(parent, name)
        add(node, "polish", value)

    ds = etree.SubElement(root, "dataset", status="published")
    add(ds, "extIdent", f"otwarte-aed-{area}")
    localized(ds, "title", f"Otwarte AED — {AREAS[area]['name']}")
    description = ("Zintegrowane lokalizacje defibrylatorów, dostępność i jakość danych. "
                   f"Zasięg: {AREAS[area]['name']}. "
                   "Braki źródłowe zachowano jako null; raport quality_errors wskazuje niezgodności ze wzorcem. "
                   "confidence_score mierzy kompletność z premią 10 pkt za instytucjonalne źródło dane.gov.pl; nie mierzy sprawności urządzenia. "
                   f"Dysponent integracji: projekt Otwarte AED. Licencja: {license_id}, {LICENSES[license_id]}. ")
    if contains_osm:
        description += "© OpenStreetMap contributors. https://www.openstreetmap.org/copyright. "
    if any(r.get("is_demo") for r in records):
        description += "UWAGA: paczka zawiera jawnie oznaczone fikcyjne rekordy DEMO na CC0-1.0. "
    if source_info and source_info.get("retrieved_at"):
        description += f"OSM pobrano: {source_info['retrieved_at']}; cache={source_info.get('from_cache', False)}. "
    localized(ds, "description", description)
    add(ds, "updateFrequency", update_frequency)
    categories = etree.SubElement(ds, "categories")
    add(categories, "category", "HEAL")
    add(categories, "category", "JUST")
    conditions = etree.SubElement(ds, "conditions")
    add(conditions, "source", "false" if license_id == "CC0-1.0" else "true")
    add(conditions, "dbOrCopyrighted", f"{license_id}: {LICENSES[license_id]}" +
        ("; © OpenStreetMap contributors, https://www.openstreetmap.org/copyright" if contains_osm else "; Otwarte AED") +
        "; " + "; ".join(sorted({s['name'] for r in records for s in r.get('sources', []) if s.get('dataset_id')})))
    if license_id != "ODbL-1.0":
        add(conditions, "dbOrCopyrightedLicenseChosen", {"CC0-1.0": "CC0 1.0", "CC-BY-4.0": "CC BY 4.0"}[license_id])
    resources = etree.SubElement(ds, "resources")
    for fmt in ("csv", "json", "geojson"):
        node = etree.SubElement(resources, "resource", status="published")
        add(node, "extIdent", f"aed-{area}-{fmt}")
        add(node, "url", f"{base_url}/export/{fmt}")
        localized(node, "title", f"AED {AREAS[area]['name']} — {fmt.upper()}")
        localized(node, "description", f"Maszynowy format {fmt.upper()}, kodowanie UTF-8. " + description)
        add(node, "availability", "remote")
        # dataDate celowo pomijana: dzień eksportu nie potwierdza aktualności każdego punktu.
        add(node, "lastUpdateDate", generated_at.isoformat())
    tags = etree.SubElement(ds, "tags")
    for word in ("AED", "defibrylatory", "dostępność", "zdrowie"):
        node = add(tags, "tag", word)
        node.set("lang", "pl")
    add(ds, "lastUpdateDate", generated_at.isoformat())
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    validate_metadata(xml)
    return xml


def danegov_api_payload(records, *, base_url, area="polska", update_frequency="irregular", generated_at=None):
    """Dokument JSON:API odpowiada publicznym obiektom Dataset/Resource 1.4.

    To paczka do uzgodnienia z dysponentem: publiczne API NIE ma POST/PATCH.
    Identyfikatory są lokalne, przed publikacją zastąpi je portal.
    """
    contains_osm = any(s.get("license") == "ODbL-1.0" for r in records for s in r.get("sources", []))
    licenses = {s.get("license") for r in records for s in r.get("sources", [])}
    license_id = "ODbL-1.0" if contains_osm else "CC-BY-4.0" if "CC-BY-4.0" in licenses else "CC0-1.0"
    license_name = {"ODbL-1.0": "ODbL 1.0", "CC-BY-4.0": "CC BY 4.0", "CC0-1.0": "CC0 1.0"}[license_id]
    configured = ".example." not in base_url and "example.org" not in base_url
    now = generated_at or datetime.now(timezone.utc)
    dataset_id = f"otwarte-aed-{area}"
    ids = [f"{dataset_id}-{fmt}" for fmt in ("csv", "json", "geojson")]
    sources = sorted({s.get("name", "") for r in records for s in r.get("sources", [])})
    return {"jsonapi": {"version": "1.0"},
            "data": {"type": "dataset", "id": dataset_id,
                     "attributes": {"title": f"Otwarte AED — {AREAS[area]['name']}",
                                    "notes": "Zintegrowane lokalizacje AED z dane.gov.pl i OpenStreetMap. Źródła i rozbieżności podano przy rekordach. Niezweryfikowana dostępność nie oznacza dostępu do AED.",
                                    "update_frequency": {"daily": "Codziennie", "weekly": "Co tydzień", "monthly": "Co miesiąc", "irregular": "Nieregularnie"}[update_frequency],
                                    "license_name": license_name, "license_condition_default_cc40": license_id == "CC-BY-4.0",
                                    "license_condition_db_or_copyrighted": f"{license_name}: {LICENSES[license_id]}",
                                    "license_condition_custom_description": "; ".join(sources),
                                    "categories": [{"code": "HEAL", "title": "Zdrowie"},
                                                   {"code": "JUST", "title": "Sprawiedliwość, ustrój sądów i bezpieczeństwo publiczne"}],
                                    "keywords": ["AED", "defibrylatory", "bezpieczeństwo", "zdrowie"], "formats": ["csv", "json", "geojson"]},
                     "relationships": {"resources": {"data": [{"type": "resource", "id": rid} for rid in ids]}}},
            "included": [{"type": "resource", "id": rid,
                          "attributes": {"title": f"Otwarte AED {AREAS[area]['name']} — {fmt.upper()}", "format": fmt,
                                         "file_url": f"{base_url.rstrip('/')}/export/{fmt}", "download_url": f"{base_url.rstrip('/')}/export/{fmt}",
                                         "description": f"UTF-8; {len(records)} rekordów; pochodzenie i jakość w każdym rekordzie.",
                                         "language": "pl", "media_type": "file"},
                          "relationships": {"dataset": {"data": {"type": "dataset", "id": dataset_id}}}}
                         for fmt, rid in zip(("csv", "json", "geojson"), ids)],
            "meta": {"api_base_url": "https://api.dane.gov.pl/1.4", "generated_at": now.isoformat(),
                     "publication_method": "harvester_xml_or_provider_panel", "public_api_write_supported": False,
                     "ids_are_local": True, "public_urls_configured": configured, "requested_license": "CC0 1.0",
                     "license_note": "OSM wymaga zachowania ODbL; CC0 wolno nadać wyłącznie odrębnemu zbiorowi ze źródeł CC0.",
                     "publication_blockers": (["Ustaw AED_PUBLIC_BASE_URL na publiczny adres HTTPS."] if not configured else []) +
                         ["Przypisz dysponenta i identyfikatory portalu w panelu dostawcy; publiczne API 1.4 udostępnia tylko GET."],
                     "sources": sources}}


def publication_bundle(records, *, base_url="https://aed.example.org", area="warszawa", generated_at=None,
                       license_id=None, update_frequency="irregular", source_info=None):
    return {
        "aed_polska.csv": csv_text(records).encode("utf-8"),
        "aed_polska.json": json_bytes(records),
        "aed_polska.geojson": json_bytes(geojson(records)),
        "harvester_metadata.xml": metadata_xml(records, base_url=base_url, area=area, generated_at=generated_at,
                                               license_id=license_id, update_frequency=update_frequency, source_info=source_info),
        "danegov_api_payload.json": json_bytes(danegov_api_payload(records, base_url=base_url, area=area,
                                                                  generated_at=generated_at, update_frequency=update_frequency)),
    }


def write_bundle(bundle, output_dir):
    """Każdy plik jest wymieniany atomowo; manifest zapisywany na końcu."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in bundle.items():
        with tempfile.NamedTemporaryFile(dir=output_dir, delete=False, suffix=".tmp") as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        os.replace(temporary, output_dir / name)
    xml_md5 = hashlib.md5(bundle["harvester_metadata.xml"]).hexdigest()  # Suma wymagana przez mechanizm importu, nie zabezpieczenie.
    (output_dir / "harvester_metadata.md5").write_text(xml_md5 + "\n", encoding="ascii")


def build_snapshot(*, area="polska", offline=True, include_demo=False, base_url="https://aed.example.org",
                   update_frequency="irregular", osm_offline=None):
    if include_demo and area != "warszawa":
        raise ValueError("Przykładowy rejestr DEMO obejmuje tylko Warszawę.")
    fetched = fetch_osm(area, offline=offline if osm_offline is None else osm_offline)
    official = fetch_danegov(offline=offline) if area == "polska" else None
    institutional = fetch_institutional() if include_demo else []
    city_contexts = load_city_contexts() if area == "polska" else {}
    records, rejected = normalize_sources(fetched.elements, institutional, AREAS[area], official.records if official else (),
                                          locality_contexts=city_contexts)
    if not records:
        raise ValueError("Brak rekordów z poprawnymi współrzędnymi; zachowano dotychczasowe eksporty.")
    generated = datetime.now(timezone.utc)
    bundle = publication_bundle(records, base_url=base_url, area=area, generated_at=generated,
                                update_frequency=update_frequency, source_info=fetched.metadata)
    report = {"generated_at": generated.isoformat(), "area": area, "source": fetched.metadata,
              "input_osm": len(fetched.elements), "input_institutional_demo": len(institutional),
              "input_danegov": len(official.records) if official else 0,
              "danegov": source_summary(official.metadata) if official else {"datasets": [], "from_cache": False},
              "output_records": len(records), "schema_valid_records": sum(r["schema_valid"] for r in records),
              "duplicates_merged": len(fetched.elements) + len(institutional) + (len(official.records) if official else 0) - len(rejected) - len(records),
              "cross_source_groups": sum(any(s.get("dataset_id") for s in r["sources"]) and any(s.get("name") == "OpenStreetMap" for s in r["sources"]) for r in records),
              "demo_records": sum(r["is_demo"] for r in records), "rejected_records": rejected,
              "base_url": base_url, "public_urls_configured": ".example." not in base_url and "example.org" not in base_url,
              "files_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in bundle.items()}}
    return records, report, bundle


def run_pipeline(*, area="polska", offline=False, include_demo=False, base_url="https://aed.example.org",
                 output_dir=EXPORT_DIR, update_frequency="irregular", osm_offline=None):
    records, report, bundle = build_snapshot(area=area, offline=offline, include_demo=include_demo, base_url=base_url,
                                            update_frequency=update_frequency, osm_offline=osm_offline)
    write_bundle(bundle, output_dir)
    (Path(output_dir) / "pipeline_report.json").write_bytes(json_bytes(report))
    return records, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", choices=AREAS, default="polska")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--include-demo", action="store_true")
    parser.add_argument("--base-url", default=os.getenv("AED_PUBLIC_BASE_URL", "https://aed.example.org"))
    parser.add_argument("--output-dir", type=Path, default=EXPORT_DIR)
    parser.add_argument("--update-frequency", choices=("irregular", "daily", "weekly", "monthly"), default="irregular")
    args = parser.parse_args()
    _, report = run_pipeline(area=args.area, offline=args.offline, include_demo=args.include_demo,
                             base_url=args.base_url, output_dir=args.output_dir, update_frequency=args.update_frequency)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
