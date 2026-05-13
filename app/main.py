import os
import uuid
import json
import logging
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from collections import Counter

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

from app.extractor import process_document
from app.validator import ejecutar_validaciones
from app.models import ResultadoGlosa, SemaforoColor
from app.security import verify_api_key, validar_archivo, sanitizar_nombre, MAX_FILES_PER_REVISION
from app.contribuciones import calcular_contribuciones
from app import db as database

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Rate limiting ──────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="GLOSA - Sistema de Glosa Preventiva Aduanal",
    description="Glosa automática de proforma de pedimento",
    version="2.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ───────────────────────────────────────────────────────────────────
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "https://web-production-699f8.up.railway.app"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)

_HTML_CACHE: str = ""


@app.on_event("startup")
async def startup():
    global _HTML_CACHE
    try:
        await database.init_db()
    except Exception as e:
        logger.error(f"DB init error: {e}")

    try:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            async with aiofiles.open(str(index_path), "r", encoding="utf-8") as f:
                _HTML_CACHE = await f.read()
    except Exception as e:
        logger.error(f"HTML cache error: {e}")


@app.on_event("shutdown")
async def shutdown():
    await database.close_db()


# ── Endpoints públicos (sin auth) ──────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def root():
    if _HTML_CACHE:
        return HTMLResponse(_HTML_CACHE)
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        with open(str(index_path), "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>GLOSA iniciando...</h1>")


# ── Endpoints protegidos ───────────────────────────────────────────────────

@app.post("/api/revision")
@limiter.limit("10/hour")
async def crear_revision(
    request: Request,
    files: List[UploadFile] = File(...),
    referencia: Optional[str] = Form(None),
    cliente: Optional[str] = Form(None),
    _key: str = Depends(verify_api_key),
):
    if not files:
        raise HTTPException(status_code=400, detail="No se recibieron archivos")

    if len(files) > MAX_FILES_PER_REVISION:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo {MAX_FILES_PER_REVISION} archivos por revisión."
        )

    revision_id = str(uuid.uuid4())[:8].upper()
    ref = referencia or f"REV-{revision_id}"
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    documentos_extraidos = {}
    documentos_cargados = []
    revision_dir = UPLOAD_DIR / revision_id
    revision_dir.mkdir(exist_ok=True)

    for file in files:
        if not file.filename:
            continue

        try:
            contenido = await validar_archivo(file)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        nombre_seguro = sanitizar_nombre(file.filename)
        file_path = revision_dir / nombre_seguro

        async with aiofiles.open(str(file_path), "wb") as f:
            await f.write(contenido)

        try:
            doc_procesado = process_document(str(file_path), nombre_seguro)
            tipo = doc_procesado["tipo"]
            datos = doc_procesado["datos"]
            if "error" not in datos:
                documentos_extraidos[tipo] = datos
            else:
                logger.error(f"Extraccion error en {nombre_seguro}: {datos.get('error','')[:200]}")
            documentos_cargados.append(f"{nombre_seguro} ({tipo})")
        except Exception as e:
            logger.error(f"Error procesando {nombre_seguro}: {e}")
            documentos_cargados.append(f"{nombre_seguro} (error: {str(e)[:50]})")

    try:
        hallazgos, semaforo, recomendacion, criticos, altos, medios, bajos = ejecutar_validaciones(documentos_extraidos)
    except Exception as e:
        logger.error(f"Error en validaciones revision {revision_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error en validaciones: {str(e)}")

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

    try:
        await database.insertar_revision(
            revision_id, ref, cliente or "", fecha,
            resultado.model_dump_json(), "completado"
        )
    except Exception as e:
        logger.error(f"Error guardando revision {revision_id} en DB: {e}")

    return resultado


@app.get("/api/revision/{revision_id}")
@limiter.limit("60/minute")
async def obtener_revision(
    request: Request,
    revision_id: str,
    _key: str = Depends(verify_api_key),
):
    rjson = await database.obtener_revision_json(revision_id.upper())
    if not rjson:
        raise HTTPException(status_code=404, detail="Revisión no encontrada")
    return JSONResponse(content=json.loads(rjson))


@app.get("/api/revisiones")
@limiter.limit("60/minute")
async def listar_revisiones(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    return await database.listar_revisiones()


@app.delete("/api/revision/{revision_id}")
@limiter.limit("60/minute")
async def eliminar_revision(
    request: Request,
    revision_id: str,
    _key: str = Depends(verify_api_key),
):
    await database.eliminar_revision(revision_id.upper())
    return {"message": "Revisión eliminada"}


@app.get("/api/dashboard")
@limiter.limit("60/minute")
async def dashboard(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Métricas agregadas de uso del sistema."""
    hace_7_dias = (datetime.now() - timedelta(days=7)).strftime("%d/%m/%Y")

    total = await database.contar_revisiones()
    all_json = await database.obtener_todas_revisiones_json()

    por_semaforo = {"verde": 0, "amarillo": 0, "rojo": 0, "negro": 0}
    campos_counter: Counter = Counter()
    ultimos_7 = 0
    total_criticos = 0

    for rjson in all_json:
        try:
            r = json.loads(rjson)
            sem = r.get("semaforo", "")
            if sem in por_semaforo:
                por_semaforo[sem] += 1
            for h in r.get("hallazgos", []):
                campos_counter[h.get("campo", "")] += 1
            total_criticos += r.get("total_criticos", 0)
            fecha_str = r.get("fecha_revision", "")
            if fecha_str and fecha_str[:10] >= hace_7_dias:
                ultimos_7 += 1
        except Exception:
            pass

    top_campos = [
        {"campo": campo, "count": cnt}
        for campo, cnt in campos_counter.most_common(10)
    ]

    return {
        "total_revisiones": total,
        "por_semaforo": por_semaforo,
        "top_campos_hallazgos": top_campos,
        "revisiones_ultimos_7_dias": ultimos_7,
        "total_criticos": total_criticos,
    }


@app.get("/api/revision/{revision_id}/contribuciones")
@limiter.limit("60/minute")
async def calcular_contrib_revision(
    request: Request,
    revision_id: str,
    _key: str = Depends(verify_api_key),
):
    """Retorna el cálculo detallado de contribuciones estimadas para una revisión guardada."""
    rjson = await database.obtener_revision_json(revision_id.upper())
    if not rjson:
        raise HTTPException(status_code=404, detail="Revisión no encontrada")
    resultado = json.loads(rjson)

    hallazgos = resultado.get("hallazgos", [])
    contrib = next(
        (h for h in hallazgos if h.get("campo") == "Contribuciones Estimadas de Importación"),
        None
    )
    regulaciones = [
        h for h in hallazgos
        if "Regulaciones" in h.get("campo", "")
        or "Precio Estimado SAT" in h.get("campo", "")
        or "TLC" in h.get("campo", "")
    ]

    return {
        "revision_id": revision_id.upper(),
        "contribuciones": contrib,
        "hallazgos_regulaciones": regulaciones,
    }


# Montar archivos estáticos (al final para no interceptar rutas API)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
