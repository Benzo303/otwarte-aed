"""Regresje Vercel: katalog kodu tylko do odczytu, migawki i duże odpowiedzi."""
import copy
from contextlib import contextmanager
from datetime import timedelta
import errno
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from .cloud_archive import pack_snapshot,unpack_snapshot
from .cloud_responses import json_chunks
from .cloud_runtime import CloudRuntime
from .cloud_store import PostgresStore,ReadOnlyStore
from .feature_store import FeatureStore
from .harvester_export import publication_bundle
from .main import create_app
from .test_features import point
from .test_pipeline import MONDAY

BASE='https://otwarte-aed.vercel.app'
ROOT=Path(__file__).resolve().parents[1]

def fixture(rows=None):
    rows=rows or [point()]
    report={'area':'polska','generated_at':MONDAY.isoformat(),'source':{},'output_records':len(rows),
            'base_url':BASE,'files_sha256':{},'input_osm':len(rows),'input_danegov':0,'duplicates_merged':0,
            'cross_source_groups':0,'danegov':{'datasets':[],'from_cache':True}}
    return {'records':rows,'report':report,'bundle':publication_bundle(rows,base_url=BASE,area='polska',generated_at=MONDAY)}

class FakeStore(ReadOnlyStore):
    persistent=True
    mode='test'
    remote=None
    def archive(self):return self.remote
    def revision(self):return self.remote[0] if self.remote else None

class CloudTests(unittest.TestCase):
    def test_archive_preserves_records_exports_and_cache(self):
        snapshot=fixture();payload=pack_snapshot(snapshot,b'{"datasets":[]}')
        loaded,cache=unpack_snapshot(payload)
        self.assertEqual(loaded['records'],snapshot['records'])
        self.assertEqual(cache,b'{"datasets":[]}')
        for name,content in snapshot['bundle'].items():self.assertEqual(loaded['bundle'][name],content)
    def test_full_start_without_writing_to_code_directory(self):
        snapshot=fixture()
        with TemporaryDirectory() as directory:
            cache=Path(directory);seed=cache/'seed.zip';seed.write_bytes(pack_snapshot(snapshot))
            runtime=CloudRuntime(seed_path=seed,cache_path=cache,base_url=BASE,store=ReadOnlyStore())
            mkdir=Path.mkdir
            def guarded(path,*args,**kwargs):
                if path.resolve().is_relative_to(ROOT):raise OSError(errno.EROFS,'Read-only file system',str(path))
                return mkdir(path,*args,**kwargs)
            with patch.object(Path,'mkdir',guarded),TestClient(create_app(runtime=runtime,clock=lambda:MONDAY)) as client:
                self.assertEqual(client.get('/').status_code,200)
                health=client.get('/api/health').json()
                self.assertEqual(health['cloud']['mode'],'read_only')
                self.assertEqual(health['records'],1)
                self.assertEqual(client.get('/api/aed').json()['count'],1)
                self.assertEqual(client.post('/api/aed/OPEN/report',json={'kind':'working'}).status_code,503)
                self.assertEqual(client.post('/api/danegov/refresh').status_code,503)
                self.assertEqual(client.get('/api/aed/OPEN/passport.svg').status_code,200)
                full=client.get('/export/json');part=client.get('/export/json',headers={'Range':'bytes=0-39'})
                self.assertEqual(part.status_code,206)
                self.assertEqual(part.content,full.content[:40])
    def test_large_json_stream_has_bounded_chunks_and_preserves_unicode(self):
        value={'text':'ą🙂'*900000}
        chunks=list(json_chunks(value))
        self.assertTrue(all(len(chunk)<=32768 for chunk in chunks))
        body=b''.join(chunks)
        self.assertGreater(len(body),4.5*1024*1024)
        self.assertEqual(json.loads(body),value)
    def test_other_instance_loads_new_snapshot(self):
        first=fixture();second=fixture([point('OTHER')]);store=FakeStore()
        with TemporaryDirectory() as directory:
            cache=Path(directory);seed=cache/'seed.zip';seed.write_bytes(pack_snapshot(first))
            runtime=CloudRuntime(seed_path=seed,cache_path=cache,base_url=BASE,store=store)
            runtime.start();store.remote=('new-revision',pack_snapshot(second))
            runtime._last_check-=6
            self.assertEqual(runtime.current()['records'][0]['id_aed'],'OTHER')
            self.assertEqual(runtime.version,'new-revision')
    def test_failed_refresh_keeps_old_snapshot_and_releases_lock(self):
        class Connection:
            autocommit=False
            calls=[]
            def commit(self):pass
            def execute(self,statement,params):
                self.calls.append(statement)
                return self
            def fetchone(self):return {'locked':True}
        connection=Connection()
        class Store(FakeStore):
            @contextmanager
            def connection(self):yield connection
        with TemporaryDirectory() as directory:
            cache=Path(directory);seed=cache/'seed.zip';seed.write_bytes(pack_snapshot(fixture()))
            runtime=CloudRuntime(seed_path=seed,cache_path=cache,base_url=BASE,store=Store());runtime.start()
            before=runtime.snapshot
            with patch('backend.harvester_export.build_snapshot',side_effect=RuntimeError('timeout')):
                with self.assertRaises(RuntimeError):runtime.refresh()
            self.assertIs(runtime.snapshot,before)
            self.assertIn('pg_advisory_unlock',connection.calls[-1])
    def test_sqlite_and_shared_overlay_keep_same_damage_warning(self):
        row=point()
        with FeatureStoreForTest() as sqlite:
            report=sqlite.report('OPEN','damaged',MONDAY)
            expected=sqlite.overlay([row],MONDAY+timedelta(minutes=1))
            class Rows:
                def execute(self,*args):return self
                def fetchall(self):return [report]
            store=PostgresStore('not-used')
            @contextmanager
            def connection():yield Rows()
            store.connection=connection
            self.assertEqual(store.overlay([row],MONDAY+timedelta(minutes=1)),expected)
    @unittest.skipUnless(os.getenv('AED_TEST_DATABASE_URL'),'Brak oddzielnej testowej bazy PostgreSQL')
    def test_postgres_report_is_visible_from_second_connection(self):
        from uuid import uuid4
        aed_id='TEST-'+uuid4().hex
        first=PostgresStore(os.environ['AED_TEST_DATABASE_URL']);second=PostgresStore(os.environ['AED_TEST_DATABASE_URL'])
        try:
            first.report(aed_id,'damaged',MONDAY)
            result=second.overlay([point(aed_id)],MONDAY+timedelta(minutes=1))[0]
            self.assertEqual(result['field_access_alert'],'damaged')
            self.assertEqual(result['field_reports_count'],1)
        finally:
            with first.connection() as connection:connection.execute('DELETE FROM otwarte_aed_reports WHERE aed_id=%s',(aed_id,))

@contextmanager
def FeatureStoreForTest():
    store=FeatureStore(':memory:')
    try:yield store
    finally:store.close()
