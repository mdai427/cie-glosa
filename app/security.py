"""
Seguridad: validación de API key, archivos y constantes de límites.
"""
import os
import re
import secrets
import logging
from fastapi import Header, HTTPException, UploadFile

logger = logging.getLogger(__name__)

MAX_FILES_PER_REVISION = 10
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# Magic bytes por tipo real de archivo
MAGIC_BYTES = {
    b"%PDF-":     "pdf",
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG":   "png",
}

EXTENSIONES_VALIDAS = {
    "pdf": [".pdf"],
    "jpg": [".jpg", ".jpeg"],
    "png": [".png"],
}

# Caracteres seguros para nombre de archivo
_SAFE_FILENAME = re.compile(r"[^\w\-. ]")


def verify_api_key(x_api_key: str = Header(default=None)) -> str:
    """
    Valida la API key del header X-Api-Key contra la variable de entorno GLOSA_API_KEY.
    Si GLOSA_API_KEY no está configurada, permite el acceso (modo desarrollo).
    """
    expected = os.getenv("GLOSA_API_KEY", "")
    if not expected:
        # Sin clave configurada → modo dev, no bloquear
        return ""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-Api-Key header requerido")
    if not secrets.compare_digest(expected, x_api_key):
        raise HTTPException(status_code=403, detail="API key inválida")
    return x_api_key


def _detectar_tipo_real(header: bytes) -> str | None:
    """Retorna el tipo real del archivo según sus magic bytes."""
    for magic, tipo in MAGIC_BYTES.items():
        if header.startswith(magic):
            return tipo
    return None


def sanitizar_nombre(filename: str) -> str:
    """Elimina path traversal y caracteres peligrosos del nombre de archivo."""
    # Tomar solo el nombre base (sin directorios)
    nombre = os.path.basename(filename)
    # Reemplazar caracteres no seguros
    nombre = _SAFE_FILENAME.sub("_", nombre)
    # Limitar longitud
    if len(nombre) > 200:
        ext = os.path.splitext(nombre)[1]
        nombre = nombre[:196] + ext
    return nombre or "archivo"


async def validar_archivo(file: UploadFile) -> bytes:
    """
    Lee el archivo, valida tamaño, tipo real por magic bytes y extensión.
    Retorna el contenido en bytes si pasa todas las validaciones.
    Lanza HTTPException en caso de error.
    """
    contenido = await file.read()

    # 1. Tamaño máximo
    if len(contenido) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo '{file.filename}' supera el límite de 20 MB."
        )

    # 2. Tipo real por magic bytes
    tipo_real = _detectar_tipo_real(contenido[:8])

    # Permitir .txt (no tiene magic bytes estándar pero es válido para pedimentos)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext == ".txt":
        return contenido

    if tipo_real is None:
        raise HTTPException(
            status_code=415,
            detail=f"Archivo '{file.filename}' no es un tipo soportado (PDF, JPG, PNG)."
        )

    # 3. Extensión coherente con tipo real
    extensiones_esperadas = EXTENSIONES_VALIDAS.get(tipo_real, [])
    if ext not in extensiones_esperadas:
        raise HTTPException(
            status_code=415,
            detail=f"Extensión '{ext}' no coincide con el contenido real del archivo (tipo detectado: {tipo_real})."
        )

    return contenido
