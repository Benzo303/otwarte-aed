# Wdrożenie Otwarte AED na Vercel — poprawka vercel-2

## Naprawione błędy

1. `ModuleNotFoundError: No module named fastapi`: pełne zależności backendu
   w pyproject.toml, Python 3.12, standardowy punkt wejścia app.py.
2. `OSError: Read-only file system: /var/task/backend/data/state`: w trybie
   Vercel aplikacja nie tworzy SQLite w katalogu kodu. Cache roboczy trafia
   do katalogu tymczasowego, a zgłoszenia i importy do PostgreSQL.
3. Przygotowywanie krajowego zbioru przeniesiono do etapu budowania.
   Gotowa migawka jest także dołączona do poprawki na wypadek jej ręcznego
   przesyłania. Przy starcie nie wykonujemy normalizacji 17 tysięcy AED.
4. Duże odpowiedzi JSON i eksporty są strumieniowane w porcjach do 32 KiB.

## Wgranie przez stronę GitHub

1. Otwórz GŁÓWNY katalog repozytorium, obok istniejących backend i frontend.
2. Wybierz Add file > Upload files.
3. Otwórz folder DO_WGRANIA_VERCEL obok kopii otwarte-aed_GITHUB.
4. Zaznacz jego ZAWARTOŚĆ (backend, frontend, docs i pliki główne),
   a następnie przeciągnij ją do GitHuba. Nie dodawaj zewnętrznego folderu
   DO_WGRANIA_VERCEL jako kolejnego poziomu w repozytorium.
5. Zatwierdź wszystko jednym Commit changes, np. „Vercel: naprawa startu”.
6. Sprawdź nowe wdrożenie w Vercel, powiązane z tym właśnie commitem.
   Jeśli używasz Redeploy, wybierz najnowszy commit i wyłącz build cache.

Framework: FastAPI. Root Directory: główny katalog repozytorium (./).
Usuń wcześniejsze ręczne nadpisania Install Command/Build Command, jeśli
omijają instalowanie bibliotek lub uruchamianie skryptu z pyproject.toml.
Domyślny etap budowania: python -B -m backend.vercel_build.

Kontrola po wdrożeniu:
https://otwarte-aed.vercel.app/api/health
Powinno być ready=true, records=17381 oraz cloud.runtime_version=vercel-2.
Pole cloud.commit pozwala sprawdzić, który commit rzeczywiście uruchomiono.

## Trwałe zgłoszenia i synchronizacja

Bez DATABASE_URL/POSTGRES_URL działa jawny tryb odczytu: mapa, wyszukiwanie,
QR, walidacja, czyszczenie plików i pobieranie eksportów pozostają dostępne.
Zgłoszenie nie jest oznaczane jako zapisane, gdy nie ma trwałej bazy.
Przycisk synchronizacji i zapis podglądu importu są wtedy niedostępne.

Aby włączyć zapis:
1. W projekcie Vercel otwórz Storage/Marketplace i podłącz PostgreSQL,
   np. przez integrację Neon. Wybierz region europejski.
2. Połącz bazę ze środowiskiem Production tego projektu.
3. Sprawdź, czy istnieje zmienna DATABASE_URL albo POSTGRES_URL.
   Wartość pozostaje w panelu Vercel; nie umieszczaj jej w kodzie ani czacie.
4. Ustaw AED_PUBLIC_BASE_URL=https://otwarte-aed.vercel.app.
5. Wykonaj nowe wdrożenie, aby funkcja otrzymała nowe zmienne środowiskowe.
6. Sprawdź /api/health: cloud.mode=postgresql i writes_enabled=true.
7. Sprawdź zapis zgłoszenia na urządzeniu testowym i trwałość po nowym
   żądaniu. Nie dodawaj fałszywych zgłoszeń do rzeczywistego AED.

Tabele otwarte_aed_reports, otwarte_aed_imports i otwarte_aed_snapshot są
zakładane automatycznie. Wymagane są uprawnienia do tworzenia tabel w tej
bazie. Istniejące inne tabele nie są usuwane ani modyfikowane.
Migawka po synchronizacji jest przechowywana jako skompresowana paczka
w PostgreSQL. Inne instancje funkcji wykrywają nową wersję co najwyżej
po około 5 sekundach od następnego odczytu. Raporty terenowe są odczytywane
bezpośrednio z bazy. Globalna blokada SQL zapobiega równoczesnej synchronizacji.
Osobny Vercel Blob nie jest wymagany w tej wersji prototypu.

Wersja online przyjmuje pliki do 3 MiB, aby uwzględnić narzut multipart
w standardowym limicie żądania Vercel. Import BIP z URL zachowuje limit
pobieranego zasobu 5 MiB. Wyniki pozostają w formatach maszynowych.

## Stan zweryfikowany 22 listopada 2026

- Produkcyjny HTTPS: https://otwarte-aed.vercel.app/.
- `/api/health`: ready=true, records=17381, cloud.mode=postgresql, writes_enabled=true.
- Neon przechowuje zgłoszenia, importy i migawkę; inne instancje odczytują wspólną wersję.
- Sprawdzono zapis testowego nieaktywnego importu i synchronizację bez fałszowania zgłoszeń realnych AED.
- 70 testów backendu zaliczonych; jeden test integracyjny bez lokalnego DSN pominięty.
- 10 testów logiki JavaScript i cztery scenariusze interfejsu zaliczone.
- Publiczny XML przechodzi walidację względem aktualnego XSD 1.13 dane.gov.pl.
- Przegląd WCAG 2.2 A/AA, rozmiary ekranu, poprawki i ograniczenia: `audyt_dostepnosci.md`.

Sekcje powyżej opisują konfigurację od zera; hosting i baza w obecnym projekcie
są już podłączone. Nie kopiuj sekretów DATABASE_URL do repozytorium ani paczki konkursowej.
To prototyp hackathonowy; nie zastępuje dyspozytora numeru 112.

Dokumentacja:
- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/docs/marketplace-storage
- https://www.psycopg.org/psycopg3/docs/basic/usage.html
