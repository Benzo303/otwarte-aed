"""Kontrola XLSX/CSV dysponenta; walidacja nie zmienia publicznego rejestru."""
import csv
import io
from collections import Counter
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from xml.etree.ElementTree import ParseError

from lxml.etree import XMLSyntaxError

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .harvester_export import csv_text
from .normalizer import attach_source, canonical_values, deduplicate, validate_record
from .schema import field_names

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10000


def read_upload(payload: bytes, filename: str):
    if not payload or len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("Plik musi mieć od 1 bajta do 5 MiB.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV musi używać UTF-8.") from exc
        try:
            dialect = csv.Sniffer().sniff(text[:16384], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(text, newline=""), dialect, strict=True)
        rows = []
        try:
            header = next(reader, [])
            for row_number, values in enumerate(reader, 2):
                if not any(v.strip() for v in values):
                    continue
                if len(rows) >= MAX_ROWS:
                    raise ValueError("Maksymalnie 10 000 rekordów w uploadzie.")
                rows.append((row_number, values, []))
        except csv.Error as exc:
            raise ValueError(f"Niepoprawna składnia CSV: {exc}") from exc
        return header, rows
    if suffix != ".xlsx":
        raise ValueError("Obsługiwane pliki: .xlsx i .csv.")
    try:
        with ZipFile(io.BytesIO(payload)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 64 * 1024 * 1024:
                raise ValueError("Zbyt duży rozpakowany skoroszyt (limit 64 MiB).")
        wb = load_workbook(io.BytesIO(payload), read_only=True, data_only=False, keep_links=False)
    except (BadZipFile, KeyError, OSError, ParseError, XMLSyntaxError, InvalidFileException) as exc:
        raise ValueError("Niepoprawny plik XLSX.") from exc
    try:
        if "Szablon_Do_Wypelnienia" not in wb.sheetnames:
            raise ValueError("Brak zakładki Szablon_Do_Wypelnienia.")
        sheet = wb["Szablon_Do_Wypelnienia"]
        if sheet.max_column > 100 or sheet.max_row > 10001:
            raise ValueError("Przekroczony zakres skoroszytu (10 000 rekordów, maksymalnie 100 kolumn).")
        iterator = sheet.iter_rows()
        header = [c.value for c in next(iterator, [])]
        rows = []
        for number, cells in enumerate(iterator, 2):
            values = [c.value for c in cells]
            if all(v is None or (isinstance(v, str) and not v.strip()) for v in values):
                continue
            formulas = [header[i] for i, c in enumerate(cells) if c.data_type == "f"]
            rows.append((number, values, formulas))
        return header, rows
    except (ParseError, XMLSyntaxError, InvalidFileException) as exc:
        raise ValueError("Uszkodzona struktura XML skoroszytu XLSX.") from exc
    finally:
        wb.close()


def validate_upload(payload, filename):
    header, rows = read_upload(payload, filename)
    header = [h.strip() if isinstance(h, str) else h for h in header]
    expected = field_names()
    header_errors = []
    for key in expected:
        if key not in header:
            header_errors.append({"row": 1, "field": key, "code": "missing_column", "message": "Brak kolumny wzorca."})
    if len(header) != len(set(header)):
        header_errors.append({"row": 1, "field": None, "code": "duplicate_column", "message": "Powtórzona nazwa kolumny."})
    for key in header:
        if key not in expected:
            header_errors.append({"row": 1, "field": str(key), "code": "unknown_column", "message": "Kolumna spoza wzorca."})
    if header_errors:
        return {"valid": False, "rows_total": len(rows), "rows_valid": 0, "rows_invalid": len(rows),
                "errors": header_errors, "warnings": [], "normalized_json": [], "normalized_csv": csv_text([], extensions=False)}
    prepared = [(number, canonical_values(dict(zip(header, values))), values, formulas) for number, values, formulas in rows]
    counts = Counter(row.get("id_aed") for _, row, _, _ in prepared if isinstance(row.get("id_aed"), str))
    errors, valid = [], []
    warnings = []
    for number, row, values, formulas in prepared:
        issues = validate_record(row)
        if len(values) != len(header):
            issues.append({"field": None, "code": "column_count", "message": "Liczba komórek nie zgadza się z nagłówkiem."})
        issues.extend({"field": field, "code": "formula", "message": "Zastąp formułę wartością."} for field in formulas)
        if isinstance(row.get("id_aed"), str) and counts[row["id_aed"]] > 1:
            issues.append({"field": "id_aed", "code": "duplicate_id", "message": "ID powtarza się w uploadzie."})
        errors.extend({"row": number, **issue} for issue in issues)
        if not issues:
            demo = row["id_aed"].startswith("DEMO-")
            valid.append(attach_source(row, "Upload dysponenta", row["zrodlo_referencyjne"], demo=demo))
            if demo:
                warnings.append({"row": number, "code": "demo", "message": "Rekord DEMO. Zastąp przed publikacją."})
    normalized = deduplicate(valid)
    if not rows:
        errors.append({"row": 2, "field": None, "code": "empty", "message": "Plik nie zawiera rekordów."})
    return {"valid": not errors, "rows_total": len(rows), "rows_valid": len(valid), "rows_invalid": len(rows) - len(valid),
            "output_records": len(normalized), "errors": errors, "warnings": warnings,
            "normalized_json": normalized, "normalized_csv": csv_text(normalized)}
