"""
turni_views.py

View to import the `turni_creati` table from a MariaDB SQL dump
into the PostgreSQL table `_turni_creati`.
"""

import re

from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

# ─── MariaDB → PostgreSQL type mapping ────────────────────────────────────────

_TYPE_MAP = [
    (re.compile(r"\btinyint\s*\(\s*1\s*\)", re.I), "BOOLEAN"),
    (re.compile(r"\bbigint\s*\(\d+\)\s*(unsigned)?", re.I), "BIGINT"),
    (re.compile(r"\bint\s*\(\d+\)\s*(unsigned)?", re.I), "INTEGER"),
    (re.compile(r"\bsmallint\s*\(\d+\)\s*(unsigned)?", re.I), "SMALLINT"),
    (re.compile(r"\btinyint\s*\(\d+\)\s*(unsigned)?", re.I), "SMALLINT"),
    (re.compile(r"\bdouble(\s+precision)?(\s*\(\d+,\d+\))?", re.I), "DOUBLE PRECISION"),
    (re.compile(r"\bfloat(\s*\(\d+,\d+\))?", re.I), "REAL"),
    (re.compile(r"\bdecimal\s*\((\d+),(\d+)\)", re.I), r"NUMERIC(\1,\2)"),
    (re.compile(r"\bdatetime(\s*\(\d+\))?", re.I), "TIMESTAMP"),
    (re.compile(r"\btimestamp(\s*\(\d+\))?", re.I), "TIMESTAMP"),
    (re.compile(r"\btime(\s*\(\d+\))?", re.I), "TIME"),
    (re.compile(r"\byear(\s*\(\d+\))?", re.I), "SMALLINT"),
    (re.compile(r"\blongtext", re.I), "TEXT"),
    (re.compile(r"\bmediumtext", re.I), "TEXT"),
    (re.compile(r"\btext", re.I), "TEXT"),
    (re.compile(r"\blongblob", re.I), "BYTEA"),
    (re.compile(r"\bblob", re.I), "BYTEA"),
    (re.compile(r"\bvarchar\s*\((\d+)\)", re.I), r"VARCHAR(\1)"),
    (re.compile(r"\bchar\s*\((\d+)\)", re.I), r"CHAR(\1)"),
    (re.compile(r"\benum\s*\([^)]+\)", re.I), "TEXT"),
    (re.compile(r"\bset\s*\([^)]+\)", re.I), "TEXT"),
    (re.compile(r"\bjson\b", re.I), "JSONB"),
    (re.compile(r"\bbit\s*\(\d+\)", re.I), "BIT VARYING"),
]

# Column-level attribute patterns to strip (MySQL-specific)
_STRIP_COL_ATTRS = re.compile(
    r"\b(unsigned|zerofill|character set \S+|collate \S+|auto_increment"
    r"|on update CURRENT_TIMESTAMP(\(\d+\))?)\b",
    re.I,
)

# Table-level options to strip (everything after the closing parenthesis)
_TABLE_OPTIONS = re.compile(
    r"\)\s*(ENGINE\s*=.*|DEFAULT\s+CHARSET.*|COLLATE.*|AUTO_INCREMENT.*|ROW_FORMAT.*)?;\s*$",
    re.I | re.DOTALL,
)


def _convert_type(col_def: str) -> str:
    """Apply all type mappings to a column definition string."""
    for pattern, replacement in _TYPE_MAP:
        col_def = pattern.sub(replacement, col_def)
    col_def = _STRIP_COL_ATTRS.sub("", col_def)
    return col_def


def _extract_create_table(sql_text: str, table_name: str) -> str | None:
    """
    Find and return the CREATE TABLE block for `table_name` in a MariaDB dump.
    Returns None if not found.
    """
    pattern = re.compile(
        r"CREATE\s+TABLE\s+[`'\"]?" + re.escape(table_name) + r"[`'\"]?"
        r"\s*\((.+?)\)\s*[^;]*;",
        re.I | re.DOTALL,
    )
    m = pattern.search(sql_text)
    if not m:
        return None
    return m.group(0)


def _parse_create_table(mysql_ddl: str) -> str:
    """
    Convert a MariaDB CREATE TABLE statement to a PostgreSQL-compatible one,
    targeting the destination table name `_turni_creati`.
    """
    # Normalise line endings
    ddl = mysql_ddl.replace("\r\n", "\n").replace("\r", "\n")

    # Extract column/constraint block between outer parentheses
    inner_match = re.search(r"\(\s*(.*)\s*\)", ddl, re.DOTALL)
    if not inner_match:
        raise ValueError("Cannot parse CREATE TABLE body.")
    inner = inner_match.group(1)

    lines = []
    for raw_line in inner.split("\n"):
        line = raw_line.strip().rstrip(",").strip()
        if not line:
            continue

        upper = line.upper()

        # Skip MySQL-specific keys that are not portable
        if re.match(r"(PRIMARY\s+KEY|UNIQUE\s+(KEY|INDEX)|KEY|INDEX|CONSTRAINT)", upper):
            # Keep PRIMARY KEY constraints; skip the rest
            if upper.startswith("PRIMARY"):
                # Remove backticks from column list
                line = re.sub(r"`", "", line)
                lines.append(line)
            # Skip KEYs / INDEXes – can be added later
            continue

        # Remove backtick quoting from column names
        line = re.sub(r"`([^`]+)`", r'"\1"', line)

        # Convert data types
        line = _convert_type(line)

        # Remove any leftover COMMENT clauses
        line = re.sub(r"\s+COMMENT\s+'[^']*'", "", line, flags=re.I)

        # Replace DEFAULT b'0' / DEFAULT b'1' (MySQL bit defaults)
        line = re.sub(r"DEFAULT\s+b'(\d)'", lambda m: "DEFAULT " + m.group(1), line, flags=re.I)

        lines.append(line)

    columns_sql = ",\n    ".join(lines)
    return f'CREATE TABLE IF NOT EXISTS "_turni_creati" (\n    {columns_sql}\n);'


def _extract_inserts(sql_text: str, source_table: str) -> list[str]:
    """
    Extract all INSERT INTO `source_table` statements from the dump and
    rewrite them to target `_turni_creati`.
    Handles both single-row and multi-row (VALUES (...),(...),...) inserts.
    """
    pattern = re.compile(
        r"INSERT\s+INTO\s+[`'\"]?" + re.escape(source_table) + r"[`'\"]?"
        r"\s*(?:\([^)]*\)\s*)?VALUES\s*.+?;",
        re.I | re.DOTALL,
    )
    results = []
    for m in pattern.finditer(sql_text):
        stmt = m.group(0)
        # Replace source table name reference with _turni_creati
        stmt = re.sub(
            r"INSERT\s+INTO\s+[`'\"]?" + re.escape(source_table) + r"[`'\"]?",
            'INSERT INTO "_turni_creati"',
            stmt,
            count=1,
            flags=re.I,
        )
        # MariaDB uses \' for escaping inside strings; PostgreSQL uses ''
        stmt = stmt.replace("\\'", "''")
        results.append(stmt)
    return results


def _detect_source_table_name(sql_text: str) -> str | None:
    """Detect the table name (turni_creati or similar) from the dump."""
    m = re.search(
        r"CREATE\s+TABLE\s+[`'\"]?(turni[_\w]*)[`'\"]?",
        sql_text,
        re.I,
    )
    return m.group(1) if m else None


# ─── View ─────────────────────────────────────────────────────────────────────


@login_required
@require_http_methods(["GET", "POST"])
def turni_import(request):
    """
    GET  – render the upload form.
    POST – accept the .sql dump, parse it, create _turni_creati and import rows.
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Permesso negato."}, status=403)

    if request.method == "GET":
        return render(request, "base/turni_import.html")

    # ── POST ──────────────────────────────────────────────────────────────────
    dump_file = request.FILES.get("dump_file")
    if not dump_file:
        return render(
            request,
            "base/turni_import.html",
            {"error": "Nessun file selezionato."},
        )

    filename = dump_file.name.lower()
    if not filename.endswith(".sql"):
        return render(
            request,
            "base/turni_import.html",
            {"error": "Il file deve avere estensione .sql"},
        )

    # Read the dump (up to 50 MB)
    max_size = 50 * 1024 * 1024
    if dump_file.size > max_size:
        return render(
            request,
            "base/turni_import.html",
            {"error": "Il file è troppo grande (max 50 MB)."},
        )

    try:
        sql_text = dump_file.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return render(
            request,
            "base/turni_import.html",
            {"error": f"Errore nella lettura del file: {exc}"},
        )

    # ── Detect source table name ──────────────────────────────────────────────
    source_table = _detect_source_table_name(sql_text)
    if not source_table:
        return render(
            request,
            "base/turni_import.html",
            {
                "error": (
                    "Nessuna tabella con nome 'turni*' trovata nel dump. "
                    "Assicurati che il dump contenga la tabella turni_creati."
                )
            },
        )

    # ── Parse CREATE TABLE ────────────────────────────────────────────────────
    create_raw = _extract_create_table(sql_text, source_table)
    if not create_raw:
        return render(
            request,
            "base/turni_import.html",
            {"error": f"CREATE TABLE per '{source_table}' non trovato nel dump."},
        )

    try:
        create_pg = _parse_create_table(create_raw)
    except ValueError as exc:
        return render(
            request,
            "base/turni_import.html",
            {"error": f"Errore nella conversione DDL: {exc}"},
        )

    # ── Extract INSERT statements ─────────────────────────────────────────────
    inserts = _extract_inserts(sql_text, source_table)

    # ── Execute in PostgreSQL ─────────────────────────────────────────────────
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Drop existing table and recreate fresh
                cursor.execute('DROP TABLE IF EXISTS "_turni_creati";')
                cursor.execute(create_pg)
                for stmt in inserts:
                    cursor.execute(stmt)
    except Exception as exc:
        return render(
            request,
            "base/turni_import.html",
            {"error": f"Errore durante l'importazione nel database: {exc}"},
        )

    return render(
        request,
        "base/turni_import.html",
        {
            "success": True,
            "rows_imported": len(inserts),
            "source_table": source_table,
        },
    )
