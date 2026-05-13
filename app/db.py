"""
Capa de acceso a base de datos.
- Si DATABASE_URL está definido (Railway PostgreSQL) → usa asyncpg
- Si no → usa aiosqlite (SQLite local)
"""
import os
import json
import logging
import aiosqlite
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")

# ── Detectar modo ──────────────────────────────────────────────────────────────
USE_PG = bool(DATABASE_URL)

if USE_PG:
    try:
        import asyncpg  # type: ignore
        logger.info("DB: modo PostgreSQL (asyncpg)")
    except ImportError:
        logger.warning("asyncpg no instalado — recayendo en SQLite")
        USE_PG = False

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "glosa.db"

# ── Pool global de Postgres ────────────────────────────────────────────────────
_pg_pool = None


async def init_db():
    """Crear tablas si no existen. Llamar en startup."""
    global _pg_pool
    if USE_PG:
        _pg_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        async with _pg_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS revisiones (
                    id TEXT PRIMARY KEY,
                    referencia TEXT,
                    cliente TEXT,
                    fecha_revision TEXT,
                    resultado_json TEXT,
                    estatus TEXT DEFAULT 'completado'
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_revisiones_cliente ON revisiones(cliente)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_revisiones_fecha ON revisiones(fecha_revision)"
            )
        logger.info("DB PostgreSQL inicializada correctamente")
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS revisiones (
                    id TEXT PRIMARY KEY,
                    referencia TEXT,
                    cliente TEXT,
                    fecha_revision TEXT,
                    resultado_json TEXT,
                    estatus TEXT DEFAULT 'completado'
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_revisiones_cliente ON revisiones(cliente)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_revisiones_fecha ON revisiones(fecha_revision)"
            )
            await db.commit()
        logger.info("DB SQLite inicializada correctamente")


async def close_db():
    """Cerrar pool al apagar. Llamar en shutdown."""
    global _pg_pool
    if USE_PG and _pg_pool:
        await _pg_pool.close()
        _pg_pool = None


# ── Operaciones ────────────────────────────────────────────────────────────────

async def insertar_revision(
    revision_id: str,
    referencia: str,
    cliente: str,
    fecha: str,
    resultado_json: str,
    estatus: str = "completado",
):
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO revisiones VALUES ($1,$2,$3,$4,$5,$6)",
                revision_id, referencia, cliente, fecha, resultado_json, estatus
            )
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                "INSERT INTO revisiones VALUES (?,?,?,?,?,?)",
                (revision_id, referencia, cliente, fecha, resultado_json, estatus)
            )
            await db.commit()


async def obtener_revision_json(revision_id: str) -> Optional[str]:
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT resultado_json FROM revisiones WHERE id = $1", revision_id
            )
            return row["resultado_json"] if row else None
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute(
                "SELECT resultado_json FROM revisiones WHERE id = ?", (revision_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None


async def listar_revisiones() -> List[dict]:
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, referencia, cliente, fecha_revision, estatus "
                "FROM revisiones ORDER BY id DESC LIMIT 50"
            )
            return [
                {"id": r["id"], "referencia": r["referencia"], "cliente": r["cliente"],
                 "fecha": r["fecha_revision"], "estatus": r["estatus"]}
                for r in rows
            ]
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute(
                "SELECT id, referencia, cliente, fecha_revision, estatus "
                "FROM revisiones ORDER BY rowid DESC LIMIT 50"
            ) as cur:
                rows = await cur.fetchall()
                return [
                    {"id": r[0], "referencia": r[1], "cliente": r[2], "fecha": r[3], "estatus": r[4]}
                    for r in rows
                ]


async def eliminar_revision(revision_id: str):
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM revisiones WHERE id = $1", revision_id)
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("DELETE FROM revisiones WHERE id = ?", (revision_id,))
            await db.commit()


async def obtener_todas_revisiones_json() -> List[str]:
    """Para el dashboard: retorna todos los resultado_json."""
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT resultado_json FROM revisiones")
            return [r["resultado_json"] for r in rows]
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute("SELECT resultado_json FROM revisiones") as cur:
                rows = await cur.fetchall()
                return [r[0] for r in rows]


async def contar_revisiones() -> int:
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM revisiones")
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute("SELECT COUNT(*) FROM revisiones") as cur:
                row = await cur.fetchone()
                return row[0]
