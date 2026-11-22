# Backend Otwarte AED

FastAPI i pipeline: dane.gov.pl + Overpass → mapowanie do wzorca XLSX → kontrola jakości →
deduplikacja Haversine → CSV/JSON/GeoJSON oraz XML harvestera dane.gov.pl.
Wszystkie polecenia poniżej wykonuj w głównym katalogu projektu.

## Uruchomienie

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Dokumentacja API: [Swagger UI](http://127.0.0.1:8000/docs).
Domyślnie API korzysta z rzeczywistego cache całej Polski i dane.gov.pl, więc start
nie zależy od sieci. Zmienna `AED_OFFLINE=false` uruchamia pobranie podczas startu,
z fallbackiem do cache. Przycisk synchronizacji lub `POST /api/danegov/refresh`
odświeża dane.gov.pl i atomowo wymienia migawkę API oraz eksportów, bez restartu.
Podczas tej synchronizacji OSM pochodzi z krajowego cache. Wywołania GET nie pobierają danych ze źródeł.

```powershell
$env:AED_OFFLINE = "false"
$env:AED_AREA = "polska"
$env:AED_PUBLIC_BASE_URL = "https://twoj-publiczny-host.pl"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Obsługiwane obszary: `polska` (domyślnie), `warszawa` i `zachodniopomorskie`. Cache ostatniego obszaru
powstaje przy pierwszym poprawnym pobraniu; nie podmieniamy go danymi Warszawy.
Serwer lokalny używa HTTP. Publiczne adresy w metadanych muszą używać HTTPS,
zgodnie z XSD 1.13; zapewnia je docelowy hosting/reverse proxy.

## Pobranie i paczka publikacyjna

```powershell
# Rzeczywiste pobranie i atomowy zapis cache; bez syntetycznych zamienników.
.\.venv\Scripts\python.exe -m backend.fetcher --area polska
.\.venv\Scripts\python.exe -m backend.danegov_client

# Rzeczywiste źródła: krajowy OSM i dane.gov.pl, ponowna integracja z cache.
.\.venv\Scripts\python.exe -m backend.harvester_export --offline --base-url https://twoj-publiczny-host.pl

# Osobna paczka hackathonowa z drugim źródłem DEMO w odmiennym formacie.
.\.venv\Scripts\python.exe -m backend.harvester_export --area warszawa --offline --include-demo --output-dir backend\exports_demo
```

`backend/exports/` zawiera `aed_polska.csv`, `aed_polska.json`,
`aed_polska.geojson`, `harvester_metadata.xml`, `harvester_metadata.md5`
i `pipeline_report.json` oraz `danegov_api_payload.json` (JSON:API). Domyślna paczka
obejmuje całą Polskę. Raport i XML podają rzeczywisty obszar i czas migawki.

Domyślne `https://aed.example.org` jest adresem demonstracyjnym. Przed zgłoszeniem
do harvestera ustaw własny publiczny adres, sprawdź dostępność URL zasobów,
wystaw XML i MD5 oraz zarejestruj źródło w portalu. Sam generator nie publikuje
paczek. Domyślna częstotliwość `irregular` odpowiada ręcznemu uruchamianiu;
`--update-frequency daily` stosuj po zapewnieniu codziennego uruchomienia procesu.

## Endpointy

| Endpoint | Działanie |
| --- | --- |
| `GET /api/aed?miasto=Warszawa&tylko_otwarte_teraz=true` | Filtr miasta bez uwzględniania wielkości liter i filtr aktualnego dostępu |
| `GET /api/aed?tylko_otwarte_teraz=false` | Wszystkie rekordy, również zamknięte i o nieznanej dostępności |
| `GET /api/aed?zrodlo=danegov` | Punkty w całej Polsce pochodzące z API dane.gov.pl, również połączone z OSM |
| `GET /api/aed?zrodlo=osm` | Punkty OSM, również połączone z danymi instytucji |
| `POST /api/validate-upload` | Multipart `file`: `.xlsx` lub `.csv`, maksymalnie 5 MiB i 10 000 rekordów |
| `GET /export/csv` | CSV UTF-8, przecinek, CRLF, cytowanie RFC 4180 |
| `GET /export/json` | JSON UTF-8, liczby dla współrzędnych, `null` dla braków |
| `GET /export/geojson` | FeatureCollection, geometria Point w kolejności `[lon, lat]` |
| `GET /export/xml` | Metadane harvestera, a nie eksport rekordów do XML |
| `GET /export/md5` | Suma kontrolna XML |
| `GET /export/payload` | Paczka JSON:API z obiektami dataset/resource i informacją o warunkach publikacji |
| `GET /api/sources/stats` | Zbiory, instytucje, ID, liczby rekordów, odrzucenia, stan cache, deduplikacja |
| `POST /api/danegov/refresh` | Pobranie dane.gov.pl i atomowa przebudowa krajowej migawki; 409 przy równoległej synchronizacji |

Filtr miasta korzysta z granic OSM, więc obejmuje również punkty bez nazwy
miejscowości w danych. Pierwsze zatwierdzone wyszukanie pobiera granicę, kolejne
używają cache; `geokoduj=false` blokuje nowe pobranie. Odpowiedź `city` zawiera
zasięg do ustawienia mapy. Zasady użycia geokodera i konfiguracja dostawcy są w
[instrukcji integracji](../docs/integracja_danegov.md#wyszukiwanie-miasta-niezależne-od-brakujących-adresów).

Upload zwraca `valid`, liczby poprawnych/odrzuconych wierszy, `errors`
z numerem wiersza/polem/kodem i `warnings`. `normalized_json` oraz
`normalized_csv` zawierają wyłącznie poprawne wiersze wejściowe po deduplikacji.
Wartość `valid=false` oznacza, że nie wolno traktować wyniku jako całego poprawnego
pliku. Upload nie zapisuje danych w rejestrze publicznym. Duplikaty ID odrzucane
są dla wszystkich powtórzeń, a formuły XLSX wymagają zamiany na wartości.
CSV może mieć separator przecinek, średnik lub tabulator; eksport zawsze używa
przecinka. Kody pocztowe i TERYT pozostają tekstem, daty: `YYYY-MM-DD`.

## Schemat, brakujące dane i kompletność

`schema.py` odczytuje nazwy, typy, wymagalność oraz listy rozwijane bezpośrednio
z `data_standard/wzorzec_danych_aed.xlsx`. Nie zmienia skoroszytu. Rdzeń ma 21 pól.
Eksport dodaje maszynowe kolumny jakości i pochodzenia; tablice i obiekty w CSV
są poprawnymi ciągami JSON. Schemat jest ładowany raz na proces.

OSM nie gwarantuje wszystkich obowiązkowych pól wzorca dysponenta. Nie tworzymy
fikcyjnych kodów pocztowych, operatorów, dat kontroli ani deklaracji sprawności.
Braki pozostają `null`, a `quality_errors` i `schema_valid` sygnalizują stan
każdego rekordu. Paczka OSM jest zatem znormalizowanym zbiorem z brakami,
nie kompletnym rejestrem zweryfikowanym przez dysponentów. `pipeline_report.json`
podaje liczbę rekordów spełniających wszystkie reguły wzorca.

`confidence_score` to procent ważonej kompletności: każde z 21 pól ma wagę 1,
a godziny i opis lokalizacji wagę 3 (łącznie 25 punktów). Brak, błędny format,
konflikt oraz wartości `niezweryfikowany`/`niezweryfikowano` nie dają punktów.
Za instytucjonalne źródło dane.gov.pl dodajemy 10 punktów procentowych (limit 100%).
Wynik nie oznacza prawdopodobieństwa sprawności ani dostępności AED.

Z OSM pobieramy `node`, `way`, `relation`; dla dwóch ostatnich pozycja to `center`.
W Warszawie kod gminy i miejscowość wynikają z administracyjnego obszaru zapytania.
Dla województwa nie dopisujemy gminy bez odpowiednich danych. Data ostatniej
edycji OSM jest zachowana w pochodzeniu; nie zastępuje daty potwierdzenia
`check_date:defibrillator`/`check_date`.

## Deduplikacja i aktualny dostęp

Odległość liczymy wzorem Haversine z promieniem Ziemi 6 371 008,8 m. Łączymy
rekordy przy odległości **ściśle mniejszej od 25 m**. Stosujemy stabilne grupowanie
complete-link: każda para w grupie musi spełniać próg, aby łańcuch bliskich punktów
nie scalał odległych urządzeń. Odległość jest wyłącznie heurystyką: urządzenia
na różnych piętrach mogą wymagać rozdzielenia. `merged_ids`, `sources`,
`conflicts`, `deduplication_review_required` i maksymalna odległość pozwalają
ocenić takie połączenie. W bazie pierwszeństwo mają instytucjonalne dane.gov.pl,
następnie kompletność. Braki są uzupełniane; sprzeczności są jawne. Pole
`zrodlo_referencyjne` łączy etykiety instytucji/ID i URL separatorami ` | `,
a `sources` zachowuje linki, ID zasobów i warunki licencji. Indeks przestrzenny
3D ogranicza liczbę porównań bez zmiany warunku Haversine. Rekordy DEMO pozostają osobno.

`opening-hours-py` interpretuje godziny OSM w `Europe/Warsaw`, z polskim
kalendarzem świąt, zmianą czasu, wieloma przedziałami i godzinami po północy.
Nieobsługiwany/błędny harmonogram lub niepotwierdzony publiczny dostęp daje
`otwarte_teraz=null`. Klucz/kod, serwis i niedostępność wykluczają wynik `true`.
Nieznany stan techniczny nie zmienia godzin dostępu; jest widoczny osobno.
Sprzeczne informacje o dostępie lub stanie technicznym również wykluczają `true`.

## Licencje i metadane

XML jest walidowany lokalnie względem dołączonego, oficjalnego
[XSD 1.13](https://dane.gov.pl/static/xml/otwarte_dane_latest.xsd).
Jedynie korzeń jest w przestrzeni `urn:otwarte-dane:harvester:1.13`, a elementy
potomne pozostają bez kwalifikacji zgodnie z XSD. `extIdent` zbioru i zasobów
są trwałe. `lastUpdateDate` opisuje eksport; nie nadajemy wszystkim AED aktualnej
daty kontroli. Tytuł, opis, kategorie `HEAL` i `JUST`, częstotliwość i zasoby są w XML.

OSM jest na [ODbL 1.0](https://www.openstreetmap.org/copyright?locale=en-GB),
dlatego paczka pochodna zachowuje ODbL i atrybucję. XSD nie ma ODbL w słowniku
Creative Commons; zapisujemy ją w przewidzianym polu `conditions/dbOrCopyrighted`.
Generator obsługuje `CC0-1.0` i `CC-BY-4.0` dla niezależnych źródeł bez OSM,
lecz odrzuca taką zmianę licencji danych OSM. Przykładowy rejestr instytucjonalny
jest syntetyczny i na CC0. Nieustalona licencja uploadu wymaga określenia praw
przed wykorzystaniem do publikacji.

Źródła techniczne: [standardy otwartości](https://www.gov.pl/web/ia/standardy-otwartosci-danych),
[Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API),
[dokumentacja godzin OSM w Pythonie](https://remi-dupre.github.io/opening-hours-rs/opening_hours.html).
XSD oraz rzeczywisty cache pobrano 2026-11-21; czas źródła jest zapisany w cache.

## Testy

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_pipeline backend.test_danegov -v
.\.venv\Scripts\python.exe -m pip check
```

Testy są deterministyczne i nie wymagają dostępu do internetu. Obejmują
rzeczywisty cache, timeout, niepełną odpowiedź, mapowania, próg odległości,
konflikty, godziny/święta/strefy, kontrolę uploadu i wszystkie formaty eksportu,
w tym walidację XML względem XSD.

Szczegóły rzeczywistych zbiorów, parserów i ograniczeń publikacji JSON:API:
[integracja_danegov.md](../docs/integracja_danegov.md).

Nowe trasy `/api/rescue/nearest`, `/api/chaos-import`, `/api/import/bip-url`,
paszporty QR, zgłoszenia SQLite i ranking jakości są opisane w
[funkcje_ratunkowe.md](../docs/funkcje_ratunkowe.md). Dotychczasowe trasy zachowano.
Testy rozszerzenia: `python -m unittest backend.test_features -v` z aktywnym `.venv`.

Prosty ekran dodaje `GET /api/location/search?q=...` (miejscowość lub adres,
Polska, lokalny `data/cache/locations.json`, jawne zatwierdzenie, wspólny limit OSM).
Niejednoznaczne wyniki zwracają 422 z prośbą o doprecyzowanie, brak sieci bez cache
zwraca 503. API nie ustala pozycji GPS na podstawie wpisanej nazwy.
`GET /api/aed` przyjmuje dodatkowo parę `lat`, `lon` i `radius_km` (0,5–50,
domyślnie 15); dotychczasowe filtry i trasy pozostają zgodne.
`POST /api/rescue/nearest` przyjmuje opcjonalne `zrodlo`: `wszystkie`, `danegov`, `osm`.
Regresje: `python -m unittest backend.test_simple_search -v` w `.venv`.
