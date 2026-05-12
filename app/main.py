import os
import uuid
import json
import aiosqlite
import aiofiles
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.extractor import process_document
from app.validator import ejecutar_validaciones
from app.models import ResultadoGlosa, SemaforoColor

load_dotenv()

app = FastAPI(
    title="GLOSA - Sistema de Glosa Preventiva Aduanal",
    description="Glosa automática de proforma de pedimento",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "glosa.db"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)


async def init_db():
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
        await db.commit()


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/health")
async def health():
    return {"status": "ok"}


# Pre-leer el HTML una sola vez al inicio (no en cada request)
_HTML_CACHE: str = ""

@app.on_event("startup")
async def cargar_html():
    global _HTML_CACHE
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        async with aiofiles.open(str(index_path), "r", encoding="utf-8") as f:
            _HTML_CACHE = await f.read()


@app.get("/", response_class=HTMLResponse)
async def root():
    if _HTML_CACHE:
        return HTMLResponse(_HTML_CACHE)
    return HTMLResponse("<h1>GLOSA - Sistema iniciando...</h1>")


@app.post("/api/revision")
async def crear_revision(
    files: List[UploadFile] = File(...),
    referencia: Optional[str] = Form(None),
    cliente: Optional[str] = Form(None)
):
    """
    Recibe los documentos, los procesa con IA y ejecuta las validaciones.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No se recibieron archivos")

    revision_id = str(uuid.uuid4())[:8].upper()
    ref = referencia or f"REV-{revision_id}"
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Guardar archivos y procesarlos
    documentos_extraidos = {}
    documentos_cargados = []
    revision_dir = UPLOAD_DIR / revision_id
    revision_dir.mkdir(exist_ok=True)

    for file in files:
        if not file.filename:
            continue
        file_path = revision_dir / file.filename
        content = await file.read()
        async with aiofiles.open(str(file_path), "wb") as f:
            await f.write(content)

        try:
            doc_procesado = process_document(str(file_path), file.filename)
            tipo = doc_procesado["tipo"]
            documentos_extraidos[tipo] = doc_procesado["datos"]
            documentos_cargados.append(f"{file.filename} ({tipo})")
        except Exception as e:
            documentos_cargados.append(f"{file.filename} (error: {str(e)[:50]})")

    # Ejecutar validaciones
    try:
        hallazgos, semaforo, recomendacion, criticos, altos, medios, bajos = ejecutar_validaciones(documentos_extraidos)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en validaciones: {str(e)}")

    # Construir resultado
    resultado = ResultadoGlosa(
        id=revision_id,
        referencia=ref,
        fecha_revision=fecha,
        documentos_cargados=documentos_cargados,
        hallazgos=hallazgos,
        semaforo=semaforo,
        recomendacion=recomendacion,
        total_criticos=criticos,
        total_altos=altos,
        total_medios=medios,
        total_bajos=bajos,
        estatus="completado"
    )

    # Guardar en base de datos
    try:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute(
                "INSERT INTO revisiones VALUES (?, ?, ?, ?, ?, ?)",
                (revision_id, ref, cliente or "", fecha, resultado.model_dump_json(), "completado")
            )
            await db.commit()
    except Exception:
        pass  # No crítico si falla el guardado

    return resultado


@app.get("/api/revision/{revision_id}")
async def obtener_revision(revision_id: str):
    """Obtiene el resultado de una revisión por ID."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(
            "SELECT resultado_json FROM revisiones WHERE id = ?",
            (revision_id.upper(),)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Revisión no encontrada")
            return JSONResponse(content=json.loads(row[0]))


@app.get("/api/revisiones")
async def listar_revisiones():
    """Lista todas las revisiones guardadas."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        async with db.execute(
            "SELECT id, referencia, cliente, fecha_revision, estatus FROM revisiones ORDER BY rowid DESC LIMIT 50"
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "referencia": r[1], "cliente": r[2], "fecha": r[3], "estatus": r[4]}
                for r in rows
            ]


@app.delete("/api/revision/{revision_id}")
async def eliminar_revision(revision_id: str):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM revisiones WHERE id = ?", (revision_id.upper(),))
        await db.commit()
    return {"message": "Revisión eliminada"}


# Montar archivos estáticos
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
