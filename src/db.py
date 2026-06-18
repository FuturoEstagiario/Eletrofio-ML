import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def ping() -> bool:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False


def init_tables() -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chamados (
                        id               SERIAL PRIMARY KEY,
                        dispositivo_id   INTEGER,
                        loja_id          INTEGER,
                        loja_nome        TEXT,
                        tag              TEXT,
                        motivo           TEXT,
                        tecnico_presencial BOOLEAN DEFAULT FALSE,
                        status           TEXT DEFAULT 'aberto',
                        criado_em        TIMESTAMP DEFAULT NOW(),
                        resolvido_em     TIMESTAMP
                    )
                """)
    finally:
        conn.close()


def inserir_chamado(
    dispositivo_id: int,
    loja_id: int,
    loja_nome: str,
    tag: str,
    motivo: str,
    tecnico_presencial: bool = False,
) -> int:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chamados
                        (dispositivo_id, loja_id, loja_nome, tag, motivo, tecnico_presencial)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (dispositivo_id, loja_id, loja_nome, tag, motivo, tecnico_presencial),
                )
                return cur.fetchone()[0]
    finally:
        conn.close()


def listar_chamados(limit: int = 100) -> list:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, dispositivo_id, loja_id, loja_nome, tag, motivo,
                       tecnico_presencial, status, criado_em, resolvido_em
                FROM chamados
                ORDER BY criado_em DESC
                LIMIT %s
                """,
                (limit,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def resolver_chamado(chamado_id: int) -> bool:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE chamados SET status='fechado', resolvido_em=NOW() WHERE id=%s AND status='aberto'",
                    (chamado_id,),
                )
                return cur.rowcount > 0
    finally:
        conn.close()


# ── scores_historico ─────────────────────────────────────────────────────────

def init_scores_historico() -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scores_historico (
                        id             SERIAL PRIMARY KEY,
                        dispositivo_id INTEGER NOT NULL,
                        risk_score     FLOAT,
                        anomaly        BOOLEAN,
                        ts             TIMESTAMP DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_scores_did_ts
                    ON scores_historico (dispositivo_id, ts DESC)
                """)
    finally:
        conn.close()


def inserir_score(dispositivo_id: int, risk_score: float | None, anomaly: bool | None) -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO scores_historico (dispositivo_id, risk_score, anomaly) VALUES (%s, %s, %s)",
                    (dispositivo_id, risk_score, anomaly),
                )
    finally:
        conn.close()


def listar_scores_device(dispositivo_id: int, limit: int = 50) -> list:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, dispositivo_id, risk_score, anomaly, ts
                FROM scores_historico
                WHERE dispositivo_id = %s
                ORDER BY ts DESC
                LIMIT %s
                """,
                (dispositivo_id, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def stats_reincidencia() -> list:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    dispositivo_id,
                    MAX(loja_nome)  AS loja_nome,
                    MAX(tag)        AS tag,
                    COUNT(*)        AS total_chamados,
                    COUNT(*) FILTER (WHERE status = 'fechado') AS chamados_resolvidos,
                    COUNT(*) FILTER (WHERE status = 'aberto')  AS chamados_abertos,
                    ROUND(
                        AVG(EXTRACT(EPOCH FROM (resolvido_em - criado_em)) / 3600.0)::numeric, 1
                    ) AS mttr_horas,
                    MIN(criado_em)  AS primeiro_chamado,
                    MAX(criado_em)  AS ultimo_chamado
                FROM chamados
                GROUP BY dispositivo_id
                ORDER BY total_chamados DESC
                LIMIT 50
            """)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
