# Integracja dane.gov.pl — rzeczywiste dane

Klient używa `https://api.dane.gov.pl/1.4` i `Accept: application/vnd.api+json`.
Wyszukuje `q=AED`, `q=defibrylator`, `q=defibrylatory`, stronicując `page` i
`per_page=50`, również zasoby datasetów. Wyniki fuzzy search są dodatkowo
filtrowane po rzeczywistym wystąpieniu AED/defibrylator w metadanych; lista
odrzuconych ID i pełne odpowiedzi wyszukiwania pozostają w cache.

## Zbiory odczytane 21 listopada 2026

| ID / zbiór | Instytucja z API | Rekordy przed deduplikacją przestrzenną | Stan |
| --- | --- | ---: | --- |
| [3624 — Defibrylatory zlokalizowane w Mieście Krosno](https://dane.gov.pl/pl/dataset/3624) | Urząd Miasta Krosna | 21 | CSV; CC0 1.0 |
| [4581 — Lokalizacje AED – Automatycznych Defibrylatorów Zewnętrznych w Przemyślu](https://dane.gov.pl/pl/dataset/4581) | Urząd Miejski w Przemyślu | 21 | CSV, JSON, GeoJSON; CC0 1.0 |
| [4955 — Defibrylatory zlokalizowane na terenie Miasta Marki](https://dane.gov.pl/pl/dataset/4955) | Urząd Miasta Marki | 7 | CSV/XLSX; CC BY 4.0 |
| [39512 — Lokalizacja defibrylatorów (AED)](https://dane.gov.pl/pl/dataset/39512) | Urząd m.st. Warszawy | 0 | znaleziony; URL pliku JSON zwraca HTML, również po próbie download_url |

Krosno: zasób 54632. Przemyśl: 62093/62094/62095; GML 62092/62424
pobrano, ale nie wykorzystano pozycji bez jawnego CRS. Marki: 68353/68355.
Warianty formatowe z tym samym identyfikatorem punktu nie zwiększają licznika
rekordów. Pełna lista plików, sumy SHA-256, błędy parsera, odrzucone wiersze
i metadane źródłowe znajdują się w cache.

Pliki Marek mają błędne etykiety osi i podwójne opakowanie CSV. Osie zamieniamy
wyłącznie wtedy, gdy druga orientacja jednoznacznie mieści się w zakresie Polski.
Jeden punkt opisany jako Marki leży w Krośnie: odrzucamy go jako >100 km od
mediany pozostałych punktów tej samej miejscowości. Kontrolę tę stosujemy tylko
dla co najmniej pięciu punktów ze wspólną miejscowością. Nie geokodujemy adresów
i nie poprawiamy lokalizacji przez zgadywanie. W XML projektowane układy
współrzędnych i GML bez określonego CRS pozostają do weryfikacji.

## Migawka i odświeżanie

Mapa domyślnie pokazuje **całą Polskę**, bez wpisanego miasta. Filtr źródeł
pozwala wybrać połączoną bazę, `dane.gov.pl` lub OSM. Przycisk „Pokaż wszystkie
punkty z API dane.gov.pl” czyści miasto i wyszukiwanie, wybiera źródło dane.gov.pl
oraz jawnie wyłącza filtr dostępności, aby pokazać również niepotwierdzone AED.
Oznaczenia otwarcia pozostają zgodne z rzeczywistymi danymi. Endpoint
`/api/aed?zrodlo=danegov` zwraca rekordy z co najmniej jednym źródłem portalu,
także połączone z OSM. `zrodlo=osm` również obejmuje rekordy połączone.
49 rekordów wejściowych portalu daje 48 punktów po deduplikacji, ponieważ dwa
rekordy Marek wskazują to samo miejsce. Zasięg wyszukiwania katalogu jest
ogólnopolski; dostępne zasoby instytucjonalne nie zapewniają pełnego pokrycia kraju.

`backend/data/cache/danegov_cache.json` zawiera datę pobrania, wszystkie odpowiedzi
wyszukiwania, metadane instytucji/zbiorów/zasobów, oryginalne pliki zakodowane
base64, sumy plików oraz rozpoznane rekordy. Timeout używa poprzedniej poprawnej
migawki i zachowuje pierwotną datę pobrania. Błędy poszczególnych zasobów są jawne.
Globalna awaria lub pusta nieudana synchronizacja nie zastępuje dobrego cache.

Parser obsługuje CSV (UTF-8/BOM, CP1250; średnik/przecinek/tabulator), XLSX,
listy i zagnieżdżone JSON, GeoJSON Point, WKT POINT oraz tabelaryczne XML/GML
z jawnym CRS WGS84. Ma limity pliku, rozpakowanego XLSX i liczby wierszy;
odrzuca formuły XLSX, DTD i strony HTML. Schemat nie wywodzi godzin dostępności
ze swobodnych opisów ani dat kontroli AED z daty modyfikacji pliku.

Przy integracji krajowej zachowujemy kontekst miasta z lokalnych zapytań
administracyjnych OSM (obecnie Warszawa). Większość punktów AED nie ma tagu
`addr:city`, więc sam filtr po tym tagu pomijał 1076 z 1077 obiektów warszawskich.
Uzupełnienie miasta i TERYT wymaga zgodnego typu/ID obiektu oraz pozycji
zmienionej o najwyżej 1 m względem migawki miejskiej; przeniesiony obiekt nie
dziedziczy starego miasta. Metoda i data zapytania są w
`sources[].administrative_context`. Pozostałym punktom nie zgadujemy miejscowości.

### Wyszukiwanie miasta niezależne od brakujących adresów

`backend/city_search.py` dopasowuje współrzędne AED do Polygon/MultiPolygon
miejscowości (z uwzględnieniem otworów i granicy). Granice pochodzą z OSM
przez Nominatim. Nie zastępujemy granicy promieniem ani prostokątem. API zwraca
rozpoznane miasto i zasięg mapy w `city`. Pole `miejscowosc_wyszukiwania`
jest opisem wyniku przestrzennego, nie zmianą danych źródłowych ani eksportu.
Wpisanie miasta działa także dla punktów bez `addr:city`.

W tym lokalnym prototypie świadomie używamy publicznego Nominatim wyłącznie
do pojedynczych wyszukiwań miejscowości przez użytkownika, zgodnie z
[polityką usługi](https://operations.osmfoundation.org/policies/nominatim/).
Obowiązuje identyfikujący User-Agent, maksymalnie jedno żądanie na sekundę,
trwały cache `backend/data/cache/city_boundaries.json` i brak autocomplete
oraz masowego geokodowania. Wyszukiwanie zatwierdza się Enterem lub przyciskiem;
odświeżanie co minutę ma `geokoduj=false` i nie odpytuje geokodera.
Uruchomienie używa jednego procesu Uvicorn. Przy większym ruchu/wielu procesach
należy użyć własnej usługi lub dostawcy przez `AED_GEOCODER_URL` (zgodne API
Nominatim), aby zachować limit wspólny dla aplikacji. `AED_CITY_OFFLINE=true`
wyłącza nowe pobrania; wcześniej zapisane granice działają bez sieci.

Rozpoznawane są nazwy bez polskich znaków. Miasto ma pierwszeństwo przed wsią
o tej samej nazwie; przy imiennikach tego samego typu trzeba dopisać powiat lub
województwo. Błąd geokodera lub nierozpoznane miasto daje opis błędu zamiast
informacji sugerującej brak AED. Filtr źródła pozostaje aktywny: gdy katalog
dane.gov.pl nie obejmuje miasta, można jawnie włączyć OSM przyciskiem na pustej liście.

Domyślny start działa offline. POST `/api/danegov/refresh` pobiera katalog i pliki,
łączy je z krajową migawką OSM i podmienia jednym przypisaniem rekordy, statystyki
oraz wszystkie eksporty w pamięci. Operacje sieciowe i normalizacja działają poza
pętlą asynchroniczną. W czasie synchronizacji GET nadal zwraca poprzednią migawkę;
drugi POST dostaje 409. Pliki dyskowe są podmieniane atomowo pojedynczo.
Podgląd w interfejsie pobiera maksymalnie 40 kB przez HTTP Range (206),
z zachowaniem rozmiaru całego zasobu w Content-Range. Pobranie bez Range zwraca
pełny, poprawny maszynowo plik. Fragment w podglądzie jest wyraźnie oznaczony.

CLI pełnego pobrania:

```powershell
.\.venv\Scripts\python.exe -m backend.danegov_client
.\.venv\Scripts\python.exe -m backend.fetcher --area polska
.\.venv\Scripts\python.exe -m backend.harvester_export --offline
```

W zrealizowanym pobraniu OSM było 18 307 obiektów i 49 rekordów dane.gov.pl.
Usunięto 975 powtórzeń, pozostawiając 17 381 punktów; 38 grup łączy oba źródła.
To liczby z migawki, a nie obietnica kompletności pokrycia AED w Polsce.
Żaden rekord nie spełnia wszystkich wymaganych pól rygorystycznego wzorca
dysponenta: braki i konflikty są jawne w `quality_errors` i `schema_valid`.

## Paczka publikacyjna i ograniczenia API

`backend/exports/danegov_api_payload.json` to dokument JSON:API: `data.type=dataset`,
powiązania `relationships.resources.data` i `included` typu `resource`. Nazwy pól
odpowiadają obiektom publicznej specyfikacji API 1.4. ID w paczce są lokalne:
portal nadaje własne identyfikatory i przypisuje instytucję. Kategorie: HEAL
(Zdrowie), JUST (bezpieczeństwo publiczne); domyślna częstotliwość nieregularna,
bo prototyp odświeża się ręcznie. Samo oznaczenie `daily` nie tworzy harmonogramu.

Publiczna [specyfikacja OpenAPI 1.4](https://api.dane.gov.pl/spec/1.4) i
[dokumentacja](https://api.dane.gov.pl/1.4/doc) zawierają dla zbiorów i zasobów
wyłącznie GET. Nie ma publicznego kontraktu POST/PATCH do publikacji zwrotnej.
Nie udajemy więc skutecznego zapisu do portalu: paczka wymaga panelu dostawcy
lub [harvestera XML 1.13](https://dane.gov.pl/static/xml/otwarte_dane_latest.xsd).
XML jest walidowany względem oficjalnego XSD.

Przed zgłoszeniem ustaw `AED_PUBLIC_BASE_URL=https://publiczny-host.pl`, udostępnij
zasoby i XML/MD5 pod tym adresem oraz przypisz dysponenta w portalu. Domyślne
`aed.example.org` jest placeholderem, wskazanym jako blokada w `meta` payloadu.
Żaden skrypt nie wysyła POST do API dane.gov.pl.

**Licencja:** połączona baza zawierająca OSM zachowuje ODbL 1.0 oraz autorstwo
źródeł instytucjonalnych. Nie wolno nazwać jej CC0. Generator tworzy payload
CC0 1.0 dla osobnego zestawu wyłącznie ze źródeł CC0; dla źródeł CC BY zachowuje
CC BY, a dla OSM ODbL. Żądanie CC0 dla bazy zawierającej OSM jest odrzucane.
Źródło warunków OSM: [OpenStreetMap copyright](https://www.openstreetmap.org/copyright).

## Testy

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_pipeline backend.test_danegov -v
```

Obejmują rzeczywiste cache, paginację, wszystkie wymagane zapytania, timeout,
oryginalny niezmieniony cache po awarii, parsery i rozpoznawanie osi/WKT,
priorytet instytucji, zachowanie proweniencji i konfliktów, licencje, JSON:API,
XSD oraz atomową podmianę migawki i zachowanie starej przy błędzie synchronizacji.
