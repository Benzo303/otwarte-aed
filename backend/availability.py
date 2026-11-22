"""Interpretacja harmonogramów OSM w Polsce, także święta, DST i godziny nocne."""
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from opening_hours import OpeningHours, ParserError

WARSAW = ZoneInfo("Europe/Warsaw")


@lru_cache(maxsize=4096)
def parse_hours(expression: str, lat=None, lon=None):
    kwargs = {"timezone": WARSAW, "country": "PL"}
    if lat is not None and lon is not None:
        kwargs["coords"] = (lat, lon)
    return OpeningHours(expression, **kwargs)


def valid_hours(expression):
    if not isinstance(expression, str) or not expression.strip():
        return False
    try:
        parse_hours(expression)
        return True
    except (ValueError, SyntaxError, ParserError):
        return False


def availability_now(record: dict, now: datetime | None = None) -> dict:
    """True wymaga jawnego dostępu bez klucza; niewiedza to null, nie False."""
    now = now or datetime.now(WARSAW)
    if now.tzinfo is None:
        raise ValueError("Czas kontroli musi zawierać strefę czasową.")
    if record.get("field_access_alert") in ("closed", "damaged"):
        return {"otwarte_teraz": False, "powod_dostepnosci": "zgloszenie_terenowe_" + record["field_access_alert"]}
    if record.get("status_techniczny") == "serwis" or record.get("dostepnosc_typ") == "niedostepny":
        return {"otwarte_teraz": False, "powod_dostepnosci": "niedostepny_lub_serwis"}
    critical = {"dostepnosc_typ", "godziny_otwarcia_osm", "wymagany_klucz_lub_kod", "status_techniczny"}
    if set(record.get("conflicts", {})) & critical:
        return {"otwarte_teraz": None, "powod_dostepnosci": "sprzeczne_informacje_o_dostepie"}
    if record.get("dostepnosc_typ") == "na_klucz_lub_kod" or record.get("wymagany_klucz_lub_kod") == "TAK":
        return {"otwarte_teraz": False, "powod_dostepnosci": "wymagany_klucz_lub_kod"}
    if record.get("dostepnosc_typ") not in ("24_7", "godziny_pracy") or record.get("wymagany_klucz_lub_kod") != "NIE":
        return {"otwarte_teraz": None, "powod_dostepnosci": "brak_potwierdzenia_dostepu"}
    expression = record.get("godziny_otwarcia_osm")
    if not expression:
        return {"otwarte_teraz": None, "powod_dostepnosci": "brak_harmonogramu"}
    try:
        hours = parse_hours(expression, record.get("lat"), record.get("lon"))
        if hours.is_unknown(now):
            return {"otwarte_teraz": None, "powod_dostepnosci": "nieokreslony_harmonogram"}
        return {"otwarte_teraz": hours.is_open(now), "powod_dostepnosci": "harmonogram"}
    except (ValueError, SyntaxError, ParserError):
        return {"otwarte_teraz": None, "powod_dostepnosci": "niepoprawny_harmonogram"}
