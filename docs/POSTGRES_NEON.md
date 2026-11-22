# PostgreSQL w Vercel: Neon

Kod odczytuje DATABASE_URL albo POSTGRES_URL ze zmiennych środowiskowych.
Integracja Neon dodaje te zmienne do wybranych środowisk Vercel. Wybierz
Production i pozostaw puste Custom Prefix. Pozostaw Sensitive włączone.
Po połączeniu bazy wymagane jest nowe wdrożenie z najnowszego commita.

## Poprawka zgodności

Neon udostępnia DATABASE_URL przez PgBouncer w trybie transakcyjnym.
Synchronizacja używa teraz pg_try_advisory_xact_lock, a timeout jest ustawiany
przez SET LOCAL. COMMIT lub ROLLBACK zwalnia blokadę, również po awarii.
Nowa migawka jest publikowana w pamięci dopiero po udanym COMMIT.
Sesyjne blokady i ustawienia nie są wymagane.

## Weryfikacja

Po wdrożeniu /api/health ma zwrócić cloud.mode=postgresql oraz
cloud.writes_enabled=true. Start sprawdza połączenie i zakłada wyłącznie
własne tabele otwarte_aed_reports, otwarte_aed_imports i otwarte_aed_snapshot.
Kod nie usuwa istniejących tabel użytkownika.

Lokalnie: 9 testów chmurowych OK, 1 test z rzeczywistym PostgreSQL pominięty,
ponieważ nie skonfigurowano jeszcze bazy. Nowe testy sprawdzają także błąd
COMMIT, brak równoczesnej synchronizacji i publikację dopiero po zapisie.
Rzeczywisty zapis i trwałość wymagają potwierdzenia po podłączeniu usługi.

Źródła:
- https://neon.com/docs/guides/vercel-managed-integration
- https://neon.com/docs/connect/connection-pooling
- https://www.postgresql.org/docs/current/functions-admin.html
