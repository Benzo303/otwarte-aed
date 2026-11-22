# Uruchomienie Otwarte AED w Dockerze

W Windows zainstaluj i uruchom [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
z silnikiem kontenerów Linux. Potem kliknij `START_DOCKER.cmd` albo wykonaj
z katalogu projektu:

```powershell
docker compose up -d --build --wait --wait-timeout 240
```

Aplikacja: **http://localhost:8080/**. Na tym samym adresie działają frontend,
mapa, API, import XLSX/CSV i eksporty. Port 8080 nie koliduje z uruchomieniem
bez Dockera na 8000. Host nie potrzebuje Pythona ani lokalnego `.venv`.
W kontenerze aplikacja używa Python 3.12 i `/app/.venv`.

## Dane i kontrola uruchomienia

Obraz zawiera rzeczywiste migawki dane.gov.pl, ogólnopolskiego OSM i zapisane
granice miast. Domyślny start korzysta z cache. Synchronizacja portalu i pierwsze
wyszukiwanie niezapisanego miasta wymagają sieci. Działają dotychczasowe limity
i cache geokodera.

Wolumeny `aed_cache` i `aed_exports` zachowują dane po odtworzeniu kontenera.
Przy pierwszym uruchomieniu cache wolumenu jest inicjalizowany z obrazu.
Przebudowanie obrazu nie nadpisuje istniejącego wolumenu. Aktualizację danych
wykonaj przyciskiem synchronizacji w aplikacji. `docker compose down` zachowuje
wolumeny; nie dodawaj `-v`, jeśli chcesz zachować dane.

Starter czeka na healthcheck: `/api/health` ma zwrócić `ready=true` i niepustą bazę.
Użytkownik procesu kontenera ma UID 10001, a zapisy aplikacji trafiają do wolumenów.
Pakiety instalują się z gotowych wheel, bez kompilatorów i instalowania bibliotek C
przez systemowy menedżer pakietów.

```powershell
docker compose ps
docker compose logs --tail=100 aed
docker compose exec aed python -m unittest backend.test_pipeline backend.test_danegov backend.test_city_search -q
docker compose down
```

Pliki `START_DOCKER.cmd` i `STOP_DOCKER.cmd` są również w `frontend` i wykrywają
katalog projektu ze swojego położenia. Pierwsze budowanie wymaga internetu
do pobrania oficjalnego obrazu Python oraz zależności.

## Zmiana ustawień i telefon

Domyślne mapowanie `127.0.0.1:8080:8000` udostępnia aplikację na komputerze.
Docker sam nie zapewnia publicznego adresu ani łączności telefonu z komputerem.
Do testu w tej samej sieci można jawnie zmienić adres wiązania:

```powershell
$env:AED_BIND_HOST = "0.0.0.0"
docker compose up -d --build --wait --wait-timeout 240
```

Telefon otwiera wtedy `http://IP_KOMPUTERA:8080/`. Dostęp zależy od sieci
i zapory. Powrót do dostępu lokalnego:

```powershell
$env:AED_BIND_HOST = "127.0.0.1"
docker compose up -d --wait --wait-timeout 240
```

Pozostałe zmienne Compose: `AED_PUBLIC_BASE_URL` (docelowy HTTPS dla metadanych),
`AED_OFFLINE`, `AED_CITY_OFFLINE`, `AED_GEOCODER_URL`. Można ustawić je w terminalu
lub pliku `.env` obok Compose. Domyślny adres `aed.example.org` nadal wymaga zmiany
przed publikacją zasobów w portalu dane.gov.pl.

`compose.yaml` używa składni JSON, która jest także poprawną składnią YAML.
Plik można odczytać standardowym parserem JSON, bez dodatkowych bibliotek.
Dokumentacja: [przewodnik Python](https://docs.docker.com/guides/python/),
[publikowanie portów](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/).
