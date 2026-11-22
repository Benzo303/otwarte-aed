"""FastAPI. Start: .venv/Scripts/python.exe -m uvicorn backend.main:app --reload"""
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime
import os
import hashlib
import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response, FileResponse, StreamingResponse
from starlette.middleware.gzip import GZipMiddleware
from .cloud_responses import byte_chunks, streamed_json
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .availability import WARSAW, availability_now
from .city_search import CityResolver, CitySearchError, city_key, contains, public_city
from .fetcher import AREAS
from .harvester_export import publication_bundle, build_snapshot, write_bundle, EXPORT_DIR, json_bytes
from .upload_validation import MAX_UPLOAD_BYTES, validate_upload
from .feature_store import FeatureStore, STATE_PATH
from .features_api import router_for
from .location_search import LocationResolver
from .normalizer import haversine, usable_coordinates


def create_app(*, offline=None, include_demo=False, area=None, records=None, source_metadata=None,
               public_base_url=None, clock=None, city_resolver=None, feature_store=None, location_resolver=None, runtime=None):
    area = area or os.getenv("AED_AREA", "polska")
    if area not in AREAS:
        raise ValueError("Nieobsługiwany obszar AED_AREA.")
    if include_demo and area != "warszawa":
        raise ValueError("Rejestr DEMO obejmuje tylko Warszawę.")
    if offline is None:
        offline = os.getenv("AED_OFFLINE", "true").lower() == "true"
    public_base_url = public_base_url or os.getenv("AED_PUBLIC_BASE_URL", "https://aed.example.org")
    clock = clock or (lambda: datetime.now(WARSAW))
    city_resolver = city_resolver or CityResolver(allow_network=records is None and os.getenv("AED_CITY_OFFLINE", "false").lower() != "true")
    location_resolver=location_resolver or LocationResolver(allow_network=records is None and os.getenv('AED_CITY_OFFLINE','false').lower()!='true')

    @asynccontextmanager
    async def lifespan(app):
        if runtime is not None:
            prepared, report, bundle = await run_in_threadpool(runtime.start)
        elif records is None:
            def prepare():
                return build_snapshot(area=area, offline=offline, include_demo=include_demo, base_url=public_base_url)
            prepared, report, bundle = await run_in_threadpool(prepare)
        else:
            prepared, metadata = records, source_metadata or {"mode": "injected"}
            report = {"area": area, "source": metadata, "generated_at": clock().isoformat(), "input_osm": 0,
                      "input_danegov": 0, "duplicates_merged": 0, "cross_source_groups": 0,
                      "output_records": len(prepared), "danegov": {"datasets": [], "from_cache": False}}
            bundle = await run_in_threadpool(publication_bundle, prepared, base_url=public_base_url, area=area,
                                                  generated_at=clock(), source_info=metadata)
        app.state.snapshot = {"records": prepared, "report": report, "bundle": bundle}
        app.state.feature_store=feature_store or (runtime.store if runtime is not None else FeatureStore(":memory:" if records is not None else STATE_PATH))
        app.state.refresh_lock = asyncio.Lock()
        try:yield
        finally:
            if feature_store is None:app.state.feature_store.close()

    app = FastAPI(title="Otwarte AED", version="0.1.0", lifespan=lifespan)
    if runtime is not None:app.add_middleware(GZipMiddleware,minimum_size=1024)
    upload_limit=3*1024*1024 if runtime is not None else MAX_UPLOAD_BYTES
    def current_snapshot():
        if runtime is not None:app.state.snapshot=runtime.current(app.state.snapshot)
        return app.state.snapshot
    def effective_records():
        return app.state.feature_store.overlay(current_snapshot()["records"],clock())
    app.include_router(router_for(effective_records,lambda:app.state.feature_store,clock,
        before_read=current_snapshot,response_factory=streamed_json if runtime is not None else None,
        upload_limit=upload_limit))

    @app.get('/api/location/search')
    def search_location(q: str=Query(min_length=2,max_length=200)):
        if len(q.strip())<2:raise HTTPException(422,'Wpisz miejscowość lub ulicę.')
        try:return location_resolver.resolve(q.strip())
        except CitySearchError as exc:raise HTTPException(exc.status_code,str(exc)) from exc

    @app.get("/api/health")
    def health():
        root = Path(__file__).resolve().parents[1]
        workspace_id = hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()[:16]
        return {"service": "otwarte-aed", "ready": True, "records": len(app.state.snapshot["records"]),
                "pid": os.getpid(), "workspace_id": workspace_id,
                "listen_host": os.getenv("AED_LISTEN_HOST", "127.0.0.1"),
                **({"cloud":runtime.status()} if runtime is not None else {})}

    def stats(snapshot):
        report = snapshot["report"]
        return {"area": report["area"], "generated_at": report["generated_at"],
                "datasets": report["danegov"]["datasets"], "danegov": report["danegov"],
                "osm_records": report["input_osm"], "danegov_records": report["input_danegov"],
                "duplicates_merged": report["duplicates_merged"], "cross_source_groups": report["cross_source_groups"],
                "integrated_records": len(snapshot["records"]), "osm": report["source"],
                "sync_in_progress": app.state.refresh_lock.locked(),
                **({"persistence":runtime.status()} if runtime is not None else {})}

    @app.get("/api/sources/stats")
    def get_source_stats():
        return stats(current_snapshot())

    @app.post("/api/danegov/refresh")
    async def refresh_danegov():
        if app.state.refresh_lock.locked():
            raise HTTPException(409, "Synchronizacja już trwa. Dotychczasowa migawka pozostaje dostępna.")
        async with app.state.refresh_lock:
            try:
                # Odświeżamy dane.gov.pl; krajowy OSM z trwałej migawki zapobiega blokowaniu demo przez Overpass.
                def rebuild():
                    prepared, report, bundle = build_snapshot(area="polska", offline=False, osm_offline=True,
                                                             base_url=public_base_url)
                    write_bundle(bundle, EXPORT_DIR)
                    (EXPORT_DIR / "pipeline_report.json").write_bytes(json_bytes(report))
                    return {"records": prepared, "report": report, "bundle": bundle}
                snapshot = await run_in_threadpool(runtime.refresh if runtime is not None else rebuild)
                app.state.snapshot = snapshot  # Jedna atomowa podmiana dla API i eksportów.
            except (RuntimeError, ValueError, OSError) as exc:
                raise HTTPException(503, f"Nie przebudowano zbioru; zachowano poprzednią migawkę. {exc}") from exc
        return stats(snapshot)

    @app.get("/api/aed")
    def get_aed(miasto: str | None = Query(default=None, max_length=100),
                tylko_otwarte_teraz: bool = False,
                zrodlo: Literal["wszystkie", "danegov", "osm"] = "wszystkie",
                geokoduj: bool = True,
                lat: float | None=Query(default=None,ge=-90,le=90,allow_inf_nan=False),
                lon: float | None=Query(default=None,ge=-180,le=180,allow_inf_nan=False),
                radius_km: float=Query(default=15,ge=.5,le=50,allow_inf_nan=False)):
        if (lat is None)!=(lon is None):raise HTTPException(422,'Podaj jednocześnie szerokość i długość geograficzną.')
        now = clock()
        snapshot = current_snapshot()
        city = None
        if miasto and miasto.strip():
            try:
                city = city_resolver.resolve(miasto, allow_lookup=geokoduj)
            except CitySearchError as exc:
                raise HTTPException(exc.status_code, str(exc)) from exc
        selected = []
        gov_count = osm_count = matched_before_availability = 0
        for row in effective_records():
            if lat is not None and (not usable_coordinates(row) or haversine(lat,lon,row['lat'],row['lon'])>radius_km*1000):continue
            has_gov = any(s.get("dataset_id") for s in row.get("sources", []))
            has_osm = any(s.get("name") == "OpenStreetMap" for s in row.get("sources", []))
            gov_count += bool(has_gov)
            osm_count += bool(has_osm)
            if (zrodlo == "danegov" and not has_gov) or (zrodlo == "osm" and not has_osm):
                continue
            if miasto and miasto.strip():
                if city:
                    if not contains(city, row.get("lat"), row.get("lon")):
                        continue
                elif city_key(row.get("miejscowosc")) != city_key(miasto):
                    continue
            matched_before_availability += 1
            state = availability_now(row, now)
            if tylko_otwarte_teraz and state["otwarte_teraz"] is not True:
                continue
            selected.append({**row, **state,
                             **({"miejscowosc_wyszukiwania": city["name"]} if city and not row.get("miejscowosc") else {})})
        result = {"count": len(selected), "area": snapshot["report"]["area"], "evaluated_at": now.isoformat(),
                "timezone": "Europe/Warsaw", "source": snapshot["report"]["source"],
                "scope": {"national_records": len(snapshot["records"]), "danegov_points": gov_count,
                          "osm_points": osm_count, "matched_before_availability": matched_before_availability},
                "filters": {"miasto": miasto, "zrodlo": zrodlo, "tylko_otwarte_teraz": tylko_otwarte_teraz},
                "city": public_city(city),
                "items": selected}
        return streamed_json(result) if runtime is not None else result

    @app.post("/api/validate-upload")
    async def upload(file: Annotated[UploadFile, File(description="Wzorzec XLSX lub CSV UTF-8")]):
        try:
            if Path(file.filename or "").suffix.lower() not in (".csv", ".xlsx"):
                raise HTTPException(415, "Obsługiwane pliki: .xlsx i .csv.")
            payload = await file.read(upload_limit + 1)
            if len(payload) > upload_limit:
                raise HTTPException(413, f"Limit pliku: {upload_limit//(1024*1024)} MiB.")
            try:
                result = await run_in_threadpool(validate_upload, payload, file.filename)
                return streamed_json(result) if runtime is not None else result
            except (ValueError, TypeError) as exc:
                raise HTTPException(400, str(exc)) from exc
        finally:
            await file.close()

    @app.get("/export/{format}")
    def export(format: str, range_header: Annotated[str | None, Header(alias="Range")] = None):
        formats = {"csv": ("aed_polska.csv", "text/csv; charset=utf-8"),
                   "json": ("aed_polska.json", "application/json"),
                   "geojson": ("aed_polska.geojson", "application/geo+json"),
                   "xml": ("harvester_metadata.xml", "application/xml"),
                   "payload": ("danegov_api_payload.json", "application/vnd.api+json"),
                   "md5": ("harvester_metadata.md5", "text/plain; charset=us-ascii")}
        if format not in formats:
            raise HTTPException(404, "Dostępne formaty: csv, json, geojson, xml, payload, md5.")
        filename, media_type = formats[format]
        bundle = current_snapshot()["bundle"]
        if format == "md5":
            import hashlib
            payload = (hashlib.md5(bundle["harvester_metadata.xml"]).hexdigest() + "\n").encode("ascii")
        else:
            payload = bundle[filename]
        headers = {"Content-Disposition": f'attachment; filename="{filename}"', "Accept-Ranges": "bytes"}
        if range_header:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header)
            size = len(payload)
            if not match or int(match[1]) >= size or (match[2] and int(match[2]) < int(match[1])):
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            start = int(match[1]); end = min(int(match[2]) if match[2] else size - 1, size - 1)
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            if runtime is not None:return StreamingResponse(byte_chunks(payload[start:end+1]),status_code=206,media_type=media_type,headers=headers)
            return Response(payload[start:end + 1], status_code=206, media_type=media_type, headers=headers)
        if runtime is not None:return StreamingResponse(byte_chunks(payload),media_type=media_type,headers=headers)
        return Response(payload, media_type=media_type, headers=headers)

    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

    @app.get("/", include_in_schema=False)
    def frontend():
        return FileResponse(frontend_dir / "index.html")

    @app.get("/data-standard/wzorzec_danych_aed.xlsx", include_in_schema=False)
    def download_template():
        from .schema import SCHEMA_PATH
        return FileResponse(SCHEMA_PATH, filename="wzorzec_danych_aed.xlsx")

    return app


app = create_app()
