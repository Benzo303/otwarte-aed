"""Uruchomienie Vercel: gotowa migawka, cache roboczy i wspólna baza PostgreSQL."""
from collections import ChainMap
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from uuid import uuid4
from fastapi import HTTPException
from .cloud_archive import pack_snapshot, unpack_snapshot
from .cloud_store import PostgresStore, ReadOnlyStore, REFRESH_LOCK

ROOT=Path(__file__).resolve().parent
SEED_PATH=ROOT/'data/deployment/vercel_seed.zip'

def public_base_url():
    configured=os.getenv('AED_PUBLIC_BASE_URL')
    host=os.getenv('VERCEL_PROJECT_PRODUCTION_URL') or os.getenv('VERCEL_URL')
    return (configured or ('https://'+host if host else 'https://aed.example.org')).rstrip('/')

def prepare_cache():
    destination=Path(os.getenv('AED_CACHE_DIR',str(Path(tempfile.gettempdir())/'otwarte-aed/cache')))
    destination.mkdir(parents=True,exist_ok=True)
    os.environ['AED_CACHE_DIR']=str(destination)
    for source in (ROOT/'data/cache').glob('*.json'):
        target=destination/source.name
        if not target.exists():shutil.copyfile(source,target)
    return destination

class CloudRuntime:
    def __init__(self,*,seed_path=SEED_PATH,cache_path=None,base_url=None,store=None):
        self.seed_path=Path(seed_path)
        self.cache_path=Path(cache_path) if cache_path is not None else prepare_cache()
        self.base_url=base_url or public_base_url()
        url=os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
        self.store=store if store is not None else PostgresStore(url) if url else ReadOnlyStore()
        self.snapshot=None
        self.version=None
        self._last_check=0
        self.lock=threading.RLock()
        self.start_seconds=None
    def _decode(self,payload):
        from .harvester_export import metadata_xml,danegov_api_payload,json_bytes
        snapshot,gov_cache=unpack_snapshot(payload)
        if gov_cache is not None:
            destination=self.cache_path/'danegov_cache.json'
            temporary=destination.with_suffix('.new')
            temporary.write_bytes(gov_cache)
            temporary.replace(destination)
        report=snapshot['report']
        if report.get('base_url')!=self.base_url:
            generated=datetime.fromisoformat(report['generated_at'])
            overrides={
                'harvester_metadata.xml':metadata_xml(snapshot['records'],base_url=self.base_url,area=report['area'],generated_at=generated,source_info=report['source']),
                'danegov_api_payload.json':json_bytes(danegov_api_payload(snapshot['records'],base_url=self.base_url,area=report['area'],generated_at=generated))
            }
            snapshot['bundle']=ChainMap(overrides,snapshot['bundle'])
            report['base_url']=self.base_url
            report['public_urls_configured']='example.org' not in self.base_url
            report['files_sha256'].update({name:hashlib.sha256(content).hexdigest() for name,content in overrides.items()})
        return snapshot
    def start(self):
        started=time.monotonic()
        remote=self.store.archive() if self.store.persistent else None
        if remote:
            self.version,payload=remote
        else:
            if not self.seed_path.is_file():raise RuntimeError('Brak vercel_seed.zip. Uruchom etap budowania: python -m backend.vercel_build.')
            payload=self.seed_path.read_bytes()
            self.version='seed:'+hashlib.sha256(payload).hexdigest()
        self.snapshot=self._decode(payload)
        self._last_check=time.monotonic()
        self.start_seconds=round(time.monotonic()-started,3)
        return self.snapshot['records'],self.snapshot['report'],self.snapshot['bundle']
    def current(self,fallback=None):
        if not self.store.persistent:return self.snapshot or fallback
        if time.monotonic()-self._last_check<5:return self.snapshot or fallback
        with self.lock:
            if time.monotonic()-self._last_check<5:return self.snapshot or fallback
            revision=self.store.revision()
            if revision and revision!=self.version:
                remote=self.store.archive()
                if remote:
                    version,payload=remote
                    prepared=self._decode(payload)
                    self.snapshot,self.version=prepared,version
            self._last_check=time.monotonic()
        return self.snapshot or fallback
    def refresh(self):
        if not self.store.persistent:raise HTTPException(503,'Synchronizacja z zapisem wymaga podłączenia trwałej bazy danych. Aktualne dane pozostają dostępne.')
        from .harvester_export import build_snapshot
        with self.store.connection() as connection:
            connection.commit()
            connection.autocommit=True
            locked=connection.execute('SELECT pg_try_advisory_lock(%s) AS locked',(REFRESH_LOCK,)).fetchone()['locked']
            if not locked:raise HTTPException(409,'Synchronizacja już trwa w innym procesie. Dotychczasowe dane są nadal dostępne.')
            try:
                records,report,bundle=build_snapshot(area='polska',offline=False,osm_offline=True,base_url=self.base_url)
                snapshot={'records':records,'report':report,'bundle':bundle}
                gov=self.cache_path/'danegov_cache.json'
                payload=pack_snapshot(snapshot,gov.read_bytes() if gov.exists() else None)
                revision=uuid4().hex
                connection.execute('INSERT INTO otwarte_aed_snapshot(id,revision,payload) VALUES(1,%s,%s) ON CONFLICT(id) DO UPDATE SET revision=EXCLUDED.revision,payload=EXCLUDED.payload',(revision,payload))
                with self.lock:
                    self.snapshot,self.version=snapshot,revision
                    self._last_check=time.monotonic()
                return snapshot
            finally:
                connection.execute('SELECT pg_advisory_unlock(%s)',(REFRESH_LOCK,))
    def status(self):
        return {'mode':self.store.mode,'writes_enabled':self.store.persistent,'snapshot_revision':self.version,
                'startup_seconds':self.start_seconds,'upload_limit_bytes':3*1024*1024,
                'commit':os.getenv('VERCEL_GIT_COMMIT_SHA'),'runtime_version':'vercel-2'}

def create_cloud_app():
    # Musi nastąpić przed importem modułów z domyślnymi ścieżkami cache.
    cache=prepare_cache()
    from .main import create_app
    runtime=CloudRuntime(cache_path=cache)
    return create_app(runtime=runtime,public_base_url=runtime.base_url)
