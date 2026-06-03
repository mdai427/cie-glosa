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
from typing import List, Optional

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
                    seq        SERIAL,
                    id         TEXT PRIMARY KEY,
                    referencia TEXT,
                    cliente    TEXT,
                    fecha_revision TEXT,
                    semaforo   TEXT,
                    resultado_json TEXT,
                    estatus    TEXT DEFAULT 'completado'
                )
            """)
            # Agregar columnas nuevas si la tabla ya existe (migraciones seguras)
            for col, defn in [
                ("seq",      "SERIAL"),
                ("semaforo", "TEXT"),
            ]:
                try:
                    if col == "seq":
                        await conn.execute(
                            "ALTER TABLE revisiones ADD COLUMN IF NOT EXISTS seq SERIAL"
                        )
                    else:
                        await conn.execute(
                            f"ALTER TABLE revisiones ADD COLUMN IF NOT EXISTS {col} {defn}"
                        )
                except Exception:
                    pass

            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rev_seq      ON revisiones(seq DESC)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rev_cliente  ON revisiones(cliente)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rev_semaforo ON revisiones(semaforo)"
            )
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    nombre TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    rol TEXT NOT NULL DEFAULT 'ejecutivo',
                    activo BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TEXT NOT NULL
                )
            """)
        logger.info("DB PostgreSQL inicializada correctamente")
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS revisiones (
                    id TEXT PRIMARY KEY,
                    referencia TEXT,
                    cliente TEXT,
                    fecha_revision TEXT,
                    semaforo TEXT,
                    resultado_json TEXT,
                    estatus TEXT DEFAULT 'completado'
                )
            """)
            # Agregar columna semaforo si no existe
            try:
                await db.execute("ALTER TABLE revisiones ADD COLUMN semaforo TEXT")
            except Exception:
                pass
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_rev_cliente  ON revisiones(cliente)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_rev_semaforo ON revisiones(semaforo)"
            )
            await db.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    nombre TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    rol TEXT NOT NULL DEFAULT 'ejecutivo',
                    activo INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            """)
            await db.commit()
        logger.info("DB SQLite inicializada correctamente")


async def close_db():
    """Cerrar pool al apagar. Llamar en shutdown."""
    global _pg_pool
    if USE_PG and _pg_pool:
        await _pg_pool.close()
        _pg_pool = None


# ── Revisiones ─────────────────────────────────────────────────────────────────

async def insertar_revision(
    revision_id: str,
    referencia: str,
    cliente: str,
    fecha: str,
    resultado_json: str,
    estatus: str = "completado",
    semaforo: str = "",
):
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO revisiones (id, referencia, cliente, fecha_revision, semaforo, resultado_json, estatus) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7)",
                revision_id, referencia, cliente, fecha, semaforo, resultado_json, estatus
            )
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                "INSERT INTO revisiones (id, referencia, cliente, fecha_revision, semaforo, resultado_json, estatus) "
                "VALUES (?,?,?,?,?,?,?)",
                (revision_id, referencia, cliente, fecha, semaforo, resultado_json, estatus)
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
                "SELECT id, referencia, cliente, fecha_revision, semaforo, estatus "
                "FROM revisiones ORDER BY seq DESC NULLS LAST LIMIT 100"
            )
            return [
                {"id": r["id"], "referencia": r["referencia"], "cliente": r["cliente"],
                 "fecha": r["fecha_revision"], "semaforo": r["semaforo"] or "",
                 "estatus": r["estatus"]}
                for r in rows
            ]
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute(
                "SELECT id, referencia, cliente, fecha_revision, semaforo, estatus "
                "FROM revisiones ORDER BY rowid DESC LIMIT 100"
            ) as cur:
                rows = await cur.fetchall()
                return [
                    {"id": r[0], "referencia": r[1], "cliente": r[2],
                     "fecha": r[3], "semaforo": r[4] or "", "estatus": r[5]}
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
    """Solo devuelve los JSON necesarios para el dashboard (últimas 200)."""
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT resultado_json FROM revisiones ORDER BY seq DESC NULLS LAST LIMIT 200"
            )
            return [r["resultado_json"] for r in rows]
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute(
                "SELECT resultado_json FROM revisiones ORDER BY rowid DESC LIMIT 200"
            ) as cur:
                rows = await cur.fetchall()
                return [r[0] for r in rows]


async def conteo_por_semaforo() -> dict:
    """Cuenta revisiones agrupadas por semáforo — sin cargar JSONs."""
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT semaforo, COUNT(*) as cnt FROM revisiones "
                "WHERE semaforo IS NOT NULL AND semaforo != '' "
                "GROUP BY semaforo"
            )
            return {r["semaforo"]: r["cnt"] for r in rows}
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute(
                "SELECT semaforo, COUNT(*) as cnt FROM revisiones "
                "WHERE semaforo IS NOT NULL AND semaforo != '' "
                "GROUP BY semaforo"
            ) as cur:
                rows = await cur.fetchall()
                return {r[0]: r[1] for r in rows}


async def contar_revisiones() -> int:
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM revisiones")
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute("SELECT COUNT(*) FROM revisiones") as cur:
                row = await cur.fetchone()
                return row[0]


# ── Usuarios ───────────────────────────────────────────────────────────────────

async def crear_usuario(email: str, nombre: str, password_hash: str, rol: str, created_at: str) -> int:
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO usuarios (email, nombre, password_hash, rol, activo, created_at) "
                "VALUES ($1,$2,$3,$4,TRUE,$5) RETURNING id",
                email, nombre, password_hash, rol, created_at
            )
            return row["id"]
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute(
                "INSERT INTO usuarios (email, nombre, password_hash, rol, activo, created_at) "
                "VALUES (?,?,?,?,1,?)",
                (email, nombre, password_hash, rol, created_at)
            ) as cur:
                await db.commit()
                return cur.lastrowid


async def obtener_usuario_por_email(email: str) -> Optional[dict]:
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, email, nombre, password_hash, rol, activo FROM usuarios WHERE email = $1",
                email
            )
            if not row:
                return None
            return dict(row)
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, email, nombre, password_hash, rol, activo FROM usuarios WHERE email = ?",
                (email,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None


async def listar_usuarios() -> List[dict]:
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, email, nombre, rol, activo, created_at FROM usuarios ORDER BY id DESC"
            )
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, email, nombre, rol, activo, created_at FROM usuarios ORDER BY id DESC"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]


async def toggle_usuario_activo(user_id: int, activo: bool):
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE usuarios SET activo = $1 WHERE id = $2", activo, user_id
            )
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                "UPDATE usuarios SET activo = ? WHERE id = ?", (1 if activo else 0, user_id)
            )
            await db.commit()


async def actualizar_password(user_id: int, password_hash: str):
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            await conn.execute(
                "UPDATE usuarios SET password_hash = $1 WHERE id = $2", password_hash, user_id
            )
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                "UPDATE usuarios SET password_hash = ? WHERE id = ?", (password_hash, user_id)
            )
            await db.commit()


async def email_existe(email: str) -> bool:
    if USE_PG:
        async with _pg_pool.acquire() as conn:
            val = await conn.fetchval("SELECT COUNT(*) FROM usuarios WHERE email = $1", email)
            return val > 0
    else:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM usuarios WHERE email = ?", (email,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] > 0
