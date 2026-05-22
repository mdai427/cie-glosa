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
import time
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
SYSTEM_PROMPT = """Eres un sistema de extracción de datos de documentos aduanales mexicanos.
Tu única tarea es COPIAR literalmente los valores que aparecen en el documento, sin corregir, interpretar ni normalizar.

REGLAS CRÍTICAS DE EXTRACCIÓN:
- Copia los caracteres EXACTAMENTE como aparecen: si ves 'O' copia 'O', si ves '0' copia '0', NUNCA los intercambies
- Para números de referencia (BL, factura, guía, COVE): transcribe caracter por caracter, sin cambios
- Para nombres y razones sociales: copia el texto literal del documento
- Para fechas: copia el formato exacto que aparece (no lo conviertas a otro formato)
- Si un campo no aparece en el documento usa null
- NUNCA inventes, corrijas, ni "mejores" los datos aunque parezcan erróneos
- Devuelve ÚNICAMENTE JSON válido, sin markdown, sin explicaciones"""

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
  "numero_bl": "Número de BL, guía aérea, AWB o documento de transporte (campo 'NO. GUIA/ORDEN EMBARQUE/ID' en el pedimento)",
  "peso_bruto": "Peso bruto total declarado (solo número)",
  "bultos": "Total de bultos declarados (solo número)",
  "partidas": [
    {
      "numero": "número de partida (001, 002, etc.)",
      "descripcion": "descripción de mercancía",
      "fraccion": "fracción arancelaria (10 dígitos)",
      "nico": "NICO si aplica",
      "umc": "clave de unidad de medida COMERCIAL (UMC) — es una abreviatura como M, PZA, KG, MT, LT, PAR, BTO, ROL. NO confundir con la cantidad ni con la UMT (unidad de tarifa)",
      "cantidad_umc": "cantidad numérica en UMC (solo el número)",
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
  "numero_bl": "Número de B/L, guía aérea o AWB referenciado en este documento (null si no aparece)",
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

INSTRUCCIONES CRÍTICAS:
- Copia el valor EXACTAMENTE como aparece en el documento, caracter por caracter
- Para números de referencia (BL, factura, guía, COVE, RFC, ID fiscal): transcripción literal sin correcciones
  * Si ves la letra O, escribe O. Si ves el dígito 0, escribe 0. NUNCA los intercambies.
  * Si ves I (i mayúscula) y 1 (uno), escríbelos tal cual sin cambios.
- Para valores monetarios/numéricos: incluye el número tal como aparece (con comas, puntos, etc.)
- Para Incoterm: extrae solo la clave (EXW, FOB, CIF, etc.)
- Si un campo no aparece en el documento: null
- NUNCA inventes, normalices ni corrijas datos aunque parezcan erróneos o inusuales"""


# ─────────────────────────────────────────────
# LLAMADA A CLAUDE CON RETRY AUTOMÁTICO
# ─────────────────────────────────────────────
def _llamar_claude(client, model: str, max_tokens: int, system: str, messages: list, retries: int = 3) -> tuple[str, int]:
    """
    Llama a Claude con reintentos automáticos si la API está saturada (error 529).
    Retorna (texto_respuesta, tokens_usados).
    """
    last_error = None
    for intento in range(retries):
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages
            )
            tokens = (msg.usage.input_tokens or 0) + (msg.usage.output_tokens or 0)
            return msg.content[0].text.strip(), tokens
        except anthropic.APIStatusError as e:
            last_error = e
            if e.status_code == 529 or "overloaded" in str(e).lower():
                espera = 10 * (intento + 1)  # 10s, 20s, 30s
                time.sleep(espera)
                continue
            raise
        except Exception as e:
            last_error = e
            if intento < retries - 1:
                time.sleep(5)
                continue
            raise
    raise last_error


def _parsear_json(raw: str) -> dict:
    """Parsea JSON de respuesta de Claude, tolerando markdown y trailing commas."""
    # Quitar bloques markdown
    raw = re.sub(r'^```json\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'^```\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
    raw = raw.strip()

    # Intento 1: parsear directamente
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Intento 2: eliminar trailing commas (,} y ,])
    cleaned = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Intento 3: JSON truncado — cerrar estructuras abiertas
    fixed = _cerrar_json_truncado(cleaned)
    if fixed:
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # Forzar error original para el mensaje de excepción
    return json.loads(raw)


def _cerrar_json_truncado(raw: str) -> str:
    """
    Intenta cerrar un JSON truncado contando llaves y corchetes abiertos.
    Solo funciona si el truncado ocurrió dentro de un objeto/array válido.
    """
    # Eliminar el último par incompleto (clave sin valor, o valor a medias)
    # Truncar hasta la última coma o abre-llave válida
    truncado = raw.rstrip()

    # Quitar el último fragmento incompleto (sin cierre de string ni valor)
    truncado = re.sub(r',?\s*"[^"]*$', '', truncado)  # clave sin valor
    truncado = re.sub(r',?\s*"[^"]*":\s*[^,{\[\]"}]*$', '', truncado)  # valor incompleto

    # Contar estructuras abiertas
    stack = []
    in_string = False
    escape = False
    for ch in truncado:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in '{[':
                stack.append(ch)
            elif ch in '}]':
                if stack:
                    stack.pop()

    if not stack:
        return truncado

    # Cerrar en orden inverso
    cierre = ''
    for ch in reversed(stack):
        cierre += '}' if ch == '{' else ']'
    return truncado + cierre


# ─────────────────────────────────────────────
# EXTRACCIÓN CON CLAUDE — TEXTO
# ─────────────────────────────────────────────
def extract_with_claude_text(text: str, doc_type: TipoDocumento) -> dict:
    """Extrae campos del documento usando texto digital. Reintenta hasta 2 veces si el JSON es inválido."""
    client = get_claude_client()
    text_truncated = text[:18000] if len(text) > 18000 else text
    messages = [{
        "role": "user",
        "content": build_extraction_prompt(doc_type) + "\n\nDOCUMENTO:\n" + text_truncated
    }]

    last_json_error = None
    for intento in range(3):  # intento inicial + hasta 2 reintentos
        try:
            raw, tokens = _llamar_claude(
                client, model="claude-sonnet-4-6", max_tokens=4096,
                system=SYSTEM_PROMPT, messages=messages
            )
            datos = _parsear_json(raw)
            datos["_tokens_used"] = tokens
            return datos
        except json.JSONDecodeError as e:
            last_json_error = e
            if intento < 2:
                time.sleep(1)
            continue
        except Exception as e:
            return {"error": str(e), "_ocr_method": "text"}

    return {"error": f"JSON inválido tras reintentos: {str(last_json_error)}", "_ocr_method": "text"}


# ─────────────────────────────────────────────
# EXTRACCIÓN CON CLAUDE VISION — IMÁGENES
# ─────────────────────────────────────────────
def extract_with_claude_vision(images: list[dict], doc_type: TipoDocumento) -> dict:
    """
    Envía imágenes del documento a Claude Vision para OCR + extracción.
    Funciona con PDFs escaneados, formularios impresos, fotos de documentos.
    """
    client = get_claude_client()

    content = [{
        "type": "text",
        "text": build_extraction_prompt(doc_type) + "\n\nA continuación las imágenes del documento:"
    }]

    for img in images[:4]:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["data"]
            }
        })

    messages = [{"role": "user", "content": content}]
    last_json_error = None
    for intento in range(3):  # intento inicial + hasta 2 reintentos
        try:
            raw, tokens = _llamar_claude(
                client, model="claude-sonnet-4-6", max_tokens=4096,
                system=SYSTEM_PROMPT, messages=messages
            )
            result = _parsear_json(raw)
            result["_ocr_method"] = "vision"
            result["_tokens_used"] = tokens
            return result
        except json.JSONDecodeError as e:
            last_json_error = e
            if intento < 2:
                time.sleep(1)
            continue
        except Exception as e:
            return {"error": str(e), "_ocr_method": "vision"}

    return {"error": f"JSON inválido en Vision tras reintentos: {str(last_json_error)}", "_ocr_method": "vision"}


# ─────────────────────────────────────────────
# IDENTIFICACIÓN DE TIPO CON VISIÓN
# ─────────────────────────────────────────────
def _identificar_tipo_con_vision(images: list, filename: str) -> TipoDocumento:
    """
    Cuando no se puede identificar el tipo por texto/nombre, usa Claude Vision
    para ver el documento y determinar qué tipo es.
    """
    client = get_claude_client()
    content = [{"type": "text", "text": (
        "Mira este documento de comercio exterior y responde SOLO con una de estas palabras exactas:\n"
        "pedimento_borrador / factura_comercial / carta_318 / cove / packing_list / bl / desconocido\n\n"
        "- pedimento_borrador: documento aduanal mexicano con clave de pedimento, aduana, régimen\n"
        "- factura_comercial: invoice/factura con precio, vendedor, comprador\n"
        "- carta_318: carta o checklist de regla 3.1.8\n"
        "- cove: comprobante de valor electrónico\n"
        "- packing_list: lista de empaque con pesos y bultos\n"
        "- bl: Bill of Lading, guía aérea o AWB con shipper/consignee\n"
        "- desconocido: cualquier otro\n\n"
        "Responde SOLO la palabra, sin explicación."
    )}]
    for img in images[:2]:
        content.append({"type": "image", "source": {"type": "base64", "media_type": img["media_type"], "data": img["data"]}})

    try:
        msg = get_claude_client().messages.create(
            model="claude-sonnet-4-6", max_tokens=20,
            system="Responde solo la palabra del tipo de documento.",
            messages=[{"role": "user", "content": content}]
        )
        tipo_str = msg.content[0].text.strip().lower()
        for t in TipoDocumento:
            if t.value == tipo_str:
                return t
    except Exception:
        pass
    # Fallback: intentar por nombre de archivo
    return identify_document_type("", filename)


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
                # Si tipo es DESCONOCIDO, pedir a Claude Vision que identifique el tipo
                if doc_type == TipoDocumento.DESCONOCIDO:
                    doc_type = _identificar_tipo_con_vision(images, filename)
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
