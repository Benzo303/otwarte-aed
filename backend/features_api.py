"""Dodatkowe trasy ratunkowe, audytu i importu; zachowują dotychczasowe API."""
import io
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit, urlencode
from xml.sax.saxutils import escape
from zipfile import BadZipFile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
import httpx
import qrcode

from .chaos_import import MAX_BYTES, clean_import, download_public
from .quality_audit import audit_cache
from .rescue import nearest


class RescueInput(BaseModel):
    lat: float = Field(ge=-90,le=90,allow_inf_nan=False)
    lon: float = Field(ge=-180,le=180,allow_inf_nan=False)
    radius_km: float = Field(default=15,ge=.5,le=50,allow_inf_nan=False)
    zrodlo: Literal['wszystkie','danegov','osm']='wszystkie'


class ReportInput(BaseModel):
    kind: Literal["working","closed","damaged"]


class BipInput(BaseModel):
    url: str = Field(min_length=8,max_length=2000)
    geocode: bool = False


def passport_svg(row, base_url, name=None):
    parsed=urlsplit(base_url)
    if parsed.scheme not in ("http","https") or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Podaj adres aplikacji HTTP/HTTPS bez danych logowania.")
    link=urlunsplit((parsed.scheme,parsed.netloc,parsed.path or "/",urlencode({"aed":row["id_aed"]}),""))
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=1,border=4)
    qr.add_data(link);qr.make(fit=True);matrix=qr.get_matrix();n=len(matrix)
    path="".join(f"M{x} {y}h1v1h-1z" for y,line in enumerate(matrix) for x,dark in enumerate(line) if dark)
    title=name or row.get("nazwa_obiektu") or row.get("ulica_numer") or "Defibrylator AED"
    words=str(title)[:120].split();lines=[""]
    for word in words:
        if len(lines[-1])+len(word)+1>27:lines.append(word)
        else:lines[-1]=(lines[-1]+" "+word).strip()
    heading="".join(f'<text x="52" y="{210+37*i}" font-size="27" font-weight="700">{escape(line)}</text>' for i,line in enumerate(lines[:4]))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="620" viewBox="0 0 1080 620" role="img" aria-label="Paszport AED">
<title>Paszport AED: {escape(title)}</title><desc>Kod QR: {escape(link)}</desc><rect width="1080" height="620" fill="#fff"/>
<rect x="10" y="10" width="1060" height="600" rx="12" fill="#fff" stroke="#003366" stroke-width="5"/><path d="M12 12h1056v18H12z" fill="#d5233f"/>
<g font-family="Arial,sans-serif" fill="#003366"><text x="52" y="95" font-size="38" font-weight="bold">OTWARTE AED</text><text x="52" y="140" font-size="22">PASZPORT RATUNKOWY · PROTOTYP</text>{heading}
<text x="52" y="395" font-size="20">{escape(row['id_aed'])}</text><text x="52" y="470" font-size="25" font-weight="700">Zeskanuj i sprawdź dostęp.</text>
<text x="52" y="512" font-size="20">Zgłoś stan urządzenia w terenie.</text><text x="52" y="565" font-size="22" fill="#b01832">W nagłym zagrożeniu życia dzwoń pod 112.</text></g>
<svg x="675" y="150" width="340" height="340" viewBox="0 0 {n} {n}" shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/><path d="{path}" fill="#000"/></svg>
<text x="845" y="535" font-family="Arial,sans-serif" text-anchor="middle" font-size="18" fill="#003366">LOKALIZACJA · GODZINY · WERYFIKACJA</text></svg>''',link


def router_for(get_records,get_store,clock):
    router=APIRouter()
    def find(aid):
        return next((r for r in get_records() if r["id_aed"]==aid or aid in r.get("merged_ids",[])),None)

    @router.post("/api/rescue/nearest")
    def rescue(body:RescueInput):
        rows=get_records()
        if body.zrodlo=='danegov':rows=[r for r in rows if any(s.get('dataset_id') for s in r.get('sources',[]))]
        elif body.zrodlo=='osm':rows=[r for r in rows if any(s.get('name')=='OpenStreetMap' for s in r.get('sources',[]))]
        return nearest(rows,body.lat,body.lon,clock(),body.radius_km)

    @router.get("/api/aed/{id_aed}")
    def detail(id_aed:str):
        row=find(id_aed)
        if row is None:raise HTTPException(404,"Nie znaleziono AED.")
        from .availability import availability_now
        return {**row,**availability_now(row,clock())}

    @router.post("/api/aed/{id_aed}/report")
    def report(id_aed:str,body:ReportInput):
        row=find(id_aed)
        if row is None:raise HTTPException(404,"Nie znaleziono AED.")
        item=get_store().report(row["id_aed"],body.kind,clock())
        return {"saved":True,"report":item,"aed":find(row["id_aed"]),
                "note":"Zgłoszenie terenowe jest społeczne. Nie zastępuje kontroli dysponenta; świeże ostrzeżenia wykluczają rekomendację przez 24 h."}

    @router.get("/api/aed/{id_aed}/passport.svg")
    def passport(id_aed:str,request:Request,base_url:str|None=None,name:str|None=None):
        row=find(id_aed)
        if row is None:raise HTTPException(404,"Wybierz istniejący identyfikator AED z mapy.")
        try:svg,link=passport_svg(row,base_url or str(request.base_url),name[:120] if name else None)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        return Response(svg,media_type="image/svg+xml",headers={"Content-Disposition":f'inline; filename="paszport-aed.svg"'})

    @router.get("/api/danegov/audit")
    def audit():return audit_cache()

    def save_import(payload):
        payload["import_id"]=get_store().save_import(payload,clock())
        return payload

    @router.post("/api/chaos-import")
    async def chaos(file:UploadFile=File(...),geocode:bool=Form(False)):
        try:
            content=await file.read(MAX_BYTES+1)
            if len(content)>MAX_BYTES:raise HTTPException(413,"Limit pliku: 5 MiB.")
            try:
                return await run_in_threadpool(lambda:save_import(clean_import(content,file.filename or "plik.csv",geocode=geocode)))
            except (ValueError,BadZipFile,KeyError,TypeError) as exc:raise HTTPException(422,str(exc)) from exc
        finally:await file.close()

    @router.post("/api/import/bip-url")
    async def bip(body:BipInput):
        def work():
            content,media,url=download_public(body.url)
            suffix=Path(urlsplit(url).path).suffix.lower()
            if "pdf" in media:suffix=".pdf"
            elif "html" in media:suffix=".html"
            if suffix not in (".pdf",".csv",".xlsx",".json",".geojson",".xml",".html",".htm"):suffix=".html"
            return save_import(clean_import(content,"bip"+suffix,source_url=url,geocode=body.geocode))
        try:return await run_in_threadpool(work)
        except (ValueError,KeyError,TypeError,BadZipFile) as exc:raise HTTPException(422,str(exc)) from exc
        except (httpx.HTTPError,OSError) as exc:raise HTTPException(502,f"Nie udało się pobrać strony BIP: {exc}") from exc

    @router.post("/api/import/{import_id}/preview")
    def activate(import_id:str):
        try:payload=get_store().activate_import(import_id)
        except KeyError:raise HTTPException(404,"Nie znaleziono importu.")
        return {"active":True,"records":len(payload["normalized_json"]),"note":"Odrębna baza podglądu; bez publikacji w rejestrze i eksportach."}

    @router.get("/api/import/preview")
    def preview():
        rows=get_store().preview()
        return {"count":len(rows),"items":rows,"is_preview":True}

    return router
