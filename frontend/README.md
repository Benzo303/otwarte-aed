# Otwarte AED — prosty ekran i panel pomocy

HTML5, lokalny CSS, Vanilla JS i Leaflet 1.9.4 + markercluster 1.5.3.
Bez bundlera, CDN i kluczy API w czasie działania. Prototyp jest oznaczony jako
nieoficjalny mimo inspiracji stylistyką gov.pl.

Nagłówek ma własny logotyp kampanii, zgodny z `branding/logo_otwarte_aed.svg`.
Kopia `frontend/assets/logo_otwarte_aed.svg` jest identyczna bajtowo; plik
`logo_otwarte_aed_kontrast.svg` jest zatwierdzonym wariantem dostępności.

## Uruchomienie

Windows: `START_AED.cmd` w katalogu głównym. Zatrzymanie: `STOP_AED.cmd`.
Skrypty startują z bieżącego położenia folderu i korzystają z `.venv`.
Adres: [http://127.0.0.1:8000/](http://127.0.0.1:8000/).
Nie otwieraj samego `index.html` przez `file://` — aplikacja wymaga API FastAPI.

## Ekran dla świadka zdarzenia

Nagłówek z numerem 112, asystent dwóch pytań, jedno pole miejscowości/ulicy
i mapa z krótką listą. Domyślnie wszystkie źródła i tylko urządzenia otwarte,
bez wymogu klucza. Na ekranie i prostej karcie AED nie ma wskaźników jakości,
surowych harmonogramów ani nazw formatów technicznych.

Po wyszukaniu tekstowym lub GPS pojawiają się najwyżej trzy karty otwartych AED:
miejsce w budynku, szacowany marsz, nawigacja piesza, głos i szczegóły.
Czas dla wpisanej lokalizacji dotyczy punktu wskazanego przez geokoder;
nie oznacza wykrycia pozycji użytkownika. Bez numeru budynku jest to punkt
orientacyjny na ulicy. Nawigacja Google Maps może ustalić własny punkt startu.

Wyszukiwanie tekstu odbywa się dopiero po zatwierdzeniu, bez autouzupełniania.
Backend korzysta z cache i geokodera OSM, ogranicza kraj do Polski i współdzieli
limit około jednego żądania/s z wyszukiwaniem granic/importerem.
Niejednoznaczne nazwy wymagają dopisania miejscowości/numeru, a błąd sieci
nie jest przedstawiany jako brak AED. GPS wymaga HTTPS/localhost i zgody.

Klastry korzystają z lokalnego `vendor/leaflet.markercluster.js` i `MarkerCluster.css`:
promień 55 px, wyłączenie od zoomu 15, porcje ładowania, rozsuwanie punktów,
trzy rozmiary liczników. Równoległe zmiany filtrów kończą się ostatnim wyborem.
Pochodzenie i licencja: `vendor/MARKERCLUSTER-SOURCE.txt`.

## Boczna szufladka

Uchwyt: „Pomoc, RKO i narzędzia ☰”.

- Desktop: szerokość ≥900 px, `hover:hover` i `pointer:fine`; pointerenter 120 ms,
  pointerleave 350 ms. Przejście z uchwytu do panelu nie zamyka go.
  Przypięcie utrzymuje panel otwarty. Fokus wewnątrz również chroni wpisywanie.
- Telefon/tablet/małe okno: hover jest ignorowany. Kliknięcie otwiera panel
  z tłem, blokadą przewijania i `inert` na treści głównej. Fokus pozostaje
  w panelu. Zamknięcie uchwytem, przyciskiem, tłem lub Escape oddaje fokus.
- Hover nie przenosi fokusu. Jawne otwarcie klawiaturą przenosi go do panelu.
  Zmiana typu urządzenia/szerokości aktualizuje tryb i tło.
- Najwyżej dwie z pięciu sekcji są otwarte. RKO domyślnie otwarte.

Sekcje: ściąga w pięciu punktach z metronomem 110/min i lektorem; dostępność;
filtry i ręczne współrzędne/mapa; strefa urzędu z walidatorem, BIP i QR;
otwarte dane z synchronizacją, rankingiem i eksportami. Zamknięcie panelu lub
sekcji pomocy zatrzymuje metronom. Lektor `pl-PL` zależy od głosów systemu.

## Paszport i wydruk

Skrót **Wygeneruj kod QR / tabliczkę AED** jest u góry szufladki.
Bezpośredni link: `http://127.0.0.1:8000/#qr`. Generator jest pierwszym narzędziem
w strefie dysponenta; po wybraniu AED automatycznie wpisuje jego identyfikator i nazwę.

Python `qrcode` tworzy SVG z odnośnikiem `/?aed=ID`. Link otwiera prostą kartę
również dla zamkniętego urządzenia. Trzy zgłoszenia to Działa/Zamknięte/Uszkodzone;
backend zapisuje je w SQLite. Dane eksperckie wybranego AED są w strefie urzędu.
Generator wymaga istniejącego ID. Przed drukiem ustaw osiągalny publiczny adres,
ponieważ localhost odnosi się do telefonu skanującego. Druk obejmuje samą tabliczkę.

## Dostępność i ograniczenia

Tekst główny 18 px, przyciski ≥48 px, fokus 3 px, kontrast czarno-żółty
około 17,37:1, powiększenie 100/120/135%, ARIA i ograniczenie animacji.
Marker pane zachowuje `aria-hidden`; lista udostępnia równoważne działania.
Kafelki mapy wymagają sieci; lista działa bez nich/Leafleta.
Pełna zgodność AAA wymaga audytu z czytnikami i na urządzeniach; implementacja
i test DOM nie są certyfikacją. Automatyzacja prawdziwej przeglądarki była w tej
sesji niedostępna. Metronom/audio/GPS są w testach symulowane.

## Testy

```powershell
node --test frontend/tests/core.test.js
cd frontend
npm install --ignore-scripts
npm run test:ui
```

Warianty DOM: dotyk, desktop hover/przypięcie, link QR i klastry. Sprawdzają
fokus, tło, opóźnienia, ignorowanie dotyku przez hover, dwa otwarte akordeony,
asystenta, Escape, metronom, głos, wyszukiwanie, raporty, QR/druk i narzędzia urzędu.
LinkeDOM jest wyłącznie zależnością testową; uruchomienie aplikacji nie wymaga npm.

Backend i zasady ratunkowe: [funkcje_ratunkowe.md](../docs/funkcje_ratunkowe.md).
Źródła wskazówek: [ERC 2025](https://www.erc.edu/media/wrhj5sye/gl2025-04-bls-e.pdf).
Instrukcje dotyczą osoby dorosłej, po braku reakcji od razu wskazują 112,
uwzględniają oddech agonalny i wyjątek urazu dla pozycji bocznej.
