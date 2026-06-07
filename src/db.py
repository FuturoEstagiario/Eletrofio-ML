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
