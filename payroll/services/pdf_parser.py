"""
pdf_parser.py
-------------
Adattamento Django del parser buste paga PDF.
Accetta bytes del PDF e restituisce il contenuto TXT come stringa.

Originale: estrai_pdf_in_txt.py
"""

from __future__ import annotations

import calendar
import io
import re
import statistics

import fitz  # pymupdf

A4_WIDTH_PT = 595.2756
A4_HEIGHT_PT = 841.8898
PT_TO_MM = 25.4 / 72.0
TARGET_TOP_PT = 80.0
TARGET_BOTTOM_PT = 390.0
ID_ROW_TOP_PT = 185.0
ID_ROW_BOTTOM_PT = 255.0
VOCI_TOP_PT = 385.0

MONTH_MAP = {
    "GEN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAG": 5, "GIU": 6,
    "LUG": 7, "AGO": 8, "SET": 9, "OTT": 10, "NOV": 11, "DIC": 12,
}

CAUSALE_MARKERS = {"*", "l", "m", "g", "v", "s", "d"}


def _find_spaced_token_end(text: str, token: str) -> int:
    """Ritorna la posizione di fine token tollerando spazi interni tra lettere.

    Esempio: token='CAUSALE' trova sia 'CAUSALE' sia 'CA USALE'.
    Restituisce -1 se non trovato.
    """
    pattern = r"\s*".join(re.escape(ch) for ch in token)
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.end() if m else -1


# ── Utility griglia ────────────────────────────────────────────────────────────

def stima_passo(chars: list[dict]) -> tuple[float, float]:
    larghezze, altezze = [], []
    for ch in chars:
        w = float(ch.get("x1", 0)) - float(ch.get("x0", 0))
        h = float(ch.get("bottom", 0)) - float(ch.get("top", 0))
        if w > 0:
            larghezze.append(w)
        if h > 0:
            altezze.append(h)
    passo_x = statistics.median(larghezze) if larghezze else 4.0
    passo_y = statistics.median(altezze) if altezze else 8.0
    passo_x = min(max(passo_x, 2.0), 8.0)
    passo_y = min(max(passo_y, 4.0), 14.0)
    return passo_x, passo_y


def normalizza_su_a4(x_pt, y_top_pt, page_width, page_height):
    sx = A4_WIDTH_PT / page_width if page_width else 1.0
    sy = A4_HEIGHT_PT / page_height if page_height else 1.0
    return x_pt * sx, y_top_pt * sy


def normalizza_riga_calendario(riga: str) -> str:
    if not riga.strip():
        return riga
    pattern = re.compile(
        r"(?P<mese>[A-Z](?:\s*[A-Z]){2})\s*\.\s*(?P<anno>\d(?:\s*\d){3})\s*$"
    )
    match = pattern.search(riga)
    if not match:
        return riga
    mese = re.sub(r"\s+", "", match.group("mese"))
    anno_txt = re.sub(r"\s+", "", match.group("anno"))
    if mese not in MONTH_MAP or not anno_txt.isdigit():
        return riga
    anno = int(anno_txt)
    ultimo_giorno = calendar.monthrange(anno, MONTH_MAP[mese])[1]
    prefisso = riga[: match.start()]
    numeri_raw = re.findall(r"\d(?:\s*\d)?", prefisso)
    giorni = []
    for n in numeri_raw:
        ns = re.sub(r"\s+", "", n)
        if ns.isdigit():
            giorni.append(int(ns))
    attesi = list(range(1, ultimo_giorno + 1))
    if giorni != attesi:
        giorni = attesi
    giorni_txt = " ".join(str(g) for g in giorni)
    return f"{giorni_txt} {mese}.{anno_txt}"


def estrai_mese_anno(riga: str):
    pattern = re.compile(
        r"(?P<mese>[A-Z](?:\s*[A-Z]){2})\s*\.\s*(?P<anno>\d(?:\s*\d){3})\s*$"
    )
    m = pattern.search(riga)
    if not m:
        return None
    mese = re.sub(r"\s+", "", m.group("mese"))
    anno_txt = re.sub(r"\s+", "", m.group("anno"))
    if mese not in MONTH_MAP or not anno_txt.isdigit():
        return None
    return mese, int(anno_txt)


def estrai_token_mese_anno(righe: list[str]):
    pattern = re.compile(r"([A-Z](?:\s*[A-Z]){2})\s*\.\s*(\d(?:\s*\d){3})")
    for r in righe:
        m = pattern.search(r.upper())
        if not m:
            continue
        mese = re.sub(r"\s+", "", m.group(1))
        anno = re.sub(r"\s+", "", m.group(2))
        if mese in MONTH_MAP and anno.isdigit():
            return f"{mese}.{anno}"
    return None


def allinea_riga_giorni_con_causale(righe, chars, page_width, page_height,
                                     passo_x, passo_y, cols, rows, centro_col, centro_row):
    if not righe or not chars:
        return righe
    row_map: dict[int, list] = {}
    for ch in chars:
        t = (ch.get("text", "") or "")[:1]
        if not t:
            continue
        x_c = (float(ch.get("x0", 0)) + float(ch.get("x1", 0))) / 2.0
        y_c = (float(ch.get("top", 0)) + float(ch.get("bottom", 0))) / 2.0
        x_a4, y_a4 = normalizza_su_a4(x_c, y_c, page_width, page_height)
        x_rel = x_a4 - (A4_WIDTH_PT / 2.0)
        y_rel = (A4_HEIGHT_PT / 2.0) - y_a4
        col = centro_col + int(round(x_rel / passo_x))
        row = centro_row - int(round(y_rel / passo_y))
        if 0 <= row < rows and 0 <= col < cols:
            row_map.setdefault(row, []).append((col, t))

    causale_row = causale_end_col = None
    for row_idx, entries in row_map.items():
        entries_sorted = sorted(entries, key=lambda x: x[0])
        testo = "".join(ch for _, ch in entries_sorted).replace(" ", "").upper()
        if "CAUSALE" in testo:
            causale_row = row_idx
            target = "CAUSALE"
            chars_only = [c.upper() for _, c in entries_sorted]
            cols_only = [c for c, _ in entries_sorted]
            for i in range(len(chars_only) - len(target) + 1):
                if "".join(chars_only[i: i + len(target)]) == target:
                    causale_end_col = cols_only[i + len(target) - 1]
                    break
            if causale_end_col is None and entries_sorted:
                causale_end_col = entries_sorted[0][0]
            break

    if causale_row is None:
        return righe

    entries_causale = sorted(row_map.get(causale_row, []), key=lambda x: x[0])
    marker_cols = sorted({
        col for col, ch in entries_causale
        if ch.lower() in CAUSALE_MARKERS and (causale_end_col is None or col > causale_end_col)
    })
    if not marker_cols:
        return righe

    day_row_idx = causale_row - 1
    if not (0 <= day_row_idx < len(righe)):
        return righe

    mese_anno = estrai_mese_anno(righe[day_row_idx])
    if not mese_anno:
        return righe

    mese, anno = mese_anno
    num_giorni = calendar.monthrange(anno, MONTH_MAP[mese])[1]
    if len(marker_cols) < num_giorni:
        return righe

    nuova = [" " for _ in range(cols)]
    for giorno in range(1, num_giorni + 1):
        start_col = marker_cols[giorno - 1]
        for offset, c in enumerate(str(giorno)):
            if 0 <= start_col + offset < cols:
                nuova[start_col + offset] = c

    mese_txt = f"{mese}.{anno}"
    mese_col = min(cols - len(mese_txt), marker_cols[num_giorni - 1] + 4)
    for offset, c in enumerate(mese_txt):
        if 0 <= mese_col + offset < cols:
            nuova[mese_col + offset] = c

    righe[day_row_idx] = "".join(nuova).rstrip()
    return righe


def normalizza_blocco_sotto_gg(righe: list[str]) -> list[str]:
    idx_gg = None
    for i, r in enumerate(righe):
        up = re.sub(r"\s+", "", r.upper())
        if "GG" in up and "CAUSALE" in up:
            idx_gg = i
            break
    if idx_gg is None:
        return righe

    idx_dl = None
    for i in range(idx_gg + 1, len(righe)):
        up = re.sub(r"\s+", "", righe[i].upper())
        if "D.L" in up or "DL." in up:
            idx_dl = i
            break

    if idx_dl is None or idx_dl <= idx_gg + 1:
        return righe

    def fix_line(line):
        txt = line
        txt = re.sub(r"(?<=\d)\s{1,2}(?=\d)", "", txt)
        txt = re.sub(r"(?<=\d)\s{1,2}(?=[\.,])", "", txt)
        txt = re.sub(r"(?<=[\.,])\s{1,2}(?=\d)", "", txt)

        def fix_dot_token(m):
            digits = m.group(1)
            return f"{digits[0]}.{digits[1:]}" if len(digits) > 1 else f"{digits}."

        txt = re.sub(r"(?<!\d)\.(\d+)(?!\d)", fix_dot_token, txt)
        txt = re.sub(r"(\d\.\d)(\d\.)", r"\1 \2", txt)
        txt = re.sub(r"(\d\.\d)(\d\.\d)", r"\1 \2", txt)
        return txt

    nuove = righe[:]
    for i in range(idx_gg + 1, idx_dl):
        nuove[i] = fix_line(nuove[i])
    return nuove


def forza_31_puntini_allineati(righe, chars, page_width, page_height,
                                passo_x, passo_y, cols, rows, centro_col, centro_row):
    if not righe or not chars:
        return righe

    row_map: dict[int, list] = {}
    for ch in chars:
        t = (ch.get("text", "") or "")[:1]
        if not t:
            continue
        x_c = (float(ch.get("x0", 0)) + float(ch.get("x1", 0))) / 2.0
        y_c = (float(ch.get("top", 0)) + float(ch.get("bottom", 0))) / 2.0
        x_a4, y_a4 = normalizza_su_a4(x_c, y_c, page_width, page_height)
        x_rel = x_a4 - (A4_WIDTH_PT / 2.0)
        y_rel = (A4_HEIGHT_PT / 2.0) - y_a4
        col = centro_col + int(round(x_rel / passo_x))
        row = centro_row - int(round(y_rel / passo_y))
        if 0 <= row < rows and 0 <= col < cols:
            row_map.setdefault(row, []).append((col, t))

    causale_row = causale_end_col = None
    for row_idx, entries in row_map.items():
        entries_sorted = sorted(entries, key=lambda x: x[0])
        testo = "".join(ch for _, ch in entries_sorted).replace(" ", "").upper()
        if "CAUSALE" in testo:
            causale_row = row_idx
            target = "CAUSALE"
            chars_only = [c.upper() for _, c in entries_sorted]
            cols_only = [c for c, _ in entries_sorted]
            for i in range(len(chars_only) - len(target) + 1):
                if "".join(chars_only[i: i + len(target)]) == target:
                    causale_end_col = cols_only[i + len(target) - 1]
                    break
            break

    if causale_row is None:
        return righe

    entries_causale = sorted(row_map.get(causale_row, []), key=lambda x: x[0])
    marker_cols = sorted({
        col for col, ch in entries_causale
        if ch.lower() in CAUSALE_MARKERS and (causale_end_col is None or col > causale_end_col)
    })
    if len(marker_cols) < 31:
        return righe

    gg_row = causale_row
    dl_row = None
    for i, r in enumerate(righe):
        up = re.sub(r"\s+", "", r.upper())
        if "D.L" in up or "DL." in up:
            dl_row = i
            break
    if dl_row is None or dl_row <= gg_row + 1:
        return righe

    day_cols = marker_cols[:31]
    first_day_col = day_cols[0]
    last_day_col = day_cols[-1]

    def cell_bounds(cols_list, idx):
        c = cols_list[idx]
        left = cols_list[idx - 1] if idx > 0 else c - 4
        right = cols_list[idx + 1] if idx < len(cols_list) - 1 else c + 4
        return int((left + c) / 2) + 1, int((c + right) / 2)

    def token_for_day(entries):
        # ritorna (digits_before_dot, digit_after_dot)
        if not entries:
            return "", ""

        seq = []
        for _, ch in sorted(entries, key=lambda x: x[0]):
            if ch.isdigit() or ch in {".", ","}:
                seq.append("." if ch == "," else ch)

        if not seq:
            return "", ""

        if "." in seq:
            dot_pos = seq.index(".")
            before = [c for c in seq[:dot_pos] if c.isdigit()]
            after = [c for c in seq[dot_pos + 1:] if c.isdigit()]
            all_digits = [c for c in seq if c.isdigit()]

            if not before and all_digits:
                before = [all_digits[0]]
                # cifre rimanenti dopo avere forzato la prima cifra prima del punto
                rest = all_digits[1:]
                after = rest[:1]
            else:
                after = after[:1]

            return "".join(before), "".join(after)

        # Nessun punto nel gruppo: trattiamo tutte le cifre come prima del punto
        digits = [c for c in seq if c.isdigit()]
        return "".join(digits), ""

    nuove = righe[:]
    for i in range(gg_row + 1, dl_row):
        base = nuove[i]
        min_len = max(len(base), last_day_col + 2)
        arr = list(base.ljust(min_len))
        row_entries = sorted(row_map.get(i, []), key=lambda x: x[0])

        for c in range(first_day_col, last_day_col + 2):
            if 0 <= c < len(arr):
                arr[c] = " "

        for idx, c in enumerate(day_cols):
            start, end = cell_bounds(day_cols, idx)
            cell_entries = [(col, ch) for col, ch in row_entries if start <= col <= end]
            before_digits, after_digit = token_for_day(cell_entries)

            if 0 <= c < len(arr):
                arr[c] = "."

            if before_digits:
                max_left = c - (day_cols[idx - 1] + 1) if idx > 0 else len(before_digits)
                max_left = max(0, max_left)
                before_use = before_digits[-max_left:] if max_left > 0 else ""
                for off, digit in enumerate(reversed(before_use), start=1):
                    pos = c - off
                    if 0 <= pos < len(arr):
                        arr[pos] = digit

            if after_digit and c + 1 < len(arr):
                if idx == len(day_cols) - 1 or (c + 1) < day_cols[idx + 1]:
                    arr[c + 1] = after_digit[0]

        nuove[i] = "".join(arr).rstrip()
    return nuove


def ricostruisci_testo_griglia(chars, page_width, page_height, solo_essenziale=False):
    if not chars:
        return [""]

    passo_x, passo_y = stima_passo(chars)
    if solo_essenziale:
        passo_y = max(4.0, min(14.0, passo_y * 0.95))
    cols = min(int(A4_WIDTH_PT / passo_x) + 3, 450)
    rows = min(int(A4_HEIGHT_PT / passo_y) + 3, 700)
    centro_col = cols // 2
    centro_row = rows // 2
    canvas = [[" " for _ in range(cols)] for _ in range(rows)]

    def inserisci_char(row, col, ch):
        if not (0 <= row < rows and 0 <= col < cols):
            return
        if canvas[row][col] == " ":
            canvas[row][col] = ch
            return
        if canvas[row][col] == ch:
            return
        deltas = (1, -1) if solo_essenziale else (1, 2, 3, -1, -2)
        for delta in deltas:
            c2 = col + delta
            if 0 <= c2 < cols and canvas[row][c2] == " ":
                canvas[row][c2] = ch
                return

    for ch in chars:
        t = ch.get("text", "")
        if not t:
            continue
        if len(t) != 1:
            t = t[0]
        x_c = (float(ch.get("x0", 0)) + float(ch.get("x1", 0))) / 2.0
        y_c = (float(ch.get("top", 0)) + float(ch.get("bottom", 0))) / 2.0
        x_a4, y_a4 = normalizza_su_a4(x_c, y_c, page_width, page_height)
        x_rel = x_a4 - (A4_WIDTH_PT / 2.0)
        y_rel = (A4_HEIGHT_PT / 2.0) - y_a4
        col = centro_col + int(round(x_rel / passo_x))
        row = centro_row - int(round(y_rel / passo_y))
        inserisci_char(row, col, t)

    righe = ["".join(r).rstrip() for r in canvas]
    righe = [normalizza_riga_calendario(r) for r in righe]
    righe = allinea_riga_giorni_con_causale(
        righe, chars, page_width, page_height,
        passo_x, passo_y, cols, rows, centro_col, centro_row,
    )
    if not solo_essenziale:
        righe = normalizza_blocco_sotto_gg(righe)
    righe = forza_31_puntini_allineati(
        righe, chars, page_width, page_height,
        passo_x, passo_y, cols, rows, centro_col, centro_row,
    )
    while righe and righe[-1] == "":
        righe.pop()
    return righe or [""]


def normalizza_ore_gg_righe(righe: list[str]) -> list[str]:
    if not righe:
        return righe

    causale_hdr_idx = None
    for i, r in enumerate(righe):
        up = re.sub(r"\s+", "", r).upper()
        if "CAUSALE" in up and "ORE" in up and "GG" in up:
            causale_hdr_idx = i
            break
    if causale_hdr_idx is None:
        return righe

    hdr = righe[causale_hdr_idx]

    # Trova la posizione di "ORE" nell'header (tollerando spazi interni)
    ore_match = re.search(r'O\s*R\s*E', hdr)
    if not ore_match:
        return righe
    ore_col = ore_match.start()

    # Trova l'ultimo marker giorno (* l m g v s d) prima di ORE
    last_marker_pos = None
    for i in range(ore_col - 1, -1, -1):
        if hdr[i].lower() in CAUSALE_MARKERS:
            last_marker_pos = i
            break

    # ore_gg_start = subito dopo l'ultimo marker + 1 (spazio per il decimale)
    ore_gg_start = last_marker_pos + 2 if last_marker_pos is not None else ore_col

    _ore_gg_re = re.compile(r'^(\d+\.\d{2})(\d{1,2})?$')

    nuove = righe[:]
    for idx in range(causale_hdr_idx + 1, len(righe)):
        row = nuove[idx]

        # Nome causale: tutto prima della zona giorni
        nome_raw = row[:min(ore_gg_start, len(row))]
        nome = re.sub(r"\s+", "", nome_raw).upper().rstrip("0123456789.")
        if not nome:
            continue

        coda = row[ore_gg_start:].replace(" ", "").strip() if ore_gg_start < len(row) else ""
        if not coda:
            continue

        m = _ore_gg_re.match(coda)
        if m:
            ore_val = m.group(1)
            gg_val = m.group(2) if m.group(2) else ""
        else:
            m2 = re.match(r'^(\d{1,3})(\d{1,2})?$', coda)
            if m2:
                ore_val = m2.group(1)
                gg_val = m2.group(2) if m2.group(2) else ""
            else:
                continue

        parte_fissa = row[:ore_gg_start].rstrip()
        coda_pulita = f"  ORE={ore_val}  GG={gg_val}" if gg_val else f"  ORE={ore_val}"
        nuove[idx] = parte_fissa + coda_pulita

    return nuove


def normalizza_celle_giorni(righe: list[str]) -> list[str]:
    causale_hdr_idx = None
    for i, r in enumerate(righe):
        up = re.sub(r"\s+", "", r.upper())
        if "CAUSALE" in up and "ORE" in up and "GG" in up:
            causale_hdr_idx = i
            break
    if causale_hdr_idx is None:
        return righe

    hdr = righe[causale_hdr_idx]
    ore_pos = hdr.find("ORE")
    if ore_pos == -1:
        return righe

    causale_end = _find_spaced_token_end(hdr, "CAUSALE")
    if causale_end == -1:
        causale_end = 0
    day_start_pos = None
    for i in range(causale_end, ore_pos):
        if i < len(hdr) and hdr[i].lower() in CAUSALE_MARKERS:
            day_start_pos = i
            break
    if day_start_pos is None:
        return righe

    day_cols = []
    for c in range(day_start_pos, ore_pos, 4):
        if c < len(hdr) and hdr[c].lower() in CAUSALE_MARKERS:
            day_cols.append(c)
    if len(day_cols) < 28:
        day_cols = [day_start_pos + i * 4 for i in range(31)]

    nuove = righe[:]
    for idx in range(causale_hdr_idx + 1, len(righe)):
        row = nuove[idx]
        nome_raw = row[:max(0, day_cols[0] - 2)] if day_cols else ""
        nome = re.sub(r"\s+", "", nome_raw).upper().rstrip("0123456789")
        if not nome:
            continue
        arr = list(row.ljust(max(len(row), day_cols[-1] + 2)))
        for dcol in day_cols:
            def gc(pos):
                return arr[pos] if 0 <= pos < len(arr) else " "
            d_tens    = gc(dcol - 2)
            d_units   = gc(dcol - 1)
            d_decimal = gc(dcol + 1)
            before = ""
            if d_tens.isdigit():
                before += d_tens
            if d_units.isdigit():
                before += d_units
            after = d_decimal if d_decimal.isdigit() else "0"
            int_part = int(before) if before else 0
            cell_str = f"{int_part}.{after}".rjust(4)
            for off, ch in enumerate(cell_str):
                pos = dcol - 2 + off
                if 0 <= pos < len(arr):
                    arr[pos] = ch
        nuove[idx] = "".join(arr).rstrip()
    return nuove


def estrai_solo_sezione_giorni(righe: list[str]) -> list[str]:
    if not righe:
        return righe
    idx_causale = None
    for i, r in enumerate(righe):
        up = re.sub(r"\s+", "", r.upper())
        if "CAUSALE" in up and "GG" in up:
            idx_causale = i
            break
    if idx_causale is None:
        return righe
    idx_day = idx_causale - 1 if idx_causale > 0 else idx_causale
    idx_dl = None
    for i in range(idx_causale + 1, len(righe)):
        up = re.sub(r"\s+", "", righe[i].upper())
        if "D.L" in up or "DL." in up:
            idx_dl = i
            break
    if idx_dl is None:
        idx_dl = len(righe)
    sezione = righe[idx_day:idx_dl]
    while sezione and sezione[-1].strip() == "":
        sezione.pop()
    return sezione or [""]


# ── Estrazione dati pagina ──────────────────────────────────────────────────────

def _fitz_page_to_chars(fpage: fitz.Page, clip=None) -> list[dict]:
    td = fpage.get_text("rawdict", clip=clip, flags=0)
    chars = []
    for block in td.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            d = line.get("dir", (1.0, 0.0))
            if abs(d[0]) < 0.9:
                continue
            for span in line.get("spans", []):
                for c in span.get("chars", []):
                    txt = c.get("c", "")
                    if not txt or not txt.strip():
                        continue
                    bbox = c["bbox"]
                    chars.append({
                        "text": txt, "x0": bbox[0], "x1": bbox[2],
                        "top": bbox[1], "bottom": bbox[3], "upright": True,
                    })
    return chars


def _fitz_page_to_words(fpage: fitz.Page, clip=None) -> list[dict]:
    raw = fpage.get_text("words", clip=clip)
    return [
        {"text": w[4], "x0": w[0], "x1": w[2], "top": w[1], "bottom": w[3]}
        for w in raw if w[4].strip()
    ]


def estrai_id_busta_da_pagina(words_id, words_fallback=None):
    words = words_id or []
    if not words and words_fallback:
        words = words_fallback
    if not words:
        return None

    cf_re = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$")
    righe: dict[int, list] = {}
    for w in words:
        y = int(round(float(w.get("top", 0)) / 2.0) * 2)
        righe.setdefault(y, []).append(w)
    for y in righe:
        righe[y].sort(key=lambda item: float(item.get("x0", 0)))

    data_row = None
    for y in sorted(righe.keys()):
        ws = righe[y]
        for w in ws:
            token = re.sub(r"\s+", "", w.get("text", "").upper())
            if cf_re.match(token):
                data_row = ws
                break
        if data_row is not None:
            break

    if data_row is None:
        return None

    def digits_for_x_range(x_min, x_max):
        parts = []
        for w in data_row:
            xc = (float(w.get("x0", 0)) + float(w.get("x1", 0))) / 2.0
            if x_min <= xc <= x_max:
                d = re.sub(r"\D", "", w.get("text", ""))
                if d:
                    parts.append(d)
        return "".join(parts)

    dl_raw = digits_for_x_range(0, 55)
    q_raw = digits_for_x_range(110, 126)
    matr_raw = digits_for_x_range(185, 235)

    dl_val = (dl_raw[-4:] if dl_raw else "").zfill(4)
    q_val = q_raw[0] if q_raw else "0"
    matr_val = (matr_raw[-6:] if matr_raw else "").zfill(6)
    return f"{dl_val}{q_val}{matr_val}"


def estrai_sezione_ferie_fs_rol(words_page: list[dict]) -> dict:
    colonne = ["RESIDUO A.P.", "MATURAZIONE A.C.", "GODUTE A.C.", "RESIDUO"]
    righe_target = ["FERIE", "F.S.", "ROL"]
    result = {r: {c: "0,00" for c in colonne} for r in righe_target}
    words = words_page or []
    if not words:
        return result

    by_y: dict[int, list] = {}
    for w in words:
        y = int(round(float(w.get("top", 0)) / 2.0) * 2)
        by_y.setdefault(y, []).append(w)
    for y in by_y:
        by_y[y].sort(key=lambda ww: float(ww.get("x0", 0)))

    righe_candidate = [y for y in sorted(by_y.keys()) if 280 <= y <= 380]
    if not righe_candidate:
        return result

    def norm(s):
        return re.sub(r"[^A-Z0-9]", "", s.upper())

    for y in righe_candidate:
        ws = by_y[y]
        label = None
        for w in ws:
            x0 = float(w.get("x0", 0))
            if x0 > 80:
                continue
            t = norm(w.get("text", ""))
            if t == "FERIE":
                label = "FERIE"
                break
            if t in {"FS", "FSS"}:
                label = "F.S."
                break
            if t == "ROL":
                label = "ROL"
                break
        if label is None:
            continue

        bins = [(80, 130), (135, 180), (185, 232), (238, 295)]
        valori = [None, None, None, None]
        for w in ws:
            token = w.get("text", "")
            x0 = float(w.get("x0", 0))
            m = re.search(r"-?\d+[\.,]\d+", token)
            if not m:
                continue
            num = m.group(0).replace(".", "").replace(",", ",")
            for idx, (xmin, xmax) in enumerate(bins):
                if xmin <= x0 <= xmax and valori[idx] is None:
                    valori[idx] = num
                    break
        for i, col in enumerate(colonne):
            if valori[i] is not None:
                result[label][col] = valori[i]

    return result


def estrai_filiale(words_page: list[dict]) -> str:
    fil_label = None
    for w in words_page:
        t = re.sub(r"\s+", "", w.get("text", "")).upper()
        x0 = float(w.get("x0", 0))
        y0 = float(w.get("top", 0))
        if t == "FIL." and 40 <= x0 <= 80 and y0 < 220:
            fil_label = w
            break
    if fil_label is None:
        return ""
    lx0 = float(fil_label.get("x0", 0))
    lx1 = float(fil_label.get("x1", 0))
    ly1 = float(fil_label.get("bottom", 0))
    lcx = (lx0 + lx1) / 2.0
    candidati = [
        w for w in words_page
        if float(w.get("top", 0)) > ly1
        and float(w.get("top", 0)) < ly1 + 20
        and abs((float(w.get("x0", 0)) + float(w.get("x1", 0))) / 2.0 - lcx) <= 20
    ]
    candidati.sort(key=lambda w: float(w.get("top", 0)))
    return candidati[0].get("text", "").strip() if candidati else ""


def estrai_netto(words_page: list[dict]) -> str:
    netto_label = None
    for w in words_page:
        t = re.sub(r"\s+", "", w.get("text", "")).upper()
        x0 = float(w.get("x0", 0))
        if t == "NETTO" and x0 > 500:
            netto_label = w
            break
    if netto_label is None:
        return "0,00"
    lx0 = float(netto_label.get("x0", 0))
    lx1 = float(netto_label.get("x1", 0))
    ly1 = float(netto_label.get("bottom", 0))
    lcx = (lx0 + lx1) / 2.0
    candidati = [
        w for w in words_page
        if float(w.get("top", 0)) > ly1
        and float(w.get("top", 0)) < ly1 + 20
        and abs((float(w.get("x0", 0)) + float(w.get("x1", 0))) / 2.0 - lcx) <= 30
        and re.search(r"\d", w.get("text", ""))
    ]
    candidati.sort(key=lambda w: float(w.get("top", 0)))
    return candidati[0].get("text", "").strip() if candidati else "0,00"


def estrai_voci_stipendiali(fpage: fitz.Page) -> list[dict]:
    pw = fpage.rect.width
    ph = fpage.rect.height
    clip_scan = fitz.Rect(0, VOCI_TOP_PT, pw, ph)
    words_scan = _fitz_page_to_words(fpage, clip=clip_scan)

    voci_bottom_pt = ph
    for w in words_scan:
        t = re.sub(r"\s+", "", w.get("text", "")).upper()
        x0 = float(w.get("x0", 0))
        y0 = float(w.get("top", 0))
        if t == "IRPEF" and x0 < 35:
            voci_bottom_pt = min(voci_bottom_pt, y0)
        if t == "IMPONIBILE" and x0 < 80 and y0 > VOCI_TOP_PT + 100:
            voci_bottom_pt = min(voci_bottom_pt, y0)

    clip = fitz.Rect(0, VOCI_TOP_PT, pw, voci_bottom_pt)
    words = _fitz_page_to_words(fpage, clip=clip)
    if not words:
        return []

    by_y: dict[int, list] = {}
    for w in words:
        y = int(round(float(w.get("top", 0)) / 2.0) * 2)
        by_y.setdefault(y, []).append(w)
    for y in by_y:
        by_y[y].sort(key=lambda ww: float(ww.get("x0", 0)))

    header_y = None
    col_positions: dict[str, float] = {}
    _HEADER_MAP = {
        "CODICE": "codice", "DESCRIZIONE": "descr", "ALIQUOTA": "aliq",
        "UNITA": "unit", "VALUNIT": "val", "IMPONIB": "val",
        "COMPETENZE": "comp", "TRATTENUTE": "trat",
    }

    def _norm_kw(s):
        return re.sub(r"[^A-Z0-9]", "", s.upper())

    for y in sorted(by_y.keys()):
        ws = by_y[y]
        row_compact = re.sub(r"\s+", "", " ".join(w.get("text", "") for w in ws).upper())
        if "CODICE" not in row_compact or "DESCRIZIONE" not in row_compact:
            continue
        header_y = y
        for w in ws:
            t = _norm_kw(w.get("text", ""))
            xc = (float(w.get("x0", 0)) + float(w.get("x1", 0))) / 2.0
            for kw, col_name in _HEADER_MAP.items():
                if t.startswith(kw) and col_name not in col_positions:
                    col_positions[col_name] = xc
                    break
        break

    if header_y is None or not col_positions:
        return []

    codice_cx = col_positions.get("codice", 0)
    descr_cx = col_positions.get("descr", 9999)
    codice_right_bound = min((codice_cx + descr_cx) / 2.0, codice_cx + 30)
    sorted_cols = sorted(col_positions.items(), key=lambda x: x[1])

    def _x_to_col(xc):
        if xc <= codice_right_bound:
            return "codice"
        for i, (name, cx) in enumerate(sorted_cols):
            if name == "codice":
                continue
            left_cx = sorted_cols[i - 1][1] if i > 0 else -1e9
            right_cx = sorted_cols[i + 1][1] if i < len(sorted_cols) - 1 else 1e9
            left_bound = codice_right_bound if name == sorted_cols[1][0] else (left_cx + cx) / 2.0
            right_bound = (cx + right_cx) / 2.0 if i < len(sorted_cols) - 1 else 1e9
            if left_bound <= xc < right_bound:
                return name
        return None

    voci = []
    for y in sorted(by_y.keys()):
        if y <= header_y:
            continue
        ws = by_y[y]
        row_cols: dict[str, list] = {}
        for w in ws:
            xc = (float(w.get("x0", 0)) + float(w.get("x1", 0))) / 2.0
            col = _x_to_col(xc)
            if col:
                row_cols.setdefault(col, []).append(w.get("text", ""))

        codice_tokens = row_cols.get("codice", [])
        codice = ""
        leftover = []
        for tok in codice_tokens:
            if not codice and re.match(r"^[1-9]\d{1,4}$", tok.strip()):
                codice = tok.strip()
            else:
                leftover.append(tok)
        if not codice:
            continue

        descr_parts = leftover + row_cols.get("descr", [])

        def _v(tokens):
            s = " ".join(tokens).strip()
            return s if s else "0,00"

        entry = {
            "codice": codice, "descr": " ".join(descr_parts).strip(),
            "aliq": _v(row_cols.get("aliq", [])), "unit": _v(row_cols.get("unit", [])),
            "val": _v(row_cols.get("val", [])), "comp": _v(row_cols.get("comp", [])),
            "trat": _v(row_cols.get("trat", [])),
        }
        toks = entry["val"].split()
        if len(toks) == 2 and entry["unit"] == "0,00":
            entry["unit"] = toks[0]
            entry["val"] = toks[1]
        voci.append(entry)

    return voci


# ── Funzione principale Django ─────────────────────────────────────────────────

def pdf_bytes_to_txt(pdf_bytes: bytes) -> str:
    """
    Converte i bytes di un PDF buste paga in testo strutturato.
    Restituisce il contenuto TXT come stringa.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    totale_pagine = len(doc)
    output = io.StringIO()

    for indice in range(1, totale_pagine + 1):
        fpage = doc.load_page(indice - 1)
        pw = fpage.rect.width
        ph = fpage.rect.height

        clip_target = fitz.Rect(0, TARGET_TOP_PT, pw, TARGET_BOTTOM_PT)
        chars = _fitz_page_to_chars(fpage, clip=clip_target)

        clip_id = fitz.Rect(0, ID_ROW_TOP_PT, pw, ID_ROW_BOTTOM_PT)
        words_id = _fitz_page_to_words(fpage, clip=clip_id)
        words_all = _fitz_page_to_words(fpage)

        matricola = estrai_id_busta_da_pagina(words_id, words_all)
        filiale = estrai_filiale(words_all)
        voci = estrai_voci_stipendiali(fpage)
        netto = estrai_netto(words_all)
        sezione_ferie = estrai_sezione_ferie_fs_rol(words_all)

        output.write(f"--- PAGINA {indice}/{totale_pagine} ---\n")
        righe = ricostruisci_testo_griglia(chars, pw, ph, solo_essenziale=True)
        righe = estrai_solo_sezione_giorni(righe)
        righe = normalizza_ore_gg_righe(righe)
        righe = normalizza_celle_giorni(righe)

        mese_anno = estrai_token_mese_anno(righe)
        if matricola:
            output.write(f"MATRICOLA: {matricola}\n")
            if mese_anno:
                output.write(f"ID_BUSTA: {matricola}{mese_anno}\n")
            else:
                output.write(f"ID_BUSTA: {matricola}\n")
        if filiale:
            output.write(f"FILIALE: {filiale}\n")

        colonne = ["RESIDUO A.P.", "MATURAZIONE A.C.", "GODUTE A.C.", "RESIDUO"]
        righe_matrix = ["FERIE", "F.S.", "ROL"]
        parts = []
        for rname in righe_matrix:
            for cname in colonne:
                key = f"{rname}_{cname}"
                val = sezione_ferie.get(rname, {}).get(cname, "0,00")
                parts.append(f"{key}={val}")
        output.write("SEZIONE_AC: " + " | ".join(parts) + "\n")

        for riga in righe:
            output.write(riga + "\n")

        output.write("SEZIONE_VOCI:\n")
        for v in voci:
            line = (
                f"VOCE: {v['codice']} | DESCR: {v['descr']} | "
                f"ALIQ: {v['aliq']} | UNIT: {v['unit']} | "
                f"VAL: {v['val']} | COMP: {v['comp']} | TRAT: {v['trat']}"
            )
            output.write(line + "\n")
        output.write(f"NETTO: {netto}\n\n")

    doc.close()
    return output.getvalue()
