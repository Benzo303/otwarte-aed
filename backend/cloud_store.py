"""Trwały PostgreSQL w chmurze; brak bazy nie udaje zapisania zgłoszenia."""
from contextlib import contextmanager
from datetime import timezone
import json
import threading
from uuid import uuid4
from fastapi import HTTPException
from .feature_store import overlay_reports

SCHEMA_LOCK=1278600001
REFRESH_LOCK=1278600002
DDL=(
    'CREATE TABLE IF NOT EXISTS otwarte_aed_reports (id TEXT PRIMARY KEY, aed_id TEXT NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL)',
    'CREATE INDEX IF NOT EXISTS otwarte_aed_reports_aed ON otwarte_aed_reports(aed_id,created_at)',
    'CREATE TABLE IF NOT EXISTS otwarte_aed_imports (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT FALSE)',
    'CREATE TABLE IF NOT EXISTS otwarte_aed_snapshot (id SMALLINT PRIMARY KEY CHECK(id=1), revision TEXT NOT NULL, payload BYTEA NOT NULL)'
)

class ReadOnlyStore:
    persistent=False
    mode='read_only'
    def close(self):pass
    def overlay(self,records,now):return records
    def report(self,*args):raise HTTPException(503,'Zapisywanie zgłoszeń jest jeszcze niedostępne. Administrator musi podłączyć trwałą bazę danych.')
    def save_import(self,*args):return None
    def activate_import(self,*args):raise HTTPException(503,'Zapisywanie podglądu wymaga podłączenia trwałej bazy danych.')
    def preview(self):return []

class PostgresStore:
    persistent=True
    mode='postgresql'
    def __init__(self,url):
        self.url=url
        self._schema_ready=False
        self._schema_lock=threading.RLock()
    def close(self):pass
    @contextmanager
    def connection(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:raise HTTPException(503,'Brakuje sterownika PostgreSQL. Przebuduj wdrożenie z aktualnymi zależnościami.') from exc
        try:
            with psycopg.connect(self.url,connect_timeout=8,prepare_threshold=None,row_factory=dict_row) as connection:
                connection.execute("SET statement_timeout = '15000'")
                with self._schema_lock:
                    if not self._schema_ready:
                        connection.execute('SELECT pg_advisory_xact_lock(%s)',(SCHEMA_LOCK,))
                        for statement in DDL:connection.execute(statement)
                        connection.commit()
                        self._schema_ready=True
                yield connection
        except psycopg.Error as exc:raise HTTPException(503,'Nie można połączyć się z bazą zgłoszeń. Spróbuj ponownie później.') from exc
    def report(self,aed_id,kind,now):
        item={'id':uuid4().hex,'aed_id':aed_id,'kind':kind,'created_at':now.astimezone(timezone.utc).isoformat()}
        with self.connection() as connection:
            connection.execute('INSERT INTO otwarte_aed_reports(id,aed_id,kind,created_at) VALUES(%(id)s,%(aed_id)s,%(kind)s,%(created_at)s)',item)
        return item
    def overlay(self,records,now):
        with self.connection() as connection:
            reports=connection.execute('SELECT id,aed_id,kind,created_at FROM otwarte_aed_reports ORDER BY created_at DESC,id DESC').fetchall()
        return overlay_reports(records,reports,now)
    def save_import(self,payload,now):
        identifier=uuid4().hex
        with self.connection() as connection:
            connection.execute('INSERT INTO otwarte_aed_imports(id,created_at,payload) VALUES(%s,%s,%s)',(identifier,now.isoformat(),json.dumps(payload,ensure_ascii=False,allow_nan=False)))
        return identifier
    def activate_import(self,identifier):
        with self.connection() as connection:
            row=connection.execute('UPDATE otwarte_aed_imports SET active=TRUE WHERE id=%s RETURNING payload',(identifier,)).fetchone()
            if row is None:raise KeyError(identifier)
        return json.loads(row['payload'])
    def preview(self):
        with self.connection() as connection:
            batches=connection.execute('SELECT id,payload FROM otwarte_aed_imports WHERE active=TRUE ORDER BY created_at DESC LIMIT 20').fetchall()
        return [{**row,'is_preview':True,'import_id':batch['id']} for batch in batches for row in json.loads(batch['payload']).get('normalized_json',[])]
    def revision(self):
        with self.connection() as connection:
            row=connection.execute('SELECT revision FROM otwarte_aed_snapshot WHERE id=1').fetchone()
        return row['revision'] if row else None
    def archive(self):
        with self.connection() as connection:
            row=connection.execute('SELECT revision,payload FROM otwarte_aed_snapshot WHERE id=1').fetchone()
        return (row['revision'],bytes(row['payload'])) if row else None
