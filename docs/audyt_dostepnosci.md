# Przegląd dostępności Otwarte AED

Data: 22 listopada 2026 r. Standard odniesienia: WCAG 2.2, poziomy A i AA.
Wersja: kopia konkursowa otwarte-aed_GITHUB, po poprawkach etykiet, fokusu i reflow.

## Wynik

W 13 scenariuszach przeglądarkowych axe-core 4.14.1 nie zgłosił
naruszeń objętych regułami WCAG A/AA. Ręcznie sprawdzono klawiaturę, powrót fokusu,
obsługę Escape, zachowanie panelu, wąski ekran i powiększony tekst.
To udokumentowany przegląd prototypu, nie certyfikat ani deklaracja pełnej zgodności AAA.
Zero błędów narzędzia nie jest samodzielnym dowodem spełnienia wszystkich kryteriów WCAG.

## Metoda i środowisko

- Rzeczywista przeglądarka Chromium w środowisku testowym; lokalna kopia kodu aplikacji.
- Dane: dołączona migawka ogólnopolska, 17 381 punktów; zapisy testowe wyłącznie w pamięci.
- axe-core pobrany z oficjalnego rejestru npm, integralność SHA-512 zweryfikowana.
- Zakres reguł: wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa.
- Szerokości treści: około 1261 px, 390 px i 320 px (305 px po odjęciu paska przewijania).
- Dodatkowe warunki: tekst 200%, odstęp liter 0,12 em, słów 0,16 em,
  wysokość wiersza 1,5 oraz odstęp po akapicie 2 em.
- Wyniki i sumy SHA-256 badanych plików są w audyt_dostepnosci.json.
- Narzędzie audytu działało poza produkcyjną aplikacją i nie jest jej zależnością runtime.

## Zbadane widoki

Ekran główny; ustawienia dostępności; strefa dysponenta i formularze; integracja i eksporty;
karty najbliższych AED; szczegóły urządzenia; tryb wysokiego kontrastu; szerokość 320 px;
tekst 200%; zwiększone odstępy; krytyczny wynik asystenta; szufladka mobilna.

## Znalezione i usunięte problemy

| Problem | Poprawka | Kryterium |
|---|---|---|
| Przycisk powiększania miał inną nazwę niż etykieta na ekranie | Nazwa dostępności zawiera „Powiększ napisy” i bieżący procent | 2.5.3 |
| Trzy przyciski nawigacji pomijały w nazwie „do tego AED” | Zachowano pełną widoczną etykietę oraz nazwę miejsca | 2.5.3 |
| Przypięty panel mógł zasłaniać element wybrany klawiaturą | Powrót fokusu do treści zamyka panel bez zmiany docelowego fokusu | 2.4.11 |
| Blok 112 i długie słowo nie mieściły się przy dużym tekście | Zawijanie bloku i długich słów; brak poziomego przewijania treści | 1.4.4, 1.4.10, 1.4.12 |
| Automatyczne aktualizacje nie miały jawnego wstrzymania | Przełącznik w dodatkowych filtrach i ochrona fokusu listy/mapy | 2.2.2, 2.4.3 |
| Karty TOP 3 miały poziom nagłówka równy nagłówkowi ich sekcji | Nagłówki kart h4; nazwane przewijane regiony tabel i podglądu | 1.3.1 |

## Sprawdzenia ręczne i uzupełniające

| Obszar | Wynik i dowód |
|---|---|
| Pominięcie nagłówka | Link „Przejdź do treści” przenosi fokus do main; Tab przechodzi do pierwszej odpowiedzi asystenta |
| Klawiatura i okna | Mobilna szufladka ma aria-modal=true i inert tła; Shift+Tab zawija fokus; Escape zamyka i oddaje fokus |
| Desktop | Panel jest niemodalny; powrót do wyszukiwarki odsłania fokus; hover/przypięcie dodatkowo sprawdzone testem DOM |
| Karta AED | Escape zamyka dialog i przywraca fokus przycisku karty |
| Fokus | Obserwowana ramka ma 3 px, styl solid, kolor #0052A5 |
| Rozmiar i reflow | Treść mieści się przy 320 px, tekście 200% i zwiększonych odstępach; mapa i tabele mają własne przewijanie |
| Kontrast klastrów | Biel / #123B34: 12.35:1; biel / #096B50: 6.5:1 |
| Wysoki kontrast | #FFED00 / #000000: 17.37:1; odrębny wariant logo i etykiet |
| Granice pól | #66768B / biel: 4.64:1 |
| Symbole powiększania mapy | Plus i minus mają opisane funkcje „Powiększ mapę” / „Pomniejsz mapę”; oceniono ręcznie |
| Nazwy, struktura, formularze | Lang=pl, nagłówki, etykiety, nazwy dialogów, komunikaty statusu i błędów sprawdzone w DOM/AX i axe |
| Alternatywa dla mapy | Nazwana lista AED zawiera te same działania; ukryta dla czytników warstwa markerów nie ma fokusu |
| Multimedia i ruch | Brak automatycznego dźwięku; użytkownik uruchamia/zatrzymuje lektor i rytm; ograniczenie ruchu sprawdzone w CSS i teście DOM |

Narzędzie pozostawiło do ręcznej oceny kontrast liczników klastrów i nazwy ikon +/-.
Uzupełniono ocenę obliczeniem kontrastu oraz odczytem nazw funkcji. Małe linki tekstowe
w atrybucji są linkami w tekście; checkboxy mają większą klikalną etykietę.
Nie traktowano samych wymiarów liter linku ani kwadratu checkboxa jako rozmiaru całego celu.

## Testy regresji

10 testów logiki JavaScript i cztery scenariusze DOM: mobile, desktop, QR deep link, clustering.
Sprawdzają też powiązanie nazw z etykietami, powrót do treści, możliwość pauzy aktualizacji
i zachowanie fokusu podczas pracy na liście. Wszystkie zaliczone.
Ostatnie testy niezmienionego backendu: 70 zaliczonych, jeden test wymagający lokalnego DSN
PostgreSQL pominięty. Produkcyjny PostgreSQL sprawdzono osobno we wdrożeniu.

## Ograniczenia oceny

Nie wykonano sesji z użytkownikiem NVDA/VoiceOver ani testu fizycznego telefonu z technologią
asystującą w tym przeglądzie. Rozmiary mobilne symulowano przez szerokość viewportu,
nie przez zmianę ustawień systemowych urządzenia. Syntetyczny test tekstu 200% nie jest
tożsamy ze sprawdzeniem każdej kombinacji powiększenia i ustawień każdej przeglądarki.
Metronom, GPS i lektor mają testy DOM z symulacją; dostępność głosów zależy od systemu.
Nie deklarujemy pełnej zgodności AAA. Usługi mapowe i zewnętrzna nawigacja mają własne interfejsy.
To zakres testowania dołączony do prototypu, z jawnym wskazaniem pozostałych testów użytkowych.

## Źródła

- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Nazwa zawierająca widoczną etykietę: https://www.w3.org/WAI/WCAG22/Understanding/label-in-name.html
- Reflow: https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
- Odstępy tekstu: https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html
- Fokus niezasłonięty: https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html
- axe-core: https://github.com/dequelabs/axe-core
