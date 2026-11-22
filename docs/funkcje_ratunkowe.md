# Funkcje ratunkowe i analityczne — Otwarte AED

Aktualny frontend ma prosty ekran z jednym polem szukania i boczny panel
pomocy/narzędzi zamiast trzech zakładek. Obsługa hover, dotyku i klawiatury,
nowe poziomy tekstu 100/120/135% oraz testy: [frontend/README.md](../frontend/README.md).

Wersja z 21 listopada 2026 r. Zachowano dotychczasowe API, wyszukiwanie
ogólnopolskie, cache źródeł, walidator 21 pól, synchronizację i eksporty.
Frontend odwzorowuje stylistykę gov.pl i oznacza serwis jako nieoficjalny prototyp.

## Dodane trasy

| Metoda i ścieżka | Dane wejściowe / rezultat |
| --- | --- |
| `POST /api/rescue/nearest` | JSON `lat`, `lon`, opcjonalnie `radius_km` 0,5–50 (domyślnie 15); TOP 3 i liczby odrzuconych punktów |
| `GET /api/aed/{id_aed}` | Karta urządzenia, bieżąca dostępność, informacje o zgłoszeniach |
| `GET /api/aed/{id_aed}/passport.svg` | Tabliczka z QR; opcjonalne `base_url` i `name`; istniejący identyfikator AED |
| `POST /api/aed/{id_aed}/report` | JSON `kind`: `working`, `closed`, `damaged` |
| `POST /api/chaos-import` | Multipart `file`, opcjonalne `geocode=false` |
| `POST /api/import/bip-url` | JSON `url`, opcjonalne `geocode=false` |
| `POST /api/import/{import_id}/preview` | Aktywacja importu w odrębnej bazie podglądu |
| `GET /api/import/preview` | Rekordy robocze oznaczone `is_preview` |
| `GET /api/danegov/audit` | Oceny zbiorów, punktacja, ranking instytucji i konkretne braki |

Przykład wyszukania: `{"lat":54.19,"lon":16.18,"radius_km":15}`.

## Dostępność i czas marszu

Backend ocenia harmonogram OSM w strefie Europe/Warsaw, wymaganie klucza,
ograniczenia dostępu, serwis, konflikty źródeł i świeże zgłoszenia terenowe.
Nieznana dostępność nie jest uznawana za potwierdzone otwarcie. Zamknięte punkty
pozostają widoczne po wyłączeniu filtra, lecz nie trafiają do TOP 3.

Odległość to Haversine, szacowany marsz = odległość × 1,25, prędkość 5 km/h.
Czas powrotu to dwukrotność marszu, bez szukania urządzenia ani obsługi.
Przerywana linia na mapie nie przedstawia rzeczywistej trasy pieszej.
Nawigację uliczną otwiera osobny link Google Maps. Przekroczenie 5 minut
powrotu jest oznaczone; czas nie jest gwarancją skuteczności pomocy.

## Paszport i zgłoszenia

`qrcode` generuje lokalnie QR z korekcją M i czteromodułowym marginesem.
SVG prowadzi do `/?aed=ID_AED`; aplikacja otwiera kartę bez pobierania całego
zbioru. Przed drukowaniem należy ustawić adres osiągalny dla skanujących.
Localhost na kodzie QR odnosi się do urządzenia skanującego.

SQLite zapisuje datę, rodzaj i identyfikator zgłoszenia. Brak dostępu lub
uszkodzenie wyklucza rekomendację przez 24 h i obniża Confidence Score o 10 pkt.
Pozytywne zgłoszenie dodaje 5 pkt, ale nie usuwa świeżego ostrzeżenia.
Wskaźnik jest ograniczony do 0–100. Data weryfikacji społecznej jest oddzielona
od daty źródła; zgłoszenie nie stanowi kontroli technicznej dysponenta.
Zgłoszenia prototypu są anonimowe; wdrożenie produkcyjne wymaga moderacji.

Baza: `backend/data/state/aed.sqlite3`; ścieżkę zmienia `AED_STATE_PATH`.
W Dockerze jest trwały wolumen `aed_state`. Kopię wykonuje się mechanizmem
backup SQLite albo po zatrzymaniu serwera (tryb WAL). Raporty nakładają się
na API, nie nadpisują źródeł ani ich eksportów.

## Importer BIP

Wejście: PDF, HTML, CSV, XLSX, JSON, GeoJSON, XML. Limity: 5 MiB, 500 wierszy,
20 stron PDF. PDF z tekstem/tabelą czyta pdfplumber/pypdf; skan wymaga OCR.
HTML jest odczytywany jako tabela/lista, bez wykonywania JavaScript.
Obsługiwane są aliasy kolumn, przecinki dziesiętne, DMS, wspólna kolumna GPS,
WKT POINT i GeoJSON. Kontrola kraju używa lokalnego wielokąta Polski.

Geokodowanie jest opcjonalne: maksymalnie 5 prób na import, wspólny limit
około jednego żądania/s z wyszukiwaniem miast i lokalny cache adresów.
Adres trafia do zewnętrznego geokodera OSM; oszacowany GPS wymaga kontroli.
Importer URL sprawdza DNS i każde przekierowanie, przypina publiczne IP,
ogranicza rozmiar oraz czas. Obsługuje publiczne HTTP/HTTPS.

Raport zwraca `changes`, `errors`, `quality`, `pending_records`, liczniki
i `import_id`. `standard_json` oraz `normalized_csv` zawierają dokładnie
21 pól; `normalized_json` ma dodatkowe informacje diagnostyczne.
Brakujące wartości pozostają puste. Rekord z GPS może nadal wymagać uzupełnienia.
Podgląd jest trwały i odrębny od rekomendacji oraz eksportów publicznych.
Import nie nadaje automatycznie praw do publikacji źródłowego dokumentu.

## Audyt instytucji

Punktacja surowego cache dane.gov.pl, przed uzupełnieniem OSM: format maszynowy
20 pkt, poprawny GPS w Polsce 30, pełny adres 20, harmonogram 15, opis miejsca 15.
Klasy: A ≥90, B ≥80, C ≥65, D ≥50, E ≥35, F <35.
HTML zamiast danych nie otrzymuje punktów za poprawny plik maszynowy.
Odrzucone rekordy GPS są uwzględniane. Ranking waży zbiory instytucji liczbą
rekordów; nie ocenia jakości opieki medycznej ani całkowitej liczby AED w gminie.

## Instrukcja ratunkowa i dostępność

Asystent dotyczy osoby dorosłej. Po stwierdzeniu braku reakcji wskazuje już
telefon pod 112 i ocenę oddechu; westchnień agonalnych nie uznaje za prawidłowy
oddech. Nie opóźnia RKO przenoszeniem z łóżka. Po AED wysyła inną osobę;
samotny świadek nie opuszcza poszkodowanego na szukanie urządzenia.
Źródła: [materialy_gov_erc.md](materialy_gov_erc.md).

Ściąga, Web Audio 110 BPM i Web Speech `pl-PL` nie wymagają kluczy API.
Głos zależy od systemu/przeglądarki. GPS wymaga HTTPS/localhost i zgody.
Pozycja służy do wyszukania, nie jest zapisywana w bazie zgłoszeń.
Kontrast czarno-żółty to około 17,37:1; są powiększanie tekstu, fokus, dialogi,
ARIA i klawiatura. Nie deklarujemy certyfikacji AAA bez pełnego audytu.

## Weryfikacja

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_pipeline backend.test_danegov backend.test_city_search backend.test_features -v
.\.venv\Scripts\python.exe -m compileall -q backend
.\.venv\Scripts\python.exe -m pip check
node --test frontend/tests/core.test.js
cd frontend
npm install --ignore-scripts
npm run test:ui
```

Testy backendu obejmują także dotychczasowe eksporty i XML XSD, miasta,
strefy czasowe, import, SSRF, trwałość SQLite i wykluczenie zgłoszonego AED.
Test DOM używa atrap API/audio/GPS. Automatyzacja prawdziwej przeglądarki
była w tej sesji niedostępna; wizualny test telefonu, głośnika i czytnika
ekranu pozostaje do wykonania na rzeczywistych urządzeniach.
