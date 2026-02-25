"""
txt_to_db.py
------------
Adattamento Django di txt_to_excel.py.
Parsifica il TXT prodotto da pdf_parser e inserisce i dati nelle tabelle
BustaPaga, SezioneAC, Causale, CausaleGiorno, VoceBusta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from employee.models import Employee
from payroll.models.buste_paga_models import (
    BustaPaga,
    Causale,
    CausaleGiorno,
    SezioneAC,
    VoceBusta,
)

CAUSALE_MARKERS = {"*", "l", "m", "g", "v", "s", "d"}

AC_KEYS = [
    "ferie_residuo_ap", "ferie_maturazione_ac", "ferie_godute_ac", "ferie_residuo",
    "fs_residuo_ap", "fs_maturazione_ac", "fs_godute_ac", "fs_residuo",
    "rol_residuo_ap", "rol_maturazione_ac", "rol_godute_ac", "rol_residuo",
]

AC_KEY_MAP = {
    "FERIE_RESIDUO A.P.":      "ferie_residuo_ap",
    "FERIE_MATURAZIONE A.C.":  "ferie_maturazione_ac",
    "FERIE_GODUTE A.C.":       "ferie_godute_ac",
    "FERIE_RESIDUO":           "ferie_residuo",
    "F.S._RESIDUO A.P.":       "fs_residuo_ap",
    "F.S._MATURAZIONE A.C.":   "fs_maturazione_ac",
    "F.S._GODUTE A.C.":        "fs_godute_ac",
    "F.S._RESIDUO":            "fs_residuo",
    "ROL_RESIDUO A.P.":        "rol_residuo_ap",
    "ROL_MATURAZIONE A.C.":    "rol_maturazione_ac",
    "ROL_GODUTE A.C.":         "rol_godute_ac",
    "ROL_RESIDUO":             "rol_residuo",
}


def _find_spaced_token_end(text: str, token: str) -> int:
    """Ritorna la posizione di fine token tollerando spazi interni."""
    pattern = r"\s*".join(re.escape(ch) for ch in token)
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.end() if m else -1


# ── Utility ────────────────────────────────────────────────────────────────────

def it_float(s: str) -> float | None:
    """Converte numero italiano (1.234,56 oppure 1234.56) in float Python."""
    if s is None:
        return None
    s = s.strip().replace("SRL", "").strip()
    if not s or s in ("-", ""):
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_ore_gg(coda: str) -> tuple[float | None, int | None]:
    m_ore = re.search(r'ORE=(\d+(?:\.\d+)?)', coda)
    m_gg = re.search(r'GG=(\d+)', coda)
    if m_ore:
        ore = float(m_ore.group(1))
        gg = int(m_gg.group(1)) if m_gg else None
        return ore, gg
    s = coda.replace(" ", "").strip()
    if not s:
        return None, None
    m = re.match(r'^(\d+\.\d{2})(\d{1,2})?$', s)
    if m:
        return float(m.group(1)), int(m.group(2)) if m.group(2) else None
    return None, None


def parse_sezione_ac(line: str) -> dict:
    result = {k: None for k in AC_KEYS}
    suffix = line[len("SEZIONE_AC:"):].strip()
    parts = [p.strip() for p in suffix.split("|")]
    for part in parts:
        if "=" not in part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        v = v.strip().replace(",", ".")
        col = AC_KEY_MAP.get(k)
        if col:
            try:
                result[col] = float(v)
            except ValueError:
                pass
    return result


def parse_causale_block(righe: list[str]) -> tuple[list[dict], list[dict]]:
    causali_list = []
    giorni_list = []

    def _day_cols_from_day_row(day_row: str) -> list[int]:
        cols: list[int] = []
        expected = 1
        for m in re.finditer(r"\d{1,2}", day_row):
            try:
                val = int(m.group())
            except ValueError:
                continue
            if val != expected:
                continue
            cols.append(m.start())
            expected += 1
            if expected > 31:
                break
        return cols if len(cols) == 31 else []

    causale_hdr_idx = None
    for i, r in enumerate(righe):
        r_comp = re.sub(r"\s+", "", r).upper()
        if "CAUSALE" in r_comp and "ORE" in r_comp and "GG" in r_comp:
            causale_hdr_idx = i
            break
    if causale_hdr_idx is None:
        return [], []

    hdr = righe[causale_hdr_idx]
    ore_end = _find_spaced_token_end(hdr, "ORE")
    ore_pos = ore_end - 3 if ore_end != -1 else -1
    gg_end = _find_spaced_token_end(hdr, "GG")
    gg_pos = gg_end - 2 if gg_end != -1 else -1
    if ore_pos == -1 or gg_pos == -1:
        return [], []

    causale_word_end = _find_spaced_token_end(hdr, "CAUSALE")
    if causale_word_end == -1:
        return [], []
    day_start_pos = None
    for i in range(causale_word_end, ore_pos):
        if hdr[i].lower() in CAUSALE_MARKERS:
            day_start_pos = i
            break
    if day_start_pos is None:
        return [], []

    # Preferisci le colonne dai numeri giorno (riga sopra header): più affidabili.
    day_cols = []
    if causale_hdr_idx > 0:
        day_cols = _day_cols_from_day_row(righe[causale_hdr_idx - 1])

    # Fallback su marker riga CAUSALE.
    if not day_cols:
        for c in range(day_start_pos, ore_pos, 4):
            if c < len(hdr) and hdr[c].lower() in CAUSALE_MARKERS:
                day_cols.append(c)
        if len(day_cols) < 28:
            day_cols = [day_start_pos + i * 4 for i in range(31)]

    caus_counter = 0
    for row in righe[causale_hdr_idx + 1:]:
        if len(row.strip()) == 0:
            continue
        nome_fine = max(0, day_cols[0] - 2) if day_cols else day_start_pos
        nome_raw = row[:nome_fine] if nome_fine <= len(row) else row
        nome = re.sub(r"\s+", "", nome_raw).upper().rstrip("0123456789")
        if not nome:
            continue

        zona_giorni = row[day_cols[0]:day_cols[-1] + 4] if day_cols else row[day_start_pos:]
        solo_punti = all(c in (". ", " ", "\t") for c in zona_giorni)
        if solo_punti and not nome:
            continue

        ore_val, gg_val = parse_ore_gg(row)
        causali_list.append({
            "_tmp_id": caus_counter,
            "causale": nome,
            "ore_totali": ore_val,
            "gg_totali": gg_val,
        })

        # Estrai i 31 valori giornalieri per posizione sequenziale:
        # la riga dati ha esattamente 31 float X.X in ordine prima di ORE=
        ore_in_row = row.find("ORE=")
        day_zone = row[:ore_in_row] if ore_in_row != -1 else row
        float_tokens = re.findall(r"\d+\.\d+", day_zone)
        if len(float_tokens) == 31:
            for giorno, val_str in enumerate(float_tokens, start=1):
                try:
                    ore_g = float(val_str)
                except ValueError:
                    continue
                if ore_g > 0:
                    giorni_list.append({
                        "_tmp_causale": caus_counter,
                        "giorno": giorno,
                        "ore": ore_g,
                    })
        else:
            # Fallback column-based (per righe con formato inatteso)
            for idx, dcol in enumerate(day_cols):
                giorno = idx + 1
                if dcol >= len(row):
                    continue
                cell_start = max(0, dcol - 2)
                cell_end = min(len(row), dcol + 2)
                cella = row[cell_start:cell_end].strip()
                if not cella or cella == ".":
                    continue
                val_str = cella.rstrip(".")
                if not val_str:
                    continue
                try:
                    ore_g = float(val_str)
                except ValueError:
                    continue
                if ore_g > 0:
                    giorni_list.append({
                        "_tmp_causale": caus_counter,
                        "giorno": giorno,
                        "ore": ore_g,
                    })

        caus_counter += 1

    return causali_list, giorni_list


def parse_voce(line: str) -> dict | None:
    line = line.strip()
    if not line.startswith("VOCE:"):
        return None

    def get_field(name, text):
        pat = re.compile(rf"{re.escape(name)}:\s*(.*?)(?:\s*\||\s*$)")
        m = pat.search(text)
        return m.group(1).strip() if m else ""

    codice_str = get_field("VOCE", line)
    descr = get_field("DESCR", line)
    aliq_str = get_field("ALIQ", line)
    unit_str = get_field("UNIT", line)
    val_str = get_field("VAL", line)
    comp_str = get_field("COMP", line)
    trat_str = get_field("TRAT", line)

    val_tokens = val_str.split()
    if len(val_tokens) == 2 and it_float(unit_str) == 0.0:
        unit_str = val_tokens[0]
        val_str = val_tokens[1]

    try:
        codice = int(codice_str.strip())
    except ValueError:
        codice = None

    return {
        "codice_voce": codice,
        "descrizione": descr,
        "aliquota": it_float(aliq_str),
        "unita": it_float(unit_str),
        "val": it_float(val_str),
        "competenza": it_float(comp_str),
        "trattenuta": it_float(trat_str),
    }


# ── Parser TXT ─────────────────────────────────────────────────────────────────

def parse_txt_string(txt_content: str) -> dict:
    """
    Parsifica il contenuto TXT e restituisce dizionari con i dati delle 5 tabelle.
    """
    buste_list: list[dict] = []
    sezione_ac_list: list[dict] = []
    causali_list: list[dict] = []
    giorni_list: list[dict] = []
    voci_list: list[dict] = []
    pagine_scartate: list[dict] = []

    lines = txt_content.splitlines()
    page_starts = [i for i, l in enumerate(lines) if l.startswith("--- PAGINA")]
    page_starts.append(len(lines))

    global_causale_id = 1

    for pi, start in enumerate(page_starts[:-1]):
        end = page_starts[pi + 1]
        block = lines[start:end]
        pagina_corrente = None
        if block:
            m_page = re.match(r"^---\s*PAGINA\s*(\d+)\s*/\s*\d+\s*---", block[0].strip(), flags=re.IGNORECASE)
            if m_page:
                pagina_corrente = int(m_page.group(1))

        matricola = id_busta = filiale = None
        sezione_ac_raw = None

        for l in block:
            if l.startswith("MATRICOLA:"):
                matricola = l[len("MATRICOLA:"):].strip()
            elif l.startswith("ID_BUSTA:"):
                id_busta = l[len("ID_BUSTA:"):].strip()
            elif l.startswith("FILIALE:"):
                filiale = l[len("FILIALE:"):].strip()
            elif l.startswith("SEZIONE_AC:"):
                sezione_ac_raw = l

        if not matricola or not id_busta:
            pagine_scartate.append({
                "pagina": pagina_corrente,
                "motivo": "MATRICOLA o ID_BUSTA non trovati",
            })
            continue

        m_anno = re.search(r"([A-Z]{3})\.(\d{4})$", id_busta)
        mese = m_anno.group(1) if m_anno else ""
        anno = int(m_anno.group(2)) if m_anno else 0

        netto = None
        for l in block:
            if l.startswith("NETTO:"):
                netto = it_float(l[len("NETTO:"):].strip())
                break

        buste_list.append({
            "id_busta": id_busta,
            "matricola": matricola,
            "filiale": filiale,
            "mese": mese,
            "anno": anno,
            "netto": netto,
            "_pagina": pagina_corrente,
        })

        if sezione_ac_raw:
            ac = parse_sezione_ac(sezione_ac_raw)
            ac["id_busta"] = id_busta
            sezione_ac_list.append(ac)

        # Blocco causali
        causale_block_righe = []
        in_causale = False
        for l in block:
            l_comp = re.sub(r"\s+", "", l).upper()
            if "CAUSALE" in l_comp and "ORE" in l_comp and "GG" in l_comp:
                in_causale = True
            if "SEZIONE_VOCI:" in l:
                break
            if in_causale:
                causale_block_righe.append(l)

        caus_raw, giorn_raw = parse_causale_block(causale_block_righe)
        for c in caus_raw:
            tmp = c["_tmp_id"]
            causali_list.append({
                "_id": global_causale_id + tmp,
                "id_busta": id_busta,
                "causale": c["causale"],
                "ore_totali": c["ore_totali"],
                "gg_totali": c["gg_totali"],
            })
        for g in giorn_raw:
            giorni_list.append({
                "_id_causale": global_causale_id + g["_tmp_causale"],
                "giorno": g["giorno"],
                "ore": g["ore"],
            })
        global_causale_id += len(caus_raw)

        # Voci stipendiali
        in_voci = False
        for l in block:
            if l.startswith("SEZIONE_VOCI:"):
                in_voci = True
                continue
            if in_voci and l.startswith("VOCE:"):
                v = parse_voce(l)
                if v:
                    v["id_busta"] = id_busta
                    voci_list.append(v)
            elif in_voci and l.startswith("NETTO:"):
                break

    return {
        "buste_paga": buste_list,
        "sezione_ac": sezione_ac_list,
        "causali": causali_list,
        "causali_giorni": giorni_list,
        "voci_busta": voci_list,
        "_pagine_scartate": pagine_scartate,
    }


# ── Insert nel DB Django ────────────────────────────────────────────────────────

@dataclass
class ImportResult:
    inserite: int = 0
    aggiornate: int = 0
    saltate: int = 0
    errori: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


def inserisci_nel_db(data: dict) -> ImportResult:
    """
    Inserisce i dati parsificati nelle tabelle Django.
    Usa update_or_create per i record principali (busta paga = idempotente).
    Restituisce un ImportResult con il riepilogo.
    """
    result = ImportResult()

    # Mappa id_causale tmp → ID Django reale
    causale_id_map: dict[int, int] = {}

    n_buste = len(data.get("buste_paga", []))
    n_voci = len(data.get("voci_busta", []))
    n_causali = len(data.get("causali", []))
    n_giorni = len(data.get("causali_giorni", []))
    n_ac = len(data.get("sezione_ac", []))
    result.log.append(f"📦 Struttura parsificata: {n_buste} buste, {n_voci} voci, {n_causali} causali, {n_giorni} giorni, {n_ac} sezioni AC")

    imported_ids = {b.get("id_busta") for b in data.get("buste_paga", []) if b.get("id_busta")}
    id_to_page = {
        b.get("id_busta"): b.get("_pagina")
        for b in data.get("buste_paga", [])
        if b.get("id_busta")
    }

    # ── 1. BustaPaga ──────────────────────────────────────────────────────────
    for b in data["buste_paga"]:
        # Cerca il dipendente per codice_paghe == matricola
        try:
            employee = Employee.objects.filter(codice_paghe=b["matricola"]).first()
        except Exception:
            employee = None

        busta, created = BustaPaga.objects.update_or_create(
            id_busta=b["id_busta"],
            defaults={
                "matricola": b["matricola"],
                "filiale": b.get("filiale"),
                "mese": b["mese"],
                "anno": b["anno"],
                "netto": b.get("netto"),
                "employee_id": employee,
            },
        )
        if created:
            result.inserite += 1
            emp_label = f"→ {employee}" if employee else "(dipendente non trovato)"
            result.log.append(f"✅ Inserita: {b['id_busta']} mat={b['matricola']} {emp_label}")
        else:
            result.aggiornate += 1
            result.log.append(f"🔄 Aggiornata: {b['id_busta']} mat={b['matricola']}")

    # ── 2. SezioneAC ──────────────────────────────────────────────────────────
    result.log.append(f"💾 Scrittura SezioneAC ({len(data['sezione_ac'])} record)…")
    for ac in data["sezione_ac"]:
        id_busta = ac.pop("id_busta")
        try:
            busta_obj = BustaPaga.objects.get(id_busta=id_busta)
            SezioneAC.objects.update_or_create(
                id_busta=busta_obj,
                defaults={k: ac.get(k) for k in AC_KEYS},
            )
        except BustaPaga.DoesNotExist:
            result.errori.append(f"SezioneAC: busta {id_busta} non trovata")
            result.log.append(f"⚠️  SezioneAC: busta {id_busta} non trovata")

    # ── 3. Causali ────────────────────────────────────────────────────────────
    result.log.append(f"💾 Scrittura Causali ({len(data['causali'])} record)…")
    for c in data["causali"]:
        tmp_id = c.pop("_id")
        id_busta = c.pop("id_busta")
        try:
            busta_obj = BustaPaga.objects.get(id_busta=id_busta)
            # Se la causale esiste già (stessa busta + stesso nome), aggiorna
            caus_obj, _ = Causale.objects.update_or_create(
                id_busta=busta_obj,
                causale=c["causale"],
                defaults={
                    "ore_totali": c.get("ore_totali"),
                    "gg_totali": c.get("gg_totali"),
                },
            )
            causale_id_map[tmp_id] = caus_obj.pk
        except BustaPaga.DoesNotExist:
            result.errori.append(f"Causale: busta {id_busta} non trovata")

    # ── 4. CausaliGiorni ──────────────────────────────────────────────────────
    result.log.append(f"💾 Scrittura CausaliGiorni ({len(data['causali_giorni'])} record)…")
    for g in data["causali_giorni"]:
        causale_pk = causale_id_map.get(g["_id_causale"])
        if causale_pk is None:
            continue
        try:
            causale_obj = Causale.objects.get(pk=causale_pk)
            CausaleGiorno.objects.update_or_create(
                id_causale=causale_obj,
                giorno=g["giorno"],
                defaults={
                    "id_busta": causale_obj.id_busta,
                    "ore": g["ore"],
                },
            )
        except Causale.DoesNotExist:
            result.errori.append(f"CausaleGiorno: causale pk {causale_pk} non trovata")

    result.log.append(f"💾 Scrittura VociBusta ({len(data['voci_busta'])} record)…")
    # ── 5. VociBusta ──────────────────────────────────────────────────────────
    for v in data["voci_busta"]:
        id_busta = v.pop("id_busta")
        try:
            busta_obj = BustaPaga.objects.get(id_busta=id_busta)
            VoceBusta.objects.update_or_create(
                id_busta=busta_obj,
                codice_voce=v["codice_voce"],
                defaults={
                    "descrizione": v.get("descrizione"),
                    "aliquota": v.get("aliquota"),
                    "unita": v.get("unita"),
                    "val": v.get("val"),
                    "competenza": v.get("competenza"),
                    "trattenuta": v.get("trattenuta"),
                },
            )
        except BustaPaga.DoesNotExist:
            result.errori.append(f"VoceBusta: busta {id_busta} non trovata")

    # ── 6. Validazione integrità id_busta post-import ───────────────────────
    if imported_ids:
        caus_ids = set(Causale.objects.filter(id_busta_id__in=imported_ids).values_list("id_busta_id", flat=True))
        ac_ids = set(SezioneAC.objects.filter(id_busta_id__in=imported_ids).values_list("id_busta_id", flat=True))
        voci_ids = set(VoceBusta.objects.filter(id_busta_id__in=imported_ids).values_list("id_busta_id", flat=True))

        def _add_missing_error(section_name: str, missing_ids: set[str]) -> None:
            if not missing_ids:
                return
            pagine = sorted({id_to_page.get(i) for i in missing_ids if id_to_page.get(i) is not None})
            pagine_txt = ", ".join(str(p) for p in pagine[:30])
            if len(pagine) > 30:
                pagine_txt += ", ..."
            msg = (
                f"Integrità import: record mancanti in {section_name} per {len(missing_ids)} buste"
                + (f" (pagine PDF: {pagine_txt})" if pagine_txt else "")
            )
            result.errori.append(msg)
            result.log.append(f"⚠️  {msg}")

        _add_missing_error("payroll_causale", imported_ids - caus_ids)
        _add_missing_error("payroll_sezioneac", imported_ids - ac_ids)
        _add_missing_error("payroll_vocebusta", imported_ids - voci_ids)

    result.log.append(
        f"🏁 Fine inserimento: {result.inserite} inserite, "
        f"{result.aggiornate} aggiornate, {result.saltate} saltate, "
        f"{len(result.errori)} errori"
    )
    return result


def importa_pdf_cedolini(pdf_bytes: bytes) -> ImportResult:
    """
    Funzione di alto livello: PDF bytes → TXT → DB insert.
    Usata dalla view Django.
    """
    import os
    from payroll.services.pdf_parser import pdf_bytes_to_txt

    size_kb = len(pdf_bytes) / 1024
    result_pre = ImportResult()
    result_pre.log.append(f"📂 File ricevuto: {size_kb:.1f} KB")

    txt_content = pdf_bytes_to_txt(pdf_bytes)
    n_pagine = txt_content.count("--- PAGINA")
    result_pre.log.append(f"📄 PDF convertito in testo: {len(txt_content)} caratteri, ~{n_pagine} pagine")

    data = parse_txt_string(txt_content)
    result_pre.log.append(
        f"🔍 Parsing completato: {len(data.get('buste_paga', []))} buste trovate"
    )

    result = inserisci_nel_db(data)

    # Segnala eventuali pagine scartate già in fase di parsing
    for item in data.get("_pagine_scartate", []):
        pagina = item.get("pagina")
        motivo = item.get("motivo", "Pagina non importata")
        if pagina is not None:
            result.errori.append(f"Pagina {pagina}: {motivo}")
            result.log.append(f"⚠️  Pagina {pagina}: {motivo}")
        else:
            result.errori.append(motivo)
            result.log.append(f"⚠️  {motivo}")

    # prepend pre-log
    result.log = result_pre.log + result.log
    return result
