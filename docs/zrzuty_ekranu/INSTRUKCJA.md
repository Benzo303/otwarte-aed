# Zrzuty do prezentacji

Prezentacja korzysta z pięciu rzeczywistych zrzutów zapisanych w tym katalogu.
Można je podmienić na nowsze. Jeśli któregoś pliku brakuje, generator wstawi
w jego miejsce oznaczoną ramkę do uzupełnienia.

Zapisz obrazy PNG w tym katalogu (najlepiej okno 1600 × 900 lub większe):

1. `01_zrodla.png`: Pomoc → Otwarte dane dane.gov.pl → wykaz źródeł i statystyki.
2. `02_wzorzec.png`: plik `data_standard/wzorzec_danych_aed.xlsx`, zakładka Schemat_Danych.
3. `03_mapa.png`: wpisz Koszalin, pokaż TOP 3 otwartych urządzeń i fragment mapy.
4. `04_dysponent_qr.png`: otwórz `http://127.0.0.1:8000/#qr`, wybierz istniejący AED
   i wygeneruj tabliczkę; alternatywnie pokaż raport walidacji w strefie dysponenta.
5. `05_eksport.png`: Pomoc → Otwarte dane → podgląd JSON lub XML harvestera.

Następnie otwórz PowerShell w głównym folderze rozpakowanego projektu.
Środowisko `.venv` przygotowuje `START_AED.cmd`; po jego utworzeniu wykonaj:

```powershell
.\.venv\Scripts\python.exe docs\generuj_prezentacje_otwarte_aed.py
```

Generator podmieni odpowiadające ramki, zachowując proporcje obrazów, i zapisze
PPTX oraz PDF. Można też wstawić obrazy ręcznie w PowerPoint; teksty i ramki są edytowalne.
Pięć uzupełnionych zrzutów jest warunkiem spełnienia tej części wymagań konkursu.
