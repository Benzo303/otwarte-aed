"""Migawka budowana przed wdrożeniem; eksporty rozpakowywane na żądanie."""
from collections.abc import Mapping
import io
import json
from zipfile import ZipFile, ZIP_DEFLATED

EXPORT_NAMES=('aed_polska.csv','aed_polska.json','aed_polska.geojson','harvester_metadata.xml','danegov_api_payload.json')

def compact(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')

class ArchiveBundle(Mapping):
    def __init__(self,payload):self.payload=payload
    def __iter__(self):return iter(EXPORT_NAMES)
    def __len__(self):return len(EXPORT_NAMES)
    def __getitem__(self,name):
        if name not in EXPORT_NAMES:raise KeyError(name)
        with ZipFile(io.BytesIO(self.payload)) as archive:return archive.read('exports/'+name)

def pack_snapshot(snapshot,gov_cache=None):
    stream=io.BytesIO()
    with ZipFile(stream,'w',compression=ZIP_DEFLATED,compresslevel=1) as archive:
        archive.writestr('manifest.json',compact({'format_version':1}))
        archive.writestr('records.json',compact(snapshot['records']))
        archive.writestr('report.json',compact(snapshot['report']))
        if gov_cache is not None:archive.writestr('danegov_cache.json',gov_cache)
        for name in EXPORT_NAMES:archive.writestr('exports/'+name,snapshot['bundle'][name])
    return stream.getvalue()

def unpack_snapshot(payload):
    with ZipFile(io.BytesIO(payload)) as archive:
        if sum(item.file_size for item in archive.infolist())>512*1024*1024:raise ValueError('Migawka jest za duża.')
        if json.loads(archive.read('manifest.json')).get('format_version')!=1:raise ValueError('Nieobsługiwana wersja migawki.')
        records=json.loads(archive.read('records.json'))
        report=json.loads(archive.read('report.json'))
        if not isinstance(records,list) or not records or report.get('output_records')!=len(records):raise ValueError('Niespójna migawka AED.')
        for name in EXPORT_NAMES:archive.getinfo('exports/'+name)
        gov_cache=archive.read('danegov_cache.json') if 'danegov_cache.json' in archive.namelist() else None
    return {'records':records,'report':report,'bundle':ArchiveBundle(payload)},gov_cache
