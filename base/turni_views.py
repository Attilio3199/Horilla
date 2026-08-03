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
    # tinyint(1) → BOOLEAN must come before generic tinyint
    (re.compile(r"\btinyint\s*\(\s*1\s*\)(?:\s+unsigned\b)?", re.I), "BOOLEAN"),
    (re.compile(r"\bbigint\s*\(\d+\)(?:\s+unsigned\b)?", re.I), "BIGINT"),
    (re.compile(r"\bint\s*\(\d+\)(?:\s+unsigned\b)?", re.I), "INTEGER"),
    (re.compile(r"\bmediumint\s*\(\d+\)(?:\s+unsigned\b)?", re.I), "INTEGER"),
    (re.compile(r"\bsmallint\s*\(\d+\)(?:\s+unsigned\b)?", re.I), "SMALLINT"),
    (re.compile(r"\btinyint\s*\(\d+\)(?:\s+unsigned\b)?", re.I), "SMALLINT"),
    (re.compile(r"\bdouble(\s+precision)?(?:\s*\(\d+,\d+\))?", re.I), "DOUBLE PRECISION"),
    (re.compile(r"\bfloat(?:\s*\(\d+,\d+\))?", re.I), "REAL"),
    (re.compile(r"\bdecimal\s*\((\d+),(\d+)\)", re.I), r"NUMERIC(\1,\2)"),
    (re.compile(r"\bdatetime(?:\s*\(\d+\))?", re.I), "TIMESTAMP"),
    (re.compile(r"\btimestamp(?:\s*\(\d+\))?", re.I), "TIMESTAMP"),
    (re.compile(r"\btime(?:\s*\(\d+\))?", re.I), "TIME"),
    (re.compile(r"\byear(?:\s*\(\d+\))?", re.I), "SMALLINT"),
    (re.compile(r"\blongtext\b", re.I), "TEXT"),
    (re.compile(r"\bmediumtext\b", re.I), "TEXT"),
    (re.compile(r"\btext\b", re.I), "TEXT"),
    (re.compile(r"\blongblob\b", re.I), "BYTEA"),
    (re.compile(r"\bblob\b", re.I), "BYTEA"),
    (re.compile(r"\bvarchar\s*\((\d+)\)", re.I), r"VARCHAR(\1)"),
    (re.compile(r"\bchar\s*\((\d+)\)", re.I), r"CHAR(\1)"),
    (re.compile(r"\benum\s*\([^)]+\)", re.I), "TEXT"),
    (re.compile(r"\bset\s*\([^)]+\)", re.I), "TEXT"),
    (re.compile(r"\bjson\b", re.I), "JSONB"),
    (re.compile(r"\bbit\s*\(\d+\)", re.I), "BIT VARYING"),
]

# Column-level attributes to strip (MySQL-specific)
_STRIP_COL_ATTRS = re.compile(
    r"\b(unsigned|zerofill|character set \S+|collate \S+|auto_increment)\b",
    re.I,
)

# These fields are deliberately not replicated in the reporting table.  Keep
# the list centralised because an ignored field must be removed from both the
# DDL and the values in every INSERT statement.
_IGNORED_COLUMNS = {"preferenza", "bloccoautomatico", "gdv_id_app"}


def _convert_type(col_def: str) -> str:
    """Apply all type and attribute mappings to a single column definition."""
    for pattern, replacement in _TYPE_MAP:
        col_def = pattern.sub(replacement, col_def)

    # Strip MySQL-only column attributes
    col_def = _STRIP_COL_ATTRS.sub("", col_def)

    # DEFAULT current_timestamp() / current_timestamp(6) → CURRENT_TIMESTAMP
    col_def = re.sub(
        r"\bDEFAULT\s+current_timestamp\s*\(\s*\d*\s*\)",
        "DEFAULT CURRENT_TIMESTAMP",
        col_def,
        flags=re.I,
    )

    # ON UPDATE CURRENT_TIMESTAMP(n) is MySQL-only — remove entirely
    col_def = re.sub(
        r"\bON\s+UPDATE\s+CURRENT_TIMESTAMP\s*(?:\(\s*\d*\s*\))?",
        "",
        col_def,
        flags=re.I,
    )

    # MySQL zero-date defaults are invalid in PostgreSQL
    col_def = re.sub(
        r"DEFAULT\s+'0000-00-00(?:\s+00:00:00)?'",
        "DEFAULT NULL",
        col_def,
        flags=re.I,
    )

    # Collapse multiple spaces left by removals
    col_def = re.sub(r"  +", " ", col_def)
    return col_def.strip()


def _find_matching_paren(text: str, open_pos: int) -> int:
    """
    Given the position of an opening '(' in *text*, return the position
    of the matching closing ')' using depth counting.
    Raises ValueError if not found.
    """
    depth = 0
    for i in range(open_pos, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("Unmatched parenthesis in SQL text.")


def _split_columns(inner: str) -> list[str]:
    """
    Split a comma-separated column/constraint list, correctly ignoring
    commas that appear inside nested parentheses (e.g. ENUM values).
    """
    items: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in inner:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            item = "".join(buf).strip()
            if item:
                items.append(item)
            buf = []
        else:
            buf.append(ch)
    item = "".join(buf).strip()
    if item:
        items.append(item)
    return items


def _column_name(definition: str) -> str | None:
    """Return the column name from a CREATE TABLE item, if it is a column."""
    match = re.match(r'\s*[`"\']?([^`"\'\s(]+)[`"\']?', definition)
    return match.group(1) if match else None


def _source_columns(mysql_ddl: str) -> list[str]:
    """Read the source column order from a MariaDB CREATE TABLE statement."""
    open_paren = mysql_ddl.index("(")
    close_paren = _find_matching_paren(mysql_ddl, open_paren)
    columns = []
    for item in _split_columns(mysql_ddl[open_paren + 1 : close_paren]):
        upper = item.upper().lstrip()
        if re.match(r"(PRIMARY\s+KEY|UNIQUE\s+(KEY|INDEX)|KEY\s+|INDEX\s+|CONSTRAINT\b)", upper):
            continue
        name = _column_name(item)
        if name:
            columns.append(name)
    return columns


def _extract_create_table(sql_text: str, table_name: str) -> str | None:
    """
    Find and return the full CREATE TABLE block for *table_name*.
    Uses parenthesis depth counting so nested parens don't break the match.
    """
    start_re = re.compile(
        r"CREATE\s+TABLE\s+[`'\"]?" + re.escape(table_name) + r"[`'\"]?\s*\(",
        re.I,
    )
    m = start_re.search(sql_text)
    if not m:
        return None

    stmt_start = m.start()
    open_paren = m.end() - 1  # position of the '(' we just matched
    close_paren = _find_matching_paren(sql_text, open_paren)

    # Include everything up to (and including) the next semicolon
    semi = sql_text.find(";", close_paren)
    end = semi + 1 if semi != -1 else close_paren + 1
    return sql_text[stmt_start:end]


def _parse_create_table(mysql_ddl: str) -> str:
    """
    Convert a MariaDB CREATE TABLE statement to a PostgreSQL-compatible DDL
    targeting the destination table `_turni_creati`.
    """
    ddl = mysql_ddl.replace("\r\n", "\n").replace("\r", "\n")

    # Locate the outer '(' using depth-counting so we get the real body
    open_paren = ddl.index("(")
    close_paren = _find_matching_paren(ddl, open_paren)
    inner = ddl[open_paren + 1 : close_paren]

    pg_items: list[str] = []
    for item in _split_columns(inner):
        item = item.strip()
        if not item:
            continue

        upper = item.upper().lstrip()

        # Skip all KEY / INDEX definitions (we only keep PRIMARY KEY)
        if re.match(r"(UNIQUE\s+(KEY|INDEX)\b|KEY\s+|INDEX\s+)", upper):
            continue
        # Skip CONSTRAINT ... KEY (foreign keys etc.)
        if re.match(r"CONSTRAINT\b", upper) and "KEY" in upper:
            continue

        if re.match(r"PRIMARY\s+KEY\b", upper):
            # Strip backtick quoting inside PRIMARY KEY column list
            item = re.sub(r"`([^`]+)`", r'"\1"', item)
            pg_items.append(item)
            continue

        column_name = _column_name(item)
        if column_name and column_name.lower() in _IGNORED_COLUMNS:
            continue

        # Dequote column names: `ColName` → "ColName"
        item = re.sub(r"`([^`]+)`", r'"\1"', item)

        # Convert MySQL types / attributes to PostgreSQL equivalents
        item = _convert_type(item)

        # Strip COMMENT clauses
        item = re.sub(r"\s+COMMENT\s+'(?:[^'\\]|\\.)*'", "", item, flags=re.I)

        # Replace MySQL bit-literal defaults: DEFAULT b'0' → DEFAULT 0
        item = re.sub(
            r"DEFAULT\s+b'(\d)'",
            lambda m: "DEFAULT " + m.group(1),
            item,
            flags=re.I,
        )

        pg_items.append(item)

    body = ",\n    ".join(pg_items)
    return f'CREATE TABLE IF NOT EXISTS "_turni_creati" (\n    {body}\n);'


def _find_sql_paren(text: str, open_pos: int) -> int:
    """Find a closing parenthesis while respecting SQL quoted literals."""
    depth = 0
    quote = None
    i = open_pos
    while i < len(text):
        char = text[i]
        if quote:
            if char == "\\\\":
                i += 2
                continue
            if char == quote:
                # SQL escapes a quote by doubling it.
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("Unmatched parenthesis in SQL values.")


def _split_sql_values(values: str) -> list[str]:
    """Split a VALUES tuple without splitting commas in strings/functions."""
    items: list[str] = []
    depth = 0
    quote = None
    start = 0
    i = 0
    while i < len(values):
        char = values[i]
        if quote:
            if char == "\\\\":
                i += 2
                continue
            if char == quote:
                if i + 1 < len(values) and values[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(values[start:i].strip())
            start = i + 1
        i += 1
    items.append(values[start:].strip())
    return items


def _rewrite_ignored_columns(stmt: str, source_columns: list[str]) -> str:
    """Remove ignored columns and their corresponding values from an INSERT."""
    header = re.match(
        r'^INSERT\s+INTO\s+"_turni_creati"\s*(?P<columns>\([^)]*\))?\s*VALUES\s*',
        stmt,
        re.I | re.S,
    )
    if not header:
        return stmt

    columns_text = header.group("columns")
    columns = (
        [_column_name(column) or "" for column in _split_columns(columns_text[1:-1])]
        if columns_text
        else source_columns
    )
    ignored_indexes = [
        index for index, column in enumerate(columns) if column.lower() in _IGNORED_COLUMNS
    ]
    if not ignored_indexes:
        return stmt

    kept_columns = [
        column for index, column in enumerate(columns) if index not in ignored_indexes
    ]
    values_text = stmt[header.end() :].rstrip()
    if values_text.endswith(";"):
        values_text = values_text[:-1].rstrip()

    tuples = []
    position = 0
    while position < len(values_text):
        while position < len(values_text) and values_text[position].isspace():
            position += 1
        if position >= len(values_text) or values_text[position] != "(":
            raise ValueError("Formato VALUES non supportato per l'importazione.")
        end = _find_sql_paren(values_text, position)
        values = _split_sql_values(values_text[position + 1 : end])
        if len(values) != len(columns):
            raise ValueError("Numero di valori non coerente con le colonne del dump.")
        tuples.append(
            "(" + ",".join(value for index, value in enumerate(values) if index not in ignored_indexes) + ")"
        )
        position = end + 1
        while position < len(values_text) and values_text[position].isspace():
            position += 1
        if position < len(values_text):
            if values_text[position] != ",":
                raise ValueError("Formato VALUES non supportato per l'importazione.")
            position += 1

    pg_columns = ", ".join(f'"{column}"' for column in kept_columns)
    return f'INSERT INTO "_turni_creati" ({pg_columns}) VALUES ' + ",".join(tuples) + ";"


def _extract_inserts(
    sql_text: str, source_table: str, source_columns: list[str]
) -> list[str]:
    """
    Extract all INSERT INTO `source_table` statements from the dump and
    rewrite them to target `_turni_creati`.
    Handles both single-row and multi-row (VALUES (...),(...),...) inserts.

    The terminator is `);` instead of just `;` so that semicolons that
    appear inside quoted string values (e.g. 'Turno unico; mattina') are
    not mistakenly treated as statement terminators.
    """
    pattern = re.compile(
        r"INSERT\s+INTO\s+[`'\"]?" + re.escape(source_table) + r"[`'\"]?"
        r"\s*(?:\([^)]*\)\s*)?VALUES\s*.+?\)\s*;",
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
        results.append(_rewrite_ignored_columns(stmt, source_columns))
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
    try:
        source_columns = _source_columns(create_raw)
        inserts = _extract_inserts(sql_text, source_table, source_columns)
    except ValueError as exc:
        return render(
            request,
            "base/turni_import.html",
            {"error": f"Errore nella conversione degli INSERT: {exc}"},
        )

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
