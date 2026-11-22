# Profil danych Otwarte AED 0.1

To profil projektu hackathonowego. Nie jest urzędowym schematem AED ani
potwierdzeniem przyjęcia zbioru przez portal. Zasady publikacji CSV/JSON oparto
na [Standardzie technicznym otwartości danych](https://dane.gov.pl/media/ckeditor/2019/01/23/standard-techniczny_22-11-2018.pdf)
i [opisie standardów na gov.pl](https://www.gov.pl/web/ia/standardy-otwartosci-danych).
Źródła sprawdzono 2026-11-21.

## Zasady integracji

Jedno urządzenie ma jeden rekord i trwałe `id_aed`. Zalecany prefiks dysponenta
ogranicza kolizje identyfikatorów przy scalaniu źródeł. Zmiana adresu nie zmienia
identyfikatora. Różnych urządzeń pod jednym adresem nie należy automatycznie
scalać. `zrodlo_referencyjne` wskazuje URL rekordu lub etykietę
`dane.gov.pl [ID: numer - instytucja]`; wiele źródeł oddziela separator ` | `.
Rozszerzenie `sources` zachowuje dokładne URL, ID datasetu/zasobu i licencje, a
`data_aktualizacji` oznacza ostatnie potwierdzenie danych przez dysponenta.

`kod_teryt` oznacza 7-cyfrowy kod TERC gminy wraz z rodzajem jednostki, nie SIMC.
Zero wiodące jest częścią identyfikatora. Przynależność do gminy trzeba sprawdzić
w aktualnym [rejestrze TERYT GUS](https://eteryt.stat.gov.pl/).
Współrzędne są w WGS84 / EPSG:4326, w stopniach dziesiętnych: `lat`, następnie `lon`.

## Dostępność

| dostepnosc_typ | Harmonogram | wymagany_klucz_lub_kod |
| --- | --- | --- |
| `24_7` | `24/7` | `NIE` |
| `godziny_pracy` | godziny faktycznego dostępu do AED | `NIE` |
| `na_klucz_lub_kod` | godziny uzyskania klucza lub pomocy | `TAK` |
| `niedostepny` | `off` | stan faktyczny: `TAK` albo `NIE` |

Klucz lub kod ma pierwszeństwo przed godzinami: ochrona dyżurująca całą dobę
nie zmienia zamkniętej szafki w swobodny dostęp `24_7`. Sposób uzyskania klucza
lub pomocy należy opisać w `opis_lokalizacji_wewnatrz`. W tym samym polu podaje
się powód niedostępności. Nie publikuje się poufnych kodów.

`godziny_otwarcia_osm` korzysta ze [składni OSM opening_hours](https://wiki.openstreetmap.org/wiki/Key:opening_hours),
np. `Mo-Fr 08:00-16:00; PH off`. Harmonogram interpretuje się w strefie
`Europe/Warsaw`. Dostępność dla osoby z ograniczoną mobilnością przyjmuje
`tak`, `nie` lub `niezweryfikowano`.

`status_techniczny` jest osobnym wymiarem: `sprawny`, `serwis`,
`niezweryfikowany`. Urządzenie w serwisie ma dostępność `niedostepny`.
Sprawny AED może być zamknięty w budynku. Niezweryfikowany stan wymaga
potwierdzenia przez dysponenta; nie należy traktować go jak potwierdzonej sprawności.

## Wartości i eksport

W XLSX daty są rzeczywistymi datami z formatem `yyyy-mm-dd`, a współrzędne
liczbami z wyświetlaniem sześciu miejsc po przecinku. Identyfikatory oraz kody
pozostają tekstem. Brak wartości opcjonalnej oznacza pustą komórkę.

CSV zawiera jeden wiersz nagłówków i dane, kodowanie UTF-8, separator przecinek,
cytowanie znaków specjalnych zgodnie z RFC 4180 i końce wierszy CRLF. W JSON
powstaje tablica obiektów z identycznymi kluczami. Daty mają postać `YYYY-MM-DD`,
braki to `null`, współrzędne to liczby, a wszystkie słowniki pozostają tekstem.
Ten profil nie deklaruje poziomu 4/5 otwartości ani semantyki JSON-LD.

Przy publikacji należy uzupełnić metadane zbioru i zasobu, wskazać warunki
ponownego wykorzystania oraz utrzymywać aktualność danych. Arkusz i eksporter
przygotowują pliki lokalne, nie publikują ich na portalu.

## Zakres kontroli

Eksporter sprawdza wymagane wartości, typy, słowniki, format kodów, zakresy
współrzędnych, poprawność dat, unikalność ID i zależności między dostępnością,
kluczem, harmonogramem i serwisem. Formuły w rekordach wymagają zamiany na wartości.

Kontrola formatu nie potwierdza istnienia AED, adresu, dostępności w terenie,
zgodności współrzędnych z gminą, istnienia URL ani aktualnego kodu w rejestrze
TERYT. Pełną składnię godzin OSM należy sprawdzić narzędziem opening_hours.
Takie potwierdzenia pozostają po stronie dysponenta lub przyszłego procesu integracji.

Pięć przykładów `DEMO-*` jest syntetycznych. Nazwy, adresy i punkty nie wskazują
zweryfikowanych lokalizacji AED; kontakty i źródła używają domeny `example.org`.
Przed publikacją trzeba zastąpić je rzeczywistymi, potwierdzonymi danymi.
