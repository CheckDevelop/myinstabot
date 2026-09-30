import os
import threading
from copy import deepcopy

from psycopg_pool import ConnectionPool
from psycopg.types.json import Jsonb

_POOL = None
_POOL_LOCK = threading.Lock()


def _get_pool():
    global _POOL

    if _POOL is not None:
        return _POOL

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")

    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ConnectionPool(
                conninfo=database_url,
                min_size=1,
                max_size=4,
                timeout=15,
                open=True,
            )

    return _POOL


def init_db():
    pool = _get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_documents (
                name TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.commit()


def load_document(name, default=None):
    pool = _get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT data FROM bot_documents WHERE name = %s",
            (name,),
        ).fetchone()

    if row is None:
        return deepcopy(default)

    return row[0]


def save_document(name, data):
    pool = _get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO bot_documents (name, data, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (name)
            DO UPDATE SET
                data = EXCLUDED.data,
                updated_at = NOW()
            """,
            (name, Jsonb(data)),
        )
        conn.commit()
