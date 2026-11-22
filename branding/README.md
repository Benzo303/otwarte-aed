# Otwarte AED — pakiet marki 2.0

Nazwa: **Otwarte AED**. Hasło: **Dane, które ratują minuty.**
Zachowano autorski model znaku z sercem, EKG, pinezką i otwartym węzłem danych.
Ta sama wersja podstawowa znajduje się na stronie, w księdze i prezentacji.

## Pliki

- `logo_otwarte_aed.svg`: podstawowy wektor z hasłem, litery na krzywych.
- `logo_otwarte_aed.png`: 2800 × 800 px, przezroczyste tło.
- `logo_otwarte_aed.jpg`: 2800 × 800 px, białe tło.
- `logo_otwarte_aed.pdf`: wektor do druku/składu.
- `sygnet_otwarte_aed.svg`: mała ikona bez tekstu, używana także jako favicon.
- Warianty `monochromatyczne`, `negatyw` i `kontrast`: zatwierdzone odmiany.
- `ksiega_znaku.pdf`: 6 stron A4; koncepcja ma dokładnie 4 zdania.
- `manifest_marki.json`: suma SHA-256 podstawowego SVG i ścieżka jego kopii na stronie.

Kolory: #D92638 i #0F2C59, biel #FFFFFF, jasne tło #F2F5FA, szaroniebieski #5C6B82.
Księga podaje HEX/RGB/CMYK, moduł u=H/5, minima 280 px/70 mm dla pełnego znaku
i 32 px/8 mm dla sygnetu oraz cztery wizualne antyprzykłady.
CMYK jest przeliczeniem sRGB bez ICC; druk wymaga dobrania profilu i próby.

## Regeneracja i edycja

```powershell
.\.venv\Scripts\python.exe branding\generuj_ksiege_znaku.py
.\.venv\Scripts\python.exe docs\generuj_prezentacje_otwarte_aed.py
```

Model i krzywe źródłowe są w `brand_assets.py`; plik SVG można też otworzyć
w edytorze wektorowym. Generator pakietu odtwarza SVG z modelu, więc trwałe
zmiany należy zapisać w modelu przed regeneracją.
Księgę składa ReportLab z osadzonym Arial, a SVG osadza svglib jako wektor.
PNG/JPG powstają z tego samego PDF przez pypdfium2/Pillow. Biblioteki są
w `.venv`; nie wymagają instalowania Cairo/Inkscape/LibreOffice w systemie.
Lokalne fonty Arial są odczytywane z Windows; ich pliki nie są dołączane do pakietu.
Alternatywę TTF wskazują `AED_FONT_REGULAR` i `AED_FONT_BOLD`.

Prezentacja ma 6 slajdów i 5 dużych, oznaczonych miejsc na zrzuty prototypu.
Teksty i diagram są edytowalne. Zrzuty dodaje się ręcznie lub plikami z instrukcji
`docs/zrzuty_ekranu/INSTRUKCJA.md`; generator wstawia istniejące PNG automatycznie.
Bez tych pięciu obrazów prezentacja pozostaje robocza i nie spełnia jeszcze
warunku dowodów ekranowych z opisu konkursu.

Zespół powinien przed zgłoszeniem sprawdzić treść, uzupełnić zrzuty i zatwierdzić
autorskie elementy. Użyte biblioteki i źródła danych zachowują własne licencje.
