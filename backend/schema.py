"""Definicje pól i słowników odczytywane z autorytatywnego wzorca XLSX."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from openpyxl import load_workbook

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "data_standard" / "wzorzec_danych_aed.xlsx"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    dtype: str
    required: bool


@lru_cache(maxsize=1)
def load_schema():
    workbook = load_workbook(SCHEMA_PATH, read_only=False, data_only=True)
    try:
        fields = tuple(FieldSpec(row[0], row[1], row[2], row[3] == "TAK")
                       for row in workbook["Schemat_Danych"].iter_rows(min_row=6, max_col=6, values_only=True)
                       if row[0])
        headers = tuple(c.value for c in workbook["Szablon_Do_Wypelnienia"][1])
        if tuple(f.name for f in fields) != headers:
            raise ValueError("Schemat_Danych i nagłówki szablonu są niespójne.")
        enums = {}
        for dv in workbook["Szablon_Do_Wypelnienia"].data_validations.dataValidation:
            if dv.type == "list":
                column = next(iter(dv.sqref.ranges)).min_col
                enums[headers[column - 1]] = tuple(dv.formula1.strip('"').split(","))
        return fields, enums
    finally:
        workbook.close()


def field_names():
    return [f.name for f in load_schema()[0]]
