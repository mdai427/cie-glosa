"""
Extractor de documentos aduanales.
Estrategia dual:
  1. Primero intenta leer el PDF con pdfplumber (texto digital, rápido).
  2. Si el texto es insuficiente (<50 chars útiles), convierte páginas a imágenes
     y usa Claude Vision para OCR completo (PDFs escaneados, imágenes, formularios).
"""

import pdfplumber
import anthropic
import json
import os
import re
import base64
from pathlib import Path
from app.models import TipoDocumento

# ─────────────────────────────────────────────
# CLIENTE CLAUDE
# ─────────────────────────────────────────────
def get_claude_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY no configurada")
    return anthropic.Anthropic(api_key=api_key)


# ─────────────────────────────────────────────
# EXTRACCIÓN DE TEXTO — PDFPLUMBER (texto digital)
# ─────────────────────────────────────────────
def extract_text_pdfplumber(file_path: str) -> str:
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception:
        pass
    return text.strip()


# ─────────────────────────────────────────────
# CONVERSIÓN PDF → IMÁGENES (para OCR Vision)
# ─────────────────────────────────────────────
def pdf_to_images_base64(file_path: str, max_pages: int = 4) -> list[dict]:
    """
    Convierte páginas de un PDF a imágenes base64 para Claude Vision.
    Retorna lista de dicts con {data: base64, media_type: 'image/jpeg'}
    """
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(
            file_path,
            dpi=200,           # suficiente para OCR, no demasiado pesado
            first_page=1,
            last_page=max_pages,
            fmt="jpeg",
            thread_count=2
        )
        images = []
        for page_img in pages:
            import io
            buf = io.BytesIO()
            page_img.save(buf, format="JPEG", quality=85)
            b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
            images.append({"data": b64, "media_type": "image/jpeg"})
        return images
    except Exception as e:
        return []


def image_file_to_base64(file_path: str) -> dict | None:
    """Convierte una imagen (jpg/png) a base64 para Claude Vision."""
    try:
        ext = Path(file_path).suffix.lower()
        media_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
        with open(file_path, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode("utf-8")
        return {"data": b64, "media_type": media_type}
    except Exception:
        return None


# ─────────────────────────────────────────────
# IDENTIFICACIÓN DE TIPO DE DOCUMENTO
# ─────────────────────────────────────────────
def identify_document_type(text: str, filename: str) -> TipoDocumento:
    text_lower = text.lower()
    filename_lower = filename.lower()

    if any(k in filename_lower for k in ["pedimento", "proforma", "borrador"]):
        return TipoDocumento.PEDIMENTO
    if any(k in filename_lower for k in ["factura", "invoice", "commercial"]):
        return TipoDocumento.FACTURA
    if any(k in filename_lower for k in ["3.1.8", "318", "carta", "checklist"]):
        return TipoDocumento.CARTA_318
    if any(k in filename_lower for k in ["cove", "acuse"]):
        return TipoDocumento.COVE
    if any(k in filename_lower for k in ["packing", "empaque"]):
        return TipoDocumento.PACKING_LIST
    if any(k in filename_lower for k in ["bl", "bill", "lading", "guia", "guía", "awb"]):
        return TipoDocumento.BL

    if any(k in text_lower for k in ["pedimento", "val. seg.", "val. fletes", "fracción arancelaria", "clave pedimento", "aduana", "regimen"]):
        return TipoDocumento.PEDIMENTO
    if any(k in text_lower for k in ["invoice", "commercial invoice", "factura comercial", "unit price", "seller", "buyer"]):
        return TipoDocumento.FACTURA
    if any(k in text_lower for k in ["regla 3.1.8", "3.1.8", "checklist", "lista de verificación"]):
        return TipoDocumento.CARTA_318
    if any(k in text_lower for k in ["cove", "acuse de valor", "comprobante de valor"]):
        return TipoDocumento.COVE
    if any(k in text_lower for k in ["packing list", "lista de empaque", "gross weight", "net weight", "cartons"]):
        return TipoDocumento.PACKING_LIST
    if any(k in text_lower for k in ["bill of lading", "b/l", "shipper", "consignee", "notify party", "ocean freight", "master bl"]):
        return TipoDocumento.BL

    return TipoDocumento.DESCONOCIDO


# ─────────────────────────────────────────────
# PROMPTS DE EXTRACCIÓN (texto o imagen)
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """Eres un experto en comercio exterior mexicano con profundo conocimiento de pedimentos,
facturas comerciales, documentos de transporte, COVEs y trámites aduanales.
Tu tarea es extraer información estructurada de documentos aduanales.
Devuelve SIEMPRE únicamente JSON válido, sin markdown, sin explicaciones adicionales.
Si un campo no aparece en el documento, usa null. Nunca inventes datos."""

PROMPTS_JSON = {
    TipoDocumento.PEDIMENTO: """{
  "rfc_importador": "RFC del importador (12 o 13 caracteres)",
  "nombre_importador": "Nombre o razón social del importador",
  "domicilio_importador": "Domicilio completo del importador",
  "nombre_proveedor": "Nombre del proveedor o exportador",
  "domicilio_proveedor": "Domicilio del proveedor",
  "id_fiscal_proveedor": "ID fiscal o tax ID del proveedor extranjero",
  "numero_factura": "Número(s) de factura declarados",
  "fecha_factura": "Fecha de la factura",
  "incoterm": "Clave Incoterm declarado (EXW, FOB, CIF, CFR, etc.)",
  "moneda": "Clave de moneda (USD, EUR, MXN, etc.)",
  "valor_moneda_factura": "Valor en moneda de la factura (Val. Mon. Fact.)",
  "valor_dolares": "Valor en dólares",
  "valor_comercial": "Valor comercial o precio pagado en MXN",
  "valor_aduana": "Valor en aduana en MXN",
  "incrementables_flete": "Monto de flete declarado como incrementable (null si no hay)",
  "incrementables_seguro": "Monto de seguro declarado como incrementable (null si no hay)",
  "incrementables_otros": "Otros incrementables declarados",
  "tipo_cambio": "Tipo de cambio aplicado",
  "numero_cove": "Número de COVE declarado",
  "numero_bl": "Número de BL, guía o documento de transporte",
  "peso_bruto": "Peso bruto total declarado (solo número)",
  "bultos": "Total de bultos declarados (solo número)",
  "partidas": [
    {
      "numero": "número de partida",
      "descripcion": "descripción de mercancía",
      "fraccion": "fracción arancelaria",
      "nico": "NICO si aplica",
      "umc": "unidad de medida comercial",
      "cantidad_umc": "cantidad en UMC",
      "valor_partida": "valor de la partida",
      "precio_unitario": "precio unitario",
      "pais_origen": "país de origen",
      "pais_vendedor": "país vendedor",
      "identificadores": "identificadores y complementos declarados"
    }
  ]
}""",

    TipoDocumento.FACTURA: """{
  "rfc_importador": "RFC del importador/comprador si aparece",
  "nombre_importador": "Nombre del comprador o destinatario",
  "domicilio_importador": "Domicilio del comprador",
  "nombre_proveedor": "Nombre del vendedor o exportador",
  "domicilio_proveedor": "Domicilio del vendedor",
  "id_fiscal_proveedor": "ID fiscal o tax ID del vendedor",
  "numero_factura": "Número de factura o invoice",
  "fecha_factura": "Fecha de emisión",
  "incoterm": "Incoterm declarado",
  "moneda": "Moneda de la factura (USD, EUR, etc.)",
  "valor_total": "Valor TOTAL de la factura incluyendo todos los cargos",
  "subtotal": "Subtotal de mercancías sin cargos adicionales",
  "flete": "Monto de flete si aparece (freight/flete)",
  "seguro": "Monto de seguro si aparece (insurance)",
  "embalaje": "Cargo por embalaje si aparece",
  "otros_cargos": "Otros cargos adicionales",
  "descripcion_general": "Descripción general de las mercancías",
  "lugar_expedicion": "Lugar de expedición del documento",
  "partidas": [
    {
      "numero": "número de línea",
      "descripcion": "descripción completa del producto",
      "cantidad": "cantidad",
      "unidad": "unidad de medida",
      "precio_unitario": "precio por unidad",
      "valor_total_linea": "valor total de la línea",
      "pais_origen": "país de origen si se indica",
      "numero_parte": "número de parte, modelo o SKU"
    }
  ]
}""",

    TipoDocumento.CARTA_318: """{
  "rfc_importador": "RFC del importador",
  "nombre_importador": "Nombre o razón social del importador",
  "domicilio_importador": "Domicilio del importador",
  "nombre_proveedor": "Nombre del proveedor o vendedor",
  "domicilio_proveedor": "Domicilio del proveedor",
  "id_fiscal_proveedor": "ID fiscal del proveedor",
  "numero_factura": "Número de factura referenciada",
  "fecha_factura": "Fecha de la factura",
  "incoterm": "Incoterm acordado",
  "moneda": "Moneda de la operación",
  "valor": "Valor de la operación",
  "lugar_expedicion": "Lugar de expedición",
  "fecha_expedicion": "Fecha de expedición del documento",
  "descripcion_mercancia": "Descripción de la mercancía",
  "cantidad": "Cantidad declarada",
  "unidad": "Unidad de medida",
  "valor_unitario": "Valor unitario",
  "valor_total": "Valor total",
  "tiene_descripcion_comercial": true,
  "flete": "Flete si se menciona",
  "seguro": "Seguro si se menciona",
  "otros_incrementables": "Otros cargos adicionales mencionados"
}""",

    TipoDocumento.COVE: """{
  "numero_cove": "Número de COVE o folio del acuse",
  "rfc_importador": "RFC del importador o comprador",
  "nombre_importador": "Nombre del importador",
  "nombre_proveedor": "Nombre del proveedor o vendedor",
  "numero_factura": "Número de factura vinculada al COVE",
  "fecha": "Fecha del COVE",
  "valor": "Valor declarado en el COVE",
  "moneda": "Moneda del COVE",
  "descripcion": "Descripción de mercancías en el COVE",
  "cantidad": "Cantidad de mercancía",
  "unidad": "Unidad de medida",
  "fecha_factura": "Fecha de la factura vinculada"
}""",

    TipoDocumento.PACKING_LIST: """{
  "peso_bruto_total": "Peso bruto total (solo número sin unidad o con unidad)",
  "peso_neto_total": "Peso neto total si aparece",
  "total_bultos": "Total de bultos, cajas, pallets (solo número)",
  "marcas_numeros": "Marcas y números del embarque",
  "descripcion_general": "Descripción general de las mercancías",
  "numero_factura": "Número de factura referenciada si aparece",
  "partidas": [
    {
      "descripcion": "descripción del ítem",
      "cantidad": "cantidad",
      "unidad": "unidad",
      "peso_bruto": "peso bruto del ítem",
      "bultos": "número de bultos del ítem"
    }
  ]
}""",

    TipoDocumento.BL: """{
  "numero_bl": "Número de B/L, guía aérea o documento de transporte",
  "shipper": "Nombre del embarcador",
  "consignee": "Nombre del consignatario",
  "notify_party": "Notify party si aplica",
  "peso_bruto": "Peso bruto total declarado (solo número o con unidad)",
  "bultos": "Total de bultos o piezas (solo número)",
  "descripcion": "Descripción de las mercancías",
  "puerto_origen": "Puerto o aeropuerto de origen",
  "puerto_destino": "Puerto o aeropuerto de destino",
  "fecha_embarque": "Fecha de embarque",
  "marcas_numeros": "Marcas y números",
  "tipo_transporte": "Marítimo, aéreo o terrestre"
}""",

    TipoDocumento.DESCONOCIDO: """{
  "tipo_detectado": "tipo de documento que crees que es",
  "datos_relevantes": "todos los campos relevantes que encuentres para comercio exterior"
}"""
}


def build_extraction_prompt(doc_type: TipoDocumento) -> str:
    schema = PROMPTS_JSON.get(doc_type, PROMPTS_JSON[TipoDocumento.DESCONOCIDO])
    return f"""Extrae los datos de este documento aduanal y devuelve ÚNICAMENTE este JSON (sin markdown):

{schema}

Instrucciones:
- Si un campo no aparece, usa null
- Para valores numéricos, incluye el número tal como aparece en el documento
- Para RFC: copia exactamente los caracteres, incluyendo mayúsculas
- Para Incoterm: extrae solo la clave (EXW, FOB, CIF, etc.)
- Nunca inventes datos que no estén en el documento"""


# ─────────────────────────────────────────────
# EXTRACCIÓN CON CLAUDE — TEXTO
# ─────────────────────────────────────────────
def extract_with_claude_text(text: str, doc_type: TipoDocumento) -> dict:
    client = get_claude_client()
    text_truncated = text[:14000] if len(text) > 14000 else text

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": build_extraction_prompt(doc_type) + "\n\nDOCUMENTO:\n" + text_truncated
            }]
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'^```\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"JSON inválido: {str(e)}", "_ocr_method": "text"}
    except Exception as e:
        return {"error": str(e), "_ocr_method": "text"}


# ─────────────────────────────────────────────
# EXTRACCIÓN CON CLAUDE VISION — IMÁGENES
# ─────────────────────────────────────────────
def extract_with_claude_vision(images: list[dict], doc_type: TipoDocumento) -> dict:
    """
    Envía imágenes del documento a Claude Vision para OCR + extracción.
    Funciona con PDFs escaneados, formularios impresos, fotos de documentos.
    """
    client = get_claude_client()

    # Construir contenido multimodal: texto + imágenes
    content = []

    # Añadir prompt primero
    content.append({
        "type": "text",
        "text": build_extraction_prompt(doc_type) + "\n\nA continuación las imágenes del documento:"
    })

    # Añadir imágenes (máx 4 páginas para no exceder tokens)
    for img in images[:4]:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["data"]
            }
        })

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}]
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'^```\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        result = json.loads(raw)
        result["_ocr_method"] = "vision"
        return result
    except json.JSONDecodeError as e:
        return {"error": f"JSON inválido en Vision: {str(e)}", "_ocr_method": "vision"}
    except Exception as e:
        return {"error": str(e), "_ocr_method": "vision"}


# ─────────────────────────────────────────────
# PROCESO PRINCIPAL — ESTRATEGIA DUAL
# ─────────────────────────────────────────────
def process_document(file_path: str, filename: str) -> dict:
    """
    Procesa un documento con estrategia dual:
    1. Intenta extraer texto con pdfplumber
    2. Si el texto es insuficiente → OCR con Claude Vision
    """
    ext = Path(file_path).suffix.lower()
    ocr_method = "text"
    text = ""
    campos = {}

    # ── Caso: imagen directa (jpg/png)
    if ext in [".jpg", ".jpeg", ".png"]:
        img = image_file_to_base64(file_path)
        if img:
            doc_type = identify_document_type("", filename)
            campos = extract_with_claude_vision([img], doc_type)
            ocr_method = "vision"
        return {
            "tipo": doc_type.value if 'doc_type' in dir() else TipoDocumento.DESCONOCIDO.value,
            "nombre_archivo": filename,
            "ocr_method": ocr_method,
            "datos": campos
        }

    # ── Caso: archivo de texto plano
    if ext in [".txt", ".csv"]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            text = ""
        doc_type = identify_document_type(text, filename)
        campos = extract_with_claude_text(text, doc_type)
        return {
            "tipo": doc_type.value,
            "nombre_archivo": filename,
            "ocr_method": "text",
            "datos": campos
        }

    # ── Caso: PDF (estrategia dual)
    if ext == ".pdf":
        # Paso 1: intentar extracción de texto digital
        text = extract_text_pdfplumber(file_path)
        texto_util = len(text.replace(" ", "").replace("\n", ""))

        doc_type = identify_document_type(text, filename)

        if texto_util >= 100:
            # PDF tiene texto suficiente → extracción rápida por texto
            campos = extract_with_claude_text(text, doc_type)
            ocr_method = "text"
        else:
            # PDF escaneado o con poco texto → Claude Vision
            images = pdf_to_images_base64(file_path, max_pages=4)
            if images:
                # Re-identificar tipo con visión si no se pudo por texto
                if doc_type == TipoDocumento.DESCONOCIDO:
                    doc_type = identify_document_type("", filename)
                campos = extract_with_claude_vision(images, doc_type)
                ocr_method = "vision"
            else:
                # Fallback: intentar texto aunque sea poco
                campos = extract_with_claude_text(text or "[PDF sin texto extraíble]", doc_type)
                ocr_method = "text_fallback"

        return {
            "tipo": doc_type.value,
            "nombre_archivo": filename,
            "ocr_method": ocr_method,
            "texto_chars": texto_util,
            "datos": campos
        }

    # ── Caso: cualquier otro archivo
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        text = ""
    doc_type = identify_document_type(text, filename)
    campos = extract_with_claude_text(text or "[Archivo sin contenido legible]", doc_type)
    return {
        "tipo": doc_type.value,
        "nombre_archivo": filename,
        "ocr_method": "text",
        "datos": campos
    }
