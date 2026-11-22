# Otwarte AED

## Stan wersji konkursowej — 22 listopada 2026

Prototyp online: https://otwarte-aed.vercel.app/ (HTTPS, Vercel, PostgreSQL / Neon). Zapis zgłoszeń, importów i migawki jest trwały; SQLite dotyczy wariantu lokalnego.

Materiały: [opis](docs/opis_projektu.md), [prezentacja](docs/prezentacja_otwarte_aed.pptx), [przegląd dostępności](docs/audyt_dostepnosci.md), [paczka konkursowa](docs/materialy_otwarte_aed.zip). Paczka zawiera obecny frontend, moduły chmurowe, konfigurację Vercel i migawkę startową. Sprawdzone sumy plików: docs/manifest_paczki.json.


**Najprostszy start w Windows:** kliknij dwukrotnie `START_AED.cmd` w tym katalogu.
Starter ustala ścieżkę z własnego położenia (`%~dp0`), więc możesz przenieść
cały folder projektu bez poprawiania ścieżek. Działa też uruchomiony z innego
katalogu terminala. W `frontend` są dodatkowe pliki START/STOP kierujące do
katalogu głównego.
Gdy `.venv` nie istnieje lub nie działa po przeniesieniu na inny komputer,
starter tworzy je przy użyciu zainstalowanego Python 3.10+ (`py -3` albo `python`)
i instaluje wymagane biblioteki. Niesprawne środowisko zachowuje jako
`.venv_backup_*`. Pierwsza instalacja wymaga internetu; gotowe środowisko
uruchamia aplikację bez ponownej instalacji.
Launcher uruchomi serwer w tle i otworzy `http://127.0.0.1:8000/` po osiągnięciu gotowości.
Nie otwieraj samego `frontend/index.html` i nie wpisuj `127.0.0.1/8080`.
Serwer pozostaje uruchomiony po zamknięciu okna startowego. `STOP_AED.cmd` go zatrzymuje.
Log startu: `backend/logs/server.log`. Ponowne uruchomienie START korzysta z działającego serwera.

## Test na telefonie

Alternatywne uruchomienie przez Docker Desktop: kliknij `START_DOCKER.cmd`.
Adres: `http://localhost:8080/`. Zatrzymanie: `STOP_DOCKER.cmd`.
Pełna instrukcja: [docs/docker.md](docs/docker.md).

Uruchom `START_TELEFON.cmd` (jest również w `frontend`). Starter przełącza własny
serwer na tryb sieci lokalnej i wypisuje **ADRES NA TELEFON** z bieżącym IPv4.
Adres zapisuje też w `backend/logs/telefon_url.txt`. Komputer i telefon muszą być
w tej samej sieci; komputer może łączyć się przewodowo z tym samym routerem.
W telefonie wpisz podany adres `http://IP_KOMPUTERA:8000/`, a nie `localhost`.
Komputer i serwer muszą pozostać włączone.

Na zaufanej sieci prywatnej, jeśli Windows zapyta o dostęp Pythona do sieci,
zezwól dla sieci prywatnej. Starter nie zmienia zapory ani profilu sieci.
Przy profilu Publicznym zapora lub izolacja urządzeń może blokować dostęp.
Do testu można użyć własnego hotspotu telefonu jako zaufanej sieci.
Zwykły `START_AED.cmd` przełącza aplikację z powrotem na dostęp tylko z komputera;
`STOP_AED.cmd` zatrzymuje oba tryby.

Interfejs jest responsywny. Szybki test układu bez telefonu w Chrome/Edge:
F12, następnie Ctrl+Shift+M i szerokość 390 px. Test w przeglądarce telefonu
obejmuje także rzeczywistą łączność sieciową i obsługę dotykową.

Projekt hackathonowy: integracja rozproszonych danych o defibrylatorach AED
na potrzeby portalu dane.gov.pl. Wzorzec opisuje rzeczywisty dostęp do urządzenia
oddzielnie od jego stanu technicznego.

## Struktura

```text
backend/          FastAPI, Overpass, normalizacja i eksporty harvestera
frontend/         responsywna mapa, strefa dysponenta i podgląd eksportów
data_standard/    generator i wzorzec danych AED
branding/         miejsce na identyfikację wizualną
docs/             dokumentacja standardu
.venv/            lokalne środowisko Python
```

## Środowisko

Wszystkie skrypty Python uruchamiaj lokalnym interpreterem projektu.
Środowisko `.venv` zostało utworzone, a wymagane biblioteki zainstalowane.
`requirements.txt` zawiera osiem wskazanych bibliotek, a `requirements-lock.txt`
zapisuje zainstalowane wersje wraz z zależnościami.

Odtworzenie środowiska na innym komputerze (PowerShell, z katalogu głównego):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
```

## Generowanie arkusza

```powershell
.\.venv\Scripts\python.exe data_standard\generuj_wzorzec_aed.py
```

Wynik: `data_standard/wzorzec_danych_aed.xlsx`. Generator używa `openpyxl`,
zapisuje plik i odczytuje go ponownie, sprawdzając strukturę, wartości,
listy rozwijane, daty i zachowanie zer wiodących. Ponowne uruchomienie zastępuje
wzorzec; kopię z własnymi danymi zapisz pod inną nazwą.

Skoroszyt zawiera dokładnie trzy zakładki:

- `Schemat_Danych`: 21 pól, w tym dodatkowe `status_techniczny`.
- `Szablon_Do_Wypelnienia`: tabela z pięcioma fikcyjnymi przykładami DEMO,
  filtrami, blokadą nagłówka i dwóch kolumn identyfikacyjnych.
- `Instrukcja_Dla_Dysponenta`: zasady wypełniania, eksportu i publikacji.

Walidacja i formaty wejściowe obejmują 10 000 rekordów (wiersze 2–10001).
Tabela początkowo obejmuje pięć przykładów; przy dopisywaniu rozszerz ją
w Excelu. Eksporter odczytuje wszystkie niepuste wiersze, niezależnie od zakresu
tabeli. Import/wklejanie może ominąć walidację Excela, dlatego przed publikacją
uruchom eksport z kontrolą danych.

## Eksport danych

Po zastąpieniu przykładów DEMO i zapisaniu uzupełnionej kopii:

```powershell
.\.venv\Scripts\python.exe data_standard\generuj_wzorzec_aed.py --eksport data_standard\moje_aed.xlsx --katalog-wyjscia data_standard\eksport
```

Powstaną `aed.csv` (UTF-8, przecinek, CRLF, RFC 4180) i `aed.json`
(UTF-8, tablica obiektów, liczby dla współrzędnych, `null` dla braków).
Nagłówki pozostają identyczne, daty mają zapis ISO `YYYY-MM-DD`, a kody TERYT
i pocztowe są tekstem. Eksport przerywa się przy brakach wymaganych danych,
niepoprawnych typach, duplikatach ID lub sprzecznej dostępności.

Szczegóły i źródła: [docs/standard_danych_aed.md](docs/standard_danych_aed.md).

## API i pipeline

Backend uruchamia ogólnopolską migawkę: rzeczywisty cache OSM i zasoby dane.gov.pl:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m unittest backend.test_pipeline backend.test_danegov -v
```

Interfejs webowy działa pod `http://127.0.0.1:8000/` z tego samego serwera.
Instrukcja i testy frontendu: [frontend/README.md](frontend/README.md).

Pobieranie danych, eksporty, endpointy, licencje i konfiguracja adresów publikacji:
[backend/README.md](backend/README.md).

W bocznym panelu, w sekcji **Otwarte dane dane.gov.pl**, są znalezione zbiory, stan
integracji, liczniki deduplikacji i przycisk synchronizacji. Aktualny raport:
`GET /api/sources/stats`. Dane.gov.pl: 21 rekordów Krosna (3624), 21 Przemyśla
(4581), 7 poprawnych lokalizacji Marek (4955). Warszawa (39512) jest znaleziona,
lecz wskazany przez portal adres zwraca HTML. Szczegóły i ograniczenia publikacji:
[docs/integracja_danegov.md](docs/integracja_danegov.md).

Rozbudowa interfejsu gov.pl, asystent RKO/AED, TOP 3 otwartych punktów,
importer BIP, paszporty QR, zgłoszenia terenowe i audyt jakości:
[docs/funkcje_ratunkowe.md](docs/funkcje_ratunkowe.md).
