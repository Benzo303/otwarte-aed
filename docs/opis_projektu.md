# Otwarte AED — Dane, które ratują minuty.

## Cel

Otwarte AED ułatwia zebranie rozproszonych informacji o defibrylatorach w jednolitym
zbiorze przeznaczonym do udostępniania w dane.gov.pl. Mapa pokazuje lokalizację,
faktyczne godziny dostępu, bariery wejścia, opis miejsca i pochodzenie informacji.
Kampania „Dane, które ratują minuty.” zachęca dysponentów do otwierania i aktualizacji danych.

## Działający prototyp

Adres: https://otwarte-aed.vercel.app/ — publiczny HTTPS, komputer i telefon.
FastAPI działa na Vercel, a PostgreSQL (Neon) trwale przechowuje zgłoszenia terenowe,
importy oraz wspólną migawkę po synchronizacji. Lokalny wariant używa SQLite.
Kontrola działania: https://otwarte-aed.vercel.app/api/health.

W pomiarze z 22 listopada 2026 r. połączono 18 307 obiektów OpenStreetMap
i 49 rekordów instytucjonalnych. Po 975 scaleniach pozostało 17 381 punktów;
38 grup zachowuje pochodzenie z obu rodzajów źródeł.
Zbiory dane.gov.pl: Krosno 3624 (21), Przemyśl 4581 (21), Marki 4955 (7 rekordów
wejściowych). Zbiór Warszawy 39512 jest odnaleziony, ale nie dostarczył poprawnej
tabeli i nie zasila mapy. Liczby dotyczą migawki prototypu, nie kompletnego rejestru kraju.
Dowód: docs/dane_prezentacji.json i GET /api/sources/stats.

## Mechanizm integracji

Klient JSON:API 1.4 wyszukuje AED w dane.gov.pl, pobiera maszynowe zasoby,
rozpoznaje różne nazwy kolumn i łączy dane z ogólnopolską migawką OSM.
Cache pozwala kontynuować pracę przy awarii źródła. Normalizator stosuje Haversine
i promień poniżej 25 m, priorytet informacji instytucjonalnej oraz zachowanie źródeł,
rozbieżności i jawnych braków. Wskaźnik „Jakość informacji” ocenia kompletność danych,
pochodzenie i uwzględnione zgłoszenia; nie jest potwierdzeniem sprawności AED.

Wzorzec XLSX zawiera 21 pól, typy, wymagalność, walidacje oraz oznaczone przykłady DEMO.
Publikowane dane są w CSV, JSON i GeoJSON; metadane harvestera w XML zgodnym
z oficjalnym XSD 1.13. PDF i HTML mogą być wejściem importera, nie formatem wyjściowym danych.
Publiczne URL eksportów są skonfigurowane. Publikacja w samym portalu wymaga
przypisania dysponenta i użycia harvestera lub panelu dostawcy; nie wykonano zapisu do portalu.
Połączenie danych OSM zachowuje ODbL oraz atrybucję instytucji; nie jest oznaczane jako CC0.

## Ścieżka świadka zdarzenia

1. Ocenia reakcję i prawidłowy oddech w dwóch pytaniach; otrzymuje wskazówki wezwania 112.
2. Wpisuje miejscowość/ulicę albo korzysta z GPS.
3. Widzi maksymalnie trzy pobliskie otwarte AED, opis miejsca, szacowany czas i nawigację.
4. Otwiera prostą kartę, może odsłuchać wskazówki lub zgłosić stan z miejsca.

Routing uwzględnia Europe/Warsaw, harmonogram, klucz, stan serwisowy i świeże ostrzeżenia.
Marsz jest szacunkiem: odległość w linii prostej ×1,25, prędkość 5 km/h.
Po AED należy wysłać inną osobę; samotny świadek nie powinien przerywać RKO na szukanie urządzenia.

## Ścieżka dysponenta

1. Otwiera boczny panel i waliduje CSV/XLSX albo importuje tabelę z BIP/PDF/HTML.
2. Poprawia wskazane błędy i pobiera uporządkowany CSV lub JSON według 21 pól.
3. Generuje tabliczkę QR kierującą do karty konkretnego urządzenia pod publicznym HTTPS.
4. Sprawdza audyt źródeł i przygotowuje paczkę dla portalu.

Import roboczy pozostaje osobnym podglądem. Online upload ma limit 3 MiB;
import BIP obsługuje do 500 rekordów i 20 stron PDF, bez OCR skanów.
Anonimowe zgłoszenia wymagają docelowej moderacji i kontroli dysponentów.

## Dostępność i UX

Prosty ekran, równoważna lista obok mapy, klawiatura, widoczny fokus, wysoki kontrast,
powiększanie tekstu i natywny lektor są wdrożone. Przegląd WCAG 2.2 A/AA i poprawki
opisano w docs/audyt_dostepnosci.md; wyniki maszynowe są w docs/audyt_dostepnosci.json.
Raport podaje zakres i ograniczenia zamiast deklaracji pełnej zgodności AAA.

## Kampania i materiały

Nazwa: Otwarte AED. Hasło: Dane, które ratują minuty.
Serce z EKG, pinezka i otwarty węzeł symbolizują pomoc, lokalizację oraz współdzielenie danych.
Identyczny źródłowy SVG jest na stronie i w księdze znaku. Dostępne formaty logo:
SVG, PNG, JPG i PDF. Księga zawiera paletę, pole ochronne, minimalną skalę,
niedozwolone użycia oraz cztery zdania opisu koncepcji.
Prezentacja PPTX/PDF ma sześć slajdów, pięć dowodów ekranowych, ścieżki i ograniczenia.

## Ograniczenia

Niepełne pokrycie instytucji, brakujące godziny i opisy oraz niepotwierdzony stan urządzeń
pozostają jawne. Deduplikacja w budynkach wielopiętrowych wymaga kontroli.
Nie przeprowadzono badania wpływu na czas udzielania pomocy. Zewnętrzna nawigacja,
kafelki mapy i nowe wyszukiwania lokalizacji mogą wymagać sieci.
Testy z użytkownikami technologii asystujących, moderacja i monitoring operacyjny
pozostają etapem dalszego wdrożenia. Prototyp nie jest oficjalnym państwowym rejestrem.

Zespół przed zgłoszeniem analizuje i zatwierdza końcową pracę, autorstwo i prawa
do własnych materiałów oraz zachowuje licencje wykorzystanych danych i bibliotek.
