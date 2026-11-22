"""Wzorzec Otwarte AED 0.1. Uruchamiaj przez .venv/Scripts/python.exe.

Bez argumentów tworzy XLSX obok skryptu. Opcja --eksport odczytuje wypełniony
skoroszyt i zapisuje CSV/JSON. Biblioteki: openpyxl oraz standardowa biblioteka.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter


VERSION = "0.1"
DEFAULT_OUTPUT = Path(__file__).resolve().with_name("wzorzec_danych_aed.xlsx")
MAX_ROW = 10001  # 10 000 rekordów objętych walidacją.
AS_OF = date(2026, 11, 21)  # Stała data przykładowych, syntetycznych rekordów.
SHEETS = ["Schemat_Danych", "Szablon_Do_Wypelnienia", "Instrukcja_Dla_Dysponenta"]
ACCESS = ("24_7", "godziny_pracy", "na_klucz_lub_kod", "niedostepny")
TECHNICAL = ("sprawny", "serwis", "niezweryfikowany")
DISABILITY = ("tak", "nie", "niezweryfikowano")
STANDARD_URL = "https://dane.gov.pl/media/ckeditor/2019/01/23/standard-techniczny_22-11-2018.pdf"
OVERVIEW_URL = "https://www.gov.pl/web/ia/standardy-otwartosci-danych"
OSM_URL = "https://wiki.openstreetmap.org/wiki/Key:opening_hours"
TERYT_URL = "https://eteryt.stat.gov.pl/"

NAVY = "17324D"
BLUE = "245C87"
INK = "223449"
LIGHT = "EFF4F8"
MUTED = "53677C"
AMBER = "FFF2CC"
RED = "FCE4E4"
RED_TEXT = "9C2424"


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    dtype: str
    required: bool
    description: str
    validation: str
    width: int


FIELDS = [
    Field("id_aed", "Identyfikator AED", "tekst", True,
          "Stały identyfikator urządzenia, niezależny od adresu. Przykład: DEMO-WAW-001.",
          "Unikalny w zbiorze; 3–100 znaków [A-Za-z0-9_.:-]. Prefiks dysponenta zapobiega kolizjom między źródłami.", 23),
    Field("nazwa_obiektu", "Nazwa obiektu", "tekst", True,
          "Nazwa budynku lub miejsca z AED. Przykład: Centrum Sąsiedzkie Północ (DEMO).",
          "1–200 znaków. Użyj nazwy rozpoznawalnej dla osoby szukającej urządzenia.", 37),
    Field("ulica_numer", "Ulica i numer", "tekst", True,
          "Adres wejścia do obiektu. Przykład: ul. Przykładowa 12A. Przy braku ulicy: nazwa miejscowości i numer.",
          "1–200 znaków. Numer budynku zachowaj razem z ewentualną literą.", 30),
    Field("kod_pocztowy", "Kod pocztowy", "tekst", True,
          "Polski kod pocztowy. Przykład: 00-001.",
          "Dokładnie NN-NNN; wyrażenie ^[0-9]{2}-[0-9]{3}$. Komórka tekstowa.", 21),
    Field("miejscowosc", "Miejscowość", "tekst", True,
          "Nazwa miejscowości. Przykład: Warszawa.",
          "1–100 znaków. Zgodność nazwy z adresem oraz kodem TERYT sprawdź w rejestrze GUS.", 22),
    Field("kod_teryt", "Kod gminy TERYT (TERC)", "tekst (7 cyfr)", True,
          "Kod TERC gminy, łącznie z rodzajem gminy, a nie kod SIMC miejscowości. Przykład: 0264011 (Wrocław).",
          "^[0-9]{7}$; zachowaj zero na początku. Istnienie i zgodność kodu z lokalizacją sprawdź w aktualnym TERYT.", 24),
    Field("lat", "Szerokość geograficzna", "liczba dziesiętna", True,
          "WGS84 / EPSG:4326, stopnie dziesiętne. Pozycja AED lub wejścia umożliwiającego jego odnalezienie. Przykład: 52.229700.",
          "Liczba od -90 do 90. Zalecane 6 miejsc po przecinku. Przy eksporcie separator dziesiętny: kropka.", 25),
    Field("lon", "Długość geograficzna", "liczba dziesiętna", True,
          "WGS84 / EPSG:4326, stopnie dziesiętne. Przykład: 21.012200. Nie zamieniaj kolejności lat / lon.",
          "Liczba od -180 do 180. Zalecane 6 miejsc po przecinku. Sprawdź punkt na mapie.", 25),
    Field("opis_lokalizacji_wewnatrz", "Dokładna lokalizacja i dojście", "tekst", True,
          "Droga od wejścia do AED, piętro, bariery i sposób uzyskania dostępu. Dla AED na zewnątrz opisz elewację. Przykład: parter, po prawej od recepcji.",
          "1–1000 znaków. Dla na_klucz_lub_kod opisz, gdzie uzyskać klucz lub pomoc. Dla niedostepny podaj powód. Nie wpisuj poufnego kodu.", 52),
    Field("dostepnosc_typ", "Dostępność dla osoby z zewnątrz", "tekst (słownik)", True,
          "Rzeczywisty dostęp do AED: 24_7; godziny_pracy; na_klucz_lub_kod; niedostepny. Otwarcie budynku nie oznacza dostępu do AED.",
          "Wyłącznie wartość z listy. 24_7: bez klucza i ograniczeń przez całą dobę. na_klucz_lub_kod ma pierwszeństwo przed godzinami.", 30),
    Field("godziny_otwarcia_osm", "Harmonogram dostępu do AED", "tekst (OSM opening_hours)", True,
          "Godziny faktycznego uzyskania AED w strefie Europe/Warsaw. Przykłady: 24/7; Mo-Fr 08:00-16:00; PH off.",
          "Wymagane dla godziny_pracy i na_klucz_lub_kod. Dla 24_7: dokładnie 24/7. Dla niedostepny: off. Składnię OSM sprawdź narzędziem opening_hours.", 44),
    Field("wymagany_klucz_lub_kod", "Czy dostęp wymaga klucza lub kodu", "tekst (TAK/NIE)", True,
          "Informacja o barierze dostępu, bez publikowania samego kodu. Przykład: TAK.",
          "TAK lub NIE. TAK dla na_klucz_lub_kod; NIE dla 24_7 i godziny_pracy. Dla niedostepny zapisz stan faktyczny.", 32),
    Field("dostepnosc_niepelnosprawni", "Dostępność dla osoby z ograniczoną mobilnością", "tekst (słownik)", True,
          "Dostęp od wejścia do AED bez schodów i innych barier. Przykład: tak. Pole nie jest pełnym audytem dostępności obiektu.",
          "tak, nie lub niezweryfikowano. Nie zastępuj braku wiedzy wartością nie. Bariery opisz w lokalizacji.", 35),
    Field("model_aed", "Producent i model AED", "tekst", False,
          "Model odczytany z urządzenia lub dokumentacji. Przykład: Philips HeartStart HS1.",
          "Do 150 znaków. Brak danych oznacz pustą komórką.", 33),
    Field("status_techniczny", "Status techniczny AED", "tekst (słownik)", True,
          "Stan niezależny od dostępności miejsca. Przykład: sprawny. Zamknięty obiekt może zawierać sprawny AED.",
          "sprawny, serwis lub niezweryfikowany. serwis wymaga dostepnosc_typ=niedostepny. Niezweryfikowany nie oznacza potwierdzonej sprawności.", 26),
    Field("data_waznosci_elektrod", "Ważność elektrod", "data (YYYY-MM-DD)", False,
          "Termin ważności aktualnie zamontowanych elektrod. Przykład: 2027-06-30.",
          "Poprawna data kalendarzowa lub pusto. Data przeszła jest dozwolona i wyróżniana; wymaga weryfikacji stanu. Nie używaj dat zastępczych.", 29),
    Field("data_waznosci_baterii", "Ważność baterii", "data (YYYY-MM-DD)", False,
          "Termin ważności baterii według dokumentacji dysponenta. Przykład: 2028-09-30.",
          "Poprawna data kalendarzowa lub pusto. Data przeszła jest dozwolona i wyróżniana; wymaga weryfikacji stanu.", 28),
    Field("data_aktualizacji", "Data weryfikacji rekordu", "data (YYYY-MM-DD)", True,
          "Data ostatniego potwierdzenia informacji przez dysponenta; nie data pobrania pliku. Przykład: 2026-11-21.",
          "Poprawna data kalendarzowa, nie późniejsza niż dzień kontroli. Aktualizuj po każdej potwierdzonej zmianie.", 26),
    Field("dysponent_nazwa", "Nazwa dysponenta", "tekst", True,
          "Organizacja odpowiedzialna za AED i aktualizację rekordu. Przykład: Centrum Sąsiedzkie Północ (DEMO).",
          "1–200 znaków. Stosuj jedną, spójną nazwę organizacji.", 38),
    Field("dysponent_kontakt", "Publiczny kontakt do dysponenta", "tekst (e-mail lub telefon)", True,
          "Kontakt instytucjonalny do korekt danych. Przykład: aed.warszawa@example.org.",
          "E-mail lub numer w formacie E.164 (np. +48 i 9 cyfr). Kontakt służy aktualizacji danych, nie jest deklaracją całodobowego dostępu.", 39),
    Field("zrodlo_referencyjne", "Źródło referencyjne rekordu", "tekst (URL lub identyfikator źródła)", True,
          "Trwały URL lub etykieta dane.gov.pl [ID: 3624 - Urząd Miasta Krosna]. Po integracji wiele źródeł oddziela ' | '; szczegóły i URL są w sources.",
          "URL http/https lub dane.gov.pl [ID: numer - instytucja]. Źródła oddzielaj ' | '. Zweryfikuj aktualność i prawa u źródła.", 58),
]
HEADERS = [f.key for f in FIELDS]
COLUMN = {key: get_column_letter(i + 1) for i, key in enumerate(HEADERS)}
DATE_FIELDS = {f.key for f in FIELDS if f.dtype.startswith("data ")}
ENUMS = {"dostepnosc_typ": ACCESS, "wymagany_klucz_lub_kod": ("TAK", "NIE"),
         "dostepnosc_niepelnosprawni": DISABILITY, "status_techniczny": TECHNICAL}


def examples() -> list[dict]:
    """Syntetyczne obiekty i adresy: nie są rejestrem rzeczywistych AED."""
    rows = [
        ["DEMO-WAW-001", "Centrum Sąsiedzkie Północ (DEMO)", "ul. Przykładowa 12", "00-001", "Warszawa", "1465011", 52.229700, 21.012200,
         "Szafka na zewnętrznej elewacji przy wejściu głównym; dojście z chodnika bez schodów.",
         "24_7", "24/7", "NIE", "tak", "Philips HeartStart HS1", "sprawny", date(2027, 6, 30), date(2028, 9, 30), AS_OF,
         "Centrum Sąsiedzkie Północ (DEMO)", "aed.warszawa@example.org", "https://example.org/aed/DEMO-WAW-001"],
        ["DEMO-KRK-002", "Biblioteka Osiedlowa Czytelnia (DEMO)", "ul. Testowa 8", "30-001", "Kraków", "1261011", 50.061400, 19.936600,
         "Parter, hol po lewej od recepcji. Wejście z podjazdem. AED dostępny tylko podczas otwarcia biblioteki.",
         "godziny_pracy", "Mo-Fr 08:00-18:00; Sa 09:00-13:00; PH off", "NIE", "tak", "ZOLL AED Plus", "sprawny", date(2027, 3, 31), date(2029, 1, 31), AS_OF,
         "Biblioteka Osiedlowa Czytelnia (DEMO)", "aed.krakow@example.org", "https://example.org/aed/DEMO-KRK-002"],
        ["DEMO-POZ-003", "Hala Sportowa Zachód (DEMO)", "ul. Pokazowa 21", "60-001", "Poznań", "3064011", 52.406400, 16.925200,
         "Hol przy portierni; klucz do szafki wydaje dyżurny w portierni w podanych godzinach. Wejście boczne z trzema stopniami.",
         "na_klucz_lub_kod", "Mo-Su 06:00-22:00; PH off", "TAK", "nie", "Defibtech Lifeline AED", "sprawny", date(2027, 11, 30), date(2028, 5, 31), AS_OF,
         "Hala Sportowa Zachód (DEMO)", "aed.poznan@example.org", "https://example.org/aed/DEMO-POZ-003"],
        ["DEMO-WRO-004", "Dom Kultury Nad Rzeką (DEMO)", "ul. Modelowa 5", "50-001", "Wrocław", "0264011", 51.107900, 17.038500,
         "AED z holu przekazano do serwisu. Urządzenie obecnie niedostępne. Trwa wymiana elektrod.",
         "niedostepny", "off", "NIE", "niezweryfikowano", "CU Medical i-PAD SP1", "serwis", date(2026, 10, 31), date(2027, 8, 31), AS_OF,
         "Dom Kultury Nad Rzeką (DEMO)", "aed.wroclaw@example.org", "https://example.org/aed/DEMO-WRO-004"],
        ["DEMO-GDA-005", "Biurowiec Przystań (DEMO)", "ul. Demonstracyjna 3", "80-001", "Gdańsk", "2261011", 54.352000, 18.646600,
         "Szafka przy recepcji na parterze; otwiera ją ochrona po zgłoszeniu przez domofon przy wejściu. Dyżur ochrony całodobowy. Stan techniczny czeka na potwierdzenie.",
         "na_klucz_lub_kod", "24/7", "TAK", "tak", None, "niezweryfikowany", None, None, AS_OF,
         "Biurowiec Przystań (DEMO)", "aed.gdansk@example.org", "https://example.org/aed/DEMO-GDA-005"],
    ]
    if any(len(row) != len(HEADERS) for row in rows):
        raise ValueError("Liczba wartości przykładu nie odpowiada schematowi.")
    return [dict(zip(HEADERS, row)) for row in rows]


def setup_sheet(ws, tab_color=BLUE):
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.sheet_properties.tabColor = tab_color
    ws.sheet_view.zoomScale = 85
    ws.sheet_properties.outlinePr.summaryRight = False
    ws.print_options.horizontalCentered = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.oddFooter.center.text = "Otwarte AED 0.1"
    ws.oddFooter.right.text = "Strona &P / &N"


def style_table(ws, ref, name, header_row):
    table = Table(displayName=name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True,
                                        showFirstColumn=False, showLastColumn=False)
    ws.add_table(table)
    for row in ws[ref]:
        for cell in row:
            cell.font = Font(name="Arial", size=11, color=INK)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for cell in ws[header_row]:
        cell.font = Font(name="Arial", size=11, color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(right=Side(style="thin", color="FFFFFF"))


def add_validation(ws, key, dv, prompt):
    dv.errorTitle = "Sprawdź wartość"
    dv.error = "Wpisz wartość zgodną ze schematem i komunikatem wejściowym."
    dv.promptTitle = next(f.label for f in FIELDS if f.key == key)[:32]
    dv.prompt = prompt[:255]
    dv.errorStyle = "stop"
    dv.showErrorMessage = True
    dv.showInputMessage = True
    dv.showDropDown = False  # W OOXML True ukrywa strzałkę listy.
    ws.add_data_validation(dv)
    col = COLUMN[key]
    dv.add(f"{col}2:{col}{MAX_ROW}")


def build_schema(ws):
    setup_sheet(ws, NAVY)
    ws["A2"] = "Otwarte AED — schemat danych"
    ws["A2"].font = Font(name="Arial", size=16, bold=True, color=NAVY)
    ws["A3"] = "Profil projektu 0.1"
    ws["A3"].font = Font(name="Arial", size=11, color=MUTED)
    ws["E3"] = "21 pól. TAK = zawsze wymagane; NIE = opcjonalne lub wymagane warunkowo (patrz walidacja)."
    ws["E3"].font = Font(name="Arial", size=11, color=MUTED, italic=True)
    ws["E3"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 27
    ws.row_dimensions[3].height = 34
    ws.append([])  # Wiersz 4 oddziela tytuł od tabeli.
    headers = ["Nazwa pola techniczna (snake_case)", "Nazwa czytelna", "Typ danych", "Wymagalność TAK/NIE", "Opis i przykład", "Walidacja"]
    for i, value in enumerate(headers, 1):
        ws.cell(5, i, value)
    for row, field in enumerate(FIELDS, 6):
        values = [field.key, field.label, field.dtype, "TAK" if field.required else "NIE", field.description, field.validation]
        for col, value in enumerate(values, 1):
            ws.cell(row, col, value)
        ws.row_dimensions[row].height = 50
    for col, width in zip("ABCDEF", [35, 32, 26, 20, 72, 86]):
        ws.column_dimensions[col].width = width
    ws.row_dimensions[5].height = 42
    style_table(ws, f"A5:F{5 + len(FIELDS)}", "SchematAED", 5)
    for row in range(6, 6 + len(FIELDS)):
        ws.cell(row, 4).alignment = Alignment(horizontal="center", vertical="center")
        if ws.cell(row, 4).value == "TAK":
            ws.cell(row, 4).font = Font(name="Arial", size=11, bold=True, color=NAVY)
    ws.freeze_panes = "C6"
    ws.print_title_rows = "1:5"
    ws.print_area = f"A1:F{5 + len(FIELDS)}"


def build_template(ws):
    setup_sheet(ws)
    ws.append(HEADERS)  # Eksport maszynowy: nagłówki w pierwszym wierszu.
    for record in examples():
        ws.append([record[key] for key in HEADERS])
    last_col = get_column_letter(len(FIELDS))
    style_table(ws, f"A1:{last_col}6", "RejestrAED", 1)
    ws.row_dimensions[1].height = 56
    for row in range(2, 7):
        ws.row_dimensions[row].height = 66
    for field in FIELDS:
        col = COLUMN[field.key]
        ws.column_dimensions[col].width = max(field.width, len(field.key) + 3)
        # Format obejmuje także przyszłe wpisy objęte walidacją.
        number_format = "yyyy-mm-dd" if field.key in DATE_FIELDS else "0.000000" if field.key in ("lat", "lon") else "@"
        for row in range(2, MAX_ROW + 1):
            ws.cell(row, HEADERS.index(field.key) + 1).number_format = number_format
        if field.key in ("lat", "lon") or field.key in DATE_FIELDS:
            for row in range(2, 7):
                ws[f"{col}{row}"].alignment = Alignment(horizontal="right", vertical="top")

    for key, options in ENUMS.items():
        add_validation(ws, key, DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=False),
                       "Wybierz: " + ", ".join(options))
    for key, low, high in [("lat", -90, 90), ("lon", -180, 180)]:
        add_validation(ws, key, DataValidation(type="decimal", operator="between", formula1=low, formula2=high, allow_blank=False),
                       f"WGS84, stopnie dziesiętne; zakres {low} do {high}. W eksporcie liczba z kropką.")
    for key in DATE_FIELDS:
        upper = "TODAY()" if key == "data_aktualizacji" else "DATE(9999,12,31)"
        add_validation(ws, key, DataValidation(type="date", operator="between", formula1="DATE(1900,1,1)", formula2=upper,
                                             allow_blank=key != "data_aktualizacji"), "Wpisz datę kalendarzową, np. 2027-06-30. Wyświetlany format: YYYY-MM-DD.")
    # Kody sprawdzamy jako tekst, aby nie utracić zer wiodących.
    for key in ("kod_pocztowy", "kod_teryt"):
        c = COLUMN[key] + "2"
        formula = (f'AND(ISTEXT({c}),LEN({c})=6,MID({c},3,1)="-",ISNUMBER(--LEFT({c},2)),ISNUMBER(--RIGHT({c},3)))'
                   if key == "kod_pocztowy" else f'AND(ISTEXT({c}),LEN({c})=7,IFERROR(TEXT(--{c},"0000000")={c},FALSE))')
        add_validation(ws, key, DataValidation(type="custom", formula1=formula, allow_blank=False),
                       "Kod pocztowy NN-NNN; TERYT: dokładnie 7 cyfr jako tekst, z zerami wiodącymi.")

    # Kolor wskazuje konkretne problemy, a nie deklarację bezpieczeństwa AED.
    def flag(ref, formula, color=RED):
        ws.conditional_formatting.add(ref, FormulaRule(formula=[formula], fill=PatternFill("solid", fgColor=color),
                                                       font=Font(name="Arial", color=RED_TEXT)))

    for key in ("dostepnosc_typ", "status_techniczny"):
        col = COLUMN[key]
        bad = "niedostepny" if key == "dostepnosc_typ" else "serwis"
        flag(f"{col}2:{col}{MAX_ROW}", f'{col}2="{bad}"')
    flag(f"O2:O{MAX_ROW}", 'O2="niezweryfikowany"', AMBER)
    for key in ("data_waznosci_elektrod", "data_waznosci_baterii"):
        col = COLUMN[key]
        flag(f"{col}2:{col}{MAX_ROW}", f'AND(ISNUMBER({col}2),{col}2<TODAY())', AMBER)
    flag(f"A2:A{MAX_ROW}", f'AND($A2<>"",COUNTIF($A$2:$A${MAX_ROW},$A2)>1)')
    for field in FIELDS:
        if field.required:
            col = COLUMN[field.key]
            flag(f"{col}2:{col}{MAX_ROW}", f'AND(COUNTA($A2:${last_col}2)>0,{col}2="")', AMBER)
    flag(f"J2:L{MAX_ROW}", 'AND($A2<>"",OR(AND($J2="24_7",OR($K2<>"24/7",$L2<>"NIE")),AND($J2="na_klucz_lub_kod",OR($K2="",$L2<>"TAK")),AND($J2="godziny_pracy",OR($K2="",$L2<>"NIE")),AND($J2="niedostepny",$K2<>"off"),AND($O2="serwis",$J2<>"niedostepny")))')
    ws.freeze_panes = "C2"
    ws.print_title_rows = "1:1"
    # 21 szerokich kolumn nie należy ściskać na jedną kartkę.
    ws.page_setup.fitToWidth = 0
    ws.page_setup.scale = 85
    ws.print_area = f"A1:{last_col}6"


def build_instructions(ws):
    setup_sheet(ws, MUTED)
    ws.sheet_view.zoomScale = 90
    ws.column_dimensions["A"].width = 29
    ws.column_dimensions["B"].width = 118
    ws["A2"] = "Otwarte AED — instrukcja dla dysponenta"
    ws["A2"].font = Font(name="Arial", size=16, bold=True, color=NAVY)
    ws.row_dimensions[2].height = 28
    steps = [
        ("Zakres i przykłady", "Wersja 0.1 to profil projektu Otwarte AED, nie urzędowy schemat AED. Pięć rekordów DEMO jest fikcyjnych: obiekty, adresy, współrzędne, kontakty i źródła nie potwierdzają lokalizacji urządzeń. Zastąp je przed publikacją."),
        ("1. Wypełnij rekord", "W zakładce Szablon_Do_Wypelnienia jeden wiersz opisuje jedno urządzenie. Zachowaj nazwy kolumn i trwałe id_aed. TAK w schemacie oznacza pole obowiązkowe; wymagania warunkowe są w kolumnie Walidacja. Puste pole opcjonalne oznacza brak danych."),
        ("2. Sprawdź lokalizację", "Kod pocztowy i 7-cyfrowy kod TERC gminy wpisuj jako tekst. Zachowaj zera wiodące. Zweryfikuj TERYT w GUS. Współrzędne lat, lon podawaj w WGS84; sprawdź punkt na mapie. Opisz wejście, piętro, szafkę i bariery."),
        ("3. Określ dostęp", "24_7 oznacza dostęp bez klucza całą dobę; harmonogram: 24/7. Przy godzinach użyj godziny_pracy. Gdy wymagany jest klucz lub kod, wybierz na_klucz_lub_kod, ustaw TAK i opisz sposób uzyskania pomocy. Dla niedostepny wpisz off i powód."),
        ("4. Zapisz godziny OSM", "Harmonogram dotyczy uzyskania AED, nie samego otwarcia budynku. Przykład: Mo-Fr 08:00-16:00; PH off. Strefa: Europe/Warsaw. Dla dostępu na klucz wpisz godziny dostępności osoby wydającej klucz. Zweryfikuj składnię w narzędziu opening_hours."),
        ("5. Potwierdź stan", "Status techniczny wybierz osobno. serwis wymaga niedostepny. niezweryfikowany oznacza brak potwierdzenia sprawności. Daty wpisuj jako daty kalendarzowe YYYY-MM-DD. Nieznane terminy pozostaw puste. data_aktualizacji to dzień potwierdzenia informacji przez dysponenta."),
        ("6. Odczytaj oznaczenia", "Listy rozwijane blokują wartości spoza słowników. Bursztynowy kolor wskazuje brak wymaganego pola, przeszły termin lub stan niezweryfikowany. Czerwony oznacza niedostępność, serwis, duplikat ID lub sprzeczne dane. Walidacja i formaty obejmują wiersze 2–10001; wklejanie może ominąć walidację Excela."),
        ("7. Eksport CSV", "Eksportuj wyłącznie zakładkę danych: pierwszy wiersz to nazwy pól, dalej tylko rekordy, bez tytułów i pustych wierszy. Użyj UTF-8, przecinka, reguł cytowania RFC 4180, kropki dziesiętnej i dat YYYY-MM-DD. Puste pola pozostają puste. Sprawdź separator po eksporcie z lokalnego Excela."),
        ("8. Eksport JSON", "Zapisz UTF-8 i tablicę obiektów z tymi samymi kluczami. lat/lon: liczby; kody i identyfikatory: tekst; daty: tekst YYYY-MM-DD; brak wartości: null. Słowniki, w tym TAK/NIE, pozostają tekstem. Excel nie ma standardowego eksportu JSON; użyj dołączonego skryptu."),
        ("Eksport skryptem", "W głównym katalogu projektu uruchom w PowerShell:\n.\\.venv\\Scripts\\python.exe data_standard\\generuj_wzorzec_aed.py --eksport data_standard\\wzorzec_danych_aed.xlsx --katalog-wyjscia data_standard\\eksport\nSkrypt sprawdzi rekordy i utworzy aed.csv oraz aed.json. Przed eksportem zastąp przykłady DEMO."),
        ("9. Publikacja i aktualizacja", "Przed publikacją sprawdź rekordy ze źródłem i usuń DEMO. Uzupełnij w portalu metadane zbioru i zasobu: tytuł, opis, dysponenta, warunki ponownego wykorzystania, datę i częstotliwość aktualizacji. Arkusz nie publikuje danych automatycznie. Po zmianie dostępności niezwłocznie popraw rekord."),
        ("Kontrola poza Excelem", "Eksporter sprawdza typy, wymagane pola, słowniki, duplikaty ID i spójność dostępności. Nie sprawdza istnienia AED, aktualnego TERYT, zgodności punktu z adresem, działania URL ani pełnej składni OSM. Te elementy potwierdź u dysponenta i w odpowiednich rejestrach."),
        ("Źródło: standard techniczny", STANDARD_URL),
        ("Źródło: opis standardów", OVERVIEW_URL),
        ("Źródło: godziny OSM", OSM_URL),
        ("Źródło: rejestr TERYT", TERYT_URL),
    ]
    ws["A4"], ws["B4"] = "Krok / zagadnienie", "Co zrobić"
    for row, (title, detail) in enumerate(steps, 5):
        ws.cell(row, 1, title)
        ws.cell(row, 2, detail)
        ws.row_dimensions[row].height = 50 if row < 17 else 26
    style_table(ws, f"A4:B{4 + len(steps)}", "InstrukcjaAED", 4)
    ws.row_dimensions[4].height = 29
    ws.row_dimensions[14].height = 78
    for row in range(5, 5 + len(steps)):
        ws.cell(row, 1).font = Font(name="Arial", size=11, color=NAVY, bold=True)
        cell = ws.cell(row, 2)
        if str(cell.value).startswith("https://"):
            cell.hyperlink = cell.value
            cell.font = Font(name="Arial", size=11, color=BLUE, underline="single")
    ws.print_title_rows = "1:4"
    ws.print_area = f"A1:B{4 + len(steps)}"


def normalized_record(values, row_number, today):
    record = dict(zip(HEADERS, values))
    errors = []
    for field in FIELDS:
        value = record[field.key]
        if isinstance(value, str):
            value = value.strip() or None
            record[field.key] = value
        if value is None:
            if field.required:
                errors.append(f"{field.key}: pole wymagane")
            continue
        if field.key in DATE_FIELDS:
            if isinstance(value, datetime):
                if value.time() != datetime.min.time():
                    errors.append(f"{field.key}: data nie może zawierać godziny")
                value = value.date()
            elif isinstance(value, str):
                try:
                    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                        raise ValueError
                    value = date.fromisoformat(value)
                except ValueError:
                    errors.append(f"{field.key}: oczekiwano daty YYYY-MM-DD")
                    continue
            if not isinstance(value, date):
                errors.append(f"{field.key}: oczekiwano daty")
                continue
            if value < date(1900, 1, 1):
                errors.append(f"{field.key}: data sprzed 1900-01-01")
            if field.key == "data_aktualizacji" and value > today:
                errors.append(f"{field.key}: data z przyszłości")
            record[field.key] = value.isoformat()
        elif field.key in ("lat", "lon"):
            bound = 90 if field.key == "lat" else 180
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -bound <= value <= bound:
                errors.append(f"{field.key}: wymagana liczba od {-bound} do {bound}")
        elif not isinstance(value, str):
            errors.append(f"{field.key}: wymagany tekst (zachowaj zera wiodące)")
        elif field.key in ENUMS and value not in ENUMS[field.key]:
            errors.append(f"{field.key}: wartość spoza słownika")
        elif len(value) > {"id_aed": 100, "nazwa_obiektu": 200, "ulica_numer": 200,
                            "miejscowosc": 100, "opis_lokalizacji_wewnatrz": 1000,
                            "model_aed": 150, "dysponent_nazwa": 200}.get(field.key, 2000):
            errors.append(f"{field.key}: przekroczona długość tekstu")
    patterns = {"id_aed": r"[A-Za-z0-9_.:-]{3,100}", "kod_pocztowy": r"[0-9]{2}-[0-9]{3}", "kod_teryt": r"[0-9]{7}"}
    for key, pattern in patterns.items():
        value = record[key]
        if value is not None and (not isinstance(value, str) or not re.fullmatch(pattern, value)):
            errors.append(f"{key}: niepoprawny format")
    contact = record["dysponent_kontakt"]
    if isinstance(contact, str) and not (re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact) or re.fullmatch(r"\+[1-9][0-9]{7,14}", contact)):
        errors.append("dysponent_kontakt: oczekiwano e-mail lub telefonu E.164")
    url = record["zrodlo_referencyjne"]
    if isinstance(url, str):
        try:
            for part in url.split(" | "):
                if re.fullmatch(r"dane\.gov\.pl \[ID: [0-9]+ - [^\[\]\r\n]+\]", part):
                    continue
                parsed = urlparse(part)
                if parsed.scheme not in ("http", "https") or not parsed.netloc or any(c.isspace() for c in part):
                    raise ValueError
        except ValueError:
            errors.append("zrodlo_referencyjne: wymagany URL http/https lub dane.gov.pl [ID: numer - instytucja]")
    access, hours, key = (record[k] for k in ("dostepnosc_typ", "godziny_otwarcia_osm", "wymagany_klucz_lub_kod"))
    if access == "24_7" and (hours != "24/7" or key != "NIE"):
        errors.append("24_7 wymaga godzin 24/7 i klucza NIE")
    if access in ("godziny_pracy", "na_klucz_lub_kod"):
        if not hours or hours == "off":
            errors.append("ograniczony dostęp wymaga harmonogramu dostępu")
        if key != ("TAK" if access == "na_klucz_lub_kod" else "NIE"):
            errors.append("typ dostępności nie zgadza się z wymaganiem klucza")
    if access == "niedostepny" and hours != "off":
        errors.append("niedostepny wymaga harmonogramu off")
    if record["status_techniczny"] == "serwis" and access != "niedostepny":
        errors.append("serwis wymaga dostępności niedostepny")
    if errors:
        raise ValueError(f"Wiersz {row_number}: " + "; ".join(errors))
    return record


def read_records(path, today=None):
    today = today or date.today()
    wb = load_workbook(path, read_only=True, data_only=False)
    try:
        ws = wb[SHEETS[1]]
        rows = ws.iter_rows()
        header = [cell.value for cell in next(rows)]
        if header != HEADERS:
            raise ValueError("Nagłówki lub kolejność kolumn nie odpowiadają schematowi Otwarte AED 0.1.")
        records, seen = [], set()
        for row_number, cells in enumerate(rows, 2):
            values = [cell.value for cell in cells]
            if all(v is None or (isinstance(v, str) and not v.strip()) for v in values):
                continue
            if any(cell.data_type == "f" for cell in cells):
                raise ValueError(f"Wiersz {row_number}: zastąp formuły wartościami przed eksportem.")
            record = normalized_record(values, row_number, today)
            if record["id_aed"] in seen:
                raise ValueError(f"Wiersz {row_number}: powtórzone id_aed {record['id_aed']}.")
            seen.add(record["id_aed"])
            records.append(record)
        if not records:
            raise ValueError("Arkusz nie zawiera żadnych rekordów.")
        return records
    finally:
        wb.close()


def verify_saved(path):
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Uszkodzone archiwum XLSX.")
    wb = load_workbook(path)
    try:
        if wb.sheetnames != SHEETS:
            raise ValueError("Nieprawidłowa lista zakładek.")
        ws = wb[SHEETS[1]]
        if ws.tables["RejestrAED"].ref != "A1:U6" or ws.freeze_panes != "C2":
            raise ValueError("Niepoprawny zakres tabeli lub blokada okienek.")
        for key, choices in ENUMS.items():
            expected_range = f"{COLUMN[key]}2:{COLUMN[key]}{MAX_ROW}"
            found = [dv for dv in ws.data_validations.dataValidation if dv.type == "list" and str(dv.sqref) == expected_range]
            if len(found) != 1 or found[0].formula1 != '"' + ",".join(choices) + '"' or found[0].showDropDown:
                raise ValueError(f"Brak widocznej listy rozwijanej: {key}.")
        if ws["F5"].value != "0264011" or ws["F5"].number_format != "@":
            raise ValueError("Utracono zero wiodące TERYT.")
        if not isinstance(ws["P2"].value, datetime) or ws["P2"].number_format != "yyyy-mm-dd":
            raise ValueError("Niepoprawny typ lub format daty.")
        if wb[SHEETS[0]].tables["SchematAED"].ref != "A5:F26":
            raise ValueError("Schemat nie obejmuje wszystkich 21 pól.")
        # Porównanie wszystkich zapisanych wartości z definicją generatora.
        for cells, expected in zip(ws.iter_rows(min_row=2, max_row=6, max_col=len(FIELDS)), examples()):
            actual = normalized_record([c.value for c in cells], cells[0].row, AS_OF)
            original = normalized_record([expected[k] for k in HEADERS], cells[0].row, AS_OF)
            if actual != original:
                raise ValueError("Odczyt XLSX różni się od danych generatora.")
    finally:
        wb.close()
    if len(read_records(path, today=AS_OF)) != 5:
        raise ValueError("Brak pięciu rekordów przykładowych.")


def generate(path):
    wb = Workbook()
    wb.remove(wb.active)
    for name in SHEETS:
        wb.create_sheet(name)
    wb.properties.creator = "Otwarte AED"
    wb.properties.title = "Otwarte AED — wzorzec danych 0.1"
    wb.properties.subject = "Integracja rozproszonych danych AED dla dane.gov.pl"
    wb.properties.description = "Profil projektu. Pięć rekordów DEMO jest fikcyjnych."
    build_schema(wb[SHEETS[0]])
    build_template(wb[SHEETS[1]])
    build_instructions(wb[SHEETS[2]])
    wb.active = 1
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    wb.close()
    verify_saved(path)
    print(f"OK: {path.resolve()} ({path.stat().st_size:,} bajtów)")
    print("Zweryfikowano: 3 zakładki, 21 pól, 5 rekordów, listy rozwijane, daty i zera wiodące.")


def export(path, output_dir):
    records = read_records(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = output_dir / "aed.csv", output_dir / "aed.json"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS, dialect="excel", lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(records)
    with json_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(records, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(f"OK: {len(records)} rekordów -> {csv_path.resolve()} oraz {json_path.resolve()}")
    if any(r["id_aed"].startswith("DEMO-") for r in records):
        print("UWAGA: eksport zawiera fikcyjne rekordy DEMO. Zastąp je przed publikacją.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plik-wyjsciowy", type=Path, default=DEFAULT_OUTPUT, help="Ścieżka generowanego XLSX.")
    parser.add_argument("--eksport", type=Path, metavar="XLSX", help="Eksport wypełnionego arkusza do CSV i JSON zamiast generowania wzorca.")
    parser.add_argument("--katalog-wyjscia", type=Path, default=DEFAULT_OUTPUT.parent / "eksport")
    args = parser.parse_args()
    try:
        if args.eksport:
            export(args.eksport, args.katalog_wyjscia)
        else:
            generate(args.plik_wyjsciowy)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"BŁĄD: {exc}\n")


if __name__ == "__main__":
    main()
