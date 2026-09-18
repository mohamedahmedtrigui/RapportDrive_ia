import ssl

import pymysql
import pymysql.cursors

from app.config import get_settings

_settings = get_settings()


def _ssl_kwargs() -> dict:
    if _settings.db_ssl_ca:
        # Full certificate verification when a CA file is available.
        return {"ssl": {"ca": _settings.db_ssl_ca}}

    if _settings.db_ssl:
        # Encrypted but unverified — enough for providers like Aiven that
        # enforce TLS, without needing to bundle their CA cert into the
        # deploy. Upgrade to db_ssl_ca above if stricter verification matters.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return {"ssl": ctx}

    return {}


def _connect():
    ssl_kwargs = _ssl_kwargs()

    return pymysql.connect(
        host=_settings.db_host,
        port=_settings.db_port,
        database=_settings.db_database,
        user=_settings.db_username,
        password=_settings.db_password,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        **ssl_kwargs,
    )


def search_entries(
    chauffeur: str | None = None,
    client: str | None = None,
    zone: str | None = None,
    categorie: str | None = None,
    severite: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    per_page: int = 10,
) -> dict:
    clauses = []
    params: list = []

    if chauffeur:
        clauses.append("d.nom LIKE %s")
        params.append(f"%{chauffeur}%")
    if client:
        clauses.append("re.client_nom LIKE %s")
        params.append(f"%{client}%")
    if zone:
        clauses.append("z.nom LIKE %s")
        params.append(f"%{zone}%")
    if categorie:
        clauses.append("re.categorie = %s")
        params.append(categorie)
    if severite:
        clauses.append("re.severite = %s")
        params.append(severite)
    if date_from:
        clauses.append("r.date_rapport >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("r.date_rapport <= %s")
        params.append(date_to)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    per_page = max(1, min(per_page, 30))

    sql = f"""
        SELECT re.id, re.course_id, re.description, re.categorie, re.severite,
               re.client_nom, d.nom AS chauffeur, z.nom AS zone,
               r.id AS report_id, r.titre AS rapport_titre, r.date_rapport
        FROM report_entries re
        JOIN reports r ON r.id = re.report_id
        LEFT JOIN drivers d ON d.id = re.driver_id
        LEFT JOIN zones z ON z.id = re.zone_id
        {where}
        ORDER BY re.created_at DESC
        LIMIT %s
    """
    params.append(per_page)

    with _connect() as conn, conn.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        count_sql = f"""
            SELECT COUNT(*) AS total
            FROM report_entries re
            JOIN reports r ON r.id = re.report_id
            LEFT JOIN drivers d ON d.id = re.driver_id
            LEFT JOIN zones z ON z.id = re.zone_id
            {where}
        """
        cursor.execute(count_sql, params[:-1])
        total = cursor.fetchone()["total"]

    for row in rows:
        row["date_rapport"] = str(row["date_rapport"]) if row["date_rapport"] else None

    return {"total": total, "entries": rows}


def top_cited_drivers(
    categorie: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    clauses = ["re.driver_id IS NOT NULL"]
    params: list = []
    needs_report_join = bool(date_from or date_to)

    if categorie:
        clauses.append("re.categorie = %s")
        params.append(categorie)
    if date_from:
        clauses.append("r.date_rapport >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("r.date_rapport <= %s")
        params.append(date_to)

    join = "JOIN reports r ON r.id = re.report_id" if needs_report_join else ""
    where = f"WHERE {' AND '.join(clauses)}"

    sql = f"""
        SELECT re.driver_id, d.nom AS chauffeur, d.score, re.categorie, COUNT(*) AS total
        FROM report_entries re
        JOIN drivers d ON d.id = re.driver_id
        {join}
        {where}
        GROUP BY re.driver_id, re.categorie
        ORDER BY total DESC
        LIMIT 20
    """

    with _connect() as conn, conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def dashboard_stats() -> dict:
    with _connect() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS c FROM reports")
        total_reports = cursor.fetchone()["c"]

        cursor.execute("SELECT COUNT(*) AS c FROM report_entries")
        total_entries = cursor.fetchone()["c"]

        cursor.execute("SELECT COUNT(*) AS c FROM report_entries WHERE categorie IS NOT NULL")
        analyzed_entries = cursor.fetchone()["c"]

        cursor.execute(
            """
            SELECT id, titre, ai_summary FROM reports
            WHERE ai_summary IS NOT NULL AND ai_summary_read_at IS NULL
            ORDER BY updated_at DESC
            LIMIT 5
            """
        )
        unread_summaries = list(cursor.fetchall())

    return {
        "total_reports": total_reports,
        "total_entries": total_entries,
        "analyzed_entries": analyzed_entries,
        "unread_summaries": unread_summaries,
    }
