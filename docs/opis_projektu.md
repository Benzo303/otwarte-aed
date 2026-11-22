# Otwarte AED — Dane, które ratują minuty

## Cel i problem

Otwarte AED integruje rozproszone informacje o defibrylatorach, aby ułatwić
publikację jednolitego zbioru w dane.gov.pl i wyszukanie urządzenia dostępnego
w chwili zdarzenia. Lokalizacja na mapie nie wystarcza: potrzebne są godziny,
informacja o kluczu, dokładne miejsce w budynku, źródło i aktualność danych.

## Rozwiązanie

Klient JSON:API 1.4 wyszukuje rzeczywiste zasoby dane.gov.pl i łączy je
z ogólnopolską migawką OpenStreetMap. Normalizator mapuje pola, łączy rekordy
oddalone o mniej niż 25 m, zachowuje pochodzenie i jawne braki. Instytucjonalne
źródła mają pierwszeństwo, a rozbieżności pozostają widoczne.
W aktualnej migawce 18 307 obiektów OSM i 49 rekordów instytucjonalnych
daje 17 381 lokalizacji po 975 scaleniach. Są to dane prototypu, nie kompletny
państwowy rejestr ani potwierdzenie sprawności wszystkich urządzeń.

Wzorzec XLSX opisuje 21 pól, typy, wymagalność, walidację i przykłady DEMO.
FastAPI udostępnia CSV, JSON, GeoJSON i XML harvestera walidowany względem XSD.
Zasoby instytucjonalne: Krosno 3624 (21), Przemyśl 4581 (21), Marki 4955 (7).
Warszawa 39512 jest odnaleziona, ale jej wskazany plik zwraca HTML i nie zasila zbioru.

## Użytkownicy

Świadek odpowiada na dwa pytania, wpisuje miejscowość/ulicę albo używa GPS,
sprawdza najwyżej trzy otwarte AED i czyta dokładny opis położenia.
Zamknięte punkty, klucz, serwis i świeże ostrzeżenia są wykluczane z rekomendacji.
Marsz jest szacunkiem odległości ×1,25 przy 5 km/h, a nie trasą po chodnikach.
Instrukcja wskazuje telefon pod 112, RKO i wysłanie innej osoby po urządzenie.

Dysponent wgrywa CSV/XLSX, poprawia wskazane błędy i pobiera dane maszynowe.
Importer BIP przyjmuje też tekstowy PDF, HTML, JSON, GeoJSON i XML, rozpoznaje
aliasy i DMS; skany wymagają OCR. Import roboczy pozostaje osobnym podglądem.
Generator QR tworzy tabliczkę do karty konkretnego AED. Zgłoszenia terenowe
trafiają do SQLite, a audyt pokazuje ranking jakości źródeł A–F.

## Kampania

Nazwa: Otwarte AED. Hasło: Dane, które ratują minuty.
Serce z EKG odnosi się do pomocy, pinezka do lokalizacji, otwarty węzeł do
współdzielenia danych. Logotyp jest na stronie, w księdze znaku i prezentacji;
pakiet zawiera SVG, PNG, JPG i PDF. QR oraz prosty wzorzec obniżają próg
udostępnienia danych i zachęcają opiekunów AED do aktualizacji informacji.

## Ograniczenia i wdrożenie

Braki źródeł i niepełne pokrycie instytucji pozostają jawne. Deduplikacja
w budynkach wielopiętrowych wymaga oceny, a wskaźnik kompletności nie jest
kontrolą techniczną. Publiczne API służy odczytowi; publikacja wymaga panelu
dysponenta/harvestera, publicznego HTTPS i skonfigurowanych adresów zasobów.
Połączenie z OSM zachowuje ODbL i atrybucję; dane CC BY zachowują autorstwo.
Nie wykonano pomiaru wpływu na czas udzielania pomocy ani pełnego audytu WCAG.
Przed produkcją potrzebne są moderacja zgłoszeń, monitoring i weryfikacja dysponentów.

## Materiały do oceny

Prezentacja PPTX/PDF ma 6 slajdów, opis ścieżek, diagram i ograniczenia.
Pięć rzeczywistych zrzutów ekranu przekazanych przez zespół pokazuje źródła,
wzorzec XLSX, wyszukiwanie otwartych AED, generator QR i eksport XML.
Podmianę obrazów i regenerację opisuje docs/zrzuty_ekranu/INSTRUKCJA.md.
Kod źródłowy, wzorzec XLSX i branding znajdują się w repozytorium.
Zespół powinien przeanalizować i zatwierdzić finalną pracę przed wysłaniem.
