"""Lettura e compilazione dei file di pagamento dipendenti XLS/XLSX."""

import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

EXCEL_CODE_COLUMN = 8  # H
ADVANCE_COLUMN = 13  # M
NET_PAY_COLUMN = 14  # N
EURO_NUMBER_FORMAT = '€ #,##0.00'


class PaymentFileError(ValueError):
    """Il file di pagamento non puo' essere letto o aggiornato."""


def _extension(filename):
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        return ".xlsx"
    if name.endswith(".xls"):
        return ".xls"
    raise PaymentFileError("Il file deve essere in formato XLS o XLSX.")


def workbook_sheet_names(content, filename):
    extension = _extension(filename)
    try:
        if extension == ".xlsx":
            from openpyxl import load_workbook
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
            names = workbook.sheetnames
            workbook.close()
            return names
        import xlrd
        return xlrd.open_workbook(file_contents=content, on_demand=True).sheet_names()
    except Exception as exc:
        raise PaymentFileError("Impossibile leggere i fogli del file Excel.") from exc


def _employee_code(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    code = str(value).strip()
    return code[:-2] if code.endswith(".0") and code[:-2].isdigit() else code


def _has_value(value):
    return value is not None and value != ""


def payment_file_has_existing_values(content, filename, sheet_name, known_codes):
    """Controlla M/N solo per Badge ID H realmente presenti in Horilla."""
    extension = _extension(filename)
    try:
        if extension == ".xlsx":
            from openpyxl import load_workbook
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
            if sheet_name not in workbook.sheetnames:
                raise PaymentFileError("Il foglio selezionato non e' presente nel file.")
            sheet = workbook[sheet_name]
            found = any(
                _employee_code(sheet.cell(row=row, column=EXCEL_CODE_COLUMN).value) in known_codes
                and (_has_value(sheet.cell(row=row, column=ADVANCE_COLUMN).value)
                     or _has_value(sheet.cell(row=row, column=NET_PAY_COLUMN).value))
                for row in range(1, sheet.max_row + 1)
            )
            workbook.close()
            return found
        import xlrd
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
        if sheet_name not in workbook.sheet_names():
            raise PaymentFileError("Il foglio selezionato non e' presente nel file.")
        sheet = workbook.sheet_by_name(sheet_name)
        return any(
            _employee_code(sheet.cell_value(row, EXCEL_CODE_COLUMN - 1)) in known_codes
            and (_has_value(sheet.cell_value(row, ADVANCE_COLUMN - 1))
                 or _has_value(sheet.cell_value(row, NET_PAY_COLUMN - 1)))
            for row in range(sheet.nrows)
        )
    except PaymentFileError:
        raise
    except Exception as exc:
        raise PaymentFileError("Impossibile controllare le celle gia' compilate.") from exc


def _fill_xlsx(content, sheet_name, values, write_mode):
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill

    workbook = load_workbook(BytesIO(content), data_only=False)
    if sheet_name not in workbook.sheetnames:
        raise PaymentFileError("Il foglio selezionato non e' presente nel file.")
    sheet = workbook[sheet_name]
    filled = missing = 0
    red_fill = PatternFill("solid", fgColor="FFC7CE")
    for row in range(1, sheet.max_row + 1):
        code = _employee_code(sheet.cell(row=row, column=EXCEL_CODE_COLUMN).value)
        if not code:
            continue
        advance_cell = sheet.cell(row=row, column=ADVANCE_COLUMN)
        net_pay_cell = sheet.cell(row=row, column=NET_PAY_COLUMN)
        if code not in values:
            # Formula, commento e valore sono mantenuti; cambia solo il colore.
            advance_cell.fill = red_fill
            net_pay_cell.fill = red_fill
            missing += 1
            continue
        advance, net_pay = values[code]
        row_filled = False
        for cell, value in ((advance_cell, advance), (net_pay_cell, net_pay)):
            if write_mode == "blanks_only" and _has_value(cell.value):
                continue
            # L'assegnazione mantiene bordi, colori e commenti della cella.
            cell.value = value
            cell.number_format = EURO_NUMBER_FORMAT
            row_filled = True
        if row_filled:
            filled += 1
    output = BytesIO()
    workbook.save(output)
    return output.getvalue(), filled, missing


def _soffice_convert(source_path, output_format, output_directory, profile_directory):
    """Converte un XLS senza appiattire le formule in valori statici."""
    try:
        result = subprocess.run(
            ["soffice", "--headless", f"-env:UserInstallation={profile_directory.as_uri()}",
             "--convert-to", output_format, "--outdir", str(output_directory), str(source_path)],
            check=False, capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PaymentFileError("Impossibile avviare la conversione del file XLS.") from exc
    if result.returncode != 0:
        raise PaymentFileError("Impossibile convertire il file XLS senza perdere le formule.")


def _fill_xls(content, sheet_name, values, write_mode):
    """Aggiorna un XLS preservando formule, formattazione e tutti i fogli."""
    with tempfile.TemporaryDirectory(prefix="horilla_xls_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        source_path = temp_dir / "source.xls"
        xlsx_dir, xls_dir = temp_dir / "xlsx", temp_dir / "xls"
        xlsx_dir.mkdir()
        xls_dir.mkdir()
        source_path.write_bytes(content)
        _soffice_convert(source_path, "xlsx", xlsx_dir, temp_dir / "profile_xlsx")
        converted_xlsx = xlsx_dir / "source.xlsx"
        if not converted_xlsx.exists():
            raise PaymentFileError("La conversione del file XLS non ha prodotto un XLSX valido.")
        updated_xlsx, filled, missing = _fill_xlsx(
            converted_xlsx.read_bytes(), sheet_name, values, write_mode
        )
        updated_xlsx_path = temp_dir / "compiled.xlsx"
        updated_xlsx_path.write_bytes(updated_xlsx)
        _soffice_convert(updated_xlsx_path, "xls:MS Excel 97", xls_dir, temp_dir / "profile_xls")
        output_xls = xls_dir / "compiled.xls"
        if not output_xls.exists():
            raise PaymentFileError("La conversione finale in XLS non e' riuscita.")
        return output_xls.read_bytes(), filled, missing


def fill_payment_file(content, filename, sheet_name, values, write_mode="overwrite"):
    """Compila M (acconto) e N (netto), restituendo il formato di input."""
    extension = _extension(filename)
    if write_mode not in {"overwrite", "blanks_only"}:
        raise PaymentFileError("Modalita' di scrittura non valida.")
    return _fill_xlsx(content, sheet_name, values, write_mode) if extension == ".xlsx" else _fill_xls(content, sheet_name, values, write_mode)
